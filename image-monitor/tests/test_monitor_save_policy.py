"""Keep native permits and fixed selections isolated across the two reviewed scopes."""

import copy
import json
from dataclasses import replace
from datetime import timedelta

import pytest
from test_candidate_save_policy import candidate_evidence, snapshot_from
from test_candidate_save_selection import BASELINE, NOW, seed, snapshot

from image_monitor.candidate_policy import classify_candidate_detail
from image_monitor.candidate_save_policy import (
    MONITOR_SCOPE,
    REVIEWED_SCOPE,
    CandidateSavePolicyError,
    make_candidate_save_permit,
)
from image_monitor.candidate_save_selection import (
    MANIFEST_NAME,
    MONITOR_MANIFEST_NAME,
    read_selection,
    select_candidate_save,
    selection_manifest_name,
    selection_service_blocked,
    write_selection_control,
)
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.dcinside import SITE_VERIFIED_POST
from image_monitor.queue import QueueError, QueueStore
from image_monitor.watch_runtime import DEFAULT_SCOPE, _eligibility
from image_monitor.watch_store import WatchScope, WatchStore

MONITOR = WatchScope(*MONITOR_SCOPE)


def monitor_evidence(**options):
    candidate, baseline, detail = candidate_evidence(**options)
    candidate["watch_name"] = detail["watch_name"] = MONITOR.watch_name
    return candidate, baseline, detail


def finish_detail(queue, candidate, *, scope=MONITOR):
    baseline = WatchStore(queue).get_state(scope)["baseline"]
    started = NOW - timedelta(seconds=60)
    finished = started + timedelta(seconds=5)
    store = CandidateDetailStore(queue)
    attempt = store.start(
        scope,
        candidate["post_id"],
        expected_first_scan_id=candidate["first_scan_id"],
        baseline_observed_at=BASELINE,
        started_at=started,
    )
    observed = snapshot(candidate, observed_at=started)
    return store.finish(
        attempt["attempt_id"],
        finished_at=finished,
        result={
            "classification": classify_candidate_detail(candidate, baseline, observed),
            "private_observation": {
                "status": "observed",
                "url": candidate["post_url"],
                "http_status": 200,
                "navigation_attempts": 1,
                "snapshot": observed,
            },
            "control": {
                "blocked": False,
                "finished_at": finished.isoformat(),
                "next_eligible_at": (finished + timedelta(seconds=60)).isoformat(),
                "interval_seconds": 60,
                "http_status": 200,
            },
        },
    )


def source_records(queue):
    store = WatchStore(queue)
    details = CandidateDetailStore(queue)
    return {
        scope.watch_name: {
            "state": store.get_state(scope),
            "candidates": store.list_candidates(scope),
            "scans": store.list_scans(scope),
            "gaps": store.list_gaps(scope),
            "details": details.list_details(scope),
        }
        for scope in (DEFAULT_SCOPE, MONITOR)
    }


def select_both(queue, root):
    selections = {}
    for scope in (DEFAULT_SCOPE, MONITOR):
        candidates = seed(queue, scope=scope)
        finish_detail(queue, candidates[0], scope=scope)
        path = root / selection_manifest_name(scope)
        selections[scope.watch_name] = (
            candidates,
            path,
            select_candidate_save(queue, scope, path),
        )
    return selections


def test_monitor_permit_is_bound_to_one_exact_observation_without_global_trust_expansion():
    candidate, baseline, detail = monitor_evidence(image_count=1)
    before = copy.deepcopy((candidate, baseline, detail))
    permit = make_candidate_save_permit(candidate, baseline, detail)
    fresh = snapshot_from(detail)
    approved = permit.authorize_snapshot(fresh)
    assert permit.watch_name == "목록 감시"
    assert permit.image_count == 1
    assert permit.post_url == candidate["post_url"]
    assert approved["layout_status"] == "candidate_reviewed"
    assert approved["queue_eligible"] is True
    assert approved["profile_evidence"]["pilot_scope"]["save_scope"] == "one_frozen_candidate"
    assert SITE_VERIFIED_POST == ("normal", "comic_new6", "7036949")
    assert fresh["layout_status"] == "unverified" and fresh["queue_eligible"] is False
    assert (candidate, baseline, detail) == before
    assert REVIEWED_SCOPE == DEFAULT_SCOPE.key()


