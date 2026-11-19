"""Carry a bounded search across confirmed empty posts and exact saved observations."""

import json

import pytest
from test_candidate_runtime import BrowserFactory as DetailBrowser
from test_candidate_runtime import no_browser
from test_candidate_save_runtime import BASELINE, NOW
from test_candidate_save_runtime import snapshot as body_snapshot
from test_watch_runtime import BrowserFactory, FakeClock, baseline_outcome, link, observed, snapshot

from image_monitor import candidate_runtime, watch_image_search, watch_runtime
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.queue import QueueStore
from image_monitor.watch_store import WatchStore


@pytest.fixture
def roots(tmp_path, monkeypatch):
    for module in (candidate_runtime, watch_image_search, watch_runtime):
        monkeypatch.setattr(module, "require_windows", lambda: None)
    watch, legacy, save = (tmp_path / name for name in ("watch", "legacy", "save"))
    clock = FakeClock(BASELINE)
    latest = observed(
        lambda stamp: snapshot([110, 109, 108], stamp, links=[link()]),
        lambda stamp: snapshot([107, 106, 105], stamp, page=2, links=[link(3)]),
    )
    report = watch_runtime.run_watch_trial(
        watch, clock=clock, backend_factory=BrowserFactory(baseline_outcome, latest)
    )
    assert report["recent_pages_verified"] and report["new_candidates"] == 6
    clock.current = NOW
    clock.waits.clear()
    return watch, legacy, save, clock


def body(count, *, attachment=False):
    def observation(candidate, stamp):
        post = body_snapshot(candidate, stamp, count=count)
        if attachment:
            post["attachment_inventory"] = [{"filename": "private-attachment.zip"}]
        return {
            "url": candidate["post_url"],
            "status": "observed",
            "http_status": 200,
            "retry_after": None,
            "navigation_attempts": 1,
            "snapshot": post,
        }

    return observation


def search(roots, backend=no_browser):
    watch, legacy, save, clock = roots
    return watch_image_search.run_watch_image_search(
        watch, legacy, save, clock=clock, backend_factory=backend
    )


def test_attachment_only_then_first_saveable_body_yields_private_exact_handoff(roots):
    watch, _, _, clock = roots
    seed = candidate_runtime.run_candidate_trial(
        watch,
        max_candidates=1,
        recent_scan_only=True,
        clock=clock,
        backend_factory=DetailBrowser(body(0, attachment=True)),
    )
    assert seed["candidates_completed"] == 1
    backend = DetailBrowser(body(0), body(1))
    result, handoff = search(roots, backend)
    assert result["status"] == "image_candidate_ready" and result["eligible_body_images"] == 1
    assert result["outcome_counts"] == {"no_body_images_observed": 2, "save_ready": 1}
    assert result["source_scan"]["unattempted_candidates"] == 5
    assert result["new_details_checked"] == 2 and result["stored_empty_posts"] == 1
    assert [row["post_id"] for row, _ in backend.browser.calls] == ["109", "108"]
    with QueueStore(watch / "watch.sqlite", read_only=True) as queue:
        state = WatchStore(queue).get_state(watch_runtime.DEFAULT_SCOPE)
        detail = CandidateDetailStore(queue).get(handoff["attempt_id"])
        assert detail["post_id"] == "108" and handoff["scan_id"] == state["latest_scan"]["scan_id"]
        assert state["latest_scan"]["gap_reason"] == "anchor_not_reached"
        assert queue.summary()["jobs"] == 0
    encoded = json.dumps(result)
    assert all(secret not in encoded for secret in (*handoff.values(), "private", "https://"))
    repeated, exact = search(roots)
    assert repeated["status"] == "image_candidate_ready" and repeated["new_details_checked"] == 0
    assert repeated["stored_empty_posts"] == 2 and exact == handoff


def test_limit_leaves_remaining_candidates_and_exhaustion_preserves_counts(roots):
    for i in range(2):
        backend = DetailBrowser(*(body(0) for _ in range(3)))
        result, exact = search(roots, backend)
        assert exact is None and result["new_details_checked"] == 3
        assert result["stored_empty_posts"] == i * 3
        assert result["outcome_counts"] == {"no_body_images_observed": (i + 1) * 3}
        assert len(backend.browser.calls) == 3
        assert result["status"] == ("image_search_limit" if i == 0 else "image_search_exhausted")
    final, exact = search(roots)
    assert final["status"] == "image_search_exhausted" and final["new_details_checked"] == 0
    assert final["stored_empty_posts"] == 6 and exact is None


def test_abnormal_new_detail_stops_then_independent_post_can_be_examined(roots):
    def incomplete_image(candidate, stamp):
        outcome = body(1)(candidate, stamp)
        outcome["snapshot"]["images"][0]["natural_width"] = 0
        return outcome

    result, exact = search(roots, DetailBrowser(incomplete_image))
    assert result["status"] == "image_search_review" and exact is None
    assert result["new_details_checked"] == 1 and result["outcome_counts"] == {"needs_review": 1}
    following, exact = search(roots, DetailBrowser(body(2)))
    assert following["eligible_body_images"] == 2 and exact
    assert following["outcome_counts"] == {"needs_review": 1, "save_ready": 1}


@pytest.mark.parametrize("http_status", [404, 410])
def test_oversized_and_deleted_posts_continue_to_two_image_body_in_one_run(roots, http_status):
    def deleted(candidate, stamp):
        return {
            "url": candidate["post_url"],
            "status": "http_error",
            "http_status": http_status,
            "retry_after": None,
            "navigation_attempts": 1,
            "error_type": "HTTPStatusError",
            "error_code": None,
            "snapshot": None,
        }

    browser = DetailBrowser(body(3), deleted, body(2))
    result, exact = search(roots, browser)
    assert result["status"] == "image_candidate_ready" and result["eligible_body_images"] == 2
    assert result["outcome_counts"] == {"outside_save_limit": 1, "unavailable": 1, "save_ready": 1}
    assert result["new_details_checked"] == len(browser.browser.calls) == 3
    with QueueStore(roots[0] / "watch.sqlite", read_only=True) as queue:
        assert CandidateDetailStore(queue).get(exact["attempt_id"])["post_id"] == "108"


def test_three_fully_observed_oversized_posts_still_stop_at_run_limit(roots):
    browser = DetailBrowser(body(3), body(4), body(5))
    result, exact = search(roots, browser)
    assert exact is None and result["status"] == "image_search_limit"
    assert result["outcome_counts"] == {"outside_save_limit": 3}
    assert result["new_details_checked"] == len(browser.browser.calls) == 3


def test_pending_target_from_previous_scan_is_not_launched_against_replacement(roots):
    watch, _, _, clock = roots
    with QueueStore(watch / "watch.sqlite", read_only=True) as queue:
        before = WatchStore(queue).get_state(watch_runtime.DEFAULT_SCOPE)["latest_scan"]["scan_id"]
    current = observed(
        lambda stamp: snapshot([120, 119], stamp, links=[link()]),
        lambda stamp: snapshot([118, 117], stamp, page=2, links=[link(3)]),
    )
    watch_runtime.run_watch_trial(
        watch, clock=clock, cycles=1, backend_factory=BrowserFactory(current)
    )
    result = candidate_runtime.run_candidate_trial(
        watch,
        max_candidates=1,
        recent_scan_only=True,
        recent_target=(before, "110"),
        clock=clock,
        backend_factory=no_browser,
    )
    assert result["reason"] == "source_scan_changed" and result["candidates_completed"] == 0
