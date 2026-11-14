import ctypes
from ctypes import wintypes
from unittest.mock import MagicMock

import pytest

from image_monitor.native_ui import NativeUIError, WindowsUI


def desktop_guard(name="Default", foreground_pid=10, available=True, foreground_hwnd=None):
    ui = WindowsUI.__new__(WindowsUI)
    ui.ctypes = ctypes
    ui.wintypes = wintypes
    ui.expected_window_title = "Unique probe 123"
    ui.target_hwnd = 100
    ui.user32 = MagicMock()
    ui.user32.OpenInputDesktop.return_value = 1 if available else 0
    ui.user32.GetForegroundWindow.return_value = (
        foreground_hwnd if foreground_hwnd is not None else 100 if foreground_pid == 10 else 999
    )
    # hwnd: pid, owner, root, class, title
    graph = {
        100: (10, 0, 100, "Chrome_WidgetWin_1", "Unique probe 123 - Edge"),
        200: (10, 0, 200, "Chrome_WidgetWin_1", "Another tab - Edge"),
        300: (10, 100, 300, "#32770", "Save As"),
        400: (10, 200, 400, "#32770", "Save As"),
        999: (999, 0, 999, "Chrome_WidgetWin_1", "Another browser"),
    }
    ui.window_graph = graph

    def desktop_info(_handle, _index, buffer, _size, _needed):
        buffer.value = name
        return True

    def window_pid(handle, pointer):
        pointer._obj.value = graph.get(handle, (0,))[0]
        return 1 if handle in graph else 0

    def window_text(handle, buffer, _size):
        buffer.value = graph[handle][4]
        return len(buffer.value)

    def class_name(handle, buffer, _size):
        buffer.value = graph[handle][3]
        return len(buffer.value)

    ui.user32.GetUserObjectInformationW.side_effect = desktop_info
    ui.user32.GetWindowThreadProcessId.side_effect = window_pid
    ui.user32.IsWindow.side_effect = lambda handle: handle in graph
    ui.user32.GetWindow.side_effect = lambda handle, _flag: graph[handle][1]
    ui.user32.GetAncestor.side_effect = lambda handle, _flag: graph.get(handle, (0, 0, 0))[2]
    ui.user32.GetWindowTextLengthW.side_effect = lambda handle: len(graph[handle][4])
    ui.user32.GetWindowTextW.side_effect = window_text
    ui.user32.GetClassNameW.side_effect = class_name
    ui.process_ids = lambda: {10}
    ui.desktop = MagicMock()
    ui.desktop.windows.return_value = [wrapper(100)]
    return ui


def wrapper(hwnd):
    window = MagicMock()
    window.handle = hwnd
    window.process_id.return_value = 999 if hwnd == 999 else 10
    return window


def test_locked_desktop_stops_before_foreground_inspection():
    ui = desktop_guard(available=False)
    with pytest.raises(NativeUIError, match="desktop unavailable"):
        ui.assert_ready()
    ui.user32.GetForegroundWindow.assert_not_called()


def test_secure_desktop_is_rejected_and_handle_closed():
    ui = desktop_guard(name="Winlogon")
    with pytest.raises(NativeUIError, match="not active"):
        ui.assert_ready()
    ui.user32.CloseDesktop.assert_called_once_with(1)
    ui.user32.GetForegroundWindow.assert_not_called()


def test_other_app_focus_is_rejected():
    ui = desktop_guard(foreground_pid=999)
    with pytest.raises(NativeUIError, match="outside"):
        ui.assert_ready()


def test_owned_windows_exclude_foreign_browser_and_dialog():
    ui = desktop_guard()
    owned, foreign = wrapper(100), wrapper(999)
    ui.desktop = MagicMock()
    ui.desktop.windows.return_value = [owned, foreign]
    assert ui.owned_windows() == [owned]


def menu_ui(labels):
    ui = WindowsUI.__new__(WindowsUI)
    ui.assert_ready = MagicMock()
    ui.assert_control_ready = MagicMock()
    window = MagicMock()
    items = []
    for label in labels:
        item = MagicMock()
        item.window_text.return_value = label
        item.is_visible.return_value = True
        item.is_enabled.return_value = True
        items.append(item)
    window.descendants.return_value = items
    ui.owned_windows = lambda: [window]

    def once(lookup):
        result = lookup()
        if result is None:
            raise NativeUIError("No identified menu")
        return result

    ui.wait_for = once
    return ui, items


def test_menu_only_invokes_identified_save_image_action():
    ui, items = menu_ui(["Save page as...", "Copy image", "Save image as..."])
    ui.click_save_image_menu()
    items[0].invoke.assert_not_called()
    items[1].invoke.assert_not_called()
    items[2].invoke.assert_called_once()


def test_ambiguous_menu_never_invokes_either_match():
    ui, items = menu_ui(["Save image as...", "Save image as..."])
    with pytest.raises(NativeUIError, match="found 2"):
        ui.click_save_image_menu()
    for item in items:
        item.invoke.assert_not_called()


def test_unknown_menu_never_uses_another_action():
    ui, items = menu_ui(["Save page as...", "Copy image"])
    with pytest.raises(NativeUIError, match="No identified"):
        ui.click_save_image_menu()
    for item in items:
        item.invoke.assert_not_called()


