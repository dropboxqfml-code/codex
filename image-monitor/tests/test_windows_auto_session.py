"""Run two automatic collection cycles through an owned Windows Chrome desktop."""

import hashlib
import json
import os
import tempfile
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from functools import partial
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from PIL import Image
from test_monitor_auto_session_integration import listing
from test_monitor_setup_retry_integration import use_windows_browser
from test_watch_runtime import BrowserFactory, FakeClock, link, observed, snapshot
from test_windows_candidate_save import CandidatePageView
from test_windows_monitor_batch import POSTS, _html, _post_url
from test_windows_post_pipeline import fixture_assets, owned_ci_focus_distractor, serve_fixtures
from test_windows_post_pipeline import pytestmark as windows_ci_only

from image_monitor import (
    monitor_batch_runtime,
    monitor_operations,
    monitor_setup_retry,
    post_worker,
)
from image_monitor.candidate_browser import HeadlessCandidateBrowser
from image_monitor.candidate_runtime import run_candidate_trial
from image_monitor.monitor_auto_discovery import run_auto_discovery
from image_monitor.monitor_auto_session import run_auto_monitor
from image_monitor.monitor_collect import collect_session_turn
from image_monitor.monitor_save_ledger import LEDGER_NAME, LedgerStore
from image_monitor.watch_runtime import run_watch_trial

pytestmark = windows_ci_only


