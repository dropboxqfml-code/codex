"""Save a bounded sequence of independently frozen monitor candidates.

The discovery database never receives image jobs. Each managed task owns a
separate native work root, and a durable started task is never an automatic
retry target. Previously completed work is verified locally before it is skipped.
"""

import re
import time
import uuid
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_finish import _paths, verify_completed_candidate_files
from image_monitor.candidate_policy import classify_candidate_detail
from image_monitor.candidate_save_policy import (
    MAX_MONITOR_SAVE_IMAGES,
    MAX_SAVE_IMAGES,
    make_candidate_save_permit,
)
from image_monitor.candidate_save_selection import (
    MANIFEST_NAME,
    MONITOR_MANIFEST_NAME,
    read_selection,
    select_candidate_save,
)
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_save_ledger import (
    LEDGER_NAME,
    RECENT_LEDGER_NAME,
    LedgerStore,
    monitor_save_claims,
    other_monitor_save_claims,
    recent_save_claims,
    task_native_base,
    task_work_root,
)
from image_monitor.monitor_settings import load_monitor_settings
from image_monitor.monitor_setup_retry import (
    FOREGROUND_RETRY_EXHAUSTED,
    FOREGROUND_RETRY_REASON,
    PARTIAL_RETRY_EXHAUSTED,
    PARTIAL_RETRY_REASON,
    verify_setup_retry,
)
from image_monitor.monitor_trial_progress import trial_stage
from image_monitor.native_probe import write_report
from image_monitor.native_state import PendingSave, session_id, shared_state_path
from image_monitor.native_ui import NativeSaveLock, NativeUIError, require_windows
from image_monitor.paths import destination, plan_folder
from image_monitor.post_worker import run_post_save, share_setup_diagnostics
from image_monitor.queue import QueueError, QueueStore
from image_monitor.retry import retry_after
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_planner import next_poll_at
from image_monitor.watch_runtime import DEFAULT_SCOPE, SERVICE_SCOPE, _eligibility, _stamp
from image_monitor.watch_store import WatchScope, WatchStore, _record

MONITOR_SCOPE = WatchScope("목록 감시", "normal", "comic_new6", "ai", "search_subject_memo")
MAX_DETAILS = 64
MAX_BATCH_POSTS = 2
_FILE_FIELDS = ("saved_filename", "detected_format", "file_size", "width", "height", "frames")


class _Clock:
    def now(self):
        return datetime.now(UTC)

    def wait(self, seconds):
        time.sleep(seconds)


def _candidate(queue, post_id, scope=MONITOR_SCOPE):
    row = queue.connection.execute(
        "SELECT * FROM watch_candidates WHERE watch_name=? AND gallery_type=? AND gallery_id=? "
        "AND keyword=? AND search_type=? AND post_id=?",
        (*scope.key(), post_id),
    ).fetchone()
    if row is None:
        raise QueueError("The batch candidate discovery is missing")
    return _record(row)


def reconstruct_permit(watch_queue, task, scope=MONITOR_SCOPE):
    """Re-derive the exact original permit; never trust a ledger identity alone."""
    candidate = _candidate(watch_queue, task["post_id"], scope)
    baseline = WatchStore(watch_queue).get_state(scope)["baseline"]
    detail = CandidateDetailStore(watch_queue).get(task["detail_attempt_id"])
    if detail is None or candidate["first_scan_id"] != task["first_scan_id"]:
        raise QueueError("The batch discovery observation changed")
    permit = make_candidate_save_permit(candidate, baseline, detail)
    if (
        permit.fingerprint != task["permit_fingerprint"]
        or permit.post_url != task["post_url"]
        or permit.watch_name != scope.watch_name
    ):
        raise QueueError("The batch permit no longer matches its frozen source")
    return permit


def verify_task_files(task, permit, legacy_root, batch_root):
    """Verify a task's exact native root. Caller owns the native/watch locks."""
    base = _plain_path(task_native_base(task, Path(batch_root), Path(legacy_root)))
    database = _plain_path(base / "queue.sqlite")
    if not database.is_file():
        raise QueueError("The completed batch native queue is missing")
    with QueueStore(database, read_only=True) as store:
        summary, _ = verify_completed_candidate_files(store, permit, base=base)
    return summary


def _clear_pending():
    if PendingSave(shared_state_path()).read() is not None:
        raise NativeUIError("An unresolved native save requires inspection")


def _preflight(task, permit, legacy_root, batch_root, native_session):
    if type(native_session) is not int or native_session < 0:
        raise NativeUIError("The batch Windows session is invalid")
    root = _plain_path(task_work_root(task, batch_root, legacy_root))
    base = _plain_path(root / f"session-{native_session}")
    reference = permit.reference_snapshot
    plan = plan_folder(
        watch_name=permit.watch_name,
        gallery_id=reference["gallery_id"],
        post_id=reference["post_id"],
        nickname=reference["nickname"],
        ip_display=reference.get("ip_display"),
        first_seen_at=permit.first_seen_at,
        published_at=datetime.fromisoformat(reference["published_at"]),
    )
    _plain_path(destination(base / "images", plan))


