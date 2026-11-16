"""Use one frozen candidate permit with real, owned Windows native saving."""

import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from test_windows_post_pipeline import (
    bind_and_foreground_ci_window,
    close_ci_browser,
    fixture_assets,
    serve_fixtures,
    wait_for_exclusive_saved_file,
)
from test_windows_post_pipeline import (
    pytestmark as windows_ci_only,
)

from image_monitor import native_body, post_worker
from image_monitor.artifact_files import finalize_saved_image
from image_monitor.browser_completion import BrowserCompletion
from image_monitor.candidate_policy import classify_candidate_detail
from image_monitor.candidate_save_policy import REVIEWED_SCOPE, make_candidate_save_permit
from image_monitor.dcinside import DIAGNOSTICS_JS, LOAD_JS, RAW_JS, parse_snapshot
from image_monitor.native_probe import (
    browser_executable,
    connect_owned_browser,
    wait_for_debug_port,
)
from image_monitor.native_ui import NativeSaveLock
from image_monitor.post_pipeline import enqueue_candidate_snapshot
from image_monitor.queue import QueueStore

POST_URL = "https://gall.dcinside.com/board/view/?id=comic_new6&no=900000001"
pytestmark = windows_ci_only


class CandidatePageView:
    """Expose an invented logical identity while all real requests stay on loopback."""

    def __init__(self, page):
        self._page = page

    @property
    def url(self):
        return POST_URL

    def __getattr__(self, name):
        return getattr(self._page, name)


def inspect_unverified_candidate(page, observed_at):
    root = page.locator(".write_div").element_handle()
    assert root is not None
    handles = []
    try:
        raw = root.evaluate(RAW_JS)
        raw["diagnostics"] = page.evaluate(DIAGNOSTICS_JS)
        handles = root.query_selector_all("img")
        assert len(handles) == len(raw["images"]) == 1
        for entry, image in zip(raw["images"], handles, strict=True):
            assert entry["excluded_reason"] is None
            image.scroll_into_view_if_needed(timeout=15_000)
            entry.update(image.evaluate(LOAD_JS, 15_000))
        return parse_snapshot(raw, expected_url=POST_URL, observed_at=observed_at)
    finally:
        for handle in [*handles, root]:
            handle.dispose()


def frozen_candidate_permit(snapshot):
    observed = datetime.fromisoformat(snapshot["observed_at"])
    published = datetime.fromisoformat(snapshot["published_at"])
    baseline_time = published - timedelta(minutes=1)
    first_seen = baseline_time + timedelta(seconds=10)
    scope = dict(
        zip(
            ("watch_name", "gallery_type", "gallery_id", "keyword", "search_type"),
            REVIEWED_SCOPE,
            strict=True,
        )
    )
    candidate = scope | {
        "post_id": snapshot["post_id"],
        "post_url": POST_URL,
        "first_scan_id": uuid.uuid4().hex,
        "first_seen_at": first_seen.isoformat(),
    }
    baseline = {"observed_at": baseline_time.isoformat()}
    finished = observed + timedelta(seconds=1)
    detail = scope | {
        "post_id": candidate["post_id"],
        "first_scan_id": candidate["first_scan_id"],
        "attempt_id": uuid.uuid4().hex,
        "baseline_observed_at": baseline_time.isoformat(),
        "started_at": (observed - timedelta(seconds=5)).isoformat(),
        "finished_at": finished.isoformat(),
        "status": "completed",
        "result": {
            "classification": classify_candidate_detail(candidate, baseline, snapshot),
            "private_observation": {
                "status": "observed",
                "http_status": 200,
                "url": POST_URL,
                "navigation_attempts": 1,
                "snapshot": snapshot,
            },
            "control": {
                "blocked": False,
                "http_status": 200,
                "finished_at": finished.isoformat(),
                "next_eligible_at": (finished + timedelta(seconds=60)).isoformat(),
                "interval_seconds": 60,
            },
        },
    }
    return make_candidate_save_permit(candidate, baseline, detail), first_seen


