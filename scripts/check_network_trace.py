"""Check the isolated Linux probe trace, with its two intentional denied controls."""

import re
import sys
from pathlib import Path


def main() -> int:
    text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    internet = [line for line in text.splitlines() if re.search(r"socket\(AF_INET6?,", line)]
    if len(internet) != 2 or not all("EPERM" in line for line in internet):
        raise RuntimeError("Unexpected native Internet socket attempt in the offline probe")
    if re.search(r"(?:connect|sendto|sendmsg)\(.*AF_INET", text):
        raise RuntimeError("Native Internet connect/send was attempted")
    executions = [line for line in text.splitlines() if "execve(" in line or "execveat(" in line]
    if len(executions) != 1:
        raise RuntimeError("Unexpected additional process execution in the offline probe")
    print("PASS: two denied socket controls only; no Internet connect/send or child exec observed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
