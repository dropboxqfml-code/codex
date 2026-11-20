"""Follow a stored ten-image detail through the work overview and the preview catalog."""

import json
from contextlib import nullcontext

from test_monitor_auto_session_integration import session_data as session_data
from test_monitor_ten_images_integration import freeze_detail, scan
from test_monitor_ten_images_integration import monitor as monitor
from test_post_worker import pilot as pilot

from image_monitor import monitor_operations, saved_catalog
from image_monitor.monitor_app import share_monitor_report
from image_monitor.monitor_controller import MonitorController


def test_ten_file_post_is_selectable_then_previews_all_verified_slots(monitor, monkeypatch):
    data = monitor.data
    roots = (data.watch, data.legacy, data.batch)
    monkeypatch.setattr(saved_catalog, "NativeSaveLock", nullcontext)
    monkeypatch.setattr(saved_catalog, "shared_state_path", lambda: data.marker)
    scan(monitor, 202, 200)
    freeze_detail(monitor)
    overview = monitor_operations.load_monitor_operations(*roots, now=monitor.clock.now())
    assert overview["save_ready"] == 1 and overview["rows"][0]["image_count"] == 10, overview
    assert MonitorController._operations_snapshot(overview)["operations_can_save"]

    saved = monitor.collect()
    assert saved["files_verified"] == 10, saved
    overview = monitor_operations.load_monitor_operations(*roots, now=monitor.clock.now())
    assert overview["save_ready"] == 0 and overview["save_completed"] == 1, overview
    assert overview["rows"][0]["image_count"] == 10
    loaded = saved_catalog.load_saved_catalog(data.watch, data.legacy, batch_root=data.batch)
    status, images = MonitorController._saved_snapshot(loaded)
    assert status["saved_status"] == "ready", status
    assert status["saved_groups_verified"] == 1 and status["saved_files_omitted"] == 0
    assert status["saved_files_verified"] == status["saved_preview_count"] == len(images) == 10
    files = status["saved_files"]
    assert [r["saved_filename"] for r in files] == [
        r["saved_filename"] for r in saved["saved_files"]
    ]
    assert len({r["group_id"] for r in files}) == 1
    assert {r["preview_id"] for r in files} == set(images)
    for row in files:
        [original] = data.batch.rglob(row["saved_filename"])
        assert images[row["preview_id"]][1] == original.read_bytes()
    public = json.dumps(share_monitor_report({"monitor_status": status}))
    assert not any(s in public for s in ("group_id", "preview_id", str(data.watch), "https://"))
