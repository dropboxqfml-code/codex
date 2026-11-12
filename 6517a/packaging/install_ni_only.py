"""Explicit, hash-pinned optional NI-only Python extension installer.

The base program does not bundle these packages. No driver, registry, device,
or output operation is performed here. NI-488.2 must already be installed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from email.parser import Parser
from pathlib import Path, PurePosixPath

VERSIONS = {"gpib-ctypes": "0.3.0", "pyvisa-py": "0.8.1"}
ENTRIES = ("gpib_ctypes/__init__.py", "gpib_ctypes/gpib/gpib.py", "pyvisa_py/__init__.py")
MARKER = "ni_only_extension.json"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def extension_directory(root):
    return root / "extensions/ni4882"


def payload_files(directory):
    return {
        p.relative_to(directory).as_posix(): p
        for p in directory.rglob("*")
        if p.is_file() and p.name != MARKER and "__pycache__" not in p.parts
    }


def inspect_payload(directory):
    versions = {}
    for info in directory.glob("*.dist-info"):
        metadata = Parser().parsestr((info / "METADATA").read_text(encoding="utf-8"))
        name = re.sub(r"[-_.]+", "-", metadata.get("Name", "")).lower()
        if name in versions or name not in VERSIONS:
            raise ValueError("Unexpected or duplicate optional distribution")
        versions[name] = metadata.get("Version")
    if versions != VERSIONS or not all((directory / name).is_file() for name in ENTRIES):
        raise ValueError("The optional NI-only extension is incomplete or has wrong versions")
    if any(
        path.suffix.lower() in (".dll", ".exe", ".pyd", ".sys")
        for path in payload_files(directory).values()
    ):
        raise ValueError(
            "The NI-only extension must contain pure Python wheels, not driver binaries"
        )
    return versions


def installed_extension(root):
    directory = extension_directory(root)
    if not directory.exists():
        return None
    if not directory.resolve().is_relative_to(root.resolve()):
        raise ValueError("NI-only extension must stay inside this program folder")
    marker = directory / MARKER
    if not marker.is_file():
        raise ValueError("An incomplete NI-only extension exists; it has not been activated")
    data = json.loads(marker.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        raise ValueError("Invalid NI-only extension completion manifest")
    requirement = root / "app/ni-only-requirements.txt"
    if (
        data.get("schema_version") != 1
        or data.get("versions") != VERSIONS
        or data.get("requirements_sha256") != digest(requirement)
    ):
        raise ValueError("NI-only extension metadata does not match this program")
    files = payload_files(directory)
    if set(data.get("files", {})) != set(files):
        raise ValueError("NI-only extension file set changed")
    for name, expected in data["files"].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
            raise ValueError("Invalid extension manifest path")
        path = files[name]
        if not path.resolve().is_relative_to(directory.resolve()) or digest(path) != expected:
            raise ValueError("NI-only extension integrity check failed")
    inspect_payload(directory)
    return directory


def pip_arguments(interpreter, requirements, target):
    return [
        str(interpreter),
        "-I",
        "-B",
        "-m",
        "pip",
        "--isolated",
        "--disable-pip-version-check",
        "install",
        "--index-url",
        "https://pypi.org/simple",
        "--require-hashes",
        "--only-binary",
        ":all:",
        "--no-deps",
        "--no-compile",
        "--target",
        str(target),
        "--requirement",
        str(requirements),
    ]


def install(root, *, runner=subprocess.run):
    root = root.resolve()
    directory = extension_directory(root)
    if directory.exists():
        installed_extension(root)  # Reject an incomplete installation; preserve all existing files.
        return directory
    requirements = root / "app/ni-only-requirements.txt"
    if not requirements.is_file():
        raise ValueError("Pinned NI-only requirements are missing from this bundle")
    parent = directory.parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ni-only-staging-", dir=parent) as temporary:
        payload = Path(temporary) / "payload"
        runner(pip_arguments(Path(sys.executable), requirements, payload), check=True)
        versions = inspect_payload(payload)
        files = {name: digest(path) for name, path in payload_files(payload).items()}
        directory.mkdir()  # Exclusive creation: never overwrite the user's extension folder.
        shutil.copytree(payload, directory, dirs_exist_ok=True)
        marker = dict(
            schema_version=1,
            versions=versions,
            requirements_sha256=digest(requirements),
            files=files,
            license_notice="gpib-ctypes is GPLv2; upstream license and Python source retained",
            driver_included=False,
            hardware_verified=False,
        )
        (directory / MARKER).write_text(json.dumps(marker, indent=2), encoding="utf-8")
    installed_extension(root)
    return directory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes", action="store_true", help="Explicitly confirm optional installation"
    )
    args = parser.parse_args(argv)
    print("Optional NI-only extension: PyVISA-py 0.8.1 and gpib-ctypes 0.3.0.")
    print("gpib-ctypes is GPLv2. Its license and Python source are retained in the extension.")
    print("Review licensing before redistributing an application combined with this extension.")
    print(
        "Internet access to PyPI is required. NI-488.2 is still required; no driver is installed."
    )
    if (
        not args.yes
        and input("Type INSTALL to install the optional extension: ").strip() != "INSTALL"
    ):
        print("Cancelled. The standard NI-VISA program is unchanged.")
        return 2
    try:
        path = install(Path(__file__).resolve().parents[1])
        print(f"Installed: {path}\nClose and restart the program, then explicitly select @py.")
        return 0
    except Exception as exc:
        print(f"Optional extension was not activated: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(
            "Existing extension files were preserved. The standard NI-VISA mode remains available.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
