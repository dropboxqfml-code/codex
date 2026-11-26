import ctypes
import sys
from ctypes import wintypes
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from image_monitor import native_ui
from image_monitor.native_ui import NativeFocusError, NativeUIError, WindowsUI


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
    ui._top_level_hwnds = MagicMock(return_value=list(graph))

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
    ui.desktop.window.side_effect = lambda *, handle: SimpleNamespace(
        wrapper_object=lambda: wrapper(handle)
    )
    return ui


def wrapper(hwnd):
    window = MagicMock()
    window.handle = hwnd
    window.process_id.return_value = 999 if hwnd == 999 else 10
    window.element_info = SimpleNamespace(control_type="Window", identity=hwnd)
    return window


def test_incomplete_native_window_enumeration_cannot_establish_uniqueness(monkeypatch):
    def partial_enumeration(callback, context):
        callback(100, context)
        raise OSError("Desktop enumeration was interrupted")

    monkeypatch.setitem(
        sys.modules, "win32gui", SimpleNamespace(EnumWindows=partial_enumeration, error=OSError)
    )
    with pytest.raises(NativeUIError, match="enumerate native top-level windows"):
        WindowsUI._top_level_hwnds()


def test_locked_desktop_stops_before_foreground_inspection():
    ui = desktop_guard(available=False)
    with pytest.raises(NativeUIError, match="desktop unavailable") as caught:
        ui.assert_ready()
    assert not isinstance(caught.value, NativeFocusError)
    ui.user32.GetForegroundWindow.assert_not_called()


def test_secure_desktop_is_rejected_and_handle_closed():
    ui = desktop_guard(name="Winlogon")
    with pytest.raises(NativeUIError, match="not active") as caught:
        ui.assert_ready()
    assert not isinstance(caught.value, NativeFocusError)
    ui.user32.CloseDesktop.assert_called_once_with(1)
    ui.user32.GetForegroundWindow.assert_not_called()


def test_other_app_focus_is_rejected():
    ui = desktop_guard(foreground_pid=999)
    with pytest.raises(NativeFocusError, match="outside") as caught:
        ui.assert_ready()
    assert isinstance(caught.value, NativeUIError)


@pytest.fixture
def foreground_sleeps(monkeypatch):
    sleeps = []
    clock = SimpleNamespace(monotonic=lambda: sum(sleeps), sleep=sleeps.append)
    monkeypatch.setattr(native_ui, "time", clock)
    return sleeps


def test_launch_wait_observes_null_and_another_app_until_the_target_gets_focus(foreground_sleeps):
    ui = desktop_guard()
    ui.user32.GetForegroundWindow.side_effect = [None, 999, 100]
    ui.wait_for_initial_foreground(timeout=1)
    assert foreground_sleeps == [0.2, 0.2]
    assert ui._top_level_hwnds.call_count == ui.user32.OpenInputDesktop.call_count == 3
    ui.user32.SetForegroundWindow.assert_not_called()
    ui.user32.SetFocus.assert_not_called()
    ui.user32.SendInput.assert_not_called()


@pytest.mark.parametrize("foreground", [0, 999])
def test_launch_wait_times_out_without_claiming_or_activating_a_window(
    foreground_sleeps, foreground
):
    ui = desktop_guard(foreground_hwnd=foreground)
    with pytest.raises(NativeFocusError, match="outside the bound"):
        ui.wait_for_initial_foreground(timeout=0.3)
    assert sum(foreground_sleeps) == pytest.approx(0.3)
    ui.user32.SetForegroundWindow.assert_not_called()


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"name": "Winlogon"}, "not active"),
        ({"available": False}, "desktop unavailable"),
        ({"foreground_hwnd": 77}, "foreground window is invalid"),
        ({"foreground_hwnd": 200}, "different window"),
        ({"foreground_hwnd": 300}, "different window"),
    ],
)
def test_launch_wait_aborts_on_unsafe_desktop_or_frame(foreground_sleeps, settings, message):
    ui = desktop_guard(**settings)
    with pytest.raises(NativeUIError, match=message) as error:
        ui.wait_for_initial_foreground(timeout=1)
    assert not isinstance(error.value, NativeFocusError)
    assert foreground_sleeps == []


def test_launch_wait_rechecks_unique_binding_every_poll(foreground_sleeps):
    ui = desktop_guard(foreground_hwnd=999)
    ui._top_level_hwnds.side_effect = [[100], []]
    with pytest.raises(NativeUIError, match="bound probe window"):
        ui.wait_for_initial_foreground(timeout=1)
    assert foreground_sleeps == [0.2]


def test_launch_wait_rejects_disabled_target_even_if_it_is_foreground(foreground_sleeps):
    ui = desktop_guard()
    ui.user32.IsWindowEnabled.return_value = False
    with pytest.raises(NativeUIError, match="disabled"):
        ui.wait_for_initial_foreground(timeout=1)
    assert foreground_sleeps == []


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


