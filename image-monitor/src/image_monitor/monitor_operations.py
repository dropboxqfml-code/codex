"""Read an anonymous, bounded view of existing monitor work.

This service owns the ordinary scan/native leases, but opens every database
read-only. It never plans, adopts, repairs, probes browsers, or retries saves.
``can_finish`` is a completed-file preflight; the explicit finish command still
has to establish browser ownership and absence before committing completion.
"""

from contextlib import contextmanager
from datetime import UTC, datetime

from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_finish import (
    _paths,
    finish_completed_candidate,
    read_completed_report,
)
from image_monitor.candidate_policy import classify_candidate_detail
from image_monitor.candidate_save_policy import MAX_MONITOR_SAVE_IMAGES
from image_monitor.candidate_save_selection import (
    MANIFEST_NAME,
    MONITOR_MANIFEST_NAME,
    _database_path,
    read_selection,
    select_candidate_save,
    selection_service_blocked,
)
from image_monitor.candidate_store import (
    MAX_DETAIL_RESULT_BYTES,
    CandidateDetailStore,
    detail_service_blocked,
)
from image_monitor.monitor_batch_runtime import (
    MONITOR_SCOPE,
    _candidate,
    _eligible_permit,
    reconstruct_permit,
)
from image_monitor.monitor_save_ledger import (
    LEDGER_NAME,
    MAX_TASKS,
    LedgerStore,
    task_native_base,
    task_work_root,
)
from image_monitor.native_state import PendingSave, session_id, shared_state_path
from image_monitor.native_ui import NativeSaveLock, NativeUIError
from image_monitor.queue import QueueStore
from image_monitor.saved_catalog import (
    MAX_PENDING_BYTES,
    _check_native_children,
    _error_type,
    _existing,
    _root,
    _task_directories,
    _verify_source,
)
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_runtime import (
    DEFAULT_SCOPE,
    SERVICE_SCOPE,
    _control,
    _list_service_blocked,
    _stamp,
    _stored_time,
)
from image_monitor.watch_store import WatchStore

MAX_OPERATION_ROWS = 20
OPERATIONS_ROW_STATUSES = frozenset(
    {
        "candidate_uninspected",
        "candidate_detail_needs_review",
        "save_ready",
        "save_planned",
        "save_active",
        "save_completed",
        "save_unavailable",
        "save_needs_review",
    }
)
OPERATIONS_REASONS = frozenset(
    {
        "no_existing_work",
        "candidate_detail_required",
        "candidate_detail_requires_review",
        "save_ready",
        "save_planned",
        "save_completed",
        "save_unavailable",
        "save_requires_review",
        "pending_save_requires_review",
        "completed_save_can_finish",
        "service_cooldown",
        "service_access_blocked",
        "navigation_in_progress",
        "another_scan_owns_this_scope",
        "native_save_in_progress",
        "operations_require_review",
        "requested_stop",
    }
)
ROW_REASONS = OPERATIONS_REASONS
_COUNTS = (
    "candidate_uninspected",
    "save_ready",
    "save_planned",
    "save_active",
    "save_completed",
    "save_unavailable",
    "save_needs_review",
)
_WHERE = "watch_name=? AND gallery_type=? AND gallery_id=? AND keyword=? AND search_type=?"


class _Cancelled(Exception):
    pass


class _NativeBusy(Exception):
    pass


def _stop(should_stop):
    if should_stop is not None:
        value = should_stop()
        if type(value) is not bool:
            raise ValueError("The operations stop condition must return a boolean")
        if value:
            raise _Cancelled


def _snapshot(status, reason, *, error_type=None):
    return {
        "status": status,
        "reason": reason,
        "error_type": error_type,
        **dict.fromkeys(_COUNTS, 0),
        "wait_until": None,
        "can_finish": False,
        "rows": [],
        "rows_omitted": 0,
    }


@contextmanager
def _native_lock():
    owner = NativeSaveLock()
    try:
        owner.__enter__()
    except NativeUIError as error:
        raise _NativeBusy from error
    try:
        yield
    finally:
        owner.__exit__(None, None, None)


