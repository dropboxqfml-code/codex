"""Verify the completed batch registry without publishing partial or private data."""

import json
import re
import socket
import uuid
from contextlib import nullcontext

import pytest
from PIL import Image
from test_candidate_finish_runtime import database_dump
from test_monitor_batch_runtime import data as data
from test_monitor_batch_runtime import (
    finalize,
    ledger,
    run,
)
from test_saved_catalog import assert_unpublished

from image_monitor import saved_catalog as catalog
from image_monitor.candidate_save_selection import MONITOR_MANIFEST_NAME, select_candidate_save
from image_monitor.monitor_controller import MONITOR_SCOPE
from image_monitor.monitor_save_ledger import LEDGER_NAME, task_native_base
from image_monitor.queue import QueueStore


@pytest.fixture
def local_batch(data, monkeypatch):
    monkeypatch.setattr(catalog, "NativeSaveLock", nullcontext)
    monkeypatch.setattr(catalog, "shared_state_path", lambda: data.marker)

    def unexpected_session():
        pytest.fail("Registered completed saves must use their frozen native session")

    monkeypatch.setattr(catalog, "session_id", unexpected_session)
    # Preserve real image verification while making the two files visibly and
    # byte-for-byte distinct despite their identical generic saved filenames.
    make_image = Image.new
    colors = iter(("#224466", "#cc8833"))
    monkeypatch.setattr(
        Image, "new", lambda mode, size, _color: make_image(mode, size, next(colors))
    )
    return data


def load(data, **options):
    return catalog.load_saved_catalog(data.watch, data.legacy, batch_root=data.batch, **options)


def disk_bytes(data):
    # SQLite mode=ro can create empty WAL/SHM coordination sidecars for an
    # existing WAL database, and the standard watch lease has its own sidecar.
    coordination = {"watch.sqlite-wal", "watch.sqlite-shm", "queue.sqlite-wal", "queue.sqlite-shm"}
    return {
        path: path.read_bytes()
        for path in data.root.rglob("*")
        if path.is_file()
        and path.name not in coordination
        and not (path.name.startswith(".image-monitor-watch-") and path.name.endswith(".lock"))
    }


def complete_with_legacy(data):
    with QueueStore(data.watch / "watch.sqlite") as queue:
        permit = select_candidate_save(queue, MONITOR_SCOPE, data.watch / MONITOR_MANIFEST_NAME)
    finalize(data.legacy, permit, data.observations[permit.post_url], data.clock.now())
    report = run(data)
    assert report["adopted_count"] == report["tasks_completed"] == 1
    return report


def test_adopted_legacy_and_managed_same_filename_have_distinct_original_previews(local_batch):
    data = local_batch
    complete_with_legacy(data)
    databases = {
        path: database_dump(path)
        for path in data.root.rglob("*.sqlite")
        if path.name in {"watch.sqlite", "queue.sqlite"}
    }
    before = disk_bytes(data)
    snapshot = load(data)
    assert snapshot.summary["status"] == "ready", snapshot.summary
    assert snapshot.summary["files_verified"] == snapshot.summary["groups_verified"] == 2
    assert snapshot.summary["files_omitted"] == 0
    assert snapshot.summary["preview_count"] == 2
    rows = snapshot.summary["files"]
    assert [row["saved_filename"] for row in rows] == ["001.png", "001.png"]
    assert len({row["group_id"] for row in rows}) == len({row["preview_id"] for row in rows}) == 2
    assert all(re.fullmatch(r"[0-9a-f]{32}", row["group_id"]) for row in rows)
    expected = {
        path.read_bytes()
        for root in (data.legacy, data.batch / "tasks")
        for path in root.rglob("001.png")
    }
    assert len(expected) == 2
    assert {value[1] for value in snapshot.images.values()} == expected
    assert {value[0] for value in snapshot.images.values()} == {"image/png"}
    assert disk_bytes(data) == before
    assert {path: database_dump(path) for path in databases} == databases
    assert not data.marker.exists()
    public = json.dumps(snapshot.summary)
    with ledger(data) as store:
        tasks = store.list_tasks()
    for private in [str(data.root), *[t[key] for t in tasks for key in ("task_id", "post_url")]]:
        assert private not in public


def test_managed_frozen_sessions_do_not_require_legacy_root_or_selection(local_batch):
    data = local_batch
    assert run(data)["tasks_completed"] == 2
    assert not data.legacy.exists()
    assert not (data.watch / MONITOR_MANIFEST_NAME).exists()
    before = disk_bytes(data)
    snapshot = load(data)
    assert snapshot.summary["status"] == "ready", snapshot.summary
    assert snapshot.summary["files_verified"] == 2
    assert disk_bytes(data) == before