class _NavigationObserver:
    """Persist service controls and the owned browser identity before navigation."""

    def __init__(
        self,
        queue,
        ledger,
        task,
        clock,
        *,
        require_identity=True,
        scope=MONITOR_SCOPE,
        interval_seconds=60,
    ):
        self.queue, self.ledger, self.task, self.clock = queue, ledger, task, clock
        self.scope = scope
        self.require_identity = require_identity
        self.interval_seconds = interval_seconds
        self.http_status = self.next_at = self.browser_identity = None
        self.blocked = False
        self.list_window = None
        self.native_document_ready = False

    def before(self):
        if self.native_document_ready:
            raise NativeUIError("Another document navigation requires a new monitor turn")
        state = WatchStore(self.queue).get_state(self.scope)
        if _eligibility(self.queue, state, self.clock.now())[0] != "ready":
            raise NativeUIError("Batch navigation requires service eligibility")
        identity = PendingSave(shared_state_path()).read()
        if identity is not None:
            _paths(
                task_native_base(self.task, self.ledger.batch_root, self.ledger.legacy_root),
                identity,
            )
            self.browser_identity = identity
        elif self.require_identity:
            raise NativeUIError("The owned batch browser identity is missing")
        started = self.clock.now()
        self.next_at = next_poll_at(started, interval_seconds=self.interval_seconds)
        self.queue.defer_service(SERVICE_SCOPE, self.next_at)
        control = {
            "blocked": False,
            "in_flight": True,
            "started_at": _stamp(started),
            "next_eligible_at": _stamp(self.next_at),
            "http_status": None,
        }
        if self.browser_identity is not None:
            control["browser_identity"] = self.browser_identity
        self.ledger.update_control(self.task["task_id"], control)

    def allow_lists_after_document(self, expected_url, enter_context):
        self.list_window = (expected_url, enter_context)

    def after(self, response, error):
        finished = self.clock.now()
        self.next_at = next_poll_at(finished, interval_seconds=self.interval_seconds)
        self.queue.defer_service(SERVICE_SCOPE, self.next_at)
        self.http_status = response.status if response is not None else None
        self.blocked = self.http_status in {401, 403}
        observed_retry_after = None
        if response is not None and self.http_status in {429, 503}:
            try:
                value = response.header_value("retry-after")
            except Exception:
                value = None
            if isinstance(value, str):
                observed_retry_after = value[:256]
                try:
                    due = retry_after(observed_retry_after, finished)
                except ValueError:
                    due = None
                if due is not None:
                    self.next_at = max(self.next_at, due)
        self.queue.defer_service(SERVICE_SCOPE, self.next_at)
        control = {
            "blocked": self.blocked,
            "in_flight": False,
            "finished_at": _stamp(finished),
            "next_eligible_at": _stamp(self.next_at),
            "http_status": self.http_status,
            "retry_after": observed_retry_after,
            "error_type": type(error).__name__ if error is not None else None,
        }
        if self.browser_identity is not None:
            control["browser_identity"] = self.browser_identity
        self.ledger.update_control(self.task["task_id"], control)
        if self.list_window is not None and not self.native_document_ready:
            expected_url, enter = self.list_window
            if (
                error is None
                and type(self.http_status) is int
                and 200 <= self.http_status < 300
                and getattr(response, "url", None) == expected_url
            ):
                # Navigation and its persisted cooldown have finished. The worker
                # retains the visible browser, exact candidate, and native save lock.
                self.native_document_ready = True
                enter(self.next_at)


def _root(value):
    root = _plain_path(Path(value).absolute())
    if str(root).startswith(("\\\\", "//")):
        raise NativeUIError("Batch saving requires local roots")
    return root.resolve()


def _task_directories(batch_root):
    """Inspect only fixed direct task children; never rediscover work by scanning files."""
    directory = _plain_path(batch_root / "tasks")
    if not directory.exists():
        return set()
    if not directory.is_dir():
        raise QueueError("The batch task directory is invalid")
    identifiers = set()
    for index, child in enumerate(directory.iterdir()):
        if index >= 1000:
            raise QueueError("The batch output range requires inspection")
        _plain_path(child)
        if not child.is_dir() or not re.fullmatch(r"[0-9a-f]{32}", child.name):
            raise QueueError("The batch output has an unrecognized task directory")
        identifiers.add(child.name)
    return identifiers


def _details(queue):
    if queue.schema_version < 5:
        return []
    rows = queue.connection.execute(
        "SELECT attempt_id FROM candidate_details WHERE watch_name=? AND gallery_type=? "
        "AND gallery_id=? AND keyword=? AND search_type=? AND status='completed' "
        "ORDER BY started_at,attempt_id LIMIT ?",
        (*MONITOR_SCOPE.key(), MAX_DETAILS + 1),
    ).fetchall()
    if len(rows) > MAX_DETAILS:
        raise QueueError("The bounded batch detail range requires review")
    return [CandidateDetailStore(queue).get(row[0]) for row in rows]


def _eligible_permit(queue, detail):
    result = detail.get("result")
    observation = result.get("private_observation") if isinstance(result, dict) else None
    if not isinstance(observation, dict):
        raise QueueError("Completed batch detail evidence is missing")
    if observation.get("status") == "http_error" and observation.get("http_status") in {404, 410}:
        return None
    snapshot = observation.get("snapshot")
    if observation.get("status") != "observed" or not isinstance(snapshot, dict):
        raise QueueError("Completed batch body evidence is missing")
    candidate = _candidate(queue, detail["post_id"])
    baseline = WatchStore(queue).get_state(MONITOR_SCOPE)["baseline"]
    classification = classify_candidate_detail(candidate, baseline, snapshot)
    if classification["time_status"] == "before_baseline":
        return None
    images, counts = snapshot.get("images"), snapshot.get("image_counts")
    if not isinstance(images, list) or not isinstance(counts, dict):
        raise QueueError("Completed batch image evidence is missing")
    if (
        not images
        and type(counts.get("included_unique")) is int
        and type(counts.get("pending")) is int
        and counts["included_unique"] == counts["pending"] == 0
    ):
        return None
    return candidate, make_candidate_save_permit(candidate, baseline, detail)


