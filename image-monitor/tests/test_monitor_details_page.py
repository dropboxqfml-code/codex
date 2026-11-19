"""Exercise the bounded candidate-detail controls in a real local-only browser."""

import copy
import json
import shutil
import sys
from types import SimpleNamespace

import pytest

from image_monitor import PUBLIC_VERSION
from image_monitor.monitor_page import render_monitor_page

BASE_URL = "http://127.0.0.1:39781/owned-test-capability/"


def initial_status(**changes):
    return {
        "phase": "stopped",
        "task_kind": "list",
        "browser": "chrome",
        "interval_seconds": 60,
        "completed_cycles": 2,
        "candidate_count": 3,
        "new_candidates": 3,
        "baseline_initialized": True,
        "last_scan_at": "2026-11-17T08:00:00+00:00",
        "next_eligible_at": None,
        "remaining_seconds": 0,
        "reason": None,
        "gap_reason": None,
        "browser_closed": True,
        "settings_editable": True,
        "detail_count": 0,
        "detail_pending_count": 3,
        "detail_completed_count": 0,
        "detail_failed_count": 0,
        "details": [],
    } | changes


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    if sys.platform == "win32":
        from image_monitor.native_probe import browser_executable

        executable = str(browser_executable("chrome"))
    else:
        executable = shutil.which("chromium") or shutil.which("google-chrome")
    if not executable:
        pytest.skip("Installed Chromium unavailable")
    with playwright.sync_playwright() as driver:
        owned = driver.chromium.launch(
            executable_path=executable,
            headless=True,
            args=["--disable-background-networking"],
        )
        try:
            yield owned
        finally:
            owned.close()


@pytest.fixture
def portal(browser):
    context = browser.new_context(accept_downloads=False)
    page = context.new_page()
    state = SimpleNamespace(snapshot=initial_status(), actions=[], requests=[], closing=False)

    def dispatch(route):
        request = route.request
        state.requests.append(request.url)
        if request.url == BASE_URL:
            route.fulfill(
                status=200,
                content_type="text/html; charset=utf-8",
                body=render_monitor_page(script_nonce="owned-page-test-nonce"),
            )
            return
        if request.url == BASE_URL + "api/action" and request.method == "POST":
            payload = request.post_data_json
            state.actions.append(payload)
            action = payload["action"]
            if action == "inspect_candidates":
                state.snapshot.update(
                    task_kind="details", phase="inspecting", settings_editable=False
                )
            elif action == "pause":
                state.snapshot.update(phase="paused")
            elif action == "start":
                state.snapshot.update(phase="waiting")
            elif action == "stop":
                state.snapshot.update(phase="stopped", settings_editable=True)
            elif action == "exit":
                state.closing = True
            else:
                pytest.fail("Unexpected page action")
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


def test_detail_button_uses_bounded_action_and_preserves_pause_resume_stop_and_exit(portal):
    from playwright.sync_api import expect

    state, page = portal
    page.goto(BASE_URL, wait_until="domcontentloaded")
    button = page.locator("#inspect-candidates")
    expect(button).to_be_enabled()
    expect(page.locator("#details-counts")).to_have_text("완료 0개 · 확인 필요 0개 · 미시도 3개")
    button.click()
    expect(page.locator("#status-title")).to_have_text("후보 내용을 확인하고 있습니다.")
    expect(button).to_be_disabled()
    expect(page.locator("#start")).to_be_disabled()
    expect(page.locator("#interval")).to_be_disabled()
    page.get_by_role("button", name="일시정지", exact=True).click()
    expect(page.locator("#status-title")).to_have_text("후보 내용 확인을 잠시 멈췄습니다.")
    page.get_by_role("button", name="내용 확인 계속", exact=True).click()
    expect(page.locator("#status-title")).to_have_text("다음 후보 확인을 기다리고 있습니다.")
    page.get_by_role("button", name="중지", exact=True).click()
    expect(page.locator("#status-title")).to_have_text("후보 내용 확인을 마쳤습니다.")
    expect(page.locator("#status-detail")).to_contain_text("자동으로 다시 시작하지 않습니다")
    expect(page.locator("#start")).to_have_text("감시 시작")
    expect(button).to_be_enabled()
    expect(page.locator("#candidate-count")).to_have_text("3")
    expect(page.locator("#cycle-count")).to_have_text("2")
    page.get_by_role("button", name="프로그램 종료", exact=True).click()
    expect(button).to_be_disabled()
    assert state.actions == [
        {"action": "inspect_candidates"},
        {"action": "pause"},
        {"action": "start"},
        {"action": "stop"},
        {"action": "exit"},
    ]
    assert all(value.startswith(BASE_URL) for value in state.requests)


