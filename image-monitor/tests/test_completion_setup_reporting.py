"""Keep completion setup failures useful in the TXT without exposing browser data."""

import json
from pathlib import Path

import pytest
from test_monitor_batch_runtime import data as data
from test_monitor_batch_runtime import run
from test_monitor_collect import targets
from test_post_worker import automatic_candidate
from test_post_worker import pilot as pilot

from image_monitor import post_worker
from image_monitor.browser_completion import BrowserCompletionError
from image_monitor.monitor_batch_runtime import share_batch_report


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "The bound source page lost its identity or foreground",
            "source_identity_or_foreground_changed",
        ),
        ("The Chrome downloads model did not become available", "downloads_model_unavailable"),
        ("unexpected exception with https://private.invalid/path", None),
    ],
)
def test_setup_diagnosis_survives_before_any_image_claim(pilot, monkeypatch, message, expected):
    def unavailable(*args, **kwargs):
        raise BrowserCompletionError(message)

    monkeypatch.setattr(post_worker, "BrowserCompletion", unavailable)
    report = post_worker.run_post_save(pilot.root, **automatic_candidate(pilot))
    private = json.loads(Path(report["report_path"]).read_text(encoding="utf-8"))
    assert private["last_stage"] == "completion_setup" and private["reason"] == message
    assert private["browser_closed"] and not private["shared_pending_retained"]
    assert private["job_counts"] == {"observed": 1, "completed": 0, "unresolved": 1}
    assert "active_attempt" not in private and pilot.native_calls == 0
    shared = post_worker.share_worker_report(report)
    assert (
        shared.get("completion_setup_reason") == private.get("completion_setup_reason") == expected
    )
    if expected is None:
        assert message not in json.dumps(shared)


@pytest.mark.parametrize(
    "reported", ["downloads_model_unavailable", "https://private.invalid", ["untrusted"]]
)
def test_batch_forwards_only_recognized_setup_diagnoses(data, reported):
    def failed(*args, **kwargs):
        return {
            "status": "manual_review",
            "error_type": "BrowserCompletionError",
            "last_stage": "completion_setup",
            "reason": "https://private.invalid",
            "completion_setup_reason": reported,
            "job_counts": {"observed": 1, "completed": 0, "unresolved": 1},
            "browser_closed": True,
            "shared_pending_retained": False,
        }

    target, _ = targets(data)
    raw = run(data, failed, max_tasks=1, monitor_handoff=target)
    shared = share_batch_report(raw)
    assert (
        shared["error_type"] == "BrowserCompletionError" and shared["worker_images_completed"] == 0
    )
    assert shared.get("completion_setup_reason") == (
        reported if reported == "downloads_model_unavailable" else None
    )
    assert "private.invalid" not in json.dumps(shared)
    assert "completion_setup_reason" not in share_batch_report(
        raw | {"worker_last_stage": "native_saving"}
    )
