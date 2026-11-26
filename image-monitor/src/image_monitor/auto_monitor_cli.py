"""Console controls and public output for an automatic monitoring session."""

import json
import os
import sys
from contextlib import nullcontext
from datetime import datetime

from image_monitor import PUBLIC_VERSION
from image_monitor.monitor_date_report import public_date_cell_checks
from image_monitor.monitor_gap_report import (
    RECOVERY_MESSAGES,
    RECOVERY_OBSERVATION_MESSAGES,
    RECOVERY_REASON_MESSAGES,
    checked_gap_route,
)
from image_monitor.monitor_list_review_text import describe_date_cells, describe_list_review
from image_monitor.monitor_settings import MAX_CATCH_UP_SCANS
from image_monitor.monitor_trial_progress import MonitorTrial
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


def _describe_recovery_evidence(check):
    if not any(
        key in check
        for key in (
            "recovery_reason",
            "recovery_observation",
            "frontier_overlap",
            "candidate_eligible_visits",
        )
    ):
        return {}
    try:
        route = checked_gap_route(check, check.get("visited_page_numbers"), check.get("page_limit"))
    except (KeyError, TypeError, ValueError):
        return {}
    details = {}
    if "recovery_reason" in route:
        code = route["recovery_reason"]
        details.update(
            recovery_reason=code,
            recovery_reason_ko=RECOVERY_REASON_MESSAGES[route["recovery_status"]][code],
        )
    elif "recovery_observation" in route:
        code = route["recovery_observation"]
        details.update(
            recovery_observation=code, recovery_observation_ko=RECOVERY_OBSERVATION_MESSAGES[code]
        )
    if "frontier_overlap" in route:
        overlap = route["frontier_overlap"]
        previous, matched = overlap["previous_rows"], overlap["matched_rows"]
        text = (
            f"이전 복구 위치의 일반 글 {previous}개 중 {matched}개를 "
            "이번에 이어서 읽은 두 쪽에서 다시 찾았습니다."
        )
        if overlap["shape"] == "prefix_at_end":
            text += " 이전 목록 첫머리의 글들이 이번 두 쪽의 끝에 같은 순서로 이어졌습니다."
        details.update(frontier_overlap=overlap, frontier_overlap_ko=text)
    if "candidate_eligible_visits" in route:
        visits, eligible = len(check["visited_page_numbers"]), route["candidate_eligible_visits"]
        scope = "모두" if visits == eligible else f"중 처음 {eligible}개"
        details.update(
            candidate_eligible_visits=eligible,
            candidate_eligible_visits_ko=f"방문한 목록 {visits}개 {scope}에서 후보를 확인했습니다.",
        )
    return details


def _describe_list_check(check):
    if not isinstance(check, dict):
        return check
    described = check.copy()
    if "date_cell_checks" in described:
        checks = public_date_cell_checks(
            described.pop("date_cell_checks"), described.get("visited_page_numbers")
        )
        if checks and described.get("status") in ("baseline", "partial", "complete"):
            described["date_cell_checks"] = [describe_date_cells(page) for page in checks]
    if "review" in described:
        review = describe_list_review(described.pop("review"))
        if check.get("status") in {"waiting", "review"} and review:
            described["review"] = review
    recovery = described.pop("recovery_status", None)
    described.pop("recovery_status_ko", None)
    described.pop("recovery_reason", None)
    described.pop("recovery_reason_ko", None)
    described.pop("recovery_observation", None)
    described.pop("recovery_observation_ko", None)
    described.pop("frontier_overlap", None)
    described.pop("frontier_overlap_ko", None)
    described.pop("candidate_eligible_visits", None)
    described.pop("candidate_eligible_visits_ko", None)
    if isinstance(recovery, str) and recovery in RECOVERY_MESSAGES:
        described.update(recovery_status=recovery, recovery_status_ko=RECOVERY_MESSAGES[recovery])
        described.update(_describe_recovery_evidence(check))
        if recovery == "held" and "recovery_reason" not in described:
            described["recovery_status_ko"] += " 이 기록에는 세부 보류 사유가 없습니다."
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
    limit = report.get("max_cycles")
    if report.get("mode") == "list_recovery_test" and limit in (2, MAX_CATCH_UP_SCANS):
        exhausted = (
            "두 차례 확인했습니다." if limit == 2 else "이번 시험의 확인 한도에 도달했습니다."
        )
        summary = {
            "list_coverage_confirmed": "이전 완료 지점까지 목록이 이어졌습니다.",
            "cycle_limit_reached": f"{exhausted} 남은 구간은 다음 감시에서 이어갑니다.",
            "recovery_followup_deferred": "복구 위치를 확정할 수 없어 추가 확인을 보류했습니다.",
            "recovery_progress_stalled": "복구 위치가 더 진행되지 않아 이번 확인을 마쳤습니다.",
            "inspection_retry_due": f"{exhausted} 다음 확인 가능 시각을 기록했습니다.",
            "requested_stop": "중단 요청을 받았습니다. 완료한 목록 확인은 기록에 남습니다.",
        }.get(report.get("reason"))
        if summary:
            result["list_test_summary_ko"] = summary
    if report.get("mode") == "automatic_monitor_session" and limit == 2:
        summary = (
            f"목록 확인 {report['list_checks']}회"
            f"(이미지 저장 중 {report['list_checks_during_save']}회), "
            f"새 후보 {report['new_candidates']}건, "
            f"새 본문 확인 {report['new_details_checked']}건. "
            f"저장 완료 게시글 {report['posts_saved']}건, 새로 저장을 확인한 이미지 "
            f"{report['newly_saved_files']}장."
        )
        checks = report["recent_list_checks"]
        if checks and checks[-1]["status"] == "partial":
            summary += " 마지막 목록 확인에서 이전 완료 지점까지 미확인 구간이 남았습니다."
        result["auto_test_summary_ko"] = summary
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


