"""Keep interrupted batch navigation controls shared by all discovery entry points."""

import sqlite3

import pytest
from test_candidate_save_policy import candidate_evidence
from test_monitor_save_policy import NOW

from image_monitor.candidate_save_policy import make_candidate_save_permit
from image_monitor.monitor_controller import MONITOR_SCOPE
from image_monitor.monitor_save_ledger import LEDGER_NAME, LedgerStore
from image_monitor.queue import QueueError, QueueStore
from image_monitor.watch_runtime import DEFAULT_SCOPE, _eligibility
from image_monitor.watch_store import WatchStore


def task_evidence():
    candidate, baseline, detail = candidate_evidence(image_count=1)
    candidate["watch_name"] = detail["watch_name"] = MONITOR_SCOPE.watch_name
    return candidate, detail, make_candidate_save_permit(candidate, baseline, detail)


@pytest.mark.parametrize("control", [{"blocked": True}, {"blocked": False, "in_flight": True}])
def test_batch_access_block_or_unknown_inflight_stops_both_scopes_after_any_cooldown(
    tmp_path, control
):
    root = tmp_path / "watch"
    root.mkdir()
    database = root / "watch.sqlite"
    with QueueStore(database) as queue:
        with LedgerStore(
            root / LEDGER_NAME,
            watch_root=root,
            legacy_root=tmp_path / "legacy",
            batch_root=tmp_path / "batch",
        ) as ledger:
            task = ledger.plan(*task_evidence(), now=NOW)
            ledger.start(task["task_id"], NOW, native_session=1)
            ledger.update_control(task["task_id"], control)
        for scope in (DEFAULT_SCOPE, MONITOR_SCOPE):
            assert _eligibility(queue, WatchStore(queue).get_state(scope), NOW) == (
                "blocked",
                None,
            )
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0


def test_legacy_discovery_without_batch_data_does_not_create_a_ledger_or_output_roots(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        for scope in (DEFAULT_SCOPE, MONITOR_SCOPE):
            assert _eligibility(queue, WatchStore(queue).get_state(scope), NOW) == ("ready", NOW)
    assert not (tmp_path / LEDGER_NAME).exists()
    assert {item.name for item in tmp_path.iterdir()} == {"watch.sqlite"}


@pytest.mark.parametrize("foreign", [b"invalid SQLite", None])
def test_unknown_or_corrupt_batch_ledger_refuses_navigation_without_repair(tmp_path, foreign):
    path = tmp_path / LEDGER_NAME
    if foreign is not None:
        path.write_bytes(foreign)
    else:
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE user_data(value TEXT)")
            connection.execute("INSERT INTO user_data VALUES('preserve')")
    before = path.read_bytes()
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        with pytest.raises((QueueError, sqlite3.Error)):
            _eligibility(queue, WatchStore(queue).get_state(MONITOR_SCOPE), NOW)
    assert path.read_bytes() == before
