"""Verify the durable checkpoint before an extended list scan can advance it."""

from datetime import timedelta

import pytest
from test_watch_runtime import BrowserFactory, FakeClock, baseline_outcome, link, observed, snapshot

from image_monitor import watch_runtime
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


def pages(*post_ids):
    return observed(
        *[
            lambda stamp, index=index, post_id=post_id: snapshot(
                [post_id], stamp, page=index, links=[link(index + 1)]
            )
            for index, post_id in enumerate(post_ids, 1)
        ]
    )


@pytest.fixture
def gap(tmp_path, monkeypatch):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    clock = FakeClock()

    def run(outcome):
        backend = BrowserFactory(outcome)
        report = watch_runtime.run_watch_trial(
            tmp_path,
            scope=MONITOR_SCOPE,
            cycles=1,
            clock=clock,
            backend_factory=backend,
            follow_up_gaps=True,
        )
        clock.wait(60)
        return report, backend.browser.calls[0][2]

    assert run(baseline_outcome)[1] == 1
    partial, limit = run(pages(110, 108))
    assert limit == 2 and partial["recent_pages_verified"] is True

    def records():
        with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
            store = WatchStore(queue)
            state = store.get_state(MONITOR_SCOPE)
            candidates = {c["post_id"] for c in store.list_candidates(MONITOR_SCOPE)}
            return state, candidates

    return run, records


@pytest.mark.parametrize(
    "fault", ["wrong_url", "backwards", "retry_after", "over_budget", "extra_after_overlap"]
)
def test_bad_followup_transport_cannot_advance_checkpoint_or_add_candidates(gap, fault):
    run, records = gap
    previous, earlier_ids = records()

    def altered(stamp):
        post_ids = (100, 98, 97) if fault == "extra_after_overlap" else (120, 100, 98)
        result = pages(*post_ids)(stamp)
        if fault == "wrong_url":
            result["navigation"][-1]["url"] = link(4)["canonical_url"]
        elif fault == "backwards":
            result["pages"][1]["observed_at"] = (stamp + timedelta(seconds=1)).isoformat()
        elif fault == "retry_after":
            result["navigation"][-1]["retry_after"] = result["retry_after"] = "120"
        elif fault == "over_budget":
            result = pages(120, 110, 100, 98)(stamp)
        return result

    report, limit = run(altered)
    assert limit == 3
    assert report["reason"] == "list_navigation_unverified"
    state, stored_ids = records()
    assert state["checkpoint"] == previous["checkpoint"] and stored_ids == earlier_ids
    assert not state["latest_scan"]["complete"] and "closed_monitor_scan" not in report


@pytest.mark.parametrize("fault", ["unverified_layout", "throttled"])
def test_followup_keeps_verified_linked_prefix_when_last_page_fails(gap, fault):
    run, records = gap
    previous, earlier_ids = records()

    def altered(stamp):
        result = pages(120, 118, 116)(stamp)
        if fault == "unverified_layout":
            result["pages"][-1]["layout_status"] = "unverified"
        else:
            result["pages"].pop()
            result["navigation"][-1].update(http_status=429, retry_after="180")
            result.update(status="http_error", http_status=429, retry_after="180")
        return result

    report, limit = run(altered)
    assert limit == 3 and report["new_candidates"] == 2
    state, stored_ids = records()
    assert stored_ids == earlier_ids | {"120", "118"}
    assert state["checkpoint"] == previous["checkpoint"] and "closed_monitor_scan" not in report
    scan = state["latest_scan"]
    assert scan["complete"] is False
    if fault == "unverified_layout":
        assert scan["result"]["verified_prefix_pages"] == 2
    else:
        assert scan["result"]["control"]["http_status"] == 429
