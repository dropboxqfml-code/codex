import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from image_monitor.validation import VerificationError, VerificationIncomplete, verify_image


def corrupt_png_crc(path: Path) -> None:
    Image.new("RGB", (24, 16), "red").save(path)
    data = bytearray(path.read_bytes())
    chunk = data.find(b"IDAT")
    size = int.from_bytes(data[chunk - 4 : chunk], "big")
    data[chunk + 4 + size] ^= 1
    path.write_bytes(data)


def test_bad_png_crc_is_a_controlled_corruption_error(tmp_path):
    path = tmp_path / "bad-crc.png"
    corrupt_png_crc(path)
    original = path.read_bytes()
    with pytest.raises(VerificationError, match="structure") as caught:
        verify_image(path, writer_finished=True)
    assert not isinstance(caught.value, VerificationIncomplete)
    assert isinstance(caught.value.__cause__, SyntaxError)
    assert path.read_bytes() == original


def test_bad_png_crc_cli_returns_failure_without_traceback(tmp_path):
    path = tmp_path / "bad-crc.png"
    corrupt_png_crc(path)
    result = subprocess.run(
        [sys.executable, "-m", "image_monitor", "verify", str(path), "--writer-finished"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "structure verification failed" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("replacement_stage", ["after_open", "at_final_path_check"])
def test_replaced_path_is_not_verified_as_the_open_file(tmp_path, monkeypatch, replacement_stage):
    path = tmp_path / "staged.png"
    replacement = tmp_path / "replacement.png"
    Image.new("RGB", (24, 16), "red").save(path)
    Image.new("RGB", (10, 10), "blue").save(replacement)
    replacement_bytes = replacement.read_bytes()
    original_open = Path.open
    original_lstat = Path.lstat

    def replace_path():
        try:
            replacement.replace(path)
        except PermissionError:
            pytest.skip("Filesystem does not permit replacement of an open file")

    if replacement_stage == "after_open":

        def open_then_replace(self, *args, **kwargs):
            stream = original_open(self, *args, **kwargs)
            if self == path:
                try:
                    replace_path()
                except BaseException:
                    stream.close()
                    raise
            return stream

        monkeypatch.setattr(Path, "open", open_then_replace)
    else:
        lstat_calls = 0

        def replace_at_final_lstat(self, *args, **kwargs):
            nonlocal lstat_calls
            if self == path:
                lstat_calls += 1
                if lstat_calls == 2:
                    replace_path()
            return original_lstat(self, *args, **kwargs)

        monkeypatch.setattr(Path, "lstat", replace_at_final_lstat)

    with pytest.raises(VerificationIncomplete, match="changed"):
        verify_image(path, writer_finished=True)
    monkeypatch.setattr(Path, "open", original_open)
    monkeypatch.setattr(Path, "lstat", original_lstat)
    assert path.read_bytes() == replacement_bytes
