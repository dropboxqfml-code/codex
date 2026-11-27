"""Exercise the exact monitor handoff and bounded search on real saved observations."""

import json
from contextlib import nullcontext
from datetime import timedelta
from functools import partial

import pytest
from test_candidate_runtime import BrowserFactory as DetailBrowser
from test_candidate_runtime import http_failure, no_browser
from test_candidate_save_runtime import BASELINE, NOW, seed
from test_watch_image_search import body
from test_watch_runtime import BrowserFactory, FakeClock, baseline_outcome, link, observed, snapshot

from image_monitor import candidate_runtime, monitor_operations, watch_runtime
from image_monitor.candidate_policy import unobserved_detail
from image_monitor.candidate_save_selection import MANIFEST_NAME, select_candidate_save
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_auto_selection import search_monitor_candidates
from image_monitor.monitor_settings import save_monitor_settings
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


@pytest.fixture
def roots(tmp_path, monkeypatch):
    monkeypatch.setattr(candidate_runtime, "require_windows", lambda: None)
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    monkeypatch.setattr(monitor_operations, "NativeSaveLock", nullcontext)
    monkeypatch.setattr(monitor_operations, "shared_state_path", lambda: tmp_path / "pending.json")
    watch, legacy, batch = (tmp_path / name for name in ("watch", "legacy", "batch"))
    seed(watch)
    clock = FakeClock(BASELINE)
    latest = observed(
        lambda stamp: snapshot([107, 106, 105], stamp, links=[link()]),
        lambda stamp: snapshot([104, 103, 102], stamp, page=2, links=[link(3)]),
    )
    report = watch_runtime.run_watch_trial(
        watch,
        scope=MONITOR_SCOPE,
        clock=clock,
        backend_factory=BrowserFactory(baseline_outcome, latest),
    )
    assert report["new_candidates"] == 6
    clock.current = NOW
    clock.waits.clear()
    return watch, legacy, batch, clock


def deleted(candidate, stamp):
    return http_failure(404)(candidate, stamp) | {"url": candidate["post_url"]}


def search(roots, *outcomes):
    watch, legacy, batch, clock = roots
    backend = DetailBrowser(*outcomes) if outcomes else no_browser
    return search_monitor_candidates(
        watch,
        legacy,
        batch,
        clock=clock,
        detail_runner=partial(candidate_runtime.run_candidate_trial, backend_factory=backend),
    )


@pytest.mark.parametrize(
    "skipped,count", [(body(0), "no_body_images_observed"), (body(11), "outside_save_limit")]
)
def test_empty_or_oversized_deleted_then_real_typed_handoff(roots, skipped, count):
    report, binding = search(roots, skipped, deleted, body(10))
    assert report["status"] == "ready", report
    assert report["new_details_checked"] == 3 and report["eligible_body_images"] == 10
    assert report["outcome_counts"] == {count: 1, "unavailable": 1, "save_ready": 1}
    assert report["last_fresh_detail_outcome"] == "save_ready"
    assert report["uninspected_at_selection"] == 3
    assert len(roots[3].waits) == 3 and all(value == 60 for value in roots[3].waits)
    with QueueStore(roots[0] / "watch.sqlite", read_only=True) as queue:
        detail = CandidateDetailStore(queue).get(binding["attempt_id"])
        assert detail["post_id"] == binding["post_id"] and len(binding["fingerprint"]) == 64
        assert (
            WatchStore(queue).get_state(MONITOR_SCOPE)["latest_scan"]["gap_reason"]
            == "anchor_not_reached"
        )
        assert len(CandidateDetailStore(queue).list_pending(MONITOR_SCOPE, limit=10)) == 3
    public = json.dumps(report)
    assert not any(
        value in public for value in (binding["attempt_id"], binding["fingerprint"], "https://")
    )
    repeat, exact = search(roots)
    assert "last_fresh_detail_outcome" not in repeat and repeat["uninspected_at_selection"] == 3
    assert repeat["status"] == "ready" and repeat["new_details_checked"] == 0 and exact == binding


def test_search_yields_to_next_invocation_after_three_empty_posts(roots):
    for expected, remaining in (("limit", 3), ("no_candidates", 0)):
        report, exact = search(roots, body(0), body(0), body(0))
        assert report["last_fresh_detail_outcome"] == "no_body_images_observed"
        assert report["uninspected_at_selection"] == remaining
        assert report["status"] == expected and exact is None
        assert report["new_details_checked"] == 3 and report["browser_closed"]
    report, exact = search(roots)
    assert (
        report["status"] == "no_candidates" and exact is None and report["new_details_checked"] == 0
    )


