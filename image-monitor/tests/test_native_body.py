import shutil
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from image_monitor import dcinside, native_body
from image_monitor.native_body import save_body_image
from image_monitor.native_ui import NativeFocusError, NativeUIError

URL = "https://gall.dcinside.com/board/view/?id=comic_new6&no=7036949"
SOURCE = "https://dcimg3.dcinside.co.kr/viewimage.php?id=body-token&no=image-token"
HEADER = """<div class="gallview_head"><span class="title_subject">시험 제목</span>
 <span class="gall_writer" data-nick="시험 사용자"></span>
 <span class="gall_date" title="2026.11.15 00:00:00"></span></div>"""


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
    content = BytesIO()
    Image.new("RGB", (4, 3), "navy").save(content, format="PNG")
    context = browser.new_context()
    current = context.new_page()

    def load(body=None, *, header=HEADER):
        html = (
            header
            + '<div class="write_div">'
            + (f'<img id="selected" src="{SOURCE}">' if body is None else body)
            + "</div><script>window.rightClicks=[];document.addEventListener('contextmenu',"
            + "event=>{event.preventDefault();window.rightClicks.push(event.target.id);});</script>"
        )

        def route(request):
            if request.request.url == URL:
                request.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            elif request.request.url.startswith(
                ("https://dcimg3.dcinside.co.kr/", "https://dccon.dcinside.com/")
            ):
                request.fulfill(status=200, content_type="image/png", body=content.getvalue())
            else:
                request.abort()

        current.route("**/*", route)
        current.goto(URL, wait_until="load")
        return current

    yield load
    context.close()


class NativeUI:
    def __init__(
        self,
        page,
        *,
        suggested="original.PNG",
        native_extension=None,
        guard=None,
        menu=None,
        saved=None,
    ):
        self.page = page
        self.suggested = suggested
        self.guard = guard
        self.menu = menu
        self.saved = saved
        self.native_extension = native_extension
        self.calls = []
        self.target = None

    def assert_target_ready(self):
        self.calls.append("guard")
        if self.guard:
            self.guard(self.calls.count("guard"))

    def click_save_image_menu(self):
        assert len(self.page.evaluate("window.rightClicks")) == 1
        self.calls.append("menu")
        if self.menu:
            self.menu()

    def save_dialog(self, target):
        self.calls.append("dialog")
        self.browser_suggested_extension = self.native_extension
        self.target = target(self.suggested)
        if self.saved:
            self.saved()
        return self.suggested


def observed(**changes):
    return {
        "display_url": SOURCE,
        "natural_width": 4,
        "natural_height": 3,
        "resource_identity": dcinside._shared_no_identity(SOURCE, body=True),
    } | changes


def expected_header(**changes):
    return {
        "title": "시험 제목",
        "nickname": "시험 사용자",
        "published_at_raw": "2026.11.15 00:00:00",
    } | changes


def save(page, ui, directory, **changes):
    return save_body_image(
        page, ui, post_url=URL, image=observed(**changes), staging_directory=directory
    )


def no_click(page, ui):
    assert page.evaluate("window.rightClicks") == []
    assert "menu" not in ui.calls
    assert "dialog" not in ui.calls


def test_exact_image_uses_native_suggestion_extension_and_preserves_source_metadata(page, tmp_path):
    current = page()
    ui = NativeUI(current, suggested=r"C:\arbitrary\..\do-not-use-this-name.JPEG")
    result = save(current, ui, tmp_path)
    assert result == {
        "staging_path": str(tmp_path / "native-image.jpeg"),
        "browser_suggested_filename": ui.suggested,
        "source_url": SOURCE,
        "natural_width": 4,
        "natural_height": 3,
        "resource_identity": observed()["resource_identity"],
    }
    assert ui.target == result["staging_path"]
    assert current.evaluate("window.rightClicks") == ["selected"]
    assert ui.calls == ["guard", "guard", "menu", "dialog"]
    assert not Path(result["staging_path"]).exists()  # No completion claim or file synthesis.


def test_extensionless_suggestion_can_use_a_proven_native_file_type_extension(page, tmp_path):
    current = page()
    ui = NativeUI(current, suggested="render-first", native_extension=".png")
    result = save(current, ui, tmp_path)
    assert result["browser_suggested_filename"] == "render-first"
    assert result["staging_path"] == str(tmp_path / "native-image.png")


def test_proven_file_type_cannot_replace_an_explicit_unsupported_filename_suffix(page, tmp_path):
    current = page()
    ui = NativeUI(current, suggested="render-first.exe", native_extension=".png")
    with pytest.raises(NativeUIError, match="supported image extension"):
        save(current, ui, tmp_path)
    assert ui.target is None


