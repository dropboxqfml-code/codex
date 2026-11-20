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

    def load(html, *, url=URL):
        def route(request):
            if request.request.url.startswith(
                ("https://fixture.invalid/", "https://dcimg3.dcinside.co.kr/")
            ):
                if request.request.url.endswith("broken.png"):
                    request.fulfill(status=200, content_type="image/png", body=b"broken image")
                else:
                    request.fulfill(status=200, content_type="image/png", body=image.getvalue())
            elif request.request.url == url:
                request.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            else:
                request.abort()

        page.route("**/*", route)
        page.goto(url, wait_until="domcontentloaded")
        return page

    yield load
    context.close()


HEADER = """<div class="gallview_head"><span class="title_subject">본문 제목</span>
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
    unverified_url = URL.replace("7036949", "999")
    current = page(html, url=unverified_url)
    snapshot = inspect_post(current, expected_url=unverified_url, observed_at=NOW)
    assert [image["body_order"] for image in snapshot["images"]] == [1, 6], [
        (image["body_order"], image["reason"]) for image in snapshot["pending_images"]
    ]
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
    assert image["original_filename_source"] is None
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
    # Allow the browser to finish the initial DOM inspection and reach the lazy image check.
    snapshot = inspect_post(current, expected_url=URL, observed_at=NOW, timeout_ms=1500)
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
        '<div class="gallview_head"><span class="gall_writer" data-nick="ㅇㅇ" '
        'data-ip="123.45.67.89">' + rendered_ip + '</span></div><div class="write_div"></div>'
    )
    snapshot = inspect_post(page(html), expected_url=URL, observed_at=NOW, timeout_ms=300)
    assert snapshot["ip_display"] is None
    assert "123.45.67.89" not in json.dumps(snapshot)


def resource_snapshot():
    raw = raw_snapshot()
    raw["images"][0]["display_url"] = (
        "https://dcimg3.dcinside.co.kr/viewimage.php?id=synthetic&no=fixture-a"
    )
    raw["images"][0]["identity"] = "wrong-attribute-identity"
    raw["images"][0]["id_attributes"] = {"data-fileno": "irrelevant-identifier"}
    raw["attachments"][0]["reference_url"] = (
        "https://image.dcinside.com/download.php?no=fixture-a&f_no=other-number"
    )
    raw["attachments"][0]["identity"] = "different-attribute-identity"
    return raw


def test_observed_resource_pair_matches_literal_no_without_order_or_other_attribute_inference():
    raw = resource_snapshot()
    raw["attachments"].insert(
        0,
        {
            "key": "unrelated",
            "filename": "unrelated.png",
            "filename_complete": True,
            "reference_url": "https://image.dcinside.com/download.php?no=fixture-b&f_no=irrelevant-identifier",
        },
    )
    snapshot = parse_snapshot(raw, expected_url=URL, observed_at=NOW)
    image = snapshot["images"][0]
    assert image["original_attachment_filename"] == "../원본.png"
    assert image["original_filename_match_status"] == "matched"
    assert image["original_filename_match_method"] == "shared_file_identifier"
    assert image["original_filename_source"] == "attachment_list_dom"
    assert image["resource_identity_source"] == "verified_shared_query_no"
    assert (
        image["original_filename_match_evidence"]["identifier_source"] == "verified_shared_query_no"
    )
    assert snapshot["attachment_inventory"][1]["identity"].startswith("dcinside-shared-no-sha256:")
    assert "fixture-a" not in snapshot["attachment_inventory"][1]["identity"]
    assert snapshot["layout_status"] == "unverified"
    assert "attachment_matching_scope_limited_to_observed_endpoints" in snapshot["warnings"]
    assert "attachment_evidence_unverified" not in snapshot["warnings"]
    assert not snapshot["queue_eligible"]


@pytest.mark.parametrize(
    "body_url",
    [
        "https://dcimg3.dcinside.co.kr/viewimage.php?id=synthetic&no=fixture-a&no=fixture-a",
        "https://dcimg3.dcinside.co.kr/viewimage.php?id=synthetic",
        "https://dcimg3.dcinside.co.kr/viewimage.php?id=synthetic&no=",
        "https://dcimg3.dcinside.co.kr/viewimage.php?id=synthetic&no=%20",
        "https://dcimg3.dcinside.co.kr.evil.example/viewimage.php?id=synthetic&no=fixture-a",
        "https://dcimg4.dcinside.co.kr/viewimage.php?id=synthetic&no=fixture-a",
        "https://dcimg3.dcinside.co.kr/other.php?no=fixture-a",
        "https://dcimg3.dcinside.co.kr:443/viewimage.php?id=synthetic&no=fixture-a",
        "https://user@dcimg3.dcinside.co.kr/viewimage.php?id=synthetic&no=fixture-a",
        "https://dcimg3.dcinside.co.kr/viewimage.php?id=synthetic&no=fixture-a#fragment",
        "http://dcimg3.dcinside.co.kr/viewimage.php?id=synthetic&no=fixture-a",
        "https://dcimg3.dcinside.co.kr/viewimage.php?id=synthetic&no=fixture-a&unknown=1",
        "https://dcimg3.dcinside.co.kr/viewimage.php?id=synthetic&no=%FF",
        "https://dcimg3.dcinside.co.kr/viewimage.php?id=synthetic&no=%QZ",
        "https://dcimg3.dcinside.co.kr/viewimage.php?no=fixture-a",
        "https://dcimg3.dcinside.co.kr/viewimage.php?id=&no=fixture-a",
        "https://dcimg3.dcinside.co.kr/viewimage.php?id=%20&no=fixture-a",
    ],
)
def test_body_resource_rule_rejects_unobserved_or_ambiguous_endpoints(body_url):
    raw = resource_snapshot()
    raw["images"][0]["display_url"] = body_url
    snapshot = parse_snapshot(raw, expected_url=URL, observed_at=NOW)
    assert all(image["original_attachment_filename"] is None for image in snapshot["images"])
    assert not snapshot["queue_eligible"]


@pytest.mark.parametrize(
    "reference_url",
    [
        "https://image.dcinside.com/download.php?no=fixture-a&no=fixture-a&f_no=companion",
        "https://image.dcinside.com/download.php?f_no=fixture-a",
        "https://image.dcinside.com/download.php?no=&f_no=companion",
        "https://image.dcinside.com.evil.example/download.php?no=fixture-a&f_no=companion",
        "https://image.dcinside.com/other.php?no=fixture-a",
        "https://image.dcinside.com:443/download.php?no=fixture-a&f_no=companion",
        "https://user@image.dcinside.com/download.php?no=fixture-a&f_no=companion",
        "http://image.dcinside.com/download.php?no=fixture-a&f_no=companion",
        "https://image.dcinside.com/download.php?no=%FF&f_no=companion",
        "https://image.dcinside.com/download.php?no=%QZ&f_no=companion",
        "https://image.dcinside.com/download.php?no=fixture-a",
        "https://image.dcinside.com/download.php?no=fixture-a&f_no=",
        "https://image.dcinside.com/download.php?no=fixture-a&f_no=%20",
    ],
)
def test_inventory_resource_rule_rejects_unobserved_or_ambiguous_endpoints(reference_url):
    raw = resource_snapshot()
    raw["attachments"][0]["reference_url"] = reference_url
    image = parse_snapshot(raw, expected_url=URL, observed_at=NOW)["images"][0]
    assert image["original_attachment_filename"] is None


def test_duplicate_inventory_shared_no_is_ambiguous_even_when_names_match():
    raw = resource_snapshot()
    raw["attachments"].append(raw["attachments"][0] | {"key": "file-b"})
    image = parse_snapshot(raw, expected_url=URL, observed_at=NOW)["images"][0]
    assert image["original_filename_match_status"] == "ambiguous"
    assert image["original_attachment_filename"] is None
    assert image["original_filename_match_reason"] == "duplicate_shared_identifier"


@pytest.mark.parametrize(
    "target",
    [
        "https://gall.dcinside.com/board/view/?id=another_gallery&no=1",
        "https://gall.dcinside.com/mgallery/board/view/?id=comic_new6&no=1",
        "https://gall.dcinside.com/mini/board/view/?id=comic_new6&no=1",
    ],
)
def test_observed_resource_relation_does_not_promote_other_gallery_profiles(target):
    image = parse_snapshot(resource_snapshot(), expected_url=target, observed_at=NOW)["images"][0]
    assert image["original_attachment_filename"] is None
    assert image["resource_identity_source"] is None


def test_real_browser_observed_structural_profile_reads_header_and_reordered_inventory(page):
    sources = ["fixture-a", "fixture-b", "fixture-c", "fixture-d"]
    images = "".join(
        '<img src="https://dcimg3.dcinside.co.kr/viewimage.php?id=synthetic&amp;no='
        + key
        + '" data-fileno="different-'
        + str(index)
        + '">'
        for index, key in enumerate(sources)
    )
    anchors = "".join(
        '<a id="attachment-' + str(index) + '" title="synthetic-' + key + '.png" '
        'href="https://image.dcinside.com/download.php?no='
        + key
        + "&amp;f_no=unrelated-"
        + str(index)
        + '">'
        "synthetic…</a>"
        for index, key in enumerate(reversed(sources))
    )
    html = HEADER + '<div class="write_div">' + images + '<span class="dccon">'
    html += '<img src="https://fixture.invalid/dccon.png"></span></div>'
    html += '<div class="appending_file">' + anchors + "</div>"
    snapshot = inspect_post(page(html), expected_url=URL, observed_at=NOW, timeout_ms=1000)
    assert snapshot["title"] == "본문 제목"
    assert snapshot["nickname"] == "ㅇㅇ"
    assert snapshot["ip_display"] == "123.45"
    assert snapshot["published_at"] == "2026-11-15T00:00:00+09:00"
    assert len(snapshot["images"]) == 4 and len(snapshot["excluded_images"]) == 1
    assert [image["original_attachment_filename"] for image in snapshot["images"]] == [
        "synthetic-" + key + ".png" for key in sources
    ]
    assert snapshot["layout_status"] == "site_verified"
    assert snapshot["queue_eligible"]
    assert all(image["stable_key"] == image["resource_identity"] for image in snapshot["images"])


def test_real_browser_ambiguous_header_is_not_arbitrarily_selected(page):
    with pytest.raises(DCSnapshotError, match="exactly one post header"):
        inspect_post(
            page(HEADER + HEADER + '<div class="write_div"></div>'),
            expected_url=URL,
            observed_at=NOW,
            timeout_ms=300,
        )


def verified_post_snapshot():
    return resource_snapshot() | {
        "header_count": 1,
        "header_field_counts": {".gall_writer": 1, ".gall_date": 1, ".title_subject": 1},
    }


def test_only_reviewed_live_post_with_complete_metadata_is_promoted():
    snapshot = parse_snapshot(verified_post_snapshot(), expected_url=URL, observed_at=NOW)
    assert snapshot["layout_status"] == "site_verified"
    assert snapshot["queue_eligible"]
    image = snapshot["images"][0]
    assert image["stable_key"] == image["resource_identity"]
    assert image["stable_key_source"] == "verified_shared_query_no"
    assert "live_dom_profile_unverified" not in snapshot["warnings"]
    assert snapshot["profile_evidence"]["source"] == "user_site_probe_v8"
    assert snapshot["profile_evidence"]["verified_post_id"] == "7036949"


@pytest.mark.parametrize(
    "url",
    [
        URL.replace("7036949", "7036950"),
        URL.replace("comic_new6", "another_gallery"),
        URL.replace("/board/view/", "/mgallery/board/view/"),
    ],
)
def test_same_layout_on_unreviewed_post_or_gallery_remains_gated(url):
    snapshot = parse_snapshot(verified_post_snapshot(), expected_url=url, observed_at=NOW)
    assert snapshot["layout_status"] == "unverified"
    assert not snapshot["queue_eligible"]
    assert snapshot["images"][0]["stable_key_source"] == "exact_display_url_hash"


@pytest.mark.parametrize(
    "change",
    [
        {"title": None},
        {"title": ""},
        {"title": "  "},
        {"nickname": None},
        {"nickname": ""},
        {"published_at_raw": None},
        {"published_at_raw": "오늘"},
        {"published_at_raw": "2026.99.99 00:00:00"},
        {"header_field_counts": {}},
        {"header_field_counts": {".gall_writer": 2, ".gall_date": 1, ".title_subject": 1}},
        {"header_field_counts": {".gall_writer": True, ".gall_date": 1, ".title_subject": 1}},
    ],
)
def test_metadata_gaps_or_ambiguous_fields_prevent_live_promotion(change):
    snapshot = parse_snapshot(verified_post_snapshot() | change, expected_url=URL, observed_at=NOW)
    assert snapshot["layout_status"] == "unverified"
    assert not snapshot["queue_eligible"]
    assert snapshot["images"][0]["stable_key_source"] == "exact_display_url_hash"


def test_pending_image_prevents_promotion_and_does_not_change_job_identity_scheme():
    raw = verified_post_snapshot()
    raw["images"].append(raw["images"][0] | {"body_order": 2, "decode_ok": False})
    snapshot = parse_snapshot(raw, expected_url=URL, observed_at=NOW)
    assert snapshot["layout_status"] == "unverified"
    assert not snapshot["queue_eligible"]
    assert snapshot["pending_images"][0]["body_order"] == 2
    assert snapshot["images"][0]["stable_key_source"] == "exact_display_url_hash"


def test_original_name_unavailable_does_not_block_otherwise_verified_body_image():
    raw = verified_post_snapshot() | {"attachments": []}
    snapshot = parse_snapshot(raw, expected_url=URL, observed_at=NOW)
    assert snapshot["layout_status"] == "site_verified" and snapshot["queue_eligible"]
    assert snapshot["images"][0]["original_attachment_filename"] is None
    assert snapshot["images"][0]["stable_key"] == snapshot["images"][0]["resource_identity"]


def test_fixture_mode_retains_exact_url_job_keys_even_on_reviewed_post():
    snapshot = parse_fixture(verified_post_snapshot(), expected_url=URL, observed_at=NOW)
    assert snapshot["layout_status"] == "fixture_validated"
    assert snapshot["images"][0]["stable_key_source"] == "exact_display_url_hash"
    assert snapshot["images"][0]["resource_identity"] is None


def test_companion_url_parameter_rotation_keeps_reviewed_resource_job_key():
    first = parse_snapshot(verified_post_snapshot(), expected_url=URL, observed_at=NOW)
    raw = verified_post_snapshot()
    raw["images"][0]["display_url"] = raw["images"][0]["display_url"].replace(
        "id=synthetic", "id=fresh"
    )
    second = parse_snapshot(raw, expected_url=URL, observed_at=NOW)
    assert first["images"][0]["display_url"] != second["images"][0]["display_url"]
    assert first["images"][0]["stable_key"] == second["images"][0]["stable_key"]


def test_url_variants_of_one_reviewed_resource_keep_all_body_occurrences():
    raw = verified_post_snapshot()
    raw["images"].append(
        raw["images"][0]
        | {
            "body_order": 3,
            "display_url": raw["images"][0]["display_url"].replace("id=synthetic", "id=fresh"),
        }
    )
    snapshot = parse_snapshot(raw, expected_url=URL, observed_at=NOW)
    assert len(snapshot["images"]) == 1
    image = snapshot["images"][0]
    assert image["occurrences"] == [1, 3]
    assert len(image["display_urls"]) == 2
    assert len(image["occurrence_attachment_matches"]) == 2
    assert image["original_filename_match_status"] == "matched"


def test_reviewed_resource_reordering_and_url_rotation_are_queue_idempotent(tmp_path):
    from image_monitor.post_pipeline import enqueue_snapshot
    from image_monitor.queue import QueueStore

    raw = verified_post_snapshot()
    raw["images"].append(
        raw["images"][0]
        | {
            "body_order": 2,
            "display_url": raw["images"][0]["display_url"].replace("no=fixture-a", "no=fixture-b"),
        }
    )
    raw["attachments"].append(
        raw["attachments"][0]
        | {
            "key": "file-b",
            "reference_url": raw["attachments"][0]["reference_url"].replace(
                "no=fixture-a", "no=fixture-b"
            ),
        }
    )
    first = parse_snapshot(raw, expected_url=URL, observed_at=NOW)
    with QueueStore(tmp_path / "queue.db") as store:
        enqueue_snapshot(store, first, watch_name="합성감시", keyword="ai")
        prior = {job["stable_key"]: (job["job_id"], job["file_slot"]) for job in store.list_jobs()}
        raw["images"].reverse()
        for order, image in enumerate(raw["images"], 1):
            image["body_order"] = order
            image["display_url"] = image["display_url"].replace("id=synthetic", "id=fresh")
        second = parse_snapshot(raw, expected_url=URL, observed_at=NOW)
        enqueue_snapshot(store, second, watch_name="합성감시", keyword="ai")
        after = store.list_jobs()
        assert len(after) == 2
        assert {job["stable_key"]: (job["job_id"], job["file_slot"]) for job in after} == prior
        assert all("id=fresh" in job["display_url"] for job in after)


def test_noncallable_interaction_guard_is_rejected_before_observing_page():
    from unittest.mock import MagicMock

    unused_page = MagicMock()
    with pytest.raises(DCSnapshotError, match="Invalid inspection options"):
        inspect_post(unused_page, expected_url=URL, observed_at=NOW, before_interaction=123)
    unused_page.evaluate.assert_not_called()
    unused_page.locator.assert_not_called()


def test_real_browser_guard_failure_after_first_scroll_preserves_typed_error_and_stops(
    page, monkeypatch
):
    from playwright.sync_api import ElementHandle

    from image_monitor.dcinside import LOAD_JS

    class FocusPaused(RuntimeError):
        pass

    paused = FocusPaused("Synthetic foreground guard stopped inspection")
    guard_calls, scrolls, loads = [], [], []
    real_scroll = ElementHandle.scroll_into_view_if_needed
    real_evaluate = ElementHandle.evaluate

    def observed_scroll(handle, **options):
        scrolls.append(handle.get_attribute("id"))
        return real_scroll(handle, **options)

    def observed_evaluate(handle, expression, arg=None):
        if expression == LOAD_JS:
            loads.append(handle.get_attribute("id"))
        return real_evaluate(handle, expression, arg)

    def guard():
        guard_calls.append(len(guard_calls) + 1)
        if len(guard_calls) == 2:
            raise paused

    monkeypatch.setattr(ElementHandle, "scroll_into_view_if_needed", observed_scroll)
    monkeypatch.setattr(ElementHandle, "evaluate", observed_evaluate)
    current = page(
        HEADER
        + """<div class="write_div">
      <img id="first" src="https://fixture.invalid/first.png">
      <span class="dccon"><img id="excluded" src="https://fixture.invalid/dccon.png"></span>
      <img id="second" src="https://fixture.invalid/second.png">
      <img id="third" src="https://fixture.invalid/third.png"></div>"""
    )
    with pytest.raises(FocusPaused) as caught:
        inspect_post(
            current, expected_url=URL, observed_at=NOW, before_interaction=guard, timeout_ms=1500
        )
    assert caught.value is paused
    assert guard_calls == [1, 2]
    assert scrolls == ["first"]
    assert loads == ["first"]
