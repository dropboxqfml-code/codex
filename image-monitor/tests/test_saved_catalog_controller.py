"""Keep local completed-file verification off the control and image threads."""

import copy
import json
import threading
from types import SimpleNamespace

import pytest
from test_monitor_controller import Clock, persist

from image_monitor.monitor_controller import MONITOR_SCOPE, MonitorController
from image_monitor.queue import QueueError, QueueStore
from image_monitor.watch_store import WatchStore

FIRST = "a" * 32
SECOND = "b" * 32


def snapshot(*, image_id=FIRST, data=b"verified fixture bytes", status="ready", reason=None):
    rows = (
        [
            {
                "saved_filename": "001.jpg",
                "detected_format": "JPEG",
                "file_size": len(data),
                "width": 732,
                "height": 1067,
                "frames": 1,
                "preview_id": image_id,
                "preview_available": True,
            }
        ]
        if status == "ready"
        else []
    )
    return SimpleNamespace(
        summary={
            "status": status,
            "reason": reason,
            "error_type": None,
            "files_verified": len(rows),
            "preview_count": len(rows),
            "files": rows,
        },
        images={image_id: ("image/jpeg", data)} if rows else {},
    )


def grouped_snapshot(count):
    result = snapshot()
    template = result.summary["files"][0]
    rows, images = [], {}
    for i in range(count):
        image_id, group_id = f"{i + 1:032x}", f"{i + 100:032x}"
        rows.append(dict(template, preview_id=image_id, group_id=group_id))
        images[image_id] = ("image/jpeg", b"verified fixture bytes")
    result.summary.update(
        files=rows,
        files_verified=count,
        preview_count=count,
        groups_verified=count,
        files_omitted=0,
    )
    result.images = images
    return result


@pytest.fixture
def controllers():
    values = []
    yield values
    for value in values:
        value.stop()
        assert value.wait_stopped(3), "A local saved-file worker leaked"


def create(controllers, root, loader, **options):
    value = MonitorController(
        root,
        save_root=options.pop("save_root", root.parent / "saved-output"),
        catalog_loader=loader,
        run_cycle=options.pop("run_cycle", lambda *_args, **_kwargs: pytest.fail("List started")),
        run_details=lambda *_args, **_kwargs: pytest.fail("Detail inspection started"),
        **options,
    )
    controllers.append(value)
    return value


def test_disabled_preview_does_not_start_a_worker_or_create_save_data(tmp_path, controllers):
    calls = []
    value = create(
        controllers,
        tmp_path / "watch",
        lambda *_args, **_kwargs: calls.append(True),
        save_root=None,
    )
    initial = value.status()
    assert initial["saved_status"] == "disabled"
    assert value.refresh_saved() == initial
    assert calls == [] and not value.is_alive()
    assert not (tmp_path / "watch" / "watch.sqlite").exists()
    assert list(tmp_path.iterdir()) == [tmp_path / "watch"]
    assert value.saved_image(FIRST) is None