def test_input_boundary_runs_once_after_foreground_guard_before_first_scroll(
    page, tmp_path, monkeypatch
):
    from playwright.sync_api import ElementHandle

    current = page()
    events = []
    ui = NativeUI(current, guard=lambda _count: events.append("guard"))
    original_scroll = ElementHandle.scroll_into_view_if_needed

    def scroll(handle, **options):
        events.append("scroll")
        return original_scroll(handle, **options)

    monkeypatch.setattr(ElementHandle, "scroll_into_view_if_needed", scroll)

    def arm():
        assert ui.stage == "image_load"
        assert ui.calls == ["guard"]
        assert current.evaluate("window.rightClicks") == []
        events.append("armed")

    save_body_image(
        current,
        ui,
        post_url=URL,
        image=observed(),
        staging_directory=tmp_path,
        before_native_input=arm,
    )
    assert events[:4] == ["guard", "armed", "guard", "scroll"]
    assert events.count("armed") == 1
    assert current.evaluate("window.rightClicks") == ["selected"]


def test_failed_input_boundary_prevents_scrolling_and_native_input(page, tmp_path, monkeypatch):
    from playwright.sync_api import ElementHandle

    current = page()
    ui = NativeUI(current)
    scroll = MagicMock()
    monkeypatch.setattr(ElementHandle, "scroll_into_view_if_needed", scroll)
    error = NativeUIError("Durable marker could not be written")

    def fail():
        raise error

    with pytest.raises(NativeUIError, match="Durable marker") as caught:
        save_body_image(
            current,
            ui,
            post_url=URL,
            image=observed(),
            staging_directory=tmp_path,
            before_native_input=fail,
        )
    assert caught.value is error
    scroll.assert_not_called()
    no_click(current, ui)


@pytest.mark.parametrize("when", ["initial_guard", "after_callback"])
def test_focus_loss_before_scroll_has_an_explicit_boundary_and_clears_stale_suggestions(
    page, tmp_path, monkeypatch, when
):
    from playwright.sync_api import ElementHandle

    current = page()
    boundary = MagicMock()
    scroll = MagicMock()
    monkeypatch.setattr(ElementHandle, "scroll_into_view_if_needed", scroll)

    def guard(count):
        if count == (1 if when == "initial_guard" else 2):
            raise NativeFocusError("Foreground focus changed")

    ui = NativeUI(current, guard=guard)
    ui.browser_suggested_filename = "previous.webp"
    ui.browser_suggested_extension = ".webp"
    ui.browser_suggested_file_type = "Previous image type"
    with pytest.raises(NativeFocusError):
        save_body_image(
            current,
            ui,
            post_url=URL,
            image=observed(),
            staging_directory=tmp_path,
            before_native_input=boundary,
        )
    assert boundary.call_count == (0 if when == "initial_guard" else 1)
    assert ui.browser_suggested_filename is None
    assert ui.browser_suggested_extension is None
    assert ui.browser_suggested_file_type is None
    scroll.assert_not_called()
    no_click(current, ui)


def test_identity_is_rechecked_after_durable_boundary_before_scrolling(page, tmp_path, monkeypatch):
    from playwright.sync_api import ElementHandle

    current = page()
    ui = NativeUI(current)
    scroll = MagicMock()
    monkeypatch.setattr(ElementHandle, "scroll_into_view_if_needed", scroll)

    def arm():
        current.evaluate("history.replaceState(null,'',location.href.replace('7036949','999'))")

    with pytest.raises(NativeUIError, match="Post identity changed"):
        save_body_image(
            current,
            ui,
            post_url=URL,
            image=observed(),
            staging_directory=tmp_path,
            before_native_input=arm,
        )
    scroll.assert_not_called()
    no_click(current, ui)


def test_post_navigation_parameters_do_not_change_the_verified_identity(page, tmp_path):
    current = page()
    current.evaluate("history.replaceState(null,'',location.href+'&page=2')")
    assert save(current, NativeUI(current), tmp_path)["source_url"] == SOURCE


@pytest.mark.parametrize("field", ["title", "nickname", "published_at_raw", "ip_display"])
def test_frozen_header_mismatch_stops_before_any_native_input(page, tmp_path, field):
    current = page()
    ui = NativeUI(current)
    with pytest.raises(NativeUIError, match="header differs from the inspected snapshot"):
        save(current, ui, tmp_path, expected_header=expected_header(**{field: "different"}))
    no_click(current, ui)
    assert ui.calls == []


def test_matching_frozen_header_uses_only_the_public_rendered_ip(page, tmp_path):
    header = HEADER.replace(
        'data-nick="시험 사용자"></span>',
        'data-nick="시험 사용자" data-ip="198.51.100.77"><span class="ip">(198.51)</span></span>',
    )
    current = page(header=header)
    result = save(
        current, NativeUI(current), tmp_path, expected_header=expected_header(ip_display="198.51")
    )
    assert result["source_url"] == SOURCE


