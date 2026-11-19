"""Reopen recent-save evidence and verify one completed task without changing it."""

import json
import sqlite3
from contextlib import closing, nullcontext
from types import SimpleNamespace

import pytest
from test_monitor_batch_runtime import finalize
from test_recent_candidate_save import recent as recent
from test_recent_candidate_save import save
from test_saved_catalog_batch import disk_bytes

from image_monitor import saved_catalog
from image_monitor.monitor_save_ledger import RECENT_LEDGER_NAME, LedgerStore
from image_monitor.queue import QueueStore
from image_monitor.watch_images_check import check_recent_images, watch_images_check_exit_code
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE


@pytest.fixture
def local(recent, monkeypatch):
    monkeypatch.setattr(saved_catalog, "NativeSaveLock", nullcontext)
    monkeypatch.setattr(saved_catalog, "shared_state_path", lambda: recent.watch.parent / "pending")
    return recent


def complete(data, post="103"):
    def worker(root, _browser, _url, *, candidate_permit, navigation_observer):
        navigation_observer.before()
        navigation_observer.after(SimpleNamespace(status=200), None)
        finalize(root, candidate_permit, candidate_permit.reference_snapshot, data.clock.now())
        return {
            "status": "post_completed",
            "browser_closed": True,
            "shared_pending_retained": False,
            "job_counts": {"observed": 1, "completed": 1, "unresolved": 0},
        }

    data.clock.wait(60)
    report = save(data, data.handoffs[post], worker)
    assert report["tasks_completed"] == 1, report
    return report["saved_files"]


def root_bytes(data):
    return disk_bytes(SimpleNamespace(root=data.watch.parent))


def result(data):
    return check_recent_images(*data.roots)


def test_verify_only_latest_completed_task_and_keep_prior_files(local):
    complete(local)
    (older,) = local.roots[2].glob("tasks/*/session-1/images/**/001.png")
    files = complete(local, "104")
    older.write_bytes(b"older artifact is outside this check")
    before = root_bytes(local)
    prior_paths = set(local.watch.parent.rglob("*"))
    for _ in range(2):
        report = result(local)
        assert watch_images_check_exit_code(report) == 0
        assert report["status"] == "watch_images_verified" and report["saved_file_count"] == 1
        assert report["saved_files"] == files
        public = json.dumps(report)
        assert all(s not in public for s in (str(local.watch.parent), "https://", "sha256"))
    assert set(local.watch.parent.rglob("*")) == prior_paths
    assert root_bytes(local) == before


@pytest.mark.parametrize("change", ["image", "missing", "metadata", "record", "fingerprint"])
def test_modified_or_missing_evidence_never_reports_success(local, change):
    complete(local)
    tasks = local.roots[2] / "tasks"
    if change in {"image", "missing"}:
        (image,) = tasks.rglob("001.png")
        if change == "image":
            image.write_bytes(b"changed")
        else:
            image.unlink()
    elif change == "metadata":
        (metadata,) = tasks.rglob("metadata.json")
        metadata.write_text("{}")
    else:
        with closing(sqlite3.connect(local.watch / RECENT_LEDGER_NAME)) as db, db:
            if change == "record":
                db.execute("UPDATE save_tasks SET result_json='{}'")
            else:
                db.execute("UPDATE save_tasks SET permit_fingerprint=?", ("c" * 64,))
    before = root_bytes(local)
    checked = result(local)
    assert checked["status"] == "watch_images_review" and watch_images_check_exit_code(checked) == 2
    assert checked["saved_files"] == [] and checked["saved_file_count"] == 0
    assert root_bytes(local) == before


def test_accept_alpha6_local_finish_result_wrapper(local):
    files = complete(local)
    with closing(sqlite3.connect(local.watch / RECENT_LEDGER_NAME)) as db, db:
        raw = db.execute("SELECT result_json FROM save_tasks").fetchone()[0]
        reconciled = {"verification": json.loads(raw), "reconciled_without_native_input": True}
        db.execute("UPDATE save_tasks SET result_json=?", (json.dumps(reconciled),))
    assert result(local)["saved_files"] == files


def test_missing_history_and_empty_ledger_do_not_create_output(tmp_path, local):
    paths = [tmp_path / part for part in ("w", "l", "b")]
    assert check_recent_images(*paths)["status"] == "watch_images_no_saved_files"
    assert list(tmp_path.iterdir()) == []
    before = root_bytes(local)
    assert result(local)["reason"] == "no_recent_save_history"
    assert root_bytes(local) == before
    with LedgerStore(
        local.watch / RECENT_LEDGER_NAME,
        watch_root=local.watch,
        legacy_root=local.roots[1],
        batch_root=local.roots[2],
        scope=DEFAULT_SCOPE.key(),
    ):
        pass
    before = root_bytes(local)
    report = result(local)
    assert report["reason"] == "no_completed_recent_save"
    assert watch_images_check_exit_code(report) == 0 and root_bytes(local) == before


