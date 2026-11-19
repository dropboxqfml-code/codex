"""Run the complete discovery path in a real browser against routed HTML."""

import shutil
import sys
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path

import pytest

from image_monitor import watch_browser, watch_runtime
from image_monitor.queue import QueueStore
from image_monitor.search_list import build_list_url
from image_monitor.watch_store import WatchStore


class AdvancingClock:
    def __init__(self):
        self.current = datetime(2026, 11, 15, 12, tzinfo=UTC)
        self.waits = []

    def now(self):
        return self.current

    def wait(self, seconds):
        self.waits.append(seconds)
        self.current += timedelta(seconds=seconds)


def list_html(ids, next_url, *, excluded_html=""):
    rows = [excluded_html]
    for post_id in ids:
        rows.append(
            '<tr class="ub-content">'
            f'<td class="gall_num">{post_id}</td>'
            '<td class="gall_tit"><a '
            f'href="/board/view/?id=comic_new6&amp;no={post_id}">'
            f"Invented title {post_id}</a></td>"
            '<td class="gall_writer">Invented author</td>'
            '<td class="gall_date">12:00</td></tr>'
        )
    return (
        '<!doctype html><html><head><meta charset="utf-8"></head><body>'
        '<table class="gall_list"><tbody>'
        + "".join(rows)
        + '</tbody></table><table class="gall_list" id="invented_recommendation"><tbody>'
        '<tr><td class="gall_num">900</td><td class="gall_tit">'
        '<a href="/board/view/?id=comic_new6&amp;no=900">Invented recommendation</a>'
        '</td><td class="gall_date">12:00</td></tr></tbody></table>'
        f'<div class="bottom_paging_box"><a href="{escape(next_url, quote=True)}">'
        "Next</a></div></body></html>"
    )


def special_row(label, href, *, has_writer=True):
    writer = '<td class="gall_writer">Invented writer</td>' if has_writer else ""
    return (
        f'<tr class="ub-content"><td class="gall_num">{label}</td>'
        f'<td class="gall_tit"><a href="{href}">{label}</a></td>'
        f'{writer}<td class="gall_date">12:00</td></tr>'
    )