def _pending():
    path = _plain_path(shared_state_path())
    if _existing(path) and path.stat().st_size > MAX_PENDING_BYTES:
        raise ValueError("Pending-save metadata exceeds its limit")
    return PendingSave(path).read()


def _add(snapshot, status, reason, image_count=None, *, count=True):
    if count and status in _COUNTS:
        snapshot[status] += 1
    order = len(snapshot["rows"]) + snapshot["rows_omitted"] + 1
    if len(snapshot["rows"]) == MAX_OPERATION_ROWS:
        snapshot["rows_omitted"] += 1
        return
    snapshot["rows"].append(
        {"order": order, "status": status, "reason": reason, "image_count": image_count}
    )


def _controls(queue, tasks, details, now, should_stop):
    """Validate every persisted control before choosing a public priority."""
    state = WatchStore(queue).get_state(MONITOR_SCOPE)
    control = _control(state)
    blocked = detail_service_blocked(queue)
    blocked = selection_service_blocked(queue) or blocked
    blocked = _list_service_blocked(queue) or blocked
    controls = [control, *(task["control"] for task in tasks)]
    for name in (MANIFEST_NAME, MONITOR_MANIFEST_NAME):
        selection = read_selection(_database_path(queue).parent / name)
        if selection is not None:
            controls.append(selection["control"])
    for detail in details:
        _stop(should_stop)
        result = detail["result"]
        if isinstance(result, dict) and "control" in result:
            if not isinstance(result["control"], dict):
                raise ValueError("Detail navigation control is invalid")
            controls.append(result["control"])
    due, in_flight = now, False
    for item in controls:
        _stop(should_stop)
        for key in ("blocked", "in_flight"):
            if key in item and type(item[key]) is not bool:
                raise ValueError("Navigation control is invalid")
        blocked = blocked or item.get("blocked") is True
        in_flight = in_flight or item.get("in_flight") is True
        for key in ("started_at", "finished_at", "next_eligible_at"):
            if key in item:
                instant = _stored_time(item[key])
                if key == "next_eligible_at":
                    due = max(due, instant)
    shared = queue.connection.execute(
        "SELECT not_before FROM service_limits WHERE scope=?", (SERVICE_SCOPE,)
    ).fetchone()
    if shared is not None:
        due = max(due, _stored_time(shared[0]))
    return blocked, in_flight, due


def _details(queue, should_stop):
    if queue.schema_version < 5:
        return []
    rows = queue.connection.execute(
        "SELECT attempt_id,length(CAST(result_json AS BLOB)) FROM candidate_details WHERE "
        + _WHERE
        + " ORDER BY started_at,attempt_id LIMIT ?",
        (*MONITOR_SCOPE.key(), MAX_TASKS + 1),
    ).fetchall()
    if len(rows) > MAX_TASKS:
        raise ValueError("Existing detail metadata exceeds its limit")
    details = []
    baseline = WatchStore(queue).get_state(MONITOR_SCOPE)["baseline"]
    for row in rows:
        _stop(should_stop)
        if row[1] is not None and row[1] > MAX_DETAIL_RESULT_BYTES:
            raise ValueError("Existing detail evidence exceeds its limit")
        detail = CandidateDetailStore(queue).get(row[0])
        candidate = _candidate(queue, detail["post_id"])
        if detail["first_scan_id"] != candidate["first_scan_id"]:
            raise ValueError("Detail discovery binding changed")
        if detail["status"] not in {"started", "failed", "completed"}:
            raise ValueError("Unknown detail status")
        if not isinstance(baseline, dict) or (
            _stored_time(detail["baseline_observed_at"]) != _stored_time(baseline["observed_at"])
        ):
            raise ValueError("Detail baseline binding changed")
        started = _stored_time(detail["started_at"])
        if started < max(
            _stored_time(detail["baseline_observed_at"]), _stored_time(candidate["first_seen_at"])
        ):
            raise ValueError("Detail observation timing changed")
        if detail["status"] == "started":
            if detail["finished_at"] is not None or detail["result"] is not None:
                raise ValueError("Unfinished detail contains finish evidence")
        elif _stored_time(detail["finished_at"]) < started or not isinstance(
            detail["result"], dict
        ):
            raise ValueError("Finished detail evidence is invalid")
        details.append(detail)
    return details


