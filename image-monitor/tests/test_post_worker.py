import hashlib
import json
import shutil
import tempfile
import uuid
from contextlib import nullcontext
from datetime import UTC, datetime
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
        focus_resumes=0,
        resume_save_counts=[],
        save_approval_counts=[],
        cancel_resume=False,
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
            return SimpleNamespace(goto=lambda *_args, **_kwargs: SimpleNamespace(status=200))

        def inspect(self, _page, _url, **_options):
            return (
                values.snapshots.pop(0)
                if values.snapshots
                else observation(count=values.image_count)
            )

        def bind(self, _process, title):
            def assert_ready():
                if not values.focus_ready:
                    raise NativeFocusError("Fixture foreground is outside the bound window")

            return SimpleNamespace(
                stage="fixture",
                expected_window_title=title,
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
        def __init__(self, *_args, **_kwargs):
            pass

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
        assert post_url == worker.DEFAULT_POST_URL
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
