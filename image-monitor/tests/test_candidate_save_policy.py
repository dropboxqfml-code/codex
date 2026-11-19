"""Freeze one completed detail without expanding the generic save profile."""

import copy
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from image_monitor.candidate_policy import classify_candidate_detail, unobserved_detail
from image_monitor.candidate_save_policy import (
    CandidateSavePermit,
    CandidateSavePolicyError,
    classify_stored_candidate_image,
    make_candidate_save_permit,
)
from image_monitor.dcinside import HEADER_FIELD_COUNTS, SITE_VERIFIED_POST, parse_snapshot

NOW = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)


def candidate_evidence(*, image_count=2, excluded=False):
    """Invented identities and ordinary parser output, never a user's snapshot."""
    candidate = {
        "watch_name": "검색 감시 시험",
        "gallery_type": "normal",
        "gallery_id": "comic_new6",
        "keyword": "ai",
        "search_type": "search_subject_memo",
        "post_id": "103",
        "post_url": "https://gall.dcinside.com/board/view/?id=comic_new6&no=103",
        "first_scan_id": "a" * 32,
        "first_seen_at": (NOW - timedelta(seconds=120)).isoformat(),
        "last_seen_at": (NOW - timedelta(seconds=100)).isoformat(),
        "title": "Invented list title",
        "latest_scan_id": "c" * 32,
        "shown_metadata": {"invented": True},
    }
    baseline = {"observed_at": (NOW - timedelta(seconds=600)).isoformat(), "mode": "new"}
    raw = {
        "body_count": 1,
        "header_count": 1,
        "header_field_counts": HEADER_FIELD_COUNTS.copy(),
        "title": "Invented inspected title",
        "nickname": "Invented author",
        "ip_display": "123.45",
        "published_at_raw": (NOW - timedelta(seconds=60))
        .astimezone(ZoneInfo("Asia/Seoul"))
        .strftime("%Y.%m.%d %H:%M:%S"),
        "inventory_total": 1,
        "attachments": [
            {
                "key": "invented-attachment",
                "filename": "invented.png",
                "filename_complete": True,
                "reference_url": "https://image.dcinside.com/download.php?no=invented",
            }
        ],
        "images": [
            {
                "body_order": order,
                "display_url": f"https://images.example/invented-{order}.png",
                "excluded_reason": None,
                "decode_ok": True,
                "complete": True,
                "natural_width": 96,
                "natural_height": 64,
            }
            for order in range(1, image_count + 1)
        ],
        "diagnostics": {"counts": {".write_div": 1, ".gallview_head": 1}},
    }
    if excluded:
        raw["images"].append(
            {
                "body_order": image_count + 1,
                "display_url": "https://dccon.dcinside.com/invented.png",
                "excluded_reason": "body_dccon",
            }
        )
    snapshot = parse_snapshot(
        raw,
        expected_url=candidate["post_url"],
        observed_at=NOW - timedelta(seconds=1),
        layout_status="unverified",
    )
    detail = {
        "attempt_id": "b" * 32,
        **{
            key: candidate[key]
            for key in (
                "watch_name",
                "gallery_type",
                "gallery_id",
                "keyword",
                "search_type",
                "post_id",
                "first_scan_id",
            )
        },
        "baseline_observed_at": baseline["observed_at"],
        "started_at": (NOW - timedelta(seconds=10)).isoformat(),
        "finished_at": NOW.isoformat(),
        "status": "completed",
        "result": {
            "classification": classify_candidate_detail(candidate, baseline, snapshot),
            "private_observation": {
                "status": "observed",
                "http_status": 200,
                "url": candidate["post_url"],
                "navigation_attempts": 1,
                "snapshot": snapshot,
            },
            "control": {
                "blocked": False,
                "http_status": 200,
                "finished_at": NOW.isoformat(),
                "interval_seconds": 60,
                "next_eligible_at": (NOW + timedelta(seconds=60)).isoformat(),
            },
        },
    }
    return candidate, baseline, detail


def snapshot_from(detail):
    return detail["result"]["private_observation"]["snapshot"]


