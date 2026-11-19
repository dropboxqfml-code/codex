"""Durable list observations, independent of inspected posts and image work.

The caller validates site-specific scan semantics. JSON records retain that
evidence without asserting that selectors or coverage are site-verified. Only
detail inspection may create a post's permanent folder plan in ``QueueStore``.
"""

import json
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from image_monitor.queue import QueueError, QueueStore, _gallery, _json_data, _text, _time


@dataclass(frozen=True)
class WatchScope:
    watch_name: str
    gallery_type: str
    gallery_id: str
    keyword: str
    search_type: str

    def key(self) -> tuple[str, str, str, str, str]:
        _text(self.watch_name, "watch_name")
        _gallery(self.gallery_type)
        _text(self.gallery_id, "gallery_id")
        _text(self.keyword, "keyword")
        _text(self.search_type, "search_type")
        return (
            self.watch_name,
            self.gallery_type,
            self.gallery_id,
            self.keyword,
            self.search_type,
        )


MONITOR_SCOPE = WatchScope("목록 감시", "normal", "comic_new6", "ai", "search_subject_memo")

_SCOPE_WHERE = "watch_name=? AND gallery_type=? AND gallery_id=? AND keyword=? AND search_type=?"


def _scope(scope: WatchScope) -> tuple[str, str, str, str, str]:
    if not isinstance(scope, WatchScope):
        raise QueueError("scope must be a WatchScope")
    return scope.key()


