import hashlib
import json
import shutil
import tempfile
import uuid
from contextlib import nullcontext
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from image_monitor import post_worker as worker
from image_monitor.artifact_files import ArtifactError
from image_monitor.dcinside import parse_snapshot
from image_monitor.native_state import PendingSave
from image_monitor.native_ui import NativeFocusError, NativeUIError
from image_monitor.queue import QueueStore
from image_monitor.watch_runtime import DEFAULT_SCOPE
from image_monitor.watch_store import MONITOR_SCOPE


def observation(*, changed=False, count=1):
    identity = "fixture-b" if changed else "fixture-a"
    return parse_snapshot(
        {
            "body_count": 1,
            "header_count": 1,
            "header_field_counts": {".gall_writer": 1, ".gall_date": 1, ".title_subject": 1},
            "title": "Synthetic controller fixture",
            "nickname": "fixture author",
            "ip_display": "123.45",
            "published_at_raw": "2026.11.14 10:00:00",
            "attachments": [
                {
                    "filename": "original-fixture.png" if index == 0 else f"original-{index}.png",
                    "filename_complete": True,
                    "reference_url": (
                        "https://image.dcinside.com/download.php?no="
                        + identity
                        + (f"-{index}" if index else "")
                        + "&f_no=other"
                    ),
                }
                for index in range(count)
            ],
            "images": [
                {
                    "body_order": index + 1,
                    "display_url": (
                        "https://dcimg3.dcinside.co.kr/viewimage.php?id=fixture&no="
                        + identity
                        + (f"-{index}" if index else "")
                    ),
                    "complete": True,
                    "natural_width": 4,
                    "natural_height": 3,
                    "decode_ok": True,
                }
                for index in range(count)
            ],
        },
        expected_url=worker.DEFAULT_POST_URL,
        observed_at=datetime.now(UTC),
    )