def _detail_row(queue, detail):
    if detail["status"] != "completed":
        return "candidate_detail_needs_review", "candidate_detail_requires_review", None
    result = detail["result"]
    observation = result.get("private_observation") if isinstance(result, dict) else None
    if not isinstance(observation, dict):
        raise ValueError("Completed detail evidence is missing")
    if observation.get("status") == "http_error" and observation.get("http_status") in {404, 410}:
        return "save_unavailable", "save_unavailable", None
    snapshot = observation.get("snapshot")
    if observation.get("status") != "observed" or not isinstance(snapshot, dict):
        raise ValueError("Completed detail body evidence is missing")
    candidate = _candidate(queue, detail["post_id"])
    baseline = WatchStore(queue).get_state(MONITOR_SCOPE)["baseline"]
    classification = classify_candidate_detail(candidate, baseline, snapshot)
    if classification["time_status"] == "unknown":
        return "candidate_detail_needs_review", "candidate_detail_requires_review", None
    images, counts = snapshot.get("images"), snapshot.get("image_counts")
    if not isinstance(images, list) or not isinstance(counts, dict):
        raise ValueError("Completed detail image evidence is missing")
    included, pending = counts.get("included_unique"), counts.get("pending")
    if (
        type(included) is not int
        or not 0 <= included <= 500
        or included != len(images)
        or type(pending) is not int
        or not 0 <= pending <= 500
    ):
        raise ValueError("Completed detail image counts are invalid")
    if classification["time_status"] == "before_baseline" or included == pending == 0:
        return "save_unavailable", "save_unavailable", included
    if pending or not 1 <= included <= MAX_MONITOR_SAVE_IMAGES:
        return "candidate_detail_needs_review", "candidate_detail_requires_review", included
    _candidate_record, permit = _eligible_permit(queue, detail)
    return "save_ready", "save_ready", permit.image_count


def _can_finish(queue, tasks, pending, legacy, batch, should_stop):
    unfinished = [task for task in tasks if task["status"] in {"started", "needs_review"}]
    if len(unfinished) != 1:
        return False
    task = unfinished[0]
    current = session_id()
    if type(current) is not int or not 0 <= current <= 2**32 - 1:
        return False
    if task["native_session"] != current:
        return False
    permit = reconstruct_permit(queue, task)
    base = _plain_path(task_native_base(task, batch, legacy))
    _stop(should_stop)
    try:
        if pending is not None:
            previous = read_completed_report(base, pending, permit=permit)
            with QueueStore(_plain_path(base / "queue.sqlite"), read_only=True) as native:
                finish_completed_candidate(
                    native, permit, base=base, pending=pending, report=previous
                )
        else:
            _paths(base, task["control"].get("browser_identity"))
            _verify_source(base, permit, lambda: _stop_bool(should_stop))
    except (OSError, ValueError, NativeUIError):
        return False
    _stop(should_stop)
    return True


def _stop_bool(should_stop):
    _stop(should_stop)
    return False


def _verify_unavailable(task, base):
    recorded = task["result"]
    if not (
        type(recorded.get("http_status")) is int
        and recorded["http_status"] in {404, 410}
        and recorded.get("no_native_work") is True
        and recorded.get("browser_closed") is True
        and recorded.get("shared_pending_retained") is False
    ):
        raise ValueError("Unavailable work lacks its no-native-work proof")
    database = _plain_path(base / "queue.sqlite")
    if not _existing(database):
        raise ValueError("Unavailable native records are missing")
    with QueueStore(database, read_only=True) as native:
        summary = native.summary()
        if (
            summary["posts"]
            or summary["jobs"]
            or native.list_artifacts()
            or native.connection.execute("SELECT COUNT(*) FROM post_observations").fetchone()[0]
        ):
            raise ValueError("Unavailable work contains native image work")
    images = _plain_path(base / "images")
    if _existing(images, directory=True) and any(images.iterdir()):
        raise ValueError("Unavailable work contains image output")


