import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from image_monitor import monitor_settings as settings
from image_monitor.queue import QueueError


def test_absent_settings_return_defaults_without_creating_any_file(tmp_path):
    missing = tmp_path / "not-created"
    assert settings.load_monitor_settings(missing) == {"schema_version": 1, "interval_seconds": 60}
    assert not missing.exists()


def test_settings_round_trip_preserves_other_files(tmp_path):
    foreign = tmp_path / "preserve.txt"
    foreign.write_bytes(b"Foreign contents")
    assert settings.save_monitor_settings(tmp_path, 120)["interval_seconds"] == 120
    assert settings.load_monitor_settings(tmp_path)["interval_seconds"] == 120
    assert settings.save_monitor_settings(tmp_path, 300)["interval_seconds"] == 300
    assert settings.load_monitor_settings(tmp_path)["interval_seconds"] == 300
    assert foreign.read_bytes() == b"Foreign contents"
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("interval", [True, False, 60.0, "60", None, 0, 59, 301])
def test_invalid_interval_never_creates_or_changes_settings(tmp_path, interval):
    with pytest.raises(QueueError):
        settings.save_monitor_settings(tmp_path, interval)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "data",
    [
        b"not JSON",
        b"[]",
        b'{"schema_version":true,"interval_seconds":60}',
        b'{"schema_version":2,"interval_seconds":60}',
        b'{"schema_version":1,"interval_seconds":59}',
        b'{"schema_version":1,"interval_seconds":NaN}',
        b'{"schema_version":1,"interval_seconds":60,"extra":"preserve"}',
        b'{"schema_version":1,"schema_version":1,"interval_seconds":60}',
        b"x" * (settings.MAX_SETTINGS_BYTES + 1),
    ],
)
def test_unknown_existing_data_is_never_replaced(tmp_path, data):
    path = tmp_path / settings.SETTINGS_NAME
    path.write_bytes(data)
    with pytest.raises(QueueError):
        settings.load_monitor_settings(tmp_path)
    with pytest.raises(QueueError):
        settings.save_monitor_settings(tmp_path, 120)
    assert path.read_bytes() == data
    assert list(tmp_path.iterdir()) == [path]


def test_settings_refuse_symlink_and_directory_without_touching_target(tmp_path):
    target = tmp_path / "preserve.json"
    original = b'{"schema_version":1,"interval_seconds":60}'
    target.write_bytes(original)
    path = tmp_path / settings.SETTINGS_NAME
    try:
        path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Creating symlinks is unavailable")
    with pytest.raises(ValueError):
        settings.load_monitor_settings(tmp_path)
    assert target.read_bytes() == original
    path.unlink()
    path.mkdir()
    with pytest.raises(QueueError):
        settings.save_monitor_settings(tmp_path, 120)
    assert path.is_dir()


def test_failed_update_preserves_old_settings_and_unowned_temporary(tmp_path, monkeypatch):
    settings.save_monitor_settings(tmp_path, 60)
    path = tmp_path / settings.SETTINGS_NAME
    original = path.read_bytes()
    foreign = tmp_path / ".foreign.tmp"
    foreign.write_bytes(b"Keep")

    def fail(*_):
        raise OSError("Synthetic replace failure")

    monkeypatch.setattr(settings.os, "replace", fail)
    with pytest.raises(OSError):
        settings.save_monitor_settings(tmp_path, 120)
    assert path.read_bytes() == original
    assert foreign.read_bytes() == b"Keep"
    assert not list(tmp_path.glob(f".{settings.SETTINGS_NAME}.*.tmp"))


def test_temp_collision_is_preserved(tmp_path, monkeypatch):
    token = "b" * 32
    path = tmp_path / f".{settings.SETTINGS_NAME}.{token}.tmp"
    path.write_bytes(b"Foreign contents")
    monkeypatch.setattr(settings.uuid, "uuid4", lambda: SimpleNamespace(hex=token))
    with pytest.raises(FileExistsError):
        settings.save_monitor_settings(tmp_path, 60)
    assert path.read_bytes() == b"Foreign contents"


def test_initial_publication_refuses_a_new_foreign_destination(tmp_path, monkeypatch):
    path = tmp_path / settings.SETTINGS_NAME
    method = "rename" if os.name == "nt" else "link"
    publish = getattr(settings.os, method)

    def collide(source, destination, **options):
        Path(destination).write_bytes(b"Foreign contents")
        return publish(source, destination, **options)

    monkeypatch.setattr(settings.os, method, collide)
    with pytest.raises(FileExistsError):
        settings.save_monitor_settings(tmp_path, 60)
    assert path.read_bytes() == b"Foreign contents"
    assert not list(tmp_path.glob(f".{settings.SETTINGS_NAME}.*.tmp"))


def test_settings_json_has_only_the_known_fields(tmp_path):
    settings.save_monitor_settings(tmp_path, 60)
    data = (tmp_path / settings.SETTINGS_NAME).read_bytes()
    assert len(data) < settings.MAX_SETTINGS_BYTES
    assert json.loads(data) == {"schema_version": 1, "interval_seconds": 60}
