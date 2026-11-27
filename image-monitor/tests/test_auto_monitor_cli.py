import io
import json
import sys
from collections import deque
from copy import deepcopy
from types import SimpleNamespace

import pytest

from image_monitor import PUBLIC_VERSION, auto_monitor_cli
from image_monitor.__main__ import main
from image_monitor.monitor_list_review import _STAGES
from image_monitor.monitor_list_review_text import _STAGE_TEXT
from image_monitor.watch_history import HEAD_JOIN_METHODS, HISTORICAL_ROUTE_REASONS


def test_bounded_cli_separates_progress_from_result_without_reading_keyboard(
    tmp_path, monkeypatch, capsys
):
    roots = [tmp_path / name for name in ("watch", "older", "images")]
    result = {
        "status": "auto_monitor_completed",
        "files_verified": 10,
        "previously_verified_files": 6,
        "newly_saved_files": 4,
    }

    def run_monitor(*paths, max_cycles, should_stop, on_progress):
        assert paths == tuple(roots)
        assert max_cycles == 2
        assert should_stop is None
        on_progress(
            {
                "phase": "waiting",
                "cycles_completed": 1,
                "posts_saved": 1,
                "files_verified": 10,
                "previously_verified_files": 6,
                "newly_saved_files": 4,
                "last_list": {
                    "status": "partial",
                    "page_limit": 4,
                    "pages_checked": 4,
                    "visited_page_numbers": [1, 2, 4, 5],
                },
                "next_eligible_at": "2026-06-01T12:00:00+00:00",
            }
        )
        return result

    monkeypatch.setattr(auto_monitor_cli, "_console_stop", lambda: pytest.fail("Keyboard polled"))
    monkeypatch.setitem(
        sys.modules,
        "image_monitor.monitor_auto_session",
        SimpleNamespace(run_auto_monitor=run_monitor, auto_monitor_exit_code=lambda report: 0),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-monitor",
            "auto-monitor",
            "--watch-root",
            str(roots[0]),
            "--legacy-root",
            str(roots[1]),
            "--work-root",
            str(roots[2]),
            "--max-cycles",
            "2",
        ],
    )
    monkeypatch.delenv("IMAGE_MONITOR_CONSOLE_PROGRESS", raising=False)
    assert main() == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == result
    assert "완료 1주기" in output.err and "재개 예정" in output.err
    assert "검증 10장 (기존 6장, 새로 저장 4장)" in output.err
    assert "확인한 목록 1, 2, 4, 5쪽 · 미확인 구간 남음" in output.err


def test_console_stop_polls_without_waiting_and_latches_enter(monkeypatch):
    keys = deque()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    import ctypes

    crt = SimpleNamespace(_kbhit=lambda: bool(keys), _getwch=lambda: ord(keys.popleft()))
    monkeypatch.setattr(ctypes, "CDLL", lambda name, *, winmode: crt)
    pressed = auto_monitor_cli._console_stop()
    assert not pressed()
    keys.extend(["x", "\r"])
    assert pressed()
    assert pressed()
    monkeypatch.setattr(sys, "stdin", io.StringIO())
    assert auto_monitor_cli._console_stop() is None


def test_launcher_routes_progress_to_its_console(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("IMAGE_MONITOR_CONSOLE_PROGRESS", "1")
    console = io.StringIO()

    def open_console(name, mode, *, encoding, buffering):
        assert (name, mode, encoding, buffering) == ("CONOUT$", "w", "utf-8", 1)
        return console

    monkeypatch.setattr("builtins.open", open_console)
    with auto_monitor_cli._progress_output() as output:
        assert output is console
    assert console.closed


def test_startup_error_is_reported_on_stdout_without_exception_text(tmp_path, monkeypatch, capsys):
    def failed(*args, **kwargs):
        raise RuntimeError("private local details")

    monkeypatch.setitem(
        sys.modules,
        "image_monitor.monitor_auto_session",
        SimpleNamespace(run_auto_monitor=failed, auto_monitor_exit_code=lambda report: 0),
    )
    assert auto_monitor_cli.run_auto_monitor_cli(tmp_path, tmp_path, tmp_path, 2) == 2
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "program_version": PUBLIC_VERSION,
        "status": "auto_monitor_review",
        "error_type": "RuntimeError",
    }
    assert "private local details" not in output.out + output.err


