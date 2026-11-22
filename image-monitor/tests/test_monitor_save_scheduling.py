"""Exercise the real scan lease, queue and native worker with a deliberately slow save."""

import shutil
import sys
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from threading import Event, get_ident

import pytest
from test_monitor_auto_session_integration import listing, local_workers
from test_monitor_auto_session_integration import session_data as session_data
from test_monitor_gap_continuation import run_scan
from test_post_worker import pilot as pilot
from test_watch_runtime import FakeClock, ScriptedBrowser, http_failure, link, observed, snapshot
from test_watch_trial_browser import list_html

from image_monitor import monitor_collect, post_worker, watch_browser, watch_runtime
from image_monitor.monitor_auto_discovery import run_auto_discovery
from image_monitor.monitor_auto_session import run_auto_monitor
from image_monitor.queue import QueueStore
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


def routed_list_chrome(post_ids):
    class RoutedListChrome(watch_browser.HeadlessWatchBrowser):
        def __enter__(self):
            super().__enter__()
            documents = {
                link(1)["canonical_url"]: list_html(post_ids, link(2)["canonical_url"]),
                link(2)["canonical_url"]: list_html(
                    [int(post_ids[-1]) - 1], link(3)["canonical_url"]
                ),
            }

            def serve(route):
                request = route.request
                if request.is_navigation_request() and request.url in documents:
                    route.fulfill(
                        content_type="text/html; charset=utf-8", body=documents[request.url]
                    )
                else:
                    route.abort()

            self._page.context.route("**/*", serve)
            return self

    return RoutedListChrome


