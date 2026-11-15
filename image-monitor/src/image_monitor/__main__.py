import argparse
import json
from datetime import datetime
from pathlib import Path

from image_monitor.paths import destination, plan_folder
from image_monitor.validation import verify_image


def main() -> int:
    parser = argparse.ArgumentParser(description="Image monitor development and native-save probe")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="Preview a path without creating directories")
    plan.add_argument("--root", type=Path, required=True)
    plan.add_argument("--watch", required=True)
    plan.add_argument("--gallery", required=True)
    plan.add_argument("--post", required=True)
    plan.add_argument("--nickname", required=True)
    plan.add_argument("--ip-display")
    plan.add_argument("--first-seen", required=True, help="ISO timestamp with timezone")
    plan.add_argument("--published", help="ISO timestamp with timezone")
    plan.add_argument("--basis", choices=("published_at", "first_seen_at"), default="published_at")
    verify = commands.add_parser("verify", help="Inspect an existing completed local file")
    verify.add_argument("file", type=Path)
    verify.add_argument("--writer-finished", action="store_true", required=True)
    probe = commands.add_parser(
        "native-probe", help="Windows native-save test of one synthetic image"
    )
    probe.add_argument(
        "--work-root", type=Path, required=True, help="Short local disposable work path"
    )
    probe.add_argument("--browser", choices=("edge", "chrome"), default="edge")
    recovery = commands.add_parser(
        "native-recover", help="Clear shared pending state after manually closing its browser"
    )
    recovery.add_argument("--confirm-browser-closed", action="store_true", required=True)
    status = commands.add_parser("queue-status", help="Read a persisted queue without modifying it")
    status.add_argument("--db", type=Path, required=True)
    demo = commands.add_parser("queue-demo", help="Create a new synthetic queue; no collection")
    demo.add_argument("--db", type=Path, required=True, help="New database path; never overwritten")
    post_demo_parser = commands.add_parser(
        "post-demo", help="Inspect a synthetic post and persist its image jobs; no collection"
    )
    post_demo_parser.add_argument("--db", type=Path, required=True)
    site = commands.add_parser(
        "site-inspect", help="Read one public post DOM in an isolated browser; never save images"
    )
    site.add_argument("--work-root", type=Path, required=True)
    site.add_argument("--browser", choices=("edge", "chrome"), default="chrome")
    site.add_argument("--post-url", help="Public DCInside post URL; defaults to the design example")
    args = parser.parse_args()
    if args.command == "post-demo":
        from image_monitor.post_commands import post_demo

        try:
            output = post_demo(args.db)
        except Exception as error:
            parser.exit(2, f"Synthetic post inspection failed ({type(error).__name__}).\n")
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    if args.command == "site-inspect":
        from image_monitor.site_inspection import run_site_inspection, share_report

        try:
            options = {"url": args.post_url} if args.post_url else {}
            output = run_site_inspection(args.work_root, args.browser, **options)
        except KeyboardInterrupt:
            parser.exit(130, "Read-only inspection cancelled.\n")
        except Exception as error:
            parser.exit(2, f"Read-only inspection stopped ({type(error).__name__}).\n")
        print(json.dumps(share_report(output), ensure_ascii=False, indent=2))
        return 2 if output.get("status") == "inspection_failed" else 0
    if args.command in {"queue-status", "queue-demo"}:
        from image_monitor.queue_commands import queue_demo, queue_status

        try:
            output = (
                queue_status(args.db) if args.command == "queue-status" else queue_demo(args.db)
            )
        except Exception as error:
            parser.exit(2, f"Queue command failed ({type(error).__name__}).\n")
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    if args.command in {"native-probe", "native-recover"}:
        from image_monitor.native_probe import run_probe
        from image_monitor.native_state import run_recovery
        from image_monitor.native_ui import NativeUIError

        try:
            output = (
                run_probe(args.work_root, args.browser)
                if args.command == "native-probe"
                else run_recovery()
            )
        except NativeUIError as error:
            parser.exit(2, f"{error}\n")
        except KeyboardInterrupt:
            parser.exit(130, "Probe cancelled. Inspect the dedicated browser and report.\n")
        except Exception as error:
            parser.exit(2, f"Probe stopped ({type(error).__name__}); inspect the report.\n")
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    try:
        if args.command == "plan":
            result = plan_folder(
                watch_name=args.watch,
                gallery_id=args.gallery,
                post_id=args.post,
                nickname=args.nickname,
                ip_display=args.ip_display,
                first_seen_at=datetime.fromisoformat(args.first_seen),
                published_at=datetime.fromisoformat(args.published) if args.published else None,
                basis=args.basis,
            )
            output = result.to_dict() | {"destination": str(destination(args.root, result))}
        else:
            output = verify_image(args.file, writer_finished=args.writer_finished).to_dict()
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        parser.exit(2, f"{error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