@pytest.mark.parametrize(
    ("count", "excluded", "expected"),
    [
        (0, False, "no_body_images_observed"),
        (0, True, "excluded_body_images_only"),
        (1, False, "save_ready"),
        (2, True, "save_ready"),
        (3, False, "outside_save_limit"),
    ],
)
def test_search_classifies_only_observed_body_elements(count, excluded, expected):
    evidence = candidate_evidence(image_count=count, excluded=excluded)
    snapshot = snapshot_from(evidence[2])
    assert len(snapshot["attachment_inventory"]) == 1
    assert snapshot["layout_status"] == "unverified"
    outcome, permit = classify_stored_candidate_image(*evidence)
    assert outcome == expected
    if outcome == "save_ready":
        assert permit == make_candidate_save_permit(*evidence)
    else:
        assert permit is None
        with pytest.raises(CandidateSavePolicyError):
            make_candidate_save_permit(*evidence)


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s["image_counts"].update(body_occurrences=1),
        lambda s: s["image_counts"].update(pending=False),
        lambda s: s.update(pending_images=[{"reason": "image_not_loaded"}]),
        lambda s: s.pop("images"),
        lambda s: s["diagnostics"]["counts"].update({".write_div": 2}),
        lambda s: s["diagnostics"].update(image_shapes=[{"tag": "IMG"}]),
        lambda s: s.update(post_url="https://gall.dcinside.com/board/view/?id=comic_new6&no=7"),
    ],
)
def test_search_keeps_conflicting_empty_body_evidence_for_review(change):
    evidence = candidate_evidence(image_count=0)
    change(snapshot_from(evidence[2]))
    assert classify_stored_candidate_image(*evidence) == ("needs_review", None)


def test_search_reviews_an_unresolved_image_even_when_over_the_save_limit():
    evidence = candidate_evidence(image_count=3)
    snapshot_from(evidence[2])["images"][-1]["natural_width"] = 0
    assert classify_stored_candidate_image(*evidence) == ("needs_review", None)


def unavailable_evidence(code):
    candidate, baseline, detail = candidate_evidence()
    result = detail["result"]
    observation = result["private_observation"]
    del observation["snapshot"]
    observation.update(status="http_error", error_type="HTTPStatusError", http_status=code)
    result["control"]["http_status"] = code
    result["classification"] = unobserved_detail("candidate_unavailable")
    return candidate, baseline, detail


@pytest.mark.parametrize("code", [404, 410])
def test_search_skips_a_confirmed_unavailable_candidate_without_saving(code):
    evidence = unavailable_evidence(code)
    assert classify_stored_candidate_image(*evidence) == ("unavailable", None)
    with pytest.raises(CandidateSavePolicyError):
        make_candidate_save_permit(*evidence)


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r["control"].update(blocked=True),
        lambda r: r["control"].update(http_status=410),
        lambda r: r["private_observation"].update(
            url="https://gall.dcinside.com/board/view/?id=comic_new6&no=7"
        ),
        lambda r: r["private_observation"].update(navigation_attempts=2),
        lambda r: r["private_observation"].update(status="network_error"),
        lambda r: r["private_observation"].update(snapshot={}),
        lambda r: r["classification"].update(reason="detail_inspection_failed"),
    ],
)
def test_search_keeps_unproven_unavailability_for_review(change):
    evidence = unavailable_evidence(404)
    change(evidence[2]["result"])
    assert classify_stored_candidate_image(*evidence) == ("needs_review", None)


@pytest.mark.parametrize("code", [403, 429, 500, 503])
def test_other_response_errors_cannot_skip_a_candidate(code):
    assert classify_stored_candidate_image(*unavailable_evidence(code)) == ("needs_review", None)


def test_search_uses_recomputed_publication_time_before_skipping_a_post():
    candidate, baseline, detail = candidate_evidence()
    snapshot = snapshot_from(detail)
    published = (NOW - timedelta(days=1)).astimezone(ZoneInfo("Asia/Seoul"))
    snapshot.update(
        published_at=published.isoformat(), published_at_raw=published.strftime("%Y.%m.%d %H:%M:%S")
    )
    assert classify_stored_candidate_image(candidate, baseline, detail) == ("needs_review", None)
    detail["result"]["classification"] = classify_candidate_detail(candidate, baseline, snapshot)
    assert classify_stored_candidate_image(candidate, baseline, detail) == ("before_baseline", None)
    with pytest.raises(CandidateSavePolicyError):
        make_candidate_save_permit(candidate, baseline, detail)


