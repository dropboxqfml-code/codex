import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from image_monitor import native_probe
from image_monitor.native_probe import (
    create_fixture,
    save_one_image,
    wait_for_fixture,
    write_report,
)
from image_monitor.native_ui import NativeUIError, WindowsUI, choose_unique, normalize_label


@pytest.mark.parametrize(
    "label,expected",
    [
        ("Save image as...", "Save image as"),
        ("이미지를 다른 이름으로 저장(&V)...", "이미지를 다른 이름으로 저장"),
        ("저장(&S)", "저장"),
    ],
)
def test_menu_label_normalization(label, expected):
    assert normalize_label(label) == expected


def test_no_arbitrary_selection_for_missing_or_duplicate_menu():
    with pytest.raises(NativeUIError, match="found 0"):
        choose_unique(["Copy", "Save page as"], lambda item: item == "Save image as", "menu")
    with pytest.raises(NativeUIError, match="found 2"):
        choose_unique(["Save", "Save"], lambda item: item == "Save", "menu")


def test_windows_guard_has_no_filesystem_side_effects(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    root = tmp_path / "not-created"
    with pytest.raises(NativeUIError, match="Windows"):
        native_probe.run_probe(root, "edge")
    assert not root.exists()


def test_synthetic_fixture_is_local_and_decodable(tmp_path):
    html, expected = create_fixture(tmp_path / "fixture")
    png = html.parent / "fixture-original.png"
    assert expected == hashlib.sha256(png.read_bytes()).hexdigest()
    assert "https://" not in html.read_text(encoding="utf-8")
    assert 'id="probe-image"' in html.read_text(encoding="utf-8")


def mock_page():
    page = MagicMock()
    body = page.locator.return_value
    body.count.return_value = 1
    image = body.locator.return_value
    image.count.return_value = 1
    return page, image


def test_native_sequence_preserves_suggested_name_without_download_api(tmp_path):
    page, image = mock_page()
    ui = MagicMock(spec=WindowsUI)
    ui.save_dialog.return_value = "original.png"
    events = []
    image.evaluate.side_effect = lambda *_args, **_kwargs: events.append("decode")
    image.click.side_effect = lambda **_kwargs: events.append("right_click")
    ui.click_save_image_menu.side_effect = lambda: events.append("menu")
    ui.save_dialog.side_effect = lambda _target: events.append("dialog") or "original.png"
    assert save_one_image(page, ui, tmp_path / "staged.png") == "original.png"
    assert events == ["decode", "right_click", "menu", "dialog"]
    image.click.assert_called_once_with(button="right", timeout=15_000)
    ui.save_dialog.assert_called_once_with(str(tmp_path / "staged.png"))
    page.expect_download.assert_not_called()


def test_missing_body_image_stops_before_right_click(tmp_path):
    page, image = mock_page()
    image.count.return_value = 0
    ui = MagicMock(spec=WindowsUI)
    with pytest.raises(NativeUIError, match="missing"):
        save_one_image(page, ui, tmp_path / "staged.png")
    image.click.assert_not_called()
    ui.save_dialog.assert_not_called()


def test_focus_failure_stops_before_native_input(tmp_path):
    page, image = mock_page()
    ui = MagicMock(spec=WindowsUI)
    ui.assert_target_ready.side_effect = NativeUIError("Focus changed")
    with pytest.raises(NativeUIError, match="Focus"):
        save_one_image(page, ui, tmp_path / "staged.png")
    image.click.assert_not_called()
    ui.click_save_image_menu.assert_not_called()


def test_menu_failure_never_writes_save_path(tmp_path):
    page, _image = mock_page()
    ui = MagicMock(spec=WindowsUI)
    ui.click_save_image_menu.side_effect = NativeUIError("Unrecognized menu")
    with pytest.raises(NativeUIError, match="Unrecognized"):
        save_one_image(page, ui, tmp_path / "staged.png")
    ui.save_dialog.assert_not_called()


def test_exact_fixture_hash_required_for_completion(tmp_path, monkeypatch):
    html, expected = create_fixture(tmp_path / "fixture")
    target = html.parent / "fixture-original.png"
    monkeypatch.setattr(native_probe, "exclusive_digest", lambda _path: expected)
    result = wait_for_fixture(target, expected, MagicMock(spec=WindowsUI))
    assert result["sha256"] == expected
    assert result["width"] == 96
    assert result["height"] == 64


def test_mismatched_or_still_open_file_never_completes(tmp_path, monkeypatch):
    html, expected = create_fixture(tmp_path / "fixture")
    target = html.parent / "fixture-original.png"
    monkeypatch.setattr(native_probe, "exclusive_digest", lambda _path: None)
    clock = iter([0, 0, 2])
    monkeypatch.setattr(native_probe.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(native_probe.time, "sleep", lambda _delay: None)
    with pytest.raises(NativeUIError, match="uncertain"):
        wait_for_fixture(target, expected, MagicMock(spec=WindowsUI), timeout=1)


def test_changed_file_after_exclusive_inspection_is_rejected(tmp_path, monkeypatch):
    html, expected = create_fixture(tmp_path / "fixture")
    target = html.parent / "fixture-original.png"
    monkeypatch.setattr(native_probe, "exclusive_digest", lambda _path: expected)
    monkeypatch.setattr(
        native_probe, "verify_image", lambda *_args, **_kwargs: MagicMock(sha256="changed")
    )
    with pytest.raises(NativeUIError, match="changed"):
        wait_for_fixture(target, expected, MagicMock(spec=WindowsUI))


def test_report_write_is_complete_and_replaceable(tmp_path):
    report = tmp_path / "report.json"
    write_report(report, {"status": "manual_review"})
    write_report(report, {"status": "probe_passed"})
    assert json.loads(report.read_text())["status"] == "probe_passed"
    assert not Path(str(report.with_suffix(".tmp"))).exists()


def test_cdp_connection_preserves_browser_native_download_behavior():
    driver = MagicMock()
    native_probe.connect_owned_browser(driver, 12345)
    driver.chromium.connect_over_cdp.assert_called_once_with(
        "http://127.0.0.1:12345",
        no_defaults=True,
        timeout=15_000,
    )


def test_browser_close_requires_process_exit_even_after_cdp_disconnect():
    browser, process = MagicMock(), MagicMock()
    browser.new_browser_cdp_session.return_value.send.side_effect = RuntimeError("Disconnected")
    native_probe.close_probe_browser(browser, process)
    process.wait.assert_called_once_with(timeout=10)
    process.wait.side_effect = subprocess.TimeoutExpired("owned-browser", 10)
    with pytest.raises(NativeUIError, match="did not close"):
        native_probe.close_probe_browser(browser, process)
