"""Exercise the bounded runner with real storage and planning, without a website."""

import json
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
from image_monitor.watch_store import WatchStore

NOW = datetime(2026, 11, 15, 8, 0, tzinfo=UTC)


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
