"""Reopen an alpha.6 save in a fresh interpreter through the read-only CLI."""

import hashlib
import json
import subprocess
import sys
from io import BytesIO
from types import SimpleNamespace

import test_recent_candidate_save as alpha6
from PIL import Image
from test_monitor_batch_runtime import finalize

from image_monitor import PUBLIC_VERSION
from image_monitor.monitor_batch_runtime import share_batch_report

recent_save = alpha6.recent

# Run the installed command's actual module in a fresh interpreter. Windows uses its
# production mutex and exclusive file read; Linux substitutes those two OS facilities.
CHECK_DRIVER = """
import runpy
import sys
from pathlib import Path

def offline(event, args):
    if event in {"builtins.input", "socket.connect", "socket.getaddrinfo", "subprocess.Popen",
                 "os.startfile", "os.system", "webbrowser.open"}:
        sys.exit(f"Unexpected operation in local verification: {event}")
    if event == "sqlite3.connect" and args[0] != ":memory:" and "mode=ro" not in str(args[0]):
        sys.exit("Local verification opened a writable database")

sys.addaudithook(offline)
from image_monitor import saved_catalog
watch_root = Path(sys.argv[sys.argv.index("--watch-root") + 1])
saved_catalog.shared_state_path = lambda: watch_root.parent / "pending.json"
if sys.platform != "win32":
    import hashlib
    from contextlib import nullcontext
    from image_monitor import candidate_finish
    saved_catalog.NativeSaveLock = nullcontext
    candidate_finish.exclusive_digest = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

runpy.run_module("image_monitor", run_name="__main__", alter_sys=True)
"""


def disk_evidence(root):
    paths = list(root.rglob("*"))
    # Include the names of coordination files so a read cannot silently create one.
    contents = {
        path.relative_to(root): hashlib.sha256(path.read_bytes()).digest()
        for path in paths
        if path.is_file() and not path.name.endswith(("-wal", "-shm", ".lock"))
    }
    return {path.relative_to(root) for path in paths}, contents


def test_fresh_cli_checks_a_completed_save_and_detects_changed_bytes(recent_save):
    watch, legacy, work = recent_save.roots
    handoff = recent_save.handoffs["103"]

    def save_file(root, browser, url, *, candidate_permit, navigation_observer):
        navigation_observer.before()
        navigation_observer.after(SimpleNamespace(status=200), None)
        finalize(
            root,
            candidate_permit,
            candidate_permit.reference_snapshot,
            recent_save.clock.now(),
            native_filename="native-image.jpg",
        )
        return {
            "status": "post_completed",
            "browser_closed": True,
            "shared_pending_retained": False,
            "job_counts": {"observed": 1, "completed": 1, "unresolved": 0},
        }

    saved = alpha6.save(recent_save, handoff, save_file)
    assert saved["status"] == "monitor_batch_completed", saved
    (metadata,) = share_batch_report(saved)["saved_files"]
    assert metadata["detected_format"] == "JPEG" and metadata["saved_filename"] == "001.jpg"
    (image,) = work.glob("tasks/*/session-1/images/**/001.jpg")
    command = [
        sys.executable,
        "-B",
        "-c",
        CHECK_DRIVER,
        "watch-images-check",
        "--watch-root",
        str(watch),
        "--legacy-root",
        str(legacy),
        "--work-root",
        str(work),
    ]
    for changed in (False, True):
        if changed:
            # Keep the path, dimensions, format and byte length valid. Only the digest differs.
            buffer = BytesIO()
            Image.new("RGB", (metadata["width"], metadata["height"])).save(buffer, format="JPEG")
            data = buffer.getvalue()
            size = metadata["file_size"]
            assert len(data) <= size
            replacement = data.ljust(size, b"\0")
            assert replacement != image.read_bytes()
            image.write_bytes(replacement)
        before = disk_evidence(watch.parent)
        finished = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert finished.returncode == (2 if changed else 0), (finished.stdout, finished.stderr)
        report = json.loads(finished.stdout)
        assert report["program_version"] == PUBLIC_VERSION
        assert report["status"] == ("watch_images_review" if changed else "watch_images_verified")
        assert report["saved_file_count"] == (0 if changed else 1)
        assert report["saved_files"] == ([] if changed else [metadata])
        assert all(
            private not in finished.stdout
            for private in (watch.parent.name, "https://", "Invented", *handoff.values())
        )
        assert disk_evidence(watch.parent) == before