@pytest.fixture
def pilot(monkeypatch):
    # The production Windows path budget also applies in these local controller tests.
    root = Path(tempfile.gettempdir()) / ("imw-" + uuid.uuid4().hex[:8])
    root.mkdir()
    values = SimpleNamespace(
        root=root,
        pending=root / "shared.json",
        snapshots=[],
        saves=[],
        runtimes=[],
        failure=None,
        approval_count=0,
        image_count=1,
        native_calls=0,
        approvals=[],
        armed=[],
        focus_ready=True,
        initial_foreground_waits=0,
        focus_resumes=0,
        focus_prompts=[],
        resume_save_counts=[],
        save_approval_counts=[],
        expected_url=worker.DEFAULT_POST_URL,
        navigation=[],
        navigation_failure=None,
        cancel_resume=False,
        window_titles=[],
        guarded_inspections=[],
    )
    monkeypatch.setattr(worker, "require_windows", lambda: None)
    monkeypatch.setattr(worker, "NativeSaveLock", nullcontext)
    monkeypatch.setattr(worker, "session_id", lambda: 1)
    monkeypatch.setattr(worker, "shared_state_path", lambda: values.pending)

    class Runtime:
        def __init__(self):
            self.browser = SimpleNamespace(version="fixture-browser")
            self.context = object()
            self.alive = False
            self.disconnects = 0
            values.runtimes.append(self)

        def launch(self, profile, kind):
            assert kind == "chrome"
            self.run_directory = profile.parent
            self.alive = True
            return SimpleNamespace(pid=42)

        def created_at(self, _process):
            return 1.0

        def attach(self, _profile, _process):
            def navigate(*_args, **_kwargs):
                values.navigation.append("goto")
                if values.navigation_failure is not None:
                    raise values.navigation_failure
                return SimpleNamespace(status=200)

            return SimpleNamespace(
                goto=navigate,
                url=values.expected_url,
                evaluate=lambda script, title: values.window_titles.append(title),
            )

        def inspect(self, _page, _url, **_options):
            guard = _options.get("before_interaction")
            values.guarded_inspections.append(guard is not None)
            if guard is not None:
                guard()
            return (
                values.snapshots.pop(0)
                if values.snapshots
                else observation(count=values.image_count)
            )

        def bind(self, _process, title):
            if values.window_titles:
                assert title == values.window_titles[-1]

            def assert_ready():
                if not values.focus_ready:
                    raise NativeFocusError("Fixture foreground is outside the bound window")

            def wait_for_initial_foreground():
                values.initial_foreground_waits += 1
                assert_ready()

            return SimpleNamespace(
                stage="fixture",
                expected_window_title=title,
                wait_for_initial_foreground=wait_for_initial_foreground,
                assert_target_ready=assert_ready,
                focus_snapshot=lambda: {"target_foreground": values.focus_ready},
                browser_suggested_filename=None,
                browser_suggested_extension=None,
                browser_suggested_file_type=None,
            )

        def close(self, _process):
            self.alive = False

        def disconnect(self):
            self.disconnects += 1

    monkeypatch.setattr(worker, "NativeRuntime", Runtime)
    monkeypatch.setattr(worker, "browser_still_running", lambda _pending: values.runtimes[-1].alive)

    def install(*_args, **kwargs):
        values.approvals.append(kwargs)
        # A return of focus cannot replace the fresh trusted approval step.
        if kwargs.get("resume"):
            values.focus_resumes += 1
            values.resume_save_counts.append(len(values.saves))
            values.focus_ready = True
        return f"nonce-{len(values.approvals)}", "owned title"

    monkeypatch.setattr(worker, "install_approval", install)

    def approve(*_args, **_kwargs):
        values.approval_count += 1
        if values.cancel_resume and values.approval_count > 1:
            raise KeyboardInterrupt

    monkeypatch.setattr(worker, "wait_for_approval", approve)

    class Completion:
        def __init__(self, *_args, allow_focus_prompt, **_kwargs):
            values.focus_prompts.append(allow_focus_prompt)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def wait_for_completion(self, path, url, _ui):
            if values.failure == "completion" or (
                values.failure == "second_completion" and len(values.saves) == 2
            ):
                raise NativeUIError("Fixture completion could not be proven")
            return {
                "state": "COMPLETE",
                "source_confirmed": True,
                "destination_confirmed": True,
                "source_url": url,
                "destination": str(path),
            }

    monkeypatch.setattr(worker, "BrowserCompletion", Completion)

    def native_save(_page, ui, *, post_url, image, staging_directory, before_native_input=None):
        assert post_url == values.expected_url
        assert image["expected_header"]["title"] == "Synthetic controller fixture"
        values.native_calls += 1
        ui.stage = "image_load"
        ui.browser_suggested_filename = None
        ui.browser_suggested_extension = None
        ui.browser_suggested_file_type = None
        if values.failure == "second_preinput_focus" and values.native_calls == 2:
            raise NativeFocusError("Fixture foreground is outside the bound window")
        ui.assert_target_ready()
        assert before_native_input is not None
        before_native_input()
        report = json.loads((values.runtimes[-1].run_directory / "report.json").read_text())
        with QueueStore(values.root / "session-1/queue.sqlite", read_only=True) as store:
            armed_job = store.get_job(report["active_attempt"]["job_id"])
        values.armed.append((report["active_attempt"].get("phase"), armed_job["status"]))
        values.saves.append(image["stable_key"])
        values.save_approval_counts.append(values.approval_count)
        path = staging_directory / "native-image.png"
        Image.new("RGB", (4, 3), "blue").save(path)
        ui.browser_suggested_filename = "browser-fixture.png"
        ui.browser_suggested_extension = ".png"
        ui.stage = "fixture_save_finished"
        return {
            "staging_path": str(path),
            "browser_suggested_filename": "browser-fixture.png",
            "source_url": image["display_url"],
            "natural_width": 4,
            "natural_height": 3,
        }

    monkeypatch.setattr(worker, "save_body_image", native_save)
    monkeypatch.setattr(
        worker, "exclusive_digest", lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    )
    yield values
    shutil.rmtree(root)


