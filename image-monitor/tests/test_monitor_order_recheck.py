"""An out-of-order live page must be read afresh before a collector can run."""

import pytest
from test_monitor_auto_session import collection
from test_monitor_frontier_relocation_integration import bookmark, seed_fifth_page
from test_monitor_gap_followup_integration import listing
from test_monitor_long_gap import read_state
from test_monitor_recent_tail_integration import due_clock

from image_monitor import watch_runtime
from image_monitor.auto_monitor_cli import _describe_result, _progress_message
from image_monitor.monitor_auto_session import run_auto_monitor
from image_monitor.monitor_list_review import previous_list_review, public_list_review


@pytest.mark.parametrize(
    ("third", "issue", "repaired"),
    [
        ([604, 550], "increase_across_pages", True),
        ([548, 552], "increase_on_page", False),
        ([551, 551], "duplicate_on_page", False),
    ],
)
def test_recheck_requires_a_new_verified_read(tmp_path, monkeypatch, third, issue, repaired):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    watch = tmp_path / "watch"
    seed_fifth_page(watch)
    checkpoint, _ = read_state(watch)
    prior = bookmark(watch)
    clock = due_clock(watch)
    visits, collected, waits = [], [], []
    head = [[603, 602], [601, 600]]
    bad = head + [third]
    feeds = iter([bad, head + [[599, 598], [597, 596]] if repaired else bad])

    def scan(root, **kwargs):
        current = []
        visits.append((clock.now(), current))
        return listing(next(feeds), current)(root, **kwargs)

    def collect(*args, **kwargs):
        collected.append(clock.now())
        return collection()

    def observe(summary):
        if summary["phase"] == "waiting":
            waits.append(_progress_message(summary))
            assert read_state(watch)[0] == checkpoint
            assert bookmark(watch) == prior

    report = _describe_result(
        run_auto_monitor(
            watch,
            tmp_path / "legacy",
            tmp_path / "saves",
            clock=clock,
            max_cycles=1,
            on_progress=observe,
            scan_runner=scan,
            collect_runner=collect,
        )
    )
    assert report["order_retries_scheduled"] == 1, report
    assert "3쪽 글번호 순서 미확인" in waits[0]
    assert (visits[1][0] - visits[0][0]).total_seconds() == 60
    assert [len(x[1]) for x in visits] == [3, 4 if repaired else 3]
    assert report["last_order_retry"]["order_check"] == {"visit": 3, "page": 3, "issue": issue}
    assert report["last_order_retry"]["observation_ko"].startswith("3쪽")
    assert report["list_checks"] == len(collected) == int(repaired)
    assert report["reason"] == ("cycle_limit_reached" if repaired else "list_scan_requires_review")
    if not repaired:
        assert bookmark(watch) == prior and read_state(watch)[0] == checkpoint
        current = previous_list_review(watch)
        assert current["order_check"] == report["last_order_retry"]["order_check"]
        for bad_field in ({"visit": True}, {"page": 53}, {"issue": ["private"]}):
            assert "order_check" not in public_list_review(
                current | {"order_check": current["order_check"] | bad_field}
            )
