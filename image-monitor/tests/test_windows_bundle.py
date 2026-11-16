import importlib.util
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

BUILDER = Path(__file__).resolve().parents[1] / "scripts" / "build_windows_bundle.py"


def test_bundle_contains_one_guide_inside_the_project_folder(tmp_path, monkeypatch):
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
        "RUN_POST_SAVE_TEST.cmd",
        "RETRY_POST_SAVE_TEST.cmd",
        "WINDOWS_TEST_GUIDE.txt",
        "pyproject.toml",
        "uv.lock",
    ]
    guide = b"\xef\xbb\xbfGuide\r\nOne file\r\nThree steps\r\n"
    for name in names:
        contents = guide if name == "WINDOWS_TEST_GUIDE.txt" else b"fixture\n"
        if name.endswith(".cmd"):
            contents = b"@echo off\r\nexit /b 0\r\n"
        (project / name).write_bytes(contents)
    spec = importlib.util.spec_from_file_location("windows_bundle_builder", BUILDER)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(builder, "__file__", str(project / "scripts" / BUILDER.name))
    tracked = "\0".join(f"image-monitor/{name}" for name in names) + "\0"
    monkeypatch.setattr(
        builder.subprocess, "check_output", lambda *_args, **_kwargs: tracked.encode()
    )
    monkeypatch.setattr(sys, "argv", [str(BUILDER), "--version", "v8"])

    builder.main()

    output = tmp_path / "downloads" / "image-monitor-windows-test-v8.zip"
    with ZipFile(output) as archive:
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
