"""Exercise existing-work summaries and explicit completion checks in a local browser."""

import copy
import json
from types import SimpleNamespace

import pytest
from test_monitor_details_page import BASE_URL, initial_status
from test_monitor_details_page import browser as browser

from image_monitor.monitor_page import render_monitor_page

COUNTS = {
    "candidate_uninspected": 1,
    "save_ready": 0,
    "save_planned": 0,
    "save_active": 0,
    "save_completed": 2,
    "save_unavailable": 0,
    "save_needs_review": 0,
}


@pytest.fixture
def portal(browser):
    context = browser.new_context(accept_downloads=False)
    page = context.new_page()
    state = SimpleNamespace(
        snapshot=initial_status(
            operations_status="ready",
            operations_reason="candidate_detail_required",
            operations_counts=COUNTS,
            operations_can_finish=True,
            operations_wait_until=None,
            operations_remaining_seconds=0,
            operations_rows=[],
            operations_finish_status=None,
            operations_finish_files_verified=0,
        ),
        actions=[],
        requests=[],
        closing=False,
    )

    def dispatch(route):
        request = route.request
        state.requests.append(request.url)
        if request.url == BASE_URL:
            route.fulfill(
                status=200,
                content_type="text/html; charset=utf-8",
                body=render_monitor_page(script_nonce="owned-operations-test-nonce"),
            )
            return
        if request.url == BASE_URL + "api/action" and request.method == "POST":
            payload = request.post_data_json
            state.actions.append(payload)
            action = payload["action"]
            if action == "refresh_operations":
                state.snapshot.update(
                    task_kind="operations",
                    phase="verifying_operations",
                    operations_status="checking",
                    settings_editable=False,
                )
            elif action == "finish_completed":
                state.snapshot.update(
                    task_kind="finish",
                    phase="finishing_completed",
                    settings_editable=False,
                )
            elif action == "stop":
                state.snapshot.update(phase="stopped", settings_editable=True)
            elif action == "exit":
                state.closing = True
            else:
                pytest.fail("Unexpected operations page action")
        elif request.url != BASE_URL + "api/status" or request.method != "GET":
            pytest.fail("The page made an unexpected request")
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": copy.deepcopy(state.snapshot), "closing": state.closing}),
        )

    context.route("**/*", dispatch)
    try:
        yield state, page
    finally:
        context.close()


def test_current_counts_are_distinct_and_visible_before_scrolling_at_390_pixels(portal):
    from playwright.sync_api import expect

    state, page = portal
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(BASE_URL, wait_until="domcontentloaded")
    panel = page.locator("#operations-panel")
    expect(panel).to_be_visible()
    expect(page.locator("#operation-candidate-uninspected")).to_have_text("1")
    expect(page.locator("#operation-save-completed")).to_have_text("2")
    expect(page.locator("#operations-help")).to_contain_text("내용을 확인하지 않은 후보")
    assert panel.bounding_box()["y"] + panel.bounding_box()["height"] < 844
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert "pending" not in panel.inner_text().lower()
    assert state.actions == []


def test_refresh_and_finish_use_only_fixed_actions_and_keep_stop_exit_responsive(portal):
    from playwright.sync_api import expect

    state, page = portal
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.get_by_role("button", name="작업 현황 새로 확인", exact=True).click()
    expect(page.locator("#status-title")).to_have_text("작업 현황을 확인하고 있습니다.")
    expect(page.locator("#refresh-operations")).to_be_disabled()
    expect(page.locator("#finish-completed")).to_be_disabled()
    expect(page.locator("#pause")).to_be_disabled()
    expect(page.locator("#start")).to_be_disabled()
    page.get_by_role("button", name="중지", exact=True).click()
    expect(page.locator("#finish-completed")).to_be_enabled()
    page.get_by_role("button", name="완료 상태 다시 확인", exact=True).click()
    expect(page.locator("#status-title")).to_have_text("완료 상태를 다시 확인하고 있습니다.")
    expect(page.locator("#status-detail")).to_contain_text("이미지를 새로 저장하지 않습니다")
    expect(page.locator("#finish-completed")).to_be_disabled()
    page.get_by_role("button", name="프로그램 종료", exact=True).click()
    expect(page.locator("#refresh-operations")).to_be_disabled()
    assert state.actions == [
        {"action": "refresh_operations"},
        {"action": "stop"},
        {"action": "finish_completed"},
        {"action": "exit"},
    ]
    assert all(url.startswith(BASE_URL) for url in state.requests)


