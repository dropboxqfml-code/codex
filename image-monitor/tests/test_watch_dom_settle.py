"""Exercise delayed and persistently incomplete search tables in a real browser."""

import shutil
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from test_watch_browser import NOW, PAGE_ONE, PAGE_TWO, SCOPE
from test_watch_trial_browser import list_html

from image_monitor import watch_browser


@pytest.mark.parametrize("hydrates", [False, True])
def test_single_passive_resample_keeps_actual_document_identity_and_page_time(
    monkeypatch, hydrates
):
    pytest.importorskip("playwright.sync_api")
    if sys.platform != "win32":
        executable = shutil.which("chromium") or shutil.which("google-chrome")
        if not executable:
            pytest.skip("Installed Chromium unavailable")
        monkeypatch.setattr(watch_browser, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "browser_executable", lambda _: Path(executable))

    html = list_html([101], PAGE_TWO).replace(
        "</body>",
        """<script>
        const aux = document.querySelector("table[id] tbody");
        const row = aux.firstElementChild;
        row.remove();
        window.populate = () => aux.appendChild(row);
        </script></body>""",
    )
    requests = []
    samples = []
    original_inspect = watch_browser.inspect_list

    def serve(route):
        requests.append(route.request.url)
        if route.request.url == PAGE_ONE:
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
        else:
            route.abort()

    def inspect(page, **options):
        result = original_inspect(page, **options)
        samples.append(result["layout_status"])
        if len(samples) == 1 and hydrates:
            # Schedule the fixture update only after the incomplete render was observed.
            page.evaluate("() => setTimeout(window.populate, 100)")
        return result

    monkeypatch.setattr(watch_browser, "inspect_list", inspect)
    times = iter((NOW, NOW + timedelta(seconds=1)))
    with watch_browser.HeadlessWatchBrowser(now=lambda: next(times)) as owned:
        owned._page.context.route("**/*", serve)
        result = owned.scan(SCOPE, NOW, max_pages=1)
    expected = "site_verified" if hydrates else "unverified"
    assert result["status"] == "observed" and owned.browser_closed is True
    assert requests == [PAGE_ONE]
    assert len(result["navigation"]) == 1
    assert samples == ["unverified", expected]
    [page] = result["pages"]
    assert page["layout_status"] == expected
    assert page["observed_at"] == (NOW + timedelta(seconds=1)).isoformat()
    assert page["scan_observed_at"] == NOW.isoformat(timespec="microseconds")
    assert page["selector_evidence"]["settle_initial_issue"] == "secondary_table_empty"