@pytest.mark.parametrize("lose_focus", [False, True], ids=["ten_in_one_run", "partial_post"])
def test_two_cycles_save_separate_owned_posts_and_resume_without_resaving(monkeypatch, lose_focus):
    clock = FakeClock(datetime.now(UTC) - timedelta(minutes=30))
    published = (clock.now() + timedelta(seconds=30)).astimezone(ZoneInfo("Asia/Seoul"))
    title = "Owned automatic session"
    header = {
        "title": title,
        "nickname": "fx",
        "published_at_raw": published.strftime("%Y.%m.%d %H:%M:%S"),
    }
    first, second = POSTS
    images = fixture_assets(title)
    first_paths = ["/render-first.png", "/render-photo.jpg", "/render-animation.gif"]
    for slot in range(4, 11):
        path = f"/render-{slot}.png"
        payload = BytesIO()
        Image.new("RGB", (slot + 3, slot + 2), (slot * 20, 128, 144)).save(payload, format="PNG")
        images[path] = ("image/png", payload.getvalue())
        first_paths.append(path)
    assert len({images[path][1] for path in first_paths}) == 10
    paths = {first: first_paths, second: ["/render-photo.jpg"]}
    assets = {path: images[path] for post_paths in paths.values() for path in post_paths}
    for post_id, post_paths in paths.items():
        document = _html(title, header, image_paths=post_paths)
        assets["/post-" + post_id] = ("text/html; charset=utf-8", document)

    anchor = "900000100"
    scan_browser = BrowserFactory(
        observed(lambda stamp: snapshot([anchor], stamp, links=[link()])),
        listing(first, anchor),
        *([listing(first, anchor)] if lose_focus else []),
        listing(second, first, anchor),
        listing(second, first, anchor),
    )
    discover = partial(
        run_auto_discovery, run_cycle=partial(run_watch_trial, backend_factory=scan_browser)
    )
    with (
        tempfile.TemporaryDirectory(prefix="as-", dir=os.environ["RUNNER_TEMP"]) as directory,
        serve_fixtures(assets) as (origin, requests),
        ExitStack() as cleanup,
    ):
        root = Path(directory).resolve()
        watch, legacy, batch = root / "w", root / "l", root / "b"
        marker = root / "pending.json"
        for module in (post_worker, monitor_batch_runtime, monitor_operations, monitor_setup_retry):
            monkeypatch.setattr(module, "shared_state_path", lambda: marker)
        baseline = discover(watch, clock=clock, interval_seconds=60)
        assert baseline["status"] == "baseline", baseline
        assert baseline["new_candidates"] == 0

        target_urls = [_post_url(first), _post_url(second)]
        details, saves, outcomes = [], [], []
        native_inputs = []

        class LocalPage(CandidatePageView):
            def goto(self, url, **options):
                assert url in target_urls
                self._post_url = url
                details.append(url)
                return self._page.goto(origin + "/post-" + url.split("no=")[-1], **options)

        class LocalCandidate(HeadlessCandidateBrowser):
            def __enter__(self):
                super().__enter__()
                self._page = LocalPage(self._page)
                return self

        def native(work, browser, url, **options):
            assert options["automatic_start"] is True
            assert url in target_urls
            with monkeypatch.context() as desktop, ExitStack() as interruption:
                use_windows_browser(desktop, cleanup, origin, url, saves)
                save_image = post_worker.save_body_image

                def record_native_save(page, ui, **kwargs):
                    ui.assert_target_ready()
                    native_inputs.append((page.url, kwargs["image"]["display_url"]))
                    return save_image(page, ui, **kwargs)

                desktop.setattr(post_worker, "save_body_image", record_native_save)
                if lose_focus and not outcomes:
                    next_image = post_worker._wait_for_next_image

                    def switch_before_seventh(
                        runtime, page, ui, snapshot, root, report, path, **kw
                    ):
                        if report["job_counts"]["completed"] == 6:
                            interruption.enter_context(owned_ci_focus_distractor(ui))
                        return next_image(runtime, page, ui, snapshot, root, report, path, **kw)

                    desktop.setattr(post_worker, "_wait_for_next_image", switch_before_seventh)
                result = post_worker.run_post_save(work, browser, url, **options)
                outcomes.append(
                    (
                        result["last_stage"],
                        result.get("native_stage"),
                        len(result["saved_files"]),
                        result["error_type"],
                        result.get("reason"),
                    )
                )
                return result

        session = partial(
            run_auto_monitor,
            watch,
            legacy,
            batch,
            clock=clock,
            scan_runner=discover,
            collect_runner=partial(
                collect_session_turn,
                detail_runner=partial(run_candidate_trial, backend_factory=LocalCandidate),
                save_runner=native,
            ),
        )
        if lose_focus:
            stopped = session(max_cycles=1)
            assert stopped["status"] == "auto_monitor_review", outcomes
            assert stopped["last_collection"]["worker_last_stage"] == "pre_input_check", outcomes
            assert stopped["browser_closed"] and not marker.exists()
            assert len(native_inputs) == 6
            [directory] = batch.glob(f"tasks/*/session-*/images/**/{first}")
            original_files = {
                directory / f"{i:03d}{Path(p).suffix}": images[p][1]
                for i, p in enumerate(first_paths[:6], start=1)
            }
            assert all(p.read_bytes() == original for p, original in original_files.items())
            original_mtimes = {p: p.stat().st_mtime_ns for p in original_files}
            [report] = batch.glob("tasks/*/session-*/runs/*/report.json")
            original_report = report.read_bytes()

            recovered = session(max_cycles=1)
            assert recovered["status"] == "auto_monitor_completed", (
                recovered["reason"],
                outcomes,
            )
            assert recovered["new_details_checked"] == recovered["new_candidates"] == 0
            assert recovered["posts_saved"] == recovered["native_save_tasks_started"] == 1
            assert recovered["files_verified"] == 10
            last = recovered["last_collection"]
            assert last["partial_retry_started"] and last["previously_verified_files"] == 6
            assert last["newly_saved_files"] == 4
            assert report.read_bytes() == original_report
            assert all(p.stat().st_mtime_ns == t for p, t in original_mtimes.items())
            assert all(p.read_bytes() == original for p, original in original_files.items())
            cycles = 1
        else:
            cycles = 2
        result = session(max_cycles=cycles)
        assert result["status"] == "auto_monitor_completed", (
            result["reason"],
            outcomes,
        )
        for count in (
            "cycles_completed",
            "list_checks",
            "new_candidates",
            "new_details_checked",
            "posts_saved",
        ):
            assert result[count] == cycles, result
        assert result["files_verified"] == (1 if lose_focus else 11), result
        expected_inputs = [
            (_post_url(post_id), origin + path)
            for post_id, post_paths in paths.items()
            for path in post_paths
        ]
        assert native_inputs == expected_inputs
        expected_visits = [target_urls[0], *target_urls] if lose_focus else target_urls
        assert details == target_urls and saves == expected_visits
        with LedgerStore(
            watch / LEDGER_NAME,
            watch_root=watch,
            legacy_root=legacy,
            batch_root=batch,
            read_only=True,
        ) as ledger:
            assert [(row["post_id"], row["status"]) for row in ledger.list_tasks()] == [
                (first, "completed"),
                (second, "completed"),
            ]
        saved_files = {}
        for post_id, post_paths in paths.items():
            [metadata] = batch.glob(f"tasks/*/session-*/images/**/{post_id}/metadata.json")
            saved_files[metadata] = (metadata.stat().st_mtime_ns, metadata.read_bytes())
            entries = json.loads(metadata.read_bytes())["images"]
            for slot, (path, entry) in enumerate(zip(post_paths, entries, strict=True), start=1):
                artifact = entry["artifact"]
                assert entry["status"] == "completed"
                assert entry["file_slot"] == artifact["body_order"] == slot
                assert artifact["display_url"] == origin + path
                name = f"{slot:03d}{Path(path).suffix}"
                assert artifact["saved_filename"] == name
                assert artifact["save_method"] == "native_context_menu_save_image_as"
                output = metadata.with_name(name)
                expected = images[path][1]
                assert output.read_bytes() == expected
                evidence = artifact["completion"]
                digest = hashlib.sha256(expected).hexdigest()
                assert artifact["verification"]["sha256"] == evidence["exclusive_sha256"] == digest
                assert evidence["state"] == "COMPLETE"
                assert evidence["source_confirmed"] and evidence["destination_confirmed"]
                saved_files[output] = (output.stat().st_mtime_ns, expected)

        repeat = session(max_cycles=1)
        assert repeat["status"] == "auto_monitor_completed", repeat
        assert repeat["cycles_completed"] == repeat["list_checks"] == 1
        assert repeat["new_candidates"] == repeat["posts_saved"] == repeat["files_verified"] == 0
        assert native_inputs == expected_inputs
        assert details == target_urls and saves == expected_visits
        assert set(saved_files) == {
            file for file in batch.glob("tasks/*/session-*/images/**/*") if file.is_file()
        }
        assert all(
            (file.stat().st_mtime_ns, file.read_bytes()) == item
            for file, item in saved_files.items()
        )
        assert requests.count("/post-" + first) == (3 if lose_focus else 2)
        assert requests.count("/post-" + second) == 2
        assert set(requests) <= {*assets, "/favicon.ico"}
        assert not marker.exists()