def test_one_detail_permit_preserves_url_identity_and_ambiguous_names():
    candidate, baseline, detail = candidate_evidence()
    before = copy.deepcopy((candidate, baseline, detail))
    permit = make_candidate_save_permit(candidate, baseline, detail)
    fresh = copy.deepcopy(snapshot_from(detail))
    fresh["observed_at"] = (NOW + timedelta(seconds=1)).isoformat()
    approved = permit.authorize_snapshot(fresh)

    assert approved["layout_status"] == "candidate_reviewed"
    assert approved["queue_eligible"] is True
    assert approved["profile_evidence"]["queue_validation"] == "reviewed_candidate_permit"
    assert approved["profile_evidence"]["pilot_scope"]["permit_fingerprint"] == permit.fingerprint
    assert all(image["stable_key"].startswith("urlsha256:") for image in approved["images"])
    assert all(
        image["original_filename_match_status"] == "ambiguous" for image in approved["images"]
    )
    assert all(image["original_attachment_filename"] is None for image in approved["images"])
    assert permit.image_count == 2
    assert permit.detail_attempt_id == detail["attempt_id"]
    assert permit.first_seen_at == datetime.fromisoformat(candidate["first_seen_at"])
    assert (candidate, baseline, detail) == before
    assert fresh["layout_status"] == "unverified" and not fresh["queue_eligible"]
    assert SITE_VERIFIED_POST == ("normal", "comic_new6", "7036949")


def test_authorizing_own_output_is_idempotent_and_returns_independent_metadata():
    candidate, baseline, detail = candidate_evidence()
    permit = make_candidate_save_permit(candidate, baseline, detail)
    first = permit.authorize_snapshot(snapshot_from(detail))
    second = permit.authorize_snapshot(first)
    assert second == first
    second["images"][0]["display_url"] = "https://unrelated.example/changed.png"
    assert (
        permit.reference_snapshot["images"][0]["display_url"] != second["images"][0]["display_url"]
    )
    reference = permit.reference_snapshot
    reference["title"] = "Changed copy"
    assert permit.reference_snapshot["title"] != "Changed copy"


def test_mutating_source_records_cannot_change_the_frozen_permit():
    candidate, baseline, detail = candidate_evidence()
    permit = make_candidate_save_permit(candidate, baseline, detail)
    fingerprint = permit.fingerprint
    candidate["post_id"] = "104"
    baseline["observed_at"] = NOW.isoformat()
    snapshot_from(detail)["title"] = "Edited source dictionary"
    assert permit.fingerprint == fingerprint
    assert permit.reference_snapshot["post_id"] == "103"
    with pytest.raises(FrozenInstanceError):
        permit._payload_json = "{}"


def test_list_refresh_metadata_does_not_change_the_permit_fingerprint():
    candidate, baseline, detail = candidate_evidence()
    first = make_candidate_save_permit(candidate, baseline, detail)
    candidate.update(
        title="New list title",
        last_seen_at=NOW.isoformat(),
        latest_scan_id="d" * 32,
        shown_metadata={"changed": True},
    )
    assert make_candidate_save_permit(candidate, baseline, detail).fingerprint == first.fingerprint


@pytest.mark.parametrize("count", [0, 3])
def test_pilot_rejects_zero_or_more_than_two_images(count):
    with pytest.raises(CandidateSavePolicyError):
        make_candidate_save_permit(*candidate_evidence(image_count=count))