@pytest.mark.parametrize(
    ("http_status", "session_data"),
    [(200, None), (429, None), (403, None), (200, "chromium_loopback")],
    indirect=["session_data"],
    ids=["two_due_lists", "rate_limited", "access_blocked", "stop_after_chrome_list"],
)
def test_durable_list_work_while_writer_still_owns_its_post(
    monkeypatch, pilot, session_data, http_status
):
    stop_with_chrome = session_data.allow_loopback
    roots = session_data.watch, session_data.legacy, session_data.batch
    database = session_data.watch / "watch.sqlite"
    clock = FakeClock(datetime.now(UTC) + timedelta(seconds=62))
    assert (
        run_scan(roots[0], clock, observed(lambda t: snapshot([200], t, links=[link()])))["status"]
        == "watch_test_completed"
    )
    clock.wait(60)
    if stop_with_chrome:
        pytest.importorskip("playwright.sync_api")
        if sys.platform != "win32":
            executable = shutil.which("chromium") or shutil.which("google-chrome")
            if not executable:
                pytest.skip("Installed Chromium unavailable")
            monkeypatch.setattr(watch_browser, "require_windows", lambda: None)
            monkeypatch.setattr(watch_browser, "browser_executable", lambda _: Path(executable))

    stop = Event()
    rate_limited = Event()
    owner = get_ident()
    checks = [Event(), Event()]
    inside_first_save = Event()
    events, owned, starts = [], [], []
    detail, save = local_workers(monkeypatch, pilot, clock, events, owned)
    regular_save = post_worker.save_body_image

    def slow_image(*args, **kwargs):
        if not starts:
            inside_first_save.set()
            for completed in checks[: 2 if http_status == 200 and not stop_with_chrome else 1]:
                # Simulate a busy disk/dialog at the point where the post worker owns the
                # image. There is no artificial delay in the monitor's scheduling code.
                clock.wait(61)
                if stop_with_chrome:
                    assert rate_limited.wait(8)
                    clock.wait(599)
                    assert not completed.wait(0.6)
                    clock.wait(1)
                assert completed.wait(35 if stop_with_chrome else 8), (
                    "A due list check did not finish during the save"
                )
            inside_first_save.clear()
        starts.append(kwargs["post_url"])
        return regular_save(*args, **kwargs)

    monkeypatch.setattr(post_worker, "save_body_image", slow_image)
    outcomes = iter(
        [
            listing(201, 200),
            listing(202, 201, 200) if http_status == 200 else http_failure(http_status, "600"),
            listing(203, 202, 201),
        ]
    )
    threads, scans = [], []

    def backend(*_args, **_kwargs):
        threads.append(get_ident())
        if get_ident() != owner:
            assert inside_first_save.is_set()
            with pytest.raises(WatchRunBusy), watch_run_lock(database, watch_runtime.DEFAULT_SCOPE):
                pass
            if stop_with_chrome:
                if len(threads) == 2:
                    return ScriptedBrowser([http_failure(429, "600")])
                return routed_list_chrome([202, 201, 200])(*_args, **_kwargs)
        return ScriptedBrowser([next(outcomes)])

    def discover(*args, **kwargs):
        result = run_auto_discovery(
            *args,
            **kwargs,
            run_cycle=partial(watch_runtime.run_watch_trial, backend_factory=backend),
        )
        scans.append((result["status"], result["reason"], result["browser_closed"]))
        if stop_with_chrome and result["status"] == "waiting":
            rate_limited.set()
        if get_ident() != owner and http_status != 200:
            assert result["status"] == ("blocked" if http_status == 403 else "waiting"), result
            checks[0].set()
        return result

    def progress(summary):
        if summary["phase"] == "scanned_during_save":
            with QueueStore(database, read_only=True) as queue:
                posts = WatchStore(queue).list_candidates(MONITOR_SCOPE)
                assert any(
                    row["post_id"] == str(201 + summary["list_checks_during_save"]) for row in posts
                )
            if stop_with_chrome:
                stop.set()
            checks[summary["list_checks_during_save"] - 1].set()

    report = run_auto_monitor(
        *roots,
        max_cycles=None if stop_with_chrome else 3,
        should_stop=stop.is_set if stop_with_chrome else None,
        clock=clock,
        scan_runner=discover,
        on_progress=progress,
        collect_runner=partial(
            monitor_collect.collect_session_turn, detail_runner=detail, save_runner=save
        ),
    )
    assert [step for step, *_ in events].count("save") == len(starts), (
        scans,
        len(threads),
        rate_limited.is_set(),
        stop.is_set(),
        report["last_collection"],
    )
    assert all(thread != owner for thread in threads[1:]) and threads[0] == owner
    assert all(browser.browser_closed for browser in owned)
    if stop_with_chrome:
        assert report["status"] == "auto_monitor_stopped", report
        assert report["list_checks"] == report["new_candidates"] == 2
        assert report["list_checks_during_save"] == report["posts_saved"] == len(starts) == 1
        assert len(threads) == 3
        with watch_run_lock(database, watch_runtime.DEFAULT_SCOPE):
            pass  # Both browser owners released the scope.
    elif http_status == 200:
        assert report["status"] == "auto_monitor_completed", report
        assert report["cycles_completed"] == report["new_candidates"] == report["list_checks"] == 3
        assert (
            report["list_checks_during_save"]
            == report["files_verified"]
            == report["posts_saved"]
            == 2
        )
        assert len(threads) == 3 and len(set(starts)) == 2
    else:
        assert report["status"] == (
            "auto_monitor_blocked" if http_status == 403 else "auto_monitor_waiting"
        ), report
        assert report["list_checks_during_save"] == 0 and report["list_checks"] == 1
        assert (
            report["native_save_tasks_started"] == report["newly_saved_files"] == len(starts) == 1
        )
        assert len(threads) == 2
        with QueueStore(database, read_only=True) as queue:
            state = WatchStore(queue).get_state(MONITOR_SCOPE)
            status, due = watch_runtime._eligibility(queue, state, clock.now())
            if http_status == 403:
                assert status == "blocked"
            else:
                assert status == "waiting" and due >= clock.now() + timedelta(seconds=599)