def test_batch_refresh_revokes_both_opaque_identity_types(local_batch):
    data = local_batch
    assert run(data)["tasks_completed"] == 2
    first, second = load(data), load(data)
    assert set(first.images).isdisjoint(second.images)
    assert {r["group_id"] for r in first.summary["files"]}.isdisjoint(
        r["group_id"] for r in second.summary["files"]
    )
    assert list(first.images.values()) == list(second.images.values())


def test_missing_ledger_with_existing_tasks_never_falls_back_to_legacy(local_batch):
    data = local_batch
    complete_with_legacy(data)
    (data.watch / LEDGER_NAME).unlink()
    before = disk_bytes(data)
    snapshot = load(data)
    assert_unpublished(snapshot, "needs_review")
    assert snapshot.summary["groups_verified"] == snapshot.summary["files_omitted"] == 0
    assert disk_bytes(data) == before
    assert not (data.watch / LEDGER_NAME).exists()


def test_existing_ledger_cannot_conceal_legacy_output_without_adoption_binding(local_batch):
    data = local_batch
    complete_with_legacy(data)
    with ledger(data, readonly=False) as store:
        store.connection.execute("DELETE FROM save_tasks WHERE output_kind='legacy'")
    before = disk_bytes(data)
    assert_unpublished(load(data), "needs_review")
    assert disk_bytes(data) == before


@pytest.mark.parametrize("output_kind", ["legacy", "managed"])
def test_extra_native_session_without_frozen_binding_requires_review(local_batch, output_kind):
    data = local_batch
    complete_with_legacy(data)
    with ledger(data) as store:
        task = next(t for t in store.list_tasks() if t["output_kind"] == output_kind)
    root = task_native_base(task, data.batch, data.legacy).parent
    (root / "session-55").mkdir()
    before = disk_bytes(data)
    assert_unpublished(load(data), "needs_review")
    assert disk_bytes(data) == before


@pytest.mark.parametrize("kind", ["image", "metadata", "queue"])
def test_bad_second_completed_source_publishes_no_first_preview(local_batch, monkeypatch, kind):
    data = local_batch
    assert run(data)["tasks_completed"] == 2
    with ledger(data) as store:
        second = store.list_tasks()[1]
    base = task_native_base(second, data.batch, data.legacy)
    path = (
        next(base.rglob("001.png"))
        if kind == "image"
        else (next(base.rglob("metadata.json")) if kind == "metadata" else base / "queue.sqlite")
    )
    path.write_bytes(b"Preserve this changed completed source for review")
    before = disk_bytes(data)
    monkeypatch.setattr(
        catalog,
        "_read_preview",
        lambda *_args: pytest.fail("Every completed source must verify before cache loading"),
    )
    assert_unpublished(load(data), "needs_review")
    assert disk_bytes(data) == before


@pytest.mark.parametrize("state", ["started", "needs_review"])
def test_unfinished_registered_task_blocks_all_previews(local_batch, state):
    data = local_batch
    assert run(data)["tasks_completed"] == 2
    with ledger(data, readonly=False) as store:
        second = store.list_tasks()[1]
        if state == "started":
            store.connection.execute(
                "UPDATE save_tasks SET status='started',finished_at=NULL,result_json=NULL "
                "WHERE task_id=?",
                (second["task_id"],),
            )
        else:
            store.connection.execute(
                "UPDATE save_tasks SET status='needs_review' WHERE task_id=?", (second["task_id"],)
            )
    before = disk_bytes(data)
    assert_unpublished(load(data), "needs_review")
    assert disk_bytes(data) == before


def test_unattempted_planned_task_does_not_hide_completed_files(local_batch):
    data = local_batch
    assert run(data, max_tasks=1)["tasks_completed"] == 1
    snapshot = load(data)
    assert snapshot.summary["status"] == "ready", snapshot.summary
    assert snapshot.summary["files_verified"] == snapshot.summary["groups_verified"] == 1


def test_planned_task_with_output_requires_review(local_batch):
    data = local_batch
    assert run(data, max_tasks=1)["tasks_completed"] == 1
    with ledger(data) as store:
        planned = next(t for t in store.list_tasks() if t["status"] == "planned")
    root = data.batch / "tasks" / planned["task_id"]
    root.mkdir(parents=True)
    (root / "unregistered-output.txt").write_text("Preserve this output")
    before = disk_bytes(data)
    assert_unpublished(load(data), "needs_review")
    assert disk_bytes(data) == before