def test_result_txt_explains_previous_and_current_historical_checks(tmp_path, monkeypatch, capsys):
    old = {"historical_status": "recent_pages_only", "historical_reason": "boundary_link_missing"}
    new = {
        "historical_status": "extended",
        "historical_reason": "boundary_extended",
        "head_join": "clipped_prefix",
    }
    ordinary = {"status": "complete", "visited_page_numbers": [1, 2]}
    result = {
        "status": "auto_monitor_completed",
        "previous_list_checks": [ordinary, old],
        "recent_list_checks": [new],
        "last_list": new,
    }
    original = deepcopy(result)
    monkeypatch.setitem(
        sys.modules,
        "image_monitor.monitor_auto_session",
        SimpleNamespace(
            run_auto_monitor=lambda *a, **kw: result, auto_monitor_exit_code=lambda r: 0
        ),
    )
    assert auto_monitor_cli.run_auto_monitor_cli(tmp_path, tmp_path, tmp_path, 2) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["previous_list_checks"] == [
        ordinary,
        old
        | {
            "historical_reason_ko": "현재 2쪽에서 지난번 마지막 쪽으로 가는 링크를 찾지 못했습니다."
        },
    ]
    assert output["recent_list_checks"] == [output["last_list"]]
    assert output["last_list"] == new | {
        "historical_reason_ko": auto_monitor_cli._HISTORICAL_REASON_KO["boundary_extended"],
        "head_join_ko": auto_monitor_cli._HEAD_JOIN_KO["clipped_prefix"],
    }
    assert result == original


def test_only_verified_head_join_methods_receive_korean_explanations():
    assert set(auto_monitor_cli._HEAD_JOIN_KO) == HEAD_JOIN_METHODS
    recent = {
        "historical_status": "recent_pages_only",
        "historical_reason": "previous_head_not_matched",
    }
    historical = {
        "historical_status": "boundary_changed",
        "historical_reason": "previous_boundary_not_matched",
    }
    for check, join in ((recent, "corroborated_suffix"), (historical, "private-row-content")):
        public = auto_monitor_cli._describe_list_check(
            check | {"head_join": join, "head_join_ko": "private"}
        )
        assert "head_join" not in public and "head_join_ko" not in public
    public = auto_monitor_cli._describe_list_check(
        historical | {"head_join": "corroborated_suffix"}
    )
    assert "2쪽" in public["head_join_ko"] and "세 개 이상" in public["head_join_ko"]


def test_all_route_reasons_have_fixed_korean_text_and_unknown_details_stay_private():
    assert set(auto_monitor_cli._HISTORICAL_REASON_KO) == set().union(
        *HISTORICAL_ROUTE_REASONS.values()
    )
    for status, reasons in HISTORICAL_ROUTE_REASONS.items():
        for reason in reasons:
            check = {"historical_status": status, "historical_reason": reason}
            text = auto_monitor_cli._describe_list_check(check)["historical_reason_ko"]
            assert any("가" <= ch <= "힣" for ch in text) and reason not in text
    for reason in ("https://example.invalid/private?no=7", "boundary_extended", {"post_id": "7"}):
        check = {
            "historical_status": "recent_pages_only",
            "historical_reason": reason,
            "historical_reason_ko": "private page details",
        }
        assert auto_monitor_cli._describe_list_check(check) == {
            "historical_status": "recent_pages_only"
        }


def test_korean_list_review_is_reprojected_for_live_and_previous_checks():
    assert set(_STAGE_TEXT) == _STAGES
    review = {
        "stage": "partial_check",
        "stage_ko": "private stored text",
        "evidence": "committed_scan",
        "http_status": 200,
        "error_type": "private stored exception",
        "pages": [{"page": 1, "post": "private post", "status": "observed"}],
        "url": "private site",
    }
    result = auto_monitor_cli._describe_result(
        {"previous_list_review": review, "last_list": {"status": "review", "review": review}}
    )
    assert result["previous_list_review"] == result["last_list"]["review"]
    assert "부분 확인" in result["previous_list_review"]["stage_ko"]
    assert result["previous_list_review"]["http_status"] == 200
    assert "private" not in json.dumps(result, ensure_ascii=False)
    assert auto_monitor_cli._describe_result(
        {
            "previous_list_review": {"stage": "private"},
            "last_list": {"status": "complete", "review": review},
        }
    ) == {"last_list": {"status": "complete"}}


