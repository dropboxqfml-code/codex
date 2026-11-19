"""Classify a frozen list candidate's publication time without approving saving."""

from datetime import UTC, datetime

from image_monitor.dcinside import (
    HEADER_FIELD_COUNTS,
    SITE_VERIFIED_POST,
    DCSnapshotError,
    _published,
    validate_post_url,
)


class CandidatePolicyError(ValueError):
    """Candidate identity or immutable baseline evidence is inconsistent."""


def unobserved_detail(reason):
    return {
        "time_status": "unknown",
        "reason": reason,
        "header_observed": False,
        "published_at": None,
        "layout_status": "unverified",
        "save_approved": False,
        "queue_eligible": False,
    }


def _identity(value, description):
    if not isinstance(value, dict):
        raise CandidatePolicyError(f"{description} identity is invalid")
    try:
        target = validate_post_url(value.get("post_url"))
    except DCSnapshotError as error:
        raise CandidatePolicyError(f"{description} URL is invalid") from error
    for key in ("gallery_type", "gallery_id", "post_id"):
        if not isinstance(value.get(key), str) or value[key] != target[key]:
            raise CandidatePolicyError(f"{description} identity does not match its URL")
    return target


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def _layout(snapshot, target):
    layout = snapshot.get("layout_status")
    if layout == "fixture_validated":
        return layout
    identity = tuple(target[key] for key in ("gallery_type", "gallery_id", "post_id"))
    if layout == "site_verified" and identity == SITE_VERIFIED_POST:
        return layout
    return "unverified"


def _header_observed(snapshot):
    evidence = snapshot.get("profile_evidence")
    if not isinstance(evidence, dict):
        return False
    counts = evidence.get("header_field_counts")
    return (
        type(evidence.get("header_count")) is int
        and evidence["header_count"] == 1
        and isinstance(counts, dict)
        and counts == HEADER_FIELD_COUNTS
        and all(type(value) is int for value in counts.values())
        and all(
            isinstance(snapshot.get(key), str) and bool(snapshot[key].strip())
            for key in ("title", "nickname")
        )
    )


def classify_candidate_detail(candidate: dict, state_baseline: dict, snapshot: dict) -> dict:
    """Compare exact, confirmed header time with an immutable aware baseline.

    Time acceptance does not verify a body profile, allow image jobs, or create
    a permanent folder plan. Missing or relative displayed dates stay unknown;
    list timestamps and first-seen time are never publication-time fallbacks.
    """
    target = _identity(candidate, "Candidate")
    observed_target = _identity(snapshot, "Snapshot")
    if target != observed_target:
        raise CandidatePolicyError("Snapshot identity does not match the candidate")
    baseline = (
        _timestamp(state_baseline.get("observed_at")) if isinstance(state_baseline, dict) else None
    )
    if baseline is None:
        raise CandidatePolicyError("An aware immutable watch baseline is required")
    result = {
        "time_status": "unknown",
        "reason": "header_unconfirmed",
        "header_observed": _header_observed(snapshot),
        "published_at": None,
        "save_approved": False,
        "queue_eligible": False,
        "layout_status": _layout(snapshot, target),
    }
    if not result["header_observed"]:
        return result
    observed = _timestamp(snapshot.get("observed_at"))
    if observed is None:
        return result | {"reason": "observation_time_unavailable"}
    if observed < baseline:
        return result | {"reason": "observation_before_baseline"}
    parsed, parse_reason = _published(snapshot.get("published_at_raw"))
    if parsed is None:
        return result | {"reason": parse_reason}
    published = _timestamp(snapshot.get("published_at"))
    raw_published = _timestamp(parsed)
    if published is None or published != raw_published:
        return result | {"reason": "publication_time_inconsistent"}
    result["published_at"] = parsed
    if published > observed:
        return result | {"reason": "published_after_observation"}
    if published < baseline:
        return result | {"time_status": "before_baseline", "reason": "published_before_baseline"}
    return result | {
        "time_status": "at_or_after_baseline",
        "reason": "published_at_or_after_baseline",
    }
