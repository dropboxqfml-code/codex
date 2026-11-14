from types import SimpleNamespace
from unittest.mock import MagicMock

from image_monitor import native_ui
from image_monitor.native_ui import WindowsUI


class Node:
    serial = 0

    def __init__(self, role, name="", *, pid=10, hwnd=0, children=()):
        Node.serial += 1
        self.element_info = SimpleNamespace(control_type=role, runtime_id=(Node.serial,))
        self.name = name
        self.pid = pid
        self.handle = hwnd
        self.nodes = list(children)
        self.name_reads = 0
        self.child_reads = 0

    def process_id(self):
        return self.pid

    def window_text(self):
        self.name_reads += 1
        return self.name

    def is_visible(self):
        return True

    def is_enabled(self):
        return True

    def children(self):
        self.child_reads += 1
        return self.nodes


def ui_with(*roots):
    ui = WindowsUI.__new__(WindowsUI)
    ui.desktop = SimpleNamespace(windows=lambda: list(roots))
    ui.process_ids = lambda: {10}
    ui._window_pid = lambda hwnd: 10 if hwnd in {100, 300} else 999
    ui._class_name = lambda hwnd: "Chrome_WidgetWin_1"
    ui.belongs_to_target = lambda hwnd: hwnd in {100, 300}
    ui.assert_ready = MagicMock(side_effect=AssertionError("diagnostics must not validate input"))
    return ui


def test_virtual_menu_root_is_included_without_treating_it_as_input_target():
    item = Node("MenuItem", "이미지를 다른 이름으로 저장…")
    menu = Node("Menu", "Context", children=[item])
    ui = ui_with(menu)
    result = ui.menu_snapshot()
    assert [entry["type"] for entry in result["items"]] == ["Menu", "MenuItem"]
    assert result["items"][0]["is_root"] is True
    assert result["items"][0]["native_hwnd"] == 0
    assert result["unbound_menu_nodes"] == 2
    assert result["errors"] == []
    ui.assert_ready.assert_not_called()


def test_foreign_windows_and_nodes_are_excluded_before_reading_names_or_children():
    foreign_root = Node("Menu", "Private other application", pid=999)
    foreign_child = Node("MenuItem", "Private foreign child", pid=999)
    private_edit = Node("Edit", "secret edit value")
    document = Node("Document", "private page content", children=[private_edit, foreign_child])
    root = Node("Window", "browser page title", hwnd=100, children=[document])
    result = ui_with(foreign_root, root).menu_snapshot()
    assert result["items"] == []
    assert result["foreign_roots_excluded"] == 1
    assert result["foreign_nodes_excluded"] == 1
    assert foreign_root.name_reads == foreign_root.child_reads == 0
    assert foreign_child.name_reads == foreign_child.child_reads == 0
    assert private_edit.name_reads == document.name_reads == root.name_reads == 0


def test_owned_menu_records_native_binding_and_caps_label_length():
    menu = Node("Menu", "Context", hwnd=300, children=[Node("MenuItem", "x" * 200)])
    result = ui_with(menu).menu_snapshot()
    assert result["bound_menu_nodes"] == 2
    assert result["items"][1]["root_hwnd"] == 300
    assert result["items"][1]["root_class"] == "Chrome_WidgetWin_1"
    assert len(result["items"][1]["label"]) == 120


def test_item_node_and_depth_limits_mark_partial_snapshot():
    menu = Node("Menu", children=[Node("MenuItem", str(index)) for index in range(10)])
    ui = ui_with(menu)
    result = ui.menu_snapshot(max_items=2)
    assert len(result["items"]) == 2
    assert result["truncated"] is True
    result = ui.menu_snapshot(max_nodes=2)
    assert result["nodes_scanned"] <= 2
    assert result["truncated"] is True
    result = ui.menu_snapshot(max_depth=0)
    assert len(result["items"]) == 1
    assert result["truncated"] is True


def test_snapshot_keeps_partial_items_and_error_type_without_message():
    good = Node("MenuItem", "Save image as…")
    bad = Node("MenuItem", "unused")

    def stale():
        raise RuntimeError("secret provider details")

    bad.window_text = stale
    menu = Node("Menu", hwnd=100, children=[good, bad])
    result = ui_with(menu).menu_snapshot()
    assert result["items"][1]["label"] == "Save image as…"
    assert result["items"][2]["label"] is None
    assert result["errors"] == ["RuntimeError"]
    assert "secret" not in str(result)


def test_closed_browser_or_unavailable_desktop_does_not_raise():
    ui = ui_with()
    ui.process_ids = MagicMock(side_effect=RuntimeError("private process details"))
    result = ui.menu_snapshot()
    assert result["diagnostic_error_type"] == "RuntimeError"
    assert result["items"] == []
    assert "private" not in str(result)


def test_duplicate_runtime_identity_is_reported_once():
    child = Node("MenuItem", "Save image as…")
    menu = Node("Menu", hwnd=300, children=[child, child])
    result = ui_with(menu).menu_snapshot()
    assert [entry["label"] for entry in result["items"]].count("Save image as…") == 1


def test_time_budget_stops_before_more_provider_traversal(monkeypatch):
    menu = Node("Menu", "Context", hwnd=300, children=[Node("MenuItem", "Save image as…")])
    readings = iter([0, 0, 2])
    monkeypatch.setattr(native_ui.time, "monotonic", lambda: next(readings))
    result = ui_with(menu).menu_snapshot(max_seconds=1)
    assert result["items"] == []
    assert result["truncated"] is True
    assert menu.name_reads == menu.child_reads == 0


def test_invalid_limits_do_not_raise_over_the_original_failure():
    result = ui_with().menu_snapshot(max_items=0)
    assert result["diagnostic_error_type"] == "ValueError"
    assert result["items"] == []
