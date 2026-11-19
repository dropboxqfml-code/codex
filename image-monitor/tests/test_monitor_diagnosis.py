"""Recover the last incomplete list profile from an existing watch DB, entirely offline."""

import json

import pytest
from test_candidate_finish_runtime import database_dump
from test_monitor_controller import AutoClock
from test_monitor_details_controller import record_detail
from test_monitor_gap_continuation import run_scan, seed_baseline
from test_watch_runtime import link, observed, snapshot

from image_monitor import monitor_app, monitor_diagnosis, watch_runtime
from image_monitor.monitor_controller import MONITOR_SCOPE, MonitorController
from image_monitor.monitor_diagnosis import PROFILE_GAP, read_latest_list_diagnosis
from image_monitor.queue import QueueStore
from image_monitor.watch_runtime import DEFAULT_SCOPE
from image_monitor.watch_store import WatchStore

INCOMPLETE_PAGE = observed(
    lambda stamp: snapshot(
        [155],
        stamp,
        status="observed",
        layout_status="unverified",
        counts={"list_containers": 2, "matched_list_containers": 1},
    )
)
COMPLETE = observed(
    lambda stamp: snapshot([103, 102, 101, 100, 99], stamp, links=[link(2)]),
    lambda stamp: snapshot([98, 97], stamp, page=2),
)


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    clock = AutoClock()
    seed_baseline(tmp_path, clock)
    assert run_scan(tmp_path, clock, COMPLETE)["new_candidates"] == 3
    for _ in range(2):
        clock.advance(60)
        record_detail(tmp_path, clock)
    clock.advance(60)
    partial = observed(
        lambda stamp: snapshot(range(150, 130, -1), stamp, links=[link(2)]),
        lambda stamp: snapshot(range(130, 110, -1), stamp, page=2, links=[link(3)]),
    )
    assert run_scan(tmp_path, clock, partial)["new_candidates"] == 40
    clock.advance(60)
    report = run_scan(tmp_path, clock, INCOMPLETE_PAGE)
    assert report["status"] == "watch_test_partial" and report["reason"] == PROFILE_GAP
    db = tmp_path / "watch.sqlite"
    with QueueStore(db) as queue:
        scan_id = WatchStore(queue).get_state(MONITOR_SCOPE)["latest_scan"]["scan_id"]
        # Recreate the alpha.2 format, which did not record a specific planner failure code.
        queue.connection.execute(
            "UPDATE watch_scans SET result_json=json_remove(result_json,'$.planner_issue') "
            "WHERE scan_id=?",
            (scan_id,),
        )
    return db, clock


def test_idle_default_dashboard_and_final_report_recover_legacy_evidence_without_scanning(
    source, tmp_path, monkeypatch
):
    db, clock = source
    monkeypatch.setattr(monitor_app, "require_windows", lambda: None)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Offline startup unexpectedly requested navigation or a native action")

    def factory(root, **kwargs):
        return MonitorController(
            root,
            clock=clock,
            run_cycle=forbidden,
            run_details=forbidden,
            save_runner=forbidden,
            finish_runner=forbidden,
            **kwargs,
        )

    class LocalScreen:
        url = "http://127.0.0.1/offline-example/"

        def __init__(self, controller):
            self.controller = controller

        def serve(self):
            assert self.controller.wait_stopped(10)
            value = self.controller.status()
            assert value["task_kind"] == "overview"
            assert value["list_diagnosis"]["http_status"] == 200
            value["list_diagnosis"]["pages"].clear()

        def server_close(self):
            pass

    before = database_dump(db)
    report = monitor_app.run_monitor_app(
        tmp_path,
        save_root=tmp_path.parent / (tmp_path.name + "-legacy"),
        batch_root=tmp_path.parent / (tmp_path.name + "-batch"),
        controller_factory=factory,
        server_factory=LocalScreen,
        opener=lambda _: True,
    )
    assert report["status"] == "monitor_closed", report
    status = monitor_app.share_monitor_report(report)["monitor_status"]
    assert status["candidate_count"] == 43 and status["detail_pending_count"] == 41
    assert status["detail_completed_count"] == 2
    assert status["completed_cycles"] == status["auto_details_checked"] == 0
    diagnosis = status["list_diagnosis"]
    assert diagnosis["reason"] == PROFILE_GAP and diagnosis["planner_issue"] is None
    assert [(p["status"], p["layout_status"], p["ordinary_rows"]) for p in diagnosis["pages"]] == [
        ("observed", "unverified", 1)
    ]
    output = json.dumps(diagnosis)
    for secret in ("Invented", "http://", "https://", "comic_new6", "155", "private_observation"):
        assert secret not in output
    assert database_dump(db) == before