def test_automatic_candidate_turn_shows_next_action_then_returns_to_the_list(portal):
    from playwright.sync_api import expect

    state, page = portal
    state.snapshot.update(
        task_kind="auto_details", phase="waiting", settings_editable=False, remaining_seconds=60
    )
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.locator(".brand-caption")).to_have_text(PUBLIC_VERSION)
    expect(page.locator("#status-title")).to_have_text("후보 자동 확인을 기다리고 있습니다.")
    expect(page.locator("#countdown")).to_have_text("1분 0초 후")
    expect(page.locator("#auto-details-checked")).to_have_text("0")
    expect(page.locator("#inspect-candidates")).to_be_disabled()
    expect(page.locator("#stop")).to_be_enabled()
    page.locator("#pause").click()
    expect(page.locator("#start")).to_have_text("계속 감시")
    page.locator("#start").click()
    expect(page.locator("#status-title")).to_have_text("후보 자동 확인을 기다리고 있습니다.")
    state.snapshot.update(phase="inspecting", browser_closed=None)
    expect(page.locator("#status-title")).to_have_text("후보 내용을 자동으로 확인하고 있습니다.")
    state.snapshot.update(task_kind="list", phase="waiting", auto_details_checked=1)
    expect(page.locator("#status-title")).to_have_text("다음 목록 확인을 기다리고 있습니다.")
    expect(page.locator("#auto-details-checked")).to_have_text("1")
    expect(page.locator("#cycle-count")).to_have_text("2")
    assert state.actions == [{"action": "pause"}, {"action": "start"}]


@pytest.mark.parametrize(
    "changes",
    [
        {"phase": "waiting", "settings_editable": False},
        {"phase": "needs_review"},
        {"settings_editable": False},
        {"browser_closed": None},
        {"candidate_count": 0},
        {"detail_pending_count": 0},
    ],
)
def test_detail_action_is_unavailable_without_stopped_owned_idle_pending_work(portal, changes):
    from playwright.sync_api import expect

    state, page = portal
    state.snapshot.update(changes)
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.locator("#connection-text")).to_have_text("연결됨")
    expect(page.locator("#inspect-candidates")).to_be_disabled()
    assert state.actions == []


def test_anonymous_detail_rows_use_fixed_labels_and_never_execute_untrusted_metadata(portal):
    from playwright.sync_api import expect

    state, page = portal
    injected = '<img src="https://foreign.example/x" onerror="window.untrustedExecuted=1">'
    rows = [
        {
            "order": 1,
            "status": "completed",
            "time_status": "at_or_after_baseline",
            "reason": injected,
            "image_count": 2,
            "pending_images": 0,
            "title": injected,
        },
        {
            "order": 2,
            "status": "failed",
            "time_status": "before_baseline",
            "image_count": None,
            "pending_images": 1,
        },
        {"order": 3, "status": "__proto__", "time_status": "toString"},
    ]
    state.snapshot.update(
        task_kind="details",
        detail_count=3,
        detail_pending_count=0,
        detail_completed_count=1,
        detail_failed_count=2,
        details=rows,
    )
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.locator("#details-table")).to_be_visible()
    expect(page.locator("#details-empty")).to_be_hidden()
    expect(page.locator("#details-counts")).to_have_text("완료 1개 · 확인 필요 2개 · 미시도 0개")
    table = page.locator("#detail-rows")
    expect(table).to_contain_text("감시 기준 시각 이후")
    expect(table).to_contain_text("감시 기준 시각 이전")
    expect(table).to_contain_text("로딩 미완료 1개")
    expect(table.locator("tr")).to_have_count(3)
    expect(table.locator("tr").nth(2)).to_have_text("확인 3확인 필요확인 못함확인 못함")
    assert "foreign.example" not in table.inner_text()
    assert page.evaluate("window.untrustedExecuted") is None
    assert page.locator("img").count() == 0
    assert all(value.startswith(BASE_URL) for value in state.requests)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_detail_rows_are_bounded_and_clear_when_source_becomes_empty(portal):
    from playwright.sync_api import expect

    state, page = portal
    state.snapshot["details"] = [
        {
            "order": i + 1,
            "status": "completed",
            "time_status": "at_or_after_baseline",
            "image_count": 1,
        }
        for i in range(14)
    ]
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.locator("#detail-rows tr")).to_have_count(10)
    state.snapshot.update(candidate_count=0, detail_pending_count=0, details=[])
    expect(page.locator("#details-table")).to_be_hidden()
    expect(page.locator("#detail-rows tr")).to_have_count(0)
    expect(page.locator("#details-empty")).to_contain_text("기록된 후보가 없습니다")


@pytest.mark.parametrize(
    ("reason", "title", "detail"),
    [
        (
            "service_retry_after",
            "후보 내용 확인을 멈췄습니다.",
            "서버 요청으로 내용 확인을 멈췄습니다. 기존 기록과 대기 시간을 유지합니다.",
        ),
        (
            "no_unattempted_candidates",
            "확인할 후보가 없습니다.",
            "아직 내용을 확인하지 않은 후보가 없습니다. 기존 확인 기록은 유지됩니다.",
        ),
        (
            "existing_baseline_required",
            "기존 감시 기준점이 필요합니다.",
            "감시에서 기준점과 새 후보를 기록한 뒤 내용을 확인할 수 있습니다.",
        ),
    ],
)
def test_stopped_detail_reasons_explain_the_outcome_without_claiming_batch_completion(
    portal, reason, title, detail
):
    from playwright.sync_api import expect

    state, page = portal
    state.snapshot.update(task_kind="details", reason=reason)
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.locator("#status-title")).to_have_text(title)
    expect(page.locator("#status-detail")).to_have_text(detail)
    assert state.actions == []


def test_deleted_candidate_uses_a_fixed_unavailable_label(portal):
    from playwright.sync_api import expect

    state, page = portal
    state.snapshot.update(
        details=[
            {
                "order": 1,
                "status": "completed",
                "time_status": "unknown",
                "reason": "candidate_deleted",
                "image_count": None,
            }
        ]
    )
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.locator("#detail-rows tr")).to_contain_text("삭제되었거나 공개되지 않음")
    assert state.actions == []
