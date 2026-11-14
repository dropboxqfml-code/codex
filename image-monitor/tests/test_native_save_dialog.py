import ctypes
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from image_monitor.native_ui import NativeUIError, WindowsUI


def dialog_ui(*, native_pid=11, provider_pid=11, provider_hwnd=300, owned=True):
    ui = WindowsUI.__new__(WindowsUI)
    ui.ctypes = ctypes
    ui.assert_ready = MagicMock()
    ui.assert_control_ready = MagicMock()
    ui.process_ids = lambda: {10, 11}
    ui.belongs_to_target = lambda hwnd: owned and hwnd in {100, 300, 301, 302}
    ui._window_pid = lambda _hwnd: native_pid
    ui._class_name = lambda hwnd: (
        "#32770" if hwnd == 300 else "Edit" if hwnd == 301 else "Chrome_WidgetWin_1"
    )
    ui._root_window = lambda hwnd: 300 if hwnd in {301, 302} else hwnd
    ui._window_text = MagicMock(return_value="Save As")
    state = {"visible": True, "exists": True, "saved": False}
    ui.user32 = SimpleNamespace(
        GetForegroundWindow=lambda: 300,
        IsWindow=lambda _hwnd: state["exists"],
        IsWindowVisible=lambda _hwnd: state["visible"],
        GetParent=lambda _hwnd: 302,
        SendMessageTimeoutW=MagicMock(return_value=1),
    )
    dialog, edit, save, host = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    dialog.handle = provider_hwnd
    dialog.process_id.return_value = provider_pid
    dialog.is_visible.return_value = True
    edit.element_info.automation_id = "1001"
    edit.handle = edit.element_info.handle = 301
    edit.process_id.return_value = provider_pid
    edit.parent.return_value = host
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
    host.element_info.automation_id = "FileNameControlHost"
    host.element_info.control_type = "ComboBox"
    host.handle = host.element_info.handle = 302
    host.process_id.return_value = provider_pid
    host.is_visible.return_value = True
    host.children.return_value = [edit]
    dialog.descendants.side_effect = lambda control_type: [
        host if control_type == "ComboBox" else save
    ]
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
    edit.set_edit_text.assert_not_called()
    assert [call.args[1] for call in ui.user32.SendMessageTimeoutW.call_args_list] == [0xB1, 0xC2]
    save.invoke.assert_called_once()
    edit.element_info.element.SetFocus.assert_not_called()
    save.element_info.element.SetFocus.assert_not_called()
    ui.owned_windows.assert_not_called()


def test_native_replacement_notifies_shell_before_save_invoke():
    ui, state, edit, save = dialog_ui()
    target = "C:\\staging\\image.png"
    state.update(focus=None, value="fixture-original.png", committed="fixture-original.png")
    edit.get_value.side_effect = lambda: state["value"]

    def focus_edit():
        state["focus"] = "edit"

    def edit_message(_hwnd, message, _wparam, lparam, _flags, _timeout, _result):
        if message == 0xC2:
            # Native replacement delivers the edit-change notification; a
            # ValuePattern-only change leaves the old accepted name behind.
            state["value"] = state["committed"] = ctypes.wstring_at(lparam)
        return 1

    def invoke_save():
        assert state["committed"] == target
        assert state["focus"] == "edit"
        state["exists"] = False

    edit.element_info.element.SetFocus.side_effect = focus_edit
    ui.user32.SendMessageTimeoutW.side_effect = edit_message
    edit.has_keyboard_focus.side_effect = lambda: state["focus"] == "edit"
    save.invoke.side_effect = invoke_save
    assert ui.save_dialog(target) == "fixture-original.png"
    assert state["committed"] == target
    edit.set_edit_text.assert_not_called()
    edit.set_focus.assert_not_called()
    save.set_focus.assert_not_called()
    save.element_info.element.SetFocus.assert_not_called()


def test_failed_filename_focus_stops_before_text_input_or_save_invoke():
    ui, _state, edit, save = dialog_ui()
    edit.has_keyboard_focus.return_value = False
    with pytest.raises(NativeUIError, match="did not acquire keyboard focus"):
        ui.save_dialog("C:\\staging\\image.png")
    save.invoke.assert_not_called()
    ui.user32.SendMessageTimeoutW.assert_not_called()
    edit.set_edit_text.assert_not_called()
    save.element_info.element.SetFocus.assert_not_called()


