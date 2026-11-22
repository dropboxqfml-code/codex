from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from image_monitor.queue import QueueError
from image_monitor.watch_lock import WatchRunBusy, watch_list_lock, watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE
from image_monitor.watch_store import MONITOR_SCOPE


def test_only_explicit_list_helper_can_use_the_writers_lease(tmp_path):
    database = tmp_path / "watch.sqlite"
    with (
        watch_run_lock(database, DEFAULT_SCOPE) as lease,
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        with pytest.raises(WatchRunBusy), watch_list_lock(database, DEFAULT_SCOPE):
            pass

        def check():
            with lease.borrow_for_list():
                with watch_list_lock(database, DEFAULT_SCOPE):
                    with pytest.raises(WatchRunBusy), watch_list_lock(database, DEFAULT_SCOPE):
                        pass
                    with pytest.raises(WatchRunBusy), watch_run_lock(database, DEFAULT_SCOPE):
                        pass
                with pytest.raises(QueueError), watch_list_lock(tmp_path / "other", DEFAULT_SCOPE):
                    pass
                with pytest.raises(QueueError), watch_list_lock(database, MONITOR_SCOPE):
                    pass
                with watch_list_lock(database, DEFAULT_SCOPE):
                    pass
            with pytest.raises(WatchRunBusy), watch_list_lock(database, DEFAULT_SCOPE):
                pass

        pool.submit(check).result(timeout=10)
    with pytest.raises(QueueError), lease.borrow_for_list():
        pass
    with watch_list_lock(database, DEFAULT_SCOPE, existing_only=True):
        pass
    with watch_run_lock(database, DEFAULT_SCOPE, purpose="monitor") as other:
        with pytest.raises(QueueError), other.borrow_for_list():
            pass


def test_releasing_owner_keeps_the_file_locked_until_borrower_exits(tmp_path):
    database = tmp_path / "watch.sqlite"
    has_lease, lending, owner_exiting, release_helper = (Event() for _ in range(4))
    ready = []

    def owner():
        with watch_run_lock(database, DEFAULT_SCOPE) as lease:
            ready.append(lease)
            has_lease.set()
            assert lending.wait(10)
            owner_exiting.set()

    def helper():
        assert has_lease.wait(10)
        with ready[0].borrow_for_list(), watch_list_lock(database, DEFAULT_SCOPE):
            lending.set()
            assert release_helper.wait(10)

    with ThreadPoolExecutor(max_workers=2) as pool:
        owner_future, helper_future = pool.submit(owner), pool.submit(helper)
        try:
            assert owner_exiting.wait(10)
            with pytest.raises(WatchRunBusy), watch_run_lock(database, DEFAULT_SCOPE):
                pass
            with pytest.raises(WatchRunBusy), ready[0].borrow_for_list():
                pass
        finally:
            release_helper.set()
        helper_future.result(timeout=10)
        owner_future.result(timeout=10)
    with watch_run_lock(database, DEFAULT_SCOPE, existing_only=True):
        pass
