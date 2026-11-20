"""Check the ownership, cadence, and stop boundaries of a single monitor session."""

from datetime import UTC, datetime, timedelta

import pytest

from image_monitor.monitor_auto_session import auto_monitor_exit_code, run_auto_monitor
from image_monitor.monitor_settings import save_monitor_settings
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_store import MONITOR_SCOPE


class Clock:
    def __init__(self):
        self.start = self.time = datetime(2026, 4, 2, tzinfo=UTC)
        self.waits = []

    def now(self):
        return self.time

    def wait(self, seconds):
        self.waits.append(seconds)
        self.time += timedelta(seconds=seconds)

    def stamp(self, seconds):
        return (self.start + timedelta(seconds=seconds)).isoformat(timespec="microseconds")


def scan(status="complete", *, due=None, candidates=0, reason=None, closed=True):
    return {
        "status": status,
        "reason": reason,
        "next_eligible_at": due,
        "new_candidates": candidates,
        "browser_closed": closed,
    }


def collection(outcome="no_candidates", *, details=0, files=0, due=None, reason=None):
    return {
        "status": "monitor_collect_" + outcome,
        "reason": reason,
        "next_eligible_at": due,
        "browser_closed": True,
        "new_details_checked": details,
        "native_save_tasks_started": int(files > 0),
        "files_verified": files,
        "saved_files": [{"saved_filename": f"{i + 1:03}.png"} for i in range(files)],
    }


def session(tmp_path, clock, scans, turns, *, cycles=2, stop=None, progress=None):
    events = []
    scans, turns = iter(scans), iter(turns)

    def run(name, results):
        def runner(*roots, **options):
            assert options["clock"] is clock and options["should_stop"] is stop
            events.append((name, (clock.now() - clock.start).total_seconds()))
            result = next(results)
            return result() if callable(result) else result

        return runner

    report = run_auto_monitor(
        tmp_path / "watch",
        tmp_path / "legacy",
        tmp_path / "saves",
        clock=clock,
        max_cycles=cycles,
        should_stop=stop,
        on_progress=progress,
        scan_runner=run("scan", scans),
        collect_runner=run("collect", turns),
    )
    return report, events


def test_baseline_skips_older_work_then_verified_partial_can_collect(tmp_path):
    clock = Clock()
    (tmp_path / "watch").mkdir()
    save_monitor_settings(tmp_path / "watch", 120)
    snapshots = []

    def progress(state):
        if state["phase"] != "starting":
            with (
                pytest.raises(WatchRunBusy),
                watch_run_lock(
                    tmp_path / "watch" / "watch.sqlite", MONITOR_SCOPE, purpose="monitor"
                ),
            ):
                pass
        snapshots.append(state["phase"])
        state["cycles_completed"] = 99

    report, events = session(
        tmp_path,
        clock,
        [scan("baseline"), scan("partial", candidates=3)],
        [collection("saved", details=1, files=2)],
        progress=progress,
    )
    assert events == [("scan", 0), ("scan", 120), ("collect", 120)]
    assert snapshots == ["starting", "scanning", "waiting", "scanning", "collecting"]
    assert report["cycles_completed"] == report["list_checks"] == 2
    assert (
        report["partial_list_checks"] == report["new_details_checked"] == report["posts_saved"] == 1
    )
    assert report["new_candidates"] == 3 and report["files_verified"] == 2
    assert report["last_saved_files"][-1]["saved_filename"] == "002.png"
    assert report["status"] == "auto_monitor_completed" and auto_monitor_exit_code(report) == 0
    assert clock.waits == [120]
    with watch_run_lock(tmp_path / "watch" / "watch.sqlite", MONITOR_SCOPE, purpose="monitor"):
        pass


def test_cooldown_before_list_and_collection_retries_the_same_phase(tmp_path):
    clock = Clock()
    report, events = session(
        tmp_path,
        clock,
        [scan("waiting", due=clock.stamp(20), closed=None), scan(), scan()],
        [collection("waiting", due=clock.stamp(62)), collection(), collection()],
    )
    assert events == [
        ("scan", 0),
        ("scan", 20),
        ("collect", 20),
        ("collect", 62),
        ("scan", 80),
        ("collect", 80),
    ]
    assert report["cycles_completed"] == report["list_checks"] == 2
    assert report["new_details_checked"] == report["native_save_tasks_started"] == 0


