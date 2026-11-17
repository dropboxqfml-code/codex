"""Display only cached, same-origin originals in the local saved-result panel."""

import copy
import io
import json
import shutil
import sys
from types import SimpleNamespace

import pytest
from PIL import Image
from test_monitor_details_page import initial_status

from image_monitor.monitor_page import render_monitor_page

BASE_URL = "http://127.0.0.1:39781/owned-saved-capability/"
FIRST_ID = "a" * 32
SECOND_ID = "b" * 32


def saved_file(preview_id=FIRST_ID, **changes):
    return {
        "saved_filename": "001.png",
        "detected_format": "PNG",
        "file_size": 102951,
        "width": 4,
        "height": 3,
        "frames": 1,
        "preview_id": preview_id,
        "preview_available": True,
    } | changes


def ready_status(**changes):
    return (
        initial_status(
            saved_status="ready",
            saved_reason=None,
            saved_error_type=None,
            saved_groups_verified=1,
            saved_files_verified=1,
            saved_files_omitted=0,
            saved_preview_count=1,
            saved_files=[saved_file()],
        )
        | changes
    )


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
    image = io.BytesIO()
    Image.new("RGB", (4, 3), "#137c70").save(image, format="PNG")
    state = SimpleNamespace(
        snapshot=ready_status(),
        actions=[],
        requests=[],
        image_requests=[],
        unexpected=[],
        errors=[],
        closing=False,
        image_status=200,
    )
    page.on("pageerror", lambda error: state.errors.append(str(error)))

    def dispatch(route):
        request = route.request
        state.requests.append(request.url)
        if request.url == BASE_URL:
            route.fulfill(
                status=200,
                content_type="text/html; charset=utf-8",
                body=render_monitor_page(script_nonce="owned-saved-page-nonce"),
            )
            return
        if request.url in {BASE_URL + "images/" + FIRST_ID, BASE_URL + "images/" + SECOND_ID}:
            state.image_requests.append(request.url)
            route.fulfill(
                status=state.image_status,
                content_type="image/png",
                body=image.getvalue() if state.image_status == 200 else b"",
            )
            return
        if request.url == BASE_URL + "api/action" and request.method == "POST":
            payload = request.post_data_json
            state.actions.append(payload)
            if payload == {"action": "refresh_saved"}:
                state.snapshot.update(
                    task_kind="saved",
                    phase="verifying_saved",
                    settings_editable=False,
                    saved_status="checking",
                    saved_files=[],
                    saved_files_verified=0,
                    saved_preview_count=0,
                )
            elif payload == {"action": "stop"}:
                state.snapshot.update(
                    phase="stopped", settings_editable=True, saved_status="cancelled"
                )
            elif payload == {"action": "exit"}:
                state.closing = True
            else:
                state.unexpected.append(payload)
        elif request.url != BASE_URL + "api/status" or request.method != "GET":
            state.unexpected.append(request.url)
            route.abort()
            return
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
        assert state.unexpected == []
        assert state.errors == []


def test_existing_original_is_displayed_with_metadata_without_starting_any_action(portal):
    from playwright.sync_api import expect

    state, page = portal
    page.goto(BASE_URL)
    expect(page.locator("#saved-state")).to_have_text("검증 완료")
    expect(page.locator("#saved-help")).to_have_text(
        "검증한 묶음 1개 · 검증한 파일 1개 · 표시 1개 · 생략 0개 · 미리보기 1개"
    )
    expect(page.locator("#saved-limits")).to_have_text(
        "파일 정보는 최대 20개 표시합니다. "
        "미리보기 원본 캐시는 파일당 최대 16 MiB · 전체 최대 32 MiB입니다."
    )
    expect(page.locator("#saved-files .saved-card")).to_have_count(1)
    expect(page.locator("#saved-files h3")).to_have_text("001.png")
    expect(page.locator("#saved-files .saved-caption p")).to_have_text(
        "PNG · 4 × 3 · 100.5 KB · 1프레임"
    )
    image = page.locator("#saved-files img")
    expect(image).to_have_attribute("src", BASE_URL + "images/" + FIRST_ID)
    page.wait_for_function("document.querySelector('#saved-files img')?.naturalWidth === 4")
    expect(page.locator("#refresh-saved")).to_be_enabled()
    assert state.image_requests == [BASE_URL + "images/" + FIRST_ID]
    assert state.actions == []
    assert all(url.startswith(BASE_URL) for url in state.requests)