def test_local_loader_owns_one_background_thread_and_preserves_source_state(tmp_path, controllers):
    root = tmp_path / "watch"
    clock = Clock()
    persist(root, clock, added=("101", "102"))
    with QueueStore(root / "watch.sqlite", read_only=True) as queue:
        before = WatchStore(queue).get_state(MONITOR_SCOPE)
        candidates = WatchStore(queue).list_candidates(MONITOR_SCOPE)
    entered, release = threading.Event(), threading.Event()
    calls = []
    loaded = snapshot()
    loaded.summary["private_path"] = "Invented private filename"
    loaded.summary["files"][0]["private_url"] = "https://private.example"

    def load(watch_root, save_root, *, should_stop):
        calls.append((watch_root, save_root, threading.get_ident(), should_stop))
        entered.set()
        assert release.wait(3)
        return loaded

    value = create(controllers, root, load, clock=clock)
    initial = value.status()
    value.refresh_saved()
    try:
        assert entered.wait(3)
        active = value.status()
        assert active["phase"] == "verifying_saved" and active["task_kind"] == "saved"
        assert active["saved_status"] == "checking"
        assert active["browser_closed"] is True
        assert value.saved_image(FIRST) is None
        assert not (tmp_path / "saved-output").exists()
    finally:
        release.set()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["phase"] == "stopped" and status["saved_status"] == "ready"
    assert status["saved_files_verified"] == status["saved_preview_count"] == 1
    assert value.saved_image(FIRST) == ("image/jpeg", b"verified fixture bytes")
    assert calls[0][:2] == (root, tmp_path / "saved-output")
    assert calls[0][2] != threading.get_ident()
    assert calls[0][3].__self__ is value
    for key in ("completed_cycles", "new_candidates", "last_scan_at", "baseline_initialized"):
        assert status[key] == initial[key]
    assert status["browser_closed"] is True
    assert "private" not in json.dumps(status)
    with QueueStore(root / "watch.sqlite", read_only=True) as queue:
        assert WatchStore(queue).get_state(MONITOR_SCOPE) == before
        assert WatchStore(queue).list_candidates(MONITOR_SCOPE) == candidates
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0


def test_refresh_revokes_previous_ids_before_validation_and_publishes_once(tmp_path, controllers):
    first, second = snapshot(), snapshot(image_id=SECOND, data=b"another verified buffer")
    entered, release = threading.Event(), threading.Event()
    calls = []

    def load(*_args, **_kwargs):
        calls.append(1)
        if len(calls) == 1:
            return first
        entered.set()
        assert release.wait(3)
        return second

    value = create(controllers, tmp_path / "watch", load)
    value.refresh_saved()
    assert value.wait_stopped(3)
    assert value.saved_image(FIRST) is not None
    value.refresh_saved()
    try:
        assert entered.wait(3)
        assert value.saved_image(FIRST) is value.saved_image(SECOND) is None
        assert value.status()["saved_files"] == []
    finally:
        release.set()
    assert value.wait_stopped(3)
    assert value.saved_image(FIRST) is None
    assert value.saved_image(SECOND) == ("image/jpeg", b"another verified buffer")


@pytest.mark.parametrize("action", ["stop", "pause"])
def test_stop_or_pause_during_local_validation_cannot_publish_late_success(
    tmp_path, controllers, action
):
    entered, release = threading.Event(), threading.Event()

    def load(*_args, should_stop):
        entered.set()
        assert release.wait(3)
        assert should_stop()
        return snapshot()

    value = create(controllers, tmp_path / "watch", load)
    value.refresh_saved()
    try:
        assert entered.wait(3)
        getattr(value, action)()
        before = value.status()
        # Starting an already active local task cannot resume discovery or
        # discard its stop/pause request.
        value.start()
        assert value.status()["phase"] == before["phase"]
        assert value._requested_stop()
    finally:
        release.set()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["phase"] == "stopped"
    assert status["saved_status"] == "cancelled" and status["saved_reason"] == "requested_stop"
    assert status["saved_files_verified"] == 0 and status["saved_files"] == []
    assert value.saved_image(FIRST) is None


@pytest.mark.parametrize(
    "status,reason",
    [
        ("empty", "existing_saved_candidate_required"),
        ("busy", "native_save_in_progress"),
        ("busy", "pending_save_requires_review"),
        ("needs_review", "saved_catalog_requires_review"),
        ("cancelled", "requested_stop"),
    ],
)
def test_catalog_outcomes_do_not_poison_discovery_or_retain_images(
    tmp_path, controllers, status, reason
):
    value = create(
        controllers,
        tmp_path / "watch",
        lambda *_args, **_kwargs: snapshot(status=status, reason=reason),
    )
    value.refresh_saved()
    assert value.wait_stopped(3)
    result = value.status()
    assert result["phase"] == "stopped" and result["saved_status"] == status
    assert result["saved_reason"] == reason
    assert result["reason"] is result["error_type"] is None
    assert result["browser_closed"] is True
    assert value.saved_image(FIRST) is None


