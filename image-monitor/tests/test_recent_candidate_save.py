"""Exact trial handoffs retain per-post native evidence and prior pilot ownership."""

import hashlib
import sys
import tempfile
import uuid
from contextlib import nullcontext
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_candidate_runtime import BrowserFactory as DetailBrowser
from test_candidate_save_selection import snapshot
from test_monitor_batch_runtime import finalize
from test_monitor_save_ledger import plan
from test_watch_runtime import BrowserFactory, FakeClock, baseline_outcome, new_posts_outcome

from image_monitor import candidate_finish, candidate_runtime, watch_runtime
from image_monitor import monitor_batch_finish as finish
from image_monitor import monitor_batch_runtime as native
from image_monitor.candidate_save_policy import make_candidate_save_permit
from image_monitor.candidate_save_selection import (
    MANIFEST_NAME,
    MONITOR_MANIFEST_NAME,
    select_candidate_save,
)
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_save_ledger import LEDGER_NAME, LedgerStore
from image_monitor.native_state import PendingSave
from image_monitor.queue import QueueError, QueueStore
from image_monitor.watch_runtime import DEFAULT_SCOPE, _eligibility
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


@pytest.fixture
def recent(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="imr") as short:
        base = Path(short)
        watch = base / "w"
        watch.mkdir()
        for module in (watch_runtime, candidate_runtime, native, finish):
            monkeypatch.setattr(module, "require_windows", lambda: None)
        for module in (native, finish):
            monkeypatch.setattr(module, "NativeSaveLock", nullcontext)
            monkeypatch.setattr(module, "session_id", lambda: 1)
            monkeypatch.setattr(module, "shared_state_path", lambda: base / "pending.json")
        if sys.platform != "win32":
            monkeypatch.setattr(
                candidate_finish,
                "exclusive_digest",
                lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            )
        clock = FakeClock()
        scan = watch_runtime.run_watch_trial(
            watch, clock=clock, backend_factory=BrowserFactory(baseline_outcome, new_posts_outcome)
        )
        assert scan["new_candidates"] == 2

        def body(candidate, now):
            observed = snapshot(candidate, observed_at=now, published=now - timedelta(seconds=1))
            observed["nickname"] = "fx"
            return {
                "status": "observed",
                "http_status": 200,
                "url": candidate["post_url"],
                "navigation_attempts": 1,
                "snapshot": observed,
            }

        for _ in range(2):
            observed = candidate_runtime.run_candidate_trial(
                watch,
                recent_scan_only=True,
                max_candidates=1,
                clock=clock,
                backend_factory=DetailBrowser(body),
            )
            assert observed["status"] == "candidate_test_completed"
        clock.wait(60)
        with QueueStore(watch / "watch.sqlite", read_only=True) as queue:
            store = WatchStore(queue)
            state = store.get_state(DEFAULT_SCOPE)
            candidates = {c["post_id"]: c for c in store.list_candidates(DEFAULT_SCOPE)}
            handoffs = {}
            for detail in CandidateDetailStore(queue).list_details(DEFAULT_SCOPE):
                post = detail["post_id"]
                permit = make_candidate_save_permit(candidates[post], state["baseline"], detail)
                handoffs[post] = {
                    "scan_id": state["latest_scan"]["scan_id"],
                    "attempt_id": detail["attempt_id"],
                    "fingerprint": permit.fingerprint,
                }
        yield SimpleNamespace(
            roots=(watch, base / "old", base / "new"), watch=watch, handoffs=handoffs, clock=clock
        )


def save(recent, handoff, runner):
    return native.run_recent_save(*recent.roots, handoff, clock=recent.clock, save_runner=runner)


def never(*args, **kwargs):
    pytest.fail("No repeated or unbound native worker may run")


def test_exact_save_repeats_offline_and_other_trial_selector_skips_the_completed_post(recent):
    handoff = recent.handoffs["103"]
    calls = []

    def commit(root, browser, url, *, candidate_permit, navigation_observer):
        assert candidate_permit.detail_attempt_id == handoff["attempt_id"]
        assert candidate_permit.fingerprint == handoff["fingerprint"]
        assert browser == "chrome" and candidate_permit.reference_snapshot["post_id"] == "103"
        calls.append(url)
        navigation_observer.before()
        navigation_observer.after(SimpleNamespace(status=200), None)
        finalize(root, candidate_permit, candidate_permit.reference_snapshot, recent.clock.now())
        return {
            "status": "post_completed",
            "browser_closed": True,
            "shared_pending_retained": False,
            "job_counts": {"observed": 1, "completed": 1, "unresolved": 0},
        }

    report = save(recent, handoff, commit)
    assert report["status"] == "monitor_batch_completed", report
    assert report["tasks_started"] == report["tasks_completed"] == len(calls) == 1
    public = native.share_batch_report(report)
    assert public["saved_file_count"] == 1 and public["saved_files"][0]["detected_format"] == "PNG"
    assert native.recent_save_exclusions(*recent.roots) == {"103"}
    again = save(recent, handoff, never)
    assert again["reason"] == "selected_candidate_already_completed"
    assert again["tasks_started"] == 0 and again["already_completed_count"] == 1
    with QueueStore(recent.watch / "watch.sqlite") as queue:
        legacy = select_candidate_save(queue, DEFAULT_SCOPE, recent.watch / MANIFEST_NAME)
    assert legacy.reference_snapshot["post_id"] == "104"
    assert native.recent_save_exclusions(*recent.roots) == {"103", "104"}
    assert save(recent, recent.handoffs["104"], never)["tasks_started"] == 0
    files = list(recent.roots[2].glob("tasks/*/session-1/images/**/001.png"))
    assert len(files) == 1
    files[0].write_bytes(b"changed")
    damaged = save(recent, handoff, never)
    assert (
        damaged["status"] == "monitor_batch_manual_review"
        and damaged["already_completed_count"] == 0
    )


