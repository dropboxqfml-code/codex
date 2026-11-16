import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from image_monitor.queue import QueueError
from image_monitor.watch_lock import WatchRunBusy, _lock_path, watch_run_lock
from image_monitor.watch_store import WatchScope

SCOPE = WatchScope("watch", "normal", "gallery", "ai", "search_subject_memo")
CHILD = """
import os
import sys
from pathlib import Path
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_store import WatchScope

scope = WatchScope("watch", "normal", "gallery", "ai", "search_subject_memo")
try:
    with watch_run_lock(Path(sys.argv[1]), scope, purpose=sys.argv[3] or None):
        print("acquired", flush=True)
        if sys.argv[2] == "crash":
            os._exit(0)
except WatchRunBusy:
    print("busy", flush=True)
"""


def child(database, mode="normal", *, purpose=None):
    return subprocess.run(
        [sys.executable, "-c", CHILD, str(database), mode, purpose or ""],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout.strip()


def test_same_scope_cannot_start_network_while_lease_is_owned(tmp_path):
    database = tmp_path / "watch.sqlite"
    calls = []
    with watch_run_lock(database, SCOPE):
        with pytest.raises(WatchRunBusy, match="owns"):
            with watch_run_lock(database, SCOPE):
                calls.append("network")
        assert child(database) == "busy"
    assert calls == []
    assert child(database) == "acquired"
    assert not database.exists()


def test_every_scope_dimension_and_database_get_an_independent_lease(tmp_path):
    database = tmp_path / "watch.sqlite"
    with watch_run_lock(database, SCOPE):
        for name, value in (
            ("watch_name", "other"),
            ("gallery_type", "minor"),
            ("gallery_id", "other"),
            ("keyword", "other"),
            ("search_type", "search_subject"),
        ):
            with watch_run_lock(database, replace(SCOPE, **{name: value})):
                pass
        with watch_run_lock(tmp_path / "other.sqlite", SCOPE):
            pass


def test_relative_and_resolved_database_paths_share_one_lease(tmp_path, monkeypatch):
    database = tmp_path / "watch.sqlite"
    monkeypatch.chdir(tmp_path)
    with watch_run_lock(database, SCOPE):
        with pytest.raises(WatchRunBusy):
            with watch_run_lock(Path("watch.sqlite"), SCOPE):
                pass


@pytest.mark.skipif(os.name != "nt", reason="Windows paths are case insensitive")
def test_windows_database_path_case_shares_one_lease(tmp_path):
    database = tmp_path / "watch.sqlite"
    with watch_run_lock(database, SCOPE):
        with pytest.raises(WatchRunBusy):
            with watch_run_lock(Path(str(database).upper()), SCOPE):
                pass


def test_database_symlink_alias_shares_one_lease(tmp_path):
    database = tmp_path / "watch.sqlite"
    database.touch()
    alias = tmp_path / "alias.sqlite"
    try:
        alias.symlink_to(database)
    except (NotImplementedError, OSError):
        pytest.skip("Creating symlinks is unavailable")
    with watch_run_lock(database, SCOPE):
        with pytest.raises(WatchRunBusy):
            with watch_run_lock(alias, SCOPE):
                pass


def test_abrupt_process_exit_releases_lease_without_deleting_sidecar(tmp_path):
    database = tmp_path / "watch.sqlite"
    assert child(database, "crash") == "acquired"
    sidecar = _lock_path(database, SCOPE)
    original = sidecar.stat()
    assert sidecar.read_bytes() == b""
    with watch_run_lock(database, SCOPE):
        assert os.path.samestat(original, sidecar.stat())
    assert sidecar.exists()


def test_body_failure_releases_lease_and_existing_sidecar_contents_are_untouched(tmp_path):
    database = tmp_path / "watch.sqlite"
    sidecar = _lock_path(database, SCOPE)
    content = b"Existing contents are not a lease or permission to overwrite."
    sidecar.write_bytes(content)
    original = sidecar.stat()
    with pytest.raises(RuntimeError, match="scan failed"):
        with watch_run_lock(database, SCOPE):
            raise RuntimeError("scan failed")
    assert sidecar.read_bytes() == content
    with watch_run_lock(database, SCOPE):
        assert os.path.samestat(original, sidecar.stat())
    assert sidecar.read_bytes() == content


def test_preexisting_sidecar_symlink_is_refused_without_touching_target(tmp_path):
    database = tmp_path / "watch.sqlite"
    target = tmp_path / "preserve.txt"
    target.write_bytes(b"Owner contents")
    sidecar = _lock_path(database, SCOPE)
    try:
        sidecar.symlink_to(target)
    except (NotImplementedError, OSError):
        pytest.skip("Creating symlinks is unavailable")
    with pytest.raises(QueueError, match="regular file"):
        with watch_run_lock(database, SCOPE):
            pytest.fail("A symlink sidecar must not be acquired")
    assert sidecar.is_symlink()
    assert target.read_bytes() == b"Owner contents"


def test_preexisting_sidecar_directory_is_refused(tmp_path):
    database = tmp_path / "watch.sqlite"
    sidecar = _lock_path(database, SCOPE)
    sidecar.mkdir()
    with pytest.raises(QueueError, match="regular file"):
        with watch_run_lock(database, SCOPE):
            pass
    assert sidecar.is_dir()


def test_invalid_scope_does_not_create_any_sidecar(tmp_path):
    with pytest.raises(QueueError, match="scope"):
        with watch_run_lock(tmp_path / "watch.sqlite", object()):
            pass
    assert list(tmp_path.iterdir()) == []


def test_default_lock_path_retains_the_exact_published_lease_identity(tmp_path):
    database = tmp_path / "watch.sqlite"
    identity = json.dumps(
        [os.path.normcase(str(database.resolve())), SCOPE.key()],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode()
    expected = tmp_path / f".image-monitor-watch-{hashlib.sha256(identity).hexdigest()}.lock"
    assert _lock_path(database, SCOPE) == expected
    assert _lock_path(database, SCOPE, purpose=None) == expected


def test_monitor_lease_is_independent_but_excludes_another_monitor_process(tmp_path):
    database = tmp_path / "watch.sqlite"
    with watch_run_lock(database, SCOPE, purpose="monitor"):
        assert child(database, purpose="monitor") == "busy"
        assert child(database) == "acquired"
        with watch_run_lock(database, SCOPE):
            pass
        with pytest.raises(WatchRunBusy):
            with watch_run_lock(database, SCOPE, purpose="monitor"):
                pytest.fail("A second monitor must not run")
    assert child(database, purpose="monitor") == "acquired"
    assert not database.exists()


@pytest.mark.parametrize("purpose", [True, 0, "scan", "Monitor", b"monitor", ""])
def test_invalid_lease_purpose_is_rejected_before_filesystem_work(tmp_path, purpose):
    with pytest.raises(QueueError, match="purpose"):
        with watch_run_lock(tmp_path / "missing" / "watch.sqlite", SCOPE, purpose=purpose):
            pass
    assert list(tmp_path.iterdir()) == []