def test_date_checks_keep_only_anonymous_counts_at_the_verified_visit():
    checked = {
        "visit": 2,
        "page": 1,
        "layout_status": "site_verified",
        "ordinary_rows": 20,
        "excluded_rows": 3,
        "date_cell_mismatches": {"ad": {"missing": 2, "raw": "private link"}},
        "date_cells": {
            "ordinary_rows_with_one": 20,
            "excluded_rows_counted": 3,
            "table_cell_total": 21,
            "row_cell_total": 21,
            "raw": "private date",
        },
        "raw": "private URL",
        "date_observation_ko": "private title",
    }
    result = {
        "status": "partial",
        "visited_page_numbers": [1, 1, 4, 5],
        "date_cell_checks": [checked],
    }
    [shown] = auto_monitor_cli._describe_list_check(result)["date_cell_checks"]
    assert shown["visit"] == 2 and shown["page"] == 1
    assert shown["date_cells"]["table_check"] == "matches_rows"
    assert shown["date_observation_ko"] == "광고 행 2개에 날짜 칸이 없습니다."
    assert "private" not in json.dumps(shown)
    for wrong in (
        {"visit": 3},
        {"page": True},
        {"visit": True},
        {"date_cells": checked["date_cells"] | {"row_cell_total": 22}},
        {"date_cell_mismatches": {"other_excluded": {"missing": 1}}},
    ):
        report = result | {"date_cell_checks": [checked | wrong]}
        assert "date_cell_checks" not in auto_monitor_cli._describe_list_check(report)
    assert "date_cell_checks" not in auto_monitor_cli._describe_list_check(
        result | {"status": "review"}
    )


def test_catch_up_command_allows_enter_and_reports_verified_totals(tmp_path, monkeypatch, capsys):
    from image_monitor import monitor_auto_session
    from image_monitor.monitor_settings import MAX_CATCH_UP_SCANS

    def pressed():
        return True

    def stop_early(*paths, max_cycles, should_stop, on_progress, list_only):
        assert paths == (tmp_path, None, None)
        assert list_only and max_cycles == MAX_CATCH_UP_SCANS
        assert should_stop is pressed
        result = {
            "mode": "list_recovery_test",
            "max_cycles": max_cycles,
            "phase": "scanning",
            "status": "auto_monitor_stopped",
            "reason": "requested_stop",
            "list_checks": 2,
            "cycles_completed": 2,
            "new_candidates": 29,
            "posts_saved": 0,
            "files_verified": 0,
        }
        on_progress(result)
        return result

    monkeypatch.setattr(
        sys,
        "argv",
        ["image-monitor", "test-list-recovery", "--watch-root", str(tmp_path), "--catch-up"],
    )
    monkeypatch.setattr(auto_monitor_cli, "_console_stop", lambda: pressed)
    monkeypatch.setattr(monitor_auto_session, "run_auto_monitor", stop_early)
    monkeypatch.delenv("IMAGE_MONITOR_CONSOLE_PROGRESS", raising=False)
    assert main() == 0
    output = capsys.readouterr()
    assert "Enter" in output.err and "확인 완료 2회 · 새 후보 29건" in output.err
    assert "중단 요청" in json.loads(output.out)["list_test_summary_ko"]


def test_catch_up_and_single_follow_up_are_mutually_exclusive(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-monitor",
            "test-list-recovery",
            "--watch-root",
            str(tmp_path),
            "--follow-gap",
            "--catch-up",
        ],
    )
    with pytest.raises(SystemExit) as stopped:
        main()
    assert stopped.value.code == 2
    assert "--catch-up" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("status", "numbers", "eligible"),
    [
        ("frontier_changed", [1, 2, 5, 6], 2),
        ("frontier_changed", [1, 2, 5], 2),
        ("frontier_relocated", [1, 2, 5, 6], 4),
    ],
)
def test_changed_frontier_separates_visited_pages_from_candidate_pages(status, numbers, eligible):
    from image_monitor.monitor_gap_report import checked_gap_route, gap_route_details

    marker = {
        "status": status,
        "route": "bookmark",
        "crossed_search_range": False,
        "depth": 6 if status == "frontier_relocated" else 5,
        "eligible_pages": eligible,
    }
    if status == "frontier_relocated":
        marker["recovery_reason"] = "frontier_prefix_overlap"
    record = {
        "complete": False,
        "control": {
            "follow_up_page_limit": 4,
            "historical_route_schema": 5 if status == "frontier_relocated" else 4,
        },
        "private_observation": {"pages": [{"page": n, "search_pos": None} for n in numbers]},
        "gap_recovery": marker,
    }
    check = gap_route_details(record) | {
        "status": "partial",
        "visited_page_numbers": numbers,
        "page_limit": 4,
    }
    assert check["candidate_eligible_visits"] == eligible
    shown = auto_monitor_cli._describe_list_check(check)
    assert shown["candidate_eligible_visits"] == eligible and shown["candidate_eligible_visits_ko"]
    for wrong in (True, 0, 3, 7, "private"):
        tampered = check | {
            "candidate_eligible_visits": wrong,
            "candidate_eligible_visits_ko": "private",
        }
        with pytest.raises(ValueError):
            checked_gap_route(tampered, numbers, 4)
        shown = auto_monitor_cli._describe_list_check(tampered)
        assert (
            "candidate_eligible_visits" not in shown and "candidate_eligible_visits_ko" not in shown
        )


