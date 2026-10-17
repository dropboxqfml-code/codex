"""Frozen entry point. Normal launches use the unmodified application."""

import sys
from pathlib import Path

from image_duplicate_finder.__main__ import main

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--build-smoke-report":
        if len(sys.argv) != 3:
            raise SystemExit(2)
        from frozen_smoke import run

        # This diagnostic can only generate its own temporary images, never accept a search folder.
        raise SystemExit(run(Path(sys.argv[2])))
    raise SystemExit(main())