@pytest.mark.parametrize(
    "candidate_watch,detail_watch",
    [("목록 감시", "검색 감시 시험"), ("검색 감시 시험", "목록 감시")],
)
def test_individually_reviewed_but_mixed_scopes_cannot_make_a_permit(candidate_watch, detail_watch):
    candidate, baseline, detail = candidate_evidence(image_count=1)
    candidate["watch_name"] = candidate_watch
    detail["watch_name"] = detail_watch
    with pytest.raises(CandidateSavePolicyError, match="scope"):
        make_candidate_save_permit(candidate, baseline, detail)


@pytest.mark.parametrize("count", [0, 11])
def test_monitor_permit_rejects_counts_outside_one_to_ten(count):
    with pytest.raises(CandidateSavePolicyError):
        make_candidate_save_permit(*monitor_evidence(image_count=count))


@pytest.mark.parametrize(
    "field,value",
    [
        ("watch_name", "Another watch"),
        ("gallery_type", "minor"),
        ("gallery_id", "another_gallery"),
        ("keyword", "another keyword"),
        ("search_type", "search_subject"),
    ],
)
def test_unknown_scope_cannot_choose_a_selection_file_or_native_permit(field, value):
    scope = replace(MONITOR, **{field: value})
    with pytest.raises(QueueError):
        selection_manifest_name(scope)
    candidate, baseline, detail = monitor_evidence(image_count=1)
    candidate[field] = detail[field] = value
    with pytest.raises(CandidateSavePolicyError):
        make_candidate_save_permit(candidate, baseline, detail)


def test_same_post_identity_in_two_scopes_has_separate_frozen_selection_and_unchanged_sources(
    tmp_path,
):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        candidates = seed(queue, scope=DEFAULT_SCOPE)
        finish_detail(queue, candidates[0], scope=DEFAULT_SCOPE)
        legacy = tmp_path / MANIFEST_NAME
        legacy_permit = select_candidate_save(queue, DEFAULT_SCOPE, legacy)
        legacy_bytes = legacy.read_bytes()
        monitor_candidates = seed(queue, scope=MONITOR)
        finish_detail(queue, monitor_candidates[0])
        before = source_records(queue)
        monitor = tmp_path / MONITOR_MANIFEST_NAME
        monitor_permit = select_candidate_save(queue, MONITOR, monitor)
        assert monitor_permit.post_url == legacy_permit.post_url
        assert monitor_permit.fingerprint != legacy_permit.fingerprint
        assert legacy.read_bytes() == legacy_bytes
        assert read_selection(legacy)["scope"]["watch_name"] == DEFAULT_SCOPE.watch_name
        assert read_selection(monitor)["scope"]["watch_name"] == MONITOR.watch_name
        assert source_records(queue) == before
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0