def test_two_cycle_summary_distinguishes_partial_coverage_from_saved_files():
    report = {
        "mode": "automatic_monitor_session",
        "max_cycles": 2,
        "list_checks": 2,
        "list_checks_during_save": 0,
        "new_candidates": 20,
        "new_details_checked": 1,
        "posts_saved": 0,
        "newly_saved_files": 0,
        "recent_list_checks": [{"status": "partial"}],
    }
    summary = auto_monitor_cli._describe_result(report)["auto_test_summary_ko"]
    assert "새 후보 20건" in summary and "이미지 0장" in summary and "미확인 구간" in summary
    report["recent_collection_attempts"] = [
        {"uninspected_at_selection": 107, "fresh_detail_outcome": "save_ready"},
        {
            "uninspected_at_selection": 106,
            "reason": "fresh_detail_limit",
            "fresh_detail_outcome": "no_body_images_observed",
        },
    ]
    summary = auto_monitor_cli._describe_result(report)["auto_test_summary_ko"]
    assert "106건" in summary and "107건" not in summary
    assert "본문에서 이미지를 찾지 못했습니다" in summary and "한도(1건)" in summary
    assert "auto_test_summary_ko" not in auto_monitor_cli._describe_result(
        report | {"max_cycles": None}
    )


@pytest.mark.parametrize("trigger", ["enter", "time_limit", "interrupt"])
def test_windows_trial_keeps_live_checkpoints_before_the_final_json(monkeypatch, capsys, trigger):
    from threading import Event

    from image_monitor import monitor_auto_session, monitor_trial_progress
    from image_monitor.monitor_trial_progress import trial_stage

    console = io.StringIO()
    key_checked = Event()
    now = [0]
    monkeypatch.setattr(monitor_trial_progress, "monotonic", lambda: now[0])

    def keypress():
        key_checked.set()
        return trigger == "enter"

    monkeypatch.setattr(auto_monitor_cli, "_console_stop", lambda: keypress)
    monkeypatch.setattr(
        auto_monitor_cli, "_progress_output", lambda: auto_monitor_cli.nullcontext(console)
    )
    monkeypatch.setenv("IMAGE_MONITOR_CONSOLE_PROGRESS", "1")
    monkeypatch.setattr(sys, "platform", "win32")

    def run(*args, on_progress, should_stop, **kwargs):
        on_progress(
            {"phase": "collecting", "cycles_completed": 1, "posts_saved": 1, "files_verified": 2}
        )
        trial_stage("저장 후보 선택")
        before = capsys.readouterr()
        assert before.out == ""
        # Every file checkpoint is synchronous even if screen updates coalesce.
        assert "완료 1주기 · 게시글 1건 · 검증 2장" in before.err
        assert "[시험 0초] 저장 후보 선택" in before.err
        if trigger == "interrupt":
            raise KeyboardInterrupt
        if trigger == "enter":
            from time import monotonic, sleep

            assert key_checked.wait(2)
            deadline = monotonic() + 2
            while not should_stop() and monotonic() < deadline:
                sleep(0.005)
        if trigger == "time_limit":
            now[0] = 299
            assert not should_stop()
            now[0] = 300
        assert should_stop()
        return {"status": "auto_monitor_stopped", "reason": "requested_stop"}

    monkeypatch.setattr(monitor_auto_session, "run_auto_monitor", run)
    assert auto_monitor_cli.run_auto_monitor_cli(None, None, None, 2) == (
        130 if trigger == "interrupt" else 0
    )
    result = json.loads(capsys.readouterr().out)
    if trigger != "interrupt":
        assert result["trial_stop_trigger"] == trigger
        assert result["trial_stop_elapsed_seconds"] == (300 if trigger == "time_limit" else 0)
        if trigger == "enter":
            assert result["trial_enter_observed_seconds"] == 0
    else:
        assert result["status"] == "auto_monitor_cancelled"
    trial_stage("must not escape the completed trial")
    assert not capsys.readouterr().err


def test_trial_timeout_emits_checkpoint_while_foreground_call_is_blocked(monkeypatch):
    from threading import Event

    from image_monitor import monitor_trial_progress as progress

    announced = Event()

    class Console(io.StringIO):
        def flush(self):
            if "종료 요청" in self.getvalue():
                announced.set()
            super().flush()

    console = Console()
    monkeypatch.setattr(progress, "_HEARTBEAT_SECONDS", 0.01)
    monkeypatch.setattr(progress, "_TRIAL_SECONDS", 0)
    trial = progress.MonitorTrial(lambda: auto_monitor_cli.nullcontext(console), None)
    with trial.observe():
        assert announced.wait(3)
        assert trial.should_stop() and trial.stop_trigger == "time_limit"
    assert "현재 단계가 안전하게 끝나기" in console.getvalue()
