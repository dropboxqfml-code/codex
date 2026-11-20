"""Save two owned fixture posts into separate durable batch tasks on Windows."""

import hashlib
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import test_windows_candidate_save as native_fixture
from test_candidate_save_selection import selected
from test_windows_post_pipeline import fixture_assets, serve_fixtures

from image_monitor.artifact_files import _relative_path
from image_monitor.candidate_policy import classify_candidate_detail
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_controller import MONITOR_SCOPE
from image_monitor.native_probe import browser_executable
from image_monitor.native_state import session_id
from image_monitor.queue import QueueStore
from image_monitor.watch_runtime import DEFAULT_SCOPE
from image_monitor.watch_store import WatchStore

pytestmark = native_fixture.pytestmark
POSTS = ("900000101", "900000102")


def _post_url(post_id):
    return f"https://gall.dcinside.com/board/view/?id=comic_new6&no={post_id}"


def _html(title, header, *, image_paths=("/render-first.png",)):
    body = "".join(f'<img src="{path}" style="width:240px;height:180px">' for path in image_paths)
    return (
        '<!doctype html><meta charset="utf-8">'
        f"<title>{title}</title>"
        '<div class="gallview_head"><span class="title_subject">'
        f'{header["title"]}</span><div class="gall_writer" '
        f'data-nick="{header["nickname"]}"></div>'
        f'<span class="gall_date" title="{header["published_at_raw"]}">'
        f"{header['published_at_raw']}</span></div>"
        '<div class="appending_file"><a href="#" title="unproven-name.png">'
        'Unproven name</a></div><div class="write_div">'
        f"{body}</div>"
    ).encode()


def _source_records(queue):
    watch = WatchStore(queue)
    detail = CandidateDetailStore(queue)
    return {
        scope.watch_name: (
            watch.get_state(scope),
            watch.list_candidates(scope),
            watch.list_scans(scope),
            watch.list_gaps(scope),
            detail.list_details(scope),
        )
        for scope in (DEFAULT_SCOPE, MONITOR_SCOPE)
    }


def _observe_and_seed(watch_root, origin, published):
    """Freeze real DOM observations before the native batch is allowed to run."""
    from playwright.sync_api import sync_playwright

    observed = {}
    with sync_playwright() as driver:
        browser = driver.chromium.launch(
            executable_path=str(browser_executable("chrome")),
            headless=True,
            args=["--disable-background-networking"],
        )
        try:
            page = browser.new_page(accept_downloads=False)
            for post_id in POSTS:
                page.goto(origin + "/post-" + post_id, wait_until="load")
                logical = native_fixture.CandidatePageView(page, post_url=_post_url(post_id))
                observed[post_id] = native_fixture.inspect_unverified_candidate(
                    logical, datetime.now(UTC)
                )
        finally:
            browser.close()

    baseline_at = published - timedelta(minutes=1)
    first_seen = published + timedelta(seconds=10)
    baseline = {
        "mode": "new",
        "observed_at": baseline_at.isoformat(),
        "anchor_ids": ["900000100"],
        "requires_published_at_filter": True,
    }
    with QueueStore(watch_root / "watch.sqlite") as queue:
        watch = WatchStore(queue)
        for generation, stamp, posts in ((0, baseline_at, ()), (1, first_seen, POSTS)):
            watch.persist_scan(
                MONITOR_SCOPE,
                observed_at=stamp,
                expected_generation=generation,
                scan_result={
                    "mode": "owned_batch_fixture",
                    "queue_eligible": False,
                    "control": {
                        "blocked": False,
                        "finished_at": stamp.isoformat(),
                        "next_eligible_at": (stamp + timedelta(seconds=60)).isoformat(),
                        "interval_seconds": 60,
                    },
                },
                candidates=[
                    {
                        "post_id": post_id,
                        "post_url": _post_url(post_id),
                        "title": "Invented batch candidate",
                        "shown_metadata": {"requires_published_at_filter": True},
                    }
                    for post_id in posts
                ],
                checkpoint=baseline | {"anchor_ids": [*posts, "900000100"]},
                complete=True,
                baseline=baseline if generation == 0 else None,
            )
        detail = CandidateDetailStore(queue)
        for candidate in watch.list_candidates(MONITOR_SCOPE):
            snapshot = observed[candidate["post_id"]]
            stamp = datetime.fromisoformat(snapshot["observed_at"])
            attempt = detail.start(
                MONITOR_SCOPE,
                candidate["post_id"],
                expected_first_scan_id=candidate["first_scan_id"],
                baseline_observed_at=baseline_at,
                started_at=stamp - timedelta(seconds=1),
            )
            detail.finish(
                attempt["attempt_id"],
                finished_at=stamp,
                result={
                    "classification": classify_candidate_detail(candidate, baseline, snapshot),
                    "private_observation": {
                        "status": "observed",
                        "url": candidate["post_url"],
                        "http_status": 200,
                        "navigation_attempts": 1,
                        "snapshot": snapshot,
                    },
                    "control": {
                        "blocked": False,
                        "http_status": 200,
                        "finished_at": stamp.isoformat(),
                        "next_eligible_at": (stamp + timedelta(seconds=60)).isoformat(),
                        "interval_seconds": 60,
                    },
                },
            )
        return _source_records(queue)


class _Clock:
    def __init__(self):
        self.current = datetime.now(UTC) + timedelta(seconds=1)

    def now(self):
        return self.current

    def wait(self, seconds):
        self.current += timedelta(seconds=seconds)

    def next_ready(self):
        self.current += timedelta(seconds=61)