def test_controller_saves_frozen_observation_and_rerun_never_repeats_native_input(pilot):
    report = worker.run_post_save(pilot.root)
    assert report["status"] == "post_completed"
    assert pilot.focus_prompts == [False]
    assert report["browser_closed"] and not report["shared_pending_retained"]
    assert report["job_counts"] == {"observed": 1, "completed": 1, "unresolved": 0}
    assert not pilot.pending.exists()
    metadata = list((pilot.root / "session-1/images").rglob("metadata.json"))
    assert len(metadata) == 1
    record = json.loads(metadata[0].read_text())["images"][0]["artifact"]
    assert record["original_attachment_filename"] == "original-fixture.png"
    assert record["browser_suggested_filename"] == "browser-fixture.png"
    assert record["saved_filename"] == "001.png"
    assert (metadata[0].parent / "001.png").is_file()
    again = worker.run_post_save(pilot.root)
    assert again["status"] == "post_completed"
    assert len(pilot.saves) == 1 and pilot.approval_count == 1
    assert again["saved_files"] == []


def test_uncertain_writer_preserves_browser_pending_staging_and_blocks_another_root(pilot):
    pilot.failure = "completion"
    report = worker.run_post_save(pilot.root)
    assert report["status"] == "manual_review"
    assert report["last_stage"] == "download_completion"
    assert report["shared_pending_retained"] and not report["browser_closed"]
    assert pilot.runtimes[0].alive
    assert PendingSave(pilot.pending).read()["browser_pid"] == 42
    with QueueStore(pilot.root / "session-1/queue.sqlite") as store:
        job = store.list_jobs()[0]
        assert job["status"] == "paused_ui" and job["attempt_count"] == 0
        assert store.list_artifacts() == []
    assert len(list((pilot.root / "session-1/images/_staging").rglob("native-image.png"))) == 1
    with pytest.raises(NativeUIError, match="unresolved"):
        worker.run_post_save(pilot.root / "another-root")
    assert len(pilot.saves) == len(pilot.runtimes) == 1


def test_second_completion_failure_reports_first_finalized_file_without_losing_progress(pilot):
    pilot.image_count = 2
    pilot.failure = "second_completion"
    report = worker.run_post_save(pilot.root)
    assert report["status"] == "manual_review"
    assert report["job_counts"] == {"observed": 2, "completed": 1, "unresolved": 1}
    assert len(report["saved_files"]) == 1
    assert report["shared_pending_retained"] and not report["browser_closed"]
    with QueueStore(pilot.root / "session-1/queue.sqlite", read_only=True) as store:
        jobs = store.list_jobs()
        assert [job["status"] for job in jobs] == ["completed", "paused_ui"]
        first = store.get_artifact(jobs[0]["job_id"])
        assert first["phase"] == "finalized"
        assert store.get_artifact(jobs[1]["job_id"]) is None
        assert all(job["attempt_count"] == 0 for job in jobs)
    final_file = pilot.root / "session-1/images" / first["final_relative"]
    assert final_file.name == "001.png"
    assert hashlib.sha256(final_file.read_bytes()).hexdigest() == report["saved_files"][0]["sha256"]
    assert len(list((pilot.root / "session-1/images/_staging").rglob("native-image.png"))) == 1


