"""Exercise the optional native handoff after a bounded recent-post search."""

import json
from datetime import timedelta

import pytest
from test_watch_runtime import FakeClock

from image_monitor import watch_images


def install_search(monkeypatch, search_status="image_candidate_ready"):
    handoff = {"scan_id": "private-scan", "attempt_id": "private-attempt", "fingerprint": "private"}
    search = {"status": search_status, "eligible_body_images": 1}
    monkeypatch.setattr(
        watch_images, "run_watch_image_search", lambda *args, **kwargs: (search, handoff)
    )
    return handoff


@pytest.mark.parametrize(("seconds", "started", "attempts"), [(60, 0, 2), (61, 0, 1), (60, 1, 1)])
def test_wait_only_before_native_start_and_revalidate_the_same_handoff(
    tmp_path, monkeypatch, seconds, started, attempts
):
    clock = FakeClock()
    handoff = install_search(monkeypatch)
    calls = []

    def save(watch, legacy, output, selection, **kwargs):
        calls.append(selection)
        if len(calls) == 1:
            return {
                "mode": "recent_candidate_native_save",
                "status": "monitor_batch_waiting",
                "tasks_started": started,
                "reason": "persisted_cooldown",
                "next_eligible_at_local": (clock.now() + timedelta(seconds=seconds)).isoformat(),
            }
        return {
            "mode": "recent_candidate_native_save",
            "status": "monitor_batch_completed",
            "tasks_started": 1,
            "tasks_completed": 1,
            "saved_files": [{"saved_filename": "001.jpg", "local_path": "private-file"}],
            "browser_closed": True,
            "shared_pending_retained": False,
        }

    monkeypatch.setattr(watch_images, "run_recent_save", save)
    report = watch_images.run_watch_images(
        tmp_path / "watch", tmp_path / "legacy", tmp_path / "images", clock=clock
    )
    assert calls == [handoff] * attempts
    assert clock.waits == ([60] if attempts == 2 else [])
    assert report["status"] == ("watch_images_saved" if attempts == 2 else "watch_images_waiting")
    assert watch_images.watch_images_exit_code(report) == 0
    assert "private" not in json.dumps(report)


def test_search_without_an_eligible_body_never_calls_native_saving(tmp_path, monkeypatch):
    install_search(monkeypatch, search_status="image_search_limit")
    monkeypatch.setattr(watch_images, "run_recent_save", lambda *a, **kw: pytest.fail())
    report = watch_images.run_watch_images(tmp_path / "watch", tmp_path / "old", tmp_path / "new")
    assert report["save"] is None and report["status"] == "image_search_limit"
    assert watch_images.watch_images_exit_code(report) == 0