def _native_files(batch_root):
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in batch_root.glob("tasks/*/session-*/images/**/*")
        if path.is_file() and path.name in {"001.png", "metadata.json"}
    }


def test_batch_saves_two_owned_posts_without_resaving_a_completed_task(monkeypatch):
    from image_monitor.monitor_batch_runtime import run_monitor_batch
    from image_monitor.monitor_save_ledger import LEDGER_NAME, LedgerStore

    title = "Image Monitor owned batch " + uuid.uuid4().hex
    published = (datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(minutes=3)).replace(microsecond=0)
    header = {
        "title": "Invented batch native save",
        "nickname": "fixture-author",
        "published_at_raw": published.strftime("%Y.%m.%d %H:%M:%S"),
        "ip_display": None,
    }
    document = _html(title, header)
    png = fixture_assets(title)["/render-first.png"]
    assets = {"/post-" + post_id: ("text/html; charset=utf-8", document) for post_id in POSTS}
    assets["/render-first.png"] = png
    with (
        tempfile.TemporaryDirectory(prefix="imb-", dir=os.environ["RUNNER_TEMP"]) as directory,
        serve_fixtures(assets) as (origin, requested),
    ):
        root = Path(directory)
        watch_root, legacy_root, batch_root = root / "w", root / "o", root / "b"
        watch_root.mkdir()
        legacy_root.mkdir()
        old_output = legacy_root / "previous-native-output.bin"
        old_output.write_bytes(b"Owned earlier trial output, never rewritten")
        previous_bytes = old_output.read_bytes()
        queue, _, _, old_selection, _ = selected(watch_root)
        queue.close()
        selection_bytes = old_selection.read_bytes()
        before = _observe_and_seed(watch_root, origin, published)
        clock = _Clock()
        calls = []

        def runner(work_root, browser, post_url, *, candidate_permit, navigation_observer):
            assert browser == "chrome"
            assert candidate_permit.watch_name == MONITOR_SCOPE.watch_name
            post_id = candidate_permit.reference_snapshot["post_id"]
            assert post_id in POSTS and post_url == _post_url(post_id)
            calls.append((post_id, work_root))
            base = work_root / f"session-{session_id()}"
            return native_fixture.run_owned_candidate_native(
                monkeypatch,
                root=base,
                post_url=post_url,
                permit_factory=lambda _snapshot: (candidate_permit, candidate_permit.first_seen_at),
                header=header,
                fixtures=(origin, requested),
                page_path="/post-" + post_id,
                queue_name="queue.sqlite",
                navigation_observer=navigation_observer,
                allowed_requests={
                    *("/post-" + item for item in POSTS),
                    "/render-first.png",
                    "/favicon.ico",
                },
            )

        first = run_monitor_batch(
            watch_root, legacy_root, batch_root, max_tasks=1, clock=clock, save_runner=runner
        )
        assert first["status"] == "monitor_batch_completed", first
        assert first["tasks_started"] == first["tasks_completed"] == 1
        assert first["tasks_remaining"] == 1
        first_files = _native_files(batch_root)
        assert len(first_files) == 2
        assert len(calls) == 1

        clock.next_ready()
        second = run_monitor_batch(
            watch_root, legacy_root, batch_root, max_tasks=1, clock=clock, save_runner=runner
        )
        assert second["status"] == "monitor_batch_completed", second
        assert second["tasks_started"] == second["tasks_completed"] == 1
        assert second["already_completed_count"] == 1
        assert second["tasks_remaining"] == 0
        assert len(calls) == 2 and calls[0][0] != calls[1][0]
        assert calls[0][1] != calls[1][1]
        all_files = _native_files(batch_root)
        assert len(all_files) == 4
        assert all(all_files[path] == evidence for path, evidence in first_files.items())

        clock.next_ready()
        third = run_monitor_batch(
            watch_root, legacy_root, batch_root, max_tasks=1, clock=clock, save_runner=runner
        )
        assert third["status"] == "monitor_batch_no_candidates", third
        assert third["tasks_started"] == third["tasks_completed"] == 0
        assert third["already_completed_count"] == 2 and len(calls) == 2
        assert _native_files(batch_root) == all_files
        assert old_output.read_bytes() == previous_bytes
        assert old_selection.read_bytes() == selection_bytes
        with QueueStore(watch_root / "watch.sqlite", read_only=True) as source:
            assert _source_records(source) == before
            assert source.summary()["posts"] == source.summary()["jobs"] == 0
        with LedgerStore(
            watch_root / LEDGER_NAME,
            watch_root=watch_root,
            legacy_root=legacy_root,
            batch_root=batch_root,
            read_only=True,
        ) as ledger:
            tasks = ledger.list_tasks()
            assert len(tasks) == 2 and {task["status"] for task in tasks} == {"completed"}
            assert {task["post_id"] for task in tasks} == set(POSTS)
        for native in batch_root.glob("tasks/*/session-*/queue.sqlite"):
            with QueueStore(native, read_only=True) as store:
                assert store.summary()["posts"] == store.summary()["jobs"] == 1
                assert store.list_jobs()[0]["status"] == "completed"
                artifact = store.list_artifacts()[0]
                final = _relative_path(Path(artifact["save_root"]), artifact["final_relative"])
                assert (
                    hashlib.sha256(final.read_bytes()).hexdigest()
                    == hashlib.sha256(png[1]).hexdigest()
                )
