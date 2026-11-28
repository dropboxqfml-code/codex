"""Keep a recovered image intact while two automatic cycles save distinct new posts."""

import hashlib
import json
import os
import socket
import sys
import tempfile
from collections import deque
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from functools import partial
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from test_candidate_runtime import ScriptedBrowser as DetailBrowser
from test_candidate_save_selection import snapshot as detail_snapshot
from test_monitor_batch_runtime import ledger
from test_monitor_collect_integration import saved_content
from test_monitor_gap_continuation import run_scan
from test_monitor_setup_retry_integration import failed_enter
from test_post_worker import pilot as pilot
from test_watch_runtime import FakeClock, ScriptedBrowser, link, observed, snapshot

from image_monitor import (
    candidate_finish,
    candidate_runtime,
    monitor_auto_selection,
    monitor_batch_runtime,
    monitor_collect,
    monitor_operations,
    monitor_setup_retry,
    monitor_trial_progress,
    post_worker,
    watch_runtime,
)
from image_monitor.auto_monitor_cli import _describe_result
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_auto_discovery import run_auto_discovery
from image_monitor.monitor_auto_session import run_auto_monitor
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE


def listing(*post_ids):
    """Two verified local pages, including an overlap page beyond the first anchor."""
    return observed(
        lambda stamp: snapshot(post_ids, stamp, links=[link()]),
        lambda stamp: snapshot([int(post_ids[-1]) - 1], stamp, page=2),
    )


@pytest.fixture
def session_data(monkeypatch, pilot, request):
    # A short path also exercises the production filename budget on Windows CI.
    with tempfile.TemporaryDirectory(prefix="as-", dir=os.environ.get("RUNNER_TEMP")) as folder:
        root = Path(folder).resolve()
        marker = root / "pending.json"
        allow_loopback = getattr(request, "param", None) == "chromium_loopback"
        isolate_desktop(monkeypatch, marker, allow_loopback=allow_loopback)
        yield SimpleNamespace(
            watch=root / "w",
            legacy=root / "l",
            batch=root / "b",
            marker=marker,
            allow_loopback=allow_loopback,
        )


def isolate_desktop(monkeypatch, marker, *, allow_loopback=False):
    def no_network(*_args, **_kwargs):
        pytest.fail("An integration fixture tried to open a network connection")

    original_connect = socket.socket.connect

    def fixture_connect(sock, address):
        # Windows asyncio creates its self-pipe by connecting a local TCP socketpair.
        if (
            allow_loopback
            and sock.family in (socket.AF_INET, socket.AF_INET6)
            and address[0] in ("127.0.0.1", "::1")
        ):
            return original_connect(sock, address)
        no_network()

    monkeypatch.setattr(socket.socket, "connect", fixture_connect)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    for module in (candidate_runtime, watch_runtime, monitor_batch_runtime):
        monkeypatch.setattr(module, "require_windows", lambda: None)
    for module in (monitor_batch_runtime, monitor_operations, monitor_auto_selection):
        monkeypatch.setattr(module, "NativeSaveLock", nullcontext)
    for module in (monitor_batch_runtime, monitor_operations, monitor_setup_retry):
        monkeypatch.setattr(module, "session_id", lambda: 1)
    for module in (post_worker, monitor_batch_runtime, monitor_operations, monitor_setup_retry):
        monkeypatch.setattr(module, "shared_state_path", lambda: marker)
    monkeypatch.setattr(monitor_setup_retry, "browser_still_running", lambda _: False)
    monkeypatch.setattr(
        candidate_finish, "exclusive_digest", lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    )


def local_workers(monkeypatch, pilot, clock, events, owned, *, image_counts=None):
    def inspect(candidate, stamp):
        events.append(("detail", candidate["post_id"], stamp))
        count = image_counts[candidate["post_id"]] if image_counts is not None else 1
        body = detail_snapshot(candidate, observed_at=stamp, published=stamp, count=count)
        body.update(title="Synthetic controller fixture", nickname="fx")
        return {
            "status": "observed",
            "http_status": 200,
            "navigation_attempts": 1,
            "url": candidate["post_url"],
            "snapshot": body,
        }

    def detail_backend(*_args, **_kwargs):
        browser = DetailBrowser([inspect])
        owned.append(browser)
        return browser

    detail = partial(candidate_runtime.run_candidate_trial, backend_factory=detail_backend)
    fixture_save = post_worker.save_body_image

    def save_colored_image(*args, **options):
        result = fixture_save(*args, **options)
        post_id = int(options["post_url"].split("no=")[1])
        Image.new("RGB", (4, 3), (post_id, 0, 0)).save(result["staging_path"])
        return result

    monkeypatch.setattr(post_worker, "save_body_image", save_colored_image)

    def save(task_root, browser, url, **options):
        assert options["automatic_start"]
        reference = options["candidate_permit"].reference_snapshot
        events.append(("save", reference["post_id"], clock.now()))
        pilot.root, pilot.expected_url = task_root, url
        pilot.snapshots = [reference, reference]
        return post_worker.run_post_save(task_root, browser, url, **options)

    return detail, save