def test_preinput_focus_race_releases_only_unstarted_claim_and_requires_fresh_resume(pilot):
    pilot.image_count = 2
    pilot.failure = "second_preinput_focus"
    report = worker.run_post_save(pilot.root)
    assert report["status"] == "post_completed"
    assert report["job_counts"] == {"observed": 2, "completed": 2, "unresolved": 0}
    assert pilot.native_calls == 3 and len(pilot.saves) == 2
    assert pilot.approval_count == 2 and pilot.focus_resumes == 1
    assert pilot.resume_save_counts == [1]
    assert pilot.save_approval_counts == [1, 2]
    assert pilot.armed == [("input_armed", "saving"), ("input_armed", "saving")]
    assert report["browser_closed"] and not pilot.pending.exists()
    with QueueStore(pilot.root / "session-1/queue.sqlite", read_only=True) as store:
        jobs = store.list_jobs()
        assert all(job["status"] == "completed" for job in jobs)
        assert store.history(jobs[0]["job_id"]) == []
        history = store.history(jobs[1]["job_id"])
        assert [(item["kind"], item["resulting_status"]) for item in history] == [
            ("ui_pause", "queued")
        ]
        assert all(job["attempt_count"] == 0 for job in jobs)
    # The empty attempt is preserved, but there is no uncertain file to overwrite/retry.
    attempts = list((pilot.root / "session-1/images/_staging").glob("*/*"))
    assert len(attempts) == 3 and all(not list(directory.iterdir()) for directory in attempts)


def test_focus_lost_between_images_waits_before_claim_even_if_focus_returns(pilot, monkeypatch):
    pilot.image_count = 2
    original = worker.finalize_saved_image

    def finalized(*args, **kwargs):
        result = original(*args, **kwargs)
        if len(pilot.saves) == 1:
            pilot.focus_ready = False
        return result

    monkeypatch.setattr(worker, "finalize_saved_image", finalized)
    report = worker.run_post_save(pilot.root)
    assert report["status"] == "post_completed"
    assert pilot.native_calls == len(pilot.saves) == 2
    assert pilot.approval_count == 2 and pilot.focus_resumes == 1
    assert pilot.resume_save_counts == [1]
    assert pilot.save_approval_counts == [1, 2]
    with QueueStore(pilot.root / "session-1/queue.sqlite", read_only=True) as store:
        assert all(store.history(job["job_id"]) == [] for job in store.list_jobs())


def test_cancelled_focus_resume_leaves_remaining_job_queued_and_first_artifact_intact(
    pilot, monkeypatch
):
    pilot.image_count = 2
    pilot.cancel_resume = True
    original = worker.finalize_saved_image

    def finalized(*args, **kwargs):
        result = original(*args, **kwargs)
        pilot.focus_ready = False
        return result

    monkeypatch.setattr(worker, "finalize_saved_image", finalized)
    report = worker.run_post_save(pilot.root)
    assert report["status"] == "manual_review" and report["error_type"] == "KeyboardInterrupt"
    assert report["job_counts"] == {"observed": 2, "completed": 1, "unresolved": 1}
    assert pilot.native_calls == len(pilot.saves) == 1
    assert report["browser_closed"] and not pilot.pending.exists()
    with QueueStore(pilot.root / "session-1/queue.sqlite", read_only=True) as store:
        jobs = store.list_jobs()
        assert [job["status"] for job in jobs] == ["completed", "queued"]
        assert store.get_artifact(jobs[0]["job_id"])["phase"] == "finalized"
        assert store.history(jobs[1]["job_id"]) == []


def test_local_failure_after_proven_completion_preserves_bytes_and_never_retries_ui(
    pilot, monkeypatch
):
    def fail_finalization(*_args, **_kwargs):
        raise ArtifactError("fixture_disk_unavailable")

    monkeypatch.setattr(worker, "finalize_saved_image", fail_finalization)
    report = worker.run_post_save(pilot.root)
    assert report["last_stage"] == "artifact_publication"
    assert report["browser_closed"] and not report["shared_pending_retained"]
    assert not pilot.pending.exists()
    with QueueStore(pilot.root / "session-1/queue.sqlite") as store:
        job = store.list_jobs()[0]
        assert job["status"] == "paused_local" and job["attempt_count"] == 0
        assert store.list_artifacts() == []
    assert len(list((pilot.root / "session-1/images/_staging").rglob("native-image.png"))) == 1
    again = worker.run_post_save(pilot.root)
    assert again["status"] == "manual_review"
    assert again["job_counts"]["unresolved"] == 1
    assert len(pilot.saves) == 1


