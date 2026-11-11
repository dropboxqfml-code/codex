"""Release tests inspect artifacts and guard launch defaults; no Windows or GPIB execution."""

import importlib.util
import json
import os
import struct
import zipfile
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("trial_builder", PROJECT / "scripts/build_trial_bundle.py")
launcher = load("trial_launcher", PROJECT / "packaging/launch.py")
verifier = load("trial_verifier", PROJECT / "packaging/verify_bundle.py")


def symlink_or_skip_unprivileged_windows(link, target):
    try:
        link.symlink_to(target)
    except OSError as exc:
        if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows runner cannot create symlinks without the required privilege")
        raise


def test_default_launchers_cannot_turn_connection_check_into_measurement(tmp_path):
    args = launcher.arguments("diagnose", [], tmp_path)
    assert args[0] == "diagnose"
    assert "--confirm-off" not in args
    assert "measure" not in args and "--resource" not in args
    args = launcher.arguments("diagnose", ["GPIB0::27::INSTR", "@ivi"], tmp_path)
    assert args[args.index("--resource") + 1] == "GPIB0::27::INSTR"
    assert args[args.index("--backend") + 1] == "@ivi"
    assert "--confirm-off" not in args
    with pytest.raises(ValueError, match="requires"):
        launcher.arguments("confirm-off", [], tmp_path)
    assert "--confirm-off" in launcher.arguments("confirm-off", ["GPIB0::27::INSTR"], tmp_path)
    with pytest.raises(ValueError, match="GPIB"):
        launcher.arguments("diagnose", ["COM1"], tmp_path)


def test_simulation_launcher_does_not_accept_silently_loaded_config(tmp_path):
    args = launcher.arguments("simulate", [], tmp_path)
    assert args[0] == "simulate"
    assert args[args.index("--config") + 1] == str(tmp_path / "app/examples/simulation_config.json")
    with pytest.raises(ValueError, match="custom simulation"):
        launcher.arguments("simulate", ["untrusted.json"], tmp_path)
    with pytest.raises(ValueError, match="no configuration"):
        launcher.main(["gui", "--config", "prior-real-run.json"])


def test_portable_gui_cannot_inherit_a_foreign_qt_plugin_stack(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_PLUGIN_PATH", "foreign-Anaconda/plugins")
    monkeypatch.setenv("QT_QPA_PLATFORM_PLUGIN_PATH", "foreign-PyQt/plugins/platforms")
    monkeypatch.setenv("PYQTGRAPH_QT_LIB", "PyQt5")
    launcher.configure_qt_environment(tmp_path)
    plugins = tmp_path / "runtime/Lib/site-packages/PySide6/plugins"
    assert os.environ["QT_PLUGIN_PATH"] == str(plugins)
    assert os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] == str(plugins / "platforms")
    assert os.environ["PYQTGRAPH_QT_LIB"] == "PySide6"


def test_bundle_manifest_detects_corruption_and_missing_files(tmp_path):
    (tmp_path / "app.txt").write_text("original")
    builder.write_manifest(tmp_path, release_version="test", native_verified=False)
    assert verifier.verify(tmp_path)["status"] == "passed"
    (tmp_path / "app.txt").write_text("changed")
    result = verifier.verify(tmp_path)
    assert result["status"] == "failed"
    assert result["errors"] == [{"file": "app.txt", "reason": "hash mismatch"}]
    (tmp_path / "app.txt").unlink()
    assert verifier.verify(tmp_path)["errors"] == [{"file": "app.txt", "reason": "missing"}]


@pytest.mark.parametrize("relative", ["../outside.txt", "/outside", "C:/outside", "a\\b"])
def test_untrusted_manifest_cannot_read_outside_bundle(tmp_path, relative):
    (tmp_path / "bundle_manifest.json").write_text(
        json.dumps({"schema_version": 1, "files": {relative: "untrusted"}})
    )
    with pytest.raises(ValueError, match="inside"):
        verifier.verify(tmp_path)