@pytest.mark.parametrize("retains_path", [True, False])
def test_save_dialog_records_suggestion_and_requires_exact_path(retains_path):
    ui = WindowsUI.__new__(WindowsUI)
    ui.assert_ready = MagicMock()
    ui.assert_control_ready = MagicMock()
    dialog, edit, button = MagicMock(), MagicMock(), MagicMock()
    dialog.class_name.return_value = "#32770"
    dialog.window_text.return_value = "다른 이름으로 저장"
    dialog.is_visible.return_value = True
    dialog.handle = 123
    target = "C:\\IMProbe\\job\\_staging\\native-image.png"
    edit.element_info.automation_id = "1001"
    edit.is_visible.return_value = True
    edit.get_value.side_effect = ["브라우저 기본.png", target if retains_path else "other.png"]
    button.element_info.automation_id = "1"
    button.window_text.return_value = "저장(&S)"
    button.is_enabled.return_value = True
    dialog.descendants.side_effect = lambda control_type: [
        edit if control_type == "Edit" else button
    ]
    ui.owned_windows = MagicMock(side_effect=[[dialog], []])
    ui.wait_for = lambda lookup: lookup()
    if retains_path:
        assert ui.save_dialog(target) == "브라우저 기본.png"
        button.invoke.assert_called_once()
    else:
        with pytest.raises(NativeUIError, match="exact staging path"):
            ui.save_dialog(target)
        button.invoke.assert_not_called()
    assert ui.browser_suggested_filename == "브라우저 기본.png"
    edit.set_edit_text.assert_called_once_with(target)


def test_same_process_other_window_focus_is_rejected():
    ui = desktop_guard(foreground_hwnd=200)
    with pytest.raises(NativeUIError, match="outside the bound"):
        ui.assert_ready()


def test_target_owned_dialog_is_allowed_but_page_input_is_not():
    ui = desktop_guard(foreground_hwnd=300)
    ui.assert_ready()
    with pytest.raises(NativeUIError, match="page itself"):
        ui.assert_target_ready()


def test_same_process_other_dialog_owner_is_rejected():
    ui = desktop_guard(foreground_hwnd=400)
    with pytest.raises(NativeUIError, match="outside the bound"):
        ui.assert_ready()


def test_window_enumeration_excludes_other_windows_in_same_process():
    ui = desktop_guard()
    windows = [wrapper(handle) for handle in (100, 200, 300, 400, 999)]
    ui.desktop.windows.return_value = windows
    assert ui.owned_windows() == [windows[0], windows[2]]


def test_owner_chain_cycle_does_not_pass_target_binding():
    ui = desktop_guard()
    ui.window_graph[500] = (10, 600, 500, "#32770", "Save As")
    ui.window_graph[600] = (10, 500, 600, "#32770", "Save As")
    assert not ui.belongs_to_target(500)


def test_target_title_change_or_duplicate_aborts_before_input():
    ui = desktop_guard()
    ui.window_graph[100] = (10, 0, 100, "Chrome_WidgetWin_1", "Other page - Edge")
    with pytest.raises(NativeUIError, match="bound probe window"):
        ui.assert_target_ready()
    ui = desktop_guard()
    ui.window_graph[200] = (10, 0, 200, "Chrome_WidgetWin_1", "Unique probe 123 - Edge")
    ui.desktop.windows.return_value = [wrapper(100), wrapper(200)]
    with pytest.raises(NativeUIError, match="ambiguous"):
        ui.assert_ready()


def test_control_from_same_process_wrong_window_is_rejected():
    ui = desktop_guard()
    control = MagicMock()
    control.process_id.return_value = 10
    control.handle = 0
    control.parent.return_value = wrapper(400)
    with pytest.raises(NativeUIError, match="owner chain"):
        ui.assert_control_ready(control, wrapper(400))
    control.invoke.assert_not_called()


def test_control_reparented_to_another_dialog_is_rejected():
    ui = desktop_guard()
    control = MagicMock()
    control.process_id.return_value = 10
    control.handle = 0
    control.parent.return_value = wrapper(400)
    with pytest.raises(NativeUIError, match="no longer belongs"):
        ui.assert_control_ready(control, wrapper(300))
    control.set_edit_text.assert_not_called()


def test_title_prefix_without_browser_suffix_boundary_is_rejected():
    ui = desktop_guard()
    ui.window_graph[100] = (10, 0, 100, "Chrome_WidgetWin_1", "Unique probe 123-impostor")
    with pytest.raises(NativeUIError, match="bound probe window"):
        ui.assert_target_ready()


def test_save_dialog_control_does_not_act_after_focus_returns_to_page():
    ui = desktop_guard(foreground_hwnd=100)
    control = wrapper(300)
    with pytest.raises(NativeUIError, match="Focus moved"):
        ui.assert_control_ready(control, wrapper(300))
    control.invoke.assert_not_called()


def test_save_dialog_control_accepts_only_its_foreground_window():
    ui = desktop_guard(foreground_hwnd=300)
    control = wrapper(300)
    ui.assert_control_ready(control, wrapper(300))
    control.is_visible.return_value = False
    with pytest.raises(NativeUIError, match="no longer visible"):
        ui.assert_control_ready(control, wrapper(300))
