from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from image_monitor.browser_completion import (
    BrowserCompletion,
    BrowserCompletionError,
    completion_setup_reason,
)

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
    ("change", "expected"),
    [
        ("page_title", "source_identity_changed"),
        ("page_url", "source_identity_changed"),
        ("window_title", "source_window_changed"),
        ("foreground", "source_foreground_changed"),
        ("hidden", "source_document_hidden"),
        ("focus", "source_document_unfocused"),
    ],
)
def test_background_tab_must_not_change_source_identity_or_focus(owned_browser, change, expected):
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
            elif change == "hidden":
                owned.source.evaluate.return_value = False
            else:
                owned.source.evaluate.side_effect = lambda script: script != "document.hasFocus()"
        return response

    owned.session.send.side_effect = changed_by_creation
    with pytest.raises(BrowserCompletionError) as exc:
        owned.reader.__enter__()
    assert completion_setup_reason(str(exc.value)) == expected
    assert owned.clock.now == 0
    owned.downloads.evaluate.assert_not_called()
    assert owned.session.send.call_args_list[-1].args[0] == "Target.closeTarget"


def test_focus_loss_during_wait_stops_before_reading_a_completion(owned_browser):
    owned = owned_browser
    with pytest.raises(BrowserCompletionError, match="lost foreground"):
        with owned.reader as reader:
            owned.downloads.evaluate.return_value = model([complete_row()])
            owned.ui.user32.GetForegroundWindow.return_value = 456
            reader.wait_for_completion(DESTINATION, SOURCE, owned.ui)
    assert owned.downloads.evaluate.call_count == 1  # Initial, empty model only.


def automatic_reader(owned):
    return BrowserCompletion(
        owned.browser, owned.context, owned.source, "chrome", ui=owned.ui, allow_focus_prompt=True
    )


def focus_controls(owned, attempts=1):
    frame_node, hint = MagicMock(), MagicMock()
    owned.source.evaluate_handle.side_effect = [*([frame_node] * attempts), hint]
    frame = frame_node.as_element.return_value.content_frame.return_value
    frame.url = "about:srcdoc"
    frame_node.evaluate.return_value = True
    return frame_node, frame.wait_for_selector.return_value, hint


def test_settles_visible_source_focus_before_creating_any_reader(owned_browser):
    owned = owned_browser
    original_send = owned.session.send.side_effect

    def ensure_source_settled(command, *args, **kwargs):
        assert owned.clock.now >= 0.3
        return original_send(command, *args, **kwargs)

    owned.source.evaluate.side_effect = lambda script: (
        script != "document.hasFocus()" or owned.clock.now >= 0.3
    )
    owned.session.send.side_effect = ensure_source_settled
    with automatic_reader(owned):
        pass
    assert owned.clock.now == pytest.approx(0.3)
    owned.source.bring_to_front.assert_not_called()
    owned.source.evaluate_handle.assert_not_called()


def test_focus_hint_is_removed_and_model_still_gets_its_bounded_initialization(owned_browser):
    owned = owned_browser
    frame_node, button, hint = focus_controls(owned, attempts=2)
    button.click.side_effect = TimeoutError("Frame is covered")
    owned.source.evaluate.side_effect = lambda script: (
        script != "document.hasFocus()" or owned.clock.now >= 5
    )
    owned.context.pages = [owned.source]
    with pytest.raises(BrowserCompletionError) as exc:
        automatic_reader(owned).__enter__()
    assert completion_setup_reason(str(exc.value)) == "downloads_target_missing"
    assert 13 <= owned.clock.now < 13.3
    assert button.click.call_args_list == [call(trial=True, timeout=1_500)] * 2
    frame_node.evaluate.assert_called_with("node => node.remove()")
    assert frame_node.dispose.call_count == 2
    hint.evaluate.assert_called_once_with("node => node.remove()")
    hint.dispose.assert_called_once()
    owned.source.bring_to_front.assert_not_called()


def test_foreign_window_during_initial_focus_wait_cannot_open_reader(owned_browser):
    owned = owned_browser
    owned.source.evaluate.side_effect = lambda script: script != "document.hasFocus()"
    owned.ui.user32.GetForegroundWindow.side_effect = [123, 123, 456]
    with pytest.raises(BrowserCompletionError, match="lost foreground"):
        automatic_reader(owned).__enter__()
    owned.session.send.assert_not_called()
    assert owned.clock.now == pytest.approx(0.1)
    owned.source.evaluate_handle.assert_not_called()


def test_blurred_visible_document_cannot_open_reader_after_prompt_timeout(owned_browser):
    owned = owned_browser
    frame_node, button, hint = focus_controls(owned, attempts=2)
    frame_node.evaluate.return_value = False  # No longer the original sandboxed frame.
    owned.source.evaluate.side_effect = lambda script: script != "document.hasFocus()"
    with pytest.raises(BrowserCompletionError, match="did not have focus") as exc:
        automatic_reader(owned).__enter__()
    assert owned.clock.now == pytest.approx(20)
    owned.session.send.assert_not_called()
    assert exc.value.setup_focus_stage == "before_target_creation"
    assert exc.value.setup_focus_recovery == "waiting_for_user"
    assert exc.value.setup_focus_loss == "first"
    button.click.assert_not_called()
    assert frame_node.dispose.call_count == 2
    hint.evaluate.assert_called_once_with("node => node.remove()")
    hint.dispose.assert_called_once()
    owned.source.bring_to_front.assert_not_called()