def test_alternating_detail_turn_survives_reopening_a_large_queue(roots):
    watch, legacy, batch, clock = roots
    database = watch / "watch.sqlite"
    with QueueStore(database) as queue:
        store = WatchStore(queue)
        state = store.get_state(MONITOR_SCOPE)
        store.persist_scan(
            MONITOR_SCOPE,
            observed_at=clock.now(),
            expected_generation=state["generation"],
            scan_result=state["latest_scan"]["result"],
            checkpoint=state["checkpoint"],
            complete=True,
            candidates=[
                {
                    "post_id": str(i),
                    "post_url": f"https://gall.dcinside.com/board/view/?id=comic_new6&no={i}",
                    "title": "Test",
                    "shown_metadata": {},
                }
                for i in range(300, 1283)
            ],
        )
    for attempt, (expected, order) in enumerate(
        (("102", "oldest_discovery"), ("1282", "highest_post_id"), ("103", "oldest_discovery"))
    ):
        if attempt == 1:
            with QueueStore(database, read_only=True) as queue:
                rows, policy = CandidateDetailStore(queue).next_monitor_pending(
                    MONITOR_SCOPE, alternate_order=True, exclude_posts={"1282"}
                )
                assert policy == order and rows[0]["post_id"] == "1281"
        report, handoff = search_monitor_candidates(
            watch,
            legacy,
            batch,
            clock=clock,
            alternate_order=True,
            max_new_details=1,
            detail_runner=partial(
                candidate_runtime.run_candidate_trial, backend_factory=DetailBrowser(deleted)
            ),
        )
        assert report["status"] == "limit" and handoff is None, report
        assert report["detail_selection_order"] == order
        assert report["uninspected_at_selection"] == 988 - attempt
        with QueueStore(database, read_only=True) as queue:
            details = CandidateDetailStore(queue).list_details(MONITOR_SCOPE)
            assert len(details) == attempt + 1 and details[-1]["post_id"] == expected


def test_newer_arrival_before_worker_releases_the_pinned_turn_without_navigation(roots):
    watch, legacy, batch, clock = roots
    search_monitor_candidates(
        watch,
        legacy,
        batch,
        clock=clock,
        alternate_order=True,
        max_new_details=1,
        detail_runner=partial(
            candidate_runtime.run_candidate_trial, backend_factory=DetailBrowser(deleted)
        ),
    )

    def raced(root, browser, **options):
        assert options["monitor_target"][1] == "107"
        with QueueStore(watch / "watch.sqlite") as queue:
            store = WatchStore(queue)
            state = store.get_state(MONITOR_SCOPE)
            store.persist_scan(
                MONITOR_SCOPE,
                observed_at=clock.now(),
                expected_generation=state["generation"],
                scan_result=state["latest_scan"]["result"],
                checkpoint=state["checkpoint"],
                complete=True,
                candidates=[
                    {"post_id": "108", "post_url": None, "title": None, "shown_metadata": {}}
                ],
            )
        return candidate_runtime.run_candidate_trial(
            root, browser, backend_factory=no_browser, **options
        )

    report, exact = search_monitor_candidates(
        watch,
        legacy,
        batch,
        clock=clock,
        alternate_order=True,
        max_new_details=1,
        detail_runner=raced,
    )
    assert exact is None and report["reason"] == "monitor_candidate_changed", report
    assert report["new_details_checked"] == 0 and "detail_selection_order" not in report


