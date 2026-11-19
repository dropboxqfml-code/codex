"""Exercise the bounded runner with real storage and planning, without a website."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import pytest

from image_monitor import watch_runtime
from image_monitor.native_ui import NativeUIError
from image_monitor.queue import QueueStore
from image_monitor.search_list import build_list_url
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE, run_watch_trial, share_watch_report
from image_monitor.watch_store import WatchScope, WatchStore

NOW = datetime(2026, 11, 15, 8, 0, tzinfo=UTC)
MONITOR_SCOPE = replace(DEFAULT_SCOPE, watch_name="목록 감시")


class FakeClock:
    def __init__(self, now=NOW, *, cancel_on_wait=False):
        self.current = now
        self.waits = []
        self.cancel_on_wait = cancel_on_wait

    def now(self):
        return self.current

    def wait(self, seconds):
        self.waits.append(seconds)
        if self.cancel_on_wait:
            raise KeyboardInterrupt
        self.current += timedelta(seconds=seconds)


class ScriptedBrowser:
    browser_version = "test-browser"

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.browser_closed = True

    def __enter__(self):
        self.browser_closed = False
        return self

    def __exit__(self, *_):
        self.browser_closed = True

    def scan(self, scope, observed_at, *, max_pages):
        self.calls.append((scope, observed_at, max_pages))
        assert self.outcomes, "The runner made an unexpected extra website request"
        return self.outcomes.pop(0)(observed_at)


class BrowserFactory:
    def __init__(self, *outcomes):
        self.browser = ScriptedBrowser(outcomes)
        self.calls = []

    def __call__(self, browser, *, now):
        self.calls.append((browser, now()))
        return self.browser


@pytest.fixture(autouse=True)
def allow_controlled_windows_trial(monkeypatch):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)


def no_browser(*_, **__):
    pytest.fail("A persisted wait, block, or busy lease must precede browser creation")


def link(page=2):
    return {
        "canonical_url": build_list_url("normal", "comic_new6", "ai", page),
        "page": page,
        "search_pos": None,
    }


def snapshot(ids, observed_at, *, page=1, links=(), **overrides):
    """Simulated verified-parser output, with wholly invented displayed metadata."""
    return {
        "scope": {
            "gallery_type": "normal",
            "gallery_id": "comic_new6",
            "keyword": "ai",
            "search_type": "search_subject_memo",
            "navigation": {},
        },
        "url": link(page)["canonical_url"],
        "page": page,
        "search_pos": None,
        "observed_at": observed_at.isoformat(),
        "scan_observed_at": observed_at.isoformat(),
        "status": "observed" if ids else "empty",
        "layout_status": "site_verified",
        "queue_eligible": False,
        "rows": [
            {
                "post_id": str(post_id),
                "canonical_url": (
                    f"https://gall.dcinside.com/board/view/?id=comic_new6&no={post_id}"
                ),
                "title": f"Invented private title {post_id}",
                "author_raw": "Invented private author",
                "published_at_raw": "11.15",
                "row_order": index + 2,
            }
            for index, post_id in enumerate(ids)
        ],
        "pagination_candidates": list(links),
        "excluded_rows": [],
        "end_of_results": False,
        "pagination_complete": False,
    } | overrides


def observed(*page_builders):
    def outcome(observed_at):
        pages = [builder(observed_at) for builder in page_builders]
        return {
            "status": "observed",
            "http_status": 200,
            "retry_after": None,
            "pages": pages,
            "navigation": [
                {"url": page["url"], "http_status": 200, "retry_after": None} for page in pages
            ],
        }

    return outcome


def baseline_outcome(observed_at):
    return observed(lambda stamp: snapshot([100, 99], stamp, links=[link()]))(observed_at)


def new_posts_outcome(observed_at):
    return observed(
        lambda stamp: snapshot([104, 103, 100, 99], stamp, links=[link()]),
        lambda stamp: snapshot([98, 97], stamp, page=2),
    )(observed_at)


def unverified_second_page(stamp):
    return observed(
        lambda now: snapshot([104, 103], now, links=[link()]),
        lambda now: snapshot([102, 101], now, page=2, layout_status="unverified"),
    )(stamp)


def http_failure(status, retry_after=None):
    return lambda _: {
        "status": "http_error",
        "http_status": status,
        "retry_after": retry_after,
        "pages": [],
        "navigation": [{"http_status": status, "retry_after": retry_after}],
        "error_type": "HTTPError",
    }


def stored(work_root):
    with QueueStore(work_root / "watch.sqlite") as queue:
        store = WatchStore(queue)
        result = {
            "state": store.get_state(DEFAULT_SCOPE),
            "candidates": store.list_candidates(DEFAULT_SCOPE),
            "scans": store.list_scans(DEFAULT_SCOPE),
            "gaps": store.list_gaps(DEFAULT_SCOPE),
            "summary": queue.summary(),
        }
    assert result["summary"]["posts"] == 0
    assert result["summary"]["jobs"] == 0
    return result


def test_two_cycles_preserve_baseline_and_discover_only_later_posts(tmp_path):
    clock = FakeClock()
    factory = BrowserFactory(baseline_outcome, new_posts_outcome)
    report = run_watch_trial(tmp_path, backend_factory=factory, clock=clock)

    assert report["status"] == "watch_test_completed"
    assert report["cycles_completed"] == 2
    assert clock.waits == [60]
    assert [call[2] for call in factory.browser.calls] == [1, 2]
    assert factory.browser.calls[1][1] - factory.browser.calls[0][1] >= timedelta(seconds=60)
    assert factory.calls == [("chrome", NOW)]
    assert report["browser_closed"] is True
    assert report["new_candidates"] == report["candidate_count"] == 2
    assert report["cycles"][0]["new_candidates"] == 0
    assert report["cycles"][0]["baseline_created"] is True
    assert report["cycles"][1]["baseline_created"] is False
    assert report["images_saved"] is False
    assert report["image_jobs_created"] == 0
    assert json.loads(Path(report["report_path"]).read_text(encoding="utf-8")) == report

    result = stored(tmp_path)
    state = result["state"]
    assert state["generation"] == 2
    assert state["baseline"]["anchor_ids"] == ["100", "99"]
    assert state["checkpoint"]["anchor_ids"] == ["104", "103", "100", "99"]
    assert {row["post_id"] for row in result["candidates"]} == {"104", "103"}
    assert result["gaps"] == []
    assert len(result["scans"]) == 2
    for scan in result["scans"]:
        assert scan["complete"] is True
        assert scan["result"]["queue_eligible"] is False
        assert scan["result"]["save_approved"] is False


def test_immediate_reopening_uses_saved_cooldown_before_creating_browser(tmp_path):
    clock = FakeClock()
    first = run_watch_trial(
        tmp_path, cycles=1, clock=clock, backend_factory=BrowserFactory(baseline_outcome)
    )
    assert first["status"] == "watch_test_completed"
    second = run_watch_trial(tmp_path, clock=clock, backend_factory=no_browser)
    assert second["status"] == "watch_waiting"
    assert second["reason"] == "persisted_cooldown"
    assert second["cycles_completed"] == 0
    assert second["baseline_initialized"] is True
    assert second["next_eligible_at_local"].endswith("+09:00")
    assert clock.waits == []
    assert stored(tmp_path)["state"]["generation"] == 1


def test_only_the_verified_first_page_survives_adjacent_layout_failure(tmp_path):
    clock = FakeClock()
    report = run_watch_trial(
        tmp_path,
        clock=clock,
        backend_factory=BrowserFactory(baseline_outcome, unverified_second_page),
    )
    assert report["status"] == "watch_test_partial"
    assert report["reason"] == "list_profile_unverified_or_incomplete"
    assert report["new_candidates"] == 2
    saved = stored(tmp_path)
    latest = saved["state"]["latest_scan"]
    assert {row["post_id"] for row in saved["candidates"]} == {"104", "103"}
    assert saved["state"]["checkpoint"] == latest["checkpoint"] == saved["scans"][1]["checkpoint"]
    assert saved["state"]["baseline"]["anchor_ids"] == ["100", "99"]
    assert saved["gaps"][0]["reason"] == report["reason"]
    assert not latest["complete"] and latest["result"]["layout_status"] == "unverified"
    assert latest["result"]["verified_prefix_pages"] == 1
    assert [page["page"] for page in latest["result"]["pages"]] == [1]
    assert all(row["page"] == 1 for row in latest["result"]["observations"])
    assert len(latest["result"]["private_observation"]["pages"]) == 2
    assert (
        latest["result"]["queue_eligible"] is False and latest["result"]["save_approved"] is False
    )

    clock.wait(60)
    again = run_watch_trial(
        tmp_path, cycles=1, clock=clock, backend_factory=BrowserFactory(unverified_second_page)
    )
    assert again["new_candidates"] == 0 and again["candidate_count"] == 2
    for candidate in stored(tmp_path)["candidates"]:
        assert candidate["first_scan_id"] == latest["scan_id"]


@pytest.mark.parametrize(
    "fault",
    [
        "no_adjacent_link",
        "different_page",
        "wrong_scope",
        "first_unverified",
        "missing_table",
        "bad_response",
        "unbound_visit",
        "stale_page",
        "invalid_post_identity",
    ],
)
def test_unproven_page_pair_produces_no_prefix_candidates(tmp_path, fault):
    def broken(stamp):
        outcome = unverified_second_page(stamp)
        first, second = outcome["pages"]
        if fault == "no_adjacent_link":
            first["pagination_candidates"] = []
        elif fault == "different_page":
            second["url"] = outcome["navigation"][1]["url"] = link(3)["canonical_url"]
            second["page"] = 3
        elif fault == "wrong_scope":
            second["scope"]["keyword"] = "different"
        elif fault == "first_unverified":
            first["layout_status"] = "unverified"
        elif fault == "missing_table":
            second.update(status="list_missing", rows=[])
        elif fault == "bad_response":
            outcome["navigation"][0]["http_status"] = 403
        elif fault == "unbound_visit":
            outcome["navigation"][1]["url"] = link(3)["canonical_url"]
        elif fault == "stale_page":
            second["observed_at"] = (stamp - timedelta(seconds=1)).isoformat()
        elif fault == "invalid_post_identity":
            second["rows"][0]["post_id"] = "99"
        return outcome

    report = run_watch_trial(
        tmp_path, clock=FakeClock(), backend_factory=BrowserFactory(baseline_outcome, broken)
    )
    assert report["status"] == "watch_test_partial"
    assert report["new_candidates"] == 0
    saved = stored(tmp_path)
    assert not saved["candidates"]
    assert saved["state"]["checkpoint"] == saved["scans"][1]["checkpoint"]
    assert "verified_prefix_pages" not in saved["state"]["latest_scan"]["result"]


def test_poll_interval_starts_after_the_previous_scan_finished(tmp_path):
    clock = FakeClock()

    def slow_baseline(stamp):
        result = baseline_outcome(stamp)
        clock.current += timedelta(seconds=15)
        return result

    factory = BrowserFactory(slow_baseline, new_posts_outcome)
    report = run_watch_trial(tmp_path, clock=clock, backend_factory=factory)
    assert report["status"] == "watch_test_completed"
    assert clock.waits == [60]
    assert factory.browser.calls[1][1] == NOW + timedelta(seconds=75)


def test_service_cooldown_alone_prevents_a_fresh_scope_from_opening_browser(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        queue.defer_service("dcinside", NOW + timedelta(seconds=180))
    report = run_watch_trial(tmp_path, clock=FakeClock(), backend_factory=no_browser)
    assert report["status"] == "watch_waiting"
    assert report["cycles_completed"] == 0
    assert report["baseline_initialized"] is False
    assert stored(tmp_path)["state"]["generation"] == 0


@pytest.mark.parametrize("status", [429, 503])
@pytest.mark.parametrize("retry_form", ["seconds", "http_date"])
def test_retry_after_is_durable_and_never_retried_in_the_failed_run(tmp_path, status, retry_form):
    clock = FakeClock()
    due = NOW + timedelta(seconds=180)
    header = "180" if retry_form == "seconds" else format_datetime(due, usegmt=True)
    factory = BrowserFactory(http_failure(status, header))
    report = run_watch_trial(tmp_path, clock=clock, backend_factory=factory)
    assert report["status"] == "watch_test_failed"
    assert len(factory.browser.calls) == 1
    assert clock.waits == []
    assert stored(tmp_path)["state"]["baseline"] is None
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        saved_due = queue.connection.execute(
            "SELECT not_before FROM service_limits WHERE scope='dcinside'"
        ).fetchone()[0]
    assert datetime.fromisoformat(saved_due) == due

    clock.current += timedelta(seconds=120)
    waiting = run_watch_trial(tmp_path, clock=clock, backend_factory=no_browser)
    assert waiting["status"] == "watch_waiting"
    assert waiting["cycles_completed"] == 0
    clock.current = due
    resumed = run_watch_trial(
        tmp_path, cycles=1, clock=clock, backend_factory=BrowserFactory(baseline_outcome)
    )
    assert resumed["status"] == "watch_test_completed"
    assert stored(tmp_path)["state"]["generation"] == 2


@pytest.mark.parametrize("status", [401, 403, 404, 410])
def test_access_block_requires_review_even_after_time_advances(tmp_path, status):
    clock = FakeClock()
    factory = BrowserFactory(http_failure(status))
    report = run_watch_trial(tmp_path, clock=clock, backend_factory=factory)
    assert report["status"] == "watch_test_failed"
    assert report["reason"] == "access_block_requires_review"
    assert len(factory.browser.calls) == 1
    clock.current += timedelta(days=2)
    reopened = run_watch_trial(tmp_path, clock=clock, backend_factory=no_browser)
    assert reopened["status"] == "watch_test_failed"
    assert reopened["reason"] == "access_block_requires_review"
    assert reopened["cycles_completed"] == 0
    result = stored(tmp_path)
    assert result["state"]["generation"] == 1
    assert result["state"]["baseline"] is None
    assert result["state"]["latest_scan"]["result"]["control"]["blocked"] is True


@pytest.mark.parametrize(
    "changes,expected_reason",
    [
        ({"layout_status": "unverified"}, "list_profile_unverified_or_incomplete"),
        ({"status": "list_ambiguous"}, "list_profile_unverified_or_incomplete"),
        ({"queue_eligible": True}, "list_profile_unverified_or_incomplete"),
        (
            {"excluded_rows": [{"row_order": 0, "reason": "non_numeric"}]},
            "excluded_rows_unverified",
        ),
        (
            {"excluded_rows": [{"row_order": 0, "reason": "survey"}]},
            "excluded_rows_unverified",
        ),
    ],
)
def test_unproven_first_observation_cannot_create_baseline_or_repeat(
    tmp_path, changes, expected_reason
):
    clock = FakeClock()
    factory = BrowserFactory(observed(lambda stamp: snapshot([100, 99], stamp, **changes)))
    report = run_watch_trial(tmp_path, clock=clock, backend_factory=factory)
    assert report["status"] == "watch_test_partial"
    assert report["reason"] == expected_reason
    assert report["cycles_completed"] == 1
    assert factory.browser.browser_closed is True
    assert len(factory.browser.calls) == 1
    assert clock.waits == []
    result = stored(tmp_path)
    assert result["state"]["baseline"] is None
    assert result["state"]["checkpoint"] is None
    assert result["candidates"] == []
    assert len(result["gaps"]) == 1


def test_cancellation_between_cycles_preserves_baseline_closes_browser_and_releases_lease(
    tmp_path,
):
    clock = FakeClock(cancel_on_wait=True)
    factory = BrowserFactory(baseline_outcome)
    report = run_watch_trial(tmp_path, clock=clock, backend_factory=factory)
    assert report["status"] == "watch_test_cancelled"
    assert report["error_type"] == "KeyboardInterrupt"
    assert report["cycles_completed"] == 1
    assert report["browser_closed"] is True
    assert clock.waits == [60]
    result = stored(tmp_path)
    assert result["state"]["generation"] == 1
    assert result["state"]["baseline"]["anchor_ids"] == ["100", "99"]
    with watch_run_lock(tmp_path / "watch.sqlite", DEFAULT_SCOPE):
        pass
    reopened = run_watch_trial(tmp_path, clock=clock, backend_factory=no_browser)
    assert reopened["status"] == "watch_waiting"


@pytest.mark.parametrize("failure", [KeyboardInterrupt, RuntimeError])
def test_interrupted_first_request_persists_cooldown_before_any_reopening(tmp_path, failure):
    clock = FakeClock()

    def interrupted(_):
        clock.current += timedelta(seconds=15)
        raise failure("Invented private browser error details")

    factory = BrowserFactory(interrupted)
    report = run_watch_trial(tmp_path, clock=clock, backend_factory=factory)
    expected = "watch_test_cancelled" if failure is KeyboardInterrupt else "watch_test_failed"
    assert report["status"] == expected
    assert report["browser_closed"] is True
    assert len(factory.browser.calls) == 1
    assert "Invented private browser error details" not in json.dumps(share_watch_report(report))
    assert stored(tmp_path)["state"]["generation"] == 0
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        due = queue.connection.execute(
            "SELECT not_before FROM service_limits WHERE scope='dcinside'"
        ).fetchone()[0]
    assert datetime.fromisoformat(due) >= clock.now() + timedelta(seconds=60)
    reopened = run_watch_trial(tmp_path, clock=clock, backend_factory=no_browser)
    assert reopened["status"] == "watch_waiting"
    assert reopened["cycles_completed"] == 0


@pytest.mark.parametrize("damage", ["missing", "empty", "missing_due", "too_early"])
def test_invalid_stored_control_cannot_remove_cooldown_and_start_requests(tmp_path, damage):
    clock = FakeClock()
    report = run_watch_trial(
        tmp_path, cycles=1, clock=clock, backend_factory=BrowserFactory(baseline_outcome)
    )
    assert report["status"] == "watch_test_completed"
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        latest = WatchStore(queue).get_state(DEFAULT_SCOPE)["latest_scan"]
        result = latest["result"]
        if damage == "missing":
            result.pop("control")
        elif damage == "empty":
            result["control"] = {}
        elif damage == "missing_due":
            result["control"]["next_eligible_at"] = None
        else:
            result["control"]["next_eligible_at"] = (NOW + timedelta(seconds=59)).isoformat()
        with queue._write():
            queue.connection.execute(
                "UPDATE watch_scans SET result_json=? WHERE scan_id=?",
                (json.dumps(result), latest["scan_id"]),
            )
    clock.current += timedelta(minutes=2)
    reopened = run_watch_trial(tmp_path, clock=clock, backend_factory=no_browser)
    assert reopened["status"] == "watch_test_failed"
    assert reopened["error_type"] == "QueueError"
    assert reopened["cycles_completed"] == 0
    assert stored(tmp_path)["state"]["generation"] == 1


def test_incomplete_second_scan_keeps_the_last_complete_checkpoint(tmp_path):
    incomplete = observed(
        lambda stamp: snapshot([104, 103], stamp, links=[link()]),
        lambda stamp: snapshot([102, 101], stamp, page=2),
    )
    factory = BrowserFactory(baseline_outcome, incomplete)
    report = run_watch_trial(tmp_path, clock=FakeClock(), backend_factory=factory)
    assert report["status"] == "watch_test_partial"
    assert report["cycles_completed"] == 2
    result = stored(tmp_path)
    assert result["state"]["generation"] == 2
    assert result["state"]["baseline"]["anchor_ids"] == ["100", "99"]
    assert result["state"]["checkpoint"]["anchor_ids"] == ["100", "99"]
    assert len(result["gaps"]) == 1
    assert {row["post_id"] for row in result["candidates"]} == {"104", "103", "102", "101"}


def test_same_scope_busy_lease_prevents_database_and_browser_work(tmp_path):
    database = tmp_path / "watch.sqlite"
    with watch_run_lock(database, DEFAULT_SCOPE):
        report = run_watch_trial(tmp_path, clock=FakeClock(), backend_factory=no_browser)
    assert report["status"] == "watch_busy"
    assert report["reason"] == "another_scan_owns_this_scope"
    assert report["cycles_completed"] == 0
    assert not database.exists()


@pytest.mark.parametrize("malicious_part", ["snapshot_scope", "post_url"])
def test_other_scope_identity_cannot_initialize_or_add_candidates(tmp_path, malicious_part):
    def malicious(stamp):
        page = snapshot([100, 99], stamp)
        if malicious_part == "snapshot_scope":
            page["scope"]["gallery_id"] = "another_gallery"
        else:
            page["rows"][0]["canonical_url"] = (
                "https://gall.dcinside.com/board/view/?id=another_gallery&no=100"
            )
        return page

    report = run_watch_trial(
        tmp_path, clock=FakeClock(), backend_factory=BrowserFactory(observed(malicious))
    )
    assert report["status"] == "watch_test_partial"
    result = stored(tmp_path)
    assert result["state"]["baseline"] is None
    assert result["candidates"] == []


def test_shared_report_keeps_counts_without_private_list_content_or_paths(tmp_path):
    report = run_watch_trial(
        tmp_path,
        clock=FakeClock(),
        backend_factory=BrowserFactory(baseline_outcome, new_posts_outcome),
    )
    report |= {
        "title": "Invented private title",
        "author_raw": "Invented private author",
        "source_url": link()["canonical_url"],
        "state_database": str(tmp_path / "watch.sqlite"),
    }
    shared = share_watch_report(report)
    encoded = json.dumps(shared, ensure_ascii=False)
    assert shared["status"] == "watch_test_completed"
    assert shared["candidate_count"] == 2
    assert shared["cycles"][1]["ordinary_rows"] == 6
    for secret in (
        "Invented private title",
        "Invented private author",
        "https://",
        "canonical_url",
        str(tmp_path),
        "report_path",
        "state_database",
    ):
        assert secret not in encoded
    private = stored(tmp_path)["state"]["latest_scan"]["result"]["private_observation"]
    assert private["pages"][0]["rows"][0]["title"] == "Invented private title 104"


def test_platform_guard_runs_before_creating_any_files(tmp_path, monkeypatch):
    def unsupported():
        raise NativeUIError("Windows is required")

    monkeypatch.setattr(watch_runtime, "require_windows", unsupported)
    root = tmp_path / "not-created"
    with pytest.raises(NativeUIError, match="Windows"):
        run_watch_trial(root, clock=FakeClock(), backend_factory=no_browser)
    assert not root.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("interval", [60.0, True, 59, 301, "60"])
def test_invalid_interval_is_rejected_before_creating_state(tmp_path, interval):
    root = tmp_path / "not-created"
    with pytest.raises(NativeUIError, match="integer"):
        run_watch_trial(root, interval_seconds=interval, backend_factory=no_browser)
    assert not root.exists()


def test_established_state_without_latest_scan_fails_closed():
    with pytest.raises(watch_runtime.QueueError, match="missing"):
        watch_runtime._control({"generation": 1, "latest_scan": None})


def test_new_watch_name_keeps_existing_trial_baseline_and_candidates_separate(tmp_path):
    clock = FakeClock()
    initial = run_watch_trial(
        tmp_path,
        clock=clock,
        backend_factory=BrowserFactory(baseline_outcome, new_posts_outcome),
    )
    assert initial["candidate_count"] == 2
    previous = stored(tmp_path)
    clock.current += timedelta(seconds=60)
    fresh = run_watch_trial(
        tmp_path,
        clock=clock,
        scope=MONITOR_SCOPE,
        backend_factory=BrowserFactory(baseline_outcome, new_posts_outcome),
    )
    assert fresh["status"] == "watch_test_completed"
    assert fresh["cycles"][0]["baseline_created"] is True
    assert fresh["cycles"][0]["new_candidates"] == 0
    assert fresh["candidate_count"] == 2
    assert stored(tmp_path) == previous
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        monitor = WatchStore(queue)
        assert monitor.get_state(MONITOR_SCOPE)["generation"] == 2
        assert len(monitor.list_candidates(MONITOR_SCOPE)) == 2
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0


def test_custom_watch_still_uses_legacy_shared_scan_lease(tmp_path):
    with watch_run_lock(tmp_path / "watch.sqlite", DEFAULT_SCOPE):
        report = run_watch_trial(
            tmp_path, scope=MONITOR_SCOPE, clock=FakeClock(), backend_factory=no_browser
        )
    assert report["status"] == "watch_busy"
    assert not (tmp_path / "watch.sqlite").exists()


@pytest.mark.parametrize(
    "scope",
    [
        None,
        "monitor",
        replace(MONITOR_SCOPE, watch_name=""),
        replace(MONITOR_SCOPE, gallery_type="minor"),
        replace(MONITOR_SCOPE, gallery_id="another"),
        replace(MONITOR_SCOPE, keyword="AI"),
        replace(MONITOR_SCOPE, search_type="other"),
    ],
)
def test_unreviewed_or_invalid_scope_is_rejected_before_filesystem_work(tmp_path, scope):
    root = tmp_path / "not-created"
    with pytest.raises(NativeUIError, match="scope"):
        run_watch_trial(root, scope=scope, backend_factory=no_browser)
    assert not root.exists()


@pytest.mark.parametrize("blocked_scope", [DEFAULT_SCOPE, MONITOR_SCOPE])
@pytest.mark.parametrize("status", [401, 403, 404, 410])
def test_latest_list_access_block_applies_to_a_fresh_watch_scope(tmp_path, blocked_scope, status):
    first = run_watch_trial(
        tmp_path,
        scope=blocked_scope,
        clock=FakeClock(),
        backend_factory=BrowserFactory(http_failure(status)),
    )
    assert first["status"] == "watch_test_failed"
    other = MONITOR_SCOPE if blocked_scope == DEFAULT_SCOPE else DEFAULT_SCOPE
    report = run_watch_trial(
        tmp_path,
        scope=other,
        clock=FakeClock(NOW + timedelta(minutes=5)),
        backend_factory=no_browser,
    )
    assert report["status"] == "watch_test_failed"
    assert report["reason"] == "access_block_requires_review"
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        assert WatchStore(queue).get_state(other)["generation"] == 0


def _manual_scan(store, scope, *, control=None, at=NOW):
    state = store.get_state(scope)
    result = {"mode": "invented local fixture"}
    if control is not None:
        result["control"] = control
    return store.persist_scan(
        scope,
        observed_at=at,
        expected_generation=state["generation"],
        scan_result=result,
        candidates=[],
        checkpoint={"anchor_ids": []},
        complete=False,
        gap_reason="invented fixture",
        baseline=None,
    )


def test_global_list_block_uses_only_latest_state_not_historical_scans(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        store = WatchStore(queue)
        _manual_scan(store, DEFAULT_SCOPE, control={"blocked": True})
        _manual_scan(
            store,
            DEFAULT_SCOPE,
            control={"blocked": False},
            at=NOW + timedelta(seconds=1),
        )
    report = run_watch_trial(
        tmp_path,
        scope=MONITOR_SCOPE,
        cycles=1,
        clock=FakeClock(NOW + timedelta(minutes=5)),
        backend_factory=BrowserFactory(baseline_outcome),
    )
    assert report["status"] == "watch_test_completed"


def test_unrelated_fixture_without_control_does_not_create_a_global_block(tmp_path):
    toy = WatchScope("invented fixture", "normal", "other", "ai", "search_subject_memo")
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        _manual_scan(WatchStore(queue), toy)
        before = WatchStore(queue).get_state(toy)
    report = run_watch_trial(
        tmp_path,
        scope=MONITOR_SCOPE,
        cycles=1,
        clock=FakeClock(),
        backend_factory=BrowserFactory(baseline_outcome),
    )
    assert report["status"] == "watch_test_completed"
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        assert WatchStore(queue).get_state(toy) == before


@pytest.mark.parametrize("blocked", [None, 0, 1, "true", {}, []])
def test_malformed_explicit_global_block_metadata_fails_before_browser(tmp_path, blocked):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        _manual_scan(WatchStore(queue), DEFAULT_SCOPE, control={"blocked": blocked})
    report = run_watch_trial(
        tmp_path, scope=MONITOR_SCOPE, clock=FakeClock(), backend_factory=no_browser
    )
    assert report["status"] == "watch_test_failed"
    assert report["error_type"] == "QueueError"


class StoppableFactory(BrowserFactory):
    def __call__(self, browser, *, now, should_stop):
        self.stop_condition = should_stop
        return super().__call__(browser, now=now)


def test_requested_stop_before_factory_creates_no_browser_or_scan(tmp_path):
    report = run_watch_trial(
        tmp_path,
        scope=MONITOR_SCOPE,
        clock=FakeClock(),
        backend_factory=no_browser,
        should_stop=lambda: True,
    )
    assert report["status"] == "watch_test_cancelled"
    assert report["reason"] == "requested_stop"
    assert report["error_type"] is None
    assert report["browser_closed"] is True
    assert report["cycles_completed"] == 0
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        assert WatchStore(queue).get_state(MONITOR_SCOPE)["generation"] == 0


def test_stop_predicate_is_forwarded_only_when_explicitly_supplied(tmp_path):
    def predicate():
        return False

    factory = StoppableFactory(baseline_outcome)
    report = run_watch_trial(
        tmp_path,
        cycles=1,
        should_stop=predicate,
        clock=FakeClock(),
        backend_factory=factory,
    )
    assert report["status"] == "watch_test_completed"
    assert factory.stop_condition is predicate


def test_cancelled_first_page_cannot_initialize_a_new_baseline(tmp_path):
    def cancelled(stamp):
        return baseline_outcome(stamp) | {"status": "cancelled"}

    report = run_watch_trial(
        tmp_path,
        cycles=1,
        should_stop=lambda: False,
        clock=FakeClock(),
        backend_factory=StoppableFactory(cancelled),
    )
    assert report["status"] == "watch_test_cancelled"
    assert report["error_type"] is None
    assert report["cycles"][0]["navigation_attempts"] == 1
    result = stored(tmp_path)
    assert result["state"]["baseline"] is None
    assert result["state"]["checkpoint"] is None
    assert result["candidates"] == []
    assert result["scans"][0]["gap_reason"] == "requested_stop"


def test_cancelled_overlap_scan_preserves_coverage_but_commits_safe_candidates(tmp_path):
    clock = FakeClock()
    run_watch_trial(
        tmp_path, cycles=1, clock=clock, backend_factory=BrowserFactory(baseline_outcome)
    )
    before = stored(tmp_path)["state"]
    clock.current += timedelta(seconds=60)

    def cancelled(stamp):
        result = new_posts_outcome(stamp)
        return result | {
            "status": "cancelled",
            "pages": result["pages"][:1],
            "navigation": result["navigation"][:1],
        }

    report = run_watch_trial(
        tmp_path,
        cycles=1,
        should_stop=lambda: False,
        clock=clock,
        backend_factory=StoppableFactory(cancelled),
    )
    assert report["status"] == "watch_test_cancelled"
    assert report["cycles"][0]["complete"] is False
    result = stored(tmp_path)
    assert result["state"]["baseline"] == before["baseline"]
    assert result["state"]["checkpoint"] == before["checkpoint"]
    assert {row["post_id"] for row in result["candidates"]} == {"104", "103"}
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        assert queue.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


def test_stop_arriving_as_scan_returns_does_not_advance_the_baseline(tmp_path):
    stopped = False

    def last_moment_stop(stamp):
        nonlocal stopped
        stopped = True
        return baseline_outcome(stamp)

    report = run_watch_trial(
        tmp_path,
        cycles=1,
        should_stop=lambda: stopped,
        clock=FakeClock(),
        backend_factory=StoppableFactory(last_moment_stop),
    )
    assert report["status"] == "watch_test_cancelled"
    assert stored(tmp_path)["state"]["baseline"] is None


def test_stop_during_between_cycle_wait_avoids_the_next_navigation(tmp_path):
    stopped = False

    class StopClock(FakeClock):
        def wait(self, seconds):
            nonlocal stopped
            super().wait(seconds)
            stopped = True

    factory = StoppableFactory(baseline_outcome)
    report = run_watch_trial(
        tmp_path,
        should_stop=lambda: stopped,
        clock=StopClock(),
        backend_factory=factory,
    )
    assert report["status"] == "watch_test_cancelled"
    assert report["cycles_completed"] == 1
    assert len(factory.browser.calls) == 1
    assert stored(tmp_path)["state"]["generation"] == 1


@pytest.mark.parametrize("predicate", [False, 1, "stop"])
def test_noncallable_stop_is_rejected_before_filesystem_work(tmp_path, predicate):
    root = tmp_path / "not-created"
    with pytest.raises(NativeUIError, match="callable"):
        run_watch_trial(root, should_stop=predicate, backend_factory=no_browser)
    assert not root.exists()


@pytest.mark.parametrize("status", [401, 403, 404, 410])
def test_cancellation_preserves_an_observed_list_access_block(tmp_path, status):
    def cancelled(_stamp):
        return http_failure(status)(_stamp) | {"status": "cancelled"}

    report = run_watch_trial(
        tmp_path,
        cycles=1,
        scope=MONITOR_SCOPE,
        should_stop=lambda: False,
        clock=FakeClock(),
        backend_factory=StoppableFactory(cancelled),
    )
    assert report["status"] == "watch_test_cancelled"
    reopened = run_watch_trial(
        tmp_path,
        scope=DEFAULT_SCOPE,
        clock=FakeClock(NOW + timedelta(minutes=5)),
        backend_factory=no_browser,
    )
    assert reopened["reason"] == "access_block_requires_review"


@pytest.mark.parametrize("status", [429, 503])
def test_cancellation_preserves_observed_server_wait(tmp_path, status):
    def cancelled(_stamp):
        return http_failure(status, "180")(_stamp) | {"status": "cancelled"}

    report = run_watch_trial(
        tmp_path,
        cycles=1,
        should_stop=lambda: False,
        clock=FakeClock(),
        backend_factory=StoppableFactory(cancelled),
    )
    assert report["status"] == "watch_test_cancelled"
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        due = queue.connection.execute(
            "SELECT not_before FROM service_limits WHERE scope='dcinside'"
        ).fetchone()[0]
        assert datetime.fromisoformat(due) >= NOW + timedelta(seconds=180)
    reopened = run_watch_trial(
        tmp_path,
        scope=MONITOR_SCOPE,
        clock=FakeClock(NOW + timedelta(seconds=60)),
        backend_factory=no_browser,
    )
    assert reopened["status"] == "watch_waiting"


@pytest.mark.parametrize("broken", ["missing", "other_scope", "generation"])
def test_corrupt_old_latest_state_cannot_be_bypassed_by_a_new_watch_name(tmp_path, broken):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        store = WatchStore(queue)
        _manual_scan(store, DEFAULT_SCOPE, control={"blocked": True})
        if broken == "other_scope":
            other = WatchScope("invented fixture", "normal", "other", "ai", "search_subject_memo")
            other_id = _manual_scan(store, other)["scan_id"]
        with queue._write():
            if broken == "generation":
                queue.connection.execute(
                    "UPDATE watch_state SET generation=generation+1 WHERE watch_name=?",
                    (DEFAULT_SCOPE.watch_name,),
                )
            else:
                queue.connection.execute(
                    "UPDATE watch_state SET latest_scan_id=? WHERE watch_name=?",
                    ("0" * 32 if broken == "missing" else other_id, DEFAULT_SCOPE.watch_name),
                )
    report = run_watch_trial(
        tmp_path, scope=MONITOR_SCOPE, clock=FakeClock(), backend_factory=no_browser
    )
    assert report["status"] == "watch_test_failed"
    assert report["error_type"] == "QueueError"