def _load(watch, legacy, batch, now, should_stop):
    database, ledger_path = watch / "watch.sqlite", watch / LEDGER_NAME
    _existing(watch, directory=True)
    _existing(legacy, directory=True)
    _existing(batch, directory=True)
    directories = _task_directories(batch)
    if not _existing(database):
        _check_native_children(legacy, set(), legacy=True)
        if _existing(ledger_path) or directories or _existing(watch / MONITOR_MANIFEST_NAME):
            raise ValueError("Existing output lost its discovery records")
        return _snapshot("empty", "no_existing_work")
    with watch_run_lock(database, DEFAULT_SCOPE), _native_lock():
        _stop(should_stop)
        pending = _pending()
        with QueueStore(database, read_only=True) as queue:
            if queue.summary()["posts"] or queue.summary()["jobs"]:
                raise ValueError("Discovery records contain image work")
            if _existing(ledger_path):
                with LedgerStore(
                    ledger_path,
                    watch_root=watch,
                    legacy_root=legacy,
                    batch_root=batch,
                    read_only=True,
                    create=False,
                ) as ledger:
                    tasks = ledger.list_tasks()
                    result = _read(queue, tasks, pending, watch, legacy, batch, now, should_stop)
                    if tasks != ledger.list_tasks():
                        raise ValueError("Existing save bindings changed")
            else:
                if directories:
                    raise ValueError("Existing task output lost its ledger")
                result = _read(
                    queue, [], pending, watch, legacy, batch, now, should_stop, standalone=True
                )
        _stop(should_stop)
        if _pending() != pending or _task_directories(batch) != directories:
            raise ValueError("Existing save ownership changed")
        return result


