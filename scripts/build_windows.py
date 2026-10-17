"""Run with the project's Python environment on Windows; never cross-build an exe."""

import subprocess
import sys
from pathlib import Path


def main() -> int:
    if sys.platform != "win32":
        print("Windows .exe 빌드는 Windows에서 실행하세요.", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parents[1]
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--windowed",
            "--onedir",
            "--name",
            "Image Duplicate Finder",
            str(root / "src" / "image_duplicate_finder" / "__main__.py"),
        ],
        cwd=root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
