import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from image_monitor import PUBLIC_VERSION
from image_monitor.paths import destination, plan_folder
from image_monitor.validation import verify_image


def main() -> int:
    parser = argparse.ArgumentParser(description="Image monitor development and native-save probe")
    parser.add_argument("--version", action="version", version=f"Image Monitor {PUBLIC_VERSION}")
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
    watch_demo_parser = commands.add_parser(
        "watch-demo", help="Create a local synthetic watch demo; no network or native UI"
    )
    watch_demo_parser.add_argument("--db", type=Path, required=True)
    monitor = commands.add_parser(
        "monitor", help="Open the local list-monitoring screen; start watching explicitly"
    )
    monitor.add_argument("--work-root", type=Path, required=True)
    monitor.add_argument(
        "--save-root", type=Path, help="Read existing monitor-saved images for local preview"
    )
    monitor.add_argument(
        "--batch-root", type=Path, help="Also read completed batch images; requires --save-root"
    )
    resume_once = commands.add_parser(
        "monitor-resume-once", help="Resume one outstanding monitor detail check and exit"
    )
    resume_once.add_argument("--work-root", type=Path, required=True)
    diagnosis = commands.add_parser(
        "monitor-diagnosis",
        help="Read the stored list-profile diagnosis and latest monitor review from local records",
    )
    diagnosis.add_argument("--work-root", type=Path, required=True)
    watch_test = commands.add_parser(
        "watch-test", help="Run a bounded public-list discovery trial; never save images"
    )
    watch_test.add_argument("--work-root", type=Path, required=True)
    watch_test.add_argument("--browser", choices=("chrome", "edge"), default="chrome")
    for name, description in (
        ("candidate-test", "Inspect at most two stored candidates; never save images"),
        ("watch-detail", "Inspect one new candidate from the latest verified watch trial"),
    ):
        candidate_test = commands.add_parser(name, help=description)
        candidate_test.add_argument("--work-root", type=Path, required=True)
        candidate_test.add_argument("--browser", choices=("chrome", "edge"), default="chrome")
    for name, description in (
        ("candidate-save-test", "Review and natively save one previously inspected candidate"),
        ("monitor-save-test", "Natively save one inspected candidate from the local monitor"),
    ):
        candidate_save = commands.add_parser(name, help=description)
        candidate_save.add_argument("--watch-root", type=Path, required=True)
        candidate_save.add_argument("--work-root", type=Path, required=True)
        candidate_save.add_argument("--browser", choices=("chrome",), default="chrome")
    for name, description in (
        ("candidate-finish", "Verify completed candidate files and resolve a closed save"),
        ("monitor-finish", "Verify completed monitor-candidate files without downloading again"),
    ):
        candidate_finish = commands.add_parser(name, help=description)
        candidate_finish.add_argument("--watch-root", type=Path, required=True)
        candidate_finish.add_argument("--work-root", type=Path, required=True)
    for name, description in (
        (
            "monitor-save-batch",
            "Save at most two inspected monitor candidates, skipping completed work",
        ),
        ("monitor-save-one", "Run one native save requested by the local monitor"),
        ("auto-collect-once", "Inspect stored monitor candidates and automatically save one post"),
        ("auto-monitor", "Repeatedly check the list and collect eligible post images"),
        ("monitor-batch-finish", "Reconcile completed monitor batch files without saving again"),
        ("watch-images", "Check recent posts for body images and offer to save one post in Chrome"),
        ("watch-images-check", "Verify the last completed recent-post image save on disk"),
        ("watch-images-finish", "Verify a pending recent-post save using completed local files"),
    ):
        monitor_batch = commands.add_parser(name, help=description)
        monitor_batch.add_argument("--watch-root", type=Path, required=True)
        monitor_batch.add_argument("--legacy-root", type=Path, required=True)
        monitor_batch.add_argument("--work-root", type=Path, required=True)
        if name == "watch-images":
            monitor_batch.add_argument("--browser", choices=("chrome",), default="chrome")
        if name == "auto-monitor":
            monitor_batch.add_argument(
                "--max-cycles", type=int, help="Stop after this many cycles (default: continuous)"
            )
    site = commands.add_parser(
        "site-inspect", help="Read one public post DOM in an isolated browser; never save images"
    )
    site.add_argument("--work-root", type=Path, required=True)
    site.add_argument("--browser", choices=("edge", "chrome"), default="chrome")
    site.add_argument("--post-url", help="Public DCInside post URL; defaults to the design example")
    list_inspection = commands.add_parser(
        "list-inspect", help="Read a public search list in a headless browser; never save images"
    )
    list_inspection.add_argument("--work-root", type=Path, required=True)
    list_inspection.add_argument("--browser", choices=("chrome", "edge"), default="chrome")
    list_inspection.add_argument(
        "--list-url", help="Public DCInside search-list URL; defaults to the design example"
    )
    save_post = commands.add_parser(
        "save-post", help="Review and natively save images from one public post in Chrome"
    )
    save_post.add_argument("--work-root", type=Path, required=True)
    save_post.add_argument("--browser", choices=("chrome",), default="chrome")
    save_post.add_argument(
        "--resume-preinput",
        action="store_true",
        help="Resume only a verified previous failure before native input began",
    )
    save_post.add_argument(
        "--post-url", help="Public DCInside post URL; defaults to the reviewed design example"
    )
    args = parser.parse_args()
    if args.command == "auto-monitor":
        if args.max_cycles is not None and args.max_cycles < 1:
            parser.error("--max-cycles must be at least 1")
        from image_monitor.auto_monitor_cli import run_auto_monitor_cli

        return run_auto_monitor_cli(
            args.watch_root, args.legacy_root, args.work_root, args.max_cycles
        )
    if args.command == "auto-collect-once":
        from image_monitor.monitor_collect import monitor_collect_exit_code, run_monitor_collect

        try:
            report = run_monitor_collect(args.watch_root, args.legacy_root, args.work_root)
        except KeyboardInterrupt:
            parser.exit(130, "Automatic collection cancelled.\n")
        except Exception as error:
            parser.exit(2, f"Automatic collection stopped ({type(error).__name__}).\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return monitor_collect_exit_code(report)
    if args.command == "monitor-resume-once":
        from image_monitor.monitor_resume_once import (
            monitor_resume_once_exit_code,
            run_monitor_resume_once,
        )

        report = run_monitor_resume_once(args.work_root)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return monitor_resume_once_exit_code(report)
    if args.command == "monitor-diagnosis":
        from image_monitor.artifact_files import _plain_path
        from image_monitor.monitor_diagnosis import read_latest_list_diagnosis
        from image_monitor.monitor_list_review import previous_list_review
        from image_monitor.monitor_list_review_text import describe_list_review
        from image_monitor.queue import QueueStore
        from image_monitor.watch_images_check import _read_mode
        from image_monitor.watch_store import MONITOR_SCOPE

        report = {
            "program_version": PUBLIC_VERSION,
            "list_diagnosis": None,
            "previous_list_review": None,
        }
        try:
            if args.work_root.anchor.startswith(("//", "\\\\")):
                raise ValueError("Use a local watch directory")
            database = _plain_path(args.work_root / "watch.sqlite")
            if not database.exists():
                report["status"] = "watch_database_missing"
            else:
                with (
                    _read_mode(database) as immutable,
                    QueueStore(database, read_only=True, immutable=immutable) as queue,
                ):
                    evidence = read_latest_list_diagnosis(queue, MONITOR_SCOPE)
                review = describe_list_review(previous_list_review(args.work_root))
                report["list_diagnosis"] = evidence
                report["previous_list_review"] = review
                report["status"] = (
                    "diagnosis_found"
                    if evidence is not None or review is not None
                    else "no_saved_diagnosis"
                )
        except Exception:
            report["status"] = "diagnosis_read_failed"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2 if report["status"] == "diagnosis_read_failed" else 0
    if args.command == "monitor-save-one":
        from image_monitor.monitor_save_action import run_dashboard_child, save_exit_code

        output = run_dashboard_child(
            args.watch_root, args.legacy_root, args.work_root, stream=sys.stdin.buffer
        )
        print(json.dumps(output))
        return save_exit_code(output)
    if args.command == "watch-images-check":
        from image_monitor.watch_images_check import (
            check_recent_images,
            watch_images_check_exit_code,
        )

        report = check_recent_images(args.watch_root, args.legacy_root, args.work_root)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return watch_images_check_exit_code(report)
    if args.command == "watch-images":
        try:
            from image_monitor.watch_images import run_watch_images, watch_images_exit_code

            output = run_watch_images(
                args.watch_root, args.legacy_root, args.work_root, args.browser
            )
        except KeyboardInterrupt:
            parser.exit(130, "Recent-post image check cancelled.\n")
        except Exception as error:
            parser.exit(2, f"Recent-post image check stopped ({type(error).__name__}).\n")
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return watch_images_exit_code(output)
    if args.command in {"monitor-save-batch", "monitor-batch-finish", "watch-images-finish"}:
        try:
            if args.command == "monitor-save-batch":
                from image_monitor.monitor_batch_runtime import (
                    run_monitor_batch,
                    share_batch_report,
                )

                output = run_monitor_batch(args.watch_root, args.legacy_root, args.work_root)
                public_report = share_batch_report(output)
            else:
                from image_monitor.monitor_batch_finish import (
                    run_monitor_batch_finish,
                    share_batch_finish_report,
                )

                options = {"recent": True} if args.command == "watch-images-finish" else {}
                output = run_monitor_batch_finish(
                    args.watch_root, args.legacy_root, args.work_root, **options
                )
                public_report = share_batch_finish_report(output)
        except KeyboardInterrupt:
            parser.exit(130, "Monitor batch operation cancelled. Inspect existing save state.\n")
        except Exception as error:
            parser.exit(2, f"Monitor batch operation stopped ({type(error).__name__}).\n")
        print(json.dumps(public_report, ensure_ascii=False, indent=2))
        if output.get("error_type") == "KeyboardInterrupt" or output.get("status") in {
            "monitor_batch_cancelled",
            "batch_finish_cancelled",
        }:
            return 130
        allowed = (
            {
                "monitor_batch_completed",
                "monitor_batch_waiting",
                "monitor_batch_busy",
                "monitor_batch_no_candidates",
            }
            if args.command == "monitor-save-batch"
            else {"batch_finish_completed", "batch_finish_no_pending", "batch_finish_busy"}
        )
        return 0 if output.get("status") in allowed else 2
    if args.command == "monitor":
        try:
            from image_monitor.monitor_app import run_monitor_app, share_monitor_report

            options = {}
            if args.save_root is not None:
                options["save_root"] = args.save_root
            if args.batch_root is not None:
                if args.save_root is None:
                    raise ValueError("Batch preview requires the legacy save root")
                options["batch_root"] = args.batch_root
            output = run_monitor_app(args.work_root, **options)
            public_report = share_monitor_report(output)
        except KeyboardInterrupt:
            parser.exit(130, "List monitoring cancelled.\n")
        except Exception as error:
            parser.exit(2, f"List monitoring stopped ({type(error).__name__}).\n")
        print(json.dumps(public_report, ensure_ascii=False, indent=2))
        if (
            output.get("error_type") == "KeyboardInterrupt"
            or output.get("status") == "monitor_cancelled"
        ):
            return 130
        return 0 if output.get("status") in {"monitor_closed", "monitor_busy"} else 2
    if args.command in {"candidate-finish", "monitor-finish"}:
        try:
            from image_monitor.candidate_finish_runtime import (
                run_candidate_finish_trial,
                share_candidate_finish_report,
            )

            if args.command == "monitor-finish":
                from image_monitor.watch_store import WatchScope

                scope = WatchScope("목록 감시", "normal", "comic_new6", "ai", "search_subject_memo")
                output = run_candidate_finish_trial(args.watch_root, args.work_root, scope=scope)
            else:
                output = run_candidate_finish_trial(args.watch_root, args.work_root)
            public_report = share_candidate_finish_report(output)
        except KeyboardInterrupt:
            parser.exit(130, "Completed candidate verification cancelled.\n")
        except Exception as error:
            parser.exit(2, f"Completed candidate verification stopped ({type(error).__name__}).\n")
        print(json.dumps(public_report, ensure_ascii=False, indent=2))
        if (
            output.get("error_type") == "KeyboardInterrupt"
            or output.get("status") == "candidate_finish_cancelled"
        ):
            return 130
        return (
            0
            if output.get("status")
            in {
                "candidate_finish_completed",
                "candidate_finish_no_pending",
                "candidate_finish_busy",
            }
            else 2
        )
    if args.command in {"candidate-save-test", "monitor-save-test"}:
        try:
            from image_monitor.candidate_save_runtime import (
                run_candidate_save_trial,
                share_candidate_save_report,
            )

            if args.command == "monitor-save-test":
                from image_monitor.watch_store import WatchScope

                scope = WatchScope("목록 감시", "normal", "comic_new6", "ai", "search_subject_memo")
                output = run_candidate_save_trial(
                    args.watch_root, args.work_root, args.browser, scope=scope
                )
            else:
                output = run_candidate_save_trial(args.watch_root, args.work_root, args.browser)
            public_report = share_candidate_save_report(output)
        except KeyboardInterrupt:
            parser.exit(130, "Candidate native saving cancelled. Inspect the dedicated browser.\n")
        except Exception as error:
            parser.exit(2, f"Candidate native saving stopped ({type(error).__name__}).\n")
        print(json.dumps(public_report, ensure_ascii=False, indent=2))
        if (
            output.get("error_type") == "KeyboardInterrupt"
            or output.get("status") == "candidate_save_cancelled"
        ):
            return 130
        return (
            0
            if output.get("status")
            in {
                "candidate_save_completed",
                "candidate_save_waiting",
                "candidate_save_busy",
                "candidate_save_no_candidate",
            }
            else 2
        )
    if args.command in {"candidate-test", "watch-detail"}:
        try:
            from image_monitor.candidate_runtime import run_candidate_trial, share_candidate_report

            if args.command == "watch-detail":
                output = run_candidate_trial(
                    args.work_root, args.browser, max_candidates=1, recent_scan_only=True
                )
            else:
                output = run_candidate_trial(args.work_root, args.browser)
            public_report = share_candidate_report(output)
        except KeyboardInterrupt:
            parser.exit(130, "Bounded candidate inspection cancelled.\n")
        except Exception as error:
            parser.exit(2, f"Bounded candidate inspection stopped ({type(error).__name__}).\n")
        print(json.dumps(public_report, ensure_ascii=False, indent=2))
        if (
            output.get("error_type") == "KeyboardInterrupt"
            or output.get("status") == "candidate_test_cancelled"
        ):
            return 130
        return (
            0
            if output.get("status")
            in {
                "candidate_test_completed",
                "candidate_waiting",
                "candidate_busy",
                "candidate_no_pending",
                "candidate_no_baseline",
            }
            else 2
        )
    if args.command == "watch-test":
        try:
            from image_monitor.watch_runtime import run_watch_trial, share_watch_report

            output = run_watch_trial(args.work_root, args.browser)
            public_report = share_watch_report(output)
        except KeyboardInterrupt:
            parser.exit(130, "Bounded list-watch trial cancelled.\n")
        except Exception as error:
            parser.exit(2, f"Bounded list-watch trial stopped ({type(error).__name__}).\n")
        print(json.dumps(public_report, ensure_ascii=False, indent=2))
        if (
            output.get("error_type") == "KeyboardInterrupt"
            or output.get("status") == "watch_test_cancelled"
        ):
            return 130
        if output.get("status") == "watch_test_partial":
            return 0 if output.get("recent_pages_verified") is True else 2
        return (
            0
            if output.get("status") in {"watch_test_completed", "watch_waiting", "watch_busy"}
            else 2
        )
    if args.command == "watch-demo":
        try:
            from image_monitor.watch_commands import watch_demo

            output = watch_demo(args.db)
        except KeyboardInterrupt:
            parser.exit(130, "Synthetic watch demo cancelled.\n")
        except Exception as error:
            parser.exit(2, f"Synthetic watch demo failed ({type(error).__name__}).\n")
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    if args.command == "list-inspect":
        try:
            from image_monitor.list_inspection import run_list_inspection, share_report

            options = {"url": args.list_url} if args.list_url else {}
            output = run_list_inspection(args.work_root, args.browser, **options)
            public_report = share_report(output)
        except KeyboardInterrupt:
            parser.exit(130, "Read-only list inspection cancelled.\n")
        except Exception as error:
            parser.exit(2, f"Read-only list inspection stopped ({type(error).__name__}).\n")
        print(json.dumps(public_report, ensure_ascii=False, indent=2))
        return 2 if output.get("status") == "inspection_failed" else 0
    if args.command == "save-post":
        from image_monitor.native_ui import NativeUIError
        from image_monitor.post_worker import run_post_save, share_worker_report

        try:
            options = {"url": args.post_url} if args.post_url else {}
            if args.resume_preinput:
                options["resume_preinput"] = True
            output = run_post_save(args.work_root, args.browser, **options)
        except NativeUIError as error:
            parser.exit(2, f"{error}\n")
        except KeyboardInterrupt:
            parser.exit(130, "Post saving cancelled. Inspect the dedicated browser and report.\n")
        except Exception as error:
            parser.exit(2, f"Post saving stopped ({type(error).__name__}); inspect the report.\n")
        print(json.dumps(share_worker_report(output), ensure_ascii=False, indent=2))
        if output.get("error_type") == "KeyboardInterrupt":
            return 130
        return 0 if output.get("status") == "post_completed" else 2
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