@pytest.mark.parametrize(
    "change",
    [
        lambda c, b, d: c.update(watch_name="Other watch"),
        lambda c, b, d: c.update(keyword="other"),
        lambda c, b, d: c.update(post_id="104"),
        lambda c, b, d: c.update(post_url=c["post_url"] + "&page=2"),
        lambda c, b, d: c.update(first_scan_id="d" * 32),
        lambda c, b, d: c.update(first_seen_at=(NOW - timedelta(seconds=601)).isoformat()),
        lambda c, b, d: b.update(observed_at=NOW.isoformat()),
        lambda c, b, d: d.update(status="started"),
        lambda c, b, d: d.update(post_id="104"),
        lambda c, b, d: d.update(attempt_id="not-a-detail-id"),
        lambda c, b, d: d.update(finished_at=d["started_at"]),
        lambda c, b, d: d["result"]["control"].update(blocked=True),
        lambda c, b, d: d["result"]["control"].update(blocked=0),
        lambda c, b, d: d["result"]["control"].update(interval_seconds=59),
        lambda c, b, d: d["result"]["private_observation"].update(http_status=403),
        lambda c, b, d: d["result"]["private_observation"].update(status="inspection_error"),
        lambda c, b, d: d["result"]["private_observation"].update(navigation_attempts=2),
        lambda c, b, d: d["result"]["classification"].update(time_status="unknown"),
        lambda c, b, d: snapshot_from(d)["diagnostics"]["counts"].update({".write_div": 2}),
        lambda c, b, d: snapshot_from(d)["profile_evidence"].update(header_count=2),
        lambda c, b, d: snapshot_from(d)["image_counts"].update(pending=1),
        lambda c, b, d: snapshot_from(d)["images"][0].update(stable_key="resource:invented"),
        lambda c, b, d: snapshot_from(d)["images"][0].update(
            original_attachment_filename="guessed.png"
        ),
    ],
)
def test_incomplete_or_conflicting_stored_evidence_cannot_create_a_permit(change):
    candidate, baseline, detail = candidate_evidence()
    change(candidate, baseline, detail)
    with pytest.raises(CandidateSavePolicyError):
        make_candidate_save_permit(candidate, baseline, detail)


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.update(title="Changed title"),
        lambda s: s.update(nickname="Changed author"),
        lambda s: s.update(ip_display=None),
        lambda s: s.update(published_at_raw="2026.11.16 17:59:01"),
        lambda s: s.update(post_id="104"),
        lambda s: s.update(observed_at=(NOW - timedelta(seconds=2)).isoformat()),
        lambda s: s["diagnostics"]["counts"].update({".gallview_head": 0}),
        lambda s: s["image_counts"].update(included_unique=1),
        lambda s: s["images"].pop(),
        lambda s: s["images"].reverse(),
        lambda s: s["images"][0].update(display_url="https://images.example/new.png"),
        lambda s: s["images"][0].update(natural_width=97),
        lambda s: s["images"][0].update(occurrences=[1, 3]),
        lambda s: s["images"][0].update(body_order=True),
        lambda s: s["images"][0].update(original_filename_match_status=[]),
        lambda s: s["pending_images"].append({"body_order": 3, "reason": "image_not_loaded"}),
    ],
)
def test_changed_current_document_is_not_authorized(change):
    candidate, baseline, detail = candidate_evidence()
    permit = make_candidate_save_permit(candidate, baseline, detail)
    fresh = copy.deepcopy(snapshot_from(detail))
    change(fresh)
    with pytest.raises(CandidateSavePolicyError):
        permit.authorize_snapshot(fresh)


def test_excluded_occurrence_must_stay_exact_and_cannot_become_an_image():
    candidate, baseline, detail = candidate_evidence(excluded=True)
    permit = make_candidate_save_permit(candidate, baseline, detail)
    fresh = copy.deepcopy(snapshot_from(detail))
    assert permit.authorize_snapshot(fresh)["excluded_images"] == fresh["excluded_images"]
    fresh["excluded_images"][0]["display_url"] += "?changed=1"
    with pytest.raises(CandidateSavePolicyError, match="exclusions changed"):
        permit.authorize_snapshot(fresh)


@pytest.mark.parametrize(
    "payload", [None, "{}", "[]", '{"candidate":NaN}', "x" * (4 * 1024 * 1024 + 1)]
)
def test_manual_permit_construction_still_requires_valid_bounded_canonical_evidence(payload):
    with pytest.raises(CandidateSavePolicyError):
        CandidateSavePermit(payload)


def test_valid_canonical_payload_round_trip_still_validates_before_use():
    permit = make_candidate_save_permit(*candidate_evidence())
    restored = CandidateSavePermit(permit._payload_json)
    restored.validate()
    assert restored.fingerprint == permit.fingerprint
    assert json.loads(restored._payload_json)["candidate"]["post_id"] == "103"
