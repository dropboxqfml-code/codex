"""Exercise the trusted-click boundary of the single-post save panel."""

import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from image_monitor.native_ui import NativeUIError
from image_monitor.post_worker import install_approval, wait_for_approval

SNAPSHOT = {
    "title": "Synthetic panel fixture",
    "post_url": "https://gall.dcinside.com/board/view/?id=comic_new6&no=7036949",
    "images": [{}, {}],
}
SAVE_ROOT = Path("C:/SyntheticPanelOutput")
PANEL = "#image-monitor-save-panel"


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    if sys.platform == "win32":
        from image_monitor.native_probe import browser_executable

        executable = str(browser_executable("edge"))
    else:
        executable = shutil.which("chromium") or shutil.which("google-chrome")
        if not executable:
            pytest.skip("Installed browser unavailable")
    with playwright.sync_playwright() as driver:
        instance = driver.chromium.launch(
            executable_path=executable, headless=True, args=["--disable-background-networking"]
        )
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    current = context.new_page()
    current.set_content(
        '<title>Original fixture title</title><div class="gallview_head">'
        '<span class="title_subject">Synthetic panel fixture</span>'
        '<span class="gall_writer" data-nick="fixture author"></span>'
        '<span class="gall_date">2026.11.15 10:00:00</span></div>'
        '<div class="write_div"><p>Unchanged synthetic body</p></div>'
    )
    yield current
    context.close()


def approval_state(page):
    return page.evaluate(
        "() => ({nonce:window.__imageMonitorApproval.nonce,"
        "approved:window.__imageMonitorApproval.approved})"
    )


def test_resume_requires_new_trusted_click_and_preserves_the_post(page):
    before = page.evaluate(
        "() => {window.fixtureBody=document.querySelector('.write_div');"
        "window.fixtureHeader=document.querySelector('.gallview_head');"
        "return {body:fixtureBody.outerHTML,header:fixtureHeader.outerHTML};}"
    )
    nonce, title = install_approval(page, SNAPSHOT, SAVE_ROOT)
    page.locator(PANEL + " button").evaluate("button => button.click()")
    assert approval_state(page) == {"nonce": nonce, "approved": False}
    page.get_by_role("button", name="저장 시작", exact=True).click()
    assert approval_state(page) == {"nonce": nonce, "approved": True}

    resume_nonce, resume_title = install_approval(
        page,
        SNAPSHOT,
        SAVE_ROOT,
        resume=True,
        title=title,
        progress={"observed": 2, "completed": 1, "unresolved": 1},
    )
    assert resume_nonce != nonce and resume_title == title == page.title()
    assert approval_state(page) == {"nonce": resume_nonce, "approved": False}
    assert page.locator(PANEL).count() == 1
    assert page.locator(".write_div " + PANEL).count() == 0
    assert "1/2개 저장 완료" in page.locator(PANEL).inner_text()
    page.locator(PANEL + " button").evaluate("button => button.click()")
    assert approval_state(page)["approved"] is False
    page.get_by_role("button", name="계속 저장", exact=True).click()
    assert approval_state(page) == {"nonce": resume_nonce, "approved": True}

    guards = []
    ui = SimpleNamespace(assert_target_ready=lambda: guards.append("foreground"))
    with pytest.raises(NativeUIError, match="not approved"):
        wait_for_approval(page, ui, nonce, timeout=0.05)
    assert guards == []
    wait_for_approval(page, ui, resume_nonce, timeout=0.05)
    assert guards == ["foreground"]
    after = page.evaluate(
        "() => ({body:document.querySelector('.write_div').outerHTML,"
        "header:document.querySelector('.gallview_head').outerHTML,"
        "sameBody:document.querySelector('.write_div')===window.fixtureBody,"
        "sameHeader:document.querySelector('.gallview_head')===window.fixtureHeader})"
    )
    assert after == before | {"sameBody": True, "sameHeader": True}


@pytest.mark.parametrize("change", ["removed", "replaced", "title", "state_title"])
def test_resume_refuses_a_changed_panel_or_window_binding(page, change):
    _nonce, title = install_approval(page, SNAPSHOT, SAVE_ROOT)
    mutations = {
        "removed": f"document.querySelector('{PANEL}').remove()",
        "replaced": (
            f"document.querySelector('{PANEL}').replaceWith("
            "Object.assign(document.createElement('section'),{id:'image-monitor-save-panel'}))"
        ),
        "title": "document.title='Unrelated window title'",
        "state_title": "window.__imageMonitorApproval.title='Unrelated panel title'",
    }
    page.evaluate(mutations[change])
    with pytest.raises(Exception, match="original save panel changed"):
        install_approval(
            page,
            SNAPSHOT,
            SAVE_ROOT,
            resume=True,
            title=title,
            progress={"observed": 2, "completed": 1, "unresolved": 1},
        )


def test_initial_panel_refuses_an_existing_element_with_the_same_id(page):
    page.evaluate(
        "document.body.append(Object.assign(document.createElement('section'),"
        "{id:'image-monitor-save-panel'}))"
    )
    with pytest.raises(Exception, match="Existing approval panel"):
        install_approval(page, SNAPSHOT, SAVE_ROOT)
    assert page.title() == "Original fixture title"
    assert page.locator(PANEL).count() == 1
