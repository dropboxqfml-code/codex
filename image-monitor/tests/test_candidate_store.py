"""Persist detail-attempt evidence without changing discovery or image work."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from image_monitor import candidate_store
from image_monitor.candidate_store import CandidateDetailStore, detail_service_blocked
from image_monitor.queue import (
    APPLICATION_ID,
    BASE_SCHEMA,
    V2_SCHEMA,
    V3_SCHEMA,
    V4_SCHEMA,
    QueueError,
    QueueStore,
)
from image_monitor.watch_store import WatchScope, WatchStore

NOW = datetime(2026, 11, 16, 4, 30, tzinfo=UTC)
SCOPE = WatchScope("detail trial", "normal", "comic_new6", "ai", "search_subject_memo")


def seed(queue, scope=SCOPE):
    watch = WatchStore(queue)
    baseline = {"observed_at": NOW.isoformat(), "anchor_ids": ["100"], "mode": "new"}
    watch.persist_scan(
        scope,
        observed_at=NOW,
        expected_generation=0,
        scan_result={"mode": "fixture"},
        candidates=[],
        checkpoint=baseline,
        complete=True,
        baseline=baseline,
    )
    watch.persist_scan(
        scope,
        observed_at=NOW + timedelta(seconds=60),
        expected_generation=1,
        scan_result={"mode": "fixture"},
        candidates=[
            {
                "post_id": post_id,
                "post_url": f"https://gall.dcinside.com/board/view/?id=comic_new6&no={post_id}",
                "title": "Invented private title",
                "shown_metadata": {"baseline_observed_at": NOW.isoformat()},
            }
            for post_id in ("101", "102")
        ],
        checkpoint=baseline | {"anchor_ids": ["102", "101", "100"]},
        complete=True,
    )
    return watch.list_candidates(scope)


def start(details, candidate, scope=SCOPE, **overrides):
    options = {
        "expected_first_scan_id": candidate["first_scan_id"],
        "baseline_observed_at": NOW,
        "started_at": NOW + timedelta(seconds=120),
    }
    return details.start(scope, candidate["post_id"], **(options | overrides))


def watch_evidence(queue, scope=SCOPE):
    watch = WatchStore(queue)
    return (
        watch.get_state(scope),
        watch.list_candidates(scope),
        watch.list_scans(scope),
        watch.list_gaps(scope),
        queue.summary(),
    )


def test_started_attempt_commits_before_work_and_completion_preserves_watch_and_jobs(tmp_path):
    path = tmp_path / "watch.sqlite"
    with QueueStore(path) as queue:
        candidates = seed(queue)
        before = watch_evidence(queue)
        details = CandidateDetailStore(queue)
        attempt = start(details, candidates[0])
        assert attempt["status"] == "started"
        assert attempt["finished_at"] is attempt["result"] is None
        assert attempt["post_id"] == "101"
        assert attempt["first_scan_id"] == candidates[0]["first_scan_id"]
        assert attempt["baseline_observed_at"] == NOW.isoformat(timespec="microseconds")
        with QueueStore(path, read_only=True) as other:
            assert CandidateDetailStore(other).get(attempt["attempt_id"]) == attempt
            assert [row["post_id"] for row in CandidateDetailStore(other).list_pending(SCOPE)] == [
                "102"
            ]
        result = {"time_eligibility": "at_or_after_baseline", "control": {"blocked": False}}
        finished = details.finish(
            attempt["attempt_id"], finished_at=NOW + timedelta(seconds=125), result=result
        )
        assert finished["status"] == "completed"
        assert finished["result"] == result
        assert details.list_details(SCOPE) == [finished]
        assert watch_evidence(queue) == before
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0
        assert queue.connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("status", ["started", "completed", "failed"])
def test_every_attempt_state_survives_reopen_and_prevents_automatic_repeat(tmp_path, status):
    path = tmp_path / "watch.sqlite"
    with QueueStore(path) as queue:
        candidate = seed(queue)[0]
        details = CandidateDetailStore(queue)
        attempt = start(details, candidate)
        if status != "started":
            attempt = details.finish(
                attempt["attempt_id"],
                finished_at=NOW + timedelta(seconds=125),
                result={"reason": "synthetic outcome"},
                status=status,
            )
    with QueueStore(path) as queue:
        details = CandidateDetailStore(queue)
        assert details.get(attempt["attempt_id"]) == attempt
        assert [row["post_id"] for row in details.list_pending(SCOPE)] == ["102"]
        with pytest.raises(QueueError, match="already"):
            start(details, candidate)
        assert details.list_details(SCOPE) == [attempt]


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"expected_first_scan_id": "different discovery"}, "changed"),
        ({"baseline_observed_at": NOW + timedelta(microseconds=1)}, "baseline"),
        ({"baseline_observed_at": NOW.replace(tzinfo=None)}, "timezone-aware"),
        ({"started_at": NOW - timedelta(seconds=1)}, "baseline"),
        ({"started_at": NOW + timedelta(seconds=30)}, "discovery"),
    ],
)
def test_stale_or_invalid_start_writes_no_attempt(tmp_path, overrides, match):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        candidate = seed(queue)[0]
        details = CandidateDetailStore(queue)
        before = watch_evidence(queue)
        with pytest.raises(QueueError, match=match):
            start(details, candidate, **overrides)
        assert details.list_details(SCOPE) == []
        assert watch_evidence(queue) == before


def test_equivalent_baseline_timezone_is_the_same_frozen_instant(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        candidate = seed(queue)[0]
        details = CandidateDetailStore(queue)
        attempt = start(
            details, candidate, baseline_observed_at=NOW.astimezone(timezone(timedelta(hours=9)))
        )
        assert attempt["baseline_observed_at"] == NOW.isoformat(timespec="microseconds")


def test_baseline_rows_missing_candidates_and_other_scopes_are_not_detail_targets(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        candidate = seed(queue)[0]
        details = CandidateDetailStore(queue)
        for post_id in ("100", "999"):
            with pytest.raises(QueueError, match="changed"):
                start(details, candidate | {"post_id": post_id})
        other = replace(SCOPE, keyword="other")
        with pytest.raises(QueueError, match="baseline"):
            start(details, candidate, scope=other)
        seed(queue, other)
        start(details, candidate)
        assert len(details.list_pending(other)) == 2
        assert details.list_details(other) == []


def test_concurrent_starts_commit_one_attempt(tmp_path):
    path = tmp_path / "watch.sqlite"
    with QueueStore(path) as queue:
        candidate = seed(queue)[0]

    def observe(_):
        with QueueStore(path) as queue:
            try:
                return start(CandidateDetailStore(queue), candidate)["status"]
            except QueueError as error:
                assert "already" in str(error)
                return "refused"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(observe, range(2))) == ["refused", "started"]
    with QueueStore(path) as queue:
        assert len(CandidateDetailStore(queue).list_details(SCOPE)) == 1


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"finished_at": NOW}, "precede"),
        ({"finished_at": NOW.replace(tzinfo=None)}, "timezone-aware"),
        ({"status": "started"}, "completed or failed"),
        ({"status": []}, "completed or failed"),
        ({"result": {"invalid": float("nan")}}, "finite JSON"),
        ({"result": {"control": None}}, "dictionary"),
        ({"result": {"control": {"blocked": 1}}}, "boolean"),
    ],
)
def test_invalid_finish_retains_the_started_attempt(tmp_path, overrides, match):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        candidate = seed(queue)[0]
        details = CandidateDetailStore(queue)
        attempt = start(details, candidate)
        options = {"finished_at": NOW + timedelta(seconds=125), "result": {"observed": True}}
        with pytest.raises(QueueError, match=match):
            details.finish(attempt["attempt_id"], **(options | overrides))
        assert details.get(attempt["attempt_id"]) == attempt


def test_finished_evidence_cannot_be_replaced_and_oversized_metadata_does_not_finish(
    tmp_path, monkeypatch
):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        candidate = seed(queue)[0]
        details = CandidateDetailStore(queue)
        attempt = start(details, candidate)
        monkeypatch.setattr(candidate_store, "MAX_DETAIL_RESULT_BYTES", 10)
        with pytest.raises(QueueError, match="metadata limit"):
            details.finish(
                attempt["attempt_id"],
                finished_at=NOW + timedelta(seconds=125),
                result={"oversized": "invented metadata"},
            )
        assert details.get(attempt["attempt_id"]) == attempt
        finished = details.finish(
            attempt["attempt_id"], finished_at=NOW + timedelta(seconds=125), result={}
        )
        with pytest.raises(QueueError, match="Only a started"):
            details.finish(
                attempt["attempt_id"], finished_at=NOW + timedelta(seconds=126), result={}
            )
        assert details.get(attempt["attempt_id"]) == finished


def test_detail_completion_sql_failure_rolls_back_result_and_status(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        candidate = seed(queue)[0]
        details = CandidateDetailStore(queue)
        attempt = start(details, candidate)
        queue.connection.execute(
            "CREATE TEMP TRIGGER deny_detail_completion BEFORE UPDATE ON candidate_details "
            "BEGIN SELECT RAISE(ABORT,'synthetic detail write failure'); END"
        )
        with pytest.raises(sqlite3.IntegrityError, match="synthetic"):
            details.finish(
                attempt["attempt_id"], finished_at=NOW + timedelta(seconds=125), result={}
            )
        assert details.get(attempt["attempt_id"]) == attempt


def test_explicit_detail_block_applies_across_scopes_and_is_not_inferred_from_gone_posts(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        candidates = seed(queue)
        other = replace(SCOPE, keyword="other")
        seed(queue, other)
        details = CandidateDetailStore(queue)
        assert not detail_service_blocked(queue)
        gone = start(details, candidates[0])
        details.finish(
            gone["attempt_id"],
            finished_at=NOW + timedelta(seconds=125),
            result={"http_status": 404, "control": {"blocked": False}},
        )
        assert not detail_service_blocked(queue)
        blocked = start(details, candidates[1])
        details.finish(
            blocked["attempt_id"],
            finished_at=NOW + timedelta(seconds=125),
            result={"http_status": 403, "control": {"blocked": True}},
            status="failed",
        )
        assert detail_service_blocked(queue)
        assert len(details.list_pending(other)) == 2


def test_malformed_stored_block_metadata_fails_closed(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        candidate = seed(queue)[0]
        details = CandidateDetailStore(queue)
        attempt = start(details, candidate)
        details.finish(attempt["attempt_id"], finished_at=NOW + timedelta(seconds=125), result={})
        queue.connection.execute(
            "UPDATE candidate_details SET result_json=? WHERE attempt_id=?",
            ('{"control":{"blocked":"false"}}', attempt["attempt_id"]),
        )
        with pytest.raises(QueueError, match="block metadata"):
            detail_service_blocked(queue)


@pytest.mark.parametrize(
    "version,schema", [(1, BASE_SCHEMA), (2, V2_SCHEMA), (3, V3_SCHEMA), (4, V4_SCHEMA)]
)
def test_legacy_readonly_detail_queries_do_not_create_audit_state(tmp_path, version, schema):
    path = tmp_path / "old.sqlite"
    with closing(sqlite3.connect(path)) as database, database:
        database.executescript(schema)
        database.execute(f"PRAGMA application_id={APPLICATION_ID}")
        database.execute(f"PRAGMA user_version={version}")
    original = path.read_bytes()
    with QueueStore(path, read_only=True) as queue:
        details = CandidateDetailStore(queue)
        assert details.list_pending(SCOPE) == []
        assert details.list_details(SCOPE) == []
        assert details.get("no attempt") is None
        assert not detail_service_blocked(queue)
        with pytest.raises(QueueError, match="read-only"):
            details.finish("no attempt", finished_at=NOW, result={})
    assert path.read_bytes() == original
