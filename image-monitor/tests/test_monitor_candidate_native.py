"""Carry a persisted monitor candidate through the real owned Windows saver.

The existing native fixture driver owns the browser, menu, Save As dialog and
completion proof. This case changes its evidence source to the monitor's
separate durable selection and checks that older trial data remains intact.
"""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

import test_windows_candidate_save as candidate_native
from test_candidate_save_selection import evidence, selected

from image_monitor import candidate_save_selection
from image_monitor.candidate_policy import classify_candidate_detail
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_controller import MONITOR_SCOPE
from image_monitor.paths import component
from image_monitor.queue import QueueStore
from image_monitor.watch_store import WatchStore

pytestmark = candidate_native.pytestmark


def _freeze_monitor_candidate(watch_root, snapshot):
    """Persist the actual fixture DOM as a completed monitor detail observation."""
    observed = datetime.fromisoformat(snapshot["observed_at"])
    published = datetime.fromisoformat(snapshot["published_at"])
    baseline_at = published - timedelta(minutes=1)
    first_seen = baseline_at + timedelta(seconds=10)
    baseline = {
        "mode": "new",
        "observed_at": baseline_at.isoformat(),
        "anchor_ids": ["900000000"],
        "requires_published_at_filter": True,
    }
    with QueueStore(watch_root / "watch.sqlite") as queue:
        watch = WatchStore(queue)
        watch.persist_scan(
            MONITOR_SCOPE,
            observed_at=baseline_at,
            expected_generation=0,
            scan_result={"mode": "owned_monitor_fixture", "queue_eligible": False},
            candidates=[],
            checkpoint=baseline,
            complete=True,
            baseline=baseline,
        )
        watch.persist_scan(
            MONITOR_SCOPE,
            observed_at=first_seen,
            expected_generation=1,
            scan_result={"mode": "owned_monitor_fixture", "queue_eligible": False},
            candidates=[
                {
                    "post_id": snapshot["post_id"],
                    "post_url": snapshot["post_url"],
                    "title": "Invented monitor candidate",
                    "shown_metadata": {"requires_published_at_filter": True},
                }
            ],
            checkpoint=baseline | {"anchor_ids": [snapshot["post_id"], "900000000"]},
            complete=True,
        )
        candidate = watch.list_candidates(MONITOR_SCOPE)[0]
        details = CandidateDetailStore(queue)
        attempt = details.start(
            MONITOR_SCOPE,
            candidate["post_id"],
            expected_first_scan_id=candidate["first_scan_id"],
            baseline_observed_at=baseline_at,
            started_at=observed - timedelta(seconds=5),
        )
        finished = observed + timedelta(seconds=1)
        details.finish(
            attempt["attempt_id"],
            finished_at=finished,
            result={
                "classification": classify_candidate_detail(candidate, baseline, snapshot),
                "private_observation": {
                    "status": "observed",
                    "http_status": 200,
                    "url": snapshot["post_url"],
                    "navigation_attempts": 1,
                    "snapshot": snapshot,
                },
                "control": {
                    "blocked": False,
                    "http_status": 200,
                    "finished_at": finished.isoformat(),
                    "next_eligible_at": (finished + timedelta(seconds=60)).isoformat(),
                    "interval_seconds": 60,
                },
            },
        )
        path = watch_root / candidate_save_selection.selection_manifest_name(MONITOR_SCOPE)
        permit = candidate_save_selection.select_candidate_save(queue, MONITOR_SCOPE, path)
        assert permit is not None and permit.image_count == 1
        assert permit.watch_name == MONITOR_SCOPE.watch_name
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0
        return permit, first_seen