def _legacy_selection(watch_root, legacy_root, name):
    selection = read_selection(_plain_path(watch_root / name))
    if selection is None:
        if legacy_root.exists():
            if not legacy_root.is_dir():
                raise QueueError("The earlier native output root is invalid")
            for index, child in enumerate(legacy_root.iterdir()):
                if index >= MAX_DETAILS:
                    raise QueueError("The earlier native output requires inspection")
                _plain_path(child)
                if child.name.startswith("session-") or child.name in {
                    "queue.sqlite",
                    "images",
                    "runs",
                }:
                    raise QueueError("The earlier native selection is missing")
    return selection


def _adopt_legacy(queue, ledger, watch_root, legacy_root, batch_root, clock):
    if _legacy_selection(watch_root, legacy_root, MONITOR_MANIFEST_NAME) is None:
        return 0
    manifest = watch_root / MONITOR_MANIFEST_NAME
    with QueueStore(watch_root / "watch.sqlite", read_only=True) as readonly:
        permit = select_candidate_save(readonly, MONITOR_SCOPE, manifest)
        if permit is None:
            raise QueueError("The earlier frozen monitor selection is missing")
        post_id = permit.reference_snapshot["post_id"]
        existing = ledger.get_for_post(post_id)
        if existing is not None:
            if existing["output_kind"] != "legacy":
                raise QueueError("The earlier selected post already has another batch root")
            return 0
        candidate = _candidate(readonly, post_id)
        detail = CandidateDetailStore(readonly).get(permit.detail_attempt_id)
        native_session = session_id()
        # Do not persist completed adoption until the original files are proven.
        with NativeSaveLock():
            _clear_pending()
            with QueueStore(
                _plain_path(legacy_root / f"session-{native_session}" / "queue.sqlite"),
                read_only=True,
            ) as native:
                verified, _ = verify_completed_candidate_files(
                    native, permit, base=legacy_root / f"session-{native_session}"
                )
        ledger.adopt_completed(
            candidate,
            detail,
            permit,
            native_session=native_session,
            result=verified,
            now=clock.now(),
        )
    return 1


def _worker_completed(worker, permit, observer):
    counts = worker.get("job_counts")
    return (
        worker.get("status") == "post_completed"
        and worker.get("browser_closed") is True
        and worker.get("shared_pending_retained") is False
        and isinstance(counts, dict)
        and set(counts) == {"observed", "completed", "unresolved"}
        and all(type(value) is int for value in counts.values())
        and counts
        == {"observed": permit.image_count, "completed": permit.image_count, "unresolved": 0}
        and type(observer.http_status) is int
        and 200 <= observer.http_status < 300
    )


def _focus_stop_reason(worker, completed, total, retrying):
    if worker.get("status") == "manual_review" and worker.get("error_type") == "NativeFocusError":
        if worker.get("last_stage") == "automatic_foreground_check":
            return FOREGROUND_RETRY_EXHAUSTED if retrying else FOREGROUND_RETRY_REASON
        if (
            worker.get("last_stage") == "pre_input_check"
            and worker.get("reason")
            == "Automatic saving stopped when the dedicated window lost focus"
            and type(completed) is int
            and 0 < completed < total
            and "active_attempt" not in worker
            and "last_preinput_attempt" not in worker
        ):
            return PARTIAL_RETRY_EXHAUSTED if retrying else PARTIAL_RETRY_REASON
    return "native_batch_task_requires_review"


def _verified_new_files(worker, verified, previous):
    """Match this invocation’s fresh native saves to exactly the verified suffix."""
    suffix = verified["saved_files"][previous:]
    saved = worker.get("saved_files")
    if not isinstance(saved, list) or not suffix or len(saved) != len(suffix):
        raise QueueError("The resumed native worker did not return the remaining file slots")
    for fresh, expected in zip(saved, suffix, strict=True):
        if not isinstance(fresh, dict) or any(fresh.get(k) != expected[k] for k in _FILE_FIELDS):
            raise QueueError("The resumed native worker returned a different file slot")
    return len(suffix)


def _unavailable_without_work(worker, observer, task, legacy_root, batch_root):
    """A missing post is terminal only when no native/image work ever began."""
    if not (
        observer.http_status in {404, 410}
        and worker.get("status") == "manual_review"
        and worker.get("last_stage") == "post_inspection"
        and worker.get("error_type") == "NativeUIError"
        and worker.get("browser_closed") is True
        and worker.get("shared_pending_retained") is False
        and worker.get("saved_files") == []
        and "active_attempt" not in worker
    ):
        return False
    try:
        with NativeSaveLock():
            _clear_pending()
            base = _plain_path(task_native_base(task, batch_root, legacy_root))
            database = _plain_path(base / "queue.sqlite")
            if not database.is_file():
                return False
            with QueueStore(database, read_only=True) as native:
                summary = native.summary()
                return (
                    summary["posts"] == summary["jobs"] == 0
                    and not native.list_artifacts()
                    and native.connection.execute(
                        "SELECT COUNT(*) FROM post_observations"
                    ).fetchone()[0]
                    == 0
                )
    except Exception:
        return False


