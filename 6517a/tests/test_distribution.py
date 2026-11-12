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


def test_verification_feedback_starts_before_hashing_and_saves_the_result(
    tmp_path, monkeypatch, capsys
):
    (tmp_path / "app.txt").write_text("original")
    builder.write_manifest(tmp_path, release_version="test", native_verified=False)
    original_digest = verifier.hashlib.file_digest
    before_hashing = []

    def digest(stream, algorithm):
        before_hashing.append(capsys.readouterr().err)
        return original_digest(stream, algorithm)

    monkeypatch.setattr(verifier.hashlib, "file_digest", digest)
    assert verifier.main([str(tmp_path), "--progress", "--save-report"]) == 0
    captured = capsys.readouterr()
    assert "[CHECK] 0/1" in before_hashing[0]
    assert "[CHECK] 1/1" in captured.err
    report = json.loads(captured.out)
    assert report["status"] == "passed"
    assert report["verified_files"] == 1
    assert report["hardware_verified"] is False
    assert report["report_saved"] is True
    saved = Path(report["report_path"])
    assert saved.parent == tmp_path.resolve() / "diagnostics"
    assert json.loads(saved.read_text(encoding="utf-8")) == report


def test_builder_style_verifier_does_not_add_reports_to_the_release(tmp_path, capsys):
    (tmp_path / "app.txt").write_text("original")
    builder.write_manifest(tmp_path, release_version="test", native_verified=False)
    original_files = set(tmp_path.rglob("*"))
    assert verifier.main([str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "passed"
    assert captured.err == ""
    assert set(tmp_path.rglob("*")) == original_files


@pytest.mark.parametrize(
    "manifest",
    [None, "{", "[]", '{"schema_version": 1, "files": {"../outside.txt": "hash"}}'],
)
def test_manifest_failures_produce_failed_results_and_reports(tmp_path, capsys, manifest):
    if manifest is not None:
        (tmp_path / "bundle_manifest.json").write_text(manifest)
    assert verifier.main([str(tmp_path), "--progress", "--save-report"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "failed"
    assert report["errors"]
    assert report["hardware_verified"] is False
    assert json.loads(Path(report["report_path"]).read_text(encoding="utf-8")) == report


@pytest.mark.parametrize("changed", [True, False])
def test_incomplete_or_changed_bundle_never_reports_success(tmp_path, capsys, changed):
    path = tmp_path / "app.txt"
    path.write_text("original")
    builder.write_manifest(tmp_path, release_version="test", native_verified=False)
    if changed:
        path.write_text("changed")
    else:
        path.unlink()
    assert verifier.main([str(tmp_path), "--progress", "--save-report"]) == 2
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert "[CHECK] 1/1" in captured.err
    assert report["status"] == "failed"
    assert report["verified_files"] == 0
    assert report["errors"][0]["reason"] == ("hash mismatch" if changed else "missing")


def test_report_write_failure_remains_visible_without_changing_integrity_result(tmp_path, capsys):
    (tmp_path / "app.txt").write_text("original")
    builder.write_manifest(tmp_path, release_version="test", native_verified=False)
    (tmp_path / "diagnostics").write_text("A file blocks report directory creation")
    assert verifier.main([str(tmp_path), "--save-report"]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["status"] == "passed"
    assert report["report_saved"] is False
    assert report["report_error"]
    assert "[WARN]" in captured.err


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


def fake_runtime_distributions(tmp_path):
    site = tmp_path / "site-packages"
    site.mkdir()
    lock = tmp_path / "uv.lock"
    packages = []
    for name in sorted(builder.RUNTIME_DISTRIBUTIONS):
        info = site / (name.replace("-", "_") + "-1.0.dist-info")
        info.mkdir()
        (info / "METADATA").write_text(f"Name: {name}\nVersion: 1.0\n", encoding="utf-8")
        (info / "WHEEL").write_text("Wheel-Version: 1.0\nTag: py3-none-any\n", encoding="utf-8")
        packages.append(f'[[package]]\nname = "{name}"\nversion = "1.0"\n')
    lock.write_text("\n".join(packages), encoding="utf-8")
    return site, lock


def test_runtime_audit_requires_base_dependencies_and_exact_lock_versions(tmp_path):
    site, lock = fake_runtime_distributions(tmp_path)
    report = builder.inspect_runtime_distributions(site, lock)
    assert len(report["locked_runtime_distributions"]) == 7
    assert "gpib-ctypes" not in report["locked_runtime_distributions"]
    assert "pyvisa-py" not in report["locked_runtime_distributions"]
    info = site / "pyvisa-1.0.dist-info/METADATA"
    info.write_text("Name: pyvisa\nVersion: 2.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match uv.lock"):
        builder.inspect_runtime_distributions(site, lock)


def test_unrelated_wheel_cannot_replace_a_missing_base_dependency_by_count(tmp_path):
    site, lock = fake_runtime_distributions(tmp_path)
    info = site / "pyvisa-1.0.dist-info/METADATA"
    info.write_text("Name: unrelated-wheel\nVersion: 1.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unexpected runtime distribution"):
        builder.inspect_runtime_distributions(site, lock)


def test_runtime_audit_rejects_missing_base_wheel_and_incompatible_platform(tmp_path):
    site, lock = fake_runtime_distributions(tmp_path)
    (site / "pyvisa-1.0.dist-info").rename(site / "pyvisa-1.0.uninstalled")
    with pytest.raises(ValueError, match="Missing required runtime distributions.*pyvisa"):
        builder.inspect_runtime_distributions(site, lock)
    (site / "pyvisa-1.0.uninstalled").rename(site / "pyvisa-1.0.dist-info")
    (site / "pyvisa-1.0.dist-info/WHEEL").write_text(
        "Tag: cp312-cp312-manylinux_2_17_x86_64\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Incompatible wheel tags"):
        builder.inspect_runtime_distributions(site, lock)


def test_runtime_audit_accepts_official_interpreter_pip_without_counting_it_as_app_dependency(
    tmp_path,
):
    site, lock = fake_runtime_distributions(tmp_path)
    info = site / "pip-99.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Name: pip\nVersion: 99\n", encoding="utf-8")
    (info / "WHEEL").write_text("Tag: py3-none-any\n", encoding="utf-8")
    report = builder.inspect_runtime_distributions(site, lock)
    assert report["interpreter_bundled_distributions"] == {"pip": "99"}
    assert set(report["locked_runtime_distributions"]) == set(builder.RUNTIME_DISTRIBUTIONS)


@pytest.mark.parametrize("name", ["gpib-32.dll", "NI4882.DLL", "visa32.dll", "visa64.dll"])
def test_trial_bundle_does_not_redistribute_vendor_driver_dlls(tmp_path, name):
    driver = tmp_path / "nested" / name
    driver.parent.mkdir()
    driver.write_bytes(b"vendor library must remain installed on the user's system")
    with pytest.raises(ValueError, match="Vendor NI/VISA drivers must not be bundled"):
        builder.verify_no_vendor_drivers(tmp_path)


extension_installer = load("trial_optional_extension", PROJECT / "packaging/install_ni_only.py")


def optional_payload(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for entry in extension_installer.ENTRIES:
        path = directory / entry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Optional package source fixture; never imported by installer\n")
    for name, version in extension_installer.VERSIONS.items():
        info = directory / (name.replace("-", "_") + f"-{version}.dist-info")
        info.mkdir()
        (info / "METADATA").write_text(f"Name: {name}\nVersion: {version}\n")
        (info / "LICENSE").write_text("GPLv2" if name == "gpib-ctypes" else "MIT")


def optional_root(tmp_path):
    root = tmp_path / "trial"
    (root / "app").mkdir(parents=True)
    builder.write_optional_ni_requirements(
        PROJECT / "uv.lock", root / "app/ni-only-requirements.txt"
    )
    return root


def test_optional_requirements_are_only_two_pinned_hash_checked_pure_wheel_packages(tmp_path):
    target = tmp_path / "optional.txt"
    builder.write_optional_ni_requirements(PROJECT / "uv.lock", target)
    lines = [line for line in target.read_text().splitlines() if not line.startswith("#")]
    assert len(lines) == 2
    assert lines[0].startswith("gpib-ctypes==0.3.0 --hash=sha256:")
    assert lines[1].startswith("pyvisa-py==0.8.1 --hash=sha256:")
    assert "numpy" not in target.read_text()
    assert "pyside" not in target.read_text()
    args = extension_installer.pip_arguments("python.exe", target, tmp_path / "extension")
    assert "--require-hashes" in args
    assert "--no-deps" in args
    assert args[args.index("--only-binary") + 1] == ":all:"
    assert args[args.index("--index-url") + 1] == "https://pypi.org/simple"
    assert "--trusted-host" not in args and "--no-verify-hashes" not in args


def test_optional_install_stays_outside_base_and_only_complete_manifest_activates(tmp_path):
    root = optional_root(tmp_path)
    baseline = root / "runtime/Lib/site-packages/base.txt"
    baseline.parent.mkdir(parents=True)
    baseline.write_text("unchanged standard NI-VISA baseline")
    calls = []

    def fake_pip(arguments, *, check):
        calls.append(arguments)
        assert check
        assert not extension_installer.extension_directory(root).exists()
        optional_payload(Path(arguments[arguments.index("--target") + 1]))

    directory = extension_installer.install(root, runner=fake_pip)
    assert len(calls) == 1
    assert directory == root / "extensions/ni4882"
    assert baseline.read_text() == "unchanged standard NI-VISA baseline"
    assert extension_installer.installed_extension(root) == directory
    assert (directory / "gpib_ctypes-0.3.0.dist-info/LICENSE").read_text() == "GPLv2"
    assert (
        extension_installer.install(root, runner=lambda *a, **k: pytest.fail("No reinstall"))
        == directory
    )
    (directory / "pyvisa_py/__init__.py").write_text("changed")
    with pytest.raises(ValueError, match="integrity"):
        extension_installer.installed_extension(root)


def test_failed_optional_install_leaves_no_activatable_extension(tmp_path):
    root = optional_root(tmp_path)

    def failed_pip(arguments, **kwargs):
        raise RuntimeError("download failed")

    with pytest.raises(RuntimeError, match="download failed"):
        extension_installer.install(root, runner=failed_pip)
    assert extension_installer.installed_extension(root) is None
    assert not extension_installer.extension_directory(root).exists()


def test_existing_incomplete_extension_is_never_overwritten_or_deleted(tmp_path):
    root = optional_root(tmp_path)
    directory = extension_installer.extension_directory(root)
    directory.mkdir(parents=True)
    user_file = directory / "keep-user-file.txt"
    user_file.write_text("preserve")
    with pytest.raises(ValueError, match="incomplete"):
        extension_installer.install(root, runner=lambda *a, **k: pytest.fail("No implicit repair"))
    assert user_file.read_text() == "preserve"


def test_launcher_never_downloads_extension_and_ignores_incomplete_payload(tmp_path, monkeypatch):
    root = optional_root(tmp_path)
    (root / "tools").mkdir()
    (root / "tools/install_ni_only.py").write_bytes(
        (PROJECT / "packaging/install_ni_only.py").read_bytes()
    )
    before = list(__import__("sys").path)
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: pytest.fail("Launch cannot install packages")
    )
    assert launcher.configure_optional_extension(root) is None
    directory = extension_installer.extension_directory(root)
    directory.mkdir(parents=True)
    optional_payload(directory)
    assert launcher.configure_optional_extension(root) is None
    assert __import__("sys").path == before


def test_completed_optional_extension_is_added_without_importing_plugin(tmp_path, monkeypatch):
    root = optional_root(tmp_path)
    (root / "tools").mkdir()
    (root / "tools/install_ni_only.py").write_bytes(
        (PROJECT / "packaging/install_ni_only.py").read_bytes()
    )

    def fake_pip(arguments, **kwargs):
        optional_payload(Path(arguments[arguments.index("--target") + 1]))

    directory = extension_installer.install(root, runner=fake_pip)
    import sys

    original_path = list(sys.path)
    original_plugins = {name: sys.modules.get(name) for name in ("pyvisa_py", "gpib_ctypes")}
    try:
        assert launcher.configure_optional_extension(root) == directory
        assert sys.path[0] == str(directory)
        assert {name: sys.modules.get(name) for name in original_plugins} == original_plugins
    finally:
        sys.path[:] = original_path


def test_unconfirmed_installer_start_does_not_download_or_access_hardware(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "CANCEL")
    monkeypatch.setattr(extension_installer, "install", lambda *a, **k: pytest.fail("No install"))
    assert extension_installer.main([]) == 2


native_smoke = load("trial_native_smoke", PROJECT / "packaging/smoke.py")


@pytest.mark.parametrize("temporary_alias", [False, True])
def test_native_optional_installer_smoke_uses_external_temporary_payload_and_removes_it(
    tmp_path, monkeypatch, temporary_alias
):
    from contextlib import contextmanager
    from types import SimpleNamespace

    if temporary_alias:
        original_temporary = native_smoke.tempfile.TemporaryDirectory

        @contextmanager
        def aliased_temporary(*args, **kwargs):
            with original_temporary(*args, **kwargs) as directory:
                if kwargs.get("prefix") == "6517a-ni-extension-smoke-":
                    alias = Path(directory) / "alias"
                    alias.mkdir()
                    yield str(alias / "..")
                else:
                    yield directory

        monkeypatch.setattr(native_smoke.tempfile, "TemporaryDirectory", aliased_temporary)

    root = optional_root(tmp_path)
    observed = []

    def install(trial):
        observed.append(trial)
        assert not trial.resolve().is_relative_to(root.resolve())
        assert (trial / "app/ni-only-requirements.txt").read_bytes() == (
            root / "app/ni-only-requirements.txt"
        ).read_bytes()

        def fake_pip(arguments, **kwargs):
            optional_payload(Path(arguments[arguments.index("--target") + 1]))

        return extension_installer.install(trial, runner=fake_pip)

    installer = SimpleNamespace(
        install=install,
        installed_extension=extension_installer.installed_extension,
        inspect_payload=extension_installer.inspect_payload,
    )
    report = native_smoke.optional_installer_smoke(root, installer=installer)
    assert report["optional_install_smoke"] == "passed"
    assert report["driver_IO"] is False
    assert report["optional_driver_imported"] is False
    assert report["temporary_extension_removed"] is True
    assert not observed[0].exists()
    assert not (root / "extensions").exists()


def test_native_optional_installer_failure_fails_smoke_and_cleans_temporary_files(tmp_path, capsys):
    from types import SimpleNamespace

    root = optional_root(tmp_path)
    observed = []

    def failed(trial):
        observed.append(trial)
        raise RuntimeError("optional download failed")

    installer = SimpleNamespace(install=failed)
    with pytest.raises(RuntimeError, match="optional download failed"):
        native_smoke.optional_installer_smoke(root, installer=installer)
    assert not observed[0].exists()
    assert "optional_install_smoke" not in capsys.readouterr().out
