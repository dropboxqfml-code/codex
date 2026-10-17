"""Build the checked-in Windows spec; never cross-build an exe."""

import struct
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if sys.platform != "win32":
        print("Windows .exe 빌드는 Windows에서 실행하세요.", file=sys.stderr)
        return 1
    if struct.calcsize("P") != 8:
        print("Windows x64 Python이 필요합니다.", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(root / "packaging" / "windows.spec"),
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        check=False,
    )
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "pyinstaller.log").write_text(result.stdout, encoding="utf-8")
    print(result.stdout)
    if result.returncode:
        # Contains only build-tool output for public source/generated fixtures, never user scans.
        message = (
            result.stdout[-1500:].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        )
        print(f"::error title=PyInstaller build failed::{message}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
