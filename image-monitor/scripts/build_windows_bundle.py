"""Build a versioned Windows ZIP with one user TXT inside the project folder."""

import argparse
import re
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Check the expected public version before packaging")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    repo = project.parent
    version_file = "src/image_monitor/VERSION"
    version = (project / version_file).read_text(encoding="ascii").strip()
    number = r"(?:0|[1-9][0-9]*)"
    stage = r"(?:-(?:alpha|beta|rc)\.[1-9][0-9]*)?"
    if not re.fullmatch(rf"{number}\.{number}\.{number}{stage}", version):
        parser.error("VERSION must contain a release such as 1.0.0 or 0.4.0-alpha.1")
    if args.version is not None and args.version != version:
        parser.error(f"expected public version {version}")
    required = {
        version_file,
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
    }
    tracked = (
        subprocess.check_output(["git", "ls-files", "-z", "--", project.name], cwd=repo)
        .decode()
        .split("\0")
    )
    sources = []
    for name in filter(None, tracked):
        relative = Path(name).relative_to(project.name)
        if relative.as_posix() in required or relative.parts[0] in {
            "src",
            "tests",
            "docs",
            "scripts",
        }:
            if "__pycache__" in relative.parts or relative.name.startswith("WINDOWS_TEST_RESULT-"):
                raise ValueError("Runtime data must not be packaged")
            sources.append((repo / name, name))
    included = {source.relative_to(project).as_posix() for source, _ in sources}
    if not required <= included:
        raise ValueError("Stage all required project files before building")
    guide_name = f"{project.name}/WINDOWS_TEST_GUIDE.txt"
    guides = [name for path, name in sources if path.name.casefold() == "windows_test_guide.txt"]
    if guides != [guide_name]:
        raise ValueError("The ZIP must contain one guide inside the project folder")
    for name in required:
        if name.endswith(".cmd"):
            data = (project / name).read_bytes()
            data.decode("ascii")
            if not data.count(b"\r\n") or b"\n" in data.replace(b"\r\n", b""):
                raise ValueError("Windows launchers must use CRLF")
    guide = (project / "WINDOWS_TEST_GUIDE.txt").read_bytes()
    if not guide.startswith(b"\xef\xbb\xbf") or len(guide.decode("utf-8-sig").splitlines()) < 3:
        raise ValueError("The user TXT must have a UTF-8 BOM and readable lines")
    if not guide.count(b"\r\n") or b"\n" in guide.replace(b"\r\n", b""):
        raise ValueError("The user TXT must use CRLF")
    destination = repo / "downloads" / f"image-monitor-windows-test-{version}.zip"
    destination.parent.mkdir(exist_ok=True)
    with ZipFile(destination, "x", ZIP_DEFLATED, compresslevel=9) as archive:
        for source, name in sorted(sources):
            archive.write(source, name)
    with ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP verification failed")
        if archive.read(guide_name) != guide:
            raise ValueError("The ZIP must contain one matching guide inside the project folder")
    print(destination)


if __name__ == "__main__":
    main()