def test_edge_korean_image_save_name_is_recognized_without_selecting_page_save():
    ui, items = menu_ui(["다른 이름으로 페이지 저장", "다른 이름으로 사진 저장(V)"])
    ui.click_save_image_menu()
    items[0].invoke.assert_not_called()
    items[1].invoke.assert_called_once()


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
    import ctypes

    ui = WindowsUI.__new__(WindowsUI)
    ui.ctypes = ctypes
    ui.assert_ready = MagicMock()
    ui.assert_control_ready = MagicMock()
    dialog, edit, button, host = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    dialog.class_name.return_value = "#32770"
    dialog.window_text.return_value = "다른 이름으로 저장"
    dialog.is_visible.return_value = True
    dialog.handle = 123
    dialog.process_id.return_value = 10
    ui.user32 = MagicMock()
    ui.user32.GetForegroundWindow.return_value = 123
    ui.user32.IsWindow.side_effect = lambda hwnd: hwnd != 123 or not button.invoke.called
    ui.user32.IsWindowVisible.return_value = True
    ui.user32.SendMessageTimeoutW.return_value = 1
    ui.user32.GetParent.return_value = 125
    ui.process_ids = lambda: {10}
    ui.belongs_to_target = lambda hwnd: hwnd in {123, 124, 125}
    ui._window_pid = lambda _hwnd: 10
    ui._class_name = lambda hwnd: "Edit" if hwnd == 124 else "#32770"
    ui._root_window = lambda _hwnd: 123
    ui._window_text = lambda _hwnd: "다른 이름으로 저장"
    ui.desktop = SimpleNamespace(
        window=lambda **_kwargs: SimpleNamespace(wrapper_object=lambda: dialog)
    )
    target = "C:\\IMProbe\\job\\_staging\\native-image.png"
    edit.element_info.automation_id = "1001"
    edit.handle = edit.element_info.handle = 124
    edit.process_id.return_value = 10
    edit.parent.return_value = host
    edit.is_visible.return_value = True
    edit.get_value.side_effect = [
        "브라우저 기본.png",
        target if retains_path else "other.png",
        target,
    ]
    button.element_info.automation_id = "1"
    button.window_text.return_value = "저장(&S)"
    button.is_enabled.return_value = True
    host.element_info.automation_id = "FileNameControlHost"
    host.element_info.control_type = "ComboBox"
    host.handle = host.element_info.handle = 125
    host.process_id.return_value = 10
    host.is_visible.return_value = True
    host.children.return_value = [edit]
    dialog.descendants.side_effect = lambda control_type: [
        host if control_type == "ComboBox" else button
    ]
    ui.owned_windows = MagicMock(side_effect=AssertionError("UIA desktop can omit the dialog"))
    ui.wait_for = lambda lookup: lookup()
    if retains_path:
        assert ui.save_dialog(target) == "브라우저 기본.png"
        button.invoke.assert_called_once()
    else:
        with pytest.raises(NativeUIError, match="exact staging path"):
            ui.save_dialog(target)
        button.invoke.assert_not_called()
    assert ui.browser_suggested_filename == "브라우저 기본.png"
    edit.set_edit_text.assert_not_called()


def test_same_process_other_window_focus_is_rejected():
    ui = desktop_guard(foreground_hwnd=200)
    with pytest.raises(NativeUIError, match="outside the bound"):
        ui.assert_ready()


def test_owned_modal_remains_usable_when_uia_omits_its_parent_browser():
    ui = desktop_guard(foreground_hwnd=300)
    # UIA presents the modal dialog as its only top-level element. Win32 still
    # sees the bound browser HWND and the dialog's owner chain.
    dialog = wrapper(300)
    ui.desktop.windows.return_value = [dialog]
    ui.user32.IsWindowEnabled.side_effect = lambda hwnd: hwnd != 100
    ui.assert_control_ready(dialog, dialog)
    with pytest.raises(NativeFocusError, match="page itself") as caught:
        ui.assert_target_ready()
    assert isinstance(caught.value, NativeUIError)


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
    with pytest.raises(NativeUIError, match="bound probe window") as caught:
        ui.assert_target_ready()
    assert not isinstance(caught.value, NativeFocusError)
    ui = desktop_guard()
    ui.window_graph[200] = (10, 0, 200, "Chrome_WidgetWin_1", "Unique probe 123 - Edge")
    with pytest.raises(NativeUIError, match="ambiguous") as caught:
        ui.assert_ready()
    assert not isinstance(caught.value, NativeFocusError)


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


