import os
from types import SimpleNamespace

import pytest
from PIL import Image

from image_monitor import validation
from image_monitor.validation import VerificationIncomplete, verify_image


def synthetic_fstat(monkeypatch, descriptor_ctimes):
    """Model Windows descriptor metadata without changing global OS/platform state."""
    real_fstat = os.fstat
    calls = []

    def fstat_with_change_time(descriptor):
        info = real_fstat(descriptor)
        ctime_ns = descriptor_ctimes[len(calls)]
        calls.append(descriptor)
        return SimpleNamespace(
            st_dev=info.st_dev,
            st_ino=info.st_ino,
            st_mode=info.st_mode,
            st_size=info.st_size,
            st_mtime_ns=info.st_mtime_ns,
            st_ctime_ns=ctime_ns,
        )

    # Patch only this module's OS reference. In particular, os.name and pathlib's
    # platform-dependent classes must retain their real host behavior.
    monkeypatch.setattr(validation, "os", SimpleNamespace(fstat=fstat_with_change_time))
    return calls


def test_path_birthtime_and_descriptor_change_time_can_differ(tmp_path, monkeypatch):
    path = tmp_path / "stable.png"
    Image.new("RGB", (24, 16), "red").save(path)
    original = path.read_bytes()
    path_birthtime = path.lstat().st_ctime_ns
    change_time = path_birthtime + 5_000_000_000
    calls = synthetic_fstat(monkeypatch, [change_time, change_time])

    result = verify_image(path, writer_finished=True)

    assert result.detected_format == "PNG"
    assert (result.width, result.height) == (24, 16)
    assert result.file_size == len(original)
    assert len(calls) == 2
    assert path.read_bytes() == original


def test_descriptor_change_time_mutation_still_rejects_file(tmp_path, monkeypatch):
    path = tmp_path / "changed-metadata.png"
    Image.new("RGB", (24, 16), "red").save(path)
    initial_change_time = path.lstat().st_ctime_ns + 5_000_000_000
    calls = synthetic_fstat(
        monkeypatch,
        [initial_change_time, initial_change_time + 1_000_000_000],
    )

    with pytest.raises(VerificationIncomplete, match="changed during verification"):
        verify_image(path, writer_finished=True)

    assert len(calls) == 2