def auto_session(roots, clock, pages, events, owned, detail, save):
    def list_backend(*_args, **_kwargs):
        outcome = pages.popleft()

        def scan(stamp):
            result = outcome(stamp)
            events.append(("list", result["pages"][0]["rows"][0]["post_id"], stamp))
            return result

        browser = ScriptedBrowser([scan])
        owned.append(browser)
        return browser

    return partial(
        run_auto_monitor,
        *roots,
        clock=clock,
        scan_runner=partial(
            run_auto_discovery,
            run_cycle=partial(watch_runtime.run_watch_trial, backend_factory=list_backend),
        ),
        collect_runner=partial(
            monitor_collect.collect_session_turn, detail_runner=detail, save_runner=save
        ),
    )


def test_two_auto_cycles_preserve_prior_recovery_and_reopen_without_duplicate(
    monkeypatch, pilot, session_data
):
    data = session_data
    clock = FakeClock(datetime.now(UTC) + timedelta(seconds=62))
    events = []
    owned = []

    detail, save = local_workers(monkeypatch, pilot, clock, events, owned)
    roots = data.watch, data.legacy, data.batch
    baseline = observed(lambda stamp: snapshot([200], stamp, links=[link()]))
    assert run_scan(data.watch, clock, baseline)["status"] == "watch_test_completed"
    clock.wait(60)
    assert run_scan(data.watch, clock, listing(203, 200))["new_candidates"] == 1
    old_collect = partial(
        monitor_collect.run_monitor_collect,
        *roots,
        clock=clock,
        detail_runner=detail,
        save_runner=save,
    )
    clock.wait(60)
    with monkeypatch.context() as fault:
        fault.setattr(post_worker.BrowserCompletion, "__enter__", failed_enter)
        failed = old_collect()
    assert failed["save"]["worker_last_stage"] == "completion_setup", failed
    assert failed["files_verified"] == 0 and failed["browser_closed"]
    clock.wait(60)
    recovered = old_collect()
    assert recovered["setup_retry_started"] and recovered["files_verified"] == 1, recovered
    assert recovered["browser_closed"] and not data.marker.exists()
    with ledger(data) as store:
        original_task = store.get_for_post("203")
    assert original_task["status"] == "completed"
    original_files = saved_content(data)
    assert len(original_files) == 2
    session_root = data.batch / "tasks" / original_task["task_id"] / "session-1"
    with QueueStore(session_root / "queue.sqlite", read_only=True) as queue:
        [original_job] = queue.list_jobs()
    reports = {p: p.read_bytes() for p in (session_root / "runs").glob("*/report.json")}
    assert len(reports) == 2
    events.clear()

    pages = deque([listing(204, 203), listing(205, 204), listing(205, 204)])
    session = auto_session(roots, clock, pages, events, owned, detail, save)
    report = session(max_cycles=2)
    assert report["status"] == "auto_monitor_completed", json.dumps(report, indent=2)
    assert report["reason"] == "cycle_limit_reached" and report["browser_closed"]
    assert report["cycles_completed"] == report["list_checks"] == report["new_candidates"] == 2
    assert report["new_details_checked"] == report["posts_saved"] == report["files_verified"] == 2
    assert [
        (turn["uninspected_at_selection"], turn["fresh_detail_outcome"])
        for turn in report["recent_collection_attempts"]
    ] == [(0, "save_ready"), (0, "save_ready")]
    completed_files = saved_content(data)
    assert len(completed_files) == 6
    assert all(completed_files[p] == v for p, v in original_files.items())
    images = [p for p in completed_files if p.name == "001.png"]
    assert {p.parent.name for p in images} == {"203", "204", "205"}
    for path in images:
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.getpixel((0, 0)) == (int(path.parent.name), 0, 0)
        [item] = json.loads((path.parent / "metadata.json").read_bytes())["images"]
        assert (
            item["artifact"]["verification"]["sha256"]
            == hashlib.sha256(path.read_bytes()).hexdigest()
        )
    reopened = session(max_cycles=1)
    assert reopened["status"] == "auto_monitor_completed", reopened
    assert reopened["cycles_completed"] == reopened["list_checks"] == 1
    assert reopened["new_candidates"] == reopened["new_details_checked"] == 0
    assert reopened["posts_saved"] == reopened["files_verified"] == 0 and reopened["browser_closed"]
    assert not pages and all(browser.browser_closed for browser in owned)
    assert all(not runtime.alive and runtime.disconnects for runtime in pilot.runtimes)
    assert not data.marker.exists() and saved_content(data) == completed_files
    assert [(action, post) for action, post, _ in events] == [
        ("list", "204"),
        ("detail", "204"),
        ("save", "204"),
        ("list", "205"),
        ("detail", "205"),
        ("save", "205"),
        ("list", "205"),
    ]
    assert all(
        later[2] - earlier[2] >= timedelta(seconds=60) for earlier, later in pairwise(events)
    )
    with ledger(data) as store:
        assert store.get_for_post("203") == original_task
        assert {t["post_id"]: t["status"] for t in store.list_tasks()} == {
            "203": "completed",
            "204": "completed",
            "205": "completed",
        }
    with QueueStore(session_root / "queue.sqlite", read_only=True) as queue:
        assert queue.list_jobs() == [original_job]
    assert {p: p.read_bytes() for p in (session_root / "runs").glob("*/report.json")} == reports
    with QueueStore(data.watch / "watch.sqlite", read_only=True) as queue:
        details = CandidateDetailStore(queue)
        assert [d["post_id"] for d in details.list_details(MONITOR_SCOPE)] == ["203", "204", "205"]
        assert not details.list_pending(MONITOR_SCOPE, limit=10)


