from types import SimpleNamespace

import pytest

from image_duplicate_finder import recycling


def test_windows_requires_modern_backend(monkeypatch):
    calls = []
    monkeypatch.setattr(recycling, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(recycling, "_windows_backend", lambda: calls.append)
    monkeypatch.setattr(recycling, "send2trash", lambda _: pytest.fail("no legacy fallback"))
    recycling.recycle_file("example.png")
    assert calls == ["example.png"]


def test_missing_pywin32_blocks_deletion(monkeypatch):
    def missing():
        raise ImportError("missing dependency")

    monkeypatch.setattr(recycling, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(recycling, "_windows_backend", missing)
    monkeypatch.setattr(recycling, "send2trash", lambda _: pytest.fail("no legacy fallback"))
    with pytest.raises(OSError, match="pywin32"):
        recycling.recycle_file("example.png")


def test_com_backend_failure_normalized_without_fallback(monkeypatch):
    def failed(_):
        raise RuntimeError("COM unavailable")

    monkeypatch.setattr(recycling, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(recycling, "_windows_backend", lambda: failed)
    monkeypatch.setattr(recycling, "send2trash", lambda _: pytest.fail("no legacy fallback"))
    with pytest.raises(OSError, match="COM unavailable"):
        recycling.recycle_file("example.png")
