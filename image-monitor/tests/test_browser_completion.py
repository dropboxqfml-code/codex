from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from image_monitor.browser_completion import BrowserCompletion, BrowserCompletionError

SOURCE = "https://cdn.example/image?opaque=private"
DESTINATION = Path("C:/ImageMonitor/_staging/unique-image.png")


def complete_row(**changes):
    return {
        "state": 2,
        "file_path": str(DESTINATION),
        "source_url": SOURCE,
        "danger_type": 0,
        "is_dangerous": False,
        "is_insecure": False,
        "file_externally_removed": False,
        "is_reviewable": False,
        **changes,
    }


def model(rows):
    return {
        "manager_present": True,
        "items_available": True,
        "truncated": False,
        "rows": rows,
    }


@pytest.fixture
def owned_browser(monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr("image_monitor.browser_completion.time.monotonic", lambda: clock.now)
    source = MagicMock()
    source.url = "https://example.com/owned-post"
    source.title.return_value = "Owned source title"
    source.is_closed.return_value = False
    source.evaluate.return_value = True
    source.wait_for_timeout.side_effect = lambda milliseconds: setattr(
        clock, "now", clock.now + milliseconds / 1000
    )
    downloads = MagicMock()
    downloads.url = "chrome://downloads/"
    downloads.is_closed.return_value = False
    downloads.evaluate.return_value = model([])
    context = MagicMock()
    context.pages = [source, downloads]
    page_session = context.new_cdp_session.return_value
    page_session.send.return_value = {
        "targetInfo": {"targetId": "created-target", "url": "chrome://downloads/"}
    }
    browser = MagicMock()
    source.context = context
    context.browser = browser
    browser.contexts = [context]
    session = browser.new_browser_cdp_session.return_value

    def send(command, params=None, **kwargs):
        if command == "Target.createTarget":
            assert params == {"url": "chrome://downloads/", "background": True}
            return {"targetId": "created-target"}
        if command == "Target.closeTarget":
            assert params == {"targetId": "created-target"}
            return {"success": True}
        pytest.fail("Unexpected browser command: " + command)

    session.send.side_effect = send
    ui = MagicMock()
    ui.assert_target_ready = MagicMock()
    ui.target_hwnd = 123
    ui.user32.GetForegroundWindow.return_value = 123
    ui._window_text.return_value = "Owned source title - Google Chrome"
    reader = BrowserCompletion(browser, context, source, "chrome", ui=ui)
    return SimpleNamespace(
        reader=reader,
        browser=browser,
        session=session,
        context=context,
        page_session=page_session,
        source=source,
        downloads=downloads,
        ui=ui,
        clock=clock,
    )


def test_waits_for_own_exact_destination_and_source_then_confirms_complete(owned_browser):
    owned = owned_browser
    with owned.reader as reader:
        owned.downloads.evaluate.side_effect = [
            model([complete_row(file_path="C:/other/image.png")]),
            model([complete_row(state=0)]),
            model([complete_row(file_path="c:\\IMAGEMONITOR\\_staging\\unique-image.png")]),
        ]
        proof = reader.wait_for_completion(DESTINATION, SOURCE, owned.ui, timeout=1)
    assert proof == {
        "state": "COMPLETE",
        "destination_confirmed": True,
        "source_confirmed": True,
        "destination": str(DESTINATION),
        "source_url": SOURCE,
    }
    assert owned.clock.now == pytest.approx(0.2)
    assert [call.args[0] for call in owned.session.send.call_args_list] == [
        "Target.createTarget",
        "Target.closeTarget",
    ]
    owned.page_session.detach.assert_called_once()
    owned.session.detach.assert_called_once()
    owned.source.bring_to_front.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"state": 1},
        {"state": 3},
        {"state": 4},
        {"state": 5},
        {"state": 6},
        {"state": 7},
        {"state": 99},
        {"state": "COMPLETE"},
        {"state": True},
        {"state": 2.0},
        {"is_dangerous": True},
        {"is_insecure": True},
        {"file_externally_removed": True},
        {"is_reviewable": True},
        {"is_insecure": None},
        {"danger_type": 1},
        {"danger_type": False},
        {"danger_type": None},
    ],
)
def test_unknown_or_unsafe_completion_cannot_succeed(owned_browser, changes):
    owned = owned_browser
    with owned.reader as reader:
        owned.downloads.evaluate.return_value = model([complete_row(**changes)])
        with pytest.raises(BrowserCompletionError):
            reader.wait_for_completion(DESTINATION, SOURCE, owned.ui, timeout=1)


@pytest.mark.parametrize("rows", [[], [complete_row(state=0)], [{"file_name": "unique-image.png"}]])
def test_missing_unknown_or_pending_record_waits_then_fails_without_completion(owned_browser, rows):
    owned = owned_browser
    with owned.reader as reader:
        owned.downloads.evaluate.return_value = model(rows)
        with pytest.raises(BrowserCompletionError, match="deadline"):
            reader.wait_for_completion(DESTINATION, SOURCE, owned.ui, timeout=0.2)


def test_exact_destination_with_another_source_is_rejected_without_leaking_source(owned_browser):
    owned = owned_browser
    with owned.reader as reader:
        owned.downloads.evaluate.return_value = model([complete_row(source_url=SOURCE + "wrong")])
        with pytest.raises(BrowserCompletionError, match="source does not match") as error:
            reader.wait_for_completion(DESTINATION, SOURCE, owned.ui)
    assert "private" not in str(error.value)
    assert "ImageMonitor" not in str(error.value)


