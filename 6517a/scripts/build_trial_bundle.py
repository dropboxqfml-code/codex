"""Build a Windows x64 portable trial ZIP and a clean developer source ZIP.

Windows binaries are downloaded from uv's official managed-CPython catalog;
dependency wheels are selected for Windows and checked against uv.lock hashes.
Cross-platform assembly is not a claim of Windows or hardware execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from datetime import UTC, datetime
from email.parser import Parser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_KEY = "cpython-3.12.14-windows-x86_64-none"
PYTHON_VERSION = "3.12.14"
# Required Windows application dependencies. CPython may also provide its own pip.
# Require identities and lock versions so an unrelated wheel cannot satisfy a count check.
RUNTIME_DISTRIBUTIONS = frozenset(
    {
        "colorama",
        "numpy",
        "pyqtgraph",
        "pyside6-essentials",
        "pyvisa",
        "shiboken6",
        "typing-extensions",
    }
)
VENDOR_DRIVER_FILENAMES = frozenset({"gpib-32.dll", "ni4882.dll", "visa32.dll", "visa64.dll"})
LAUNCHERS = (
    "Start-GUI.cmd",
    "Test-Simulation.cmd",
    "Check-Connection.cmd",
    "Check-Output-Off.cmd",
    "Verify-Bundle.cmd",
    "Run-CLI.cmd",
    "Enable-NI-Only.cmd",
)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(arguments, *, directory=PROJECT_ROOT, environment=None):
    return subprocess.run(
        [str(v) for v in arguments],
        cwd=directory,
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )


def version(root=PROJECT_ROOT):
    return tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]


def portable_source_files(root=PROJECT_ROOT):
    """An allowlist: never bundle local runs, diagnostics, credentials, or ignored files."""
    paths = [root / name for name in ("README.md", "pyproject.toml", "uv.lock")]
    paths += sorted((root / "src/keithley6517a").rglob("*.py"))
    paths += sorted((root / "docs").glob("*.md"))
    paths += sorted((root / "docs").glob("*.txt"))
    paths += sorted((root / "examples").glob("*.json"))
    paths += sorted((root / "examples").glob("*.png"))
    return [path for path in paths if path.is_file() and "__pycache__" not in path.parts]


def copy_sources(destination, root=PROJECT_ROOT, developer=False):
    paths = portable_source_files(root)
    if developer:
        paths += sorted((root / "tests").rglob("*.py"))
        paths += sorted((root / "scripts").glob("*.py"))
        paths += sorted((root / "packaging").glob("*"))
    for path in paths:
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Source symlink escapes project: {path}")
        target = destination / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def pe_machine(path: Path) -> int:
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError(f"Not a Windows PE file: {path}")
        stream.seek(0x3C)
        raw = stream.read(4)
        if len(raw) != 4:
            raise ValueError(f"Truncated PE header: {path}")
        stream.seek(struct.unpack("<I", raw)[0])
        if stream.read(4) != b"PE\0\0":
            raise ValueError(f"Invalid PE signature: {path}")
        raw = stream.read(2)
        if len(raw) != 2:
            raise ValueError(f"Truncated PE machine type: {path}")
        return struct.unpack("<H", raw)[0]


def copy_windows_runtime(source: Path, target: Path):
    def ignored(directory, names):
        excluded = {"__pycache__"} & set(names)
        # uv on a non-Windows host creates a host-only `python` alias pointing to a
        # POSIX-style python3.12 name. Windows uses the actual python.exe payload.
        if Path(directory) == source and "python" in names and (source / "python").is_symlink():
            excluded.add("python")
        return excluded

    shutil.copytree(source, target, ignore=ignored)


def inspect_windows_binaries(runtime: Path):
    ancillary = {
        "Lib/site-packages/pip/_vendor/distlib/t32.exe": 0x14C,
        "Lib/site-packages/pip/_vendor/distlib/w32.exe": 0x14C,
        "Lib/site-packages/pip/_vendor/distlib/t64-arm.exe": 0xAA64,
        "Lib/site-packages/pip/_vendor/distlib/w64-arm.exe": 0xAA64,
    }
    x64_count = 0
    helpers = {}
    for path in runtime.rglob("*"):
        if path.suffix.lower() not in (".exe", ".dll", ".pyd"):
            continue
        relative = path.relative_to(runtime).as_posix()
        machine = pe_machine(path)
        if machine == 0x8664:
            x64_count += 1
        elif ancillary.get(relative) == machine:
            # Official CPython's pip includes installer templates for other targets.
            # They are not the interpreter, Qt plugins, or application extensions.
            helpers[relative] = hex(machine)
        else:
            raise ValueError(f"Not an x64 Windows application binary: {relative}")
    return {
        "windows_x64_binary_count": x64_count,
        "upstream_pip_ancillary_launcher_templates": helpers,
    }


def normalized_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def inspect_runtime_distributions(site: Path, lock_path: Path):
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    locked = {
        normalized_distribution_name(package["name"]): package["version"]
        for package in lock.get("package", [])
    }
    missing_lock = RUNTIME_DISTRIBUTIONS - locked.keys()
    if missing_lock:
        raise ValueError(f"Runtime dependency missing from uv.lock: {sorted(missing_lock)}")
    wheels = {}
    distributions = {}
    for info in sorted(site.glob("*.dist-info")):
        metadata = Parser().parsestr((info / "METADATA").read_text(encoding="utf-8"))
        if not metadata.get("Name") or not metadata.get("Version"):
            raise ValueError(f"Missing distribution identity/version: {info.name}")
        name = normalized_distribution_name(metadata["Name"])
        if name in distributions:
            raise ValueError(f"Duplicate runtime distribution: {name}")
        if name not in RUNTIME_DISTRIBUTIONS and name != "pip":
            raise ValueError(f"Unexpected runtime distribution: {name}")
        if name != "pip" and metadata["Version"] != locked[name]:
            raise ValueError(f"Runtime distribution does not match uv.lock: {name}")
        wheel = (info / "WHEEL").read_text(encoding="utf-8")
        tags = [
            line.removeprefix("Tag: ").strip()
            for line in wheel.splitlines()
            if line.startswith("Tag: ")
        ]
        if not tags or any(
            not (tag.endswith("-win_amd64") or tag.endswith("-none-any")) for tag in tags
        ):
            raise ValueError(f"Incompatible wheel tags: {info.name}: {tags}")
        wheels[info.name] = tags
        distributions[name] = metadata["Version"]
    missing = RUNTIME_DISTRIBUTIONS - distributions.keys()
    if missing:
        raise ValueError(f"Missing required runtime distributions: {sorted(missing)}")
    return {
        "wheels": wheels,
        "locked_runtime_distributions": {
            name: value for name, value in distributions.items() if name != "pip"
        },
        "interpreter_bundled_distributions": (
            {"pip": distributions["pip"]} if "pip" in distributions else {}
        ),
    }


def verify_no_vendor_drivers(runtime: Path):
    vendor_files = [
        str(path.relative_to(runtime))
        for path in runtime.rglob("*")
        if path.is_file() and path.name.lower() in VENDOR_DRIVER_FILENAMES
    ]
    if vendor_files:
        raise ValueError(f"Vendor NI/VISA drivers must not be bundled: {vendor_files}")


def validate_windows_layout(root):
    runtime = root / "runtime"
    site = runtime / "Lib/site-packages"
    required = [
        runtime / "python.exe",
        runtime / "pythonw.exe",
        runtime / "python312.dll",
        runtime / "vcruntime140.dll",
        runtime / "LICENSE.txt",
        site / "PySide6/QtCore.pyd",
        site / "PySide6/QtWidgets.pyd",
        site / "PySide6/plugins/platforms/qwindows.dll",
        site / "pyvisa/__init__.py",
        root / "app/ni-only-requirements.txt",
        root / "tools/install_ni_only.py",
        site / "numpy/__init__.py",
        site / "pyqtgraph/__init__.py",
        root / "tools/launch.py",
        root / "tools/verify_bundle.py",
        root / "app/src/keithley6517a/cli.py",
        root / "app/uv.lock",
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"Missing portable bundle files: {missing}")
    verify_no_vendor_drivers(runtime)
    binaries = inspect_windows_binaries(runtime)
    dependencies = inspect_runtime_distributions(site, root / "app/uv.lock")
    return {
        "status": "passed",
        "scope": "PE architecture, wheel tags, required files",
        **binaries,
        **dependencies,
        "vendor_drivers_included": False,
        "ni4882_only_backend": "optional user-installed @py extension; NI-488.2 required",
        "ni_only_extension_bundled": False,
        "hardware_verified": False,
    }


def write_optional_ni_requirements(lock_path: Path, target: Path):
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    expected = {"gpib-ctypes": "0.3.0", "pyvisa-py": "0.8.1"}
    lines = ["# Optional user-installed extension only; not bundled with the base program."]
    for name, version in expected.items():
        records = [p for p in lock.get("package", []) if p["name"] == name]
        if len(records) != 1 or records[0]["version"] != version:
            raise ValueError(f"Missing pinned optional NI-only package: {name}")
        hashes = sorted(
            {
                wheel["hash"]
                for wheel in records[0].get("wheels", [])
                if wheel["url"].endswith("-none-any.whl")
                and re.fullmatch(r"sha256:[0-9a-f]{64}", wheel["hash"])
            }
        )
        if not hashes:
            raise ValueError(f"No hash-verified pure Python optional wheel: {name}")
        lines.append(f"{name}=={version} " + " ".join("--hash=" + value for value in hashes))
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def third_party_notices(root):
    """Retain upstream notices verbatim; provide an index without guessing licenses."""
    notices = {
        "CPython": {"version": PYTHON_VERSION, "license_files": ["runtime/LICENSE.txt"]},
        "distributions": [],
    }
    site = root / "runtime/Lib/site-packages"
    for info in sorted(site.glob("*.dist-info")):
        metadata = Parser().parsestr((info / "METADATA").read_text(encoding="utf-8"))
        files = [
            path.relative_to(root).as_posix()
            for path in sorted(info.rglob("*"))
            if path.is_file()
            and (
                "licenses" in path.relative_to(info).parts
                or any(token in path.name.lower() for token in ("license", "copying", "notice"))
            )
        ]
        notices["distributions"].append(
            {
                "name": metadata.get("Name"),
                "version": metadata.get("Version"),
                "license_expression": metadata.get("License-Expression"),
                "license_metadata": metadata.get("License"),
                "license_files": files,
                "metadata_file": (info / "METADATA").relative_to(root).as_posix(),
            }
        )
    (root / "THIRD_PARTY_NOTICES.json").write_text(
        json.dumps(notices, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return notices


def write_manifest(root, *, release_version, native_verified, layout=None):
    files = {
        path.relative_to(root).as_posix(): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "bundle_manifest.json"
    }
    manifest = dict(
        schema_version=1,
        version=release_version,
        files=files,
        native_windows_execution_verified=native_verified,
        hardware_verified=False,
    )
    if layout is not None:
        manifest["layout_validation"] = layout
    (root / "bundle_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def archive(root: Path, output: Path):
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing release: {output}")
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as stream:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                stream.write(path, (Path(root.name) / path.relative_to(root)).as_posix())
    (output.with_suffix(output.suffix + ".sha256")).write_text(
        f"{sha256(output)}  {output.name}\n", encoding="ascii"
    )


def install_windows_payload(cache: Path, uv: str):
    environment = os.environ.copy()
    environment.setdefault("UV_CACHE_DIR", str(cache / "uv"))
    python_root = cache / "windows-python"
    run(
        [
            uv,
            "python",
            "install",
            PYTHON_KEY,
            "--install-dir",
            python_root,
            "--no-bin",
            "--no-registry",
        ],
        environment=environment,
    )
    runtime = python_root / PYTHON_KEY
    if not (runtime / "python.exe").is_file():
        raise ValueError("uv did not produce the requested Windows CPython installation")
    requirements = cache / "requirements-runtime.txt"
    run(
        [
            uv,
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--no-header",
            "--no-annotate",
            "--format",
            "requirements.txt",
            "--output-file",
            requirements,
        ],
        environment=environment,
    )
    site = cache / "windows-site-packages"
    # Reuse the same pinned payload; uv checks dependency hashes and only uses wheels.
    run(
        [
            uv,
            "pip",
            "install",
            "--python-platform",
            "x86_64-pc-windows-msvc",
            "--python-version",
            "3.12",
            "--target",
            site,
            "--require-hashes",
            "--only-binary",
            ":all:",
            "--exact",
            "--link-mode",
            "copy",
            "-r",
            requirements,
        ],
        environment=environment,
    )
    catalog = json.loads(
        run(
            [
                uv,
                "python",
                "list",
                PYTHON_KEY,
                "--all-platforms",
                "--all-arches",
                "--only-downloads",
                "--show-urls",
                "--output-format",
                "json",
            ],
            environment=environment,
        ).stdout
    )
    provenance = next(item for item in catalog if item["key"] == PYTHON_KEY)
    return runtime, site, requirements, provenance


def build(output: Path, cache: Path, uv="uv", *, native_smoke=False, payload=None):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cache = cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    release_version = version()
    stem = f"6517A-USB-GPIB-Trial-{release_version}"
    portable_zip = output / f"{stem}-Windows-x64.zip"
    source_zip = output / f"{stem}-Source.zip"
    if portable_zip.exists() or source_zip.exists():
        raise FileExistsError("Use a new output directory; existing release ZIPs are preserved")
    if native_smoke and sys.platform != "win32":
        raise ValueError("--native-smoke requires an actual Windows host")
    runtime, site, requirements, provenance = payload or install_windows_payload(cache, uv)
    with tempfile.TemporaryDirectory(prefix="6517a-package-", dir=output) as temporary:
        working = Path(temporary)
        portable = working / f"{stem}-Windows-x64"
        portable.mkdir()
        copy_sources(portable / "app")
        write_optional_ni_requirements(
            PROJECT_ROOT / "uv.lock", portable / "app/ni-only-requirements.txt"
        )
        copy_windows_runtime(runtime, portable / "runtime")
        shutil.copytree(
            site,
            portable / "runtime/Lib/site-packages",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "bin"),
        )
        # The cross-platform installer emits POSIX convenience wrappers. The application uses
        # python.exe plus source modules, so those host wrappers are deliberately not shipped.
        (portable / "tools").mkdir()
        for name in ("launch.py", "verify_bundle.py", "smoke.py", "install_ni_only.py"):
            shutil.copy2(PROJECT_ROOT / "packaging" / name, portable / "tools" / name)
        for name in LAUNCHERS:
            content = (PROJECT_ROOT / "packaging" / name).read_text(encoding="ascii")
            (portable / name).write_bytes(
                content.replace("\r\n", "\n").replace("\n", "\r\n").encode("ascii")
            )
        first_read = PROJECT_ROOT / "docs/READ_FIRST_KO.txt"
        if not first_read.is_file():
            raise FileNotFoundError("docs/READ_FIRST_KO.txt is required for the user trial bundle")
        shutil.copy2(first_read, portable / "READ_FIRST_KO.txt")
        (portable / "configs").mkdir()
        shutil.copy2(
            PROJECT_ROOT / "examples/low_voltage_template.json",
            portable / "configs/low_voltage_template.json",
        )
        shutil.copy2(requirements, portable / "runtime-requirements.txt")
        release = dict(
            schema_version=1,
            version=release_version,
            kind="Windows x64 portable trial",
            built_at=datetime.now(UTC).isoformat(),
            build_host=sys.platform,
            python_version=PYTHON_VERSION,
            python_download=provenance,
            dependency_integrity="uv.lock SHA-256 requirements; binary Windows wheels only",
            native_windows_execution_verified=native_smoke,
            hardware_verified=False,
            default_mode="SIMULATION",
            automatic_output_enable=False,
            vendor_visa_included=False,
        )
        (portable / "release.json").write_text(
            json.dumps(release, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        third_party_notices(portable)
        layout = validate_windows_layout(portable)
        if native_smoke:
            run(
                [portable / "runtime/python.exe", "-I", portable / "tools/smoke.py"],
                directory=portable,
            )
            shutil.rmtree(portable / "native-smoke-results", ignore_errors=True)
        write_manifest(
            portable, release_version=release_version, native_verified=native_smoke, layout=layout
        )
        # Verify exactly what will be archived using the same helper shipped to testers.
        run([sys.executable, portable / "tools/verify_bundle.py", portable])
        archive(portable, portable_zip)
        source = working / f"{stem}-Source"
        source.mkdir()
        copy_sources(source, developer=True)
        write_optional_ni_requirements(
            PROJECT_ROOT / "uv.lock", source / "ni-only-requirements.txt"
        )
        shutil.copy2(requirements, source / "runtime-requirements.txt")
        write_manifest(source, release_version=release_version, native_verified=False)
        archive(source, source_zip)
    result = {
        "version": release_version,
        "portable": str(portable_zip),
        "source": str(source_zip),
        "native_windows_execution_verified": native_smoke,
        "hardware_verified": False,
        "layout_validation": layout,
    }
    (output / f"{stem}-build-report.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "dist")
    parser.add_argument("--cache", type=Path, default=PROJECT_ROOT / "build/package-cache")
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--native-smoke", action="store_true")
    args = parser.parse_args(argv)
    print(
        json.dumps(
            build(args.output, args.cache, args.uv, native_smoke=args.native_smoke), indent=2
        )
    )


if __name__ == "__main__":
    main()