def test_existing_output_without_owner_needs_review(local):
    complete(local)
    (local.watch / RECENT_LEDGER_NAME).unlink()
    assert result(local)["reason"] == "recent_save_ledger_missing"
    assert not (local.watch / RECENT_LEDGER_NAME).exists()


def test_no_sampling_when_another_process_owns_a_lease(local):
    complete(local)
    with watch_run_lock(local.watch / "watch.sqlite", DEFAULT_SCOPE):
        report = result(local)
        assert report["status"] == "watch_images_busy" and report["saved_files"] == []
    marker = local.watch.parent / "pending"
    marker.write_text(json.dumps(dict(run_id="x", run_directory="private", browser_profile="p")))
    before = root_bytes(local)
    assert result(local)["reason"] == "pending_native_save"
    assert root_bytes(local) == before


def test_history_from_before_recent_saving_is_not_migrated(tmp_path):
    watch = tmp_path / "watch"
    watch.mkdir()
    path = watch / "watch.sqlite"
    with QueueStore(path):
        pass
    before = path.read_bytes()
    files = set(tmp_path.rglob("*"))
    report = check_recent_images(watch, tmp_path / "old", tmp_path / "work")
    assert report["status"] == "watch_images_no_saved_files"
    assert path.read_bytes() == before and set(tmp_path.rglob("*")) == files


def test_reading_a_save_with_missing_lease_never_recreates_it(local):
    from image_monitor.watch_lock import _lock_path

    complete(local)
    lease = _lock_path(local.watch / "watch.sqlite", DEFAULT_SCOPE)
    lease.unlink()
    assert result(local)["reason"] == "recent_save_lease_missing"
    assert not lease.exists()


@pytest.mark.parametrize(
    ("source", "sql", "expected_reason"),
    [
        ("ledger", "UPDATE save_tasks SET result_json='{}'", "saved_completion_record_mismatch"),
        ("watch", "DELETE FROM candidate_details", "saved_observation_mismatch"),
        ("native", "DELETE FROM artifact_finalizations", "saved_files_missing_or_changed"),
    ],
)
def test_live_committed_wal_is_authoritative_for_all_three_databases(
    local, source, sql, expected_reason
):
    complete(local)
    (native,) = local.roots[2].glob("tasks/*/session-1/queue.sqlite")
    paths = {
        "ledger": local.watch / RECENT_LEDGER_NAME,
        "watch": local.watch / "watch.sqlite",
        "native": native,
    }
    database = paths[source]
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute(sql)
        connection.commit()
        assert database.with_name(database.name + "-wal").stat().st_size > 0
        before = set(local.watch.parent.rglob("*"))
        checked = result(local)
        assert checked["status"] == "watch_images_review" and checked["reason"] == expected_reason
        assert checked["saved_files"] == [] and set(local.watch.parent.rglob("*")) == before
    finally:
        connection.close()


def test_wal_without_shm_is_never_ignored_or_repaired(local):
    complete(local)
    database = local.watch / "watch.sqlite"
    wal = database.with_name(database.name + "-wal")
    shm = database.with_name(database.name + "-shm")
    connection = sqlite3.connect(database)
    try:
        connection.execute("DELETE FROM candidate_details")
        connection.commit()
        pending_wal = wal.read_bytes()
    finally:
        connection.close()
    assert pending_wal and not shm.exists()
    wal.write_bytes(pending_wal)
    checked = result(local)
    assert checked["status"] == "watch_images_busy" and checked["saved_files"] == []
    assert wal.read_bytes() == pending_wal and not shm.exists()


def test_concurrent_change_after_snapshot_cannot_be_reported_as_verified(local, monkeypatch):
    from image_monitor import watch_images_check as check

    complete(local)
    verify = check.verify_completed_candidate_files

    def change_ledger(*args, **kwargs):
        with closing(sqlite3.connect(local.watch / RECENT_LEDGER_NAME)) as ledger, ledger:
            ledger.execute("UPDATE save_tasks SET result_json='{}'")
        return verify(*args, **kwargs)

    monkeypatch.setattr(check, "verify_completed_candidate_files", change_ledger)
    checked = result(local)
    assert checked["status"] == "watch_images_busy" and checked["saved_files"] == []
