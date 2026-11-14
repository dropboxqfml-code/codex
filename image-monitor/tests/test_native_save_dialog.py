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
    edit.get_value.side_effect = [
        "fixture-original.png",
        "C:\\staging\\image.png",
        "C:\\staging\\image.png",
    ]
    edit.has_keyboard_focus.return_value = True
    save.element_info.automation_id = "1"
    save.window_text.return_value = "Save"
    save.is_enabled.return_value = True
    save.has_keyboard_focus.return_value = True
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


def test_shell_filename_is_committed_by_focus_loss_before_save_invoke():
    ui, state, edit, save = dialog_ui()
    target = "C:\\staging\\image.png"
    state.update(focus=None, value="fixture-original.png", committed="fixture-original.png")
    edit.get_value.side_effect = lambda: state["value"]

    def focus_edit():
        state["focus"] = "edit"

    def set_value(value):
        # This is the observed shell provider: ValuePattern readback alone
        # reports success, but the accepted filename is still the old name.
        state["value"] = value

    def focus_save():
        if state["focus"] == "edit":
            state["committed"] = state["value"]
        state["focus"] = "save"

    def invoke_save():
        assert state["committed"] == target
        assert state["focus"] == "save"
        state["exists"] = False

    edit.element_info.element.SetFocus.side_effect = focus_edit
    edit.set_edit_text.side_effect = set_value
    edit.has_keyboard_focus.side_effect = lambda: state["focus"] == "edit"
    save.element_info.element.SetFocus.side_effect = focus_save
    save.has_keyboard_focus.side_effect = lambda: state["focus"] == "save"
    save.invoke.side_effect = invoke_save
    assert ui.save_dialog(target) == "fixture-original.png"
    assert state["committed"] == target
    edit.set_focus.assert_not_called()
    save.set_focus.assert_not_called()


@pytest.mark.parametrize("denied_control", ["edit", "save"])
def test_failed_control_focus_stops_before_save_invoke(denied_control):
    ui, _state, edit, save = dialog_ui()
    denied = edit if denied_control == "edit" else save
    denied.has_keyboard_focus.return_value = False
    with pytest.raises(NativeUIError, match="did not acquire keyboard focus"):
        ui.save_dialog("C:\\staging\\image.png")
    save.invoke.assert_not_called()
    if denied_control == "edit":
        edit.set_edit_text.assert_not_called()
        save.element_info.element.SetFocus.assert_not_called()


def test_path_changed_during_focus_commit_is_rejected():
    ui, _state, edit, save = dialog_ui()
    edit.get_value.side_effect = [
        "fixture-original.png",
        "C:\\staging\\image.png",
        "fixture-original.png",
    ]
    with pytest.raises(NativeUIError, match="did not commit the exact staging path"):
        ui.save_dialog("C:\\staging\\image.png")
    save.invoke.assert_not_called()


def test_focus_loss_after_field_selection_prevents_focusing_or_editing():
    ui, _state, edit, save = dialog_ui()
    ui.assert_control_ready.side_effect = [None, NativeUIError("Foreground focus changed")]
    with pytest.raises(NativeUIError, match="Foreground focus changed"):
        ui.save_dialog("C:\\staging\\image.png")
    edit.element_info.element.SetFocus.assert_not_called()
    edit.set_edit_text.assert_not_called()
    save.invoke.assert_not_called()


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