def test_reopen_after_a_thousand_inspections_honors_last_deadline_and_finds_new_body(roots):
    watch, _, _, clock = roots
    stamp = clock.now()
    deadline = stamp + timedelta(minutes=4)
    with QueueStore(watch / "watch.sqlite") as queue:
        store = WatchStore(queue)
        state = store.get_state(MONITOR_SCOPE)
        candidates = [
            {
                "post_id": str(i),
                "post_url": f"https://gall.dcinside.com/board/view/?id=comic_new6&no={i}",
                "title": "Fixture",
                "shown_metadata": {},
            }
            for i in range(300, 1301)
        ]
        scan = store.persist_scan(
            MONITOR_SCOPE,
            observed_at=stamp,
            expected_generation=state["generation"],
            scan_result=state["latest_scan"]["result"],
            complete=True,
            candidates=candidates,
            checkpoint=state["checkpoint"],
        )
        # Ordered frozen records put the longest service wait in the 1,001st row.
        records = []
        for i, candidate in enumerate(candidates):
            due = deadline if i == 1000 else stamp + timedelta(minutes=1)
            result = {
                "private_observation": deleted(candidate, stamp),
                "classification": unobserved_detail("candidate_unavailable"),
                "control": {
                    "blocked": False,
                    "interval_seconds": 60,
                    "http_status": 404,
                    "finished_at": stamp.isoformat(),
                    "next_eligible_at": due.isoformat(),
                },
            }
            records.append(
                (
                    f"{i + 1:032x}",
                    *MONITOR_SCOPE.key(),
                    candidate["post_id"],
                    scan["scan_id"],
                    state["baseline"]["observed_at"],
                    stamp.isoformat(),
                    stamp.isoformat(),
                    "completed",
                    json.dumps(result),
                )
            )
        with queue._write():
            queue.connection.executemany(
                "INSERT INTO candidate_details VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", records
            )
    report, exact = search(roots)
    assert exact is None and report["reason"] == "persisted_cooldown", report
    assert report["next_eligible_at"] == deadline.isoformat(timespec="microseconds")
    assert report["uninspected_at_selection"] == 6
    assert report["detail_attempts_at_selection"] == 1001
    clock.current = deadline
    report, exact = search(roots, body(1))
    assert report["status"] == "ready" and exact["post_id"] == "102", report
    assert report["new_details_checked"] == 1 and report["uninspected_at_selection"] == 5
    assert report["detail_attempts_at_selection"] == 1002
    assert report["outcome_counts"] == {"unavailable": 1001, "save_ready": 1}
    repeated, binding = search(roots)
    assert binding == exact and repeated["new_details_checked"] == 0

    with QueueStore(watch / "watch.sqlite") as queue, queue._write():
        queue.connection.execute(
            "UPDATE candidate_details SET result_json=json_set(result_json,'$.control.in_flight',1)"
            " WHERE attempt_id=?",
            (records[-1][0],),
        )
    stopped, binding = search(roots)
    assert binding is None and stopped["reason"] == "operations_require_review"
    assert stopped["new_details_checked"] == 0


def test_longer_monitor_interval_preserves_next_deadline(roots):
    watch, _, _, clock = roots
    save_monitor_settings(watch, 180)
    report, slot = search(roots, body(1))
    assert report["status"] == "waiting" and slot is None
    assert report["new_details_checked"] == 1 and clock.waits == []
    assert report["next_eligible_at"] == (clock.now() + timedelta(seconds=180)).isoformat(
        timespec="microseconds"
    )


def test_backlog_candidate_consumed_before_worker_lease_is_not_replaced(roots):
    watch, legacy, batch, clock = roots

    def raced(root, browser, **kwargs):
        answer = candidate_runtime.run_candidate_trial(
            root, browser, backend_factory=DetailBrowser(body(0)), **kwargs
        )
        assert answer["candidates_completed"] == 1
        clock.wait(60)
        return candidate_runtime.run_candidate_trial(
            root, browser, backend_factory=no_browser, **kwargs
        )

    report, exact = search_monitor_candidates(
        watch, legacy, batch, clock=clock, detail_runner=raced
    )
    assert report["status"] == "busy" and report["reason"] == "monitor_candidate_changed"
    assert report["new_details_checked"] == 0 and exact is None
    with QueueStore(watch / "watch.sqlite", read_only=True) as queue:
        assert len(CandidateDetailStore(queue).list_details(MONITOR_SCOPE)) == 1


@pytest.mark.parametrize("when", ["before_search", "before_detail"])
def test_other_watch_claim_excludes_same_physical_post_even_across_worker_race(roots, when):
    watch, legacy, batch, clock = roots
    database = watch / "watch.sqlite"

    def claim():
        with QueueStore(database) as queue:
            permit = select_candidate_save(
                queue, watch_runtime.DEFAULT_SCOPE, watch / MANIFEST_NAME
            )
            assert permit.reference_snapshot["post_id"] == "102"

    if when == "before_search":
        claim()
        report, exact = search(roots, body(1))
        assert report["status"] == "ready" and exact["post_id"] == "103"
    else:

        def raced(root, browser, **kwargs):
            assert kwargs["monitor_target"][1] == "102"
            claim()
            return candidate_runtime.run_candidate_trial(
                root, browser, backend_factory=no_browser, **kwargs
            )

        report, exact = search_monitor_candidates(
            watch, legacy, batch, clock=clock, detail_runner=raced
        )
        assert report["status"] == "busy" and exact is None
    with QueueStore(database, read_only=True) as queue:
        details = CandidateDetailStore(queue).list_details(MONITOR_SCOPE)
        assert [d["post_id"] for d in details] == (["103"] if when == "before_search" else [])
