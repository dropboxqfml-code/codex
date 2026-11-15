import json
import shutil
import sys
from datetime import UTC, datetime
from io import BytesIO

import pytest
from PIL import Image

from image_monitor.dcinside import DCSnapshotError, inspect_post, parse_snapshot, validate_post_url

URL = "https://gall.dcinside.com/board/view/?id=comic_new6&no=7036949"
NOW = datetime(2026, 11, 15, tzinfo=UTC)


def parse_fixture(raw, **options):
    options.setdefault("layout_status", "fixture_validated")
    return parse_snapshot(raw, **options)


def raw_snapshot():
    return {
        "body_count": 1,
        "title": "본문 제목",
        "nickname": "ㅇㅇ",
        "ip_display": "123.45",
        "published_at_raw": "2026.11.14 23:59:50",
        "attachments": [{"key": "file-a", "filename": "../원본.png", "filename_complete": True}],
        "images": [
            {
                "body_order": 1,
                "display_url": "https://images.example/a.png?token=one",
                "complete": True,
                "natural_width": 4,
                "natural_height": 3,
                "decode_ok": True,
                "attachment_key": "file-a",
            }
        ],
    }


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("/board/view/", "normal"),
        ("/mgallery/board/view", "minor"),
        ("/mini/board/view/", "mini"),
    ],
)
def test_post_url_identity_and_canonical_navigation_parameters(path, kind):
    result = validate_post_url(
        f"https://gall.dcinside.com{path}?id=gallery_x&no=00123&page=2&s_keyword=ai"
    )
    assert result["gallery_type"] == kind
    assert result["post_id"] == "123"
    assert result["canonical_url"].endswith("/?id=gallery_x&no=123")


@pytest.mark.parametrize(
    "url",
    [
        "http://gall.dcinside.com/board/view/?id=a&no=1",
        "https://gall.dcinside.com.evil.example/board/view/?id=a&no=1",
        "https://user@gall.dcinside.com/board/view/?id=a&no=1",
        "https://gall.dcinside.com:443/board/view/?id=a&no=1",
        "https://gall.dcinside.com/board/view/?id=a&no=1#section",
        "https://gall.dcinside.com/board/lists/?id=a&no=1",
        "https://gall.dcinside.com/board/view/?id=a&id=b&no=1",
        "https://gall.dcinside.com/board/view/?id=a&no=1&no=2",
        "https://gall.dcinside.com/board/view/?id=../a&no=1",
        "https://gall.dcinside.com/board/view/?id=a&no=0",
        "https://gall.dcinside.com/board/view/?id=a&no=abc",
        "https://gall.dcinside.com/board/view/?id=a&no=1&redirect=evil",
    ],
)
def test_other_or_ambiguous_urls_are_rejected(url):
    with pytest.raises(DCSnapshotError):
        validate_post_url(url)


def test_explicit_fixture_reference_and_three_names_remain_separate():
    snapshot = parse_fixture(raw_snapshot(), expected_url=URL, observed_at=NOW)
    image = snapshot["images"][0]
    assert snapshot["queue_eligible"]
    assert image["original_attachment_filename"] == "../원본.png"
    assert image["original_filename_match_status"] == "matched"
    assert image["browser_suggested_filename"] is None
    assert image["saved_filename"] is None
    assert snapshot["published_at"] == "2026-11-14T23:59:50+09:00"
    assert snapshot["ip_display"] == "123.45"
    json.dumps(snapshot)


def test_live_profile_does_not_claim_verified_attachment_mapping_or_queue_readiness():
    snapshot = parse_fixture(
        raw_snapshot(), expected_url=URL, observed_at=NOW, layout_status="unverified"
    )
    assert not snapshot["queue_eligible"]
    assert snapshot["images"][0]["original_attachment_filename"] is None
    assert snapshot["images"][0]["original_filename_match_status"] == "ambiguous"


def test_order_or_same_filename_never_proves_original_name_correspondence():
    raw = raw_snapshot()
    raw["images"][0].pop("attachment_key")
    raw["images"][0]["display_url"] = "https://images.example/原本.png"
    snapshot = parse_fixture(raw, expected_url=URL, observed_at=NOW)
    assert snapshot["queue_eligible"]
    assert snapshot["images"][0]["original_filename_match_status"] == "ambiguous"
    assert snapshot["images"][0]["original_attachment_filename"] is None


