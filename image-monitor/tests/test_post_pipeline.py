import json
import sys
from datetime import UTC, datetime

import pytest

from image_monitor.__main__ import main
from image_monitor.dcinside import parse_snapshot
from image_monitor.post_commands import fixture_raw, post_demo
from image_monitor.post_pipeline import (
    PostPipelineError,
    enqueue_candidate_snapshot,
    enqueue_snapshot,
)
from image_monitor.queue import QueueStore


def test_post_demo_keeps_attachment_evidence_and_unique_jobs_after_reopen(tmp_path):
    database = tmp_path / "post.sqlite"
    result = post_demo(database)
    assert result["synthetic_only"] is True
    assert result["browser_started"] is result["native_save_started"] is False
    assert result["files_downloaded"] == 0
    assert len(result["jobs"]) == 3
    images = result["snapshot"]["images"]
    assert images[0]["occurrences"] == [1, 4]
    assert images[0]["original_attachment_filename"] == "첫째.png"
    assert images[1]["original_attachment_filename"] == "둘째.gif"
    assert images[2]["original_attachment_filename"] is None
    assert images[2]["original_filename_match_status"] == "ambiguous"
    assert len(result["snapshot"]["attachment_inventory"]) == 3
    with QueueStore(database, read_only=True) as store:
        assert len(store.list_jobs()) == 3
        assert (
            store.get_checkpoint(
                "합성 본문 시험", "normal", "monitor_fixture", "synthetic", "search_subject_memo"
            )
            is None
        )
        post = store.get_post("normal", "monitor_fixture", "1")
        assert post["folder_plan"]["folder_date"] == "2026-11-14"


def test_unverified_live_layout_never_enters_save_queue(tmp_path):
    snapshot = parse_snapshot(
        fixture_raw(),
        expected_url="https://gall.dcinside.com/board/view/?id=monitor_fixture&no=1",
        observed_at=datetime.now(UTC),
        layout_status="unverified",
    )
    with QueueStore(tmp_path / "queue.sqlite") as store:
        with pytest.raises(PostPipelineError, match="not eligible"):
            enqueue_snapshot(store, snapshot, watch_name="watch", keyword="ai")
        assert store.list_jobs() == []
        assert store.get_post("normal", "monitor_fixture", "1") is None


def test_fixture_observation_requires_explicit_synthetic_mode(tmp_path):
    snapshot = parse_snapshot(
        fixture_raw(),
        expected_url="https://gall.dcinside.com/board/view/?id=monitor_fixture&no=1",
        observed_at=datetime.now(UTC),
        layout_status="fixture_validated",
    )
    with QueueStore(tmp_path / "queue.sqlite") as store:
        with pytest.raises(PostPipelineError, match="explicit fixture mode"):
            enqueue_snapshot(store, snapshot, watch_name="watch", keyword="ai")
        assert store.list_jobs() == []


def test_candidate_queue_requires_explicit_permit_and_preserves_original_discovery(tmp_path):
    from test_post_worker import candidate_observation, candidate_permit

    snapshot = candidate_observation(count=2)
    permit = candidate_permit(snapshot)
    authorized = permit.authorize_snapshot(snapshot)
    with QueueStore(tmp_path / "queue.sqlite") as store:
        with pytest.raises(PostPipelineError, match="unverified site layout"):
            enqueue_snapshot(store, authorized, watch_name="manual", keyword="manual")
        assert store.list_jobs() == []
        queued = enqueue_candidate_snapshot(store, authorized, permit=permit)
        assert len(queued["jobs"]) == 2
        assert len(store.list_jobs()) == 2
        post = store.get_post("normal", "comic_new6", snapshot["post_id"])
        assert datetime.fromisoformat(post["first_seen_at"]) == permit.first_seen_at
        assert post["folder_plan"]["folder_date"] == "2026-11-14"
        assert post["watch_name"] == permit.watch_name
        match = store.connection.execute("SELECT * FROM matches").fetchone()
        assert (match["keyword"], match["search_type"]) == (permit.keyword, permit.search_type)
        observation = store.get_observation(queued["observation_id"])
        assert observation["snapshot"]["layout_status"] == "candidate_reviewed"
        assert all(
            image["original_attachment_filename"] is None
            and image["original_filename_match_status"] == "ambiguous"
            for image in observation["snapshot"]["images"]
        )
        repeated = enqueue_candidate_snapshot(store, snapshot, permit=permit)
        assert [job["job_id"] for job in repeated["jobs"]] == [
            job["job_id"] for job in queued["jobs"]
        ]
        assert len(store.list_jobs()) == 2


def test_candidate_queue_refuses_missing_permit_and_changed_sources_without_writes(tmp_path):
    from test_post_worker import candidate_observation, candidate_permit

    from image_monitor.candidate_save_policy import CandidateSavePolicyError

    snapshot = candidate_observation()
    permit = candidate_permit(snapshot)
    with QueueStore(tmp_path / "queue.sqlite") as store:
        with pytest.raises(PostPipelineError, match="permit"):
            enqueue_candidate_snapshot(store, snapshot, permit=object())
        changed = candidate_observation()
        changed["images"][0]["display_url"] += "?changed=1"
        with pytest.raises(CandidateSavePolicyError):
            enqueue_candidate_snapshot(store, changed, permit=permit)
        assert store.summary()["posts"] == 0 and store.list_jobs() == []


def test_post_demo_cli_outputs_durable_jobs_without_overwriting_database(
    tmp_path, monkeypatch, capsys
):
    database = tmp_path / "post.sqlite"
    monkeypatch.setattr(sys, "argv", ["image-monitor", "post-demo", "--db", str(database)])
    assert main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["files_downloaded"] == 0 and len(output["jobs"]) == 3
    before = database.read_bytes()
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert database.read_bytes() == before


def test_site_inspection_cli_shares_only_sanitized_failure_report(tmp_path, monkeypatch, capsys):
    from image_monitor import site_inspection

    monkeypatch.setattr(
        site_inspection,
        "run_site_inspection",
        lambda *_args, **_kwargs: {
            "status": "inspection_failed",
            "report_path": "C:/private/report.json",
            "diagnostics": {"url": "https://cdn.example/image.png?token=secret"},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["image-monitor", "site-inspect", "--work-root", str(tmp_path), "--browser", "chrome"],
    )
    assert main() == 2
    output = capsys.readouterr().out
    assert "inspection_failed" in output
    assert "secret" not in output and "C:/private" not in output
    assert not list(tmp_path.iterdir())


def test_site_inspection_non_windows_cli_has_no_filesystem_side_effects(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(sys, "platform", "linux")
    root = tmp_path / "not_created"
    monkeypatch.setattr(sys, "argv", ["image-monitor", "site-inspect", "--work-root", str(root)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert not root.exists()
    assert "NativeUIError" in capsys.readouterr().err