def _deadline(report, due):
    report["next_eligible_at_local"] = due.astimezone(ZoneInfo("Asia/Seoul")).isoformat()


def _public_initial_focus(snapshot):
    if not isinstance(snapshot, dict):
        return {}
    flags = {
        key: snapshot[key]
        for key in ("target_exists", "target_foreground", "belongs_to_target")
        if type(snapshot.get(key)) is bool
    }
    if "foreground_hwnd" in snapshot:
        handle = snapshot["foreground_hwnd"]
        if handle is None or type(handle) is int and handle >= 0:
            flags["foreground_identified"] = bool(handle)
    return flags


def share_batch_report(report):
    fields = (
        "schema_version",
        "mode",
        "status",
        "last_stage",
        "error_type",
        "reason",
        "browser",
        "browser_version",
        "browser_closed",
        "shared_pending_retained",
        "adopted_count",
        "already_completed_count",
        "unavailable_count",
        "tasks_planned",
        "tasks_started",
        "tasks_completed",
        "tasks_remaining",
        "tasks_needing_review",
        "max_tasks",
        "http_status",
        "next_eligible_at_local",
        "worker_last_stage",
        "worker_images_completed",
        "setup_retry_started",
        "partial_retry_started",
        "native_stage",
        "native_file_type",
        "native_suggested_suffix",
        "focus_at_failure",
        "focus_at_pause",
        "focus_pauses",
        "shutdown",
    )
    public = {key: report[key] for key in fields if key in report}
    if (
        report.get("setup_retry_started") is True
        and report.get("previous_failure_reason") == FOREGROUND_RETRY_REASON
    ):
        public["previous_failure_reason"] = FOREGROUND_RETRY_REASON
    if (
        report.get("partial_retry_started") is True
        and report.get("previous_failure_reason") == PARTIAL_RETRY_REASON
    ):
        public["previous_failure_reason"] = PARTIAL_RETRY_REASON
        for key in ("previously_verified_files", "newly_saved_files"):
            value = report.get(key)
            if type(value) is int and 0 < value < MAX_MONITOR_SAVE_IMAGES:
                public[key] = value
    if report.get("mode") == "bounded_monitor_automatic_save" and report.get(
        "worker_last_stage"
    ) in ("automatic_foreground_check", "pre_input_check"):
        for key in ("focus_at_failure", "focus_at_pause"):
            flags = _public_initial_focus(public.pop(key, None))
            if flags:
                public[key] = flags
    public.update(share_setup_diagnostics(report, stage_key="worker_last_stage"))
    error_type = public.get("error_type")
    if error_type is not None and (
        not isinstance(error_type, str)
        or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", error_type)
    ):
        public["error_type"] = None
    files = report.get("saved_files", [])
    mode = report.get("mode")
    limit = MAX_SAVE_IMAGES
    if mode in {"bounded_monitor_candidate_native_batch", "bounded_monitor_automatic_save"}:
        limit = MAX_MONITOR_SAVE_IMAGES
        if (
            mode == "bounded_monitor_candidate_native_batch"
            and report.get("max_tasks") == MAX_BATCH_POSTS
        ):
            limit *= MAX_BATCH_POSTS
    public["saved_file_count"] = len(files)
    public["saved_files"] = [
        {key: item[key] for key in _FILE_FIELDS if key in item} for item in files[:limit]
    ]
    return public


def _prior_pilot_claims(watch_root, legacy_root):
    # Both fixed pilots target normal/comic_new6. Their independent observations
    # and output roots remain untouched while a physical post can have only one owner.
    claims = monitor_save_claims(watch_root / "watch.sqlite")
    selections = (
        _legacy_selection(watch_root, legacy_root, MANIFEST_NAME),
        read_selection(_plain_path(watch_root / MONITOR_MANIFEST_NAME)),
    )
    claims.update(value["post_id"] for value in selections if value is not None)
    return claims


def recent_save_exclusions(watch_root, legacy_root, save_root):
    """Return existing claimed legacy and terminal recent posts under the caller's lease."""
    watch_root, legacy_root, save_root = map(_root, (watch_root, legacy_root, save_root))
    excluded = _prior_pilot_claims(watch_root, legacy_root)
    existing_dirs = _task_directories(save_root)
    path = _plain_path(watch_root / RECENT_LEDGER_NAME)
    if not path.exists():
        if existing_dirs:
            raise QueueError("Recent save output lost its original ledger")
        return excluded
    with LedgerStore(
        path,
        watch_root=watch_root,
        legacy_root=legacy_root,
        batch_root=save_root,
        scope=DEFAULT_SCOPE.key(),
        read_only=True,
    ) as ledger:
        tasks = ledger.list_tasks()
    if existing_dirs - {task["task_id"] for task in tasks}:
        raise QueueError("Recent save output has no original task binding")
    for task in tasks:
        if task["status"] in {"started", "needs_review"}:
            raise QueueError("An unfinished recent save requires review")
        if task["status"] in {"completed", "unavailable"}:
            excluded.add(task["post_id"])
    return excluded


