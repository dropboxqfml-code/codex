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
from image_monitor.native_ui import NativeUIError
from image_monitor.queue import QueueStore


def observation(*, changed=False):
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
                    "filename": "original-fixture.png",
                    "filename_complete": True,
                    "reference_url": (
                        "https://image.dcinside.com/download.php?no=" + identity + "&f_no=other"
                    ),
                }
            ],
            "images": [
                {
                    "body_order": 1,
                    "display_url": (
                        "https://dcimg3.dcinside.co.kr/viewimage.php?id=fixture&no=" + identity
                    ),
                    "complete": True,
                    "natural_width": 4,
                    "natural_height": 3,
                    "decode_ok": True,
                }
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

        def launch(self, _profile, kind):
            assert kind == "chrome"
            self.alive = True
            return SimpleNamespace(pid=42)

        def created_at(self, _process):
            return 1.0

        def attach(self, _profile, _process):
            return SimpleNamespace(goto=lambda *_args, **_kwargs: SimpleNamespace(status=200))

        def inspect(self, _page, _url):
            return values.snapshots.pop(0) if values.snapshots else observation()

        def bind(self, _process, _title):
            return SimpleNamespace(
                stage="fixture", assert_target_ready=lambda: None, focus_snapshot=lambda: {}
            )

        def close(self, _process):
            self.alive = False

        def disconnect(self):
            self.disconnects += 1

    monkeypatch.setattr(worker, "NativeRuntime", Runtime)
    monkeypatch.setattr(worker, "browser_still_running", lambda _pending: values.runtimes[-1].alive)
    monkeypatch.setattr(worker, "install_approval", lambda *_args: ("nonce", "owned title"))

    def approve(*_args):
        values.approval_count += 1

    monkeypatch.setattr(worker, "wait_for_approval", approve)

    class Completion:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def wait_for_completion(self, path, url, _ui):
            if values.failure == "completion":
                raise NativeUIError("Fixture completion could not be proven")
            return {
                "state": "COMPLETE",
                "source_confirmed": True,
                "destination_confirmed": True,
                "source_url": url,
                "destination": str(path),
            }

    monkeypatch.setattr(worker, "BrowserCompletion", Completion)

    def native_save(_page, _ui, *, post_url, image, staging_directory):
        assert post_url == worker.DEFAULT_POST_URL
        assert image["expected_header"]["title"] == "Synthetic controller fixture"
        values.saves.append(image["stable_key"])
        path = staging_directory / "native-image.png"
        Image.new("RGB", (4, 3), "blue").save(path)
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
