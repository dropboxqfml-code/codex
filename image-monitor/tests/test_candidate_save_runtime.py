"""Exercise the native-pilot wrapper without sending native input or visiting a site."""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from image_monitor import candidate_save_runtime as runtime
from image_monitor.candidate_policy import classify_candidate_detail
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.dcinside import parse_snapshot
from image_monitor.native_ui import NativeUIError
from image_monitor.queue import QueueStore
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE, _eligibility
from image_monitor.watch_store import WatchStore

NOW = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
BASELINE = NOW - timedelta(minutes=10)


class FakeClock:
    def __init__(self):
        self.current = NOW

    def now(self):
        return self.current


@pytest.fixture(autouse=True)
def allow_controlled_windows_wrapper(monkeypatch):
    monkeypatch.setattr(runtime, "require_windows", lambda: None)


def snapshot(candidate, stamp, *, count):
    published = BASELINE + timedelta(minutes=5)
    return parse_snapshot(
        {
            "body_count": 1,
            "header_count": 1,
            "header_field_counts": {
                ".gall_writer": 1,
                ".gall_date": 1,
                ".title_subject": 1,
            },
            "title": "Invented private saved-post title",
            "nickname": "Invented private saved-post author",
            "ip_display": "123.45",
            "published_at_raw": published.astimezone(ZoneInfo("Asia/Seoul")).strftime(
                "%Y.%m.%d %H:%M:%S"
            ),
            "diagnostics": {"counts": {".write_div": 1, ".gallview_head": 1}},
            "attachments": [
                {
                    "key": "invented-attachment",
                    "filename": "Invented private original filename.png",
                    "filename_complete": True,
                    "reference_url": (
                        "https://image.dcinside.com/download.php?no=unrelated&f_no=1"
                    ),
                }
            ]
            if count
            else [],
            "images": [
                {
                    "body_order": index + 1,
                    "display_url": (
                        f"https://private.example/image-{index}.png?token=private-token"
                    ),
                    "complete": True,
                    "decode_ok": True,
                    "natural_width": 4 + index,
                    "natural_height": 3 + index,
                }
                for index in range(count)
            ],
        },
        expected_url=candidate["post_url"],
        observed_at=stamp,
    )


def evidence(watch_root):
    with QueueStore(watch_root / "watch.sqlite", read_only=True) as queue:
        store = WatchStore(queue)
        return {
            "state": store.get_state(DEFAULT_SCOPE),
            "candidates": store.list_candidates(DEFAULT_SCOPE),
            "scans": store.list_scans(DEFAULT_SCOPE),
            "gaps": store.list_gaps(DEFAULT_SCOPE),
            "details": CandidateDetailStore(queue).list_details(DEFAULT_SCOPE),
            "posts": queue.summary()["posts"],
            "jobs": queue.summary()["jobs"],
        }


def seed(watch_root, *, with_images=True):
    watch_root.mkdir()
    frozen = {"observed_at": BASELINE.isoformat(), "anchor_ids": ["100"], "mode": "new"}
    observations = {}
    with QueueStore(watch_root / "watch.sqlite") as queue:
        watch = WatchStore(queue)
        for generation, stamp, posts in (
            (0, BASELINE, ()),
            (1, NOW - timedelta(seconds=120), ("101", "102")),
        ):
            watch.persist_scan(
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
                        "title": "Invented private list title",
                        "shown_metadata": {"baseline_observed_at": frozen["observed_at"]},
                    }
                    for post_id in posts
                ],
                checkpoint=frozen | {"anchor_ids": [*posts, "100"]},
                complete=True,
                baseline=frozen if generation == 0 else None,
            )
        details = CandidateDetailStore(queue)
        for candidate in watch.list_candidates(DEFAULT_SCOPE):
            item = details.start(
                DEFAULT_SCOPE,
                candidate["post_id"],
                expected_first_scan_id=candidate["first_scan_id"],
                baseline_observed_at=BASELINE,
                started_at=NOW - timedelta(seconds=90),
            )
            observed = snapshot(
                candidate,
                NOW - timedelta(seconds=85),
                count=2 if with_images and candidate["post_id"] == "102" else 0,
            )
            observations[candidate["post_url"]] = observed
            details.finish(
                item["attempt_id"],
                finished_at=NOW - timedelta(seconds=80),
                result={
                    "classification": classify_candidate_detail(candidate, frozen, observed),
                    "private_observation": {
                        "status": "observed",
                        "url": candidate["post_url"],
                        "http_status": 200,
                        "navigation_attempts": 1,
                        "snapshot": observed,
                    },
                    "control": {
                        "blocked": False,
                        "finished_at": (NOW - timedelta(seconds=80)).isoformat(),
                        "next_eligible_at": (NOW - timedelta(seconds=20)).isoformat(),
                        "interval_seconds": 60,
                        "http_status": 200,
                    },
                },
            )
    return observations