def test_monitor_selection_is_pinned_after_other_detail_and_list_metadata_refresh(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        candidates = seed(queue, scope=MONITOR)
        first = finish_detail(queue, candidates[0])
        path = tmp_path / MONITOR_MANIFEST_NAME
        permit = select_candidate_save(queue, MONITOR, path)
        finish_detail(queue, candidates[1])
        store = WatchStore(queue)
        state = store.get_state(MONITOR)
        store.persist_scan(
            MONITOR,
            observed_at=NOW,
            expected_generation=state["generation"],
            scan_result={"mode": "invented_refresh"},
            candidates=[
                {
                    "post_id": candidates[0]["post_id"],
                    "post_url": candidates[0]["post_url"],
                    "title": "Invented refreshed title",
                    "shown_metadata": {"changed": True},
                }
            ],
            checkpoint=state["checkpoint"],
            complete=True,
        )
        before = path.read_bytes()
        repeated = select_candidate_save(queue, MONITOR, path)
        assert repeated.detail_attempt_id == first["attempt_id"]
        assert repeated.fingerprint == permit.fingerprint
        assert path.read_bytes() == before


@pytest.mark.parametrize(
    "scope,wrong_name", [(DEFAULT_SCOPE, MONITOR_MANIFEST_NAME), (MONITOR, MANIFEST_NAME)]
)
def test_selection_rejects_the_other_scope_filename_before_creating_it(tmp_path, scope, wrong_name):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        candidates = seed(queue, scope=scope)
        finish_detail(queue, candidates[0], scope=scope)
        with pytest.raises(QueueError):
            select_candidate_save(queue, scope, tmp_path / wrong_name)
        assert not (tmp_path / wrong_name).exists()


@pytest.mark.parametrize(
    "source_name,target_name",
    [(MANIFEST_NAME, MONITOR_MANIFEST_NAME), (MONITOR_MANIFEST_NAME, MANIFEST_NAME)],
)
def test_copied_selection_with_wrong_scope_binding_is_preserved_and_rejected_for_reads_and_updates(
    tmp_path, source_name, target_name
):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        select_both(queue, tmp_path)
        source = tmp_path / source_name
        target = tmp_path / target_name
        original = source.read_bytes()
        target.write_bytes(original)
        with pytest.raises(QueueError, match="filename"):
            read_selection(target)
        with pytest.raises(QueueError, match="filename"):
            write_selection_control(target, {"blocked": True})
        with pytest.raises(QueueError, match="filename"):
            selection_service_blocked(queue)
        assert source.read_bytes() == target.read_bytes() == original


@pytest.mark.parametrize("blocked_scope", [DEFAULT_SCOPE, MONITOR])
def test_either_native_selection_block_stops_both_watch_scopes(tmp_path, blocked_scope):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        select_both(queue, tmp_path)
        write_selection_control(
            tmp_path / selection_manifest_name(blocked_scope), {"blocked": True}
        )
        assert selection_service_blocked(queue) is True
        for scope in (DEFAULT_SCOPE, MONITOR):
            assert _eligibility(queue, WatchStore(queue).get_state(scope), NOW)[0] == "blocked"


@pytest.mark.parametrize("corrupt_name", [MANIFEST_NAME, MONITOR_MANIFEST_NAME])
def test_corrupt_sidecar_blocks_even_when_the_other_selection_is_valid_and_unblocked(
    tmp_path, corrupt_name
):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        select_both(queue, tmp_path)
        path = tmp_path / corrupt_name
        path.write_bytes(b'{"invalid":')
        with pytest.raises(QueueError):
            selection_service_blocked(queue)
        assert path.read_bytes() == b'{"invalid":'


def test_changed_frozen_monitor_detail_cannot_rebind_or_replace_the_manifest(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        candidates = seed(queue, scope=MONITOR)
        detail = finish_detail(queue, candidates[0])
        path = tmp_path / MONITOR_MANIFEST_NAME
        permit = select_candidate_save(queue, MONITOR, path)
        original = path.read_bytes()
        changed = copy.deepcopy(detail["result"])
        changed["private_observation"]["snapshot"]["title"] = "Invented changed body title"
        with queue._write():
            queue.connection.execute(
                "UPDATE candidate_details SET result_json=? WHERE attempt_id=?",
                (json.dumps(changed), detail["attempt_id"]),
            )
        with pytest.raises(QueueError, match="changed"):
            select_candidate_save(queue, MONITOR, path)
        assert path.read_bytes() == original
        assert read_selection(path)["evidence_sha256"] == permit.fingerprint


def test_current_monitor_image_source_change_cannot_reuse_the_frozen_permit():
    candidate, baseline, detail = monitor_evidence(image_count=1)
    permit = make_candidate_save_permit(candidate, baseline, detail)
    current = copy.deepcopy(snapshot_from(detail))
    current["images"][0]["display_url"] = "https://images.example/changed.png"
    with pytest.raises(CandidateSavePolicyError):
        permit.authorize_snapshot(current)
