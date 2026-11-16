"""Exercise candidate-detail trials with real SQLite and an inert owned browser."""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from image_monitor import candidate_runtime
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.native_ui import NativeUIError
from image_monitor.queue import QueueStore
from image_monitor.search_list import build_list_url
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE, run_watch_trial
from image_monitor.watch_store import WatchStore

NOW = datetime(2026, 11, 16, 4, 0, tzinfo=UTC)
BASELINE_TIME = NOW - timedelta(minutes=10)


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

    def inspect(self, candidate, observed_at):
        self.calls.append((deepcopy(candidate), observed_at))
        assert self.outcomes, "The runner made an unexpected detail navigation"
        return self.outcomes.pop(0)(candidate, observed_at)


class BrowserFactory:
    def __init__(self, *outcomes):
        self.browser = ScriptedBrowser(outcomes)
        self.calls = []

    def __call__(self, browser, *, now):
        self.calls.append((browser, now()))
        return self.browser


@pytest.fixture(autouse=True)
def allow_controlled_windows_trial(monkeypatch):
    monkeypatch.setattr(candidate_runtime, "require_windows", lambda: None)


def no_browser(*_, **__):
    pytest.fail("Eligibility and pending checks must precede browser creation")


def seed(work_root, ids=("103", "104")):
    """Create two invented prior list scans; do not run any collection pipeline."""
    baseline = {
        "mode": "new",
        "observed_at": BASELINE_TIME.isoformat(),
        "anchor_ids": ["100", "99"],
        "source_url": build_list_url("normal", "comic_new6", "ai"),
        "requires_published_at_filter": True,
    }
    with QueueStore(work_root / "watch.sqlite") as queue:
        store = WatchStore(queue)
        for generation, stamp, posts in (
            (0, BASELINE_TIME, ()),
            (1, NOW - timedelta(seconds=120), ids),
        ):
            store.persist_scan(
                DEFAULT_SCOPE,
                observed_at=stamp,
                expected_generation=generation,
                scan_result={
                    "mode": "invented_fixture",
                    "control": {
                        "finished_at": stamp.isoformat(),
                        "next_eligible_at": (stamp + timedelta(seconds=60)).isoformat(),
                        "interval_seconds": 60,
                        "blocked": False,
                    },
                },
                candidates=[
                    {
                        "post_id": post_id,
                        "post_url": (
                            f"https://gall.dcinside.com/board/view/?id=comic_new6&no={post_id}"
                        ),
                        "title": f"Invented private list title {post_id}",
                        "shown_metadata": {
                            "author_raw": "Invented private list author",
                            "published_at_raw": "13:00",
                            "baseline_observed_at": baseline["observed_at"],
                            "requires_published_at_filter": True,
                        },
                    }
                    for post_id in posts
                ],
                checkpoint={
                    "anchor_ids": list(posts) + ["100", "99"],
                    "observed_at": stamp.isoformat(),
                    "source_url": baseline["source_url"],
                },
                complete=True,
                baseline=baseline if generation == 0 else None,
            )
    return saved(work_root)


def saved(work_root):
    with QueueStore(work_root / "watch.sqlite") as queue:
        watch = WatchStore(queue)
        return {
            "state": watch.get_state(DEFAULT_SCOPE),
            "candidates": watch.list_candidates(DEFAULT_SCOPE),
            "scans": watch.list_scans(DEFAULT_SCOPE),
            "gaps": watch.list_gaps(DEFAULT_SCOPE),
            "details": CandidateDetailStore(queue).list_details(DEFAULT_SCOPE),
            "summary": queue.summary(),
            "service": queue.connection.execute(
                "SELECT not_before FROM service_limits WHERE scope='dcinside'"
            ).fetchone(),
        }


