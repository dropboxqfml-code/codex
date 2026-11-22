"""Reopen a watch with a displaced fifth page and check both acceptance and refusal."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import test_monitor_catchup_integration as fixture
from test_monitor_gap_followup_integration import listing
from test_monitor_long_gap import read_state
from test_monitor_recent_tail_integration import due_clock, enable_chrome, release_archive

from image_monitor import PUBLIC_VERSION
from image_monitor.monitor_gap_store import load_bookmark
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore

# 26 genuinely newer posts; older posts keep their relative order across the saved head
# and frontier. The lower end of the live fixture contains the original checkpoint.
ARRIVALS = list(range(523, 497, -1))
SHIFTED = ARRIVALS + [n for n in fixture.FEED if n > 240 or n <= 100]


def seed_fifth_page(watch):
    fixture.seed_open_gap(watch)
    for numbers in ([1, 2, 3, 4], [1, 2, 4, 5]):
        pages = [fixture.FEED[(n - 1) * 20 : n * 20] for n in numbers]
        result = listing(pages, [], page_numbers=numbers)(
            watch, clock=due_clock(watch), interval_seconds=60
        )
        if numbers[-1] == 4:
            assert result["recovery_status"] == "segment_queued" and result["new_candidates"] == 28
            assert result["recovery_observation"] == "disjoint_recent_rows"
        else:
            assert result["recovery_status"] == "advanced" and result["new_candidates"] == 1


def catchup(watch, *, seed=False, short=False):
    with pytest.MonkeyPatch.context() as patch:
        enable_chrome(patch)
        if seed:
            seed_fifth_page(watch)
        # Only the first two saved frontier IDs reach page six in the short variant.
        feed = SHIFTED[: SHIFTED.index(416) + 1] if short else SHIFTED
        patch.setattr(fixture, "FEED", feed)
        return fixture.run_catchup(watch)


def restart(watch, *, seed=False, short=False, archived=None):
    env = os.environ | {"PYTHONUTF8": "1"}
    if archived:
        env["PYTHONPATH"] = str(archived / "image-monitor" / "src")
    run = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,sys; from pathlib import Path; "
            "from test_monitor_frontier_relocation_integration import catchup; "
            "print(json.dumps(catchup(Path(sys.argv[1]), **json.load(sys.stdin))))",
            str(watch),
        ],
        cwd=Path(__file__).parent,
        input=json.dumps({"seed": seed, "short": short}),
        capture_output=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr
    report, trace = json.loads(run.stdout)
    assert report["program_version"] == ("0.5.0-alpha.17" if archived else PUBLIC_VERSION)
    return report, trace


def bookmark(watch):
    with QueueStore(watch / "watch.sqlite", read_only=True) as queue:
        current = WatchStore(queue).get_state(MONITOR_SCOPE)
        return load_bookmark(queue, current)


def test_restart_after_26_arrivals_relocates_the_clipped_frontier_only_on_positive_evidence(
    tmp_path, monkeypatch
):
    pytest.importorskip("playwright.sync_api")
    enable_chrome(monkeypatch)
    watch = tmp_path / "이전 감시"
    shipped = release_archive(17)
    if (shipped.parent.parent / ".git").exists():
        assert shipped.is_file(), "The checkout must include the distributed alpha.17"
    if shipped.is_file():
        # Same two physical snapshots as the accepted upgrade case, read by the old binary.
        held, trace = restart(watch, seed=True, archived=shipped)
    else:
        # A standalone project ZIP has no previous distributions. Exercise the real current
        # refusal on short evidence, then supply a complete sixth page on this same watch.
        held, trace = restart(watch, seed=True, short=True)
    fixture.assert_public_checks(held, trace)
    assert held["reason"] == "recovery_followup_deferred" and len(trace) == 1
    assert trace[0]["pages"] == [1, 2, 5, 6] and set(trace[0]["new"]) == {str(n) for n in ARRIVALS}
    assert [check["recovery_status"] for check in held["previous_list_checks"]] == [
        "segment_queued",
        "advanced",
    ]
    assert held["last_list"]["recovery_status"] == "frontier_changed"
    checkpoint, known = read_state(watch)
    assert checkpoint["anchor_ids"] == ["100", "99"]
    saved = bookmark(watch)
    assert saved["frontier"]["page"] == saved["depth"] == 5 and saved["deferred"]
    assert saved["frontier_ids"] == [str(n) for n in range(417, 397, -1)]
    # Pages 3 and 4 are physically skipped. All their stable visible posts were already
    # registered on the preceding recent route; a new first_scan_id would be a duplicate.
    assert {str(n) for n in SHIFTED[40:80]} <= known.keys()

    weak, trace = catchup(watch, short=True)
    fixture.assert_public_checks(weak, trace)
    assert len(trace) == 1 and trace[0]["pages"] == [1, 2, 5, 6] and trace[0]["new"] == []
    assert weak["last_list"]["recovery_status"] == "frontier_changed" and bookmark(watch) == saved
    short = weak["last_list"]
    assert short["frontier_overlap"] == {
        "previous_rows": 20,
        "matched_rows": 2,
        "shape": "prefix_at_end",
    }
    assert short["candidate_eligible_visits"] == 2 and short["frontier_overlap_ko"]
    if shipped.is_file():
        # The read-only projection can describe the old observation, while respecting its
        # original decision to hold both tail pages out of the eligible candidate set.
        archived = weak["previous_list_checks"][-1]
        assert (
            archived["recovery_status"] == "frontier_changed"
            and archived["candidate_eligible_visits"] == 2
        )
        assert archived["frontier_overlap"] == {
            "previous_rows": 20,
            "matched_rows": 14,
            "shape": "prefix_at_end",
        }
    assert read_state(watch) == (checkpoint, known)

    first, scans = restart(watch)
    fixture.assert_public_checks(first, scans)
    assert first["reason"] == "cycle_limit_reached" and len(scans) == 8
    relocated = first["recent_list_checks"][0]
    assert (relocated["status"], relocated["recovery_status"], relocated["recovery_depth"]) == (
        "partial",
        "frontier_relocated",
        6,
    )
    assert (
        relocated["recovery_reason"] == "frontier_prefix_overlap"
        and relocated["recovery_reason_ko"]
    )
    assert relocated["frontier_overlap"] == {
        "previous_rows": 20,
        "matched_rows": 14,
        "shape": "prefix_at_end",
    }
    assert relocated["candidate_eligible_visits"] == 4 and relocated["frontier_overlap_ko"]
    assert [scan["pages"] for scan in scans[:2]] == [[1, 2, 5, 6], [1, 2, 6, 7]]
    assert scans[0]["new"] == [] and first["gap_followups_completed"] == 0
    with QueueStore(watch / "watch.sqlite", read_only=True) as queue:
        [relocation] = [
            item
            for item in WatchStore(queue).list_scans(MONITOR_SCOPE)
            if item["result"].get("gap_recovery", {}).get("status") == "frontier_relocated"
        ]
    moved = relocation["result"]["gap_recovery"]["bookmark"]
    assert moved["target_ids"] == saved["target_ids"] and moved["deferred"] == saved["deferred"]
    assert moved["frontier"]["page"] == moved["depth"] == 6
    assert moved["frontier_ids"] == [str(n) for n in SHIFTED[100:120]]
    previous, partial = read_state(watch)
    assert previous == checkpoint and known.items() <= partial.items()

    second, resumed = restart(watch)
    fixture.assert_public_checks(second, resumed)
    boundary = scans[-1]["pages"][-1]
    assert resumed[0]["pages"] == [1, 2, boundary, boundary + 1]
    anchor = SHIFTED.index(100) // 20 + 1
    assert resumed[-2]["pages"][-1] == anchor and resumed[-1]["pages"] == [1, 2, anchor, anchor + 1]
    assert second["recent_list_checks"][-2]["status"] == "partial"
    assert second["reason"] == "list_coverage_confirmed" and second["gap_followups_completed"] == 1
    completed, found = read_state(watch)
    assert completed["anchor_ids"][0] == "523" and partial.items() <= found.items()
    assert set(found) == {str(n) for n in SHIFTED if n > 100}