def test_changed_post_after_user_start_is_rejected_before_native_input(pilot):
    pilot.snapshots = [observation(), observation(changed=True)]
    report = worker.run_post_save(pilot.root)
    assert report["last_stage"] == "post_recheck"
    assert report["status"] == "manual_review" and report["browser_closed"]
    assert pilot.saves == [] and not pilot.pending.exists()


def candidate_observation(*, count=1):
    return parse_snapshot(
        {
            "body_count": 1,
            "header_count": 1,
            "header_field_counts": {".gall_writer": 1, ".gall_date": 1, ".title_subject": 1},
            "title": "Synthetic controller fixture",
            "nickname": "fixture author",
            "ip_display": "123.45",
            "published_at_raw": "2026.11.14 10:00:00",
            "attachments": [
                {
                    "filename": "unrelated-declared-name.png",
                    "filename_complete": True,
                    "reference_url": "https://image.dcinside.com/download.php?no=one&f_no=1",
                }
            ],
            "images": [
                {
                    "body_order": index + 1,
                    "display_url": f"https://cdn.example/candidate-{index + 1}.png",
                    "complete": True,
                    "natural_width": 4,
                    "natural_height": 3,
                    "decode_ok": True,
                }
                for index in range(count)
            ],
            "diagnostics": {"counts": {".write_div": 1, ".gallview_head": 1}},
        },
        expected_url="https://gall.dcinside.com/board/view/?id=comic_new6&no=2",
        observed_at=datetime.now(UTC),
    )


def candidate_permit(snapshot, scope=DEFAULT_SCOPE):
    from image_monitor.candidate_policy import classify_candidate_detail
    from image_monitor.candidate_save_policy import make_candidate_save_permit

    observed = datetime.fromisoformat(snapshot["observed_at"])
    baseline = {"observed_at": "2026-11-14T00:59:00+00:00", "mode": "new"}
    scope = dict(
        zip(
            ("watch_name", "gallery_type", "gallery_id", "keyword", "search_type"),
            scope.key(),
            strict=True,
        )
    )
    candidate = scope | {
        "post_id": snapshot["post_id"],
        "post_url": snapshot["post_url"],
        "first_scan_id": "f" * 32,
        "first_seen_at": "2026-11-14T01:01:00+00:00",
    }
    detail = scope | {
        "post_id": snapshot["post_id"],
        "first_scan_id": candidate["first_scan_id"],
        "attempt_id": "a" * 32,
        "baseline_observed_at": baseline["observed_at"],
        "status": "completed",
        "started_at": (observed - timedelta(seconds=1)).isoformat(),
        "finished_at": (observed + timedelta(seconds=1)).isoformat(),
        "result": {
            "classification": classify_candidate_detail(candidate, baseline, snapshot),
            "private_observation": {
                "status": "observed",
                "http_status": 200,
                "url": snapshot["post_url"],
                "navigation_attempts": 1,
                "snapshot": snapshot,
            },
            "control": {
                "blocked": False,
                "http_status": 200,
                "finished_at": (observed + timedelta(seconds=1)).isoformat(),
                "next_eligible_at": (observed + timedelta(seconds=61)).isoformat(),
                "interval_seconds": 60,
            },
        },
    }
    return make_candidate_save_permit(candidate, baseline, detail)


