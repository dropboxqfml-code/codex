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
    monkeypatch.setitem(
        sys.modules, "msvcrt", SimpleNamespace(kbhit=lambda: bool(keys), getwch=keys.popleft)
    )
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