def test_periodic_status_polls_keep_the_same_image_node_and_do_not_reload_bytes(portal):
    from playwright.sync_api import expect

    state, page = portal
    page.goto(BASE_URL)
    expect(page.locator("#saved-files img")).to_have_count(1)
    page.wait_for_function("document.querySelector('#saved-files img')?.naturalWidth === 4")
    page.evaluate("window.savedOriginalNode = document.querySelector('#saved-files img')")
    for _ in range(2):
        with page.expect_response(BASE_URL + "api/status") as response:
            pass
        response.value.finished()
        page.evaluate("() => new Promise(requestAnimationFrame)")
    assert page.evaluate("window.savedOriginalNode === document.querySelector('#saved-files img')")
    assert state.image_requests == [BASE_URL + "images/" + FIRST_ID]


def test_repeated_filenames_from_anonymous_groups_keep_separate_stable_originals(portal):
    from playwright.sync_api import expect

    state, page = portal
    first_group, second_group = "c" * 32, "d" * 32
    state.snapshot = ready_status(
        saved_groups_verified=2,
        saved_files_verified=2,
        saved_preview_count=2,
        saved_files=[
            saved_file(
                FIRST_ID,
                saved_filename="001.jpg",
                detected_format="JPEG",
                group_id=first_group,
                source_id="private-source-one",
            ),
            saved_file(
                SECOND_ID,
                saved_filename="001.jpg",
                detected_format="JPEG",
                group_id=second_group,
                source_id="private-source-two",
                source_root="C:/private/output",
                sha256="private-image-hash",
            ),
        ],
    )
    page.goto(BASE_URL)
    expect(page.locator("#saved-files h3")).to_have_text(
        ["저장 묶음 1 · 001.jpg", "저장 묶음 2 · 001.jpg"]
    )
    page.wait_for_function(
        "[...document.querySelectorAll('#saved-files img')].length === 2 && "
        "[...document.querySelectorAll('#saved-files img')]"
        ".every(image => image.naturalWidth === 4)"
    )
    assert state.image_requests == [
        BASE_URL + "images/" + FIRST_ID,
        BASE_URL + "images/" + SECOND_ID,
    ]
    expect(page.locator("#saved-help")).to_have_text(
        "검증한 묶음 2개 · 검증한 파일 2개 · 표시 2개 · 생략 0개 · 미리보기 2개"
    )
    for private in (first_group, second_group, "private", "source_id", "sha256"):
        assert private not in page.locator(".saved-panel").inner_html()
    page.evaluate("window.savedBatchNodes = [...document.querySelectorAll('#saved-files img')]")
    state.snapshot.update(saved_groups_verified=3, saved_files_verified=4, saved_files_omitted=2)
    expect(page.locator("#saved-help")).to_have_text(
        "검증한 묶음 3개 · 검증한 파일 4개 · 표시 2개 · 생략 2개 · 미리보기 2개"
    )
    assert page.evaluate(
        "window.savedBatchNodes.every((image, index) => "
        "image === document.querySelectorAll('#saved-files img')[index])"
    )
    assert len(state.image_requests) == 2
    assert state.actions == []
    assert all(url.startswith(BASE_URL) for url in state.requests)