def test_release_source_allowlist_excludes_runs_credentials_and_generated_history(tmp_path):
    for name in (
        "README.md",
        "pyproject.toml",
        "uv.lock",
        "src/keithley6517a/code.py",
        "docs/guide.md",
        "examples/config.json",
        "examples/picture.png",
        "runs/private.csv",
        ".env",
        "diagnostics/device.json",
        "src/keithley6517a/__pycache__/secret.py",
        "examples/manual_verified_simulation/private/raw_io.jsonl",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("sample")
    destination = tmp_path / "release"
    builder.copy_sources(destination, root=tmp_path)
    shipped = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    }
    assert shipped == {
        "README.md",
        "pyproject.toml",
        "uv.lock",
        "src/keithley6517a/code.py",
        "docs/guide.md",
        "examples/config.json",
        "examples/picture.png",
    }


def test_source_symlink_cannot_leak_outside_file(tmp_path):
    source = tmp_path / "project"
    package = source / "src/keithley6517a"
    package.mkdir(parents=True)
    outside = tmp_path / "outside.py"
    outside.write_text("private = True")
    symlink_or_skip_unprivileged_windows(package / "leak.py", outside)
    with pytest.raises(ValueError, match="escapes"):
        builder.copy_sources(tmp_path / "release", root=source)


def test_archive_is_verifiable_and_never_overwrites_existing_release(tmp_path):
    source = tmp_path / "app"
    source.mkdir()
    (source / "file.txt").write_text("public data")
    target = tmp_path / "app.zip"
    builder.archive(source, target)
    assert target.with_suffix(".zip.sha256").read_text().split()[0] == builder.sha256(target)
    with zipfile.ZipFile(target) as archive:
        assert archive.namelist() == ["app/file.txt"]
    with pytest.raises(FileExistsError, match="overwrite"):
        builder.archive(source, target)


def test_pe_validation_rejects_x86_and_non_executable_payload(tmp_path):
    path = tmp_path / "python.exe"
    path.write_bytes(
        b"MZ" + b"\0" * 58 + struct.pack("<I", 64) + b"PE\0\0" + struct.pack("<H", 0x8664)
    )
    assert builder.pe_machine(path) == 0x8664
    path.write_text("not a binary")
    with pytest.raises(ValueError, match="PE"):
        builder.pe_machine(path)


def test_cross_host_uv_alias_is_not_copied_as_windows_payload(tmp_path):
    source = tmp_path / "runtime-source"
    source.mkdir()
    (source / "python.exe").write_bytes(b"MZ-real-Windows-payload")
    (source / "LICENSE.txt").write_text("upstream license")
    symlink_or_skip_unprivileged_windows(source / "python", source / "python3.12")
    target = tmp_path / "runtime-target"
    builder.copy_windows_runtime(source, target)
    assert not (target / "python").exists()
    assert (target / "python.exe").read_bytes() == b"MZ-real-Windows-payload"
    assert (target / "LICENSE.txt").read_text() == "upstream license"


def test_only_documented_upstream_pip_templates_may_have_non_x64_architecture(tmp_path):
    def executable(relative, machine):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            b"MZ" + b"\0" * 58 + struct.pack("<I", 64) + b"PE\0\0" + struct.pack("<H", machine)
        )

    executable("python.exe", 0x8664)
    executable("Lib/site-packages/pip/_vendor/distlib/t32.exe", 0x14C)
    assert builder.inspect_windows_binaries(tmp_path)["windows_x64_binary_count"] == 1
    executable("Lib/site-packages/PySide6/QtCore.pyd", 0x14C)
    with pytest.raises(ValueError, match="application binary"):
        builder.inspect_windows_binaries(tmp_path)


def test_third_party_notices_preserve_metadata_and_license_paths(tmp_path):
    info = tmp_path / "runtime/Lib/site-packages/example-1.dist-info"
    (info / "licenses").mkdir(parents=True)
    (info / "METADATA").write_text("Name: example\nVersion: 1\nLicense-Expression: MIT\n")
    (info / "licenses/LICENSE").write_text("verbatim upstream notice")
    result = builder.third_party_notices(tmp_path)
    package = result["distributions"][0]
    assert package["name"] == "example" and package["license_expression"] == "MIT"
    assert package["license_files"] == [
        "runtime/Lib/site-packages/example-1.dist-info/licenses/LICENSE"
    ]
    assert (info / "licenses/LICENSE").read_text() == "verbatim upstream notice"
