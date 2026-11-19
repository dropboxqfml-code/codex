"""Durable discovery and image work queue; no browser or file-saving side effects.

Returned records use UTC ISO timestamps and a decoded ``folder_plan`` dictionary.
``verifying`` is not a completed-file state. Artifact journals bridge verified
filesystem finalization and metadata writes; file checks remain the caller's duty.
"""

import json
import ntpath
import re
import sqlite3
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath, PureWindowsPath

from image_monitor.paths import RESERVED, aware, plan_folder
from image_monitor.retry import retry_after, schedule_retry
from image_monitor.validation import EXTENSIONS

APPLICATION_ID = 0x494D5131
SCHEMA_VERSION = 5
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


def _relative_path(value: str) -> str:
    _text(value, "relative path")
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if (
        any(
            part in {"", ".", ".."}
            or part != part.rstrip(" .")
            or part.split(".")[0].upper() in RESERVED
            for part in parts
        )
        or any(ord(char) < 32 or char in '<>:"|?*' for char in normalized)
        or PurePosixPath(normalized).is_absolute()
        or PureWindowsPath(value).drive
    ):
        raise QueueError("Unsafe artifact relative path")
    return "/".join(parts)


def _save_root(value: str) -> tuple[str, bool]:
    _text(value, "save_root")
    if any(ord(char) < 32 for char in value):
        raise QueueError("Artifact save root must be an absolute local path")
    windows = PureWindowsPath(value)
    if windows.drive:
        if not windows.is_absolute() or windows.drive.startswith("\\"):
            raise QueueError("Artifact save root must be an absolute local path")
        path = windows
        is_windows = True
    else:
        if "\\" in value:
            raise QueueError("Artifact save root must be an absolute local path")
        path = PurePosixPath(value)
        is_windows = False
        if not path.is_absolute():
            raise QueueError("Artifact save root must be an absolute local path")
    if ".." in path.parts:
        raise QueueError("Artifact save root must not contain parent traversal")
    return path.as_posix(), is_windows


def _json_data(value: dict, description: str) -> str:
    if not isinstance(value, dict):
        raise QueueError(f"{description} must be a dictionary")
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError, RecursionError) as error:
        raise QueueError(f"{description} must contain finite JSON data") from error


