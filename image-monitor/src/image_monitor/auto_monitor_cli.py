"""Console controls and public output for an automatic monitoring session."""

import json
import os
import sys
from contextlib import nullcontext
from datetime import datetime

from image_monitor import PUBLIC_VERSION


def _console_stop():
    if sys.platform != "win32" or not sys.stdin.isatty():
        return None
    import msvcrt

    requested = False

    def pressed():
        nonlocal requested
        while not requested and msvcrt.kbhit():
            requested = msvcrt.getwch() == "\r"
        return requested

    return pressed


def _progress_output():
    # The double-click launcher captures diagnostics into the result TXT.
    if sys.platform == "win32" and os.environ.get("IMAGE_MONITOR_CONSOLE_PROGRESS") == "1":
        try:
            return open("CONOUT$", "w", encoding="utf-8", buffering=1)
        except OSError:
            pass  # A headless process has no console device.
    return nullcontext(sys.stderr)


def _show_progress(report, stream):
    phase = report["phase"]
    messages = {
        "starting": "자동 감시 시작",
        "scanning": "목록 확인 중",
        "collecting": "게시글 이미지 확인 및 저장 중",
        "waiting": "다음 확인 대기 중",
    }
    if phase not in messages:
        return
    message = (
        f"{messages[phase]} | 완료 {report['cycles_completed']}주기 · "
        f"게시글 {report['posts_saved']}건 · 검증 {report['files_verified']}장"
    )
    if report.get("previously_verified_files"):
        previous = report["previously_verified_files"]
        new = report["newly_saved_files"]
        message += f" (기존 {previous}장, 새로 저장 {new}장)"
    last_list = report.get("last_list")
    if last_list and last_list.get("page_limit", 0) > 2:
        outcome = "확인 완료" if last_list["status"] == "complete" else "미확인 구간 남음"
        numbers = ", ".join(str(page) for page in last_list["visited_page_numbers"])
        message += f" | 확인한 목록 {numbers}쪽 · {outcome}"
    due = report.get("next_eligible_at")
    if phase == "waiting" and due:
        local_time = datetime.fromisoformat(due).astimezone()
        message += f" | 재개 예정 {local_time:%m-%d %H:%M:%S}"
    print(message, file=stream, flush=True)


def run_auto_monitor_cli(watch_root, legacy_root, work_root, max_cycles):
    try:
        from image_monitor.monitor_auto_session import auto_monitor_exit_code, run_auto_monitor

        with _progress_output() as progress:
            should_stop = _console_stop() if max_cycles is None else None
            if should_stop:
                print(
                    "종료하려면 저장이 끝난 뒤 이 창에서 Enter를 누르세요.",
                    file=progress,
                    flush=True,
                )
            report = run_auto_monitor(
                watch_root,
                legacy_root,
                work_root,
                max_cycles=max_cycles,
                should_stop=should_stop,
                on_progress=lambda snapshot: _show_progress(snapshot, progress),
            )
            code = auto_monitor_exit_code(report)
    except (KeyboardInterrupt, Exception) as error:
        interrupted = isinstance(error, KeyboardInterrupt)
        report = {
            "program_version": PUBLIC_VERSION,
            "status": "auto_monitor_cancelled" if interrupted else "auto_monitor_review",
            "error_type": type(error).__name__,
        }
        code = 130 if interrupted else 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code