def test_owned_monitor_candidate_saves_once_and_preserves_trial_selection(tmp_path, monkeypatch):
    watch_root = tmp_path / "watch"
    watch_root.mkdir()
    queue, _, _, legacy_manifest, _ = selected(watch_root)
    with queue:
        prior_trial = evidence(queue)
    prior_manifest = legacy_manifest.read_bytes()
    legacy_output = tmp_path / "legacy-output" / "previous-file.png"
    legacy_output.parent.mkdir()
    legacy_output.write_bytes(b"Invented earlier trial output, preserved verbatim")
    previous_output = legacy_output.read_bytes()

    frozen = []
    monitor_records = []
    native_calls = []
    finalized = []
    real_enqueue = candidate_native.enqueue_candidate_snapshot
    real_finalize = candidate_native.finalize_saved_image
    real_native_save = candidate_native.native_body.save_body_image

    def freeze(snapshot):
        permit, first_seen = _freeze_monitor_candidate(watch_root, snapshot)
        frozen.append(permit)
        with QueueStore(watch_root / "watch.sqlite", read_only=True) as queue:
            watch = WatchStore(queue)
            monitor_records.append(
                (
                    watch.get_state(MONITOR_SCOPE),
                    watch.list_candidates(MONITOR_SCOPE),
                    watch.list_scans(MONITOR_SCOPE),
                    watch.list_gaps(MONITOR_SCOPE),
                    CandidateDetailStore(queue).list_details(MONITOR_SCOPE),
                )
            )
        return permit, first_seen

    def enqueue(store, snapshot, *, permit):
        assert permit.watch_name == MONITOR_SCOPE.watch_name
        result = real_enqueue(store, snapshot, permit=permit)
        assert len(result["jobs"]) == 1
        job = result["jobs"][0]
        assert PurePosixPath(job["folder_plan"]["relative_directory"]).parts[0] == component(
            MONITOR_SCOPE.watch_name
        )
        assert store.get_post("normal", "comic_new6", snapshot["post_id"])["watch_name"] == (
            MONITOR_SCOPE.watch_name
        )
        return result

    def native_save(*args, **kwargs):
        native_calls.append(1)
        return real_native_save(*args, **kwargs)

    def finalize(*args, **kwargs):
        artifact = real_finalize(*args, **kwargs)
        image = Path(artifact["final_path"])
        metadata = json.loads(Path(artifact["metadata_path"]).read_bytes())
        assert artifact["phase"] == "finalized" and image.name == "001.png"
        assert image.relative_to(kwargs["save_root"]).parts[0] == component(
            MONITOR_SCOPE.watch_name
        )
        assert PurePosixPath(metadata["folder_plan"]["relative_directory"]).parts[0] == component(
            MONITOR_SCOPE.watch_name
        )
        finalized.append(hashlib.sha256(image.read_bytes()).hexdigest())
        return artifact

    monkeypatch.setattr(candidate_native, "frozen_candidate_permit", freeze)
    monkeypatch.setattr(candidate_native, "enqueue_candidate_snapshot", enqueue)
    monkeypatch.setattr(candidate_native, "finalize_saved_image", finalize)
    monkeypatch.setattr(candidate_native.native_body, "save_body_image", native_save)
    candidate_native.test_owned_candidate_permit_saves_ambiguous_name_as_generic_png_without_resaving(
        monkeypatch
    )

    assert len(frozen) == len(native_calls) == len(finalized) == 1
    monitor_manifest = watch_root / candidate_save_selection.selection_manifest_name(MONITOR_SCOPE)
    assert monitor_manifest != legacy_manifest and monitor_manifest.is_file()
    assert legacy_manifest.read_bytes() == prior_manifest
    assert legacy_output.read_bytes() == previous_output
    with QueueStore(watch_root / "watch.sqlite", read_only=True) as queue:
        assert evidence(queue) == prior_trial
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0
        assert len(CandidateDetailStore(queue).list_details(MONITOR_SCOPE)) == 1
        watch = WatchStore(queue)
        assert (
            watch.get_state(MONITOR_SCOPE),
            watch.list_candidates(MONITOR_SCOPE),
            watch.list_scans(MONITOR_SCOPE),
            watch.list_gaps(MONITOR_SCOPE),
            CandidateDetailStore(queue).list_details(MONITOR_SCOPE),
        ) == monitor_records[0]
        repeated = candidate_save_selection.select_candidate_save(
            queue, MONITOR_SCOPE, monitor_manifest
        )
        assert repeated.fingerprint == frozen[0].fingerprint
