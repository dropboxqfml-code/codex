from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from image_monitor.native_ui import NativeUIError, WindowsUI


@dataclass(frozen=True)
class Element:
    # Equality models UIA CompareElements identity, not wrapper Python identity.
    identity: str
    control_type: str


class Control:
    def __init__(self, identity, role, *, hwnd=None, pid=10, parent=None):
        self.element_info = Element(identity, role)
        self.handle = hwnd
        self.pid = pid
        self.ancestor = parent
        self.parent_reads = 0
        self.invoke = MagicMock()

    def process_id(self):
        return self.pid

    def parent(self):
        self.parent_reads += 1
        return self.ancestor

    def is_visible(self):
        return True

    def is_enabled(self):
        return True


def binding_ui(*, foreground=100, provider_handle=100):
    ui = WindowsUI.__new__(WindowsUI)
    ui.target_hwnd = 100
    ui.assert_ready = MagicMock()
    ui.process_ids = lambda: {10}
    ui.belongs_to_target = lambda hwnd: hwnd in {100, 300}
    ui._root_window = lambda hwnd: hwnd
    ui._window_pid = lambda _hwnd: 10
    ui._class_name = lambda hwnd: "#32770" if hwnd == 300 else "Chrome_WidgetWin_1"
    ui.user32 = SimpleNamespace(
        IsWindow=lambda hwnd: hwnd in {100, 300}, GetForegroundWindow=lambda: foreground
    )
    rebound = []

    def bind(*, handle):
        rebound.append(handle)
        # Fresh wrapper: identity is equal even though this is a different object
        # and UIA can omit its NativeWindowHandle property.
        root = Control(f"window-{handle}", "Window", hwnd=provider_handle)
        return SimpleNamespace(wrapper_object=lambda: root)

    ui.desktop = SimpleNamespace(window=bind)
    return ui, rebound


def test_observed_chromium_intermediate_pane_hwnd_does_not_replace_real_window_root():
    ui, rebound = binding_ui(provider_handle=None)
    desktop = Control("desktop", "Pane", hwnd=999, pid=999)
    root = Control("window-100", "Window", hwnd=100, parent=desktop)
    current = root
    chain = []
    # The observed CI chain includes a Pane whose GA_ROOT is itself (66158),
    # before a later real browser Window. It must be traversed, not accepted.
    for index, (role, hwnd) in enumerate(
        reversed(
            [
                ("MenuItem", None),
                ("Menu", None),
                ("Pane", None),
                ("Pane", None),
                ("MenuBar", None),
                ("Pane", None),
                ("Pane", 66158),
                ("Pane", None),
            ]
        )
    ):
        current = Control(f"ancestor-{index}", role, hwnd=hwnd, parent=current)
        chain.append(current)

    ui.assert_control_ready(current, root)

    assert rebound == [100]
    assert root.parent_reads == 0  # Never traverse beyond the proven root.
    assert next(node for node in chain if node.handle == 66158).handle == 66158
    current.invoke.assert_not_called()


def test_same_process_different_window_cannot_supply_a_menu_item():
    ui, _rebound = binding_ui()
    expected = Control("window-100", "Window", hwnd=100)
    wrong = Control("window-200", "Window", hwnd=200)
    item = Control("item", "MenuItem", parent=wrong)
    with pytest.raises(NativeUIError, match="no longer belongs"):
        ui.assert_control_ready(item, expected)
    item.invoke.assert_not_called()


def test_web_document_aria_menu_is_rejected_even_under_the_owned_window():
    ui, _rebound = binding_ui()
    root = Control("window-100", "Window", hwnd=100)
    document = Control("web-page", "Document", parent=root)
    menu = Control("spoofed-menu", "Menu", parent=document)
    item = Control("spoofed-item", "MenuItem", parent=menu)
    with pytest.raises(NativeUIError, match="Document"):
        ui.assert_control_ready(item, root)
    item.invoke.assert_not_called()


def test_foreign_process_ancestor_is_rejected_before_its_parent_is_read():
    ui, _rebound = binding_ui()
    root = Control("window-100", "Window", hwnd=100)
    foreign = Control("foreign", "Pane", pid=999, parent=root)
    item = Control("item", "MenuItem", parent=foreign)
    with pytest.raises(NativeUIError, match="no longer belongs"):
        ui.assert_control_ready(item, root)
    assert foreign.parent_reads == 0


def test_virtual_parent_cycle_is_rejected_with_bounded_reads():
    ui, _rebound = binding_ui()
    root = Control("window-100", "Window", hwnd=100)
    first = Control("cycle-a", "Pane")
    second = Control("cycle-b", "Pane", parent=first)
    first.ancestor = second
    item = Control("item", "MenuItem", parent=first)
    with pytest.raises(NativeUIError, match="no longer belongs"):
        ui.assert_control_ready(item, root)
    assert first.parent_reads == second.parent_reads == 1


def test_native_ownership_and_foreground_are_still_required():
    ui, _rebound = binding_ui(foreground=100)
    dialog = Control("window-300", "Window", hwnd=300)
    edit = Control("filename", "Edit", parent=dialog)
    with pytest.raises(NativeUIError, match="Focus moved"):
        ui.assert_control_ready(edit, dialog)
