"""Durable, single-attempt detail observations for discovered list candidates.

Starting an observation commits before navigation. An interrupted or failed
observation remains an audit record and is never an automatic retry target.
This store does not mutate list coverage, posts, image jobs, or file plans.
"""

import json
import re
import uuid
from datetime import datetime

from image_monitor.queue import QueueError, QueueStore, _json_data, _text, _time
from image_monitor.watch_store import WatchScope, WatchStore, _limit, _record, _scope

RECENT_PICTURE_CANDIDATES = 20
MAX_DETAIL_RESULT_BYTES = 4 * 1024 * 1024
_WHERE = "watch_name=? AND gallery_type=? AND gallery_id=? AND keyword=? AND search_type=?"


def _instant(value, name):
    if not isinstance(value, datetime):
        raise QueueError(f"{name} must be a timezone-aware datetime")
    try:
        return _time(value)
    except (TypeError, ValueError, AttributeError) as error:
        raise QueueError(f"{name} must be a timezone-aware datetime") from error


def _stored_instant(value):
    try:
        return _instant(datetime.fromisoformat(value), "Stored detail time")
    except (TypeError, ValueError) as error:
        raise QueueError("Stored detail timing is invalid") from error


def _post_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        raise QueueError("Candidate post ID must be a canonical positive decimal string")
    return value


def _detail(row):
    if row is None:
        return None
    result = dict(row)
    value = result.pop("result_json")
    result["result"] = json.loads(value) if value is not None else None
    return result


def _control(result):
    if "control" not in result:
        return
    control = result["control"]
    if not isinstance(control, dict):
        raise QueueError("Detail control must be a dictionary")
    if "blocked" in control and type(control["blocked"]) is not bool:
        raise QueueError("Detail block state must be a boolean")


def detail_service_blocked(queue: QueueStore) -> bool:
    """Honor an explicit permanent detail block across every scope in this DB."""
    if queue.schema_version < 5:
        return False
    invalid = queue.connection.execute(
        "SELECT 1 FROM candidate_details WHERE result_json IS NOT NULL AND ("
        "(json_type(result_json,'$.control') IS NOT NULL AND "
        "json_type(result_json,'$.control')!='object') OR "
        "(json_type(result_json,'$.control.blocked') IS NOT NULL AND "
        "json_type(result_json,'$.control.blocked') NOT IN ('true','false'))) LIMIT 1"
    ).fetchone()
    if invalid is not None:
        raise QueueError("Stored detail block metadata is invalid")
    return (
        queue.connection.execute(
            "SELECT 1 FROM candidate_details WHERE result_json IS NOT NULL "
            "AND json_extract(result_json,'$.control.blocked')=1 LIMIT 1"
        ).fetchone()
        is not None
    )