def test_catalog_exception_is_safe_and_does_not_prevent_a_later_discovery_start(
    tmp_path, controllers
):
    def broken(*_args, **_kwargs):
        raise OSError("Invented private path and https://private.example")

    cycles = []

    def cycle(*_args, **_kwargs):
        cycles.append(1)
        value.stop()
        return {
            "status": "watch_test_cancelled",
            "cycles_completed": 0,
            "new_candidates": 0,
            "browser_closed": True,
        }

    value = create(controllers, tmp_path / "watch", broken, run_cycle=cycle)
    value.refresh_saved()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["saved_status"] == "needs_review" and status["saved_error_type"] == "OSError"
    assert status["saved_reason"] == "saved_catalog_requires_review"
    assert status["phase"] == "stopped"
    assert "private" not in json.dumps(status)
    value.start()
    assert value.wait_stopped(3)
    assert cycles == [1]
    assert value.status()["phase"] == "stopped"


def test_snapshot_rows_and_cache_are_not_aliased_to_the_loader_or_callers(tmp_path, controllers):
    loaded = snapshot()
    value = create(controllers, tmp_path / "watch", lambda *_args, **_kwargs: loaded)
    value.refresh_saved()
    assert value.wait_stopped(3)
    loaded.summary["files"][0]["width"] = 1
    loaded.images[FIRST] = ("text/html", b"malicious replacement")
    status = value.status()
    status["saved_files"][0]["height"] = 1
    assert value.status()["saved_files"][0]["width"] == 732
    assert value.status()["saved_files"][0]["height"] == 1067
    assert value.saved_image(FIRST) == ("image/jpeg", b"verified fixture bytes")


def test_cached_image_lookup_never_reads_sql_or_local_files(tmp_path, controllers, monkeypatch):
    value = create(controllers, tmp_path / "watch", lambda *_args, **_kwargs: snapshot())
    value.refresh_saved()
    assert value.wait_stopped(3)

    def forbidden(*_args, **_kwargs):
        pytest.fail("An image lookup performed I/O")

    monkeypatch.setattr("image_monitor.monitor_controller.QueueStore", forbidden)
    monkeypatch.setattr("pathlib.Path.open", forbidden)
    assert value.saved_image(FIRST) == ("image/jpeg", b"verified fixture bytes")
    for invalid in (None, [], "../001.jpg", "a" * 31, "a" * 33, "A" * 32, "unknown"):
        assert value.saved_image(invalid) is None
    assert value.status()["saved_status"] == "ready"


def test_metadata_only_verified_file_can_be_shown_without_an_inline_preview(tmp_path, controllers):
    loaded = snapshot()
    loaded.summary.update(preview_count=0, reason="preview_limit")
    loaded.summary["files"][0].update(
        detected_format="TIFF", saved_filename="001.tiff", preview_id=None, preview_available=False
    )
    loaded.images = {}
    value = create(controllers, tmp_path / "watch", lambda *_args, **_kwargs: loaded)
    value.refresh_saved()
    assert value.wait_stopped(3)
    assert value.status()["saved_status"] == "ready"
    assert value.status()["saved_files_verified"] == 1
    assert value.status()["saved_preview_count"] == 0
    assert value.saved_image(FIRST) is None


