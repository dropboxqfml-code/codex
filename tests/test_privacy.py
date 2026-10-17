import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from threading import Event

import pytest
from PIL import EpsImagePlugin

from image_duplicate_finder.models import Decision
from image_duplicate_finder.privacy import LocalOnlyError, local_path, windows_local_drive
from image_duplicate_finder.scanner import read_image, scan
from image_duplicate_finder.storage import ReviewStore
from image_duplicate_finder.trash import move_to_trash


def test_unc_and_network_drive_rejected_before_lookup(monkeypatch):
    queried = []
    for value in [r"\\server\share\pictures", "//server/share", r"\\?\UNC\server\share"]:
        with pytest.raises(LocalOnlyError):
            windows_local_drive(value, lambda p: queried.append(p))
    assert not queried
    with pytest.raises(LocalOnlyError):
        windows_local_drive(r"Z:\pictures", lambda _: 4)
    assert windows_local_drive(r"C:\pictures", lambda _: 3) == "C:\\"
    with pytest.raises(LocalOnlyError):
        local_path(Path("//server/share"))


def test_linked_ancestor_is_rejected(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(LocalOnlyError):
        local_path(alias / "not-yet-created.sqlite3")


def test_eps_delegate_never_invoked_even_with_misleading_extension(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(EpsImagePlugin, "Ghostscript", lambda *a, **k: calls.append(a))
    (tmp_path / "not-really.png").write_bytes(
        b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 20 20\n%%EndComments\nshowpage\n"
    )
    result = scan(tmp_path)
    assert result.scanned == 0
    assert len(result.errors) == 1
    assert not calls


def test_database_stores_no_plaintext_path_hash_or_thumbnail(tmp_path, image_factory):
    record = read_image(image_factory(), Event())
    database = tmp_path / "private.sqlite3"
    with ReviewStore(database) as store:
        store.set(record, Decision.KEEP)
        columns = {r[1] for r in store.connection.execute("PRAGMA table_info(reviews)")}
        assert columns == {"review_id", "decision"}
        assert store.get(record) == Decision.KEEP
        assert store.connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 1
        store.set(record, Decision.HOLD)
        assert store.connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0
    contents = database.read_bytes()
    assert str(record.path).encode("utf-8") not in contents
    assert record.sha256.encode() not in contents
    assert record.thumbnail not in contents
    if os.name != "nt":
        assert database.stat().st_mode & 0o777 == 0o600
        assert database.with_name(database.name + ".key").stat().st_mode & 0o777 == 0o600


def test_vulnerable_sqlite_is_rejected_before_opening_any_database(tmp_path, monkeypatch):
    database = tmp_path / "private.sqlite3"
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 49, 1))
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: pytest.fail("must not open database"))
    with pytest.raises(ValueError, match="CVE-2025-6965"):
        ReviewStore(database)
    assert not database.exists()


def test_legacy_db_migration_preserves_decisions_and_removes_raw_fields(tmp_path, image_factory):
    record = read_image(image_factory(), Event())
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            "CREATE TABLE reviews(path TEXT, sha256 TEXT, decision TEXT, updated_at TEXT)"
        )
        connection.execute(
            "INSERT INTO reviews VALUES (?, ?, 'keep', 'old timestamp')",
            (str(record.path), record.sha256),
        )
    connection.close()
    assert str(record.path).encode("utf-8") in database.read_bytes()
    assert record.sha256.encode() in database.read_bytes()
    with ReviewStore(database) as store:
        assert store.get(record) == Decision.KEEP
        assert store.connection.execute("PRAGMA user_version").fetchone()[0] == 2
    for path in tmp_path.glob("legacy.sqlite3*"):
        data = path.read_bytes()
        assert str(record.path).encode("utf-8") not in data
        assert record.sha256.encode() not in data
    with ReviewStore(database) as store:
        store.clear()
        assert store.get(record) == Decision.HOLD


def test_runtime_guard_blocks_dns_socket_process_and_file_urls():
    code = """
import json, socket, subprocess, sys, urllib.request
from image_duplicate_finder.privacy import install_runtime_guard, runtime_blocks
install_runtime_guard()
operations = [lambda: socket.getaddrinfo('example.invalid',443),
              lambda: socket.socket(socket.AF_INET,socket.SOCK_STREAM),
              lambda: subprocess.run([sys.executable,'-c','pass']),
              lambda: urllib.request.urlopen('https://example.invalid')]
for operation in operations:
    try: operation()
    except (PermissionError, OSError): pass
    else: raise AssertionError('forbidden operation was allowed')
print(json.dumps(runtime_blocks()))
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    counts = json.loads(result.stdout)
    assert counts["network"] >= 3
    assert counts["process"] == 1


def test_local_hostname_getter_is_distinct_from_network_resolution():
    code = """
import socket
from image_duplicate_finder.privacy import (
    install_runtime_guard, runtime_blocks, runtime_local_observations,
)
install_runtime_guard()
assert isinstance(socket.gethostname(), str)
assert runtime_local_observations() == {'socket.gethostname': 1}
assert runtime_blocks() == {'network': 0, 'process': 0}
try: socket.getaddrinfo('example.invalid',443)
except PermissionError: pass
else: raise AssertionError('DNS resolution was allowed')
assert runtime_blocks()['network'] == 1
"""
    subprocess.run([sys.executable, "-c", code], check=True, timeout=20)


def test_move_requires_positive_confirmation():
    with pytest.raises(ValueError, match="확인"):
        move_to_trash([], trash=lambda _: pytest.fail("must not move"))


@pytest.mark.parametrize("platform", ["vnc", "webgl"])
def test_remote_qt_backend_is_rejected_before_qt_initialization(platform):
    code = """
from image_duplicate_finder.privacy import LocalOnlyError, install_runtime_guard
try: install_runtime_guard()
except LocalOnlyError: pass
else: raise AssertionError('remote GUI backend accepted')
"""
    subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "QT_QPA_PLATFORM": platform},
        check=True,
    )


def test_generic_input_plugin_override_is_removed():
    code = """
import os
from image_duplicate_finder.privacy import install_runtime_guard
install_runtime_guard()
assert 'QT_QPA_GENERIC_PLUGINS' not in os.environ
assert 'QT_PLUGIN_PATH' not in os.environ
"""
    subprocess.run(
        [sys.executable, "-c", code],
        env={
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QPA_GENERIC_PLUGINS": "tuio",
            "QT_PLUGIN_PATH": "//example.invalid/plugins",
        },
        check=True,
    )


@pytest.mark.parametrize("extension", [".json", ".png", ".cross.png"])
def test_packaged_diagnostic_cannot_overwrite_existing_files(tmp_path, extension):
    root = Path(__file__).resolve().parents[1]
    report = tmp_path / "existing.json"
    protected = report.with_suffix(extension)
    protected.write_bytes(b"original private file")
    result = subprocess.run(
        [
            sys.executable,
            str(root / "packaging" / "windows_launcher.py"),
            "--build-smoke-report",
            str(report),
        ],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert protected.read_bytes() == b"original private file"


def test_one_drive_root_is_denied_before_stat(monkeypatch):
    from image_duplicate_finder import privacy

    if sys.platform != "win32":
        pytest.skip("Windows path policy test")
    monkeypatch.setenv("OneDrive", r"C:\Users\Tester\OneDrive")
    with pytest.raises(LocalOnlyError, match="OneDrive"):
        privacy.local_path(Path(r"C:\Users\Tester\OneDrive\photo.png"))