def automatic_candidate(pilot, count=1):
    snapshot = candidate_observation(count=count)
    permit = candidate_permit(snapshot, MONITOR_SCOPE)
    pilot.expected_url = permit.post_url
    pilot.snapshots = [deepcopy(snapshot), deepcopy(snapshot)]
    return {
        "url": permit.post_url,
        "candidate_permit": permit,
        "navigation_observer": SimpleNamespace(
            before=lambda: pilot.navigation.append("before"),
            after=lambda response, error: pilot.navigation.append(
                ("after", response.status, error)
            ),
        ),
        "automatic_start": True,
    }


def test_automatic_save_binds_foreground_and_rechecks_permit_without_a_button(pilot):
    report = worker.run_post_save(pilot.root, **automatic_candidate(pilot, count=2))
    assert report["status"] == "post_completed" and report["browser_closed"]
    assert pilot.navigation == ["before", "goto", ("after", 200, None)]
    assert len(pilot.window_titles) == 1 and pilot.window_titles[0].startswith("Image Monitor ")
    assert pilot.guarded_inspections == [True, True]
    assert pilot.initial_foreground_waits == 1
    assert pilot.approvals == [] and pilot.approval_count == 0
    assert pilot.focus_prompts == [True]
    assert [item["saved_filename"] for item in report["saved_files"]] == ["001.png", "002.png"]
    assert pilot.armed == [("input_armed", "saving"), ("input_armed", "saving")]


@pytest.mark.parametrize("problem", ["bare_url", "trial_scope", "no_observer", "string_flag"])
def test_automatic_save_only_accepts_explicit_monitored_work(pilot, problem):
    options = automatic_candidate(pilot)
    if problem == "bare_url":
        options.update(url=worker.DEFAULT_POST_URL, candidate_permit=None, navigation_observer=None)
    elif problem == "trial_scope":
        options["candidate_permit"] = candidate_permit(pilot.snapshots[0])
    elif problem == "no_observer":
        options.pop("navigation_observer")
    else:
        options["automatic_start"] = "true"
    with pytest.raises(NativeUIError):
        worker.run_post_save(pilot.root, **options)
    assert pilot.runtimes == [] and not pilot.pending.exists()


def test_automatic_save_without_foreground_closes_before_first_inspection(pilot):
    pilot.focus_ready = False
    report = worker.run_post_save(pilot.root, **automatic_candidate(pilot))
    assert report["status"] == "manual_review" and report["error_type"] == "NativeFocusError"
    assert report["last_stage"] == "automatic_foreground_check"
    assert pilot.initial_foreground_waits == 1
    assert pilot.guarded_inspections == [] and pilot.approvals == [] and pilot.native_calls == 0
    assert report["browser_closed"] and not report["shared_pending_retained"]


def test_automatic_save_rejects_post_change_before_native_input(pilot):
    options = automatic_candidate(pilot)
    pilot.snapshots[-1]["nickname"] = "changed"
    report = worker.run_post_save(pilot.root, **options)
    assert report["last_stage"] == "post_recheck" and report["status"] == "manual_review"
    assert pilot.guarded_inspections == [True, True] and pilot.native_calls == 0
    assert report["browser_closed"] and not pilot.pending.exists()


@pytest.mark.parametrize("failure", ["second_preinput_focus", "second_completion"])
def test_automatic_partial_failure_preserves_first_file_and_stops(pilot, failure):
    pilot.failure = failure
    report = worker.run_post_save(pilot.root, **automatic_candidate(pilot, count=2))
    assert report["status"] == "manual_review"
    assert report["job_counts"] == {"observed": 2, "completed": 1, "unresolved": 1}
    assert pilot.approvals == [] and pilot.approval_count == 0 and pilot.native_calls == 2
    assert report["browser_closed"] == (failure == "second_preinput_focus")
    assert pilot.pending.exists() == (failure == "second_completion")
    with QueueStore(pilot.root / "session-1/queue.sqlite", read_only=True) as store:
        first, second = store.list_jobs()
        assert store.get_artifact(first["job_id"])["phase"] == "finalized"
        assert second["status"] == ("queued" if failure == "second_preinput_focus" else "paused_ui")