def never_run(*_args, **_kwargs):
    pytest.fail("Candidate selection and eligibility must precede the native worker")


class FakeRunner:
    def __init__(self, clock, snapshots, *, status=200, retry_after=None, error=None):
        self.clock = clock
        self.snapshots = snapshots
        self.status = status
        self.retry_after = retry_after
        self.error = error
        self.calls = []
        self.worker_status = "post_completed"
        self.retain_pending = False

    def __call__(self, work_root, browser, url, *, candidate_permit, navigation_observer):
        self.calls.append((work_root, browser, url, candidate_permit))
        navigation_observer.before()
        # The persisted timer must already exist when navigation would begin.
        manifest = work_root.parent / "watch" / "candidate-save-selection.json"
        if manifest.exists():
            assert json.loads(manifest.read_text())["control"]["in_flight"] is True
        self.clock.current += timedelta(seconds=15)
        response = (
            SimpleNamespace(status=self.status, header_value=lambda _key: self.retry_after)
            if self.status is not None
            else None
        )
        navigation_observer.after(response, self.error)
        if self.error is not None:
            raise self.error
        if self.status >= 400:
            return {
                "status": "manual_review",
                "browser_closed": True,
                "shared_pending_retained": False,
                "error_type": "NativeUIError",
            }
        fresh = deepcopy(self.snapshots[url])
        fresh["observed_at"] = self.clock.now().isoformat()
        approved = candidate_permit.authorize_snapshot(fresh)
        assert len(approved["images"]) == 2
        assert all(image["original_attachment_filename"] is None for image in approved["images"])
        return {
            "status": self.worker_status,
            "browser": browser,
            "browser_version": "invented-fixture-browser",
            "browser_closed": True,
            "shared_pending_retained": self.retain_pending,
            "last_stage": "complete",
            "job_counts": {"observed": 2, "completed": 2, "unresolved": 0},
            "saved_files": [
                {
                    "saved_filename": f"00{number}.png",
                    "detected_format": "PNG",
                    "size_bytes": 99,
                    "width": 4,
                    "height": 3,
                    "frames": 1,
                    "sha256": "Invented private saved-image hash",
                    "original_attachment_filename": "Invented private original filename.png",
                    "final_path": str(work_root / "Invented private output"),
                }
                for number in (1, 2)
            ],
            "output_directory": str(work_root / "Invented private output"),
            "report_path": str(work_root / "Invented private worker-report.json"),
        }


def test_selects_image_candidate_and_delegates_to_separate_native_queue_without_watch_mutation(
    tmp_path,
):
    watch_root, work_root = tmp_path / "watch", tmp_path / "native"
    snapshots = seed(watch_root)
    before = evidence(watch_root)
    clock = FakeClock()
    runner = FakeRunner(clock, snapshots)

    report = runtime.run_candidate_save_trial(
        watch_root, work_root, clock=clock, save_runner=runner
    )

    assert report["status"] == "candidate_save_completed", report
    assert report["browser_closed"] is True
    assert report["job_counts"] == {"observed": 2, "completed": 2, "unresolved": 0}
    assert len(runner.calls) == 1
    assert runner.calls[0][:3] == (
        work_root,
        "chrome",
        "https://gall.dcinside.com/board/view/?id=comic_new6&no=102",
    )
    assert evidence(watch_root) == before
    assert (watch_root / "candidate-save-selection.json").is_file()
    with QueueStore(watch_root / "watch.sqlite", read_only=True) as queue:
        due = queue.connection.execute(
            "SELECT not_before FROM service_limits WHERE scope='dcinside'"
        ).fetchone()[0]
    assert datetime.fromisoformat(due) >= clock.now() + timedelta(seconds=60)
    assert json.loads(Path(report["report_path"]).read_text()) == report