def detail_snapshot(candidate, observed_at, *, published_at=None, **overrides):
    published_at = published_at or BASELINE_TIME + timedelta(minutes=5)
    return {
        "schema_version": 1,
        "gallery_type": candidate["gallery_type"],
        "gallery_id": candidate["gallery_id"],
        "post_id": candidate["post_id"],
        "post_url": candidate["post_url"],
        "title": "Invented private detail title",
        "nickname": "Invented private detail author",
        "ip_display": "123.45",
        "published_at": published_at.isoformat(),
        "published_at_raw": published_at.astimezone(ZoneInfo("Asia/Seoul")).strftime(
            "%Y.%m.%d %H:%M:%S"
        ),
        "date_parse_reason": None,
        "observed_at": observed_at.isoformat(),
        "layout_status": "unverified",
        "queue_eligible": False,
        "profile_evidence": {
            "header_count": 1,
            "header_field_counts": {".gall_writer": 1, ".gall_date": 1, ".title_subject": 1},
            "queue_validation": "not_enabled",
        },
        "image_counts": {"body_occurrences": 2, "included_unique": 1, "excluded": 1, "pending": 0},
        "images": [
            {
                "display_url": "https://private.example/invented.webp?secret=private-token",
                "stable_id": "private-resource-hash",
                "original_attachment_filename": "Invented private filename.webp",
                "original_filename_match_status": "matched",
            }
        ],
        "pending_images": [],
        "excluded_images": [{"reason": "body_dccon"}],
        "attachment_inventory": [{"filename": "Invented private filename.webp"}],
    } | overrides


def observed(**snapshot_options):
    return lambda candidate, stamp: {
        "status": "observed",
        "http_status": 200,
        "retry_after": None,
        "navigation_attempts": 1,
        "snapshot": detail_snapshot(candidate, stamp, **snapshot_options),
    }


def http_failure(status, retry_after=None):
    return lambda *_: {
        "status": "http_error",
        "http_status": status,
        "retry_after": retry_after,
        "navigation_attempts": 1,
        "error_type": "HTTPStatusError",
    }


def run(work_root, **options):
    return candidate_runtime.run_candidate_trial(work_root, **options)


def assert_list_state_unchanged(before, after):
    for key in ("state", "candidates", "scans", "gaps"):
        assert after[key] == before[key], key
    assert after["summary"]["posts"] == after["summary"]["jobs"] == 0


def test_two_details_classify_publication_without_creating_image_work_or_list_scan(tmp_path):
    before = seed(tmp_path)
    clock = FakeClock()
    factory = BrowserFactory(
        observed(), observed(published_at=BASELINE_TIME - timedelta(seconds=1))
    )
    report = run(tmp_path, clock=clock, backend_factory=factory)

    assert report["status"] == "candidate_test_completed", report
    assert report["browser_closed"] is True
    assert report["images_saved"] is False
    assert report["image_jobs_created"] == 0
    assert clock.waits == [60]
    assert factory.calls == [("chrome", NOW)]
    assert len(factory.browser.calls) == 2
    assert factory.browser.calls[1][1] - factory.browser.calls[0][1] == timedelta(seconds=60)
    after = saved(tmp_path)
    assert_list_state_unchanged(before, after)
    assert len(after["details"]) == 2
    assert {row["status"] for row in after["details"]} == {"completed"}
    encoded = json.dumps(after["details"])
    assert "at_or_after_baseline" in encoded
    assert "before_baseline" in encoded
    assert json.loads(Path(report["report_path"]).read_text()) == report


def test_start_is_committed_before_the_first_detail_navigation(tmp_path):
    seed(tmp_path, ids=("103",))

    def inspect(candidate, stamp):
        details = saved(tmp_path)["details"]
        assert len(details) == 1
        assert details[0]["status"] == "started"
        assert details[0]["post_id"] == candidate["post_id"]
        return observed()(candidate, stamp)

    report = run(tmp_path, clock=FakeClock(), backend_factory=BrowserFactory(inspect))
    assert report["status"] == "candidate_test_completed"