BASE_SCHEMA = """
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


OBSERVATION_STATEMENTS = (
    """CREATE TABLE post_observations (
        observation_id TEXT PRIMARY KEY, gallery_type TEXT NOT NULL,
        gallery_id TEXT NOT NULL, post_id TEXT NOT NULL, observed_at TEXT NOT NULL,
        snapshot_json TEXT NOT NULL,
        FOREIGN KEY(gallery_type,gallery_id,post_id) REFERENCES posts
    )""",
    """CREATE TABLE observation_jobs (
        observation_id TEXT NOT NULL REFERENCES post_observations,
        job_id TEXT NOT NULL REFERENCES jobs, body_order INTEGER NOT NULL,
        PRIMARY KEY(observation_id,job_id)
    )""",
    """CREATE INDEX observations_post_time ON post_observations
        (gallery_type,gallery_id,post_id,observed_at)""",
)
V2_SCHEMA = BASE_SCHEMA + ";\n".join(OBSERVATION_STATEMENTS) + ";"
ARTIFACT_STATEMENTS = (
    """CREATE TABLE artifact_finalizations (
        job_id TEXT PRIMARY KEY REFERENCES jobs,
        artifact_id TEXT NOT NULL UNIQUE,
        observation_id TEXT NOT NULL REFERENCES post_observations,
        save_root TEXT NOT NULL, staging_relative TEXT NOT NULL,
        final_relative TEXT NOT NULL, verification_json TEXT NOT NULL,
        image_metadata_json TEXT NOT NULL, saved_at TEXT NOT NULL,
        phase TEXT NOT NULL CHECK(phase IN ('prepared','metadata_pending','finalized')),
        target_key TEXT NOT NULL UNIQUE
    )""",
)
V3_SCHEMA = V2_SCHEMA + ";\n".join(ARTIFACT_STATEMENTS) + ";"
WATCH_STATEMENTS = (
    """CREATE TABLE watch_state (
        watch_name TEXT NOT NULL, gallery_type TEXT NOT NULL, gallery_id TEXT NOT NULL,
        keyword TEXT NOT NULL, search_type TEXT NOT NULL, generation INTEGER NOT NULL,
        baseline_json TEXT, checkpoint_json TEXT, latest_scan_id TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(watch_name,gallery_type,gallery_id,keyword,search_type)
    )""",
    """CREATE TABLE watch_scans (
        scan_id TEXT PRIMARY KEY, watch_name TEXT NOT NULL, gallery_type TEXT NOT NULL,
        gallery_id TEXT NOT NULL, keyword TEXT NOT NULL, search_type TEXT NOT NULL,
        generation INTEGER NOT NULL, observed_at TEXT NOT NULL, result_json TEXT NOT NULL,
        checkpoint_json TEXT NOT NULL, complete INTEGER NOT NULL CHECK(complete IN (0,1)),
        gap_reason TEXT,
        UNIQUE(watch_name,gallery_type,gallery_id,keyword,search_type,generation)
    )""",
    """CREATE TABLE watch_candidates (
        watch_name TEXT NOT NULL, gallery_type TEXT NOT NULL, gallery_id TEXT NOT NULL,
        keyword TEXT NOT NULL, search_type TEXT NOT NULL, post_id TEXT NOT NULL,
        post_url TEXT, title TEXT, shown_metadata_json TEXT NOT NULL,
        first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
        first_scan_id TEXT NOT NULL REFERENCES watch_scans,
        latest_scan_id TEXT NOT NULL REFERENCES watch_scans,
        PRIMARY KEY(watch_name,gallery_type,gallery_id,keyword,search_type,post_id)
    )""",
    """CREATE TABLE watch_gaps (
        scan_id TEXT PRIMARY KEY REFERENCES watch_scans,
        watch_name TEXT NOT NULL, gallery_type TEXT NOT NULL, gallery_id TEXT NOT NULL,
        keyword TEXT NOT NULL, search_type TEXT NOT NULL, generation INTEGER NOT NULL,
        observed_at TEXT NOT NULL, reason TEXT NOT NULL
    )""",
)
V4_SCHEMA = V3_SCHEMA + ";\n".join(WATCH_STATEMENTS) + ";"
CANDIDATE_DETAIL_STATEMENTS = (
    """CREATE TABLE candidate_details (
        attempt_id TEXT PRIMARY KEY, watch_name TEXT NOT NULL,
        gallery_type TEXT NOT NULL, gallery_id TEXT NOT NULL,
        keyword TEXT NOT NULL, search_type TEXT NOT NULL, post_id TEXT NOT NULL,
        first_scan_id TEXT NOT NULL REFERENCES watch_scans,
        baseline_observed_at TEXT NOT NULL, started_at TEXT NOT NULL,
        finished_at TEXT, status TEXT NOT NULL CHECK(status IN ('started','completed','failed')),
        result_json TEXT,
        UNIQUE(watch_name,gallery_type,gallery_id,keyword,search_type,post_id),
        FOREIGN KEY(watch_name,gallery_type,gallery_id,keyword,search_type,post_id)
            REFERENCES watch_candidates,
        CHECK((status='started' AND finished_at IS NULL AND result_json IS NULL) OR
            (status IN ('completed','failed') AND finished_at IS NOT NULL
                AND result_json IS NOT NULL))
    )""",
    """CREATE INDEX candidate_detail_blocks ON candidate_details
        (json_extract(result_json,'$.control.blocked')) WHERE result_json IS NOT NULL""",
)
SCHEMA = V4_SCHEMA + ";\n".join(CANDIDATE_DETAIL_STATEMENTS) + ";"


def _schema_objects(connection: sqlite3.Connection) -> set[tuple]:
    return {
        (row[0], row[1], row[2], " ".join((row[3] or "").split()))
        for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'"
        )
    }


def _matches_schema(connection: sqlite3.Connection, schema: str) -> bool:
    # An application_id/version pair is not enough evidence to mutate an existing
    # file. Compare the known object definitions before the additive migration.
    reference = sqlite3.connect(":memory:")
    try:
        reference.executescript(schema)
        return _schema_objects(connection) == _schema_objects(reference)
    finally:
        reference.close()


class QueueStore:
    def __init__(self, path: Path | str, *, read_only: bool = False, immutable: bool = False):
        if sqlite3.sqlite_version_info < (3, 50, 2):
            raise QueueError("SQLite 3.50.2 or newer is required")
        path = Path(path)
        self.read_only = read_only
        if immutable and not read_only:
            raise QueueError("An immutable database must be read-only")
        if read_only:
            self.connection = sqlite3.connect(
                path.resolve().as_uri() + ("?mode=ro&immutable=1" if immutable else "?mode=ro"),
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
            objects = _schema_objects(self.connection)
            if application == 0 and version == 0 and not objects and not read_only:
                self.connection.executescript(
                    "BEGIN IMMEDIATE;"
                    + SCHEMA
                    + f"PRAGMA application_id={APPLICATION_ID};"
                    + f"PRAGMA user_version={SCHEMA_VERSION};"
                    + "COMMIT;"
                )
                version = SCHEMA_VERSION
            elif application == APPLICATION_ID and version in {1, 2, 3, 4}:
                if read_only:
                    expected = {1: BASE_SCHEMA, 2: V2_SCHEMA, 3: V3_SCHEMA, 4: V4_SCHEMA}[version]
                    if not _matches_schema(self.connection, expected):
                        raise QueueError("Unknown queue database schema; migration refused")
                else:
                    with self._write():
                        # Recheck after acquiring the migration lock: another
                        # process may already have upgraded the same database.
                        current = self.connection.execute("PRAGMA user_version").fetchone()[0]
                        if current == 1:
                            if not _matches_schema(self.connection, BASE_SCHEMA):
                                raise QueueError("Unknown queue database schema; migration refused")
                            for statement in OBSERVATION_STATEMENTS:
                                self.connection.execute(statement)
                            current = 2
                        if current == 2:
                            if not _matches_schema(self.connection, V2_SCHEMA):
                                raise QueueError("Unknown queue database schema; migration refused")
                            for statement in ARTIFACT_STATEMENTS:
                                self.connection.execute(statement)
                            current = 3
                        if current == 3:
                            if not _matches_schema(self.connection, V3_SCHEMA):
                                raise QueueError("Unknown queue database schema; migration refused")
                            for statement in WATCH_STATEMENTS:
                                self.connection.execute(statement)
                            current = 4
                        if current == 4:
                            if not _matches_schema(self.connection, V4_SCHEMA):
                                raise QueueError("Unknown queue database schema; migration refused")
                            for statement in CANDIDATE_DETAIL_STATEMENTS:
                                self.connection.execute(statement)
                            self.connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                        elif current != SCHEMA_VERSION or not _matches_schema(
                            self.connection, SCHEMA
                        ):
                            raise QueueError("Unknown queue database schema; migration refused")
                    version = SCHEMA_VERSION
            elif (
                application != APPLICATION_ID
                or version != SCHEMA_VERSION
                or not _matches_schema(self.connection, SCHEMA)
            ):
                raise QueueError(
                    "Unknown or unsupported queue database schema; no migration attempted"
                )
            self.schema_version = version
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

    def _upsert_post_match(
        self,
        *,
        watch_name,
        gallery_type,
        gallery_id,
        keyword,
        search_type,
        post,
        checked,
        folder_date_basis,
    ) -> tuple[int, int]:
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
        added = 0
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
            added = 1
        else:
            self.connection.execute(
                "UPDATE posts SET last_seen_at=MAX(last_seen_at,?), "
                "published_at=COALESCE(?,published_at),title=COALESCE(?,title),"
                "post_url=COALESCE(?,post_url) WHERE gallery_type=? "
                "AND gallery_id=? AND post_id=?",
                (checked, published, post.title, post.post_url, *key),
            )
        matched = self.connection.execute(
            "INSERT OR IGNORE INTO matches VALUES (?,?,?,?,?,?,?,?)",
            (watch_name, *key, keyword, search_type, first, checked),
        ).rowcount
        self.connection.execute(
            "UPDATE matches SET last_seen_at=MAX(last_seen_at,?) WHERE watch_name=? "
            "AND gallery_type=? AND gallery_id=? AND post_id=? "
            "AND keyword=? AND search_type=?",
            (checked, watch_name, *key, keyword, search_type),
        )
        return added, matched

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
                post_added, match_added = self._upsert_post_match(
                    watch_name=watch_name,
                    gallery_type=gallery_type,
                    gallery_id=gallery_id,
                    keyword=keyword,
                    search_type=search_type,
                    post=post,
                    checked=checked,
                    folder_date_basis=folder_date_basis,
                )
                added += post_added
                matched += match_added
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

    def _queue_images(
        self, key: tuple[str, str, str], images: Sequence[ImageDiscovery]
    ) -> list[str]:
        identifiers = []
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
        return identifiers

    def queue_images(
        self,
        *,
        gallery_type: str,
        gallery_id: str,
        post_id: str,
        images: Sequence[ImageDiscovery],
    ) -> list[dict]:
        key = (gallery_type, gallery_id, post_id)
        if len({image.stable_key for image in images}) != len(images):
            raise QueueError("A batch must not contain duplicate image stable keys")
        with self._write():
            identifiers = self._queue_images(key, images)
        return [self.get_job(job_id) for job_id in identifiers]

    def persist_post_snapshot(
        self,
        *,
        watch_name: str,
        gallery_type: str,
        gallery_id: str,
        keyword: str,
        search_type: str,
        post: PostDiscovery,
        images: Sequence[ImageDiscovery],
        snapshot: dict,
        observed_at: datetime,
        folder_date_basis: str = "published_at",
    ) -> dict:
        """Atomically enqueue an inspected post without moving a list checkpoint.

        Snapshot image entries may include repeated body occurrences of one stable
        key; the image job's body_order must identify one of those occurrences.
        Every entry and queued job must agree on the display URL for that key.
        """
        _text(watch_name, "watch_name")
        _gallery(gallery_type)
        _text(keyword, "keyword")
        _text(search_type, "search_type")
        observed = _time(observed_at)
        key = (gallery_type, gallery_id, post.post_id)
        if not isinstance(snapshot, dict) or any(
            snapshot.get(name) != value
            for name, value in zip(("gallery_type", "gallery_id", "post_id"), key, strict=True)
        ):
            raise QueueError("Snapshot identity does not match the inspected post")
        entries = snapshot.get("images")
        if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
            raise QueueError("Snapshot images must be a list of image records")
        if len({image.stable_key for image in images}) != len(images):
            raise QueueError("A batch must not contain duplicate image stable keys")
        by_key = {image.stable_key: image for image in images}
        occurrences = {name: set() for name in by_key}
        orders = set()
        for entry in entries:
            stable_key = entry.get("stable_key")
            order = entry.get("body_order")
            if (
                not isinstance(stable_key, str)
                or stable_key not in by_key
                or type(order) is not int
                or order < 1
                or order in orders
                or entry.get("display_url") != by_key[stable_key].display_url
            ):
                raise QueueError("Snapshot image records do not match the queued images")
            occurrences[stable_key].add(order)
            orders.add(order)
        if any(image.body_order not in occurrences[image.stable_key] for image in images):
            raise QueueError("Snapshot image records do not match the queued images")
        try:
            payload = json.dumps(snapshot, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, RecursionError) as error:
            raise QueueError("Snapshot must contain finite JSON data") from error
        observation_id = uuid.uuid4().hex
        with self._write():
            latest = self.connection.execute(
                "SELECT MAX(observed_at) FROM post_observations WHERE gallery_type=? "
                "AND gallery_id=? AND post_id=?",
                key,
            ).fetchone()[0]
            if latest is not None and latest > observed:
                raise QueueError("A stale observation cannot replace a newer post snapshot")
            self._upsert_post_match(
                watch_name=watch_name,
                gallery_type=gallery_type,
                gallery_id=gallery_id,
                keyword=keyword,
                search_type=search_type,
                post=post,
                checked=observed,
                folder_date_basis=folder_date_basis,
            )
            identifiers = self._queue_images(key, images)
            self.connection.execute(
                "INSERT INTO post_observations VALUES (?,?,?,?,?,?)",
                (observation_id, *key, observed, payload),
            )
            self.connection.executemany(
                "INSERT INTO observation_jobs VALUES (?,?,?)",
                [
                    (observation_id, job_id, image.body_order)
                    for job_id, image in zip(identifiers, images, strict=True)
                ],
            )
        return {
            "observation_id": observation_id,
            "jobs": [self.get_job(job) for job in identifiers],
        }

    def _observation_record(self, row: sqlite3.Row) -> dict:
        record = dict(row)
        record["snapshot"] = json.loads(record.pop("snapshot_json"))
        record["jobs"] = [
            dict(job)
            for job in self.connection.execute(
                "SELECT o.job_id,o.body_order,j.stable_key,j.file_slot FROM observation_jobs o "
                "JOIN jobs j USING(job_id) WHERE o.observation_id=? ORDER BY o.body_order",
                (record["observation_id"],),
            )
        ]
        return record

    def get_observation(self, observation_id: str) -> dict | None:
        """Read immutable source data, including after a completed job is rediscovered."""
        if self.schema_version == 1:
            return None
        row = self.connection.execute(
            "SELECT * FROM post_observations WHERE observation_id=?", (observation_id,)
        ).fetchone()
        return self._observation_record(row) if row is not None else None

    def list_post_snapshots(self, gallery_type: str, gallery_id: str, post_id: str) -> list[dict]:
        """Return immutable observations newest first, with their frozen job associations."""
        if self.schema_version == 1:
            return []
        return [
            self._observation_record(row)
            for row in self.connection.execute(
                "SELECT * FROM post_observations WHERE gallery_type=? AND gallery_id=? "
                "AND post_id=? "
                "ORDER BY observed_at DESC,rowid DESC",
                (gallery_type, gallery_id, post_id),
            )
        ]

    def _job_source(self, job: dict, observation_id: str | None = None) -> dict | None:
        if self.schema_version == 1:
            return None
        rows = self.connection.execute(
            "SELECT p.*,o.body_order AS source_body_order FROM observation_jobs o "
            "JOIN post_observations p USING(observation_id) WHERE o.job_id=? "
            "AND (? IS NULL OR p.observation_id=?) ORDER BY p.observed_at DESC,p.rowid DESC",
            (job["job_id"], observation_id, observation_id),
        )
        for row in rows:
            snapshot = json.loads(row["snapshot_json"])
            if any(
                snapshot.get(key) != job[key] for key in ("gallery_type", "gallery_id", "post_id")
            ):
                raise QueueError("Stored source identity does not match its image job")
            images = [
                image
                for image in snapshot.get("images", [])
                if image.get("stable_key") == job["stable_key"]
                and image.get("display_url") == job["display_url"]
                and image.get("body_order") == row["source_body_order"]
            ]
            if len(images) > 1:
                raise QueueError("Stored source has ambiguous image identity")
            if images:
                return {
                    "observation_id": row["observation_id"],
                    "snapshot": snapshot,
                    "image": images[0],
                }
        return None

    def get_job_source(self, job_id: str, observation_id: str | None = None) -> dict | None:
        """Return associated source matching this job's exact current URL and stable key."""
        job = self.get_job(job_id)
        return self._job_source(job, observation_id) if job is not None else None

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

    @staticmethod
    def _artifact_record(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        record = dict(row)
        record.pop("target_key", None)
        record["verification"] = json.loads(record.pop("verification_json"))
        record["image_metadata"] = json.loads(record.pop("image_metadata_json"))
        return record

    def get_artifact(self, job_id: str) -> dict | None:
        if self.schema_version < 3:
            return None
        return self._artifact_record(
            self.connection.execute(
                "SELECT * FROM artifact_finalizations WHERE job_id=?", (job_id,)
            ).fetchone()
        )

    def list_artifacts(self) -> list[dict]:
        if self.schema_version < 3:
            return []
        return [
            self._artifact_record(row)
            for row in self.connection.execute(
                "SELECT * FROM artifact_finalizations ORDER BY saved_at,artifact_id"
            )
        ]

    def prepare_artifact(
        self,
        job_id: str,
        token: str,
        *,
        observation_id: str,
        save_root: str,
        staging_relative: str,
        final_relative: str,
        verification: dict,
        image_metadata: dict,
        saved_at: datetime,
    ) -> dict:
        """Journal an externally verified staging file before its final move.

        This API performs no file I/O and cannot establish writer completion or
        image correspondence. The native saver/finalizer must supply that proof.
        """
        root, windows_root = _save_root(save_root)
        staging = _relative_path(staging_relative)
        final = _relative_path(final_relative)
        if not staging.startswith(f"_staging/{job_id}/") or staging == final:
            raise QueueError("Artifact staging path must belong to this image job")
        if not isinstance(verification, dict):
            raise QueueError("Artifact verification must be a dictionary")
        fmt = verification.get("detected_format")
        sha = verification.get("sha256")
        size = verification.get("file_size")
        if (
            not isinstance(fmt, str)
            or fmt not in EXTENSIONS
            or not isinstance(sha, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", sha) is None
            or type(size) is not int
            or size < 1
            or verification.get("extension", EXTENSIONS[fmt]) != EXTENSIONS[fmt]
            or any(
                type(verification[key]) is not int or verification[key] < 1
                for key in ("width", "height", "frames")
                if key in verification
            )
        ):
            raise QueueError("Invalid artifact verification data")
        verified = verification | {"sha256": sha.lower(), "extension": EXTENSIONS[fmt]}
        verified_json = _json_data(verified, "Artifact verification")
        image_json = _json_data(image_metadata, "Artifact image metadata")
        timestamp = _time(saved_at)
        target_key = (
            "windows:" + ntpath.normcase(ntpath.join(root, final))
            if windows_root
            else "posix:" + PurePosixPath(root, final).as_posix()
        )
        with self._write():
            job = self._claimed(job_id, token)
            if job["status"] != "verifying":
                raise QueueError("Only a verifying image job can prepare an artifact")
            source = self._job_source(job, observation_id)
            if source is None:
                raise QueueError("Artifact requires an associated immutable image source")
            expected = (
                job["folder_plan"]["relative_directory"]
                + f"/{job['file_slot']:03d}.{EXTENSIONS[fmt]}"
            )
            if final != expected:
                raise QueueError("Artifact target differs from the job's frozen folder and slot")
            if any(
                image_metadata.get(key) != source["image"].get(key)
                for key in ("stable_key", "display_url")
            ):
                raise QueueError("Artifact image metadata does not match its frozen source")
            if (
                image_metadata.get("saved_filename", final.rsplit("/", 1)[1])
                != final.rsplit("/", 1)[1]
            ):
                raise QueueError("Artifact saved filename does not match its final target")
            values = {
                "observation_id": observation_id,
                "save_root": root,
                "staging_relative": staging,
                "final_relative": final,
                "verification": verified,
                "image_metadata": image_metadata,
                "saved_at": timestamp,
            }
            existing = self.get_artifact(job_id)
            if existing is not None:
                if existing["phase"] != "prepared" or any(
                    existing[key] != value for key, value in values.items()
                ):
                    raise QueueError("Existing artifact journal is immutable")
                return existing
            try:
                self.connection.execute(
                    "INSERT INTO artifact_finalizations(job_id,artifact_id,observation_id,"
                    "save_root,staging_relative,final_relative,verification_json,"
                    "image_metadata_json,saved_at,phase,target_key) "
                    "VALUES (?,?,?,?,?,?,?,?,?,'prepared',?)",
                    (
                        job_id,
                        uuid.uuid4().hex,
                        observation_id,
                        root,
                        staging,
                        final,
                        verified_json,
                        image_json,
                        timestamp,
                        target_key,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise QueueError("Artifact journal or final target is already reserved") from error
            return self.get_artifact(job_id)

    def _complete_artifact(self, job_id: str) -> dict:
        self.connection.execute(
            "UPDATE jobs SET status='completed',worker_id=NULL,lease_token=NULL,"
            "last_error=NULL,next_retry_at=NULL WHERE job_id=?",
            (job_id,),
        )
        self.connection.execute(
            "UPDATE artifact_finalizations SET phase='metadata_pending' WHERE job_id=?", (job_id,)
        )
        return self.get_artifact(job_id)

    def complete_artifact(self, job_id: str, token: str) -> dict:
        """Commit completion only after the caller verified the actual final file."""
        with self._write():
            job = self._claimed(job_id, token)
            artifact = self.get_artifact(job_id)
            if job["status"] != "verifying" or artifact is None or artifact["phase"] != "prepared":
                raise QueueError("Only a prepared verifying artifact can be completed")
            return self._complete_artifact(job_id)

    def mark_metadata_written(self, job_id: str) -> dict:
        with self._write():
            artifact = self.get_artifact(job_id)
            job = self.get_job(job_id)
            if (
                artifact is None
                or job is None
                or job["status"] != "completed"
                or artifact["phase"] not in {"metadata_pending", "finalized"}
            ):
                raise QueueError("Artifact metadata is not ready for finalization")
            self.connection.execute(
                "UPDATE artifact_finalizations SET phase='finalized' WHERE job_id=?", (job_id,)
            )
            self.connection.execute("UPDATE jobs SET last_error=NULL WHERE job_id=?", (job_id,))
            return self.get_artifact(job_id)

    def mark_artifact_manual_review(
        self,
        job_id: str,
        reason: str,
        *,
        confirm_workers_stopped: bool = False,
    ) -> dict:
        """Record a journal conflict after the caller has confirmed worker shutdown."""
        if confirm_workers_stopped is not True:
            raise QueueError("Confirm all workers stopped before reviewing an artifact")
        _text(reason, "reason")
        with self._write():
            artifact = self.get_artifact(job_id)
            job = self.get_job(job_id)
            if artifact is None or job is None:
                raise QueueError("Artifact journal is missing")
            if artifact["phase"] == "prepared":
                if job["status"] == "completed":
                    raise QueueError("Prepared artifact has inconsistent completed state")
                self.connection.execute(
                    "UPDATE jobs SET status='manual_review',worker_id=NULL,lease_token=NULL,"
                    "last_error=? WHERE job_id=?",
                    (reason, job_id),
                )
            elif job["status"] == "completed":
                # The final file is already committed. Preserve that fact while
                # reporting the metadata issue through last_error and journal phase.
                self.connection.execute(
                    "UPDATE jobs SET last_error=? WHERE job_id=?", (reason, job_id)
                )
            else:
                raise QueueError("Artifact journal has inconsistent completion state")
            return self.get_artifact(job_id)

    def recover_artifact_complete(
        self,
        job_id: str,
        *,
        confirm_workers_stopped: bool = False,
    ) -> dict:
        """Finish a prepared journal after external file/source checks and worker shutdown."""
        if confirm_workers_stopped is not True:
            raise QueueError("Confirm all workers stopped before recovering an artifact")
        with self._write():
            artifact = self.get_artifact(job_id)
            job = self.get_job(job_id)
            if (
                artifact is None
                or artifact["phase"] != "prepared"
                or job is None
                or job["status"] not in {"verifying", "manual_review", "paused_local"}
            ):
                raise QueueError("Artifact is not a recoverable prepared save")
            return self._complete_artifact(job_id)

    def claim_next(
        self,
        worker_id: str,
        now: datetime,
        *,
        job_ids: Sequence[str] | None = None,
    ) -> dict | None:
        _text(worker_id, "worker_id")
        approved = None
        if job_ids is not None:
            if isinstance(job_ids, (str, bytes)) or not isinstance(job_ids, Sequence):
                raise QueueError("Approved job IDs must be a sequence of nonempty strings")
            if len(job_ids) > 500:
                raise QueueError("At most 500 approved job IDs are allowed")
            for job_id in job_ids:
                _text(job_id, "approved job ID")
            approved = tuple(dict.fromkeys(job_ids))
            if not approved:
                return None
        # Only bounded placeholder counts are composed; all caller IDs remain
        # bound values. Empty approval lists never fall back to the global queue.
        placeholders = ",".join("?" for _job_id in approved) if approved is not None else ""
        expiry_scope = f" AND job_id IN ({placeholders})" if approved is not None else ""
        select_scope = f"AND j.job_id IN ({placeholders}) " if approved is not None else ""
        parameters = approved or ()
        at = _time(now)
        with self._write():
            self.connection.execute(
                "UPDATE jobs SET status='manual_review',last_error='automatic_retry_limit' "
                "WHERE status IN ('queued','retry_wait','deferred') "
                "AND (attempt_count>=8 OR first_failure_at<=?)" + expiry_scope,
                (_time(now - timedelta(hours=24)), *parameters),
            )
            row = self.connection.execute(
                "SELECT j.job_id FROM jobs j JOIN posts p "
                "USING(gallery_type,gallery_id,post_id) "
                "LEFT JOIN service_limits s ON s.scope=j.service_scope "
                "WHERE j.status IN ('queued','retry_wait','deferred') "
                "AND NOT EXISTS (SELECT 1 FROM artifact_finalizations a WHERE a.job_id=j.job_id) "
                "AND COALESCE(j.next_retry_at,'')<=? AND COALESCE(j.server_not_before,'')<=? "
                "AND COALESCE(s.not_before,'')<=? "
                + select_scope
                + "ORDER BY COALESCE(j.next_retry_at,p.first_seen_at),j.rowid LIMIT 1",
                (at, at, at, *parameters),
            ).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            self.connection.execute(
                "UPDATE jobs SET status='loading',worker_id=?,lease_token=? WHERE job_id=?",
                (worker_id, token, row[0]),
            )
            job = self.get_job(row[0])
            return job | {"source": self._job_source(job)}

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

    def release_unstarted_claim(
        self,
        job_id: str,
        token: str,
        *,
        now: datetime,
        reason: str = "pre_input_focus_pause",
    ) -> dict:
        """Release a loading claim only when the caller proves no native input occurred.

        This queue operation cannot inspect GUI state. The worker must durably
        record the pre-input boundary and stop before any right-click/save action.
        """
        _text(reason, "reason")
        at = _time(now)
        with self._write():
            job = self._claimed(job_id, token)
            if job["status"] != "loading" or self.get_artifact(job_id) is not None:
                raise QueueError(
                    "Only an unstarted loading claim without an artifact may be released"
                )
            self.connection.execute(
                "UPDATE jobs SET status='queued',worker_id=NULL,lease_token=NULL,last_error=NULL "
                "WHERE job_id=?",
                (job_id,),
            )
            self.connection.execute(
                "INSERT INTO attempts(job_id,at,kind,reason,attempt_count,resulting_status) "
                "VALUES (?,?,'ui_pause',?,?,'queued')",
                (job_id, at, reason, job["attempt_count"]),
            )
            return self.get_job(job_id)

    def resume_preinput_failure(
        self,
        job_id: str,
        *,
        observation_id: str,
        expected_history_id: int,
        now: datetime,
        confirm_workers_stopped: bool = False,
        confirmed_no_input: bool = False,
    ) -> dict:
        """Resume one precisely identified UI failure after external no-input proof.

        Both confirmations are assertions by the recovery controller, which must
        validate its private attempt report, stopped worker and empty staging.
        They do not make arbitrary paused or interrupted jobs safe to reset.
        """
        if confirm_workers_stopped is not True or confirmed_no_input is not True:
            raise QueueError("Confirm stopped workers and verified absence of native input")
        _text(observation_id, "observation_id")
        if type(expected_history_id) is not int or not 0 < expected_history_id < 2**63:
            raise QueueError("A valid expected failure history ID is required")
        at = _time(now)
        with self._write():
            job = self.get_job(job_id)
            if (
                job is None
                or job["status"] != "paused_ui"
                or job["last_error"] != "NativeUIError"
                or job["worker_id"] is not None
                or job["lease_token"] is not None
                or self.get_artifact(job_id) is not None
            ):
                raise QueueError("Image job is not an eligible pre-input UI failure")
            latest = self.connection.execute(
                "SELECT * FROM attempts WHERE job_id=? ORDER BY history_id DESC LIMIT 1", (job_id,)
            ).fetchone()
            if (
                latest is None
                or latest["history_id"] != expected_history_id
                or latest["kind"] != "ui"
                or latest["reason"] != "NativeUIError"
                or latest["resulting_status"] != "paused_ui"
            ):
                raise QueueError("The expected UI failure is not the latest job history")
            if self._job_source(job, observation_id) is None:
                raise QueueError(
                    "The pre-input observation does not match the current image source"
                )
            self.connection.execute(
                "UPDATE jobs SET status='queued',worker_id=NULL,lease_token=NULL,last_error=NULL "
                "WHERE job_id=?",
                (job_id,),
            )
            self.connection.execute(
                "INSERT INTO attempts(job_id,at,kind,reason,attempt_count,resulting_status) "
                "VALUES (?,?,'pre_input_resume','verified_no_input',?,'queued')",
                (job_id, at, job["attempt_count"]),
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
            "schema_version": self.schema_version,
            "posts": self.connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
            "jobs": sum(counts.values()),
            "statuses": counts,
            "unresolved_gaps": self.connection.execute("SELECT COUNT(*) FROM gaps").fetchone()[0],
            "oldest_first_seen_at": self.connection.execute(
                "SELECT MIN(first_seen_at) FROM posts WHERE (gallery_type,gallery_id,post_id) "
                "IN (SELECT gallery_type,gallery_id,post_id FROM jobs)"
            ).fetchone()[0],
        }