def test_repeated_body_occurrences_share_job_identity_but_new_urls_do_not():
    raw = raw_snapshot()
    raw["images"].append(raw["images"][0] | {"body_order": 3})
    first = parse_fixture(raw, expected_url=URL, observed_at=NOW)
    assert len(first["images"]) == 1
    assert first["images"][0]["occurrences"] == [1, 3]
    raw["images"][0]["body_order"] = 2
    second = parse_fixture(raw, expected_url=URL, observed_at=NOW)
    assert first["images"][0]["stable_key"] == second["images"][0]["stable_key"]
    raw["images"][0]["display_url"] += "-changed"
    third = parse_fixture(raw, expected_url=URL, observed_at=NOW)
    assert len(third["images"]) == 2


@pytest.mark.parametrize(
    "change",
    [
        {"complete": False},
        {"natural_width": 0},
        {"natural_height": 0},
        {"decode_ok": False},
        {"display_url": None},
    ],
)
def test_loading_failures_are_pending_work_not_excluded_or_successfully_empty_posts(change):
    raw = raw_snapshot()
    raw["images"][0].update(change)
    snapshot = parse_fixture(raw, expected_url=URL, observed_at=NOW)
    assert not snapshot["queue_eligible"]
    assert snapshot["images"] == []
    assert snapshot["excluded_images"] == []
    assert snapshot["pending_images"][0]["body_order"] == 1


@pytest.mark.parametrize("body_count", [0, 2])
def test_missing_or_ambiguous_body_never_falls_back_to_page_images(body_count):
    raw = raw_snapshot() | {"body_count": body_count}
    with pytest.raises(DCSnapshotError, match="exactly one"):
        parse_fixture(raw, expected_url=URL, observed_at=NOW)


def test_unrecognized_or_invalid_date_is_retained_and_falls_back_explicitly():
    for value, reason in [
        ("오늘 10:00", "published_at_unrecognized"),
        ("2026.13.14 23:59:50", "published_at_invalid"),
        (None, "published_at_missing"),
    ]:
        raw = raw_snapshot() | {"published_at_raw": value}
        snapshot = parse_fixture(raw, expected_url=URL, observed_at=NOW)
        assert snapshot["published_at"] is None
        assert snapshot["date_parse_reason"] == reason
        assert snapshot["published_at_raw"] == value


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
    image = BytesIO()
    Image.new("RGB", (4, 3), "navy").save(image, format="PNG")
    context = browser.new_context()
    page = context.new_page()

    def load(html):
        def route(request):
            if request.request.url.startswith("https://fixture.invalid/"):
                if request.request.url.endswith("broken.png"):
                    request.fulfill(status=200, content_type="image/png", body=b"broken image")
                else:
                    request.fulfill(status=200, content_type="image/png", body=image.getvalue())
            elif request.request.url == URL:
                request.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            else:
                request.abort()

        page.route("**/*", route)
        page.goto(URL, wait_until="domcontentloaded")
        return page

    yield load
    context.close()


HEADER = """<div class="view_head"><span class="title_subject">본문 제목</span>
 <span class="gall_writer" data-nick="ㅇㅇ" data-ip="123.45.67.89">
 <span class="ip">(123.45)</span></span>
 <span class="gall_date" title="2026.11.15 00:00:00"></span></div>"""