def test_hidden_ip_attribute_is_not_a_frozen_header_identity_source(page, tmp_path):
    header = HEADER.replace(
        'data-nick="시험 사용자"', 'data-nick="시험 사용자" data-ip="198.51.100.77"'
    )
    current = page(header=header)
    assert (
        save(
            current, NativeUI(current), tmp_path, expected_header=expected_header(ip_display=None)
        )["source_url"]
        == SOURCE
    )


def test_frozen_header_change_during_prepare_stops_before_right_click(page, tmp_path):
    current = page()

    def change(guard):
        if guard == 2:
            current.evaluate(
                "document.querySelector('.gall_date').setAttribute('title','2026.11.15 01:00:00')"
            )

    ui = NativeUI(current, guard=change)
    with pytest.raises(NativeUIError, match="header changed"):
        save(current, ui, tmp_path, expected_header=expected_header())
    no_click(current, ui)


@pytest.mark.parametrize("kind", ["post", "body", "header", "title", "source", "dccon"])
def test_changed_post_root_header_or_source_before_right_click_stops_input(page, tmp_path, kind):
    current = page()

    def change(guard):
        if guard != 2:
            return
        script = {
            "post": "history.replaceState(null,'',location.href.replace('7036949','999'))",
            "body": "document.querySelector('.write_div').outerHTML="
            "document.querySelector('.write_div').outerHTML",
            "header": "document.querySelector('.gallview_head').outerHTML="
            "document.querySelector('.gallview_head').outerHTML",
            "title": "document.querySelector('.title_subject').textContent='다른 제목'",
            "source": "document.querySelector('#selected').src="
            "document.querySelector('#selected').src.replace('body-token','other-token')",
            "dccon": "document.querySelector('#selected').className='written_dccon'",
        }[kind]
        current.evaluate(script)

    ui = NativeUI(current, guard=change)
    with pytest.raises(NativeUIError, match="changed"):
        save(current, ui, tmp_path)
    no_click(current, ui)


@pytest.mark.parametrize(
    "wrapper", ["dccon", "comment_wrap", "ad_wrap", "video_wrap", "recommend_box"]
)
def test_excluded_ancestors_are_never_native_save_targets(page, tmp_path, wrapper):
    current = page(f'<div class="{wrapper}"><img id="excluded" src="{SOURCE}"></div>')
    ui = NativeUI(current)
    with pytest.raises(NativeUIError, match="missing from the eligible post body"):
        save(current, ui, tmp_path)
    no_click(current, ui)


def test_dccon_host_is_ineligible_even_without_dccon_dom_classes(page, tmp_path):
    source = "https://dccon.dcinside.com/image.png"
    current = page(f'<img src="{source}">')
    ui = NativeUI(current)
    with pytest.raises(NativeUIError, match="missing from the eligible post body"):
        save(current, ui, tmp_path, display_url=source, resource_identity=None)
    no_click(current, ui)


def test_identical_url_occurrences_share_one_exact_native_target(page, tmp_path):
    current = page(f'<img id="first" src="{SOURCE}"><img id="second" src="{SOURCE}">')
    save(current, NativeUI(current), tmp_path)
    assert current.evaluate("window.rightClicks") == ["first"]


def test_duplicate_url_with_inconsistent_dimensions_is_rejected(page, tmp_path):
    current = page(f'<img id="first" src="{SOURCE}"><img id="second" src="{SOURCE}">')
    current.evaluate(
        "Object.defineProperty(document.querySelector('#second'),'naturalWidth',{value:5})"
    )
    ui = NativeUI(current)
    with pytest.raises(NativeUIError, match="occurrences disagree"):
        save(current, ui, tmp_path)
    no_click(current, ui)


def test_same_no_identifier_cannot_replace_the_exact_inspected_source(page, tmp_path):
    alternative = SOURCE.replace("body-token", "rotated-token")
    assert dcinside._shared_no_identity(alternative, body=True) == observed()["resource_identity"]
    current = page(f'<img id="alternative" src="{alternative}">')
    ui = NativeUI(current)
    with pytest.raises(NativeUIError, match="missing from the eligible post body"):
        save(current, ui, tmp_path)
    no_click(current, ui)


@pytest.mark.parametrize("mode", ["failure", "timeout"])
def test_failed_or_unfinished_decode_is_not_right_clicked(page, tmp_path, monkeypatch, mode):
    current = page()
    decode = (
        "Promise.reject(new Error('decode failed'))" if mode == "failure" else "new Promise(()=>{})"
    )
    current.evaluate(f"() => {{document.querySelector('#selected').decode=()=>{decode};}}")
    monkeypatch.setattr(native_body, "_LOAD_TIMEOUT_MS", 100)
    ui = NativeUI(current)
    with pytest.raises(NativeUIError, match="did not decode"):
        save(current, ui, tmp_path)
    no_click(current, ui)