def test_detail_interval_starts_after_the_previous_inspection_finishes(tmp_path):
    seed(tmp_path)
    clock = FakeClock()

    def slow_inspection(candidate, stamp):
        result = observed()(candidate, stamp)
        clock.current += timedelta(seconds=15)
        return result

    factory = BrowserFactory(slow_inspection, observed())
    report = run(tmp_path, clock=clock, backend_factory=factory)
    assert report["status"] == "candidate_test_completed"
    assert clock.waits == [60]
    assert factory.browser.calls[1][1] == NOW + timedelta(seconds=75)


@pytest.mark.parametrize(
    "changes",
    [
        {"published_at_raw": "13:00", "published_at": None},
        {"profile_evidence": {"header_count": 2}},
        {"published_at": NOW + timedelta(days=1)},
    ],
)
def test_unknown_header_time_remains_partial_without_falling_back_to_list_time(tmp_path, changes):
    before = seed(tmp_path)
    factory = BrowserFactory(observed(**changes))
    report = run(tmp_path, clock=FakeClock(), backend_factory=factory)
    assert report["status"] == "candidate_test_partial"
    assert len(factory.browser.calls) == 1
    assert report["details"][0]["time_status"] == "unknown"
    assert report["details"][0]["save_approved"] is False
    assert report["details"][0]["queue_eligible"] is False
    after = saved(tmp_path)
    assert after["details"][0]["status"] == "completed"
    assert_list_state_unchanged(before, after)


@pytest.mark.parametrize("status", ["network_error", "inspection_error"])
def test_failed_inspection_stops_without_second_request_or_private_error_text(tmp_path, status):
    before = seed(tmp_path)

    def failure(*_):
        return {
            "status": status,
            "http_status": None if status == "network_error" else 200,
            "retry_after": None,
            "navigation_attempts": 1,
            "error_type": "TimeoutError",
            "error_code": "Timeout",
            "diagnostics": {"private": "Invented private diagnostics"},
        }

    factory = BrowserFactory(failure)
    report = run(tmp_path, clock=FakeClock(), backend_factory=factory)
    assert report["status"] == "candidate_test_failed"
    assert len(factory.browser.calls) == 1
    assert report["browser_closed"] is True
    assert "Invented private diagnostics" not in json.dumps(
        candidate_runtime.share_candidate_report(report)
    )
    after = saved(tmp_path)
    assert after["details"][0]["status"] == "failed"
    assert_list_state_unchanged(before, after)


def test_unverified_body_stays_unapproved_even_after_confirmed_header_time(tmp_path):
    seed(tmp_path, ids=("103",))
    report = run(tmp_path, clock=FakeClock(), backend_factory=BrowserFactory(observed()))
    assert report["status"] == "candidate_test_completed"
    detail = report["details"][0]
    assert detail["time_status"] == "at_or_after_baseline"
    assert detail["layout_status"] == "unverified"
    assert detail["save_approved"] is False and detail["queue_eligible"] is False
    assert detail["attachment_matching_counts"] == {"matched": 1}


def test_completed_details_are_not_repeated_by_a_later_trial(tmp_path):
    seed(tmp_path)
    clock = FakeClock()
    first = run(tmp_path, clock=clock, backend_factory=BrowserFactory(observed(), observed()))
    assert first["status"] == "candidate_test_completed"
    clock.current += timedelta(seconds=300)
    report = run(tmp_path, clock=clock, backend_factory=no_browser)
    assert report["status"] == "candidate_no_pending"
    assert len(saved(tmp_path)["details"]) == 2


def test_bounded_batch_freezes_two_and_leaves_a_third_candidate_for_next_run(tmp_path):
    seed(tmp_path, ids=("103", "104", "105"))
    clock = FakeClock()
    first_factory = BrowserFactory(observed(), observed())
    first = run(tmp_path, clock=clock, backend_factory=first_factory)
    assert first["status"] == "candidate_test_completed"
    assert len(first_factory.browser.calls) == 2
    clock.current += timedelta(seconds=300)
    next_factory = BrowserFactory(observed())
    second = run(tmp_path, clock=clock, backend_factory=next_factory)
    assert second["status"] == "candidate_test_completed"
    assert len(next_factory.browser.calls) == 1
    first_ids = {candidate["post_id"] for candidate, _ in first_factory.browser.calls}
    assert next_factory.browser.calls[0][0]["post_id"] not in first_ids
    assert len(saved(tmp_path)["details"]) == 3


