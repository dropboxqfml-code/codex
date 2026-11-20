"""Keep completion setup failures useful in the TXT without exposing browser data."""

import json
from pathlib import Path

import pytest
from test_monitor_auto_session import Clock, collection, scan, session
from test_monitor_batch_runtime import data as data
from test_monitor_batch_runtime import run
from test_monitor_collect import targets
from test_post_worker import automatic_candidate
from test_post_worker import pilot as pilot

from image_monitor import post_worker
from image_monitor.browser_completion import BrowserCompletionError
from image_monitor.monitor_batch_runtime import share_batch_report

FOCUS_DIAGNOSIS = {
    "setup_focus_stage": "after_target_creation",
    "setup_focus_recovery": "waiting_for_user",
    "setup_focus_loss": "repeated",
}


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


def test_focus_setup_failure_returns_safe_codes_in_all_user_reports(
    pilot, data, tmp_path, monkeypatch
):
    def fail_setup(*_args, **_kwargs):
        error = BrowserCompletionError("The source document did not have focus")
        vars(error).update(FOCUS_DIAGNOSIS, private_title="share-nothing.invalid")
        raise error

    monkeypatch.setattr(post_worker, "BrowserCompletion", fail_setup)
    worker = post_worker.run_post_save(pilot.root, **automatic_candidate(pilot))
    private = json.loads(Path(worker["report_path"]).read_bytes())
    target, _ = targets(data)
    batch = run(data, lambda *_a, **_kw: worker, max_tasks=1, monitor_handoff=target)
    shared = share_batch_report(batch)
    report, events = session(tmp_path, Clock(), [scan()], [collection("review") | {"save": shared}])
    assert events == [("scan", 0), ("collect", 0)]
    assert report["status"] == "auto_monitor_review" and pilot.native_calls == 0
    for result in (
        private,
        post_worker.share_worker_report(worker),
        batch,
        shared,
        report["last_collection"],
    ):
        assert FOCUS_DIAGNOSIS.items() <= result.items()
        assert result["completion_setup_reason"] == "source_document_unfocused"
        assert "share-nothing.invalid" not in json.dumps(result)


@pytest.mark.parametrize(
    ("stage", "kind", "focus"),
    [
        (
            "completion_setup",
            "BrowserCompletionError",
            {
                "setup_focus_stage": ["private"],
                "setup_focus_loss": "https://private.invalid",
                "setup_focus_recovery": "https://private.invalid",
            },
        ),
        ("native_saving", "BrowserCompletionError", FOCUS_DIAGNOSIS),
        ("completion_setup", "OtherError", FOCUS_DIAGNOSIS),
        ("completion_setup", "BrowserCompletionError", {}),
    ],
)
def test_shared_setup_fields_accept_only_known_stage_and_recovery(tmp_path, stage, kind, focus):
    worker = {"last_stage": stage, "error_type": kind, **focus}
    batch = {"worker_last_stage": stage, "error_type": kind, **focus}
    report, _ = session(tmp_path, Clock(), [scan()], [collection("review") | {"save": batch}])
    for result in (
        post_worker.share_worker_report(worker),
        share_batch_report(batch),
        report["last_collection"],
    ):
        assert FOCUS_DIAGNOSIS.keys().isdisjoint(result)
