"""Reopen retained body observations with mixed formats and exact persisted image slots."""

import hashlib
import json
from collections import deque
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from test_monitor_auto_session_integration import auto_session, listing, local_workers
from test_monitor_auto_session_integration import session_data as session_data
from test_monitor_batch_runtime import ledger
from test_monitor_gap_continuation import run_scan
from test_post_worker import pilot as pilot
from test_watch_runtime import FakeClock, link, observed, snapshot

from image_monitor import monitor_collect, post_worker
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_batch_runtime import reconstruct_permit
from image_monitor.native_ui import NativeUIError
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE

FORMATS = ("PNG", "JPEG", "WEBP", "GIF")
EXTENSIONS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif"}


def saved_post(base):
    return {
        p.name: (p.read_bytes(), p.stat().st_mtime_ns)
        for p in (base / "images").rglob("*")
        if p.is_file() and (p.stem.isdigit() or p.name == "metadata.json")
    }


def post_base(data, post):
    with ledger(data) as store:
        task = store.get_for_post(post)
    return data.batch / task["relative_root"] / f"session-{task['native_session']}"


@pytest.fixture
def monitor(session_data, pilot, monkeypatch):
    data = session_data
    clock = FakeClock(datetime.now(UTC) + timedelta(seconds=62))
    events, owned = [], []
    detail, save = local_workers(
        monkeypatch, pilot, clock, events, owned, image_counts={"201": 2, "202": 10, "203": 11}
    )
    fixture_save = post_worker.save_body_image

    def mixed_image(page, ui, **options):
        native = fixture_save(page, ui, **options)
        slot = options["image"]["body_order"]
        fmt = FORMATS[(slot - 1) % len(FORMATS)]
        path = Path(native["staging_path"])
        # Browser suggestions intentionally differ from the format identified in the bytes.
        Image.new("RGB", (4, 3), (slot * 17, slot * 9, 43)).save(path, format=fmt)
        return native

    monkeypatch.setattr(post_worker, "save_body_image", mixed_image)
    roots = data.watch, data.legacy, data.batch
    collect = partial(
        monitor_collect.run_monitor_collect,
        *roots,
        clock=clock,
        detail_runner=detail,
        save_runner=save,
    )
    pages = deque()
    automatic = auto_session(roots, clock, pages, events, owned, detail, save)
    baseline = observed(lambda stamp: snapshot([200], stamp, links=[link()]))
    assert run_scan(data.watch, clock, baseline)["status"] == "watch_test_completed"
    return SimpleNamespace(
        data=data,
        clock=clock,
        detail=detail,
        collect=collect,
        auto=automatic,
        pages=pages,
        events=events,
        owned=owned,
    )


def scan(monitor, *ids):
    monitor.clock.wait(60)
    result = run_scan(monitor.data.watch, monitor.clock, listing(*ids))
    assert result["status"] == "watch_test_completed", result


def freeze_detail(monitor):
    monitor.clock.wait(60)
    result = monitor.detail(
        monitor.data.watch, clock=monitor.clock, scope=MONITOR_SCOPE, max_candidates=1
    )
    assert result["candidates_completed"] == 1, result
    with QueueStore(monitor.data.watch / "watch.sqlite", read_only=True) as queue:
        return CandidateDetailStore(queue).list_details(MONITOR_SCOPE)[-1]