def test_candidate_controller_preserves_discovery_time_and_ambiguous_original_name(pilot):
    snapshot = candidate_observation()
    permit = candidate_permit(snapshot)
    pilot.expected_url = snapshot["post_url"]
    pilot.snapshots = [deepcopy(snapshot), deepcopy(snapshot)]
    observer = SimpleNamespace(
        before=lambda: pilot.navigation.append("before"),
        after=lambda response, error: pilot.navigation.append(("after", response.status, error)),
    )
    report = worker.run_post_save(
        pilot.root, url=permit.post_url, candidate_permit=permit, navigation_observer=observer
    )
    assert report["status"] == "post_completed", report
    assert pilot.navigation == ["before", "goto", ("after", 200, None)]
    assert report["mode"] == "reviewed_candidate_native_context_menu"
    assert report["job_counts"] == {"observed": 1, "completed": 1, "unresolved": 0}
    assert len(pilot.saves) == 1
    with QueueStore(pilot.root / "session-1/queue.sqlite", read_only=True) as store:
        post = store.get_post("normal", "comic_new6", "2")
        assert datetime.fromisoformat(post["first_seen_at"]) == permit.first_seen_at
    metadata = list((pilot.root / "session-1/images").rglob("metadata.json"))
    artifact = json.loads(metadata[0].read_text())["images"][0]["artifact"]
    assert artifact["original_attachment_filename"] is None
    assert artifact["original_filename_match_status"] == "ambiguous"
    assert artifact["browser_suggested_filename"] == "browser-fixture.png"
    assert artifact["saved_filename"] == "001.png"


@pytest.mark.parametrize("field", ["title", "nickname", "published_at_raw", "ip_display"])
def test_candidate_header_change_after_start_stops_before_native_input(pilot, field):
    snapshot = candidate_observation()
    permit = candidate_permit(snapshot)
    changed = deepcopy(snapshot)
    changed[field] = "Changed inspected header"
    pilot.expected_url = snapshot["post_url"]
    pilot.snapshots = [snapshot, changed]
    report = worker.run_post_save(pilot.root, url=permit.post_url, candidate_permit=permit)
    assert report["status"] == "manual_review"
    assert report["last_stage"] == "post_recheck"
    assert pilot.approval_count == 1
    assert pilot.saves == [] and not pilot.pending.exists()


def test_candidate_source_change_is_rejected_during_initial_inspection(pilot):
    snapshot = candidate_observation()
    permit = candidate_permit(snapshot)
    changed = candidate_observation()
    changed["images"][0]["display_url"] += "?changed=1"
    pilot.expected_url = snapshot["post_url"]
    pilot.snapshots = [changed]
    report = worker.run_post_save(pilot.root, url=permit.post_url, candidate_permit=permit)
    assert report["status"] == "manual_review"
    assert pilot.approval_count == 0 and pilot.saves == []
    with QueueStore(pilot.root / "session-1/queue.sqlite", read_only=True) as store:
        assert store.list_jobs() == []


def test_candidate_focus_resume_reauthorizes_the_frozen_header(pilot):
    snapshot = candidate_observation(count=2)
    permit = candidate_permit(snapshot)
    changed = deepcopy(snapshot)
    changed["title"] = "Edited while paused"
    pilot.expected_url = snapshot["post_url"]
    pilot.snapshots = [snapshot, deepcopy(snapshot), changed]
    pilot.failure = "second_preinput_focus"
    report = worker.run_post_save(pilot.root, url=permit.post_url, candidate_permit=permit)
    assert report["status"] == "manual_review"
    assert report["job_counts"] == {"observed": 2, "completed": 1, "unresolved": 1}
    assert len(pilot.saves) == 1 and pilot.approval_count == 2