@pytest.mark.parametrize(
    ("second_page_verified", "ad_has_writer"),
    [(True, True), (False, True), (True, False)],
)
def test_real_browser_two_cycle_discovery_uses_verified_dom_and_durable_state(
    tmp_path, monkeypatch, second_page_verified, ad_has_writer
):
    pytest.importorskip("playwright.sync_api")
    if sys.platform != "win32":
        executable = shutil.which("chromium") or shutil.which("google-chrome")
        if not executable:
            pytest.skip("Installed Chromium unavailable")
        monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "browser_executable", lambda _: Path(executable))

    first_url = build_list_url("normal", "comic_new6", "ai")
    second_url = build_list_url("normal", "comic_new6", "ai", page=2)
    third_url = build_list_url("normal", "comic_new6", "ai", page=3)
    baseline_ids = list(range(100, 80, -1))
    first_ids = list(range(102, 82, -1))
    second_ids = list(range(82, 62, -1))
    notice = special_row("공지", "/board/view/?id=comic_new6&amp;no=1")
    survey = special_row("설문", "javascript:void(0)")
    ad = special_row("광고", "/fixture/ad", has_writer=ad_has_writer)
    adjacent_html = list_html(second_ids, third_url, excluded_html=notice)
    if not second_page_verified:
        adjacent_html = adjacent_html.replace("Invented author", "")
    documents = [
        (first_url, list_html(baseline_ids, second_url)),
        (first_url, list_html(first_ids, second_url, excluded_html=ad + survey + notice)),
        (second_url, adjacent_html),
    ]
    navigation = []
    unexpected_requests = []
    owned_browsers = []
    sessions = []

    def local_document(route):
        url = route.request.url
        if (
            route.request.is_navigation_request()
            and len(navigation) < len(documents)
            and url == documents[len(navigation)][0]
        ):
            html = documents[len(navigation)][1]
            navigation.append(url)
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
        else:
            unexpected_requests.append(url)
            route.abort()

    class RoutedBrowser(watch_browser.HeadlessWatchBrowser):
        def __enter__(self):
            entered = super().__enter__()
            sessions.append(self)
            owned_browsers.append(self._owned_browser)
            self._page.context.route("**/*", local_document)
            return entered

    clock = AdvancingClock()
    report = watch_runtime.run_watch_trial(tmp_path, backend_factory=RoutedBrowser, clock=clock)

    expected_status = "watch_test_completed" if second_page_verified else "watch_test_partial"
    assert report["status"] == expected_status, report
    if not second_page_verified:
        assert report["reason"] == "list_profile_unverified_or_incomplete"
    assert report["cycles_completed"] == 2
    assert report["baseline_initialized"] is True
    assert report["new_candidates"] == report["candidate_count"] == 2
    assert report["images_saved"] is False
    assert report["image_jobs_created"] == 0
    assert clock.waits == [60]
    assert navigation == [first_url, first_url, second_url]
    assert unexpected_requests == []
    assert [cycle["navigation_attempts"] for cycle in report["cycles"]] == [1, 2]
    assert [cycle["layout_statuses"] for cycle in report["cycles"]] == [
        ["site_verified"],
        ["site_verified", "site_verified" if second_page_verified else "unverified"],
    ]
    shared = watch_runtime.share_watch_report(report)
    public_first, public_second = shared["cycles"][1]["page_checks"]
    assert public_first["layout_status"] == "site_verified"
    if ad_has_writer:
        assert "author_cell_mismatches" not in public_first
    else:
        assert public_first["author_cell_mismatches"] == {"ad": {"missing": 1}}
    assert "author_cell_mismatches" not in public_second
    assert len(sessions) == len(owned_browsers) == 1
    assert report["browser_closed"] is sessions[0].browser_closed is True
    assert owned_browsers[0].is_connected() is False

    with QueueStore(tmp_path / "watch.sqlite") as queue:
        store = WatchStore(queue)
        state = store.get_state(watch_runtime.DEFAULT_SCOPE)
        scans = list(reversed(store.list_scans(watch_runtime.DEFAULT_SCOPE)))
        candidates = store.list_candidates(watch_runtime.DEFAULT_SCOPE)
        assert state["generation"] == 2
        assert state["baseline"]["anchor_ids"] == list(map(str, baseline_ids))
        expected_anchors = first_ids if second_page_verified else baseline_ids
        assert state["checkpoint"]["anchor_ids"] == list(map(str, expected_anchors))
        assert {candidate["post_id"] for candidate in candidates} == {"102", "101"}
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0
        assert [scan["complete"] for scan in scans] == [True, second_page_verified]
        assert all(scan["result"]["queue_eligible"] is False for scan in scans)
        observations = [scan["result"]["private_observation"] for scan in scans]
        assert [len(outcome["navigation"]) for outcome in observations] == [1, 2]
        first_page, second_page = observations[1]["pages"]
        assert [len(page["rows"]) for page in (first_page, second_page)] == [20, 20]
        assert [row["reason"] for row in first_page["excluded_rows"]] == ["ad", "survey", "pinned"]
        assert first_page["excluded_rows"][0]["field_counts"]["author"] == int(ad_has_writer)
        assert [row["reason"] for row in second_page["excluded_rows"]] == ["pinned"]
        assert [
            page["selector_evidence"]["live_layout_verified"]
            for outcome in observations
            for page in outcome["pages"]
        ] == [True, True, second_page_verified]
        first_scan, second_scan = (datetime.fromisoformat(scan["observed_at"]) for scan in scans)
        assert second_scan - first_scan >= timedelta(seconds=60)