@pytest.mark.parametrize("name", ["unknown", uuid.uuid4().hex])
def test_unknown_task_directory_is_not_discovered_as_an_image_source(local_batch, name):
    data = local_batch
    assert run(data)["tasks_completed"] == 2
    (data.batch / "tasks" / name).mkdir()
    before = disk_bytes(data)
    assert_unpublished(load(data), "needs_review")
    assert disk_bytes(data) == before


def test_bounded_page_reports_omitted_files_but_verifies_every_source(local_batch, monkeypatch):
    data = local_batch
    assert run(data)["tasks_completed"] == 2
    monkeypatch.setattr(catalog, "MAX_CATALOG_FILES", 1)
    real_verify = catalog.verify_completed_candidate_files
    verified = []

    def counted(*args, **kwargs):
        verified.append(kwargs["base"])
        return real_verify(*args, **kwargs)

    monkeypatch.setattr(catalog, "verify_completed_candidate_files", counted)
    snapshot = load(data)
    assert snapshot.summary["status"] == "ready", snapshot.summary
    assert snapshot.summary["reason"] == "preview_limit"
    assert snapshot.summary["files_verified"] == snapshot.summary["groups_verified"] == 2
    assert len(verified) == 2 and len(set(verified)) == 2
    assert snapshot.summary["files_omitted"] == 1
    assert len(snapshot.summary["files"]) == snapshot.summary["preview_count"] == 1
    # The omitted source is still mandatory, including on later refreshes.
    next(verified[1].rglob("001.png")).write_bytes(b"Changed omitted image")
    assert_unpublished(load(data), "needs_review")


def test_batch_total_cache_limit_retains_verified_metadata(local_batch, monkeypatch):
    data = local_batch
    assert run(data)["tasks_completed"] == 2
    sizes = [p.stat().st_size for p in data.batch.rglob("001.png")]
    monkeypatch.setattr(catalog, "MAX_TOTAL_PREVIEW_BYTES", max(sizes))
    snapshot = load(data)
    assert snapshot.summary["status"] == "ready"
    assert snapshot.summary["files_verified"] == 2 and snapshot.summary["preview_count"] == 1
    assert snapshot.summary["reason"] == "preview_limit"
    assert len(snapshot.summary["files"]) == 2
    assert sum(len(v[1]) for v in snapshot.images.values()) <= max(sizes)


def test_batch_local_verification_does_not_open_network_or_native_worker(local_batch, monkeypatch):
    data = local_batch
    assert run(data)["tasks_completed"] == 2

    def unexpected(*_args, **_kwargs):
        pytest.fail("A saved catalog must perform only local read-only verification")

    monkeypatch.setattr(socket, "socket", unexpected)
    monkeypatch.setattr("image_monitor.monitor_batch_runtime.run_post_save", unexpected)
    monkeypatch.setattr("image_monitor.monitor_save_ledger.LedgerStore._write", unexpected)
    assert load(data).summary["status"] == "ready"


def test_configured_batch_without_registry_or_tasks_can_show_existing_legacy(
    local_batch, monkeypatch
):
    data = local_batch
    with QueueStore(data.watch / "watch.sqlite") as queue:
        permit = select_candidate_save(queue, MONITOR_SCOPE, data.watch / MONITOR_MANIFEST_NAME)
    finalize(data.legacy, permit, data.observations[permit.post_url], data.clock.now())
    monkeypatch.setattr(catalog, "session_id", lambda: 1)
    before = disk_bytes(data)
    snapshot = load(data)
    assert snapshot.summary["status"] == "ready", snapshot.summary
    assert snapshot.summary["groups_verified"] == snapshot.summary["files_verified"] == 1
    assert snapshot.summary["files_omitted"] == 0
    assert disk_bytes(data) == before
    assert not (data.watch / LEDGER_NAME).exists() and not data.batch.exists()


def test_missing_batch_roots_do_not_create_registry_or_output(tmp_path):
    snapshot = catalog.load_saved_catalog(
        tmp_path / "watch", tmp_path / "legacy", batch_root=tmp_path / "batch"
    )
    assert_unpublished(snapshot, "empty")
    assert snapshot.summary["groups_verified"] == snapshot.summary["files_omitted"] == 0
    assert list(tmp_path.iterdir()) == []