def test_repeat_uses_the_same_pinned_candidate_and_respects_intervening_wait(tmp_path):
    watch_root, work_root = tmp_path / "watch", tmp_path / "native"
    snapshots = seed(watch_root)
    clock = FakeClock()
    first = FakeRunner(clock, snapshots)
    assert (
        runtime.run_candidate_save_trial(watch_root, work_root, clock=clock, save_runner=first)[
            "status"
        ]
        == "candidate_save_completed"
    )
    manifest_before = json.loads((watch_root / "candidate-save-selection.json").read_text())
    waiting = runtime.run_candidate_save_trial(
        watch_root, work_root, clock=clock, save_runner=never_run
    )
    assert waiting["status"] == "candidate_save_waiting"
    clock.current += timedelta(seconds=300)
    repeated = FakeRunner(clock, snapshots)
    assert (
        runtime.run_candidate_save_trial(watch_root, work_root, clock=clock, save_runner=repeated)[
            "status"
        ]
        == "candidate_save_completed"
    )
    assert repeated.calls[0][2] == first.calls[0][2]
    manifest_after = json.loads((watch_root / "candidate-save-selection.json").read_text())
    assert {k: v for k, v in manifest_after.items() if k != "control"} == {
        k: v for k, v in manifest_before.items() if k != "control"
    }


def test_missing_discovery_database_does_not_create_empty_watch_or_run_worker(tmp_path):
    watch_root, work_root = tmp_path / "watch", tmp_path / "native"
    report = runtime.run_candidate_save_trial(watch_root, work_root, save_runner=never_run)
    assert report["status"] == "candidate_save_no_candidate"
    assert not (watch_root / "watch.sqlite").exists()


def test_completed_zero_image_details_do_not_start_native_worker(tmp_path):
    watch_root, work_root = tmp_path / "watch", tmp_path / "native"
    seed(watch_root, with_images=False)
    report = runtime.run_candidate_save_trial(
        watch_root, work_root, clock=FakeClock(), save_runner=never_run
    )
    assert report["status"] == "candidate_save_no_candidate"
    assert not (watch_root / "candidate-save-selection.json").exists()


def test_persisted_service_wait_precedes_selection_and_native_worker(tmp_path):
    watch_root, work_root = tmp_path / "watch", tmp_path / "native"
    seed(watch_root)
    with QueueStore(watch_root / "watch.sqlite") as queue:
        queue.defer_service("dcinside", NOW + timedelta(seconds=180))
    report = runtime.run_candidate_save_trial(
        watch_root, work_root, clock=FakeClock(), save_runner=never_run
    )
    assert report["status"] == "candidate_save_waiting"
    assert not (watch_root / "candidate-save-selection.json").exists()


def test_scope_lease_prevents_selection_and_native_worker(tmp_path):
    watch_root, work_root = tmp_path / "watch", tmp_path / "native"
    seed(watch_root)
    with watch_run_lock(watch_root / "watch.sqlite", DEFAULT_SCOPE):
        report = runtime.run_candidate_save_trial(
            watch_root, work_root, clock=FakeClock(), save_runner=never_run
        )
    assert report["status"] == "candidate_save_busy"


@pytest.mark.parametrize("status", [401, 403])
def test_access_denial_blocks_future_list_and_save_navigation(tmp_path, status):
    watch_root, work_root = tmp_path / "watch", tmp_path / "native"
    snapshots = seed(watch_root)
    clock = FakeClock()
    report = runtime.run_candidate_save_trial(
        watch_root,
        work_root,
        clock=clock,
        save_runner=FakeRunner(clock, snapshots, status=status),
    )
    assert report["status"] == "candidate_save_failed"
    clock.current += timedelta(seconds=300)
    with QueueStore(watch_root / "watch.sqlite") as queue:
        assert _eligibility(queue, WatchStore(queue).get_state(DEFAULT_SCOPE), clock.now())[0] == (
            "blocked"
        )
    repeated = runtime.run_candidate_save_trial(
        watch_root, work_root, clock=clock, save_runner=never_run
    )
    assert repeated["status"] == "candidate_save_failed"