def test_candidate_observer_wraps_navigation_and_runs_after_cancellation(pilot):
    snapshot = candidate_observation()
    permit = candidate_permit(snapshot)
    events = pilot.navigation

    class Observer:
        def before(self):
            events.append("before")

        def after(self, response, error):
            events.append(("after", response, type(error)))

    pilot.expected_url = snapshot["post_url"]
    pilot.navigation_failure = KeyboardInterrupt()
    report = worker.run_post_save(
        pilot.root, url=permit.post_url, candidate_permit=permit, navigation_observer=Observer()
    )
    assert events == ["before", "goto", ("after", None, KeyboardInterrupt)]
    assert report["error_type"] == "KeyboardInterrupt"
    assert report["browser_closed"] and not pilot.pending.exists()
    assert pilot.saves == []


@pytest.mark.parametrize("invalid", ["type", "identity", "resume", "legacy_observer"])
def test_candidate_scope_options_are_rejected_before_creating_files(pilot, invalid):
    snapshot = candidate_observation()
    permit = candidate_permit(snapshot)
    root = pilot.root / "not-created"
    options = {"url": permit.post_url, "candidate_permit": permit}
    if invalid == "type":
        options["candidate_permit"] = object()
    elif invalid == "identity":
        options["url"] = worker.DEFAULT_POST_URL
    elif invalid == "resume":
        options["resume_preinput"] = True
    else:
        options = {
            "navigation_observer": SimpleNamespace(before=lambda: None, after=lambda *_: None)
        }
    with pytest.raises(NativeUIError):
        worker.run_post_save(root, **options)
    assert not root.exists() and pilot.runtimes == []


def test_completed_file_needs_exact_source_and_destination_before_pillow(pilot, monkeypatch):
    path = pilot.root / "unknown.png"
    evidence = {
        "state": "COMPLETE",
        "destination_confirmed": True,
        "source_confirmed": True,
        "destination": str(path),
        "source_url": "https://fixture.invalid/wrong",
    }
    monkeypatch.setattr(worker, "verify_image", lambda *_args, **_kw: pytest.fail("Too early"))
    with pytest.raises(NativeUIError, match="completion proof"):
        worker._verify_completed_file(path, evidence, {"source_url": "expected"}, object())


def test_platform_guard_and_browser_scope_precede_any_filesystem_changes(tmp_path, monkeypatch):
    def unsupported():
        raise NativeUIError("Windows is required")

    monkeypatch.setattr(worker, "require_windows", unsupported)
    with pytest.raises(NativeUIError, match="Windows"):
        worker.run_post_save(tmp_path / "not-created")
    assert list(tmp_path.iterdir()) == []
    monkeypatch.setattr(worker, "require_windows", lambda: None)
    with pytest.raises(NativeUIError, match="Chrome only"):
        worker.run_post_save(tmp_path / "not-created", browser="edge")
    with pytest.raises(NativeUIError, match="reviewed example"):
        worker.run_post_save(
            tmp_path / "not-created", url=worker.DEFAULT_POST_URL.replace("7036949", "2")
        )
    assert list(tmp_path.iterdir()) == []


def test_runtime_disconnect_is_idempotent():
    runtime = worker.NativeRuntime()
    stopped = []
    runtime.driver = SimpleNamespace(stop=lambda: stopped.append(True))
    runtime.disconnect()
    runtime.disconnect()
    assert stopped == [True]


def test_shared_summary_omits_private_source_and_active_attempt_details():
    public = worker.share_worker_report(
        {
            "status": "manual_review",
            "native_stage": "save_dialog",
            "native_file_type": "PNG Image",
            "native_suggested_suffix": "",
            "active_attempt": {"source_url": "private-token", "staging_path": "private-path"},
            "snapshot": {"nickname": "private-name", "title": "private-title"},
        }
    )
    assert public == {
        "status": "manual_review",
        "native_stage": "save_dialog",
        "native_file_type": "PNG Image",
        "native_suggested_suffix": "",
    }
