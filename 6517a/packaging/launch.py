"""Portable launch boundary. GUI starts in SIMULATION; no stored run is resumed."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path


def bundle_root() -> Path:
    return Path(__file__).resolve().parents[1]


def configure_qt_environment(root: Path):
    plugins = root / "runtime/Lib/site-packages/PySide6/plugins"
    os.environ["QT_PLUGIN_PATH"] = str(plugins)
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugins / "platforms")
    os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"


def configure_optional_extension(root: Path):
    """Activate only a complete local extension. Never install or access a device here."""
    helper = root / "tools/install_ni_only.py"
    if not helper.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_6517a_optional_extension", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        directory = module.installed_extension(root)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"NI-only extension inactive: {exc}", file=sys.stderr)
        return None
    if directory is not None:
        sys.path.insert(0, str(directory))
    return directory


def arguments(action: str, supplied: list[str], root: Path) -> list[str]:
    if action == "simulate":
        if supplied:
            raise ValueError("Use Run-CLI.cmd for custom simulation options")
        return [
            "simulate",
            "--fast",
            "--config",
            str(root / "app/examples/simulation_config.json"),
            "--output",
            str(root / "results"),
        ]
    if action in {"diagnose", "confirm-off"}:
        if len(supplied) > 2:
            raise ValueError("Check-Connection.cmd accepts resource and optional VISA backend")
        result = ["diagnose", "--report-dir", str(root / "diagnostics")]
        if action == "confirm-off":
            if not supplied:
                raise ValueError("Output OFF check requires a selected GPIB resource")
            result.append("--confirm-off")
        if supplied:
            if not supplied[0].upper().startswith("GPIB"):
                raise ValueError("Select an explicit GPIB VISA resource")
            result += ["--resource", supplied[0]]
        if len(supplied) == 2:
            result += ["--backend", supplied[1]]
        return result
    if action == "cli":
        return supplied
    raise ValueError(f"Unknown launcher action: {action}")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        raise ValueError("Choose gui, simulate, diagnose, confirm-off, or cli")
    root = bundle_root()
    os.chdir(root)
    sys.path.insert(0, str(root / "app/src"))
    configure_optional_extension(root)
    if argv[0] == "gui":
        if len(argv) != 1:
            raise ValueError("GUI launcher accepts no configuration or run arguments")
        configure_qt_environment(root)
        if sys.platform == "win32":
            os.environ["QT_QPA_PLATFORM"] = "windows"
        from keithley6517a.ui.main_window import main as gui_main

        return gui_main()
    from keithley6517a.cli import main as cli_main

    return cli_main(arguments(argv[0], argv[1:], root))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        root = bundle_root()
        directory = root / "diagnostics"
        directory.mkdir(exist_ok=True)
        path = directory / (
            "launcher-error-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + f"-{os.getpid()}.json"
        )
        path.write_text(
            json.dumps(
                {"status": "failed", "traceback": traceback.format_exc()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None, f"Start failed. See:\n{path}", "6517A trial program", 0x10
            )
        traceback.print_exc()
        raise SystemExit(2) from None
