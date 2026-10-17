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
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(root / "packaging" / "windows.spec"),
        ],
        cwd=root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