def test_owned_candidate_permit_saves_ambiguous_name_as_generic_png_without_resaving(monkeypatch):
    import psutil
    import pywinauto  # noqa: F401
    from playwright.sync_api import sync_playwright

    assert sys.__stderr__ is not None and not sys.__stderr__.closed
    for handler in logging.getLogger("pywinauto").handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, logging.FileHandler
        ):
            monkeypatch.setattr(handler, "stream", sys.__stderr__)

    title = "Image Monitor owned candidate " + uuid.uuid4().hex
    date = (datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(minutes=1)).strftime(
        "%Y.%m.%d %H:%M:%S"
    )
    header = {
        "title": "Invented candidate native save",
        "nickname": "fixture-author",
        "published_at_raw": date,
        "ip_display": None,
    }
    png = fixture_assets(title)["/render-first.png"]
    html = (
        '<!doctype html><meta charset="utf-8">'
        f"<title>{title}</title>"
        '<div class="gallview_head"><span class="title_subject">'
        f'{header["title"]}</span><div class="gall_writer" '
        f'data-nick="{header["nickname"]}"></div>'
        f'<span class="gall_date" title="{date}">{date}</span></div>'
        '<div class="appending_file"><a href="#" title="unproven-name.png">'
        'Unproven name</a></div><div class="write_div">'
        '<img src="/render-first.png" style="width:240px;height:180px"></div>'
    ).encode()
    assets = {"/post": ("text/html; charset=utf-8", html), "/render-first.png": png}
    with (
        tempfile.TemporaryDirectory(prefix="imc-", dir=os.environ["RUNNER_TEMP"]) as directory,
        serve_fixtures(assets) as (origin, requested),
        NativeSaveLock(),
    ):
        root = Path(directory)
        database, save_root, profile = root / "q.sqlite", root / "images", root / "profile"
        profile.mkdir()
        process = subprocess.Popen(
            [
                str(browser_executable("chrome")),
                f"--user-data-dir={profile}",
                "--remote-debugging-port=0",
                "--remote-debugging-address=127.0.0.1",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--force-renderer-accessibility",
                "--lang=en-US",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        owned_process = psutil.Process(process.pid)
        created_at = owned_process.create_time()
        driver = cleanup_session = ui = None
        try:
            port = wait_for_debug_port(profile, process, timeout=30)
            driver = sync_playwright().start()
            browser = connect_owned_browser(driver, port)
            cleanup_session = browser.new_browser_cdp_session()
            context = browser.contexts[0]
            actual_page = context.pages[0] if context.pages else context.new_page()
            actual_page.goto(origin + "/post", wait_until="load", timeout=30_000)
            assert actual_page.url == origin + "/post"
            page = CandidatePageView(actual_page)
            snapshot = inspect_unverified_candidate(page, datetime.now(UTC))
            assert snapshot["layout_status"] == "unverified"
            assert snapshot["queue_eligible"] is False
            image = snapshot["images"][0]
            assert image["original_filename_match_status"] == "ambiguous"
            assert image["original_attachment_filename"] is None
            permit, first_seen = frozen_candidate_permit(snapshot)
            authorized = permit.authorize_snapshot(snapshot)
            assert authorized["layout_status"] == "candidate_reviewed"
            nonce, _ = post_worker.install_approval(page, authorized, save_root)
            ui = bind_and_foreground_ci_window(process, actual_page)
            page.get_by_role("button", name="저장 시작", exact=True).click()
            post_worker.wait_for_approval(page, ui, nonce, timeout=10)
            fresh = inspect_unverified_candidate(page, datetime.now(UTC))
            authorized = permit.authorize_snapshot(fresh)
            with QueueStore(database) as store:
                queued = enqueue_candidate_snapshot(store, authorized, permit=permit)
                job_ids = [job["job_id"] for job in queued["jobs"]]
                assert len(job_ids) == 1
                post = store.get_post("normal", "comic_new6", snapshot["post_id"])
                assert datetime.fromisoformat(post["first_seen_at"]) == first_seen
                with BrowserCompletion(browser, context, page, "chrome", ui=ui) as completion:
                    job = store.claim_next("owned-candidate-ci", datetime.now(UTC), job_ids=job_ids)
                    assert job is not None and job["source"] is not None
                    source = job["source"]
                    image = source["image"] | {"expected_header": header}
                    staging = save_root / "_staging" / job["job_id"] / uuid.uuid4().hex
                    staging.mkdir(parents=True)

                    def arm_input():
                        store.transition(job["job_id"], job["lease_token"], "saving")

                    saved = native_body.save_body_image(
                        page,
                        ui,
                        post_url=POST_URL,
                        image=image,
                        staging_directory=staging,
                        before_native_input=arm_input,
                    )
                    store.transition(job["job_id"], job["lease_token"], "verifying")
                    staging_file = Path(saved["staging_path"])
                    evidence = completion.wait_for_completion(
                        staging_file, image["display_url"], ui, timeout=30
                    )
                    digest, verified = wait_for_exclusive_saved_file(staging_file, page, ui)
                    evidence["exclusive_sha256"] = digest
                    artifact = finalize_saved_image(
                        store,
                        job["job_id"],
                        job["lease_token"],
                        observation_id=source["observation_id"],
                        save_root=save_root,
                        staging_file=staging_file,
                        verification=verified,
                        completion_evidence=evidence,
                        browser_suggested_filename=saved["browser_suggested_filename"],
                        saved_at=datetime.now(UTC),
                    )
                assert artifact["phase"] == "finalized"
                final_file = Path(artifact["final_path"])
                assert final_file.name == "001.png"
                assert final_file.read_bytes() == png[1]
                assert verified["sha256"] == hashlib.sha256(png[1]).hexdigest()
                metadata_file = Path(artifact["metadata_path"])
                metadata_bytes = metadata_file.read_bytes()
                metadata = json.loads(metadata_bytes)
                saved_metadata = metadata["images"][0]["artifact"]
                assert saved_metadata["original_filename_match_status"] == "ambiguous"
                assert saved_metadata["original_attachment_filename"] is None
                assert saved_metadata["saved_filename"] == "001.png"
                assert saved_metadata["completion"]["state"] == "COMPLETE"
                assert store.claim_next("nothing-left", datetime.now(UTC)) is None
            close_ci_browser(process, owned_process, created_at, cleanup_session, ui)
            with QueueStore(database) as store:
                repeated = authorized | {"observed_at": datetime.now(UTC).isoformat()}
                queued = enqueue_candidate_snapshot(store, repeated, permit=permit)
                assert [job["job_id"] for job in queued["jobs"]] == job_ids
                assert {job["status"] for job in queued["jobs"]} == {"completed"}
                assert store.claim_next("reopened-candidate-ci", datetime.now(UTC)) is None
                post = store.get_post("normal", "comic_new6", snapshot["post_id"])
                assert datetime.fromisoformat(post["first_seen_at"]) == first_seen
                assert final_file.read_bytes() == png[1]
                assert metadata_file.read_bytes() == metadata_bytes
            assert set(requested) <= {"/post", "/render-first.png", "/favicon.ico"}
        finally:
            close_ci_browser(process, owned_process, created_at, cleanup_session, ui)
            if driver is not None:
                driver.stop()