def test_refresh_invalidates_old_images_and_renders_new_snapshot_only_when_ready(portal):
    from playwright.sync_api import expect

    state, page = portal
    page.goto(BASE_URL)
    expect(page.locator("#saved-files img")).to_have_count(1)
    page.wait_for_function("document.querySelector('#saved-files img')?.naturalWidth === 4")
    page.locator("#refresh-saved").click()
    expect(page.locator("#saved-state")).to_have_text("저장 결과 확인 중")
    expect(page.locator("#status-title")).to_have_text("저장 결과를 확인하고 있습니다.")
    expect(page.locator("#saved-files img")).to_have_count(0)
    expect(page.locator("#refresh-saved")).to_be_disabled()
    expect(page.locator("#pause")).to_be_disabled()
    expect(page.locator("#stop")).to_be_enabled()
    expect(page.locator("#exit")).to_be_enabled()
    expect(page.locator("#start")).to_be_disabled()
    state.snapshot = ready_status(
        task_kind="saved", saved_files=[saved_file(SECOND_ID, saved_filename="002.png")]
    )
    expect(page.locator("#saved-state")).to_have_text("검증 완료")
    expect(page.locator("#saved-files img")).to_have_attribute(
        "src", BASE_URL + "images/" + SECOND_ID
    )
    page.wait_for_function("document.querySelector('#saved-files img')?.naturalWidth === 4")
    expect(page.locator("#refresh-saved")).to_be_enabled()
    assert state.actions == [{"action": "refresh_saved"}]
    assert state.image_requests == [
        BASE_URL + "images/" + FIRST_ID,
        BASE_URL + "images/" + SECOND_ID,
    ]


def test_local_verification_can_be_stopped_and_exited_without_a_pause_resume_action(portal):
    from playwright.sync_api import expect

    state, page = portal
    state.snapshot = ready_status(
        task_kind="saved", phase="verifying_saved", settings_editable=False, saved_status="checking"
    )
    page.goto(BASE_URL)
    expect(page.locator("#pause")).to_be_disabled()
    page.locator("#stop").click()
    expect(page.locator("#saved-state")).to_have_text("확인 중지")
    expect(page.locator("#saved-files img")).to_have_count(0)
    expect(page.locator("#start")).to_be_enabled()
    page.locator("#exit").click()
    expect(page.locator("#refresh-saved")).to_be_disabled()
    assert state.actions == [{"action": "stop"}, {"action": "exit"}]


@pytest.mark.parametrize(
    "status,label",
    [
        ("disabled", "저장 결과 확인 꺼짐"),
        ("checking", "저장 결과 확인 중"),
        ("empty", "저장 결과 없음"),
        ("busy", "저장 중 또는 보류"),
        ("needs_review", "확인 필요"),
        ("cancelled", "확인 중지"),
        ("__proto__", "저장 결과 확인 꺼짐"),
    ],
)
def test_saved_outcome_labels_are_fixed_and_never_show_raw_error_data(portal, status, label):
    from playwright.sync_api import expect

    state, page = portal
    state.snapshot.update(
        saved_status=status,
        saved_reason="C:/Invented/private/path and https://foreign.example/token",
        saved_error_type="<script>window.savedInjected=1</script>",
    )
    page.goto(BASE_URL)
    expect(page.locator("#saved-state")).to_have_text(label)
    expect(page.locator("#saved-files img")).to_have_count(0)
    assert "private" not in page.locator(".saved-panel").inner_text()
    assert page.evaluate("window.savedInjected") is None
    assert state.image_requests == []
    assert state.actions == []


@pytest.mark.parametrize(
    "changes",
    [
        {"phase": "waiting", "settings_editable": False},
        {"phase": "needs_review"},
        {"phase": "paused"},
        {"settings_editable": False},
        {"browser_closed": None},
        {"saved_status": "disabled"},
    ],
)
def test_refresh_requires_stopped_owned_idle_configuration(portal, changes):
    from playwright.sync_api import expect

    state, page = portal
    state.snapshot.update(changes)
    page.goto(BASE_URL)
    expect(page.locator("#refresh-saved")).to_be_disabled()
    assert state.actions == []


