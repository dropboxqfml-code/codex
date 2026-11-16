"""Freeze one candidate without mutating list state or retrying another post."""

import json
import os
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from image_monitor import candidate_save_selection as selection
from image_monitor.candidate_policy import classify_candidate_detail
from image_monitor.candidate_save_selection import (
    MANIFEST_NAME,
    MAX_SELECTION_BYTES,
    read_selection,
    select_candidate_save,
    selection_service_blocked,
    write_selection_control,
)
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.dcinside import parse_snapshot
from image_monitor.queue import QueueError, QueueStore
from image_monitor.watch_runtime import DEFAULT_SCOPE
from image_monitor.watch_store import WatchStore

NOW = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)
BASELINE = NOW - timedelta(minutes=10)


def seed(queue, ids=("101", "102"), *, scope=DEFAULT_SCOPE):
    store = WatchStore(queue)
    baseline = {"mode": "new", "observed_at": BASELINE.isoformat(), "anchor_ids": ["100"]}
    store.persist_scan(
        scope,
        observed_at=BASELINE,
        expected_generation=0,
        scan_result={"mode": "invented_fixture"},
        candidates=[],
        checkpoint=baseline,
        complete=True,
        baseline=baseline,
    )
    store.persist_scan(
        scope,
        observed_at=NOW - timedelta(minutes=2),
        expected_generation=1,
        scan_result={"mode": "invented_fixture"},
        candidates=[
            {
                "post_id": post_id,
                "post_url": f"https://gall.dcinside.com/board/view/?id=comic_new6&no={post_id}",
                "title": "Invented list title",
                "shown_metadata": {},
            }
            for post_id in ids
        ],
        checkpoint=baseline | {"anchor_ids": list(ids) + ["100"]},
        complete=True,
    )
    return store.list_candidates(scope)


def snapshot(
    candidate,
    *,
    count=1,
    published=BASELINE + timedelta(seconds=30),
    observed_at=NOW - timedelta(seconds=60),
):
    return parse_snapshot(
        {
            "body_count": 1,
            "header_count": 1,
            "header_field_counts": {".gall_writer": 1, ".gall_date": 1, ".title_subject": 1},
            "title": "Invented body title",
            "nickname": "Invented author",
            "ip_display": None,
            "published_at_raw": published.astimezone(ZoneInfo("Asia/Seoul")).strftime(
                "%Y.%m.%d %H:%M:%S"
            ),
            "attachments": [],
            "images": [
                {
                    "body_order": index + 1,
                    "display_url": f"https://example.test/body-{candidate['post_id']}-{index}.png",
                    "complete": True,
                    "decode_ok": True,
                    "natural_width": 4,
                    "natural_height": 3,
                }
                for index in range(count)
            ],
            "diagnostics": {"counts": {".write_div": 1, ".gallview_head": 1}},
        },
        expected_url=candidate["post_url"],
        observed_at=observed_at,
    )


def finish(queue, candidate, *, count=1, published=BASELINE + timedelta(seconds=30)):
    store = CandidateDetailStore(queue)
    started = NOW - timedelta(seconds=60) + timedelta(seconds=int(candidate["post_id"]) - 101)
    finished = started + timedelta(seconds=5)
    baseline = WatchStore(queue).get_state(DEFAULT_SCOPE)["baseline"]
    attempt = store.start(
        DEFAULT_SCOPE,
        candidate["post_id"],
        expected_first_scan_id=candidate["first_scan_id"],
        baseline_observed_at=BASELINE,
        started_at=started,
    )
    observed = snapshot(candidate, count=count, published=published, observed_at=started)
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


def evidence(queue):
    watch = WatchStore(queue)
    return (
        watch.get_state(DEFAULT_SCOPE),
        watch.list_candidates(DEFAULT_SCOPE),
        watch.list_scans(DEFAULT_SCOPE),
        watch.list_gaps(DEFAULT_SCOPE),
        CandidateDetailStore(queue).list_details(DEFAULT_SCOPE),
        queue.summary(),
    )


