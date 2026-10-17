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


def test_windows_import_uses_kernel_version_and_restores_stdlib(monkeypatch):
    import platform

    def forbidden_hostname_version():
        raise AssertionError("hostname-based platform.version must not run")

    monkeypatch.setattr(platform, "version", forbidden_hostname_version)
    monkeypatch.setattr(
        recycling,
        "sys",
        SimpleNamespace(getwindowsversion=lambda: SimpleNamespace(platform_version=(10, 0, 26100))),
    )
    module = SimpleNamespace(send2trash=lambda _: None)

    def load(name):
        assert name == "send2trash.win.modern"
        assert platform.version() == "10.0.26100"
        return module

    monkeypatch.setattr(recycling.importlib, "import_module", load)
    assert recycling._windows_backend() == module.send2trash
    assert module.version() == "10.0.26100"
    assert platform.version is forbidden_hostname_version


def test_windows_import_restores_stdlib_when_dependency_missing(monkeypatch):
    import platform

    original = platform.version

    def missing(_):
        raise ImportError("missing pywin32")

    monkeypatch.setattr(recycling.importlib, "import_module", missing)
    with pytest.raises(ImportError):
        recycling._windows_backend()
    assert platform.version is original