@pytest.mark.parametrize("status", [404, 410])
def test_deleted_selected_post_requires_review_without_gallery_block_or_fallback(tmp_path, status):
    watch_root, work_root = tmp_path / "watch", tmp_path / "native"
    snapshots = seed(watch_root)
    clock = FakeClock()
    runner = FakeRunner(clock, snapshots, status=status)
    report = runtime.run_candidate_save_trial(
        watch_root, work_root, clock=clock, save_runner=runner
    )
    assert report["status"] == "candidate_save_manual_review"
    assert len(runner.calls) == 1
    assert report["reason"] == "selected_candidate_unavailable"
    clock.current += timedelta(seconds=300)
    with QueueStore(watch_root / "watch.sqlite") as queue:
        assert _eligibility(queue, WatchStore(queue).get_state(DEFAULT_SCOPE), clock.now())[0] == (
            "ready"
        )
    assert (
        json.loads((watch_root / "candidate-save-selection.json").read_text())["post_id"] == "102"
    )


@pytest.mark.parametrize("status", [429, 503])
@pytest.mark.parametrize("header", ["180", format_datetime(NOW + timedelta(seconds=300))])
def test_server_wait_is_preserved_after_native_document_navigation(tmp_path, status, header):
    watch_root, work_root = tmp_path / "watch", tmp_path / "native"
    snapshots = seed(watch_root)
    clock = FakeClock()
    report = runtime.run_candidate_save_trial(
        watch_root,
        work_root,
        clock=clock,
        save_runner=FakeRunner(clock, snapshots, status=status, retry_after=header),
    )
    assert report["status"] == "candidate_save_waiting"
    with QueueStore(watch_root / "watch.sqlite") as queue:
        due = queue.connection.execute(
            "SELECT not_before FROM service_limits WHERE scope='dcinside'"
        ).fetchone()[0]
    minimum = (
        clock.now() + timedelta(seconds=180) if header == "180" else NOW + timedelta(seconds=300)
    )
    assert datetime.fromisoformat(due) >= minimum
    repeated = runtime.run_candidate_save_trial(
        watch_root, work_root, clock=clock, save_runner=never_run
    )
    assert repeated["status"] == "candidate_save_waiting"


@pytest.mark.parametrize("failure", [KeyboardInterrupt, RuntimeError])
def test_interrupted_navigation_keeps_frozen_selection_and_finish_based_wait(tmp_path, failure):
    watch_root, work_root = tmp_path / "watch", tmp_path / "native"
    snapshots = seed(watch_root)
    clock = FakeClock()
    report = runtime.run_candidate_save_trial(
        watch_root,
        work_root,
        clock=clock,
        save_runner=FakeRunner(
            clock, snapshots, status=None, error=failure("Invented private error")
        ),
    )
    expected = (
        "candidate_save_cancelled" if failure is KeyboardInterrupt else "candidate_save_failed"
    )
    assert report["status"] == expected
    assert (watch_root / "candidate-save-selection.json").is_file()
    with QueueStore(watch_root / "watch.sqlite") as queue:
        due = queue.connection.execute(
            "SELECT not_before FROM service_limits WHERE scope='dcinside'"
        ).fetchone()[0]
    assert datetime.fromisoformat(due) >= clock.now() + timedelta(seconds=60)
    assert "Invented private error" not in json.dumps(runtime.share_candidate_save_report(report))


def test_worker_manual_review_and_pending_writer_are_not_automatically_cleared(tmp_path):
    watch_root, work_root = tmp_path / "watch", tmp_path / "native"
    snapshots = seed(watch_root)
    clock = FakeClock()
    runner = FakeRunner(clock, snapshots)
    runner.worker_status = "manual_review"
    runner.retain_pending = True
    report = runtime.run_candidate_save_trial(
        watch_root, work_root, clock=clock, save_runner=runner
    )
    assert report["status"] == "candidate_save_manual_review"
    assert report["shared_pending_retained"] is True
    assert len(runner.calls) == 1