def selected(tmp_path):
    queue = QueueStore(tmp_path / "watch.sqlite")
    candidates = seed(queue)
    detail = finish(queue, candidates[0])
    manifest = tmp_path / MANIFEST_NAME
    permit = select_candidate_save(queue, DEFAULT_SCOPE, manifest)
    return queue, candidates, detail, manifest, permit


def test_zero_image_detail_is_skipped_and_one_selection_preserves_database(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        candidates = seed(queue)
        finish(queue, candidates[0], count=0)
        target = finish(queue, candidates[1], count=2)
        before = evidence(queue)
        path = tmp_path / MANIFEST_NAME
        permit = select_candidate_save(queue, DEFAULT_SCOPE, path)
        assert permit.detail_attempt_id == target["attempt_id"]
        assert permit.post_url == candidates[1]["post_url"]
        assert evidence(queue) == before
        value = read_selection(path)
        assert value["detail_attempt_id"] == target["attempt_id"]
        assert value["post_id"] == "102"
        assert value["control"] == {"blocked": False}
        assert value["evidence_sha256"] == permit.fingerprint
        encoded = path.read_text()
        assert "example.test" not in encoded and "Invented body title" not in encoded
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0


def test_repeat_selection_retains_same_binding_and_control_after_other_detail_completes(tmp_path):
    queue, candidates, detail, path, permit = selected(tmp_path)
    with queue:
        write_selection_control(path, {"blocked": False, "http_status": 200})
        finish(queue, candidates[1])
        repeated = select_candidate_save(queue, DEFAULT_SCOPE, path)
        assert repeated.detail_attempt_id == detail["attempt_id"]
        assert repeated.fingerprint == permit.fingerprint
        assert read_selection(path)["control"] == {"blocked": False, "http_status": 200}


def test_normal_candidate_metadata_refresh_does_not_change_frozen_selection(tmp_path):
    queue, _, _, path, permit = selected(tmp_path)
    with queue:
        queue.connection.execute(
            "UPDATE watch_candidates SET title='New displayed title',last_seen_at=?,"
            "shown_metadata_json='{}' WHERE post_id='101'",
            ((NOW + timedelta(minutes=5)).isoformat(),),
        )
        assert select_candidate_save(queue, DEFAULT_SCOPE, path).fingerprint == permit.fingerprint


@pytest.mark.parametrize("change", ["baseline", "detail", "discovery", "first_seen"])
def test_changed_frozen_evidence_refuses_repeat_without_replacing_manifest(tmp_path, change):
    queue, _, detail, path, _ = selected(tmp_path)
    with queue:
        before = path.read_bytes()
        if change == "baseline":
            value = WatchStore(queue).get_state(DEFAULT_SCOPE)["baseline"]
            value["observed_at"] = (BASELINE + timedelta(seconds=1)).isoformat()
            queue.connection.execute("UPDATE watch_state SET baseline_json=?", (json.dumps(value),))
        elif change == "detail":
            result = deepcopy(detail["result"])
            result["private_observation"]["snapshot"]["title"] = "Changed body title"
            queue.connection.execute(
                "UPDATE candidate_details SET result_json=? WHERE attempt_id=?",
                (json.dumps(result), detail["attempt_id"]),
            )
        elif change == "discovery":
            queue.connection.execute(
                "UPDATE watch_candidates SET first_scan_id=(SELECT scan_id FROM watch_scans "
                "WHERE generation=1) WHERE post_id='101'"
            )
        else:
            queue.connection.execute(
                "UPDATE watch_candidates SET first_seen_at=? WHERE post_id='101'",
                ((NOW - timedelta(seconds=61)).isoformat(),),
            )
        with pytest.raises(QueueError):
            select_candidate_save(queue, DEFAULT_SCOPE, path)
        assert path.read_bytes() == before


def test_existing_selection_cannot_switch_watch_scope(tmp_path):
    queue, _, _, path, _ = selected(tmp_path)
    with queue:
        before = path.read_bytes()
        with pytest.raises(QueueError, match="scope"):
            select_candidate_save(queue, replace(DEFAULT_SCOPE, watch_name="other"), path)
        assert path.read_bytes() == before


def test_before_baseline_detail_is_skipped_for_later_confirmed_candidate(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        candidates = seed(queue)
        finish(queue, candidates[0], published=BASELINE - timedelta(seconds=1))
        target = finish(queue, candidates[1])
        permit = select_candidate_save(queue, DEFAULT_SCOPE, tmp_path / MANIFEST_NAME)
        assert permit.detail_attempt_id == target["attempt_id"]


def test_invalid_image_bearing_detail_does_not_silently_choose_another_post(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        candidates = seed(queue)
        bad = finish(queue, candidates[0])
        finish(queue, candidates[1])
        result = deepcopy(bad["result"])
        result["private_observation"]["snapshot"]["images"][0]["natural_width"] = 0
        queue.connection.execute(
            "UPDATE candidate_details SET result_json=? WHERE attempt_id=?",
            (json.dumps(result), bad["attempt_id"]),
        )
        with pytest.raises(QueueError, match="review"):
            select_candidate_save(queue, DEFAULT_SCOPE, tmp_path / MANIFEST_NAME)
        assert not (tmp_path / MANIFEST_NAME).exists()


def test_no_baseline_or_no_eligible_detail_creates_no_manifest(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        path = tmp_path / MANIFEST_NAME
        assert select_candidate_save(queue, DEFAULT_SCOPE, path) is None
        candidates = seed(queue)
        finish(queue, candidates[0], count=0)
        assert select_candidate_save(queue, DEFAULT_SCOPE, path) is None
        assert not path.exists()


def test_selection_must_stay_beside_its_database(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        seed(queue)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        with pytest.raises(QueueError, match="beside"):
            select_candidate_save(queue, DEFAULT_SCOPE, elsewhere / MANIFEST_NAME)
        assert not list(elsewhere.iterdir())


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(schema_version=True),
        lambda value: value.update(mode="foreign"),
        lambda value: value.update(evidence_sha256="not a digest"),
        lambda value: value.update(post_id="0101"),
        lambda value: value.update(detail_attempt_id="unknown"),
        lambda value: value.update(control={}),
        lambda value: value.update(control={"blocked": 1}),
        lambda value: value.update(control={"blocked": False, "finished_at": "relative"}),
        lambda value: value.update(control={"blocked": False, "interval_seconds": 60.0}),
        lambda value: value.update(control={"blocked": False, "http_status": 999}),
        lambda value: value["scope"].update(gallery_type=[]),
    ],
)
def test_malformed_existing_selection_is_preserved(tmp_path, mutation):
    queue, _, _, path, _ = selected(tmp_path)
    with queue:
        value = read_selection(path)
        mutation(value)
        path.write_text(json.dumps(value))
        before = path.read_bytes()
        with pytest.raises(QueueError):
            select_candidate_save(queue, DEFAULT_SCOPE, path)
        with pytest.raises(QueueError):
            selection_service_blocked(queue)
        assert path.read_bytes() == before


def test_control_updates_preserve_binding_and_explicit_block_is_global_and_not_auto_cleared(
    tmp_path,
):
    queue, _, _, path, _ = selected(tmp_path)
    with queue:
        before = read_selection(path)
        assert not selection_service_blocked(queue)
        control = {
            "blocked": True,
            "finished_at": NOW.isoformat(),
            "next_eligible_at": (NOW + timedelta(seconds=60)).isoformat(),
            "interval_seconds": 60,
            "http_status": 403,
        }
        write_selection_control(path, control)
        after = read_selection(path)
        assert {key: value for key, value in after.items() if key != "control"} == {
            key: value for key, value in before.items() if key != "control"
        }
        assert selection_service_blocked(queue)
        with QueueStore(tmp_path / "watch.sqlite", read_only=True) as other:
            assert selection_service_blocked(other)
        with pytest.raises(QueueError, match="manual"):
            write_selection_control(path, {"blocked": False})
        assert read_selection(path)["control"] == control


def test_service_block_read_with_no_manifest_does_not_create_one(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        assert not selection_service_blocked(queue)
        assert not (tmp_path / MANIFEST_NAME).exists()


def test_missing_control_target_and_nonpersistent_database_are_refused(tmp_path):
    with pytest.raises(QueueError, match="required"):
        write_selection_control(tmp_path / MANIFEST_NAME, {"blocked": True})
    with QueueStore(":memory:") as queue:
        with pytest.raises(QueueError, match="persisted"):
            selection_service_blocked(queue)


def test_duplicate_json_and_oversized_selection_are_refused_without_changes(tmp_path):
    path = tmp_path / MANIFEST_NAME
    for contents in (
        b'{"schema_version":1,"schema_version":1}',
        b" " * (MAX_SELECTION_BYTES + 1),
        b"\xff",
    ):
        path.write_bytes(contents)
        with pytest.raises(QueueError):
            read_selection(path)
        assert path.read_bytes() == contents


def test_symlink_or_directory_selection_is_refused_without_touching_target(tmp_path):
    path = tmp_path / MANIFEST_NAME
    target = tmp_path / "preserve.txt"
    target.write_text("Foreign contents")
    try:
        path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(QueueError):
        read_selection(path)
    assert target.read_text() == "Foreign contents"
    path.unlink()
    path.mkdir()
    with pytest.raises(QueueError, match="regular"):
        read_selection(path)


def test_failed_replace_preserves_original_and_cleans_only_owned_temporary(tmp_path, monkeypatch):
    queue, _, _, path, _ = selected(tmp_path)
    with queue:
        before = path.read_bytes()
        foreign = tmp_path / ".candidate-save-selection.foreign.tmp"
        foreign.write_text("preserve")

        def fail(*_):
            raise OSError("Synthetic publication failure")

        monkeypatch.setattr(selection.os, "replace", fail)
        with pytest.raises(OSError):
            write_selection_control(path, {"blocked": True})
        assert path.read_bytes() == before
        assert foreign.read_text() == "preserve"
        assert list(tmp_path.glob(f".{MANIFEST_NAME}.*.tmp")) == []


def test_preexisting_temporary_collision_is_preserved(tmp_path, monkeypatch):
    queue, _, _, path, _ = selected(tmp_path)
    with queue:
        token = "a" * 32
        foreign = tmp_path / f".{MANIFEST_NAME}.{token}.tmp"
        foreign.write_text("preserve")
        before = path.read_bytes()
        monkeypatch.setattr(selection.uuid, "uuid4", lambda: SimpleNamespace(hex=token))
        with pytest.raises(FileExistsError):
            write_selection_control(path, {"blocked": True})
        assert path.read_bytes() == before
        assert foreign.read_text() == "preserve"


def test_exclusive_first_publish_never_overwrites_a_new_foreign_destination(tmp_path, monkeypatch):
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        candidate = seed(queue)[0]
        finish(queue, candidate)
        path = tmp_path / MANIFEST_NAME
        method = "rename" if os.name == "nt" else "link"
        original = getattr(selection.os, method)

        def collide(source, destination, **options):
            Path(destination).write_text("Foreign contents")
            return original(source, destination, **options)

        monkeypatch.setattr(selection.os, method, collide)
        with pytest.raises(FileExistsError):
            select_candidate_save(queue, DEFAULT_SCOPE, path)
        assert path.read_text() == "Foreign contents"
        assert not list(tmp_path.glob(f".{MANIFEST_NAME}.*.tmp"))
