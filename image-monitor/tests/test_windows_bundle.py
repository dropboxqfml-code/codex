import importlib.util
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from image_monitor import PUBLIC_VERSION
from image_monitor.__main__ import main

BUILDER = Path(__file__).resolve().parents[1] / "scripts" / "build_windows_bundle.py"


@pytest.fixture
def bundle_project(tmp_path, monkeypatch):
    project = tmp_path / "image-monitor"
    project.mkdir()
    names = [
        ".gitignore",
        "README.md",
        "RUN_WINDOWS_TEST.cmd",
        "RETRY_WINDOWS_TEST.cmd",
        "RUN_CHROME_TEST.cmd",
        "RETRY_CHROME_TEST.cmd",
        "RUN_SITE_INSPECTION.cmd",
        "RUN_LIST_INSPECTION.cmd",
        "RUN_WATCH_TEST.cmd",
        "RUN_CANDIDATE_TEST.cmd",
        "RUN_CANDIDATE_SAVE_TEST.cmd",
        "RUN_CANDIDATE_FINISH.cmd",
        "RUN_MONITOR.cmd",
        "RUN_MONITOR_SAVE.cmd",
        "RUN_MONITOR_FINISH.cmd",
        "RUN_MONITOR_BATCH.cmd",
        "RUN_MONITOR_BATCH_FINISH.cmd",
        "RUN_POST_SAVE_TEST.cmd",
        "RETRY_POST_SAVE_TEST.cmd",
        "WINDOWS_TEST_GUIDE.txt",
        "pyproject.toml",
        "uv.lock",
        "src/image_monitor/VERSION",
    ]
    guide = b"\xef\xbb\xbfGuide\r\nOne file\r\nThree steps\r\n"
    for name in names:
        contents = guide if name == "WINDOWS_TEST_GUIDE.txt" else b"fixture\n"
        if name.endswith(".cmd"):
            contents = b"@echo off\r\nexit /b 0\r\n"
        if name.endswith("/VERSION"):
            contents = b"0.4.0-alpha.1\n"
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        (project / name).write_bytes(contents)
    spec = importlib.util.spec_from_file_location("windows_bundle_builder", BUILDER)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(builder, "__file__", str(project / "scripts" / BUILDER.name))
    monkeypatch.setattr(
        builder.subprocess,
        "check_output",
        lambda *_args, **_kwargs: "".join(f"image-monitor/{name}\0" for name in names).encode(),
    )
    monkeypatch.setattr(sys, "argv", [str(BUILDER)])
    return builder, project, names, guide


@pytest.mark.parametrize("version", ["0.4.0-alpha.1", "0.4.0-beta.2", "1.0.0-rc.1", "1.0.0"])
def test_bundle_uses_product_version_and_one_guide_inside_project(bundle_project, version):
    builder, project, _, guide = bundle_project
    (project / "src/image_monitor/VERSION").write_text(version, encoding="ascii")
    builder.main()

    output = project.parent / "downloads" / f"image-monitor-windows-test-{version}.zip"
    with ZipFile(output) as archive:
        assert archive.read("image-monitor/src/image_monitor/VERSION").decode("ascii") == version
        guides = [
            name for name in archive.namelist() if Path(name).name == "WINDOWS_TEST_GUIDE.txt"
        ]
        assert guides == ["image-monitor/WINDOWS_TEST_GUIDE.txt"]
        assert archive.read(guides[0]) == guide
        assert all(name.startswith("image-monitor/") for name in archive.namelist())
        assert archive.testzip() is None
    assert list(output.parent.iterdir()) == [output]
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        builder.main()
    assert output.read_bytes() == before


@pytest.mark.parametrize("version", ["v24", "0.4.0-beta.1", "../0.4.0-alpha.1"])
def test_explicit_version_must_match_product(bundle_project, monkeypatch, version):
    builder, project, _, _ = bundle_project
    monkeypatch.setattr(sys, "argv", [str(BUILDER), "--version", version])
    with pytest.raises(SystemExit) as stopped:
        builder.main()
    assert stopped.value.code == 2
    assert not (project.parent / "downloads").exists()


@pytest.mark.parametrize("version", ["v23", "0.04.0", "0.4.0-alpha", "../0.4.0-alpha.1"])
def test_invalid_product_version_fails_before_build(bundle_project, version):
    builder, project, _, _ = bundle_project
    (project / "src/image_monitor/VERSION").write_text(version, encoding="ascii")
    with pytest.raises(SystemExit) as stopped:
        builder.main()
    assert stopped.value.code == 2
    assert not (project.parent / "downloads").exists()


def test_nested_guide_fails_before_writing_an_archive(bundle_project):
    builder, project, names, _ = bundle_project
    names.append("docs/Windows_Test_Guide.txt")
    with pytest.raises(ValueError, match="one guide"):
        builder.main()
    assert not (project.parent / "downloads").exists()


def test_cli_shows_packaged_public_version(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["image-monitor", "--version"])
    with pytest.raises(SystemExit) as stopped:
        main()
    assert stopped.value.code == 0
    assert capsys.readouterr().out.strip() == f"Image Monitor {PUBLIC_VERSION}"