def _limit(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 1000:
        raise QueueError("limit must be an integer between 1 and 1000")
    return value


def _record(row) -> dict | None:
    if row is None:
        return None
    result = dict(row)
    for name in ("baseline", "checkpoint", "result", "shown_metadata"):
        column = name + "_json"
        if column in result:
            value = result.pop(column)
            result[name] = json.loads(value) if value is not None else None
    if "complete" in result:
        result["complete"] = bool(result["complete"])
    return result


def _candidate(value: dict) -> tuple[str, str | None, str | None, str]:
    if not isinstance(value, dict) or set(value) - {
        "post_id",
        "post_url",
        "title",
        "shown_metadata",
    }:
        raise QueueError("Candidate must contain only list identity and shown metadata")
    post_id = value.get("post_id")
    if not isinstance(post_id, str) or not re.fullmatch(r"[0-9]{1,20}", post_id):
        raise QueueError("Candidate post_id must be a positive canonical decimal string")
    if int(post_id) < 1 or str(int(post_id)) != post_id:
        raise QueueError("Candidate post_id must be a positive canonical decimal string")
    post_url = value.get("post_url")
    title = value.get("title")
    if post_url is not None:
        _text(post_url, "post_url")
    if title is not None and not isinstance(title, str):
        raise QueueError("Candidate title must be a string or null")
    metadata = _json_data(value.get("shown_metadata", {}), "Candidate shown metadata")
    return post_id, post_url, title, metadata


def _observed_candidates(result: dict) -> list[tuple[str, str | None, str | None, str]]:
    """Validate refreshes from rows whose planner role retains safe list evidence."""
    observations = result.get("observations", [])
    if isinstance(observations, (str, bytes)) or not isinstance(observations, Sequence):
        raise QueueError("Scan observations must be a sequence")
    rows = []
    for observation in observations:
        if not isinstance(observation, dict):
            raise QueueError("Scan observations must be dictionaries")
        role = observation.get("role")
        if not isinstance(role, str) or role not in {"candidate", "anchor", "overlap_recheck"}:
            continue
        rows.append(
            _candidate(
                {
                    key: observation.get(key)
                    for key in ("post_id", "post_url", "title", "shown_metadata")
                }
            )
        )
    return rows


class WatchStore:
    """A bounded facade using the queue's connection and atomic write discipline."""

    def __init__(self, store: QueueStore):
        self.store = store

    def get_state(self, scope: WatchScope) -> dict:
        key = _scope(scope)
        if self.store.schema_version < 4:
            row = None
        else:
            row = self.store.connection.execute(
                f"SELECT * FROM watch_state WHERE {_SCOPE_WHERE}", key
            ).fetchone()
        if row is None:
            return {
                "generation": 0,
                "baseline": None,
                "checkpoint": None,
                "latest_scan": None,
            }
        state = _record(row)
        latest = self.store.connection.execute(
            "SELECT * FROM watch_scans WHERE scan_id=?", (state.pop("latest_scan_id"),)
        ).fetchone()
        state["latest_scan"] = _record(latest)
        return state

    def list_candidates(self, scope: WatchScope, *, limit: int = 100) -> list[dict]:
        key, limit = _scope(scope), _limit(limit)
        if self.store.schema_version < 4:
            return []
        return [
            _record(row)
            for row in self.store.connection.execute(
                f"SELECT * FROM watch_candidates WHERE {_SCOPE_WHERE} "
                "ORDER BY first_seen_at,post_id LIMIT ?",
                (*key, limit),
            )
        ]

    def list_scans(self, scope: WatchScope, *, limit: int = 100) -> list[dict]:
        key, limit = _scope(scope), _limit(limit)
        if self.store.schema_version < 4:
            return []
        return [
            _record(row)
            for row in self.store.connection.execute(
                f"SELECT * FROM watch_scans WHERE {_SCOPE_WHERE} ORDER BY generation DESC LIMIT ?",
                (*key, limit),
            )
        ]

    def list_gaps(self, scope: WatchScope, *, limit: int = 100) -> list[dict]:
        key, limit = _scope(scope), _limit(limit)
        if self.store.schema_version < 4:
            return []
        return [
            dict(row)
            for row in self.store.connection.execute(
                f"SELECT * FROM watch_gaps WHERE {_SCOPE_WHERE} ORDER BY generation DESC LIMIT ?",
                (*key, limit),
            )
        ]

    def persist_scan(
        self,
        scope: WatchScope,
        *,
        observed_at: datetime,
        expected_generation: int,
        scan_result: dict,
        candidates: Sequence[dict],
        checkpoint: dict,
        complete: bool,
        gap_reason: str | None = None,
        baseline: dict | None = None,
    ) -> dict:
        """Commit one validated plan; a partial scan never advances coverage.

        ``baseline`` is initialized once and contains the caller's exact excluded
        anchor identities. ``checkpoint`` on every scan supports pending resume;
        only a complete scan replaces the state's coverage checkpoint. A stale
        generation or observation rejects the entire candidate/scan/gap batch.
        Safe anchor and overlap observations refresh existing candidates without
        creating candidates for baseline posts or changing their first-seen data.
        """
        key = _scope(scope)
        observed = _time(observed_at)
        if type(expected_generation) is not int or expected_generation < 0:
            raise QueueError("expected_generation must be a nonnegative integer")
        if type(complete) is not bool or (complete and gap_reason is not None):
            raise QueueError("A complete scan cannot have a gap reason")
        if not complete:
            _text(gap_reason, "gap_reason")
        result_json = _json_data(scan_result, "Scan result")
        checkpoint_json = _json_data(checkpoint, "Scan checkpoint")
        baseline_json = _json_data(baseline, "Scan baseline") if baseline is not None else None
        if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
            raise QueueError("Candidates must be a sequence of candidate records")
        rows = [_candidate(candidate) for candidate in candidates]
        if len({row[0] for row in rows}) != len(rows):
            raise QueueError("A scan must not contain duplicate candidate post IDs")
        refreshes = {row[0]: row for row in rows}
        refreshes.update({row[0]: row for row in _observed_candidates(scan_result)})
        scan_id = uuid.uuid4().hex
        generation = expected_generation + 1
        added = 0
        with self.store._write():
            state = self.get_state(scope)
            if state["generation"] != expected_generation:
                raise QueueError("A stale scan generation cannot replace watch state")
            if state.get("updated_at", observed) > observed:
                raise QueueError("A stale scan observation cannot move watch state backwards")
            previous_baseline = state["baseline"]
            if previous_baseline is not None:
                if baseline is not None and previous_baseline != baseline:
                    raise QueueError("An established watch baseline cannot change")
                baseline_json = _json_data(previous_baseline, "Scan baseline")
            previous_checkpoint = state["checkpoint"]
            coverage_json = (
                checkpoint_json
                if complete
                else (
                    _json_data(previous_checkpoint, "Coverage checkpoint")
                    if previous_checkpoint is not None
                    else None
                )
            )
            self.store.connection.execute(
                "INSERT INTO watch_scans VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    scan_id,
                    *key,
                    generation,
                    observed,
                    result_json,
                    checkpoint_json,
                    int(complete),
                    gap_reason,
                ),
            )
            for post_id, post_url, title, metadata in rows:
                added += self.store.connection.execute(
                    "INSERT OR IGNORE INTO watch_candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        *key,
                        post_id,
                        post_url,
                        title,
                        metadata,
                        observed,
                        observed,
                        scan_id,
                        scan_id,
                    ),
                ).rowcount
            for post_id, post_url, title, metadata in refreshes.values():
                self.store.connection.execute(
                    "UPDATE watch_candidates SET post_url=COALESCE(?,post_url),"
                    "title=COALESCE(?,title),shown_metadata_json=?,last_seen_at=?,latest_scan_id=? "
                    f"WHERE {_SCOPE_WHERE} AND post_id=?",
                    (post_url, title, metadata, observed, scan_id, *key, post_id),
                )
            self.store.connection.execute(
                "INSERT INTO watch_state VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT "
                "(watch_name,gallery_type,gallery_id,keyword,search_type) DO UPDATE SET "
                "generation=excluded.generation,baseline_json=excluded.baseline_json,"
                "checkpoint_json=excluded.checkpoint_json,latest_scan_id=excluded.latest_scan_id,"
                "updated_at=excluded.updated_at",
                (*key, generation, baseline_json, coverage_json, scan_id, observed),
            )
            if not complete:
                self.store.connection.execute(
                    "INSERT INTO watch_gaps VALUES (?,?,?,?,?,?,?,?,?)",
                    (scan_id, *key, generation, observed, gap_reason),
                )
        return {"scan_id": scan_id, "generation": generation, "candidates_added": added}
