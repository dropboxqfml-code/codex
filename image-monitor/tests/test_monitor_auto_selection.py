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
from image_monitor.candidate_policy import classify_candidate_detail, unobserved_detail
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
    assert repeat["status"] == "ready" and repeat["new_details_checked"] == 0 and exact == binding


def test_search_yields_to_next_invocation_after_three_empty_posts(roots):
    for expected in ("limit", "no_candidates"):
        report, exact = search(roots, body(0), body(0), body(0))
        assert report["status"] == expected and exact is None
        assert report["new_details_checked"] == 3 and report["browser_closed"]
    report, exact = search(roots)
    assert (
        report["status"] == "no_candidates" and exact is None and report["new_details_checked"] == 0
    )


def test_backlog_can_exceed_previous_batch_sixty_four_detail_limit(roots):
    watch, _, _, clock = roots
    with QueueStore(watch / "watch.sqlite") as queue:
        store = WatchStore(queue)
        state = store.get_state(MONITOR_SCOPE)
        stamp = clock.now()
        store.persist_scan(
            MONITOR_SCOPE,
            observed_at=stamp,
            expected_generation=state["generation"],
            scan_result=state["latest_scan"]["result"],
            complete=True,
            candidates=[
                {
                    "post_id": str(i),
                    "post_url": f"https://gall.dcinside.com/board/view/?id=comic_new6&no={i}",
                    "title": "Invented",
                    "shown_metadata": {},
                }
                for i in range(300, 362)
            ],
            checkpoint=state["checkpoint"],
        )
        stored = CandidateDetailStore(queue)
        baseline = state["baseline"]
        for candidate in stored.list_pending(MONITOR_SCOPE, limit=100):
            post = candidate["post_id"]
            attempt = stored.start(
                MONITOR_SCOPE,
                post,
                expected_first_scan_id=candidate["first_scan_id"],
                baseline_observed_at=BASELINE,
                started_at=stamp,
            )
            outcome = (body(1) if post == "361" else deleted)(candidate, stamp)
            if outcome["status"] == "observed":
                classification = classify_candidate_detail(candidate, baseline, outcome["snapshot"])
            else:
                classification = unobserved_detail("candidate_unavailable")
            stored.finish(
                attempt["attempt_id"],
                finished_at=stamp,
                result={
                    "private_observation": outcome,
                    "classification": classification,
                    "control": {
                        "blocked": False,
                        "interval_seconds": 60,
                        "finished_at": stamp.isoformat(),
                        "http_status": outcome["http_status"],
                        "next_eligible_at": (stamp + timedelta(seconds=60)).isoformat(),
                    },
                },
            )
    report, exact = search(roots)
    assert report["status"] == "ready", report
    assert exact["post_id"] == "361" and report["new_details_checked"] == 0


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
