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

from PIL import Image
from test_monitor_auto_session_integration import listing
from test_monitor_setup_retry_integration import use_windows_browser
from test_watch_runtime import BrowserFactory, FakeClock, link, observed, snapshot
from test_windows_candidate_save import CandidatePageView
from test_windows_monitor_batch import POSTS, _html, _post_url
from test_windows_post_pipeline import fixture_assets, serve_fixtures
from test_windows_post_pipeline import pytestmark as windows_ci_only

from image_monitor import monitor_batch_runtime, monitor_operations, post_worker
from image_monitor.candidate_browser import HeadlessCandidateBrowser
from image_monitor.candidate_runtime import run_candidate_trial
from image_monitor.monitor_auto_discovery import run_auto_discovery
from image_monitor.monitor_auto_session import run_auto_monitor
from image_monitor.monitor_collect import collect_session_turn
from image_monitor.monitor_save_ledger import LEDGER_NAME, LedgerStore
from image_monitor.watch_runtime import run_watch_trial

pytestmark = windows_ci_only


def test_two_cycles_save_separate_owned_posts_and_resume_without_resaving(monkeypatch):
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
        for module in (post_worker, monitor_batch_runtime, monitor_operations):
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
            with monkeypatch.context() as desktop:
                use_windows_browser(desktop, cleanup, origin, url, saves)
                save_image = post_worker.save_body_image

                def record_native_save(page, ui, **kwargs):
                    ui.assert_target_ready()
                    native_inputs.append((page.url, kwargs["image"]["display_url"]))
                    return save_image(page, ui, **kwargs)

                desktop.setattr(post_worker, "save_body_image", record_native_save)
                result = post_worker.run_post_save(work, browser, url, **options)
                outcomes.append(
                    {key: result[key] for key in ("status", "last_stage", "error_type")}
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
        result = session(max_cycles=2)
        assert result["status"] == "auto_monitor_completed", (result, outcomes)
        for count in (
            "cycles_completed",
            "list_checks",
            "new_candidates",
            "new_details_checked",
            "posts_saved",
        ):
            assert result[count] == 2, result
        assert result["files_verified"] == 11, result
        expected_inputs = [
            (_post_url(post_id), origin + path)
            for post_id, post_paths in paths.items()
            for path in post_paths
        ]
        assert native_inputs == expected_inputs
        assert details == saves == target_urls
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
        assert details == saves == target_urls
        assert set(saved_files) == {
            file for file in batch.glob("tasks/*/session-*/images/**/*") if file.is_file()
        }
        assert all(
            (file.stat().st_mtime_ns, file.read_bytes()) == item
            for file, item in saved_files.items()
        )
        assert all(requests.count("/post-" + post_id) == 2 for post_id in POSTS)
        assert set(requests) <= {*assets, "/favicon.ico"}
        assert not marker.exists()
