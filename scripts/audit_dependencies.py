"""Build-time only: send public dependency names/versions to PyPI's advisory service."""

import json
import subprocess
import sys
from pathlib import Path

from packaging.requirements import Requirement


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    exported = subprocess.check_output(
        [
            "uv",
            "export",
            "--locked",
            "--all-groups",
            "--no-emit-project",
            "--no-hashes",
            "--no-annotate",
            "--no-header",
        ],
        cwd=root,
        text=True,
    )
    versions = set()
    for line in exported.splitlines():
        if line.strip() and not line.startswith("#"):
            requirement = Requirement(line)
            # Include Windows-only pins even when the audit itself runs on Linux.
            versions.add(requirement.name + str(requirement.specifier))
    requirements = reports / "audit-requirements.txt"
    requirements.write_text("\n".join(sorted(versions)) + "\n", encoding="utf-8")
    report = reports / "dependency-audit.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "--no-deps",
            "--disable-pip",
            "--strict",
            "--vulnerability-service",
            "pypi",
            "--cache-dir",
            str(reports / "audit-cache"),
            "-r",
            str(requirements),
            "--format",
            "json",
            "--output",
            str(report),
        ],
        cwd=root,
        check=False,
    )
    if not report.exists():
        return result.returncode or 1
    data = json.loads(report.read_text(encoding="utf-8"))
    if any(d.get("skip_reason") for d in data.get("dependencies", [])):
        print("Audit was incomplete; do not treat it as passed.", file=sys.stderr)
        return 1
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