def test_wait_after_new_detail_does_not_charge_another_detail_in_same_turn(tmp_path):
    clock = Clock()
    report, events = session(
        tmp_path,
        clock,
        [scan(), scan()],
        [
            collection("waiting", details=1, due=clock.stamp(75), reason="service_retry_after"),
            collection("saved", details=0, files=1),
        ],
        cycles=None,
        stop=lambda: clock.now() >= clock.start + timedelta(seconds=76),
    )
    assert events == [("scan", 0), ("collect", 0), ("scan", 75), ("collect", 75)]
    assert report["status"] == "auto_monitor_stopped" and report["cycles_completed"] == 2
    assert report["new_details_checked"] == report["files_verified"] == 1


@pytest.mark.parametrize("outcome", ["review", "blocked", "busy", "complete"])
def test_uncertain_or_failed_list_does_not_start_collection(tmp_path, outcome):
    closed = False if outcome in {"complete", "review"} else None
    report, events = session(tmp_path, Clock(), [scan(outcome, closed=closed)], [])
    assert events == [("scan", 0)]
    assert report["status"] == "auto_monitor_" + ("review" if outcome == "complete" else outcome)
    assert report["cycles_completed"] == report["list_checks"] == 0


def test_stop_after_verified_list_before_collection_keeps_both_counts(tmp_path):
    stop = False

    def scanned():
        nonlocal stop
        stop = True
        return scan(candidates=2)

    report, events = session(tmp_path, Clock(), [scanned], [], cycles=None, stop=lambda: stop)
    assert events == [("scan", 0)]
    assert report["status"] == "auto_monitor_stopped" and report["list_checks"] == 1
    assert report["cycles_completed"] == 0 and report["new_candidates"] == 2


def test_stop_during_writer_records_finished_save_before_releasing_lock(tmp_path):
    stop = False

    def saved():
        nonlocal stop
        stop = True
        return collection("saved", details=1, files=1)

    report, events = session(tmp_path, Clock(), [scan()], [saved], cycles=None, stop=lambda: stop)
    assert events == [("scan", 0), ("collect", 0)]
    assert report["status"] == "auto_monitor_stopped"
    assert report["files_verified"] == report["cycles_completed"] == 1
    assert report["browser_closed"] is True


def test_bounded_long_service_wait_and_stale_deadline_are_terminal(tmp_path):
    clock = Clock()
    report, events = session(
        tmp_path, clock, [scan()], [collection("waiting", due=clock.stamp(600))]
    )
    assert report["status"] == "auto_monitor_waiting" and report["next_eligible_at"] == clock.stamp(
        600
    )
    assert events == [("scan", 0), ("collect", 0)] and not clock.waits
    report, events = session(tmp_path, clock, [scan("waiting", due=clock.stamp(0))], [])
    assert report["status"] == "auto_monitor_review" and report["reason"] == "invalid_wait_deadline"
    assert events == [("scan", 0)] and not clock.waits


def test_bounded_trial_returns_on_renewed_wait_instead_of_looping(tmp_path):
    clock = Clock()
    report, events = session(
        tmp_path,
        clock,
        [
            scan("waiting", due=clock.stamp(60)),
            scan("waiting", due=clock.stamp(120)),
        ],
        [],
    )
    assert report["status"] == "auto_monitor_waiting" and report["next_eligible_at"] == clock.stamp(
        120
    )
    assert events == [("scan", 0), ("scan", 60)] and clock.waits == [60]


def test_continuous_wait_is_interruptible_without_reopening_any_browser(tmp_path):
    clock = Clock()
    report, events = session(
        tmp_path,
        clock,
        [scan("waiting", due=clock.stamp(7200), closed=None)],
        [],
        cycles=None,
        stop=lambda: len(clock.waits) >= 2,
    )
    assert report["status"] == "auto_monitor_stopped" and report["next_eligible_at"] == clock.stamp(
        7200
    )
    assert clock.waits == [0.5, 0.5] and events == [("scan", 0)]


def test_uncertain_writer_result_never_unlocks_a_followup_scan(tmp_path):
    turn = collection("waiting", due=Clock().stamp(60))
    turn["native_save_tasks_started"] = None
    report, events = session(tmp_path, Clock(), [scan()], [turn])
    assert events == [("scan", 0), ("collect", 0)]
    assert report["status"] == "auto_monitor_review" and auto_monitor_exit_code(report) == 2
    assert report["native_save_tasks_started"] is None and report["cycles_completed"] == 0