def _progress_message(report):
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
        if report.get("max_cycles") == MAX_CATCH_UP_SCANS:
            message += (
                f" | 확인 완료 {report['list_checks']}회 · 새 후보 {report['new_candidates']}건"
            )
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
        recovery = _describe_recovery_evidence(last_list)
        if explanation := recovery.get("recovery_reason_ko") or recovery.get(
            "recovery_observation_ko"
        ):
            message += f" | {explanation}"
        if "frontier_overlap_ko" in recovery:
            message += " | " + recovery["frontier_overlap_ko"]
    if phase == "waiting" and last_list and last_list.get("reason") == "inspection_retry_due":
        page = (last_list.get("review") or {}).get("failed_page")
        if type(page) is int:
            message += f" | {page}쪽 읽기 시간 초과 · 목록 한 번 재확인 예정"
    due = report.get("next_eligible_at")
    if phase == "waiting" and due:
        local_time = datetime.fromisoformat(due).astimezone()
        message += f" | 재개 예정 {local_time:%m-%d %H:%M:%S}"
    return message


def _show_progress(report, stream):
    if message := _progress_message(report):
        print(message, file=stream, flush=True)


def run_auto_monitor_cli(watch_root, legacy_root, work_root, max_cycles, *, list_only=False):
    try:
        from image_monitor.monitor_auto_session import auto_monitor_exit_code, run_auto_monitor

        with _progress_output() as progress:
            catch_up = list_only and max_cycles == MAX_CATCH_UP_SCANS
            trial = None
            if (
                not list_only
                and max_cycles == 2
                and sys.platform == "win32"
                and os.environ.get("IMAGE_MONITOR_CONSOLE_PROGRESS") == "1"
            ):
                trial = MonitorTrial(progress, _console_stop())
            should_stop = (
                trial.should_stop
                if trial
                else (_console_stop() if max_cycles is None or catch_up else None)
            )
            if trial:
                trial.record("두 주기 시험 · 5분 후 종료 요청 · 일찍 마치려면 실행 창에서 Enter")
            elif should_stop:
                print(
                    "목록 확인을 마치려면 이 창에서 Enter를 누르세요."
                    if catch_up
                    else "종료하려면 저장이 끝난 뒤 이 창에서 Enter를 누르세요.",
                    file=progress,
                    flush=True,
                )

            def show(snapshot):
                if trial:
                    if message := _progress_message(snapshot):
                        # A background scan can finish while the writer is still saving.
                        stage = (
                            None
                            if snapshot["phase"] == "scanned_during_save"
                            else message.split(" | ")[0]
                        )
                        trial.record(message, stage=stage)
                else:
                    _show_progress(snapshot, progress)

            with trial.observe() if trial else nullcontext():
                report = run_auto_monitor(
                    watch_root,
                    legacy_root,
                    work_root,
                    max_cycles=max_cycles,
                    should_stop=should_stop,
                    on_progress=show,
                    **({"list_only": True} if list_only else {}),
                )
            if trial and trial.stop_trigger:
                report["trial_stop_trigger"] = trial.stop_trigger
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