def test_filename_focus_is_requested_only_when_needed():
    ui, state, edit, save = dialog_ui()
    edit.has_keyboard_focus.side_effect = [False, True]
    save.invoke.side_effect = lambda: state.update(exists=False)
    ui.save_dialog("C:\\staging\\image.png")
    edit.element_info.element.SetFocus.assert_called_once()
    save.element_info.element.SetFocus.assert_not_called()
    save.invoke.assert_called_once()


def test_focus_loss_after_field_selection_prevents_focusing_or_editing():
    ui, _state, edit, save = dialog_ui()
    ui.assert_control_ready.side_effect = [None, NativeUIError("Foreground focus changed")]
    with pytest.raises(NativeUIError, match="Foreground focus changed"):
        ui.save_dialog("C:\\staging\\image.png")
    edit.element_info.element.SetFocus.assert_not_called()
    edit.set_edit_text.assert_not_called()
    save.invoke.assert_not_called()


def test_native_replacement_messages_are_bounded_and_preserve_unicode():
    ui, _state, edit, _save = dialog_ui()
    host = edit.parent()
    target = "C:\\사용자😀\\_staging\\native-image.png"
    edit.get_value.side_effect = None
    edit.get_value.return_value = target
    messages = []

    def send(hwnd, message, wparam, lparam, flags, timeout, _result):
        assert hwnd == 301
        assert flags == 0x22
        assert timeout == 2_000
        if message == 0xB1:
            assert (wparam, lparam) == (0, -1)
        else:
            assert message == 0xC2
            assert wparam == 1
            assert ctypes.wstring_at(lparam) == target
        messages.append(message)
        return 1

    ui.user32.SendMessageTimeoutW.side_effect = send
    dialog = ui.desktop.window().wrapper_object()
    ui._replace_filename_text(edit, host, dialog, target)
    assert messages == [0xB1, 0xC2]
    edit.set_edit_text.assert_not_called()


@pytest.mark.parametrize(
    "invalid",
    ["virtual", "native_class", "native_pid", "native_root", "native_parent", "uia_parent"],
)
def test_native_edit_must_match_the_verified_dialog_and_filename_host(invalid):
    ui, _state, edit, _save = dialog_ui()
    host = edit.parent()
    if invalid == "virtual":
        edit.handle = edit.element_info.handle = 0
    elif invalid == "native_class":
        ui._class_name = lambda _hwnd: "ComboBox"
    elif invalid == "native_pid":
        ui._window_pid = lambda _hwnd: 10  # Still owned, but not this UIA provider's PID.
    elif invalid == "native_root":
        ui._root_window = lambda _hwnd: 100
    elif invalid == "native_parent":
        ui.user32.GetParent = lambda _hwnd: 999
    else:
        edit.parent.return_value = MagicMock()
    dialog = ui.desktop.window().wrapper_object()
    with pytest.raises(NativeUIError, match="does not match its owned native dialog"):
        ui._replace_filename_text(edit, host, dialog, "C:\\staging\\image.png")
    ui.user32.SendMessageTimeoutW.assert_not_called()


@pytest.mark.parametrize("failed_message", [0xB1, 0xC2])
def test_uncertain_native_message_is_never_retried_or_followed_by_save(failed_message):
    ui, _state, edit, save = dialog_ui()
    messages = []

    def send(_hwnd, message, *_args):
        messages.append(message)
        return 0 if message == failed_message else 1

    ui.user32.SendMessageTimeoutW.side_effect = send
    with pytest.raises(NativeUIError, match="did not complete safely"):
        ui.save_dialog("C:\\staging\\image.png")
    assert messages == ([0xB1] if failed_message == 0xB1 else [0xB1, 0xC2])
    save.invoke.assert_not_called()


def test_changed_focus_between_selection_and_replacement_prevents_text_input():
    ui, _state, edit, _save = dialog_ui()
    ui.assert_control_ready.side_effect = [None, None, NativeUIError("Foreground focus changed")]
    dialog = ui.desktop.window().wrapper_object()
    with pytest.raises(NativeUIError, match="Foreground focus changed"):
        ui._replace_filename_text(edit, edit.parent(), dialog, "C:\\staging\\image.png")
    assert [call.args[1] for call in ui.user32.SendMessageTimeoutW.call_args_list] == [0xB1]


def test_edit_search_is_scoped_to_the_exact_filename_host():
    ui, state, edit, save = dialog_ui()
    dialog = ui.desktop.window().wrapper_object()
    save.invoke.side_effect = lambda: state.update(exists=False)
    ui.save_dialog("C:\\staging\\image.png")
    assert [call.kwargs["control_type"] for call in dialog.descendants.call_args_list] == [
        "ComboBox",
        "Button",
    ]
    edit.parent().children.assert_called_once_with(control_type="Edit")


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
