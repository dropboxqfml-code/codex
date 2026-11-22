"""Console controls and public output for an automatic monitoring session."""

import json
import os
import sys
from contextlib import nullcontext
from datetime import datetime

from image_monitor import PUBLIC_VERSION
from image_monitor.monitor_gap_report import RECOVERY_MESSAGES
from image_monitor.monitor_list_review_text import describe_list_review
from image_monitor.watch_history import HISTORICAL_ROUTE_REASONS

_HEAD_JOIN_KO = {
    "clipped_prefix": (
        "지난 첫 쪽의 첫 글부터 세 건 이상이 현재 1·2쪽의 끝부분에 같은 순서로 이어졌습니다."
    ),
    "corroborated_suffix": (
        "지난 첫 쪽 끝의 글 세 개 이상과 그 뒤에 오던 2쪽 글이 현재 목록에서도 연달아 확인됐습니다."
    ),
}

_HISTORICAL_REASON_KO = {
    "checkpoint_in_recent_pages": "최근 두 쪽 안에서 이전 완료 기준 글을 찾았습니다.",
    "insufficient_recent_pages": "최근 두 쪽 중 한 쪽만 확인했습니다.",
    "recent_chain_unverified": "최근 1·2쪽의 연결과 글 순서를 확인하기 어려웠습니다.",
    "previous_head_not_matched": "최근 1·2쪽에서 지난번 첫 쪽의 글 순서를 찾지 못했습니다.",
    "boundary_link_missing": "현재 2쪽에서 지난번 마지막 쪽으로 가는 링크를 찾지 못했습니다.",
    "boundary_link_ambiguous": "현재 2쪽에 지난번 마지막 쪽으로 가는 링크가 여러 개 있었습니다.",
    "route_not_observed": "이어갈 링크를 확인했지만 그 링크로 이동한 기록이 없습니다.",
    "boundary_extended": "지난번 마지막 쪽의 글 순서를 대조한 뒤 그다음 쪽까지 확인했습니다.",
    "successor_link_missing": "지난번 마지막 쪽에 그다음 쪽으로 가는 링크가 없었습니다.",
    "successor_link_ambiguous": "지난번 마지막 쪽에 그다음 쪽으로 가는 링크가 여러 개 있었습니다.",
    "previous_boundary_not_matched": "지난번 마지막 쪽의 글 순서를 다시 확인하지 못했습니다.",
    "route_evidence_unverified": "남은 목록 기록으로는 탐색 경로를 판단하기 어렵습니다.",
}


def _describe_list_check(check):
    if not isinstance(check, dict):
        return check
    described = check.copy()
    if "review" in described:
        review = describe_list_review(described.pop("review"))
        if check.get("status") in {"waiting", "review"} and review:
            described["review"] = review
    recovery = described.pop("recovery_status", None)
    described.pop("recovery_status_ko", None)
    if isinstance(recovery, str) and recovery in RECOVERY_MESSAGES:
        described.update(recovery_status=recovery, recovery_status_ko=RECOVERY_MESSAGES[recovery])
    reason = described.pop("historical_reason", None)
    described.pop("historical_reason_ko", None)
    join = described.pop("head_join", None)
    described.pop("head_join_ko", None)
    allowed = HISTORICAL_ROUTE_REASONS.get(check.get("historical_status"), ())
    if isinstance(reason, str) and reason in allowed:
        described.update(
            historical_reason=reason, historical_reason_ko=_HISTORICAL_REASON_KO[reason]
        )
        if (
            check.get("historical_status") in ("extended", "boundary_changed")
            and isinstance(join, str)
            and join in _HEAD_JOIN_KO
        ):
            described.update(head_join=join, head_join_ko=_HEAD_JOIN_KO[join])
    return described


def _describe_result(report):
    result = report.copy()
    for key in ("previous_list_review", "last_inspection_retry"):
        if key in result:
            review = describe_list_review(result.pop(key))
            if review:
                result[key] = review
    if "last_list" in report:
        result["last_list"] = _describe_list_check(report["last_list"])
    for key in ("previous_list_checks", "recent_list_checks"):
        if key in report:
            result[key] = [_describe_list_check(check) for check in report[key]]
    return result


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
        "scanned_during_save": "이미지 저장 중 목록 확인 완료",
        "waiting": "다음 확인 대기 중",
    }
    if phase not in messages:
        return
    message = (
        f"{messages[phase]} | 완료 {report['cycles_completed']}주기 · "
        f"게시글 {report['posts_saved']}건 · 검증 {report['files_verified']}장"
    )
    if report.get("mode") == "list_recovery_test":
        message = "목록 복구 확인 시작" if phase == "starting" else messages[phase]
    if report.get("previously_verified_files"):
        previous = report["previously_verified_files"]
        new = report["newly_saved_files"]
        message += f" (기존 {previous}장, 새로 저장 {new}장)"
    last_list = report.get("last_list")
    if last_list and (
        last_list.get("page_limit", 0) > 2 or last_list.get("search_window_start_visits")
    ):
        outcome = "확인 완료" if last_list["status"] == "complete" else "미확인 구간 남음"
        numbers = ", ".join(str(page) for page in last_list["visited_page_numbers"])
        message += f" | 확인한 목록 {numbers}쪽 · {outcome}"
        if "recovery_depth" in last_list:
            message += f" · 복구 위치 {last_list['recovery_depth']}쪽"
        if last_list.get("search_window_start_visits") or last_list.get(
            "recovery_crossed_search_range"
        ):
            message += " · 다음 검색 구간 진입"
    if phase == "waiting" and last_list and last_list.get("reason") == "inspection_retry_due":
        page = (last_list.get("review") or {}).get("failed_page")
        if type(page) is int:
            message += f" | {page}쪽 읽기 시간 초과 · 목록 한 번 재확인 예정"
    due = report.get("next_eligible_at")
    if phase == "waiting" and due:
        local_time = datetime.fromisoformat(due).astimezone()
        message += f" | 재개 예정 {local_time:%m-%d %H:%M:%S}"
    print(message, file=stream, flush=True)


def run_auto_monitor_cli(watch_root, legacy_root, work_root, max_cycles, *, list_only=False):
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
                **({"list_only": True} if list_only else {}),
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
    print(json.dumps(_describe_result(report), ensure_ascii=False, indent=2))
    return code
