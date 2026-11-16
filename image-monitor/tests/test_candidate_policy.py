import copy
from datetime import UTC, datetime, timedelta

import pytest

from image_monitor.candidate_policy import CandidatePolicyError, classify_candidate_detail
from image_monitor.dcinside import HEADER_FIELD_COUNTS

BASELINE = {"observed_at": "2026-11-16T04:35:00+00:00"}
CANDIDATE = {
    "gallery_type": "normal",
    "gallery_id": "comic_new6",
    "post_id": "123",
    "post_url": "https://gall.dcinside.com/board/view/?id=comic_new6&no=123",
    "first_scan_id": "invented-scan",
    "first_seen_at": "2026-11-16T04:36:00+00:00",
    "shown_metadata": {"published_at_raw": "13:36", "requires_published_at_filter": True},
}


def snapshot(**overrides):
    return {
        **{key: CANDIDATE[key] for key in ("gallery_type", "gallery_id", "post_id", "post_url")},
        "observed_at": "2026-11-16T04:40:00+00:00",
        "title": "Invented private title",
        "nickname": "Invented private author",
        "published_at_raw": "2026.11.16 13:36:00",
        "published_at": "2026-11-16T13:36:00+09:00",
        "profile_evidence": {"header_count": 1, "header_field_counts": dict(HEADER_FIELD_COUNTS)},
        "layout_status": "unverified",
        "queue_eligible": False,
    } | overrides


def classify(observation=None, *, candidate=None, baseline=None):
    return classify_candidate_detail(
        CANDIDATE if candidate is None else candidate,
        BASELINE if baseline is None else baseline,
        snapshot() if observation is None else observation,
    )


@pytest.mark.parametrize(
    ("published", "expected"),
    [
        ("13:34:59", "before_baseline"),
        ("13:35:00", "at_or_after_baseline"),
        ("13:35:01", "at_or_after_baseline"),
    ],
)
def test_exact_time_comparison_includes_boundary_and_never_approves_saving(published, expected):
    result = classify(
        snapshot(
            published_at_raw=f"2026.11.16 {published}",
            published_at=f"2026-11-16T{published}+09:00",
        )
    )
    assert result["time_status"] == expected
    assert result["header_observed"] is True
    assert result["published_at"] == f"2026-11-16T{published}+09:00"
    assert result["queue_eligible"] is result["save_approved"] is False
    assert result["layout_status"] == "unverified"
    assert "Invented private" not in str(result)


def test_fractional_baseline_is_not_rounded_down_to_publication_second():
    result = classify(
        snapshot(published_at_raw="2026.11.16 13:35:00", published_at="2026-11-16T13:35:00+09:00"),
        baseline={"observed_at": "2026-11-16T04:35:00.000001+00:00"},
    )
    assert result["time_status"] == "before_baseline"


def test_equivalent_aware_timestamp_offsets_compare_as_instants():
    result = classify(snapshot(published_at="2026-11-16T04:36:00Z"))
    assert result["time_status"] == "at_or_after_baseline"
    assert result["published_at"] == "2026-11-16T13:36:00+09:00"


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (None, "published_at_missing"),
        ("", "published_at_missing"),
        ("13:36", "published_at_unrecognized"),
        ("11.16", "published_at_unrecognized"),
        ("2026.11.16 13:36", "published_at_unrecognized"),
        ("2026.02.30 13:36:00", "published_at_invalid"),
        (123, "published_at_unrecognized"),
    ],
)
def test_missing_or_relative_date_never_uses_list_time_or_first_seen(raw, reason):
    result = classify(snapshot(published_at_raw=raw))
    assert result["time_status"] == "unknown"
    assert result["reason"] == reason
    assert result["header_observed"] is True
    assert result["published_at"] is None


@pytest.mark.parametrize(
    "value", [None, "", "2026-11-16T13:36:00", "2026-11-16T13:36:00.000001+09:00", "invalid"]
)
def test_parsed_timestamp_must_be_aware_and_exactly_match_displayed_date(value):
    result = classify(snapshot(published_at=value))
    assert result["time_status"] == "unknown"
    assert result["reason"] == "publication_time_inconsistent"
    assert result["published_at"] is None


def test_future_publication_stays_unknown_with_confirmed_time_for_audit():
    result = classify(snapshot(observed_at="2026-11-16T04:35:59.999999+00:00"))
    assert result["time_status"] == "unknown"
    assert result["reason"] == "published_after_observation"
    assert result["published_at"] == "2026-11-16T13:36:00+09:00"


@pytest.mark.parametrize("value", [None, "invalid", "2026-11-16T04:40:00", True])
def test_unusable_observation_time_stays_unknown(value):
    result = classify(snapshot(observed_at=value))
    assert result["time_status"] == "unknown"
    assert result["reason"] == "observation_time_unavailable"


def test_observation_before_immutable_baseline_cannot_classify_a_candidate():
    result = classify(snapshot(observed_at="2026-11-16T04:34:59+00:00"))
    assert result["time_status"] == "unknown"
    assert result["reason"] == "observation_before_baseline"


