"""Show the current Chrome worker's final error when it failed before recording a list scan."""

from functools import partial
from pathlib import Path

from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_finish import CandidateFinishError, _read_json, _same_json, _uuid
from image_monitor.monitor_list_review import public_list_review
from image_monitor.watch_runtime import run_watch_trial

_FAILED_BEFORE_COMMIT = {
    "schema_version": 1,
    "mode": "bounded_live_list_discovery",
    "status": "watch_test_failed",
    "browser": "chrome",
    "browser_closed": True,
    "discovery_only": True,
    "images_saved": False,
    "image_jobs_created": 0,
    "cycles_requested": 1,
    "cycles_completed": 0,
    "cycles": [],
    "new_candidates": 0,
}


def uncommitted_list_review(database, before, after, raw, *, run_cycle):
    """Use only the direct return of the worker that created a new, exclusive run directory."""
    if type(run_cycle) is partial:
        run_cycle = run_cycle.func
    if run_cycle is not run_watch_trial or not isinstance(raw, dict):
        return None
    try:
        if (
            not isinstance(before, dict)
            or type(before.get("generation")) is not int
            or not _same_json(before, after)
            or not _same_json({k: raw.get(k) for k in _FAILED_BEFORE_COMMIT}, _FAILED_BEFORE_COMMIT)
            or "closed_monitor_scan" in raw
        ):
            return None
        database = _plain_path(Path(database))
        if not database.is_file() or not isinstance(raw.get("report_path"), str):
            return None
        run_id = Path(raw["report_path"]).parent.name
        report_path = database.parent / "runs" / run_id / "report.json"
        if (
            not _uuid(run_id)
            or str(report_path) != raw["report_path"]
            or not _same_json(raw, _read_json(report_path))
        ):
            return None
        return public_list_review(
            {
                "stage": "watch_result",
                "evidence": "worker_report",
                "watch_status": raw["status"],
                "watch_stage": raw.get("last_stage"),
                "error_type": raw.get("error_type"),
            }
        )
    except (OSError, ValueError, TypeError, RecursionError, OverflowError, CandidateFinishError):
        return None