def test_real_browser_body_scope_lazy_decode_and_exclusion_reasons(page):
    html = (
        HEADER
        + """<img src="https://fixture.invalid/outside.png">
    <div class="write_div">
     <img src="https://fixture.invalid/tiny.png" data-attachment-key="file-a">
     <div class="comment_wrap"><img src="https://fixture.invalid/comment.png"></div>
     <span class="dccon"><img src="https://fixture.invalid/dccon.png"></span>
     <div class="ad_wrap"><img src="https://fixture.invalid/ad.png"></div>
     <div class="video"><img src="https://fixture.invalid/video.png"></div>
     <img id="lazy" data-src="https://fixture.invalid/lazy.png">
    </div><div class="appending_file"><a id="file-a" title="원본 전체.png">원본…</a></div>
    <script>setTimeout(()=>document.querySelector('#lazy').src=
      document.querySelector('#lazy').dataset.src,30)</script>"""
    )
    current = page(html)
    snapshot = inspect_post(current, expected_url=URL, observed_at=NOW, timeout_ms=1500)
    assert [image["body_order"] for image in snapshot["images"]] == [1, 6]
    assert all(image["natural_width"] == 4 for image in snapshot["images"])
    assert {item["reason"] for item in snapshot["excluded_images"]} == {
        "comment_content",
        "body_dccon",
        "irrelevant_body_content",
        "video_content",
    }
    assert snapshot["attachment_inventory"][0]["filename"] == "원본 전체.png"
    assert snapshot["ip_display"] == "123.45"
    assert "123.45.67.89" not in json.dumps(snapshot)
    assert not snapshot["queue_eligible"]
    assert snapshot["pending_images"] == []


def test_real_browser_include_dccon_and_broken_image_preserve_unresolved_work(page):
    current = page(
        HEADER
        + """<div class="write_div">
      <span class="dccon"><img src="https://fixture.invalid/dccon.png"></span>
      <img src="https://fixture.invalid/broken.png"></div>"""
    )
    snapshot = inspect_post(
        current, expected_url=URL, observed_at=NOW, include_dccon=True, timeout_ms=300
    )
    assert len(snapshot["images"]) == 1
    assert snapshot["images"][0]["body_order"] == 1
    assert snapshot["pending_images"][0]["body_order"] == 2
    assert not snapshot["queue_eligible"]


def test_real_browser_identity_and_missing_body_fail_closed(page):
    current = page(HEADER + '<img src="https://fixture.invalid/outside.png">')
    with pytest.raises(DCSnapshotError) as error:
        inspect_post(current, expected_url=URL, observed_at=NOW, timeout_ms=100)
    assert error.value.diagnostics["counts"][".write_div"] == 0
    assert "outside" not in json.dumps(error.value.diagnostics)
    with pytest.raises(DCSnapshotError, match="identity changed"):
        inspect_post(current, expected_url=URL.replace("7036949", "999"), observed_at=NOW)


def test_snapshot_mapping_defaults_to_unverified_and_cannot_queue_by_accident():
    snapshot = parse_snapshot(raw_snapshot(), expected_url=URL, observed_at=NOW)
    assert snapshot["layout_status"] == "unverified"
    assert not snapshot["queue_eligible"]


@pytest.mark.parametrize(
    "source",
    [
        "data:image/png;base64,PRIVATE_IMAGE_PAYLOAD",
        "blob:https://example/PRIVATE_IMAGE_PAYLOAD",
        "file:///PRIVATE_IMAGE_PAYLOAD.png",
        "https://username:PRIVATE_IMAGE_PAYLOAD@example/image.png",
        "https://[PRIVATE_IMAGE_PAYLOAD",
    ],
)
def test_unsupported_or_credential_urls_never_leak_payload_into_pending_records(source):
    raw = raw_snapshot()
    raw["images"][0]["display_url"] = source
    snapshot = parse_fixture(raw, expected_url=URL, observed_at=NOW)
    assert snapshot["pending_images"][0]["display_url"] is None
    assert "PRIVATE_IMAGE_PAYLOAD" not in json.dumps(snapshot)
    assert not snapshot["queue_eligible"]


def test_repeated_image_conflicting_dom_references_preserve_both_evidence_and_names():
    raw = raw_snapshot()
    raw["attachments"].append(
        {"key": "file-b", "filename": "다른 원본.png", "filename_complete": True}
    )
    raw["images"].append(raw["images"][0] | {"body_order": 2, "attachment_key": "file-b"})
    image = parse_fixture(raw, expected_url=URL, observed_at=NOW)["images"][0]
    assert image["original_filename_match_status"] == "ambiguous"
    assert image["original_attachment_filename"] is None
    assert image["original_filename_match_evidence"]["candidate_keys"] == ["file-a", "file-b"]
    assert len(image["occurrence_attachment_matches"]) == 2
    assert {item["filename"] for item in image["candidates"]} == {"../원본.png", "다른 원본.png"}