def test_foreground_guard_failure_prevents_native_context_menu(page, tmp_path):
    current = page()

    def guard(count):
        if count == 2:
            raise NativeUIError("Foreground focus changed")

    ui = NativeUI(current, guard=guard)
    with pytest.raises(NativeUIError, match="Foreground focus changed"):
        save(current, ui, tmp_path)
    no_click(current, ui)


@pytest.mark.parametrize("kind", ["incomplete", "dimensions", "lazy", "detached"])
def test_image_loading_or_membership_changes_before_click_stop_input(page, tmp_path, kind):
    current = page()

    def change(guard):
        if guard != 2:
            return
        script = {
            "incomplete": "Object.defineProperty(img,'complete',{value:false})",
            "dimensions": "Object.defineProperty(img,'naturalHeight',{value:8})",
            "lazy": "img.dataset.original=img.currentSrc.replace('body-token','lazy-token')",
            "detached": "document.body.append(img)",
        }[kind]
        current.evaluate("() => {const img=document.querySelector('#selected');" + script + ";}")

    ui = NativeUI(current, guard=change)
    with pytest.raises(NativeUIError, match="Exact body image changed"):
        save(current, ui, tmp_path)
    no_click(current, ui)


@pytest.mark.parametrize(
    "kind", ["second_body", "second_header", "missing_field", "duplicate_field"]
)
def test_ambiguous_or_incomplete_post_structure_stops_before_input(page, tmp_path, kind):
    current = page()
    script = {
        "second_body": "document.body.insertAdjacentHTML('beforeend',"
        "'<div class=write_div></div>')",
        "second_header": "document.body.append("
        "document.querySelector('.gallview_head').cloneNode(true))",
        "missing_field": "document.querySelector('.gall_date').remove()",
        "duplicate_field": "document.querySelector('.gallview_head').append("
        "document.querySelector('.gall_date').cloneNode(true))",
    }[kind]
    current.evaluate(script)
    ui = NativeUI(current)
    with pytest.raises(NativeUIError, match="exactly one|header fields"):
        save(current, ui, tmp_path)
    no_click(current, ui)


@pytest.mark.parametrize("suggested", [None, "image", "image.exe", "image.png:stream", "x\0.png"])
def test_unsupported_native_suggestion_does_not_create_a_staging_path(page, tmp_path, suggested):
    current = page()
    ui = NativeUI(current, suggested=suggested)
    with pytest.raises(NativeUIError, match="supported image extension"):
        save(current, ui, tmp_path)
    assert ui.target is None
    assert list(tmp_path.iterdir()) == []


def test_stage_path_created_during_native_menu_is_never_overwritten(page, tmp_path):
    current = page()
    existing = tmp_path / "native-image.png"
    ui = NativeUI(current, menu=lambda: existing.write_text("existing", encoding="utf-8"))
    with pytest.raises(NativeUIError, match="already exists"):
        save(current, ui, tmp_path)
    assert existing.read_text(encoding="utf-8") == "existing"
    assert ui.target is None


def test_nonempty_stage_is_rejected_before_any_native_input(page, tmp_path):
    current = page()
    (tmp_path / "previous.png").write_bytes(b"previous attempt")
    ui = NativeUI(current)
    with pytest.raises(NativeUIError, match="must be empty"):
        save(current, ui, tmp_path)
    no_click(current, ui)


def test_changed_post_after_native_save_is_not_reported_as_a_valid_result(page, tmp_path):
    current = page()
    ui = NativeUI(
        current,
        saved=lambda: current.evaluate(
            "history.replaceState(null,'',location.href.replace('7036949','999'))"
        ),
    )
    with pytest.raises(NativeUIError, match="Post identity changed"):
        save(current, ui, tmp_path)
    assert current.evaluate("window.rightClicks") == ["selected"]


def test_mismatched_resource_identity_is_rejected_before_input(page, tmp_path):
    current = page()
    ui = NativeUI(current)
    with pytest.raises(NativeUIError, match="resource identity"):
        save(current, ui, tmp_path, resource_identity="dcinside-shared-no-sha256:wrong")
    no_click(current, ui)


@pytest.mark.parametrize(
    "source",
    [None, "", "data:image/png;base64,payload", "file:///private/image.png", "https://u:p@x/y"],
)
def test_unusable_inspected_sources_are_rejected_before_native_input(page, tmp_path, source):
    current = page()
    ui = NativeUI(current)
    with pytest.raises(NativeUIError, match="exact inspected image source"):
        save(current, ui, tmp_path, display_url=source, resource_identity=None)
    no_click(current, ui)
