"""Write actual test/build outcomes to the GitHub job summary, including failures."""

import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    lines = ["## Windows test and packaging results", ""]
    junit = root / "reports" / "pytest.xml"
    if junit.exists():
        tree = ET.parse(junit)
        for suite in tree.findall(".//testsuite"):
            lines.append(
                f"Tests: **{suite.get('tests')}**; failures: **{suite.get('failures')}**; "
                f"errors: **{suite.get('errors')}**; skipped: **{suite.get('skipped')}**."
            )
        for case in tree.findall(".//testcase"):
            for tag in ("failure", "error", "skipped"):
                problem = case.find(tag)
                if problem is not None:
                    lines.extend(
                        [
                            "",
                            f"### {tag}: {case.get('classname')}.{case.get('name')}",
                            "",
                            "````text",
                            (problem.text or problem.get("message", ""))[-16000:],
                            "````",
                        ]
                    )
    else:
        lines.append("Test report unavailable: tests did not run or did not complete.")
    smoke = root / "reports" / "frozen-smoke.json"
    lines.extend(["", "### Frozen executable smoke", ""])
    if smoke.exists():
        data = json.loads(smoke.read_text(encoding="utf-8"))
        lines.extend(["````json", json.dumps(data, ensure_ascii=False, indent=2), "````"])
    else:
        lines.append(
            "Not completed; no successful frozen Windows executable validation is claimed."
        )
    audit = root / "reports" / "dependency-audit.json"
    if audit.exists():
        dependencies = json.loads(audit.read_text(encoding="utf-8")).get("dependencies", [])
        lines.extend(
            [
                "",
                "### Dependency advisory lookup (PyPI)",
                "",
                f"Versions: {len(dependencies)}; known advisories: "
                f"{sum(len(d.get('vulns', [])) for d in dependencies)}; skipped: "
                f"{sum(bool(d.get('skip_reason')) for d in dependencies)}.",
            ]
        )
    inventory = root / "reports" / "bundle-inventory.json"
    if inventory.exists():
        data = json.loads(inventory.read_text(encoding="utf-8"))
        suspicious = [
            name
            for name in data["native_files"]
            if any(
                token in name.lower()
                for token in ("qt6network", "qt6webengine", "qtwebengineprocess")
            )
        ]
        lines.extend(
            [
                "",
                "### Bundle inventory",
                "",
                f"Python modules: {len(data['python_modules'])}; "
                f"native files: {len(data['native_files'])}.",
                f"Unexpected network Qt files: {suspicious}.",
            ]
        )
    lines.extend(
        [
            "",
            "Manual Windows 10/11 acceptance, no-Python PC, DPI, Defender, "
            "and restoration: **not run**.",
        ]
    )
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


if __name__ == "__main__":
    main()