@pytest.mark.parametrize(
    "evidence",
    [
        None,
        {},
        {"header_count": 0, "header_field_counts": HEADER_FIELD_COUNTS},
        {"header_count": 2, "header_field_counts": HEADER_FIELD_COUNTS},
        {"header_count": True, "header_field_counts": HEADER_FIELD_COUNTS},
        {"header_count": 1.0, "header_field_counts": HEADER_FIELD_COUNTS},
        {"header_count": 1, "header_field_counts": {}},
        {"header_count": 1, "header_field_counts": HEADER_FIELD_COUNTS | {".gall_date": 2}},
        {"header_count": 1, "header_field_counts": HEADER_FIELD_COUNTS | {".gall_date": True}},
        {"header_count": 1, "header_field_counts": HEADER_FIELD_COUNTS | {".gall_date": 1.0}},
        {"header_count": 1, "header_field_counts": HEADER_FIELD_COUNTS | {"extra": 1}},
    ],
)
def test_ambiguous_or_malformed_header_evidence_is_not_temporal_confirmation(evidence):
    result = classify(snapshot(profile_evidence=evidence))
    assert result["time_status"] == "unknown"
    assert result["reason"] == "header_unconfirmed"
    assert result["header_observed"] is False


@pytest.mark.parametrize("key", ["title", "nickname"])
@pytest.mark.parametrize("value", [None, "", " \t\n", 123])
def test_complete_nonblank_title_and_author_are_required(key, value):
    result = classify(snapshot(**{key: value}))
    assert result["time_status"] == "unknown"
    assert result["header_observed"] is False


@pytest.mark.parametrize("value", [None, {}, {"observed_at": None}, {"observed_at": "bad"}])
def test_missing_immutable_baseline_is_a_policy_precondition_error(value):
    with pytest.raises(CandidatePolicyError, match="baseline"):
        classify_candidate_detail(CANDIDATE, value, snapshot())


def test_naive_baseline_is_rejected_instead_of_assuming_a_timezone():
    with pytest.raises(CandidatePolicyError, match="baseline"):
        classify(baseline={"observed_at": "2026-11-16T04:35:00"})


@pytest.mark.parametrize("field", ["gallery_type", "gallery_id", "post_id", "post_url"])
@pytest.mark.parametrize("part", ["candidate", "snapshot"])
def test_identity_fields_must_match_their_validated_url(field, part):
    candidate = dict(CANDIDATE)
    observation = snapshot()
    value = {
        "gallery_type": "minor",
        "gallery_id": "other",
        "post_id": "124",
        "post_url": "https://gall.dcinside.com/board/view/?id=other&no=124",
    }[field]
    (candidate if part == "candidate" else observation)[field] = value
    with pytest.raises(CandidatePolicyError, match="identity"):
        classify_candidate_detail(candidate, BASELINE, observation)


@pytest.mark.parametrize(
    "url",
    [
        "http://gall.dcinside.com/board/view/?id=comic_new6&no=123",
        "https://gall.dcinside.com.evil.example/board/view/?id=comic_new6&no=123",
        "https://gall.dcinside.com/board/view/?id=comic_new6&no=123&no=123",
        "https://gall.dcinside.com/board/lists/?id=comic_new6&no=123",
        "https://gall.dcinside.com/board/view/?id=comic_new6&no=123#fragment",
    ],
)
def test_malformed_candidate_url_is_rejected_before_classification(url):
    with pytest.raises(CandidatePolicyError, match="URL"):
        classify(candidate=CANDIDATE | {"post_url": url})


def test_two_individually_valid_but_different_post_identities_are_rejected():
    observation = snapshot(
        post_id="124", post_url="https://gall.dcinside.com/board/view/?id=comic_new6&no=124"
    )
    with pytest.raises(CandidatePolicyError, match="does not match the candidate"):
        classify(observation)


@pytest.mark.parametrize("value", [None, [], "private external layout", "site_verified"])
def test_new_post_cannot_gain_verified_body_profile_from_temporal_confirmation(value):
    result = classify(snapshot(layout_status=value, queue_eligible=True))
    assert result["time_status"] == "at_or_after_baseline"
    assert result["layout_status"] == "unverified"
    assert result["queue_eligible"] is result["save_approved"] is False


def test_existing_reviewed_body_status_may_be_preserved_but_saving_stays_disabled():
    candidate = CANDIDATE | {
        "post_id": "7036949",
        "post_url": "https://gall.dcinside.com/board/view/?id=comic_new6&no=7036949",
    }
    observation = snapshot(
        post_id=candidate["post_id"],
        post_url=candidate["post_url"],
        layout_status="site_verified",
        queue_eligible=True,
    )
    result = classify_candidate_detail(candidate, BASELINE, observation)
    assert result["layout_status"] == "site_verified"
    assert result["queue_eligible"] is result["save_approved"] is False


def test_policy_does_not_mutate_inputs_or_create_side_effects():
    observation = snapshot()
    before = copy.deepcopy((CANDIDATE, BASELINE, observation))
    result = classify_candidate_detail(CANDIDATE, BASELINE, observation)
    assert (CANDIDATE, BASELINE, observation) == before
    assert set(result) == {
        "time_status",
        "reason",
        "header_observed",
        "published_at",
        "save_approved",
        "queue_eligible",
        "layout_status",
    }


def test_cross_day_seoul_timestamp_compares_against_utc_baseline():
    publication = datetime(2026, 11, 16, 15, 0, tzinfo=UTC)
    result = classify(
        snapshot(
            published_at_raw="2026.11.17 00:00:00",
            published_at=publication.isoformat(),
            observed_at=(publication + timedelta(seconds=1)).isoformat(),
        ),
        baseline={"observed_at": (publication - timedelta(seconds=1)).isoformat()},
    )
    assert result["time_status"] == "at_or_after_baseline"
