from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from image_monitor.native_ui import NativeUIError, WindowsUI


def dialog_ui(*, native_pid=11, provider_pid=11, provider_hwnd=300, owned=True):
    ui = WindowsUI.__new__(WindowsUI)
    ui.assert_ready = MagicMock()
    ui.assert_control_ready = MagicMock()
    ui.process_ids = lambda: {10, 11}
    ui.belongs_to_target = lambda hwnd: owned and hwnd in {100, 300}
    ui._window_pid = lambda _hwnd: native_pid
    ui._class_name = lambda hwnd: "#32770" if hwnd == 300 else "Chrome_WidgetWin_1"
    ui._window_text = MagicMock(return_value="Save As")
    state = {"visible": True, "exists": True, "saved": False}
    ui.user32 = SimpleNamespace(
        GetForegroundWindow=lambda: 300,
        IsWindow=lambda _hwnd: state["exists"],
        IsWindowVisible=lambda _hwnd: state["visible"],
    )
    dialog, edit, save = MagicMock(), MagicMock(), MagicMock()
    dialog.handle = provider_hwnd
    dialog.process_id.return_value = provider_pid
    dialog.is_visible.return_value = True
    edit.element_info.automation_id = "1001"
    edit.is_visible.return_value = True
    edit.get_value.side_effect = ["fixture-original.png", "C:\\staging\\image.png"]
    save.element_info.automation_id = "1"
    save.window_text.return_value = "Save"
    save.is_enabled.return_value = True
    dialog.descendants.side_effect = lambda control_type: [edit if control_type == "Edit" else save]
    ui.desktop = SimpleNamespace(
        window=MagicMock(return_value=SimpleNamespace(wrapper_object=lambda: dialog))
    )
    # This is the observed Edge tree: the picker exists but is not a direct
    # desktop UIA child. Selection and closure must not depend on that view.
    ui.owned_windows = MagicMock(side_effect=AssertionError("nested dialog omitted by desktop UIA"))
    ui.wait_for = lambda lookup: lookup()
    return ui, state, edit, save


def test_owned_descendant_process_dialog_uses_its_actual_foreground_hwnd():
    ui, state, edit, save = dialog_ui()
    save.invoke.side_effect = lambda: state.update(exists=False)
    result = ui.save_dialog("C:\\staging\\image.png")
    assert result == "fixture-original.png"
    ui.desktop.window.assert_called_once_with(handle=300)
    edit.set_edit_text.assert_called_once_with("C:\\staging\\image.png")
    save.invoke.assert_called_once()
    ui.owned_windows.assert_not_called()


@pytest.mark.parametrize("option", [{"native_pid": 999}, {"owned": False}])
def test_unrelated_dialog_is_rejected_before_reading_its_caption_or_controls(option):
    ui, _state, edit, save = dialog_ui(**option)
    with pytest.raises(NativeUIError, match="outside the owned"):
        ui.save_dialog("C:\\staging\\image.png")
    ui._window_text.assert_not_called()
    ui.desktop.window.assert_not_called()
    edit.set_edit_text.assert_not_called()
    save.invoke.assert_not_called()


@pytest.mark.parametrize("option", [{"provider_pid": 10}, {"provider_hwnd": 100}])
def test_provider_must_match_the_guarded_native_hwnd_and_pid(option):
    ui, _state, edit, save = dialog_ui(**option)
    with pytest.raises(NativeUIError, match="provider does not match"):
        ui.save_dialog("C:\\staging\\image.png")
    edit.set_edit_text.assert_not_called()
    save.invoke.assert_not_called()


@pytest.mark.parametrize("closed_by", ["destroyed", "hidden"])
def test_dialog_closure_waits_for_native_state_not_the_incomplete_uia_desktop(closed_by):
    ui, state, _edit, save = dialog_ui()
    polls = []

    def waiting(lookup):
        if not state["saved"]:
            return lookup()
        # The dialog still exists and is visible after Save was invoked. An
        # empty UIA desktop result must not make this poll report completion.
        polls.append(lookup())
        assert polls[-1] is None
        state["exists" if closed_by == "destroyed" else "visible"] = False
        polls.append(lookup())
        assert polls[-1] is True
        return True

    ui.wait_for = waiting
    save.invoke.side_effect = lambda: state.update(saved=True)
    assert ui.save_dialog("C:\\staging\\image.png") == "fixture-original.png"
    assert polls == [None, True]
    ui.owned_windows.assert_not_called()
