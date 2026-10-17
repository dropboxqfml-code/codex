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