def _recent_detail(queue, state, handoff):
    from image_monitor.watch_detail_source import recent_scan_candidates

    latest = state["latest_scan"]
    if latest is None or latest["scan_id"] != handoff["scan_id"]:
        raise QueueError("The selected recent scan changed")
    summary, rows = recent_scan_candidates(queue, DEFAULT_SCOPE, state)
    if summary is None:
        raise QueueError("The selected recent scan cannot be verified")
    candidate = next((r for r in rows if r["attempt_id"] == handoff["attempt_id"]), None)
    if candidate is None:
        raise QueueError("The selected observation is outside the verified recent window")
    detail = CandidateDetailStore(queue).get(handoff["attempt_id"])
    permit = make_candidate_save_permit(candidate, state["baseline"], detail)
    if permit.fingerprint != handoff["fingerprint"]:
        raise QueueError("The selected recent permit changed")
    return candidate, detail, permit


def _monitor_detail(queue, state, handoff):
    candidate = _candidate(queue, handoff["post_id"])
    detail = CandidateDetailStore(queue).get(handoff["attempt_id"])
    permit = make_candidate_save_permit(candidate, state["baseline"], detail)
    if permit.fingerprint != handoff["fingerprint"]:
        raise QueueError("The selected monitor permit changed")
    return candidate, detail, permit


def run_recent_save(
    watch_root, legacy_root, save_root, handoff, *, clock=None, save_runner=run_post_save
):
    """Save only the qualified trial post identified by an immutable private handoff."""
    if not isinstance(handoff, dict) or set(handoff) != {"scan_id", "attempt_id", "fingerprint"}:
        raise QueueError("An exact recent candidate handoff is required")
    return run_monitor_batch(
        watch_root,
        legacy_root,
        save_root,
        max_tasks=1,
        clock=clock,
        save_runner=save_runner,
        recent_handoff=handoff,
    )


class _StopBeforeSave(Exception):
    pass