def test_inventory_truncation_is_an_explicit_error_not_silent_success():
    raw = raw_snapshot() | {"inventory_total": 201}
    with pytest.raises(DCSnapshotError, match="inventory exceeds"):
        parse_fixture(raw, expected_url=URL, observed_at=NOW)


def test_real_browser_data_original_placeholder_is_not_accepted_as_loaded_image(page):
    current = page(
        HEADER
        + """<div class="write_div"><img src="https://fixture.invalid/placeholder.png"
      data-original="https://fixture.invalid/actual.png"></div>"""
    )
    snapshot = inspect_post(current, expected_url=URL, observed_at=NOW, timeout_ms=150)
    assert snapshot["images"] == []
    assert snapshot["pending_images"][0]["reason"] == "image_loading_timed_out"


def test_real_browser_post_mutation_while_loading_is_not_a_complete_snapshot(page):
    current = page(
        HEADER
        + """<div class="write_div"><img id="late"
      style="display:block;margin-top:2000px;width:4px;height:3px"
      data-src="https://fixture.invalid/late.png"></div>
      <script>window.addEventListener('scroll',()=>{const img=document.createElement('img');
       img.src='https://fixture.invalid/new.png';document.querySelector('.write_div').append(img);
       document.querySelector('#late').src=document.querySelector('#late').dataset.src;
      },{once:true});</script>"""
    )
    with pytest.raises(DCSnapshotError, match="collection changed"):
        inspect_post(current, expected_url=URL, observed_at=NOW, timeout_ms=500)


def test_real_browser_inventory_limit_is_not_silently_sliced(page):
    anchors = "".join(f'<a id="file-{i}">name.png</a>' for i in range(201))
    current = page(
        HEADER + '<div class="write_div"></div><div class="appending_file">' + anchors + "</div>"
    )
    with pytest.raises(DCSnapshotError, match="inventory exceeds"):
        inspect_post(current, expected_url=URL, observed_at=NOW, timeout_ms=500)


def test_reference_evidence_hashes_query_and_id_values_without_claiming_a_match():
    raw = raw_snapshot()
    raw["attachments"][0]["reference_url"] = (
        "https://download.example/file.php?no=PRIVATE_LINK_TOKEN"
    )
    raw["attachments"][0]["id_attributes"] = {
        "data-file-no": "PRIVATE_ID_TOKEN",
        "data-cookie": "DO_NOT_KEEP",
        "onclick": "IGNORE_ME",
    }
    raw["images"][0]["id_attributes"] = {"data-image-id": "PRIVATE_ID_TOKEN"}
    raw["images"][0]["display_url"] = "https://images.example/view.php?file=PRIVATE_LINK_TOKEN"
    snapshot = parse_snapshot(raw, expected_url=URL, observed_at=NOW)
    inventory = snapshot["attachment_inventory"][0]
    image = snapshot["images"][0]
    assert (
        inventory["source_reference"]["query"][0]["value_sha256"]
        == image["display_reference"]["query"][0]["value_sha256"]
    )
    assert (
        inventory["id_attribute_hints"][0]["value_sha256"]
        == image["id_attribute_hints"][0]["value_sha256"]
    )
    assert image["original_filename_match_status"] == "ambiguous"
    assert not snapshot["queue_eligible"]
    public_inventory = json.dumps(snapshot["attachment_inventory"])
    assert "PRIVATE_" not in public_inventory
    assert "DO_NOT_KEEP" not in public_inventory and "IGNORE_ME" not in public_inventory


@pytest.mark.parametrize(
    "rendered_ip", ["", '<span class="ip" style="display:none">(123.45)</span>']
)
def test_real_browser_ip_display_never_falls_back_to_full_data_attribute(page, rendered_ip):
    html = (
        '<div class="view_head"><span class="gall_writer" data-nick="ㅇㅇ" '
        'data-ip="123.45.67.89">' + rendered_ip + '</span></div><div class="write_div"></div>'
    )
    snapshot = inspect_post(page(html), expected_url=URL, observed_at=NOW, timeout_ms=300)
    assert snapshot["ip_display"] is None
    assert "123.45.67.89" not in json.dumps(snapshot)