@pytest.mark.parametrize("restored_after_creation", [True, False])
def test_each_setup_phase_can_restore_focus_after_an_earlier_restoration(
    owned_browser, restored_after_creation
):
    owned = owned_browser
    reader = automatic_reader(owned)
    nodes = [MagicMock(), MagicMock()]
    hint = MagicMock()
    focused = False
    owned.source.evaluate.side_effect = lambda script: script != "document.hasFocus()" or focused
    owned.source.evaluate_handle.side_effect = [*nodes, hint]
    buttons = []

    def focus(trial=False, **kwargs):
        nonlocal focused
        if not trial and (reader._target_id is None or restored_after_creation):
            focused = True

    for node in nodes:
        frame = node.as_element.return_value.content_frame.return_value
        frame.url = "about:srcdoc"
        node.evaluate.return_value = True
        button = frame.wait_for_selector.return_value
        button.click.side_effect = focus
        buttons.append(button)

    original = owned.session.send.side_effect

    def blur_after_creation(command, *args, **kwargs):
        nonlocal focused
        if command == "Target.createTarget":
            assert focused
            focused = False
        return original(command, *args, **kwargs)

    owned.session.send.side_effect = blur_after_creation
    if restored_after_creation:
        with reader:
            assert focused
        hint.evaluate.assert_not_called()
    else:
        with pytest.raises(BrowserCompletionError) as exc:
            reader.__enter__()
        assert exc.value.setup_focus_stage == "after_target_creation"
        assert exc.value.setup_focus_recovery == "waiting_for_user"
        assert exc.value.setup_focus_loss == "repeated"
        hint.dispose.assert_called_once()
    for button, node in zip(buttons, nodes, strict=True):
        assert button.click.call_args_list == [call(trial=True, timeout=1_500), call(timeout=1_500)]
        node.evaluate.assert_called_with("node => node.remove()")
        node.dispose.assert_called_once()
    owned.source.bring_to_front.assert_not_called()


def test_ownership_changed_during_actionability_prevents_dispatch(owned_browser):
    owned = owned_browser
    node, button, hint = focus_controls(owned)
    owned.source.evaluate.side_effect = lambda script: script != "document.hasFocus()"

    def change_foreground(*, trial, timeout):
        assert trial and timeout
        owned.ui.user32.GetForegroundWindow.return_value = 456

    button.click.side_effect = change_foreground
    with pytest.raises(BrowserCompletionError, match="lost foreground"):
        automatic_reader(owned).__enter__()
    assert button.click.call_args_list == [call(trial=True, timeout=1_500)]
    node.dispose.assert_called_once()
    hint.evaluate.assert_not_called()
    owned.session.send.assert_not_called()


@pytest.mark.parametrize("ambiguous_dispatch", [True, False], ids=["dispatch_timeout", "restored"])
def test_transient_focus_failures_allow_only_pre_dispatch_retries(
    owned_browser, ambiguous_dispatch
):
    owned = owned_browser
    reader = automatic_reader(owned)
    expected_trials = 1 if ambiguous_dispatch else 2
    node, button, hint = focus_controls(owned, attempts=expected_trials)
    focused = False
    trials = 0
    dispatches = 0

    def transient(trial=False, **kwargs):
        nonlocal focused, trials, dispatches
        if trial:
            trials += 1
            if trials == 1 and not ambiguous_dispatch:
                raise TimeoutError("The iframe is still becoming actionable")
        else:
            dispatches += 1
            if ambiguous_dispatch:
                raise TimeoutError("Click may already have been issued")
            focused = True

    button.click.side_effect = transient
    owned.source.evaluate.side_effect = lambda script: script != "document.hasFocus()" or focused
    if ambiguous_dispatch:
        with pytest.raises(BrowserCompletionError, match="did not have focus"):
            reader.__enter__()
        hint.dispose.assert_called_once()
        owned.session.send.assert_not_called()
    else:
        with reader:
            assert focused
        hint.dispose.assert_not_called()
    assert trials == expected_trials and dispatches == 1
    assert node.dispose.call_count == expected_trials
    owned.source.bring_to_front.assert_not_called()


def test_focus_preflight_that_outlasts_the_deadline_never_dispatches(owned_browser):
    owned = owned_browser
    node, button, _ = focus_controls(owned)
    button.click.side_effect = lambda **kwargs: setattr(owned.clock, "now", 20)
    owned.source.evaluate.side_effect = lambda script: script != "document.hasFocus()"
    with pytest.raises(BrowserCompletionError, match="did not have focus"):
        automatic_reader(owned).__enter__()
    assert button.click.call_args_list == [call(trial=True, timeout=1_500)]
    node.dispose.assert_called_once()
    owned.session.send.assert_not_called()


def test_focus_loss_during_save_does_not_use_startup_grace(owned_browser):
    owned = owned_browser
    with pytest.raises(BrowserCompletionError, match="did not have focus"):
        with owned.reader:
            owned.source.evaluate.side_effect = lambda script: script != "document.hasFocus()"
            owned.reader.wait_for_completion(DESTINATION, SOURCE, owned.ui)
    assert owned.clock.now == 0


def test_private_error_text_is_never_used_as_a_public_setup_reason():
    assert completion_setup_reason("private path " + SOURCE) is None
    assert completion_setup_reason("The bound source page lost its identity or foreground") == (
        "source_identity_or_foreground_changed"
    )


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