@pytest.mark.parametrize("conflict", ["active", "review", "unknown_browser"])
def test_refresh_requires_the_monitor_to_be_fully_stopped(tmp_path, controllers, conflict):
    entered, release = threading.Event(), threading.Event()

    def load(*_args, **_kwargs):
        entered.set()
        assert release.wait(3)
        return snapshot()

    value = create(controllers, tmp_path / "watch", load)
    try:
        if conflict == "active":
            value.refresh_saved()
            assert entered.wait(3)
        elif conflict == "review":
            value._set(phase="needs_review")
        else:
            value._set(browser_closed=None)
        with pytest.raises(QueueError):
            value.refresh_saved()
    finally:
        release.set()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.summary.update(status="private status"),
        lambda s: s.summary.update(reason="Invented private path"),
        lambda s: s.summary.update(files_verified=True),
        lambda s: s.summary.update(preview_count=0),
        lambda s: s.summary["files"].extend(copy.deepcopy(s.summary["files"]) * 2),
        lambda s: s.summary["files"][0].update(saved_filename="../private.jpg"),
        lambda s: s.summary["files"][0].update(saved_filename="001.png"),
        lambda s: s.summary["files"][0].update(detected_format="TIFF", saved_filename="001.tiff"),
        lambda s: s.summary["files"][0].update(width=True),
        lambda s: s.summary["files"][0].update(preview_id="private-image-id"),
        lambda s: s.images.update({FIRST: ("text/html", b"verified fixture bytes")}),
        lambda s: s.images.update({FIRST: ("image/jpeg", bytearray(b"verified fixture bytes"))}),
        lambda s: s.images.update({SECOND: ("image/jpeg", b"unreferenced")}),
    ],
)
def test_malformed_catalog_never_publishes_partial_or_unsafe_preview(tmp_path, controllers, mutate):
    loaded = snapshot()
    mutate(loaded)
    value = create(controllers, tmp_path / "watch", lambda *_args, **_kwargs: loaded)
    value.refresh_saved()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["phase"] == "stopped" and status["saved_status"] == "needs_review"
    assert status["saved_reason"] == "saved_catalog_requires_review"
    assert status["saved_files_verified"] == status["saved_preview_count"] == 0
    assert status["saved_files"] == [] and value.saved_image(FIRST) is None
    assert "private" not in json.dumps(status)


def test_batch_loader_receives_roots_and_same_names_are_distinct_by_group(tmp_path, controllers):
    loaded = grouped_snapshot(3)
    batch = tmp_path / "batch"
    calls = []

    def load(watch, legacy, *, batch_root, should_stop):
        calls.append((watch, legacy, batch_root))
        assert not should_stop()
        return loaded

    value = create(controllers, tmp_path / "watch", load, batch_root=batch)
    value.refresh_saved()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["saved_status"] == "ready"
    assert status["saved_files_verified"] == status["saved_groups_verified"] == 3
    assert status["saved_files_omitted"] == 0
    assert [r["saved_filename"] for r in status["saved_files"]] == ["001.jpg"] * 3
    assert len({r["group_id"] for r in status["saved_files"]}) == 3
    assert calls == [(tmp_path / "watch", tmp_path / "saved-output", batch)]
    assert not batch.exists()


def test_bounded_batch_page_reports_omissions_without_losing_total_counts():
    loaded = grouped_snapshot(20)
    loaded.summary.update(files_verified=24, groups_verified=24, files_omitted=4)
    status, images = MonitorController._saved_snapshot(loaded)
    assert status["saved_files_verified"] == status["saved_groups_verified"] == 24
    assert status["saved_files_omitted"] == 4
    assert len(status["saved_files"]) == len(images) == 20


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.summary["files"][1].update(group_id=s.summary["files"][0]["group_id"]),
        lambda s: s.summary["files"][1].pop("group_id"),
        lambda s: s.summary["files"][1].update(group_id="../private"),
        lambda s: s.summary.update(groups_verified=1),
        lambda s: s.summary.update(files_omitted=1),
        lambda s: s.summary.update(files_verified=2001, files_omitted=1999),
    ],
)
def test_invalid_batch_group_or_count_cannot_publish_either_image(mutate):
    loaded = grouped_snapshot(2)
    mutate(loaded)
    with pytest.raises(QueueError):
        MonitorController._saved_snapshot(loaded)


def test_batch_without_legacy_root_is_rejected_before_creating_watch_root(tmp_path):
    with pytest.raises(QueueError):
        MonitorController(tmp_path / "watch", batch_root=tmp_path / "batch")
    assert not list(tmp_path.iterdir())