def test_focus_snapshot_identifies_unrelated_window_without_titles_or_input():
    ui = desktop_guard(foreground_hwnd=999)
    ui.assert_ready = MagicMock(side_effect=AssertionError("Snapshot must not use an input guard"))

    assert ui.focus_snapshot() == {
        "target_hwnd": 100,
        "foreground_hwnd": 999,
        "foreground_pid": 999,
        "foreground_class": "Chrome_WidgetWin_1",
        "target_exists": True,
        "belongs_to_target": False,
        "target_foreground": False,
    }

    ui.assert_ready.assert_not_called()
    ui.user32.GetWindowTextLengthW.assert_not_called()
    ui.user32.GetWindowTextW.assert_not_called()
    ui.user32.SetForegroundWindow.assert_not_called()


def test_focus_snapshot_distinguishes_owned_dialog_from_page_foreground():
    ui = desktop_guard(foreground_hwnd=300)
    result = ui.focus_snapshot()
    assert result["foreground_class"] == "#32770"
    assert result["belongs_to_target"] is True
    assert result["target_foreground"] is False
    assert "diagnostic_error_type" not in result


def test_focus_snapshot_keeps_partial_diagnostics_when_browser_process_disappears():
    ui = desktop_guard(foreground_hwnd=999)
    ui.process_ids = MagicMock(side_effect=NativeUIError("Private failure message must not leak"))

    result = ui.focus_snapshot()

    assert result["foreground_hwnd"] == 999
    assert result["foreground_pid"] == 999
    assert result["foreground_class"] == "Chrome_WidgetWin_1"
    assert result["target_exists"] is None
    assert result["belongs_to_target"] is None
    assert result["target_foreground"] is None
    assert result["diagnostic_error_type"] == "NativeUIError"
    assert "Private failure" not in str(result)
    ui.user32.GetWindowTextW.assert_not_called()


def test_focus_snapshot_handles_closed_or_replaced_target_window():
    ui = desktop_guard(foreground_hwnd=999)
    del ui.window_graph[100]
    result = ui.focus_snapshot()
    assert result["target_exists"] is False
    assert result["belongs_to_target"] is False
    assert result["target_foreground"] is False

    ui = desktop_guard(foreground_hwnd=100)
    ui.window_graph[100] = (999, 0, 100, "Chrome_WidgetWin_1", "Private unrelated title")
    result = ui.focus_snapshot()
    assert result["target_exists"] is False
    assert result["belongs_to_target"] is False
    assert result["target_foreground"] is False
    assert "Private unrelated title" not in str(result)


def test_focus_snapshot_contains_no_input_when_foreground_inspection_fails():
    ui = desktop_guard()
    ui.user32.GetForegroundWindow.side_effect = RuntimeError("Private error detail")
    result = ui.focus_snapshot()
    assert result["foreground_hwnd"] is None
    assert result["diagnostic_error_type"] == "RuntimeError"
    assert "Private error" not in str(result)
    ui.user32.GetWindowTextW.assert_not_called()
    ui.user32.SetForegroundWindow.assert_not_called()


@pytest.mark.parametrize("accepted", [True, False])
@pytest.mark.parametrize("confirmed", [True, False])
def test_null_foreground_can_request_once_but_only_verified_focus_allows_input(
    foreground_sleeps, accepted, confirmed
):
    ui = desktop_guard(foreground_hwnd=0)
    ui.user32.IsIconic.return_value = False
    ui.user32.IsWindowVisible.return_value = True

    def request(hwnd):
        assert hwnd == ui.target_hwnd and sum(foreground_sleeps) >= 1
        # Even if Windows accepts, do not treat that return value as focus evidence.
        if confirmed:
            ui.user32.GetForegroundWindow.return_value = hwnd
        return accepted

    ui.user32.SetForegroundWindow.side_effect = request
    if not confirmed:
        with pytest.raises(NativeFocusError):
            ui.wait_for_initial_foreground(timeout=2)
    else:
        # Windows can also foreground the right window independently after a refusal.
        ui.wait_for_initial_foreground(timeout=2)
    ui.user32.SetForegroundWindow.assert_called_once_with(ui.target_hwnd)
    ui.user32.SendInput.assert_not_called()


@pytest.mark.parametrize("case", ["other_seen", "other_at_request", "hidden", "minimized", "stop"])
def test_foreground_request_respects_active_window_visibility_and_stop(
    foreground_sleeps, monkeypatch, case
):
    ui = desktop_guard(foreground_hwnd=0)
    ui.user32.IsWindowVisible.return_value = case != "hidden"
    ui.user32.IsIconic.return_value = case == "minimized"
    monkeypatch.setattr(native_ui, "trial_stop_requested", lambda: case == "stop")
    if case == "other_seen":
        ui.user32.GetForegroundWindow.side_effect = lambda: 999 if not foreground_sleeps else 0
    if case == "other_at_request":
        ui.user32.IsIconic.side_effect = lambda hwnd: (
            setattr(ui.user32.GetForegroundWindow, "return_value", 999) or False
        )
    with pytest.raises(NativeFocusError):
        ui.wait_for_initial_foreground(timeout=2)
    ui.user32.SetForegroundWindow.assert_not_called()
