"""Durable, single-attempt saves for independently frozen monitor candidates.

The caller holds the shared watch lease. This separate database never changes
the discovery schema or native image queues. An explicit retry can resume a
failed completion setup after the caller proves that native input never began.
"""

import json
import re
import sqlite3
import stat
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_save_policy import MONITOR_SCOPE, REVIEWED_SCOPE, CandidateSavePermit
from image_monitor.queue import QueueError, _json_data, _matches_schema, _schema_objects, _time

LEDGER_NAME = "monitor-save-ledger.sqlite"
RECENT_LEDGER_NAME = "watch-save-ledger.sqlite"
_LEDGER_NAMES = {MONITOR_SCOPE: LEDGER_NAME, REVIEWED_SCOPE: RECENT_LEDGER_NAME}
SCHEMA_VERSION = 1
APPLICATION_ID = 0x494D424C
MAX_JSON_BYTES = 64 * 1024
MAX_TASKS = 1000
_SCOPE_FIELDS = ("watch_name", "gallery_type", "gallery_id", "keyword", "search_type")
_RESULT_STATES = {"completed", "needs_review", "unavailable"}
_SCHEMA = """
CREATE TABLE ledger_meta (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    watch_root TEXT NOT NULL,
    legacy_root TEXT NOT NULL,
    batch_root TEXT NOT NULL,
    scope_json TEXT NOT NULL
);
CREATE TABLE save_tasks (
    task_id TEXT PRIMARY KEY,
    post_id TEXT NOT NULL UNIQUE,
    post_url TEXT NOT NULL,
    first_scan_id TEXT NOT NULL,
    detail_attempt_id TEXT NOT NULL,
    permit_fingerprint TEXT NOT NULL,
    output_kind TEXT NOT NULL CHECK(output_kind IN ('legacy','managed')),
    relative_root TEXT,
    status TEXT NOT NULL CHECK(status IN
        ('planned','started','completed','needs_review','unavailable')),
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    native_session INTEGER,
    result_json TEXT,
    control_json TEXT NOT NULL,
    CHECK((output_kind='legacy' AND relative_root IS NULL) OR
          (output_kind='managed' AND relative_root='tasks/'||task_id)),
    CHECK((status='planned' AND started_at IS NULL AND finished_at IS NULL
           AND native_session IS NULL AND result_json IS NULL) OR
          (status='started' AND started_at IS NOT NULL AND finished_at IS NULL
           AND native_session IS NOT NULL AND result_json IS NULL) OR
          (status IN ('completed','needs_review','unavailable') AND started_at IS NOT NULL
           AND finished_at IS NOT NULL AND native_session IS NOT NULL AND result_json IS NOT NULL))
);
"""


def _require(condition, message):
    if not condition:
        raise QueueError(message)


def _root(value):
    path = _plain_path(Path(value).absolute())
    _require(not str(path).startswith(("\\\\", "//")), "Ledger roots must be local and plain")
    if path.exists():
        _require(stat.S_ISDIR(path.lstat().st_mode), "Ledger roots must be directories")
    return path.resolve()


def _roots(watch_root, legacy_root, batch_root):
    roots = tuple(_root(value) for value in (watch_root, legacy_root, batch_root))
    for index, left in enumerate(roots):
        for right in roots[index + 1 :]:
            _require(
                left != right and not left.is_relative_to(right) and not right.is_relative_to(left),
                "Discovery, legacy and batch roots must be separate",
            )
    return roots