@pytest.mark.parametrize(
    "changes",
    [
        {"phase": "waiting"},
        {"phase": "paused"},
        {"phase": "stopping"},
        {"phase": "verifying_saved"},
        {"phase": "verifying_operations"},
        {"phase": "verifying_overview"},
        {"phase": "finishing_completed"},
        {"browser_closed": None},
        {"browser_closed": False},
        {"operations_can_finish": False},
        {"operations_can_finish": 1},
    ],
)
def test_finish_is_disabled_without_idle_owned_eligible_completion(portal, changes):
    from playwright.sync_api import expect

    state, page = portal
    state.snapshot.update(changes)
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.locator("#connection-text")).to_have_text("연결됨")
    expect(page.locator("#finish-completed")).to_be_disabled()
    assert state.actions == []


def test_idle_review_allows_readonly_refresh_and_eligible_completion(portal):
    from playwright.sync_api import expect

    state, page = portal
    state.snapshot.update(phase="needs_review", settings_editable=False)
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.locator("#refresh-operations")).to_be_enabled()
    expect(page.locator("#finish-completed")).to_be_enabled()
    state.snapshot["browser_closed"] = None
    expect(page.locator("#finish-completed")).to_be_disabled()
    expect(page.locator("#refresh-operations")).to_be_enabled()
    assert state.actions == []


def test_pending_and_network_wait_causes_use_plain_labels_and_server_countdown(portal):
    from playwright.sync_api import expect

    state, page = portal
    state.snapshot.update(
        operations_status="busy",
        operations_reason="service_cooldown",
        operations_wait_until="2026-11-18T08:02:05+00:00",
        operations_remaining_seconds=125,
        operations_can_finish=False,
    )
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.locator("#operations-help")).to_contain_text("서버가 요청한 대기 시간")
    expect(page.locator("#operations-wait")).to_contain_text("2분 5초 후")
    state.snapshot.update(
        operations_status="needs_review",
        operations_reason="pending_save_requires_review",
        operations_remaining_seconds=124,
    )
    expect(page.locator("#operations-help")).to_contain_text("이전 저장의 보류 사유")
    expect(page.locator("#operations-wait")).to_contain_text("2분 4초 후")
    assert state.actions == []


def test_completion_outcome_reports_verified_existing_files_without_restart(portal):
    from playwright.sync_api import expect

    state, page = portal
    state.snapshot.update(
        task_kind="finish",
        operations_finish_status="batch_finish_completed",
        operations_finish_files_verified=4,
        operations_can_finish=False,
    )
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.locator("#operations-finish")).to_contain_text("파일 4개를 검증")
    expect(page.locator("#status-title")).to_have_text("완료 상태 확인을 마쳤습니다.")
    expect(page.locator("#finish-completed")).to_be_disabled()
    assert state.actions == []


def test_operation_rows_are_bounded_anonymous_and_never_render_untrusted_metadata(portal):
    from playwright.sync_api import expect

    state, page = portal
    injected = '<img src="https://foreign.example/x" onerror="window.untrustedExecuted=1">'
    state.snapshot.update(
        operations_reason=injected,
        operations_rows=[
            {
                "order": index + 1,
                "status": "save_completed",
                "reason": "save_completed",
                "image_count": 2,
                "title": injected,
                "path": "C:/private/image.jpg",
            }
            for index in range(24)
        ],
        operations_rows_omitted=4,
    )
    state.snapshot["operations_rows"][0].update(status="__proto__", reason="toString")
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.locator("#operations-records summary").click()
    expect(page.locator("#operations-rows tr")).to_have_count(20)
    expect(page.locator("#operations-records summary")).to_contain_text("생략 4개")
    assert "private" not in page.locator("#operations-panel").inner_text()
    assert "foreign.example" not in page.locator("#operations-panel").inner_text()
    assert page.evaluate("window.untrustedExecuted") is None
    assert page.locator("img").count() == 0
    assert all(url.startswith(BASE_URL) for url in state.requests)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    state.snapshot["operations_rows"] = []
    expect(page.locator("#operations-records")).to_be_hidden()


@pytest.mark.parametrize("status", [None, "disabled"])
def test_legacy_page_without_configured_work_catalog_keeps_panel_hidden(portal, status):
    from playwright.sync_api import expect

    state, page = portal
    if status is None:
        state.snapshot.pop("operations_status")
    else:
        state.snapshot["operations_status"] = status
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.locator("#operations-panel")).to_be_hidden()
    expect(page.locator("#finish-completed")).to_be_disabled()
    expect(page.locator("#start")).to_be_enabled()
    assert state.actions == []