def test_trial_finishes_before_unreachable_save_and_reopens_same_post(
    monkeypatch, pilot, session_data
):
    data = session_data
    roots = data.watch, data.legacy, data.batch
    clock = FakeClock(datetime.now(UTC) + timedelta(seconds=62))
    events, owned = [], []
    detail, save = local_workers(monkeypatch, pilot, clock, events, owned)
    baseline = observed(lambda stamp: snapshot([200], stamp, links=[link()]))
    assert run_scan(data.watch, clock, baseline)["status"] == "watch_test_completed"
    clock.wait(60)
    elapsed = 0

    def inspect(*args, **options):
        nonlocal elapsed
        result = detail(*args, **options)
        if options["monitor_target"][1] == "202":
            elapsed = 267
        return result

    monkeypatch.setattr(monitor_trial_progress, "monotonic", lambda: elapsed)
    pages = deque([listing(201, 200), listing(202, 201), listing(202, 201)])
    session = auto_session(roots, clock, pages, events, owned, inspect, save)
    trial = monitor_trial_progress.MonitorTrial(lambda: nullcontext(sys.stderr), None)
    with trial.observe():
        result = session(max_cycles=2, should_stop=trial.should_stop)
    assert (
        result["status"] == "auto_monitor_waiting" and result["reason"] == "save_due_after_trial"
    ), result
    assert result["cycles_completed"] == result["posts_saved"] == result["files_verified"] == 1
    assert result["list_checks"] == result["new_details_checked"] == 2 and result["browser_closed"]
    assert result["last_collection"]["fresh_detail_outcome"] == "save_ready"
    assert (
        trial.stop_trigger is None
        and "다음 실행" in _describe_result(result)["auto_test_summary_ko"]
    )
    due = datetime.fromisoformat(result["next_eligible_at"])
    assert due - clock.now() == timedelta(seconds=60)
    original = saved_content(data)
    assert original
    clock.wait(60)
    resumed = session(max_cycles=1)
    assert resumed["status"] == "auto_monitor_completed", resumed
    assert resumed["new_details_checked"] == 0 and resumed["newly_saved_files"] == 1
    assert [(op, post) for op, post, _ in events if op in ("detail", "save")] == [
        ("detail", "201"),
        ("save", "201"),
        ("detail", "202"),
        ("save", "202"),
    ]
    assert all(saved_content(data)[path] == content for path, content in original.items())