def run_monitor_batch(
    watch_root,
    legacy_root,
    batch_root,
    *,
    max_tasks=MAX_BATCH_POSTS,
    clock=None,
    save_runner=run_post_save,
    should_stop=None,
    recent_handoff=None,
    monitor_handoff=None,
    during_native_save=None,
):
    require_windows()
    scope = DEFAULT_SCOPE if recent_handoff is not None else MONITOR_SCOPE
    ledger_name = RECENT_LEDGER_NAME if recent_handoff is not None else LEDGER_NAME
    automatic = monitor_handoff is not None
    if during_native_save is not None and (not automatic or not callable(during_native_save)):
        raise NativeUIError("Concurrent list checks require an automatic monitor handoff")
    handoff_fields = {"post_id", "attempt_id", "fingerprint"}
    retry_fields = handoff_fields | {"retry_task_id", "prior_run"}
    retrying = isinstance(monitor_handoff, dict) and set(monitor_handoff) in (
        retry_fields,
        retry_fields | {"previously_verified_files"},
    )
    if automatic and (
        recent_handoff is not None
        or max_tasks != 1
        or not isinstance(monitor_handoff, dict)
        or not retrying
        and set(monitor_handoff) != handoff_fields
    ):
        raise NativeUIError("Automatic saving requires one exact monitor candidate")
    if recent_handoff is not None and max_tasks != 1:
        raise NativeUIError("A recent save requires exactly one task")
    if type(max_tasks) is not int or not 1 <= max_tasks <= MAX_BATCH_POSTS:
        raise NativeUIError("Choose one or two new batch save attempts")
    if should_stop is not None and (max_tasks != 1 or not callable(should_stop)):
        raise NativeUIError("A dashboard stop condition requires a single save attempt")

    def stop_if_requested():
        if should_stop is not None:
            stopped = should_stop()
            if type(stopped) is not bool:
                raise NativeUIError("The save stop condition must return a boolean")
            if stopped:
                raise _StopBeforeSave

    clock = clock or _Clock()
    _stamp(clock.now())
    watch_root, legacy_root, batch_root = map(_root, (watch_root, legacy_root, batch_root))
    roots = (watch_root, legacy_root, batch_root)
    if any(a == b or a.is_relative_to(b) for a in roots for b in roots if a is not b):
        raise NativeUIError("Batch discovery, prior output and new output roots must be separate")
    run_directory = batch_root / "batch-runs" / uuid.uuid4().hex
    run_directory.mkdir(parents=True)
    report_path = run_directory / "report.json"
    report = {
        "schema_version": 1,
        "mode": "recent_candidate_native_save"
        if recent_handoff is not None
        else "bounded_monitor_automatic_save"
        if automatic
        else "bounded_monitor_candidate_native_batch",
        "status": "monitor_batch_manual_review",
        "last_stage": "existing_watch_check",
        "error_type": None,
        "browser": "chrome",
        "browser_closed": True,
        "shared_pending_retained": False,
        "adopted_count": 0,
        "already_completed_count": 0,
        "unavailable_count": 0,
        "tasks_planned": 0,
        "tasks_started": 0,
        "tasks_completed": 0,
        "tasks_remaining": 0,
        "tasks_needing_review": 0,
        "max_tasks": max_tasks,
        "saved_files": [],
    }
    if automatic:
        report["worker_images_completed"] = 0
        report["setup_retry_started"] = False
        report["partial_retry_started"] = False
    active = ledger = None
    database = _plain_path(watch_root / "watch.sqlite")
    try:
        stop_if_requested()
        if not database.is_file():
            report.update(status="monitor_batch_no_candidates", reason="existing_watch_required")
        else:
            with (
                watch_run_lock(database, DEFAULT_SCOPE) as watch_lease,
                QueueStore(database) as queue,
            ):
                if queue.summary()["posts"] or queue.summary()["jobs"]:
                    raise QueueError("The batch requires the separate discovery database")
                state = WatchStore(queue).get_state(scope)
                if state["baseline"] is None:
                    report.update(
                        status="monitor_batch_no_candidates", reason="existing_baseline_required"
                    )
                else:
                    selected = None
                    recent_claims = set()
                    if recent_handoff is not None:
                        selected = _recent_detail(queue, state, recent_handoff)
                        if selected[0]["post_id"] in _prior_pilot_claims(watch_root, legacy_root):
                            raise QueueError("An earlier pilot already owns this physical post")
                    elif automatic:
                        recent_claims = other_monitor_save_claims(database)
                        selected = _monitor_detail(queue, state, monitor_handoff)
                    else:
                        recent_claims = recent_save_claims(database)
                    interval = (
                        load_monitor_settings(watch_root)["interval_seconds"] if automatic else 60
                    )
                    with NativeSaveLock():
                        _clear_pending()
                    ledger_path = _plain_path(watch_root / ledger_name)
                    ledger_existed = ledger_path.exists()
                    existing_directories = _task_directories(batch_root)
                    if existing_directories and not ledger_path.is_file():
                        raise QueueError("Existing batch output lost its original ledger")
                    with LedgerStore(
                        ledger_path,
                        watch_root=watch_root,
                        legacy_root=legacy_root,
                        batch_root=batch_root,
                        create=not ledger_existed,
                        scope=scope.key(),
                    ) as ledger:
                        managed_ids = {
                            task["task_id"]
                            for task in ledger.list_tasks()
                            if task["output_kind"] == "managed"
                        }
                        if existing_directories - managed_ids:
                            raise QueueError("Existing batch output has no original task binding")
                        unfinished = [
                            t
                            for t in ledger.list_tasks()
                            if t["status"] in {"started", "needs_review"}
                        ]
                        if retrying and (
                            len(unfinished) != 1
                            or unfinished[0]["task_id"] != monitor_handoff["retry_task_id"]
                            or unfinished[0]["status"] != "needs_review"
                            or unfinished[0]["post_id"] != monitor_handoff["post_id"]
                        ):
                            report.update(reason="setup_retry_binding_changed")
                        elif unfinished and not retrying:
                            report.update(reason="unfinished_batch_requires_reconcile")
                        elif any(
                            t["output_kind"] == "legacy" and t["status"] != "completed"
                            for t in ledger.list_tasks()
                        ):
                            report.update(reason="unfinished_legacy_requires_review")
                        else:
                            report["last_stage"] = "completed_file_verification"
                            for task in ledger.list_tasks():
                                stop_if_requested()
                                if task["status"] == "completed":
                                    permit = reconstruct_permit(queue, task, scope)
                                    with NativeSaveLock():
                                        _clear_pending()
                                        verify_task_files(task, permit, legacy_root, batch_root)
                                    report["already_completed_count"] += 1
                                elif task["status"] == "unavailable":
                                    report["unavailable_count"] += 1
                            stop_if_requested()
                            if recent_handoff is None:
                                report["adopted_count"] = _adopt_legacy(
                                    queue, ledger, watch_root, legacy_root, batch_root, clock
                                )
                                report["already_completed_count"] += report["adopted_count"]
                            if selected is not None:
                                candidate, detail, permit = selected
                                previous = ledger.get_for_post(candidate["post_id"])
                                if automatic and candidate["post_id"] in recent_claims:
                                    report.update(
                                        status="monitor_batch_no_candidates",
                                        reason="selected_candidate_already_claimed",
                                    )
                                    return report
                                if retrying:
                                    task = unfinished[0]
                                    pending = [task]
                                else:
                                    task = ledger.plan(candidate, detail, permit, now=clock.now())
                                    report["tasks_planned"] = int(previous is None)
                                    pending = [task] if task["status"] == "planned" else []
                            else:
                                report["last_stage"] = "candidate_planning"
                                for detail in _details(queue):
                                    stop_if_requested()
                                    if (
                                        detail["post_id"] in recent_claims
                                        or ledger.get_for_post(detail["post_id"]) is not None
                                    ):
                                        continue
                                    eligible = _eligible_permit(queue, detail)
                                    if eligible is not None:
                                        candidate, permit = eligible
                                        ledger.plan(candidate, detail, permit, now=clock.now())
                                        report["tasks_planned"] += 1
                                pending = [
                                    t
                                    for t in ledger.list_tasks()
                                    if t["status"] == "planned" and t["output_kind"] == "managed"
                                ]
                            if not pending:
                                reason = "no_unsaved_reviewed_candidates"
                                if selected is not None:
                                    reason = (
                                        "selected_candidate_already_completed"
                                        if task["status"] == "completed"
                                        else "candidate_unavailable"
                                    )
                                report.update(status="monitor_batch_no_candidates", reason=reason)
                            for task in pending[:max_tasks]:
                                if task["post_id"] in recent_claims:
                                    raise QueueError(
                                        "A recent save already owns this physical post"
                                    )
                                stop_if_requested()
                                state = WatchStore(queue).get_state(scope)
                                eligibility, due = _eligibility(queue, state, clock.now())
                                if eligibility == "blocked":
                                    report.update(
                                        status="monitor_batch_manual_review",
                                        reason="access_block_requires_review",
                                        last_stage="blocked",
                                    )
                                    break
                                if eligibility == "waiting":
                                    _deadline(report, due)
                                    remaining = (due - clock.now()).total_seconds()
                                    if report["tasks_started"] == 0 or remaining > 60:
                                        report.update(
                                            status="monitor_batch_waiting",
                                            reason="persisted_cooldown",
                                        )
                                        break
                                    getattr(clock, "wait", time.sleep)(max(0, remaining))
                                    eligibility, due = _eligibility(queue, state, clock.now())
                                    if eligibility != "ready":
                                        report.update(
                                            status="monitor_batch_waiting",
                                            reason="cooldown_not_elapsed",
                                        )
                                        break
                                permit = reconstruct_permit(queue, task, scope)
                                if (
                                    retrying
                                    and permit.fingerprint != monitor_handoff["fingerprint"]
                                ):
                                    raise QueueError("The prior setup attempt's permit changed")
                                native_session = session_id()
                                _preflight(task, permit, legacy_root, batch_root, native_session)
                                work_root = task_work_root(task, batch_root, legacy_root)
                                # After starting a durable task the native worker owns it
                                # through verification and cleanup, even if the dashboard exits.
                                stop_if_requested()
                                if retrying:
                                    report["last_stage"] = "setup_retry_evidence"
                                    with NativeSaveLock():
                                        prior_run, prior_reason, previous = verify_setup_retry(
                                            ledger, task, permit
                                        )
                                        expected_previous = monitor_handoff.get(
                                            "previously_verified_files", 0
                                        )
                                        if (
                                            prior_run != monitor_handoff["prior_run"]
                                            or type(expected_previous) is not int
                                            or previous != expected_previous
                                            or (prior_reason == PARTIAL_RETRY_REASON)
                                            != ("previously_verified_files" in monitor_handoff)
                                        ):
                                            raise QueueError(
                                                "The prior native run or verified prefix changed"
                                            )
                                        active = ledger.start_setup_retry(
                                            task, prior_run=prior_run, now=clock.now()
                                        )
                                    if prior_reason == PARTIAL_RETRY_REASON:
                                        report.update(
                                            partial_retry_started=True,
                                            previously_verified_files=previous,
                                            previous_failure_reason=prior_reason,
                                        )
                                    else:
                                        report["setup_retry_started"] = True
                                    if prior_reason == FOREGROUND_RETRY_REASON:
                                        report["previous_failure_reason"] = prior_reason
                                else:
                                    if work_root.exists() and any(work_root.iterdir()):
                                        raise QueueError(
                                            "A planned batch task already has native output"
                                        )
                                    active = ledger.start(
                                        task["task_id"], clock.now(), native_session=native_session
                                    )
                                report["tasks_started"] += 1
                                report.update(
                                    last_stage="native_post_worker",
                                    browser_closed=None,
                                    shared_pending_retained=None,
                                )
                                if automatic:
                                    report["worker_images_completed"] = None
                                observer = _NavigationObserver(
                                    queue,
                                    ledger,
                                    active,
                                    clock,
                                    require_identity=automatic or save_runner is run_post_save,
                                    scope=scope,
                                    interval_seconds=interval,
                                )
                                try:
                                    with ExitStack() as window:
                                        if during_native_save is not None:
                                            observer.allow_lists_after_document(
                                                permit.post_url,
                                                lambda due: window.enter_context(
                                                    during_native_save(watch_lease, due)
                                                ),
                                            )
                                        trial_stage("Chrome에서 이미지 저장 및 파일 검증")
                                        worker = save_runner(
                                            task_work_root(active, batch_root, legacy_root),
                                            "chrome",
                                            permit.post_url,
                                            candidate_permit=permit,
                                            navigation_observer=observer,
                                            **({"automatic_start": True} if automatic else {}),
                                        )
                                    if not isinstance(worker, dict):
                                        raise QueueError(
                                            "The native worker did not return a report"
                                        )
                                except BaseException as error:
                                    ledger.finish(
                                        active["task_id"],
                                        status="needs_review",
                                        result={"error_type": type(error).__name__},
                                        now=clock.now(),
                                    )
                                    active = None
                                    raise
                                report.update(
                                    browser_closed=worker.get("browser_closed"),
                                    shared_pending_retained=worker.get("shared_pending_retained"),
                                    http_status=observer.http_status,
                                    worker_last_stage=worker.get("last_stage"),
                                )
                                report.update(share_setup_diagnostics(worker))
                                if automatic:
                                    counts = worker.get("job_counts")
                                    if (
                                        isinstance(counts, dict)
                                        and all(
                                            type(counts.get(key)) is int
                                            and 0 <= counts[key] <= permit.image_count
                                            for key in ("observed", "completed", "unresolved")
                                        )
                                        and counts["completed"] + counts["unresolved"]
                                        == counts["observed"]
                                    ):
                                        report["worker_images_completed"] = counts["completed"]
                                for key in (
                                    "native_stage",
                                    "native_file_type",
                                    "native_suggested_suffix",
                                    "focus_at_failure",
                                    "focus_at_pause",
                                    "focus_pauses",
                                    "shutdown",
                                ):
                                    if key in worker:
                                        report[key] = worker[key]
                                version = worker.get("browser_version")
                                if isinstance(version, str) and re.fullmatch(
                                    r"[0-9.]{1,40}", version
                                ):
                                    report["browser_version"] = version
                                if observer.next_at is not None:
                                    _deadline(report, observer.next_at)
                                if _unavailable_without_work(
                                    worker, observer, active, legacy_root, batch_root
                                ):
                                    ledger.finish(
                                        active["task_id"],
                                        status="unavailable",
                                        result={
                                            "http_status": observer.http_status,
                                            "no_native_work": True,
                                            "browser_closed": True,
                                            "shared_pending_retained": False,
                                        },
                                        now=clock.now(),
                                    )
                                    active = None
                                    report["unavailable_count"] += 1
                                    report.update(
                                        status="monitor_batch_completed",
                                        last_stage="complete",
                                        reason="candidate_unavailable",
                                    )
                                    continue
                                if not _worker_completed(worker, permit, observer):
                                    failure = {
                                        "worker_status": worker.get("status"),
                                        "error_type": worker.get("error_type"),
                                    }
                                    reason = "native_batch_task_requires_review"
                                    if automatic:
                                        reason = _focus_stop_reason(
                                            worker,
                                            report["worker_images_completed"],
                                            permit.image_count,
                                            retrying,
                                        )
                                        if reason in (
                                            FOREGROUND_RETRY_EXHAUSTED,
                                            PARTIAL_RETRY_EXHAUSTED,
                                        ):
                                            failure["reason"] = reason
                                    ledger.finish(
                                        active["task_id"],
                                        status="needs_review",
                                        result=failure,
                                        now=clock.now(),
                                    )
                                    active = None
                                    report.update(
                                        status="monitor_batch_cancelled"
                                        if worker.get("error_type") == "KeyboardInterrupt"
                                        else "monitor_batch_manual_review",
                                        reason=reason,
                                        error_type=worker.get("error_type"),
                                    )
                                    if observer.blocked:
                                        report.update(
                                            reason="access_block_requires_review",
                                            last_stage="blocked",
                                        )
                                    elif observer.http_status in {429, 503}:
                                        report.update(reason="service_retry_after")
                                    elif observer.http_status in {404, 410}:
                                        report.update(reason="selected_candidate_unavailable")
                                    break
                                try:
                                    with NativeSaveLock():
                                        _clear_pending()
                                        verified = verify_task_files(
                                            active, permit, legacy_root, batch_root
                                        )
                                        if report.get("partial_retry_started"):
                                            new_count = _verified_new_files(
                                                worker,
                                                verified,
                                                report["previously_verified_files"],
                                            )
                                except BaseException as error:
                                    ledger.finish(
                                        active["task_id"],
                                        status="needs_review",
                                        result={"error_type": type(error).__name__},
                                        now=clock.now(),
                                    )
                                    active = None
                                    raise
                                ledger.finish(
                                    active["task_id"],
                                    status="completed",
                                    result=verified,
                                    now=clock.now(),
                                )
                                active = None
                                if report.get("partial_retry_started"):
                                    report["newly_saved_files"] = new_count
                                report["tasks_completed"] += 1
                                report["saved_files"].extend(verified["saved_files"])
                                report.update(
                                    status="monitor_batch_completed",
                                    last_stage="complete",
                                    reason=None,
                                )
                            report["tasks_remaining"] = sum(
                                t["status"] == "planned" for t in ledger.list_tasks()
                            )
                if queue.summary()["posts"] or queue.summary()["jobs"]:
                    raise QueueError("Batch saving changed the discovery image queue")
    except _StopBeforeSave:
        report.update(status="monitor_batch_cancelled", reason="requested_stop")
    except WatchRunBusy:
        report.update(status="monitor_batch_busy", reason="another_scan_owns_this_scope")
    except KeyboardInterrupt:
        report.update(
            status="monitor_batch_cancelled", reason="cancelled", error_type="KeyboardInterrupt"
        )
    except Exception as error:
        report.update(
            status="monitor_batch_manual_review",
            reason="batch_requires_review",
            error_type=type(error).__name__,
        )
    finally:
        if active is not None and ledger is not None:
            # If the context already closed, the committed started row remains
            # an audit record and still blocks any automatic retry.
            try:
                ledger.finish(
                    active["task_id"],
                    status="needs_review",
                    result={"error_type": report.get("error_type")},
                    now=clock.now(),
                )
            except Exception:
                pass
        # A failed/interrupting worker can exit the ledger context before the
        # normal counter update. Read existing state only; never recreate it.
        if (watch_root / ledger_name).is_file():
            try:
                with LedgerStore(
                    watch_root / ledger_name,
                    watch_root=watch_root,
                    legacy_root=legacy_root,
                    batch_root=batch_root,
                    read_only=True,
                    create=False,
                    scope=scope.key(),
                ) as existing:
                    tasks = existing.list_tasks()
                report["tasks_remaining"] = sum(
                    task["status"] == "planned" and task["output_kind"] == "managed"
                    for task in tasks
                )
                report["tasks_needing_review"] = sum(
                    task["status"] in {"started", "needs_review"}
                    or task["output_kind"] == "legacy"
                    and task["status"] != "completed"
                    for task in tasks
                )
            except Exception:
                pass
        report["report_path"] = str(report_path)
        write_report(report_path, report)
    return report