def test_only_exact_local_image_ids_can_create_image_requests(portal):
    from playwright.sync_api import expect

    state, page = portal
    injected = '<img src="https://foreign.example/x" onerror="window.savedInjected=1">'
    state.snapshot.update(
        saved_files=[
            saved_file("https://foreign.example/x", saved_filename=injected, group_id=injected),
            saved_file(
                "../api/status", detected_format=injected, preview_url=injected, group_id=injected
            ),
        ]
    )
    page.goto(BASE_URL)
    expect(page.locator("#saved-files .saved-card")).to_have_count(2)
    expect(page.locator("#saved-files img")).to_have_count(0)
    expect(page.locator("#saved-files h3").first).to_have_text("저장 이미지")
    assert "foreign.example" not in page.locator(".saved-panel").inner_text()
    assert page.evaluate("window.savedInjected") is None
    assert state.image_requests == []
    assert all(url.startswith(BASE_URL) for url in state.requests)


def test_failed_image_request_shows_local_fallback_without_retrying_on_each_poll(portal):
    from playwright.sync_api import expect

    state, page = portal
    state.image_status = 404
    page.goto(BASE_URL)
    expect(page.locator("#saved-files img")).to_have_count(0)
    expect(page.locator("#saved-files .saved-fallback")).to_have_text(
        "미리보기를 불러오지 못했습니다. 저장 파일은 유지됩니다."
    )
    with page.expect_response(BASE_URL + "api/status") as response:
        pass
    response.value.finished()
    assert state.image_requests == [BASE_URL + "images/" + FIRST_ID]


def test_metadata_only_results_and_long_row_payload_stay_bounded_at_mobile_width(portal):
    from playwright.sync_api import expect

    state, page = portal
    state.snapshot.update(
        saved_groups_verified=22,
        saved_files_verified=22,
        saved_files_omitted=2,
        saved_preview_count=1,
        saved_files=[
            saved_file(group_id=f"{20:032x}"),
            saved_file(
                None,
                saved_filename="002.tiff",
                detected_format="TIFF",
                preview_available=False,
                group_id=f"{21:032x}",
            ),
            *[
                saved_file(
                    None,
                    group_id=f"{index:032x}",
                    preview_available=False,
                )
                for index in range(20)
            ],
        ],
    )
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(BASE_URL)
    expect(page.locator("#saved-files .saved-card")).to_have_count(20)
    expect(page.locator("#saved-files img")).to_have_count(1)
    expect(page.locator("#saved-help")).to_have_text(
        "검증한 묶음 22개 · 검증한 파일 22개 · 표시 20개 · 생략 2개 · 미리보기 1개"
    )
    expect(page.locator("#saved-files .saved-caption").nth(1)).to_contain_text("TIFF")
    expect(page.locator("#saved-files .saved-fallback").nth(1)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("filename", ["001.jpeg", "001.tif", "001.PNG", "003.jpg", "001.svg"])
def test_only_fixed_saved_filenames_are_shown(portal, filename):
    from playwright.sync_api import expect

    state, page = portal
    state.snapshot.update(saved_files=[saved_file(None, saved_filename=filename)])
    page.goto(BASE_URL)
    expect(page.locator("#saved-files h3")).to_have_text("저장 이미지")
    assert state.image_requests == []


def test_legacy_status_without_saved_fields_keeps_the_panel_inert(portal):
    from playwright.sync_api import expect

    state, page = portal
    state.snapshot = initial_status()
    page.goto(BASE_URL)
    expect(page.locator("#saved-state")).to_have_text("저장 결과 확인 꺼짐")
    expect(page.locator("#refresh-saved")).to_be_disabled()
    assert state.image_requests == state.actions == []