def test_later_complete_scan_keeps_previous_diagnosis_across_restart_and_scope(source):
    db, clock = source
    controller = MonitorController(db.parent, clock=clock)
    previous = controller.status()["list_diagnosis"]
    clock.advance(60)
    success = run_scan(db.parent, clock, COMPLETE)
    assert success["status"] == "watch_test_completed"
    controller._after_cycle(success)
    state = controller.status()
    assert state["gap_reason"] is None and state["list_diagnosis"] == previous
    assert MonitorController(db.parent, clock=clock).status()["list_diagnosis"] == previous
    with QueueStore(db, read_only=True) as queue:
        assert read_latest_list_diagnosis(queue, DEFAULT_SCOPE) is None
        assert read_latest_list_diagnosis(queue, MONITOR_SCOPE, max_generation=1) is None


def test_new_failure_replaces_old_diagnosis_and_preserves_review_stop(source):
    db, clock = source
    controller = MonitorController(db.parent, clock=clock)
    assert controller.status()["list_diagnosis"]["pages"][0]["ordinary_rows"] == 1
    clock.advance(60)
    missing = observed(
        lambda stamp: snapshot([], stamp, status="missing_list", layout_status="unverified")
    )
    report = run_scan(db.parent, clock, missing)
    assert not controller._after_cycle(report)
    public = monitor_app.share_monitor_report({"monitor_status": controller.status()})[
        "monitor_status"
    ]
    assert public["phase"] == "needs_review" and public["gap_reason"] == PROFILE_GAP
    assert public["list_diagnosis"]["pages"][0]["status"] == "missing_list"
    assert public["list_diagnosis"]["pages"][0]["ordinary_rows"] == 0
    assert public["auto_details_checked"] == 0 and public["detail_pending_count"] == 41


@pytest.mark.parametrize("damage", ["too_big", "malformed_json", "reason_mismatch", "wrong_scope"])
def test_unusable_historical_diagnostics_do_not_block_valid_latest_scan(
    source, monkeypatch, damage
):
    db, clock = source
    with QueueStore(db, read_only=True) as queue:
        target = WatchStore(queue).get_state(MONITOR_SCOPE)["latest_scan"]["scan_id"]
    clock.advance(60)
    assert run_scan(db.parent, clock, COMPLETE)["status"] == "watch_test_completed"
    if damage == "too_big":
        monkeypatch.setattr(monitor_diagnosis, "MAX_DIAGNOSIS_BYTES", 8)
    else:
        with QueueStore(db) as queue:
            if damage == "malformed_json":
                queue.connection.execute(
                    "UPDATE watch_scans SET result_json='{' WHERE scan_id=?", (target,)
                )
            elif damage == "reason_mismatch":
                queue.connection.execute(
                    "UPDATE watch_scans SET result_json='{}' WHERE scan_id=?", (target,)
                )
            else:
                queue.connection.execute(
                    "UPDATE watch_gaps SET watch_name=? WHERE scan_id=?",
                    (DEFAULT_SCOPE.watch_name, target),
                )
    status = MonitorController(db.parent, clock=clock).status()
    assert status["phase"] == "stopped" and status["candidate_count"] == 43
    assert status["list_diagnosis"] is None