def _read(queue, tasks, pending, watch, legacy, batch, now, should_stop, *, standalone=False):
    result = _snapshot("ready", "no_existing_work")
    details = _details(queue, should_stop)
    managed = {task["task_id"] for task in tasks if task["output_kind"] == "managed"}
    if _task_directories(batch) - managed:
        raise ValueError("Existing task output has no frozen binding")
    sessions = {
        task["native_session"]
        for task in tasks
        if task["output_kind"] == "legacy" and task["native_session"] is not None
    }
    represented = {task["post_id"] for task in tasks}
    if standalone:
        selection = read_selection(watch / MONITOR_MANIFEST_NAME)
        if selection is not None:
            permit = select_candidate_save(queue, MONITOR_SCOPE, watch / MONITOR_MANIFEST_NAME)
            if permit is None:
                raise ValueError("Existing selection lost its frozen evidence")
            current = session_id()
            base = _plain_path(legacy / f"session-{current}")
            if _existing(base, directory=True):
                sessions.add(current)
                if pending is None:
                    proofs = _verify_source(base, permit, lambda: _stop_bool(should_stop))
                    represented.add(permit.reference_snapshot["post_id"])
                    _add(result, "save_completed", "save_completed", len(proofs))
    _check_native_children(legacy, sessions, legacy=True)
    bases = set()
    for task in tasks:
        _stop(should_stop)
        permit = reconstruct_permit(queue, task)
        if task["output_kind"] == "managed":
            root = _plain_path(task_work_root(task, batch, legacy))
            _check_native_children(
                root, set() if task["native_session"] is None else {task["native_session"]}
            )
        if task["native_session"] is not None:
            base = _plain_path(task_native_base(task, batch, legacy))
            if base in bases:
                raise ValueError("Existing tasks share native output")
            bases.add(base)
        if task["status"] == "completed":
            _verify_source(base, permit, lambda: _stop_bool(should_stop))
        elif task["status"] == "unavailable":
            _verify_unavailable(task, base)
        status = {
            "planned": "save_planned",
            "started": "save_active",
            "completed": "save_completed",
            "unavailable": "save_unavailable",
            "needs_review": "save_needs_review",
        }[task["status"]]
        reason = {
            "save_active": "save_requires_review",
            "save_needs_review": "save_requires_review",
        }.get(status, status)
        _add(result, status, reason, permit.image_count)
    detail_review = False
    for detail in details:
        _stop(should_stop)
        if detail["post_id"] in represented:
            continue
        status, reason, images = _detail_row(queue, detail)
        detail_review = detail_review or status == "candidate_detail_needs_review"
        _add(result, status, reason, images)
    if queue.schema_version >= 4:
        attempted = (
            (
                "AND NOT EXISTS (SELECT 1 FROM candidate_details d WHERE d.watch_name=c.watch_name "
                "AND d.gallery_type=c.gallery_type AND d.gallery_id=c.gallery_id "
                "AND d.keyword=c.keyword "
                "AND d.search_type=c.search_type AND d.post_id=c.post_id)"
            )
            if queue.schema_version >= 5
            else ""
        )
        uninspected = queue.connection.execute(
            "SELECT COUNT(*) FROM watch_candidates c WHERE " + _WHERE + " " + attempted,
            MONITOR_SCOPE.key(),
        ).fetchone()[0]
        result["candidate_uninspected"] = uninspected
        for _index in range(min(uninspected, MAX_OPERATION_ROWS - len(result["rows"]))):
            _add(result, "candidate_uninspected", "candidate_detail_required", count=False)
        result["rows_omitted"] += max(
            0, uninspected - sum(row["status"] == "candidate_uninspected" for row in result["rows"])
        )
    blocked, in_flight, due = _controls(queue, tasks, details, now, should_stop)
    result["wait_until"] = _stamp(due) if due > now else None
    result["can_finish"] = _can_finish(queue, tasks, pending, legacy, batch, should_stop)
    if blocked:
        result.update(status="needs_review", reason="service_access_blocked")
    elif in_flight:
        result.update(status="needs_review", reason="navigation_in_progress")
    elif result["can_finish"]:
        result.update(status="needs_review", reason="completed_save_can_finish")
    elif pending is not None:
        result.update(status="busy", reason="pending_save_requires_review")
    elif result["save_active"] or result["save_needs_review"]:
        result.update(status="needs_review", reason="save_requires_review")
    elif detail_review:
        result.update(status="needs_review", reason="candidate_detail_requires_review")
    elif due > now:
        result["reason"] = "service_cooldown"
    else:
        for count, reason in (
            ("save_ready", "save_ready"),
            ("save_planned", "save_planned"),
            ("candidate_uninspected", "candidate_detail_required"),
            ("save_completed", "save_completed"),
            ("save_unavailable", "save_unavailable"),
        ):
            if result[count]:
                result["reason"] = reason
                break
        else:
            result["status"] = "empty"
    return result


def load_monitor_operations(watch_root, legacy_root, batch_root, *, now=None, should_stop=None):
    """Return sanitized existing work and an advisory completed-only finish preflight."""
    try:
        if should_stop is not None and not callable(should_stop):
            raise ValueError("The operations stop condition must be callable")
        _stop(should_stop)
        now = datetime.now(UTC) if now is None else now
        _stamp(now)
        watch, legacy, batch = (_root(value) for value in (watch_root, legacy_root, batch_root))
        roots = (watch, legacy, batch)
        if any(
            a == b or a.is_relative_to(b) for i, a in enumerate(roots) for b in roots[i + 1 :]
        ) or any(b.is_relative_to(a) for i, a in enumerate(roots) for b in roots[i + 1 :]):
            raise ValueError("Monitor operations require separate local roots")
        return _load(watch, legacy, batch, now, should_stop)
    except _Cancelled:
        return _snapshot("cancelled", "requested_stop")
    except WatchRunBusy:
        return _snapshot("busy", "another_scan_owns_this_scope")
    except _NativeBusy:
        return _snapshot("busy", "native_save_in_progress")
    except Exception as error:
        return _snapshot("needs_review", "operations_require_review", error_type=_error_type(error))