def test_early_native_worker_guard_failure_keeps_browser_and_pending_state_unknown(tmp_path):
    watch_root, work_root = tmp_path / "watch", tmp_path / "native"
    seed(watch_root)
    marker = tmp_path / "shared-pending.json"
    marker_bytes = b'{"synthetic_owner":"another unresolved native save"}\n'
    marker.write_bytes(marker_bytes)
    calls = []

    def blocked_worker(*_args, **_kwargs):
        calls.append("guard")
        assert marker.read_bytes() == marker_bytes
        raise NativeUIError("Synthetic unresolved native state")

    report = runtime.run_candidate_save_trial(
        watch_root, work_root, clock=FakeClock(), save_runner=blocked_worker
    )

    assert report["status"] == "candidate_save_failed"
    assert report["error_type"] == "NativeUIError"
    assert report["browser_closed"] is None
    assert report["shared_pending_retained"] is None
    assert marker.read_bytes() == marker_bytes
    assert calls == ["guard"]
    with QueueStore(watch_root / "watch.sqlite", read_only=True) as queue:
        assert queue.connection.execute("SELECT COUNT(*) FROM service_limits").fetchone()[0] == 0
    selection = json.loads((watch_root / "candidate-save-selection.json").read_text())
    assert selection["control"].get("in_flight") is not True


def test_response_header_failure_still_preserves_finish_based_minimum_wait(tmp_path):
    watch_root, work_root = tmp_path / "watch", tmp_path / "native"
    seed(watch_root)
    clock = FakeClock()

    def fail_header(_key):
        raise RuntimeError("Invented private closed-browser header error")

    def runner(*_args, navigation_observer, **_kwargs):
        navigation_observer.before()
        clock.current += timedelta(seconds=15)
        navigation_observer.after(SimpleNamespace(status=429, header_value=fail_header), None)
        return {"status": "manual_review", "browser_closed": True, "error_type": "NativeUIError"}

    report = runtime.run_candidate_save_trial(
        watch_root, work_root, clock=clock, save_runner=runner
    )
    assert report["status"] == "candidate_save_waiting"
    with QueueStore(watch_root / "watch.sqlite") as queue:
        due = queue.connection.execute(
            "SELECT not_before FROM service_limits WHERE scope='dcinside'"
        ).fetchone()[0]
    assert datetime.fromisoformat(due) >= clock.now() + timedelta(seconds=60)


def test_shared_report_omits_frozen_source_details_and_private_worker_metadata(tmp_path):
    watch_root, work_root = tmp_path / "watch", tmp_path / "native"
    snapshots = seed(watch_root)
    clock = FakeClock()
    report = runtime.run_candidate_save_trial(
        watch_root, work_root, clock=clock, save_runner=FakeRunner(clock, snapshots)
    )
    assert report["status"] == "candidate_save_completed", report
    public = runtime.share_candidate_save_report(report)
    assert public["saved_files"][0]["saved_filename"] == "001.png"
    assert public["job_counts"]["completed"] == 2
    encoded = json.dumps(public, ensure_ascii=False)
    for secret in (
        "Invented private",
        "private.example",
        "private-token",
        "https://",
        "sha256",
        "original_attachment_filename",
        str(tmp_path),
        "report_path",
        "output_directory",
    ):
        assert secret not in encoded


@pytest.mark.parametrize("relation", ["same", "watch_inside_output", "output_inside_watch"])
def test_overlapping_roots_are_rejected_before_creating_any_files(tmp_path, relation):
    watch_root = tmp_path / "watch"
    work_root = {
        "same": watch_root,
        "watch_inside_output": tmp_path,
        "output_inside_watch": watch_root / "native",
    }[relation]
    with pytest.raises(NativeUIError, match="separate"):
        runtime.run_candidate_save_trial(watch_root, work_root, save_runner=never_run)
    assert list(tmp_path.iterdir()) == []


def test_platform_guard_precedes_every_filesystem_change(tmp_path, monkeypatch):
    def unsupported():
        raise NativeUIError("Windows required")

    monkeypatch.setattr(runtime, "require_windows", unsupported)
    with pytest.raises(NativeUIError, match="Windows"):
        runtime.run_candidate_save_trial(tmp_path / "watch", tmp_path / "native")
    assert list(tmp_path.iterdir()) == []