def test_duplicate_destination_records_are_ambiguous(owned_browser):
    owned = owned_browser
    with owned.reader as reader:
        owned.downloads.evaluate.return_value = model([complete_row(), complete_row()])
        with pytest.raises(BrowserCompletionError, match="Multiple"):
            reader.wait_for_completion(DESTINATION, SOURCE, owned.ui)


@pytest.mark.parametrize(
    "change", ["page_title", "page_url", "window_title", "foreground", "focus"]
)
def test_background_tab_must_not_change_source_identity_or_focus(owned_browser, change):
    owned = owned_browser
    original_send = owned.session.send.side_effect

    def changed_by_creation(command, *args, **kwargs):
        response = original_send(command, *args, **kwargs)
        if command == "Target.createTarget":
            if change == "page_title":
                owned.source.title.return_value = "Changed title"
            elif change == "page_url":
                owned.source.url = "https://example.com/other-post"
            elif change == "window_title":
                owned.ui._window_text.return_value = "Downloads - Google Chrome"
            elif change == "foreground":
                owned.ui.user32.GetForegroundWindow.return_value = 456
            else:
                owned.source.evaluate.return_value = False
        return response

    owned.session.send.side_effect = changed_by_creation
    with pytest.raises(BrowserCompletionError, match="identity or foreground"):
        owned.reader.__enter__()
    assert owned.session.send.call_args_list[-1].args[0] == "Target.closeTarget"


def test_focus_loss_during_wait_stops_before_reading_a_completion(owned_browser):
    owned = owned_browser
    with pytest.raises(BrowserCompletionError, match="identity or foreground"):
        with owned.reader as reader:
            owned.downloads.evaluate.return_value = model([complete_row()])
            owned.ui.user32.GetForegroundWindow.return_value = 456
            reader.wait_for_completion(DESTINATION, SOURCE, owned.ui)
    assert owned.downloads.evaluate.call_count == 1  # Initial, empty model only.


def test_a_different_tab_with_same_internal_url_is_never_inspected(owned_browser):
    owned = owned_browser
    owned.page_session.send.return_value["targetInfo"]["targetId"] = "not-created-target"
    with pytest.raises(BrowserCompletionError, match="not the created target"):
        owned.reader.__enter__()
    owned.downloads.evaluate.assert_not_called()
    owned.session.send.assert_called_with(
        "Target.closeTarget", {"targetId": "created-target"}, timeout=2_000
    )


def test_downloads_model_bound_prevents_ignoring_ambiguous_rows(owned_browser):
    owned = owned_browser
    with owned.reader as reader:
        owned.downloads.evaluate.return_value = {**model([complete_row()]), "truncated": True}
        with pytest.raises(BrowserCompletionError, match="inspection bound"):
            reader.wait_for_completion(DESTINATION, SOURCE, owned.ui)


def test_unsupported_browser_and_missing_ui_fail_before_creating_a_tab(owned_browser):
    owned = owned_browser
    for kind, ui in (("edge", owned.ui), ("chrome", None)):
        with pytest.raises(BrowserCompletionError):
            with BrowserCompletion(owned.browser, owned.context, owned.source, kind, ui=ui):
                pytest.fail("Unverified browser must not enter")
    owned.browser.new_browser_cdp_session.assert_not_called()


@pytest.mark.parametrize("mismatch", ["page_context", "context_browser", "browser_contexts"])
def test_mismatched_context_identity_fails_before_creating_a_tab(owned_browser, mismatch):
    owned = owned_browser
    if mismatch == "page_context":
        owned.source.context = MagicMock()
    elif mismatch == "context_browser":
        owned.context.browser = MagicMock()
    else:
        owned.browser.contexts = [MagicMock()]
    with pytest.raises(BrowserCompletionError, match="outside the supplied owned context"):
        owned.reader.__enter__()
    owned.browser.new_browser_cdp_session.assert_not_called()


def test_missing_model_has_a_bounded_deadline_and_closes_only_created_target(owned_browser):
    owned = owned_browser
    owned.downloads.evaluate.return_value = {
        "manager_present": False,
        "items_available": False,
        "truncated": False,
        "rows": [],
    }
    with pytest.raises(BrowserCompletionError, match="did not become available"):
        owned.reader.__enter__()
    assert 8 <= owned.clock.now < 8.2
    owned.session.send.assert_called_with(
        "Target.closeTarget", {"targetId": "created-target"}, timeout=2_000
    )


def test_close_failure_cannot_report_success_but_preserves_existing_save_failure(owned_browser):
    owned = owned_browser
    original_send = owned.session.send.side_effect

    def fail_close(command, *args, **kwargs):
        if command == "Target.closeTarget":
            return {"success": False}
        return original_send(command, *args, **kwargs)

    owned.session.send.side_effect = fail_close
    with pytest.raises(BrowserCompletionError, match="did not close safely"):
        with owned.reader:
            pass
    assert owned.reader.cleanup_error == "BrowserCompletionError"


def test_cleanup_error_does_not_mask_original_failure(owned_browser):
    owned = owned_browser
    with pytest.raises(ValueError, match="original save failure"):
        with owned.reader:
            owned.session.send.side_effect = RuntimeError("private browser detail")
            raise ValueError("original save failure")
    assert owned.reader.cleanup_error == "RuntimeError"
