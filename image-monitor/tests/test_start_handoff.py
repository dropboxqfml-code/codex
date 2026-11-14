from unittest.mock import MagicMock

import pytest

from image_monitor import native_probe
from image_monitor.native_ui import NativeUIError, WindowsUI


def clock(monkeypatch, values):
    readings = iter(values)
    monkeypatch.setattr(native_probe.time, "monotonic", lambda: next(readings))
    monkeypatch.setattr(native_probe.time, "sleep", lambda _seconds: None)


def test_no_native_checks_or_input_before_user_start(tmp_path, monkeypatch):
    page = MagicMock()
    page.evaluate.return_value = False
    ui = MagicMock(spec=WindowsUI)
    clock(monkeypatch, [0, 0, 2])
    with pytest.raises(NativeUIError, match="Start was not confirmed"):
        native_probe.wait_for_user_start(page, ui, timeout=1)
    ui.assert_target_ready.assert_not_called()
    ui.click_save_image_menu.assert_not_called()
    ui.save_dialog.assert_not_called()
    assert ui.stage == "waiting_for_user_start"


def test_click_and_foreground_are_both_required(monkeypatch):
    page = MagicMock()
    page.evaluate.side_effect = [False, True, True, None]
    ui = MagicMock(spec=WindowsUI)
    ui.assert_target_ready.side_effect = [NativeUIError("Not foreground yet"), None]
    clock(monkeypatch, [0, 0, 0.1, 0.2])
    native_probe.wait_for_user_start(page, ui, timeout=1)
    assert ui.assert_target_ready.call_count == 2
    ui.click_save_image_menu.assert_not_called()
    ui.save_dialog.assert_not_called()


def test_initial_focus_loss_is_passive_and_bounded(monkeypatch):
    page = MagicMock()
    page.evaluate.return_value = True
    ui = MagicMock(spec=WindowsUI)
    ui.assert_target_ready.side_effect = NativeUIError("Other application is active")
    clock(monkeypatch, [0, 0, 2])
    with pytest.raises(NativeUIError, match="Start was not confirmed"):
        native_probe.wait_for_user_start(page, ui, timeout=1)
    ui.click_save_image_menu.assert_not_called()
    ui.save_dialog.assert_not_called()