@pytest.mark.parametrize("field", ["scan_id", "attempt_id", "fingerprint"])
def test_changed_private_handoff_cannot_retarget_worker(recent, field):
    wrong = recent.handoffs["103"].copy()
    wrong[field] = "0" * 32 if field == "scan_id" else recent.handoffs["104"][field]
    out = save(recent, wrong, never)
    assert out["status"] == "monitor_batch_manual_review" and out["tasks_started"] == 0


def test_uncertain_save_blocks_reexecution_and_server_block_reaches_both_scopes(recent):
    def denied(*args, navigation_observer, **kwargs):
        navigation_observer.before()
        navigation_observer.after(SimpleNamespace(status=403), None)
        return {"status": "manual_review", "browser_closed": True, "shared_pending_retained": False}

    report = save(recent, recent.handoffs["103"], denied)
    assert report["tasks_started"] == 1 and report["tasks_needing_review"] == 1
    assert report["reason"] == "access_block_requires_review"
    with pytest.raises(QueueError):
        native.recent_save_exclusions(*recent.roots)
    assert save(recent, recent.handoffs["103"], never)["tasks_started"] == 0
    with QueueStore(recent.watch / "watch.sqlite", read_only=True) as queue:
        for scope in (MONITOR_SCOPE, DEFAULT_SCOPE):
            assert (
                _eligibility(queue, WatchStore(queue).get_state(scope), recent.clock.now())[0]
                == "blocked"
            )


def test_uncertain_completed_recent_files_can_reconcile_without_a_new_browser(recent):
    def interrupted(root, browser, url, *, candidate_permit, navigation_observer):
        state = PendingSave(native.shared_state_path())
        directory = root / "session-1" / "runs" / uuid.uuid4().hex
        (directory / "browser-profile").mkdir(parents=True)
        (root / "session-1" / "images").mkdir()
        pending = state.begin(directory)
        state.update_browser(pending, 202, 100.0)
        navigation_observer.before()
        navigation_observer.after(SimpleNamespace(status=200), None)
        finalize(root, candidate_permit, candidate_permit.reference_snapshot, recent.clock.now())
        state.finish(pending)
        raise InterruptedError("Browser closed after local completion")

    handoff = recent.handoffs["103"]
    first = save(recent, handoff, interrupted)
    assert first["tasks_needing_review"] == 1
    assert save(recent, handoff, never)["tasks_started"] == 0
    with QueueStore(recent.watch / "watch.sqlite") as queue:
        for scope, manifest in (
            (DEFAULT_SCOPE, MANIFEST_NAME),
            (MONITOR_SCOPE, MONITOR_MANIFEST_NAME),
        ):
            with pytest.raises(QueueError, match="unfinished recent"):
                select_candidate_save(queue, scope, recent.watch / manifest)
    reconciled = finish.run_monitor_batch_finish(
        *recent.roots, recent=True, is_running=lambda identity: False, close_owned=never
    )
    assert reconciled["status"] == "batch_finish_completed", reconciled
    assert reconciled["files_verified"] == reconciled["tasks_completed"] == 1
    assert save(recent, handoff, never)["reason"] == "selected_candidate_already_completed"


def test_existing_other_scope_ledger_owns_overlapping_physical_post(recent):
    with LedgerStore(
        recent.watch / LEDGER_NAME,
        watch_root=recent.watch,
        legacy_root=recent.watch.parent / "monitor-old",
        batch_root=recent.watch.parent / "batch",
    ) as monitor:
        task = plan(monitor, "104")
    assert native.recent_save_exclusions(*recent.roots) == {"104"}
    result = save(recent, recent.handoffs["104"], never)
    assert result["status"] == "monitor_batch_manual_review" and result["tasks_started"] == 0
    assert not (recent.watch / native.RECENT_LEDGER_NAME).exists()
    with LedgerStore(
        recent.watch / LEDGER_NAME,
        watch_root=recent.watch,
        legacy_root=recent.watch.parent / "monitor-old",
        batch_root=recent.watch.parent / "batch",
        read_only=True,
    ) as monitor:
        assert monitor.list_tasks() == [task]