def _regular(path):
    info = _plain_path(path).lstat()
    _require(
        stat.S_ISREG(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
        "The monitor save ledger must be a regular non-reparse file",
    )


def _stamp(value):
    _require(isinstance(value, datetime), "Ledger timing must be timezone-aware")
    try:
        return _time(value)
    except (TypeError, ValueError, AttributeError) as error:
        raise QueueError("Ledger timing must be timezone-aware") from error


def _stored_stamp(value):
    try:
        _require(isinstance(value, str), "Stored ledger timing is invalid")
        return _stamp(datetime.fromisoformat(value))
    except (TypeError, ValueError, OverflowError) as error:
        raise QueueError("Stored ledger timing is invalid") from error


def _uuid(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def _json(value, label):
    _require(isinstance(value, dict), f"{label} must be a dictionary")
    encoded = _json_data(value, label)
    _require(len(encoded.encode("utf-8")) <= MAX_JSON_BYTES, f"{label} exceeds its metadata limit")
    return encoded


def _unique(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, "Ledger JSON contains duplicate fields")
        value[key] = item
    return value


def _parse(value, label):
    _require(isinstance(value, str), f"{label} is invalid")
    _require(len(value.encode("utf-8")) <= MAX_JSON_BYTES, f"{label} exceeds its metadata limit")
    try:
        result = json.loads(value, object_pairs_hook=_unique)
    except (ValueError, TypeError, RecursionError) as error:
        raise QueueError(f"{label} is invalid") from error
    _json(result, label)
    return result


def _control(value):
    _json(value, "Ledger navigation control")
    _require(type(value.get("blocked")) is bool, "Ledger control requires a boolean block state")
    if "in_flight" in value:
        _require(type(value["in_flight"]) is bool, "Ledger in-flight state must be boolean")
    for key in ("started_at", "finished_at", "next_eligible_at"):
        if key in value:
            _stored_stamp(value[key])
    if "http_status" in value:
        status = value["http_status"]
        _require(
            status is None or type(status) is int and 100 <= status <= 599,
            "Ledger HTTP status is invalid",
        )
    if "interval_seconds" in value:
        interval = value["interval_seconds"]
        _require(type(interval) is int and 60 <= interval <= 300, "Ledger interval is invalid")


def _record(row):
    if row is None:
        return None
    result = dict(row)
    raw_result = result.pop("result_json")
    result["result"] = _parse(raw_result, "Ledger task result") if raw_result is not None else None
    result["control"] = _parse(result.pop("control_json"), "Ledger navigation control")
    _control(result["control"])
    _require(_uuid(result["task_id"]), "Stored ledger task identity is invalid")
    _require(
        isinstance(result["post_id"], str) and re.fullmatch(r"[1-9][0-9]{0,19}", result["post_id"]),
        "Stored ledger post identity is invalid",
    )
    for key in ("first_scan_id", "detail_attempt_id"):
        _require(_uuid(result[key]), "Stored ledger observation identity is invalid")
    _require(
        isinstance(result["permit_fingerprint"], str)
        and re.fullmatch(r"[0-9a-f]{64}", result["permit_fingerprint"]),
        "Stored ledger permit fingerprint is invalid",
    )
    _require(
        result["post_url"]
        == f"https://gall.dcinside.com/board/view/?id=comic_new6&no={result['post_id']}",
        "Stored ledger post URL is invalid",
    )
    _stored_stamp(result["created_at"])
    status = result["status"]
    _require(status in {"planned", "started", *_RESULT_STATES}, "Stored ledger status is invalid")
    if status == "planned":
        _require(
            all(
                result[key] is None
                for key in ("started_at", "finished_at", "native_session", "result")
            ),
            "A planned ledger task contains an attempted save",
        )
    else:
        _require(
            type(result["native_session"]) is int and 0 <= result["native_session"] <= 2**32 - 1,
            "Stored native session is invalid",
        )
        started = _stored_stamp(result["started_at"])
        _require(started >= _stored_stamp(result["created_at"]), "Stored ledger times conflict")
        if status in _RESULT_STATES:
            _require(
                _stored_stamp(result["finished_at"]) >= started and result["result"] is not None,
                "A finished ledger task has incomplete evidence",
            )
        else:
            _require(
                result["finished_at"] is None and result["result"] is None,
                "A started ledger task has invalid finish evidence",
            )
    task_work_root(result, Path("/batch"), Path("/legacy"), _validate_only=True)
    return result


def task_work_root(task, batch_root, legacy_root, *, _validate_only=False):
    """Derive a work root from a fixed kind and task UUID, never an arbitrary stored path."""
    _require(
        isinstance(task, dict) and _uuid(task.get("task_id")), "Ledger task identity is invalid"
    )
    kind = task.get("output_kind")
    if kind == "legacy":
        _require(task.get("relative_root") is None, "Legacy ledger output binding is invalid")
        return None if _validate_only else _root(legacy_root)
    _require(
        kind == "managed" and task.get("relative_root") == f"tasks/{task['task_id']}",
        "Managed ledger output binding is invalid",
    )
    return None if _validate_only else _root(_root(batch_root) / "tasks" / task["task_id"])


def task_native_base(task, batch_root, legacy_root):
    session = task.get("native_session") if isinstance(task, dict) else None
    _require(
        type(session) is int and 0 <= session <= 2**32 - 1, "A frozen native session is required"
    )
    return _root(task_work_root(task, batch_root, legacy_root) / f"session-{session}")


def is_setup_retry_candidate(task):
    """This ledger shape is necessary but not sufficient proof of a pre-input failure."""
    return (
        task["status"] == "needs_review"
        and task["output_kind"] == "managed"
        and task["result"]
        == {"worker_status": "manual_review", "error_type": "BrowserCompletionError"}
        and task["control"].get("blocked") is False
        and task["control"].get("in_flight") is False
        and task["control"].get("http_status") == 200
        and isinstance(task["control"].get("browser_identity"), dict)
        and "setup_retry" not in task["control"]
    )


class LedgerStore:
    """Keep immutable candidate bindings and committed attempt transitions."""

    def __init__(
        self,
        path,
        *,
        watch_root,
        legacy_root,
        batch_root,
        read_only=False,
        create=True,
        scope=MONITOR_SCOPE,
        immutable=False,
    ):
        self.watch_root, self.legacy_root, self.batch_root = _roots(
            watch_root, legacy_root, batch_root
        )
        checked = _plain_path(Path(path))
        # Windows may return a short-name parent for the same directory that
        # the ledger stores under its long name. Keep the exact fixed leaf.
        self.path = checked.parent.resolve() / checked.name
        _require(scope in _LEDGER_NAMES, "Unknown save ledger scope")
        self.scope = scope
        _require(
            self.path == self.watch_root / _LEDGER_NAMES[scope],
            "Ledger must stay beside its watch database with the scoped filename",
        )
        _require(
            self.watch_root.is_dir() and stat.S_ISDIR(self.watch_root.lstat().st_mode),
            "The existing watch directory is required",
        )
        _require(not immutable or read_only, "An immutable ledger must be read-only")
        self.read_only = read_only
        existed = self.path.exists()
        if existed:
            _regular(self.path)
        _require(
            existed or create and not read_only, "The existing monitor save ledger is required"
        )
        mode = "ro" if read_only else "rw" if existed or not create else "rwc"
        uri = self.path.as_uri() + f"?mode={mode}" + ("&immutable=1" if immutable else "")
        self.connection = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5)
        self.connection.row_factory = sqlite3.Row
        try:
            self.connection.execute("PRAGMA trusted_schema=OFF")
            self.connection.execute("PRAGMA busy_timeout=5000")
            if read_only:
                self.connection.execute("PRAGMA query_only=ON")
            if not existed and not read_only:
                with self._write():
                    application = self.connection.execute("PRAGMA application_id").fetchone()[0]
                    version = self.connection.execute("PRAGMA user_version").fetchone()[0]
                    if application == 0 and version == 0 and not _schema_objects(self.connection):
                        for statement in _SCHEMA.split(";"):
                            if statement.strip():
                                self.connection.execute(statement)
                        self.connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                        self.connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                        self.connection.execute(
                            "INSERT INTO ledger_meta VALUES(1,?,?,?,?)",
                            (*self._root_values(), json.dumps(self.scope, ensure_ascii=False)),
                        )
            self._check_schema()
            self._check_meta()
            self.list_tasks()
            if not read_only:
                self.connection.execute("PRAGMA synchronous=FULL")
        except BaseException:
            self.connection.close()
            raise

    def _root_values(self):
        return tuple(
            path.as_posix() for path in (self.watch_root, self.legacy_root, self.batch_root)
        )

    def _check_schema(self):
        _require(
            self.connection.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
            and self.connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
            and _matches_schema(self.connection, _SCHEMA),
            "Unknown monitor save ledger schema; existing data preserved",
        )

    def _check_meta(self):
        rows = self.connection.execute("SELECT * FROM ledger_meta").fetchall()
        _require(len(rows) == 1 and rows[0]["singleton"] == 1, "Ledger root metadata is invalid")
        row = rows[0]
        try:
            stored = tuple(_root(row[key]) for key in ("watch_root", "legacy_root", "batch_root"))
            scope = json.loads(row["scope_json"])
        except (TypeError, ValueError) as error:
            raise QueueError("Ledger root metadata is invalid") from error
        _require(
            stored == (self.watch_root, self.legacy_root, self.batch_root)
            and scope == list(self.scope),
            "Ledger roots or monitor scope changed",
        )

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def close(self):
        self.connection.close()

    @contextmanager
    def _write(self):
        _require(not self.read_only, "Monitor save ledger is read-only")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def list_tasks(self):
        count = self.connection.execute("SELECT COUNT(*) FROM save_tasks").fetchone()[0]
        _require(count <= MAX_TASKS, "Monitor save ledger exceeds its task limit")
        return [
            _record(row)
            for row in self.connection.execute(
                "SELECT * FROM save_tasks ORDER BY created_at,task_id"
            )
        ]

    def get_task(self, task_id):
        _require(_uuid(task_id), "Ledger task identity is invalid")
        return _record(
            self.connection.execute(
                "SELECT * FROM save_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        )

    def get_for_post(self, post_id):
        _require(
            isinstance(post_id, str) and re.fullmatch(r"[1-9][0-9]{0,19}", post_id),
            "Ledger post identity is invalid",
        )
        return _record(
            self.connection.execute(
                "SELECT * FROM save_tasks WHERE post_id=?", (post_id,)
            ).fetchone()
        )

    def _binding(self, candidate, detail, permit, output_kind, now):
        _require(isinstance(permit, CandidateSavePermit), "A frozen candidate permit is required")
        frozen, _baseline, frozen_detail, _snapshot = permit._evidence()
        _require(
            isinstance(candidate, dict)
            and isinstance(detail, dict)
            and tuple(candidate.get(key) for key in _SCOPE_FIELDS) == self.scope
            and tuple(detail.get(key) for key in _SCOPE_FIELDS) == self.scope
            and all(candidate.get(key) == frozen[key] for key in frozen)
            and detail == frozen_detail,
            "Ledger planning requires the exact frozen monitor observation",
        )
        _require(output_kind in {"legacy", "managed"}, "Ledger output kind is invalid")
        stamp = _stamp(now)
        _require(
            stamp >= _stored_stamp(frozen_detail["finished_at"]),
            "Ledger planning precedes its completed detail evidence",
        )
        fingerprint = permit.fingerprint
        binding = {
            "post_id": frozen["post_id"],
            "post_url": frozen["post_url"],
            "first_scan_id": frozen["first_scan_id"],
            "detail_attempt_id": permit.detail_attempt_id,
            "permit_fingerprint": fingerprint,
            "output_kind": output_kind,
        }
        return stamp, binding

    def plan(self, candidate, detail, permit, *, output_kind="managed", now):
        stamp, binding = self._binding(candidate, detail, permit, output_kind, now)
        with self._write():
            existing = self.get_for_post(binding["post_id"])
            if existing is not None:
                _require(
                    all(existing[key] == value for key, value in binding.items()),
                    "The frozen ledger candidate binding changed",
                )
                return existing
            count = self.connection.execute("SELECT COUNT(*) FROM save_tasks").fetchone()[0]
            _require(count < MAX_TASKS, "Monitor save ledger exceeds its task limit")
            task_id = uuid.uuid4().hex
            self.connection.execute(
                "INSERT INTO save_tasks VALUES(?,?,?,?,?,?,?,?,'planned',?,NULL,NULL,NULL,NULL,?)",
                (
                    task_id,
                    *(
                        binding[key]
                        for key in (
                            "post_id",
                            "post_url",
                            "first_scan_id",
                            "detail_attempt_id",
                            "permit_fingerprint",
                            "output_kind",
                        )
                    ),
                    f"tasks/{task_id}" if output_kind == "managed" else None,
                    stamp,
                    _json({"blocked": False}, "Ledger navigation control"),
                ),
            )
            return self.get_task(task_id)

    def adopt_completed(self, candidate, detail, permit, *, native_session, result, now):
        """Atomically import separately verified legacy files with no runnable gap.

        The caller must prove every old file under the shared watch and native
        locks before this call. Adoption never launches a writer or passes
        through a persisted started state.
        """
        stamp, binding = self._binding(candidate, detail, permit, "legacy", now)
        _require(
            type(native_session) is int and 0 <= native_session <= 2**32 - 1,
            "A frozen native Windows session is required",
        )
        encoded = _json(result, "Ledger task result")
        with self._write():
            existing = self.get_for_post(binding["post_id"])
            if existing is not None:
                _require(
                    all(existing[key] == value for key, value in binding.items()),
                    "The frozen legacy adoption binding changed",
                )
                if existing["status"] == "completed":
                    _require(
                        existing["native_session"] == native_session,
                        "The adopted native session changed",
                    )
                    return existing
                _require(
                    existing["status"] == "planned",
                    "An attempted legacy save requires completed-file reconciliation",
                )
                _require(
                    stamp >= _stored_stamp(existing["created_at"]),
                    "Legacy adoption precedes its plan",
                )
                changed = self.connection.execute(
                    "UPDATE save_tasks SET status='completed',started_at=?,finished_at=?,"
                    "native_session=?,result_json=? WHERE task_id=? AND status='planned'",
                    (stamp, stamp, native_session, encoded, existing["task_id"]),
                ).rowcount
                _require(changed == 1, "The legacy plan changed during adoption")
                return self.get_task(existing["task_id"])
            count = self.connection.execute("SELECT COUNT(*) FROM save_tasks").fetchone()[0]
            _require(count < MAX_TASKS, "Monitor save ledger exceeds its task limit")
            task_id = uuid.uuid4().hex
            self.connection.execute(
                "INSERT INTO save_tasks VALUES(?,?,?,?,?,?,'legacy',NULL,'completed',?,?,?,?,?,?)",
                (
                    task_id,
                    *(
                        binding[key]
                        for key in (
                            "post_id",
                            "post_url",
                            "first_scan_id",
                            "detail_attempt_id",
                            "permit_fingerprint",
                        )
                    ),
                    stamp,
                    stamp,
                    stamp,
                    native_session,
                    encoded,
                    _json({"blocked": False}, "Ledger navigation control"),
                ),
            )
            return self.get_task(task_id)

    def start(self, task_id, now, *, native_session):
        stamp = _stamp(now)
        _require(
            type(native_session) is int and 0 <= native_session <= 2**32 - 1,
            "A native Windows session is required",
        )
        with self._write():
            task = self.get_task(task_id)
            _require(
                task is not None and task["status"] == "planned", "Only a planned task may start"
            )
            _require(stamp >= _stored_stamp(task["created_at"]), "Task start precedes its plan")
            _require(
                self.connection.execute(
                    "SELECT 1 FROM save_tasks WHERE status IN ('started','needs_review') LIMIT 1"
                ).fetchone()
                is None,
                "An earlier monitor save requires reconciliation",
            )
            _require(
                not any(
                    item["control"]["blocked"] or item["control"].get("in_flight") is True
                    for item in self.list_tasks()
                ),
                "A monitor save access block requires explicit manual recovery",
            )
            changed = self.connection.execute(
                "UPDATE save_tasks SET status='started',started_at=?,native_session=? "
                "WHERE task_id=? AND status='planned'",
                (stamp, native_session, task_id),
            ).rowcount
            _require(changed == 1, "The planned task changed before starting")
            return self.get_task(task_id)

    def start_setup_retry(self, task, *, prior_run, now):
        """Consume the proved setup-only retry under the caller's watch and native locks."""
        stamp = _stamp(now)
        with self._write():
            latest = self.get_task(task["task_id"])
            _require(
                self.scope == MONITOR_SCOPE and latest == task and is_setup_retry_candidate(latest),
                "The failed setup task changed before retry",
            )
            control = latest["control"]
            _require(
                _uuid(prior_run)
                and control["browser_identity"].get("run_directory")
                == str(
                    task_native_base(latest, self.batch_root, self.legacy_root) / "runs" / prior_run
                )
                and stamp >= _stored_stamp(latest["finished_at"]),
                "The previous attempt is not bound to this retry",
            )
            _require(
                all(
                    other["control"]["blocked"] is False
                    and other["control"].get("in_flight") is not True
                    and (
                        other["task_id"] == latest["task_id"]
                        or other["status"] not in {"started", "needs_review"}
                    )
                    for other in self.list_tasks()
                ),
                "An additional unfinished task or service block requires review",
            )
            receipt = {
                "started_at": stamp,
                "prior_run": prior_run,
                "prior_started_at": latest["started_at"],
                "prior_finished_at": latest["finished_at"],
                "prior_control": control,
            }
            self.connection.execute(
                "UPDATE save_tasks SET status='started',started_at=?,finished_at=NULL,"
                "result_json=NULL,control_json=? WHERE task_id=?",
                (
                    stamp,
                    _json(control | {"setup_retry": receipt}, "Setup retry receipt"),
                    task["task_id"],
                ),
            )
            return self.get_task(task["task_id"])

    def finish(self, task_id, *, status, result, now):
        _require(status in _RESULT_STATES, "A finished ledger task needs a final status")
        return self._finish(task_id, status=status, result=result, now=now, allowed={"started"})

    def reconcile_completed(self, task_id, *, result, now):
        """Record separately verified completion; never make an attempt runnable again."""
        return self._finish(
            task_id, status="completed", result=result, now=now, allowed={"started", "needs_review"}
        )

    def _finish(self, task_id, *, status, result, now, allowed):
        encoded = _json(result, "Ledger task result")
        stamp = _stamp(now)
        with self._write():
            task = self.get_task(task_id)
            _require(
                task is not None and task["status"] in allowed, "Ledger completion state changed"
            )
            _require(stamp >= _stored_stamp(task["started_at"]), "Task finish precedes its start")
            changed = self.connection.execute(
                "UPDATE save_tasks SET status=?,finished_at=?,result_json=? "
                "WHERE task_id=? AND status=?",
                (status, stamp, encoded, task_id, task["status"]),
            ).rowcount
            _require(changed == 1, "The attempted task changed before completion")
            return self.get_task(task_id)

    def update_control(self, task_id, control):
        _control(control)
        with self._write():
            task = self.get_task(task_id)
            _require(task is not None, "Ledger navigation requires an existing task")
            _require("setup_retry" not in control, "Only the retry transition may set its receipt")
            if "setup_retry" in task["control"]:
                control = control | {"setup_retry": task["control"]["setup_retry"]}
            encoded = _json(control, "Ledger navigation control")
            _require(
                not task["control"]["blocked"] or control["blocked"] is True,
                "A monitor save access block requires explicit manual recovery",
            )
            self.connection.execute(
                "UPDATE save_tasks SET control_json=? WHERE task_id=?", (encoded, task_id)
            )
            return self.get_task(task_id)


def batch_service_blocked(watch_database: Path) -> bool:
    """Read every fixed ledger block without creating or repairing any data."""
    database = _plain_path(Path(watch_database).absolute())
    _require(database.name == "watch.sqlite", "Batch control requires its watch database")
    return any(
        task["control"]["blocked"] or task["control"].get("in_flight") is True
        for scope in _LEDGER_NAMES
        for task in _ledger_records(database, scope)
    )


def monitor_save_claims(watch_database, *, managed_only=False):
    """Return posts already reserved in the other reviewed pilot for this same gallery."""
    return {
        task["post_id"]
        for task in _ledger_records(_plain_path(Path(watch_database).absolute()), MONITOR_SCOPE)
        if not managed_only or task["output_kind"] == "managed"
    }


def recent_save_claims(watch_database):
    """Keep older native pilots from duplicating or bypassing a recent save."""
    tasks = _ledger_records(_plain_path(Path(watch_database).absolute()), REVIEWED_SCOPE)
    _require(
        not any(t["status"] in {"started", "needs_review"} for t in tasks),
        "An unfinished recent save requires review",
    )
    return {task["post_id"] for task in tasks}


def other_monitor_save_claims(watch_database):
    """Posts reserved by a prior fixed selection or the independent recent-save ledger."""
    from image_monitor.candidate_save_selection import (
        MANIFEST_NAME,
        MONITOR_MANIFEST_NAME,
        read_selection,
    )

    claimed = recent_save_claims(watch_database)
    for name in (MANIFEST_NAME, MONITOR_MANIFEST_NAME):
        selection = read_selection(watch_database.parent / name)
        if selection is not None:
            claimed.add(selection["post_id"])
    return claimed


def _ledger_records(database, scope):
    name = _LEDGER_NAMES[scope]
    watch_root = _root(database.parent)
    path = _plain_path(watch_root / name)
    if not path.exists():
        return []
    _regular(path)
    try:
        connection = sqlite3.connect(
            path.as_uri() + "?mode=ro", uri=True, isolation_level=None, timeout=5
        )
    except sqlite3.Error as error:
        raise QueueError("Monitor save ledger control is unreadable; navigation refused") from error
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA query_only=ON")
        _require(
            connection.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
            and connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
            and _matches_schema(connection, _SCHEMA),
            "Unknown monitor save ledger schema; navigation refused",
        )
        rows = connection.execute("SELECT * FROM ledger_meta").fetchall()
        _require(len(rows) == 1 and rows[0]["singleton"] == 1, "Ledger root metadata is invalid")
        row = rows[0]
        _require(_root(row["watch_root"]) == watch_root, "Ledger belongs to another watch root")
        _require(json.loads(row["scope_json"]) == list(scope), "Ledger monitor scope is invalid")
        _roots(row["watch_root"], row["legacy_root"], row["batch_root"])
        count = connection.execute("SELECT COUNT(*) FROM save_tasks").fetchone()[0]
        _require(count <= MAX_TASKS, "Monitor save ledger exceeds its task limit")
        return [_record(row) for row in connection.execute("SELECT * FROM save_tasks")]
    except (sqlite3.Error, ValueError, TypeError) as error:
        raise QueueError("Monitor save ledger control is invalid; navigation refused") from error
    finally:
        connection.close()
