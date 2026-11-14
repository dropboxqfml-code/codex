"""Durable discovery and image work queue; no browser or file-saving side effects.

Returned records use UTC ISO timestamps and a decoded ``folder_plan`` dictionary.
``verifying`` is deliberately not a completed-file state. Artifact finalization and
filesystem reconciliation must be supplied by a later, Windows-validated pipeline.
"""

import json
import sqlite3
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from image_monitor.paths import aware, plan_folder
from image_monitor.retry import retry_after, schedule_retry

APPLICATION_ID = 0x494D5131
SCHEMA_VERSION = 1
ACTIVE = ("loading", "saving", "verifying")


class QueueError(ValueError):
    pass


@dataclass(frozen=True)
class PostDiscovery:
    post_id: str
    nickname: str
    ip_display: str | None
    first_seen_at: datetime
    published_at: datetime | None = None
    title: str | None = None
    post_url: str | None = None


@dataclass(frozen=True)
class ImageDiscovery:
    stable_key: str
    body_order: int
    display_url: str
    service_scope: str = "default"


def _time(value: datetime) -> str:
    return aware(value).astimezone(UTC).isoformat(timespec="microseconds")


def _date(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QueueError(f"{name} must be a nonempty string")
    return value


def _gallery(value: str) -> str:
    if value not in {"normal", "minor", "mini"}:
        raise QueueError("Unknown gallery type")
    return value


SCHEMA = """
CREATE TABLE posts (
    gallery_type TEXT NOT NULL, gallery_id TEXT NOT NULL, post_id TEXT NOT NULL,
    watch_name TEXT NOT NULL, nickname TEXT NOT NULL, ip_display TEXT,
    first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, published_at TEXT,
    title TEXT, post_url TEXT, folder_plan TEXT NOT NULL,
    PRIMARY KEY(gallery_type,gallery_id,post_id)
);
CREATE TABLE matches (
    watch_name TEXT NOT NULL, gallery_type TEXT NOT NULL, gallery_id TEXT NOT NULL,
    post_id TEXT NOT NULL, keyword TEXT NOT NULL, search_type TEXT NOT NULL,
    first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
    PRIMARY KEY(watch_name,gallery_type,gallery_id,post_id,keyword,search_type),
    FOREIGN KEY(gallery_type,gallery_id,post_id) REFERENCES posts
);
CREATE TABLE checkpoints (
    watch_name TEXT NOT NULL, gallery_type TEXT NOT NULL, gallery_id TEXT NOT NULL,
    keyword TEXT NOT NULL, search_type TEXT NOT NULL, cursor TEXT, checked_at TEXT NOT NULL,
    complete INTEGER NOT NULL, gap_reason TEXT,
    PRIMARY KEY(watch_name,gallery_type,gallery_id,keyword,search_type)
);
CREATE TABLE gaps (
    gap_id TEXT PRIMARY KEY, watch_name TEXT NOT NULL, gallery_type TEXT NOT NULL,
    gallery_id TEXT NOT NULL, keyword TEXT NOT NULL, search_type TEXT NOT NULL,
    cursor TEXT, checked_at TEXT NOT NULL, reason TEXT NOT NULL
);
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY, gallery_type TEXT NOT NULL, gallery_id TEXT NOT NULL,
    post_id TEXT NOT NULL, stable_key TEXT NOT NULL, body_order INTEGER NOT NULL,
    file_slot INTEGER NOT NULL, display_url TEXT NOT NULL, service_scope TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued', attempt_count INTEGER NOT NULL DEFAULT 0,
    first_failure_at TEXT, next_retry_at TEXT, server_not_before TEXT,
    worker_id TEXT, lease_token TEXT, last_error TEXT,
    UNIQUE(gallery_type,gallery_id,post_id,stable_key),
    UNIQUE(gallery_type,gallery_id,post_id,file_slot),
    FOREIGN KEY(gallery_type,gallery_id,post_id) REFERENCES posts
);
CREATE TABLE attempts (
    history_id INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs,
    at TEXT NOT NULL, kind TEXT NOT NULL, reason TEXT NOT NULL,
    attempt_count INTEGER NOT NULL, resulting_status TEXT NOT NULL
);
CREATE TABLE service_limits (scope TEXT PRIMARY KEY, not_before TEXT NOT NULL);
CREATE INDEX jobs_due ON jobs(status,next_retry_at);
"""


class QueueStore:
    def __init__(self, path: Path | str, *, read_only: bool = False):
        if sqlite3.sqlite_version_info < (3, 50, 2):
            raise QueueError("SQLite 3.50.2 or newer is required")
        path = Path(path)
        self.read_only = read_only
        if read_only:
            self.connection = sqlite3.connect(
                path.resolve().as_uri() + "?mode=ro",
                uri=True,
                isolation_level=None,
                timeout=5,
            )
        else:
            self.connection = sqlite3.connect(path, isolation_level=None, timeout=5)
        self.connection.row_factory = sqlite3.Row
        try:
            self.connection.execute("PRAGMA foreign_keys=ON")
            self.connection.execute("PRAGMA trusted_schema=OFF")
            self.connection.execute("PRAGMA busy_timeout=5000")
            if read_only:
                self.connection.execute("PRAGMA query_only=ON")
            application = self.connection.execute("PRAGMA application_id").fetchone()[0]
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            objects = {
                (row[0], row[1])
                for row in self.connection.execute(
                    "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            }
            tables = {name for kind, name in objects if kind == "table"}
            if application == 0 and version == 0 and not objects and not read_only:
                self.connection.executescript(
                    "BEGIN IMMEDIATE;"
                    + SCHEMA
                    + f"PRAGMA application_id={APPLICATION_ID};"
                    + f"PRAGMA user_version={SCHEMA_VERSION};"
                    + "COMMIT;"
                )
            elif (
                application != APPLICATION_ID
                or version != SCHEMA_VERSION
                or not {
                    "posts",
                    "matches",
                    "checkpoints",
                    "gaps",
                    "jobs",
                    "attempts",
                    "service_limits",
                }.issubset(tables)
            ):
                raise QueueError(
                    "Unknown or unsupported queue database schema; no migration attempted"
                )
            if not read_only:
                self.connection.execute("PRAGMA journal_mode=WAL")
                self.connection.execute("PRAGMA synchronous=FULL")
        except BaseException:
            self.connection.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def _write(self) -> Iterator[None]:
        if self.read_only:
            raise QueueError("Queue database is read-only")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _record(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        result = dict(row)
        if "folder_plan" in result:
            result["folder_plan"] = json.loads(result["folder_plan"])
        return result

    def discover_batch(
        self,
        *,
        watch_name: str,
        gallery_type: str,
        gallery_id: str,
        keyword: str,
        search_type: str,
        posts: Sequence[PostDiscovery],
        checked_at: datetime,
        cursor: str | None,
        complete: bool,
        gap_reason: str | None = None,
        folder_date_basis: str = "published_at",
    ) -> dict:
        _text(watch_name, "watch_name")
        _gallery(gallery_type)
        _text(keyword, "keyword")
        _text(search_type, "search_type")
        checked = _time(checked_at)
        if (
            type(complete) is not bool
            or (not complete and not gap_reason)
            or (complete and gap_reason)
        ):
            raise QueueError("An incomplete scan requires a gap reason")
        # Validate target/date policy even for a legitimately empty result page.
        plan_folder(
            watch_name=watch_name,
            gallery_id=gallery_id,
            post_id="0",
            nickname="_",
            ip_display=None,
            first_seen_at=checked_at,
            basis=folder_date_basis,
        )
        scope = (watch_name, gallery_type, gallery_id, keyword, search_type)
        added = matched = 0
        with self._write():
            previous = self.get_checkpoint(*scope)
            if previous is not None and previous["checked_at"] > checked:
                raise QueueError("A stale scan cannot move its checkpoint backwards")
            for post in posts:
                folder = plan_folder(
                    watch_name=watch_name,
                    gallery_id=gallery_id,
                    post_id=post.post_id,
                    nickname=post.nickname,
                    ip_display=post.ip_display,
                    first_seen_at=post.first_seen_at,
                    published_at=post.published_at,
                    basis=folder_date_basis,
                )
                first = _time(post.first_seen_at)
                if first > checked:
                    raise QueueError("Discovery time is later than the scan observation")
                published = _time(post.published_at) if post.published_at is not None else None
                key = (gallery_type, gallery_id, post.post_id)
                existing = self.get_post(*key)
                if existing is None:
                    self.connection.execute(
                        "INSERT INTO posts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            *key,
                            watch_name,
                            post.nickname,
                            post.ip_display,
                            first,
                            checked,
                            published,
                            post.title,
                            post.post_url,
                            json.dumps(folder.to_dict()),
                        ),
                    )
                    added += 1
                else:
                    self.connection.execute(
                        "UPDATE posts SET last_seen_at=MAX(last_seen_at,?), "
                        "published_at=COALESCE(?,published_at),title=COALESCE(?,title),"
                        "post_url=COALESCE(?,post_url) WHERE gallery_type=? "
                        "AND gallery_id=? AND post_id=?",
                        (checked, published, post.title, post.post_url, *key),
                    )
                count = self.connection.execute(
                    "INSERT OR IGNORE INTO matches VALUES (?,?,?,?,?,?,?,?)",
                    (watch_name, *key, keyword, search_type, first, checked),
                ).rowcount
                matched += count
                self.connection.execute(
                    "UPDATE matches SET last_seen_at=MAX(last_seen_at,?) WHERE watch_name=? "
                    "AND gallery_type=? AND gallery_id=? AND post_id=? "
                    "AND keyword=? AND search_type=?",
                    (checked, watch_name, *key, keyword, search_type),
                )
            self.connection.execute(
                "INSERT INTO checkpoints VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT "
                "(watch_name,gallery_type,gallery_id,keyword,search_type) DO UPDATE SET "
                "cursor=excluded.cursor,checked_at=excluded.checked_at,complete=excluded.complete,"
                "gap_reason=excluded.gap_reason",
                (*scope, cursor, checked, int(complete), gap_reason),
            )
            if not complete:
                self.connection.execute(
                    "INSERT INTO gaps VALUES (?,?,?,?,?,?,?,?,?)",
                    (uuid.uuid4().hex, *scope, cursor, checked, gap_reason),
                )
        return {"posts_added": added, "matches_added": matched}

    def queue_images(
        self,
        *,
        gallery_type: str,
        gallery_id: str,
        post_id: str,
        images: Sequence[ImageDiscovery],
    ) -> list[dict]:
        key = (gallery_type, gallery_id, post_id)
        identifiers = []
        if len({image.stable_key for image in images}) != len(images):
            raise QueueError("A batch must not contain duplicate image stable keys")
        with self._write():
            if self.get_post(*key) is None:
                raise QueueError("Post must be durably discovered before its images")
            for image in images:
                _text(image.stable_key, "stable_key")
                _text(image.display_url, "display_url")
                _text(image.service_scope, "service_scope")
                if type(image.body_order) is not int or image.body_order < 1:
                    raise QueueError("body_order must be a positive integer")
                existing = self.connection.execute(
                    "SELECT * FROM jobs WHERE gallery_type=? AND gallery_id=? AND post_id=? "
                    "AND stable_key=?",
                    (*key, image.stable_key),
                ).fetchone()
                if existing is not None:
                    if existing["service_scope"] != image.service_scope:
                        raise QueueError("An existing image's service scope must not change")
                    # Updating display order never changes a job's permanent file slot.
                    # An active worker retains the URL it claimed until its operation ends.
                    if existing["status"] in ACTIVE:
                        self.connection.execute(
                            "UPDATE jobs SET body_order=? WHERE job_id=?",
                            (image.body_order, existing["job_id"]),
                        )
                    else:
                        self.connection.execute(
                            "UPDATE jobs SET body_order=?,display_url=? WHERE job_id=?",
                            (image.body_order, image.display_url, existing["job_id"]),
                        )
                    identifiers.append(existing["job_id"])
                    continue
                slot = self.connection.execute(
                    "SELECT COALESCE(MAX(file_slot),0)+1 FROM jobs "
                    "WHERE gallery_type=? AND gallery_id=? AND post_id=?",
                    key,
                ).fetchone()[0]
                job_id = uuid.uuid4().hex
                self.connection.execute(
                    "INSERT INTO jobs(job_id,gallery_type,gallery_id,post_id,stable_key,body_order,"
                    "file_slot,display_url,service_scope) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        job_id,
                        *key,
                        image.stable_key,
                        image.body_order,
                        slot,
                        image.display_url,
                        image.service_scope,
                    ),
                )
                identifiers.append(job_id)
        return [self.get_job(job_id) for job_id in identifiers]

    def get_post(self, gallery_type: str, gallery_id: str, post_id: str) -> dict | None:
        return self._record(
            self.connection.execute(
                "SELECT * FROM posts WHERE gallery_type=? AND gallery_id=? AND post_id=?",
                (gallery_type, gallery_id, post_id),
            ).fetchone()
        )

    def get_job(self, job_id: str) -> dict | None:
        return self._record(
            self.connection.execute(
                "SELECT j.*,p.folder_plan FROM jobs j "
                "JOIN posts p USING(gallery_type,gallery_id,post_id) "
                "WHERE job_id=?",
                (job_id,),
            ).fetchone()
        )

    def list_jobs(self) -> list[dict]:
        return [
            self.get_job(row[0])
            for row in self.connection.execute(
                "SELECT job_id FROM jobs ORDER BY gallery_type,gallery_id,post_id,file_slot"
            )
        ]

    def get_checkpoint(
        self, watch_name, gallery_type, gallery_id, keyword, search_type
    ) -> dict | None:
        return self._record(
            self.connection.execute(
                "SELECT * FROM checkpoints WHERE watch_name=? AND gallery_type=? AND gallery_id=? "
                "AND keyword=? AND search_type=?",
                (watch_name, gallery_type, gallery_id, keyword, search_type),
            ).fetchone()
        )

    def list_gaps(self) -> list[dict]:
        return [
            dict(row) for row in self.connection.execute("SELECT * FROM gaps ORDER BY checked_at")
        ]

    def history(self, job_id: str) -> list[dict]:
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT * FROM attempts WHERE job_id=? ORDER BY history_id",
                (job_id,),
            )
        ]

    def claim_next(self, worker_id: str, now: datetime) -> dict | None:
        _text(worker_id, "worker_id")
        at = _time(now)
        with self._write():
            self.connection.execute(
                "UPDATE jobs SET status='manual_review',last_error='automatic_retry_limit' "
                "WHERE status IN ('queued','retry_wait','deferred') "
                "AND (attempt_count>=8 OR first_failure_at<=?)",
                (_time(now - timedelta(hours=24)),),
            )
            row = self.connection.execute(
                "SELECT j.job_id FROM jobs j JOIN posts p "
                "USING(gallery_type,gallery_id,post_id) "
                "LEFT JOIN service_limits s ON s.scope=j.service_scope "
                "WHERE j.status IN ('queued','retry_wait','deferred') "
                "AND COALESCE(j.next_retry_at,'')<=? AND COALESCE(j.server_not_before,'')<=? "
                "AND COALESCE(s.not_before,'')<=? "
                "ORDER BY COALESCE(j.next_retry_at,p.first_seen_at),j.rowid LIMIT 1",
                (at, at, at),
            ).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            self.connection.execute(
                "UPDATE jobs SET status='loading',worker_id=?,lease_token=? WHERE job_id=?",
                (worker_id, token, row[0]),
            )
            return self.get_job(row[0])

    def _claimed(self, job_id: str, token: str) -> dict:
        job = self.get_job(job_id)
        if job is None or not token or job["lease_token"] != token or job["status"] not in ACTIVE:
            raise QueueError("Stale or invalid worker claim")
        return job

    def transition(self, job_id: str, token: str, status: str) -> dict:
        with self._write():
            job = self._claimed(job_id, token)
            if (job["status"], status) not in {("loading", "saving"), ("saving", "verifying")}:
                raise QueueError("Unsupported job transition")
            self.connection.execute("UPDATE jobs SET status=? WHERE job_id=?", (status, job_id))
            return self.get_job(job_id)

    def record_failure(
        self,
        job_id: str,
        token: str,
        kind: str,
        reason: str,
        now: datetime,
        jitter_fraction: float = 0,
        server_retry_after: str | None = None,
    ) -> dict:
        _text(reason, "reason")
        at = _time(now)
        if kind not in {"network", "ui", "local", "access"}:
            raise QueueError("Unknown failure kind")
        with self._write():
            job = self._claimed(job_id, token)
            attempts = job["attempt_count"]
            first = job["first_failure_at"]
            server = job["server_not_before"]
            next_retry = job["next_retry_at"]
            if kind == "network":
                attempts += 1
                first = first or at
                observed = retry_after(server_retry_after, now)
                if observed is not None:
                    server = max(server or "", _time(observed))
                    self._defer_service(job["service_scope"], server)
                shared = self.connection.execute(
                    "SELECT not_before FROM service_limits WHERE scope=?",
                    (job["service_scope"],),
                ).fetchone()
                decision = schedule_retry(
                    attempt_count=attempts,
                    first_failure_at=_date(first),
                    now=now,
                    jitter_fraction=jitter_fraction,
                    server_not_before=_date(server),
                    service_not_before=_date(shared[0]) if shared is not None else None,
                )
                status = decision.status
                next_retry = _time(decision.next_retry_at) if decision.next_retry_at else None
            else:
                status = {"ui": "paused_ui", "local": "paused_local", "access": "blocked"}[kind]
            self.connection.execute(
                "UPDATE jobs SET status=?,attempt_count=?,first_failure_at=?,next_retry_at=?,"
                "server_not_before=?,last_error=?,worker_id=NULL,lease_token=NULL WHERE job_id=?",
                (status, attempts, first, next_retry, server, reason, job_id),
            )
            self.connection.execute(
                "INSERT INTO attempts(job_id,at,kind,reason,attempt_count,resulting_status) "
                "VALUES (?,?,?,?,?,?)",
                (job_id, at, kind, reason, attempts, status),
            )
            return self.get_job(job_id)

    def _defer_service(self, scope: str, not_before: str) -> None:
        self.connection.execute(
            "INSERT INTO service_limits VALUES (?,?) ON CONFLICT(scope) DO UPDATE SET "
            "not_before=MAX(not_before,excluded.not_before)",
            (scope, not_before),
        )

    def defer_service(self, scope: str, not_before: datetime) -> None:
        _text(scope, "scope")
        at = _time(not_before)
        with self._write():
            self._defer_service(scope, at)

    def recover_interrupted(self, *, confirm_workers_stopped: bool = False) -> int:
        if confirm_workers_stopped is not True:
            raise QueueError("Confirm all workers stopped before recovering interrupted jobs")
        with self._write():
            return self.connection.execute(
                "UPDATE jobs SET status='manual_review',worker_id=NULL,lease_token=NULL,"
                "last_error='interrupted_operation_requires_review' "
                "WHERE status IN ('loading','saving','verifying')"
            ).rowcount

    def summary(self) -> dict:
        counts = dict(self.connection.execute("SELECT status,COUNT(*) FROM jobs GROUP BY status"))
        return {
            "schema_version": SCHEMA_VERSION,
            "posts": self.connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
            "jobs": sum(counts.values()),
            "statuses": counts,
            "unresolved_gaps": self.connection.execute("SELECT COUNT(*) FROM gaps").fetchone()[0],
            "oldest_first_seen_at": self.connection.execute(
                "SELECT MIN(first_seen_at) FROM posts WHERE (gallery_type,gallery_id,post_id) "
                "IN (SELECT gallery_type,gallery_id,post_id FROM jobs)"
            ).fetchone()[0],
        }