@pytest.mark.parametrize("entry", ["stored_one_shot", "fresh_auto"])
def test_ten_verified_slots_and_eleven_outside_limit_preserve_old_post(monitor, pilot, entry):
    data = monitor.data
    scan(monitor, 201, 200)
    assert monitor.collect()["files_verified"] == 2
    old_base = post_base(data, "201")
    originals = saved_post(old_base)
    assert set(originals) == {"001.png", "002.jpg", "metadata.json"}
    with ledger(data) as store:
        old_task = store.get_for_post("201")
    if entry == "stored_one_shot":
        scan(monitor, 202, 201)
        retained = freeze_detail(monitor)
        monitor.events.clear()
        report = monitor.collect()
        assert report["status"] == "monitor_collect_saved", report
        assert report["new_details_checked"] == 0
        saved = report["saved_files"]
        assert [e[:2] for e in monitor.events] == [("save", "202")]
    else:
        monitor.pages.append(listing(202, 201))
        report = monitor.auto(max_cycles=1)
        assert report["status"] == "auto_monitor_completed", report
        assert report["posts_saved"] == report["new_details_checked"] == 1
        saved = report["last_saved_files"]
    assert report["files_verified"] == len(saved) == 10 and report["browser_closed"]
    assert [f["detected_format"] for f in saved] == [FORMATS[i % 4] for i in range(10)]
    assert all(browser.browser_closed for browser in monitor.owned) and not data.marker.exists()
    with ledger(data) as store:
        task = store.get_for_post("202")
    assert task["status"] == "completed"
    with QueueStore(data.watch / "watch.sqlite", read_only=True) as queue:
        permit = reconstruct_permit(queue, task)
        detail = CandidateDetailStore(queue).get(task["detail_attempt_id"])
        if entry == "stored_one_shot":
            assert detail == retained
        assert permit.image_count == 10 and permit.fingerprint == task["permit_fingerprint"]
        assert [i["stable_key"] for i in permit.reference_snapshot["images"]] == pilot.saves[2:]
    base = post_base(data, "202")
    output = saved_post(base)
    metadata = json.loads(output["metadata.json"][0])
    with QueueStore(base / "queue.sqlite", read_only=True) as queue:
        jobs = sorted(queue.list_jobs(), key=lambda j: j["file_slot"])
        assert len(jobs) == len(metadata["images"]) == len(queue.list_artifacts()) == 10
        for slot, (job, published) in enumerate(zip(jobs, metadata["images"], strict=True), 1):
            fmt = FORMATS[(slot - 1) % len(FORMATS)]
            name = f"{slot:03d}.{EXTENSIONS[fmt]}"
            evidence = published["artifact"]["verification"]
            assert published["file_slot"] == slot and published["job_id"] == job["job_id"]
            assert job["status"] == "completed" and published["artifact"]["saved_filename"] == name
            assert evidence["detected_format"] == fmt
            assert evidence["sha256"] == hashlib.sha256(output[name][0]).hexdigest()
        assert len({j["job_id"] for j in jobs}) == 10
    assert len(output) == 11 and saved_post(old_base) == originals
    monitor.pages.append(listing(203, 202))
    exceeds = monitor.auto(max_cycles=1)
    assert exceeds["status"] == "auto_monitor_completed", exceeds
    assert exceeds["new_details_checked"] == 1
    assert exceeds["posts_saved"] == exceeds["files_verified"] == 0
    assert exceeds["native_save_tasks_started"] == 0
    reopened = monitor.collect()
    assert reopened["status"] == "monitor_collect_no_candidates", reopened
    assert reopened["search"]["outcome_counts"]["outside_save_limit"] == 1
    assert reopened["new_details_checked"] == reopened["native_save_tasks_started"] == 0
    assert len(pilot.saves) == len(set(pilot.saves)) == 12
    assert saved_post(old_base) == originals and saved_post(base) == output
    with ledger(data) as store:
        assert store.get_for_post("201") == old_task and store.get_for_post("202") == task
        assert store.get_for_post("203") is None


def test_uncertain_seventh_image_preserves_six_finalized_files_without_another_save(
    monitor, pilot, monkeypatch
):
    scan(monitor, 202, 200)
    complete = post_worker.BrowserCompletion.wait_for_completion

    def uncertain(completion, *args):
        if len(pilot.saves) == 7:
            raise NativeUIError("Synthetic completion proof unavailable")
        return complete(completion, *args)

    monkeypatch.setattr(post_worker.BrowserCompletion, "wait_for_completion", uncertain)
    failed = monitor.collect()
    assert failed["status"] == "monitor_collect_review", failed
    assert failed["worker_images_completed"] == 6 and failed["files_verified"] == 0
    assert failed["browser_closed"] is False and monitor.data.marker.exists()
    with ledger(monitor.data) as store:
        task = store.get_for_post("202")
    assert task["status"] == "needs_review"
    base = post_base(monitor.data, "202")
    files = saved_post(base)
    with QueueStore(base / "queue.sqlite", read_only=True) as queue:
        jobs = sorted(queue.list_jobs(), key=lambda j: j["file_slot"])
        artifacts = queue.list_artifacts()
        assert [j["status"] for j in jobs] == ["completed"] * 6 + ["paused_ui"] + ["queued"] * 3
        assert {a["job_id"] for a in artifacts} == {j["job_id"] for j in jobs[:6]}
        for item in artifacts:
            published = files[Path(item["final_relative"]).name][0]
            assert hashlib.sha256(published).hexdigest() == item["verification"]["sha256"]
    assert len(files) == 7
    stop = monitor.collect()
    assert stop["status"] == "monitor_collect_busy"
    assert stop["native_save_tasks_started"] == 0 and len(pilot.saves) == 7
    assert saved_post(base) == files and monitor.data.marker.exists()
    with ledger(monitor.data) as store:
        assert store.get_for_post("202") == task
    with QueueStore(base / "queue.sqlite", read_only=True) as queue:
        assert sorted(queue.list_jobs(), key=lambda j: j["file_slot"]) == jobs
        assert queue.list_artifacts() == artifacts