class CandidateDetailStore:
    """Use the queue's transaction discipline for frozen detail-attempt records."""

    def __init__(self, queue: QueueStore):
        self.queue = queue

    def list_pending(self, scope: WatchScope, *, limit: int = 2, exclude_posts=()) -> list[dict]:
        return self._pending(scope, limit, exclude_posts, newest=False)

    def next_monitor_pending(self, scope, *, exclude_posts, alternate_order):
        """Use committed attempts so cooldown checks and restarts do not advance the turn."""
        newest = False
        if alternate_order and self.queue.schema_version >= 5:
            attempts = self.queue.connection.execute(
                f"SELECT COUNT(*) FROM candidate_details WHERE {_WHERE}", _scope(scope)
            ).fetchone()[0]
            newest = attempts % 2 == 1
        if not newest:
            return self._pending(scope, 1, exclude_posts, newest=False), "oldest_discovery"
        recent = self._pending(scope, RECENT_PICTURE_CANDIDATES, exclude_posts, newest=True)
        for candidate in recent:
            if candidate["shown_metadata"].get("picture_marker") is True:
                return [candidate], "recent_picture_marker"
        return recent[:1], "highest_post_id"

    def _pending(self, scope, limit, exclude_posts, *, newest):
        key, limit = _scope(scope), _limit(limit)
        if self.queue.schema_version < 5:
            return []
        # Decimal post IDs can exceed SQLite's signed integer range.
        order = "length(c.post_id) DESC,c.post_id DESC" if newest else "c.first_seen_at,c.post_id"
        return [
            _record(row)
            for row in self.queue.connection.execute(
                "SELECT c.* FROM watch_candidates c WHERE "
                "c.watch_name=? AND c.gallery_type=? AND c.gallery_id=? "
                "AND c.keyword=? AND c.search_type=? "
                "AND c.post_id NOT IN (SELECT value FROM json_each(?)) AND NOT EXISTS ("
                "SELECT 1 FROM candidate_details d WHERE d.watch_name=c.watch_name "
                "AND d.gallery_type=c.gallery_type AND d.gallery_id=c.gallery_id "
                "AND d.keyword=c.keyword AND d.search_type=c.search_type AND d.post_id=c.post_id) "
                f"ORDER BY {order} LIMIT ?",
                (*key, json.dumps([_post_id(post) for post in exclude_posts]), limit),
            )
        ]

    def get(self, attempt_id: str) -> dict | None:
        _text(attempt_id, "attempt_id")
        if self.queue.schema_version < 5:
            return None
        return _detail(
            self.queue.connection.execute(
                "SELECT * FROM candidate_details WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
        )

    def iter_details(self, scope: WatchScope):
        """Stream history in inspection order without sorting full body evidence in memory."""
        key = _scope(scope)
        if self.queue.schema_version < 5:
            return
        rows = self.queue.connection.execute(
            f"SELECT attempt_id,length(CAST(result_json AS BLOB)) FROM candidate_details "
            f"WHERE {_WHERE} ORDER BY started_at,attempt_id",
            key,
        )
        for attempt_id, size in rows:
            if size is not None and size > MAX_DETAIL_RESULT_BYTES:
                raise QueueError("Existing detail evidence exceeds its limit")
            yield self.get(attempt_id)

    def iter_detail_timing(self, scope: WatchScope):
        """Read completion evidence and cooldown times without loading the body reports."""
        key = _scope(scope)
        if self.queue.schema_version >= 5:
            yield from self.queue.connection.execute(
                f"SELECT post_id,status,finished_at FROM candidate_details WHERE {_WHERE}", key
            )

    def list_details(self, scope: WatchScope, *, limit: int = 100) -> list[dict]:
        key, limit = _scope(scope), _limit(limit)
        if self.queue.schema_version < 5:
            return []
        return [
            _detail(row)
            for row in self.queue.connection.execute(
                f"SELECT * FROM candidate_details WHERE {_WHERE} "
                "ORDER BY started_at,attempt_id LIMIT ?",
                (*key, limit),
            )
        ]

    def start(
        self,
        scope: WatchScope,
        post_id: str,
        *,
        expected_first_scan_id: str,
        baseline_observed_at: datetime,
        started_at: datetime,
    ) -> dict:
        key = _scope(scope)
        post_id = _post_id(post_id)
        _text(expected_first_scan_id, "expected_first_scan_id")
        baseline = _instant(baseline_observed_at, "baseline_observed_at")
        started = _instant(started_at, "started_at")
        if started < baseline:
            raise QueueError("Detail inspection cannot precede its baseline")
        attempt_id = uuid.uuid4().hex
        with self.queue._write():
            state = WatchStore(self.queue).get_state(scope)
            frozen = state.get("baseline")
            if (
                not isinstance(frozen, dict)
                or _stored_instant(frozen.get("observed_at")) != baseline
            ):
                raise QueueError("Detail inspection must retain the established watch baseline")
            candidate = self.queue.connection.execute(
                f"SELECT * FROM watch_candidates WHERE {_WHERE} AND post_id=?", (*key, post_id)
            ).fetchone()
            if candidate is None or candidate["first_scan_id"] != expected_first_scan_id:
                raise QueueError("Candidate discovery changed before detail inspection")
            if started < _stored_instant(candidate["first_seen_at"]):
                raise QueueError("Detail inspection cannot precede candidate discovery")
            prior = self.queue.connection.execute(
                f"SELECT 1 FROM candidate_details WHERE {_WHERE} AND post_id=?", (*key, post_id)
            ).fetchone()
            if prior is not None:
                raise QueueError("Candidate detail already has an observation attempt")
            self.queue.connection.execute(
                "INSERT INTO candidate_details VALUES (?,?,?,?,?,?,?,?,?,?,NULL,'started',NULL)",
                (attempt_id, *key, post_id, expected_first_scan_id, baseline, started),
            )
            return self.get(attempt_id)

    def finish(
        self,
        attempt_id: str,
        *,
        finished_at: datetime,
        result: dict,
        status: str = "completed",
    ) -> dict:
        _text(attempt_id, "attempt_id")
        if not isinstance(status, str) or status not in {"completed", "failed"}:
            raise QueueError("A finished detail observation must be completed or failed")
        finished = _instant(finished_at, "finished_at")
        encoded = _json_data(result, "Detail result")
        _control(result)
        if len(encoded.encode("utf-8")) > MAX_DETAIL_RESULT_BYTES:
            raise QueueError("Detail result exceeds its metadata limit")
        with self.queue._write():
            prior = self.get(attempt_id)
            if prior is None or prior["status"] != "started":
                raise QueueError("Only a started detail observation may finish")
            if finished < _stored_instant(prior["started_at"]):
                raise QueueError("Detail finish cannot precede its start")
            changed = self.queue.connection.execute(
                "UPDATE candidate_details SET finished_at=?,status=?,result_json=? "
                "WHERE attempt_id=? AND status='started'",
                (finished, status, encoded, attempt_id),
            ).rowcount
            if changed != 1:
                raise QueueError("Detail observation changed before completion")
            return self.get(attempt_id)