def test_existing_service_wait_prevents_browser_creation(tmp_path):
    before = seed(tmp_path)
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        queue.defer_service("dcinside", NOW + timedelta(seconds=180))
    report = run(tmp_path, clock=FakeClock(), backend_factory=no_browser)
    assert report["status"] == "candidate_waiting"
    assert saved(tmp_path)["details"] == []
    assert_list_state_unchanged(before, saved(tmp_path))


def test_missing_database_does_not_create_an_empty_watch_or_launch_browser(tmp_path):
    report = run(tmp_path, clock=FakeClock(), backend_factory=no_browser)
    assert report["status"] == "candidate_no_baseline"
    assert not (tmp_path / "watch.sqlite").exists()


def test_existing_database_without_baseline_requires_previous_discovery(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite"):
        pass
    report = run(tmp_path, clock=FakeClock(), backend_factory=no_browser)
    assert report["status"] == "candidate_no_baseline"
    assert saved(tmp_path)["state"]["generation"] == 0
    assert saved(tmp_path)["details"] == []


@pytest.mark.parametrize("status", [404, 410])
def test_deleted_candidate_is_terminal_without_blocking_the_next_detail(tmp_path, status):
    before = seed(tmp_path)
    factory = BrowserFactory(http_failure(status), observed())
    report = run(tmp_path, clock=FakeClock(), backend_factory=factory)
    assert report["status"] == "candidate_test_completed", report
    assert len(factory.browser.calls) == 2
    after = saved(tmp_path)
    assert {row["status"] for row in after["details"]} == {"completed"}
    assert_list_state_unchanged(before, after)


@pytest.mark.parametrize("status", [401, 403])
def test_access_block_stops_other_details_and_future_list_navigation(tmp_path, monkeypatch, status):
    before = seed(tmp_path)
    clock = FakeClock()
    factory = BrowserFactory(http_failure(status))
    report = run(tmp_path, clock=clock, backend_factory=factory)
    assert report["status"] == "candidate_test_failed"
    assert len(factory.browser.calls) == 1
    assert factory.browser.browser_closed
    after = saved(tmp_path)
    assert after["details"][0]["status"] == "failed"
    assert_list_state_unchanged(before, after)
    clock.current += timedelta(seconds=300)
    repeated = run(tmp_path, clock=clock, backend_factory=no_browser)
    assert repeated["status"] == "candidate_test_failed"
    monkeypatch.setattr("image_monitor.watch_runtime.require_windows", lambda: None)
    watch = run_watch_trial(tmp_path, clock=clock, backend_factory=no_browser)
    assert watch["status"] == "watch_test_failed"


@pytest.mark.parametrize("status", [429, 503])
@pytest.mark.parametrize("header", ["180", format_datetime(NOW + timedelta(seconds=180))])
def test_retry_after_is_shared_and_prevents_the_second_detail(tmp_path, status, header):
    seed(tmp_path)
    clock = FakeClock()
    factory = BrowserFactory(http_failure(status, header))
    report = run(tmp_path, clock=clock, backend_factory=factory)
    assert report["status"] in {"candidate_waiting", "candidate_test_failed"}
    assert len(factory.browser.calls) == 1
    assert clock.waits == []
    after = saved(tmp_path)
    assert len(after["details"]) == 1
    assert datetime.fromisoformat(after["service"][0]) >= NOW + timedelta(seconds=180)
    repeated = run(tmp_path, clock=clock, backend_factory=no_browser)
    assert repeated["status"] == "candidate_waiting"


@pytest.mark.parametrize("failure", [KeyboardInterrupt, RuntimeError])
def test_interrupted_request_keeps_audit_and_cooldown_without_automatic_repeat(tmp_path, failure):
    seed(tmp_path)
    clock = FakeClock()

    def interrupt(*_):
        clock.current += timedelta(seconds=15)
        raise failure("Invented private external error")

    factory = BrowserFactory(interrupt)
    report = run(tmp_path, clock=clock, backend_factory=factory)
    assert report["status"] == (
        "candidate_test_cancelled" if failure is KeyboardInterrupt else "candidate_test_failed"
    )
    assert report["browser_closed"] is True
    after = saved(tmp_path)
    assert len(after["details"]) == 1
    assert after["details"][0]["status"] == "started"
    assert datetime.fromisoformat(after["service"][0]) >= clock.now() + timedelta(seconds=60)
    immediate = run(tmp_path, clock=clock, backend_factory=no_browser)
    assert immediate["status"] == "candidate_waiting"
    interrupted_id = factory.browser.calls[0][0]["post_id"]
    clock.current += timedelta(seconds=300)
    next_factory = BrowserFactory(observed())
    next_report = run(tmp_path, clock=clock, backend_factory=next_factory)
    assert next_report["status"] == "candidate_test_completed"
    assert next_factory.browser.calls[0][0]["post_id"] != interrupted_id


def test_cancel_during_between_detail_wait_keeps_first_result_and_second_unstarted(tmp_path):
    seed(tmp_path)
    factory = BrowserFactory(observed())
    report = run(tmp_path, clock=FakeClock(cancel_on_wait=True), backend_factory=factory)
    assert report["status"] == "candidate_test_cancelled"
    assert report["browser_closed"] is True
    details = saved(tmp_path)["details"]
    assert len(details) == 1
    assert details[0]["status"] == "completed"
    with watch_run_lock(tmp_path / "watch.sqlite", DEFAULT_SCOPE):
        pass


def test_existing_scope_lease_prevents_detail_network_before_state_read(tmp_path):
    seed(tmp_path)
    with watch_run_lock(tmp_path / "watch.sqlite", DEFAULT_SCOPE):
        report = run(tmp_path, clock=FakeClock(), backend_factory=no_browser)
    assert report["status"] == "candidate_busy"
    assert saved(tmp_path)["details"] == []


def test_shared_report_contains_no_private_candidate_or_snapshot_content(tmp_path):
    seed(tmp_path)
    report = run(
        tmp_path,
        clock=FakeClock(),
        backend_factory=BrowserFactory(observed(), observed()),
    )
    assert report["status"] == "candidate_test_completed"
    report |= {
        "post_url": "https://private.example/post?secret=token",
        "title": "Invented private report title",
        "author": "Invented private report author",
        "snapshot": {"url": "https://private.example/image?secret=token"},
    }
    shared = candidate_runtime.share_candidate_report(report)
    encoded = json.dumps(shared, ensure_ascii=False)
    assert shared["status"] == "candidate_test_completed"
    for secret in (
        "Invented private",
        "private.example",
        "private-resource-hash",
        "private-token",
        "123.45",
        "https://",
        str(tmp_path),
        "report_path",
        "post_id",
        "first_scan_id",
    ):
        assert secret not in encoded
    assert "Invented private detail title" in json.dumps(saved(tmp_path)["details"])


def test_platform_guard_precedes_every_filesystem_change(tmp_path, monkeypatch):
    def unsupported():
        raise NativeUIError("Windows is required")

    monkeypatch.setattr(candidate_runtime, "require_windows", unsupported)
    root = tmp_path / "not-created"
    with pytest.raises(NativeUIError, match="Windows"):
        run(root, clock=FakeClock(), backend_factory=no_browser)
    assert not root.exists()


@pytest.mark.parametrize(
    "options",
    [
        {"max_candidates": True},
        {"max_candidates": 1.5},
        {"max_candidates": 3},
        {"interval_seconds": 60.0},
        {"interval_seconds": True},
        {"interval_seconds": 59},
    ],
)
def test_invalid_trial_limits_are_rejected_before_creating_reports_or_state(tmp_path, options):
    root = tmp_path / "not-created"
    with pytest.raises(NativeUIError):
        run(root, clock=FakeClock(), backend_factory=no_browser, **options)
    assert not root.exists()
