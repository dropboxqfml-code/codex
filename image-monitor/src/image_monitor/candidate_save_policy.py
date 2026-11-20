"""An explicit, immutable permit for one previously inspected candidate post."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from image_monitor.candidate_policy import (
    CandidatePolicyError,
    classify_candidate_detail,
    unobserved_detail,
)
from image_monitor.dcinside import _shared_no_identity, validate_post_url

MAX_PERMIT_BYTES = 4 * 1024 * 1024
MAX_SAVE_IMAGES = 2
MAX_MONITOR_SAVE_IMAGES = 10
REVIEWED_SCOPE = ("검색 감시 시험", "normal", "comic_new6", "ai", "search_subject_memo")
MONITOR_SCOPE = ("목록 감시", "normal", "comic_new6", "ai", "search_subject_memo")
SCOPE_FIELDS = ("watch_name", "gallery_type", "gallery_id", "keyword", "search_type")
_HEADER_FIELDS = ("title", "nickname", "ip_display", "published_at_raw")
_EXCLUSION_REASONS = {
    "body_dccon",
    "comment_content",
    "irrelevant_body_content",
    "video_content",
}


class CandidateSavePolicyError(ValueError):
    """The stored observation or current document does not prove this permit."""


def _require(condition, reason):
    if not condition:
        raise CandidateSavePolicyError(reason)


def _canonical(value):
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as error:
        raise CandidateSavePolicyError("Candidate permit metadata is invalid") from error
    _require(
        len(encoded.encode("utf-8")) <= MAX_PERMIT_BYTES,
        "Candidate permit metadata exceeds its limit",
    )
    return encoded


def _time(value):
    try:
        _require(isinstance(value, str), "An aware candidate timestamp is required")
        instant = datetime.fromisoformat(value)
        _require(
            instant.tzinfo is not None and instant.utcoffset() is not None,
            "An aware candidate timestamp is required",
        )
        return instant.astimezone(UTC)
    except (ValueError, OverflowError) as error:
        raise CandidateSavePolicyError("Candidate timing is invalid") from error


def _uuid(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def _image_limit(candidate):
    # _confirmed_detail requires the candidate and detail to share a known scope.
    scope = tuple(candidate[key] for key in SCOPE_FIELDS)
    return MAX_MONITOR_SAVE_IMAGES if scope == MONITOR_SCOPE else MAX_SAVE_IMAGES


def _image_signature(snapshot):
    _require(isinstance(snapshot, dict), "A candidate snapshot is required")
    diagnostics = snapshot.get("diagnostics")
    _require(
        isinstance(diagnostics, dict) and isinstance(diagnostics.get("counts"), dict),
        "Candidate body evidence is missing",
    )
    for selector in (".write_div", ".gallview_head"):
        count = diagnostics["counts"].get(selector)
        _require(type(count) is int and count == 1, "Candidate body or header is ambiguous")
    images = snapshot.get("images")
    excluded = snapshot.get("excluded_images")
    pending = snapshot.get("pending_images")
    counts = snapshot.get("image_counts")
    _require(isinstance(images, list) and len(images) <= 500, "Invalid candidate image inventory")
    _require(
        isinstance(excluded, list) and len(excluded) <= 500, "Candidate exclusions are invalid"
    )
    _require(isinstance(pending, list) and not pending, "Candidate images remain unresolved")
    _require(isinstance(counts, dict), "Candidate image counts are missing")
    for key in ("body_occurrences", "included_unique", "excluded", "pending"):
        _require(
            type(counts.get(key)) is int and 0 <= counts[key] <= 500,
            "Candidate image counts are invalid",
        )
    _require(
        counts["included_unique"] == len(images)
        and counts["excluded"] == len(excluded)
        and counts["pending"] == 0,
        "Candidate image counts conflict",
    )
    signatures = []
    orders = set()
    sources = set()
    for image in images:
        _require(isinstance(image, dict), "Candidate image metadata is invalid")
        source = image.get("display_url")
        try:
            parsed = urlsplit(source) if isinstance(source, str) else None
            usable = bool(
                parsed
                and parsed.scheme in {"http", "https"}
                and parsed.hostname
                and not parsed.username
                and not parsed.password
                and not any(ord(char) <= 32 for char in source)
            )
        except ValueError:
            usable = False
        _require(
            usable and source not in sources, "An exact unique candidate image source is required"
        )
        sources.add(source)
        stable = "urlsha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()
        _require(
            image.get("stable_key") == stable
            and image.get("stable_key_source") == "exact_display_url_hash",
            "Candidate image identity is not its exact URL hash",
        )
        _require(
            image.get("display_urls") == [source],
            "Candidate image source variants are not approved",
        )
        width, height = image.get("natural_width"), image.get("natural_height")
        _require(
            type(width) is int and type(height) is int and 0 < width < 2**31 and 0 < height < 2**31,
            "Candidate image dimensions are invalid",
        )
        occurrences = image.get("occurrences")
        _require(
            isinstance(occurrences, list)
            and 1 <= len(occurrences) <= 500
            and all(type(order) is int and order > 0 for order in occurrences),
            "Candidate image occurrences are invalid",
        )
        _require(
            occurrences == sorted(set(occurrences))
            and type(image.get("body_order")) is int
            and image.get("body_order") == occurrences[0],
            "Candidate image order is inconsistent",
        )
        _require(not orders.intersection(occurrences), "Candidate image occurrences overlap")
        orders.update(occurrences)
        resource = image.get("resource_identity")
        _require(
            resource is None or resource == _shared_no_identity(source, body=True),
            "Candidate resource evidence conflicts with its exact source",
        )
        status = image.get("original_filename_match_status")
        _require(
            isinstance(status, str)
            and status in {"matched", "ambiguous", "unavailable", "not_applicable"},
            "Candidate filename evidence is invalid",
        )
        if status != "matched":
            _require(
                image.get("original_attachment_filename") is None,
                "An uncertain candidate filename must remain null",
            )
        else:
            _require(
                isinstance(image.get("original_attachment_filename"), str)
                and bool(image["original_attachment_filename"].strip()),
                "A matched candidate filename is missing",
            )
        signatures.append((stable, source, width, height, tuple(occurrences)))
    _require(
        [image["body_order"] for image in images]
        == sorted(image["body_order"] for image in images),
        "Candidate images are not in body order",
    )
    excluded_signature = []
    for item in excluded:
        _require(isinstance(item, dict), "Candidate exclusion metadata is invalid")
        order = item.get("body_order")
        _require(
            type(order) is int
            and order > 0
            and order not in orders
            and isinstance(item.get("reason"), str)
            and item.get("reason") in _EXCLUSION_REASONS,
            "Candidate exclusion evidence is invalid",
        )
        orders.add(order)
        excluded_signature.append(
            {
                key: item.get(key)
                for key in ("body_order", "display_url", "display_url_scheme", "reason")
            }
        )
    _require(
        orders == set(range(1, counts["body_occurrences"] + 1)),
        "Candidate body occurrences are incomplete",
    )
    return signatures, excluded_signature


def _confirmed_detail(candidate, baseline, detail):
    _require(
        all(isinstance(value, dict) for value in (candidate, baseline, detail)),
        "Candidate permit evidence is invalid",
    )
    candidate_scope = tuple(candidate.get(key) for key in SCOPE_FIELDS)
    detail_scope = tuple(detail.get(key) for key in SCOPE_FIELDS)
    _require(
        candidate_scope in (REVIEWED_SCOPE, MONITOR_SCOPE) and detail_scope == candidate_scope,
        "Candidate permit scope is outside this pilot",
    )
    try:
        target = validate_post_url(candidate.get("post_url"))
    except (TypeError, ValueError) as error:
        raise CandidateSavePolicyError("Candidate permit URL is invalid") from error
    _require(
        target["canonical_url"] == candidate["post_url"]
        and all(
            candidate.get(key) == target[key] for key in ("gallery_type", "gallery_id", "post_id")
        ),
        "Candidate permit identity conflicts with its URL",
    )
    _require(
        detail.get("post_id") == candidate["post_id"]
        and _uuid(candidate.get("first_scan_id"))
        and detail.get("first_scan_id") == candidate["first_scan_id"]
        and _uuid(detail.get("attempt_id")),
        "Candidate discovery and detail identity conflict",
    )
    _require(detail.get("status") == "completed", "Candidate detail was not completed")
    baseline_time = _time(baseline.get("observed_at"))
    _require(
        _time(detail.get("baseline_observed_at")) == baseline_time,
        "Candidate detail baseline changed",
    )
    first_seen = _time(candidate.get("first_seen_at"))
    started, finished = _time(detail.get("started_at")), _time(detail.get("finished_at"))
    _require(
        baseline_time <= first_seen <= started <= finished, "Candidate detail timing conflicts"
    )
    result = detail.get("result")
    _require(isinstance(result, dict), "Candidate detail result is missing")
    observation = result.get("private_observation")
    control = result.get("control")
    _require(
        isinstance(observation, dict)
        and type(observation.get("http_status")) is int
        and observation.get("url") == candidate["post_url"]
        and type(observation.get("navigation_attempts")) is int
        and observation["navigation_attempts"] == 1,
        "Candidate detail navigation was not confirmed",
    )
    _require(
        isinstance(control, dict) and control.get("blocked") is False,
        "Candidate detail is blocked or unconfirmed",
    )
    _require(
        _time(control.get("finished_at")) == finished
        and type(control.get("http_status")) is int
        and control.get("http_status") == observation["http_status"],
        "Candidate detail response timing conflicts",
    )
    interval = control.get("interval_seconds")
    _require(
        type(interval) is int
        and 60 <= interval <= 300
        and _time(control.get("next_eligible_at")) >= finished + timedelta(seconds=interval),
        "Candidate detail cooldown is invalid",
    )
    snapshot = observation.get("snapshot")
    if observation["http_status"] in {404, 410}:
        _require(
            observation.get("status") == "http_error"
            and observation.get("error_type") == "HTTPStatusError"
            and observation.get("error_code") is None
            and snapshot is None
            and result.get("classification") == unobserved_detail("candidate_unavailable"),
            "Candidate unavailability was not confirmed",
        )
        return None, "unavailable"
    _require(
        observation.get("status") == "observed"
        and 200 <= observation["http_status"] < 300
        and isinstance(snapshot, dict)
        and snapshot.get("post_url") == candidate["post_url"],
        "Candidate detail snapshot is missing",
    )
    _require(
        started <= _time(snapshot.get("observed_at")) <= finished,
        "Candidate snapshot is outside its recorded attempt",
    )
    try:
        classification = classify_candidate_detail(candidate, baseline, snapshot)
    except CandidatePolicyError as error:
        raise CandidateSavePolicyError(
            "Candidate detail identity or baseline is invalid"
        ) from error
    _require(
        classification["time_status"] in {"at_or_after_baseline", "before_baseline"}
        and classification["header_observed"] is True
        and result.get("classification") == classification,
        "Candidate publication time was not confirmed",
    )
    ip = snapshot.get("ip_display")
    _require(
        ip is None or isinstance(ip, str) and bool(ip.strip()),
        "Candidate public IP display is invalid",
    )
    return snapshot, classification["time_status"]


def _validate_payload(payload):
    _require(
        isinstance(payload, dict) and set(payload) == {"candidate", "baseline", "detail"},
        "Candidate permit payload is invalid",
    )
    candidate, baseline, detail = (payload[key] for key in ("candidate", "baseline", "detail"))
    snapshot, time_status = _confirmed_detail(candidate, baseline, detail)
    _require(
        time_status == "at_or_after_baseline",
        "Candidate publication time was not confirmed after the baseline",
    )
    included, _ = _image_signature(snapshot)
    _require(
        1 <= len(included) <= _image_limit(candidate),
        "Candidate image count is outside the save limit",
    )
    return candidate, baseline, detail, snapshot


@dataclass(frozen=True)
class CandidateSavePermit:
    """Canonical private evidence; construction and use both revalidate it."""

    _payload_json: str

    def __post_init__(self):
        self.validate()

    def _evidence(self):
        _require(isinstance(self._payload_json, str), "Candidate permit metadata is invalid")
        _require(
            len(self._payload_json.encode("utf-8")) <= MAX_PERMIT_BYTES,
            "Candidate permit metadata exceeds its limit",
        )
        try:
            payload = json.loads(self._payload_json)
        except (TypeError, ValueError) as error:
            raise CandidateSavePolicyError("Candidate permit metadata is invalid") from error
        _require(
            _canonical(payload) == self._payload_json, "Candidate permit metadata is not canonical"
        )
        return _validate_payload(payload)

    def validate(self):
        self._evidence()

    @property
    def fingerprint(self):
        self.validate()
        return hashlib.sha256(self._payload_json.encode("utf-8")).hexdigest()

    @property
    def post_url(self):
        return self._evidence()[0]["post_url"]

    @property
    def watch_name(self):
        return self._evidence()[0]["watch_name"]

    @property
    def keyword(self):
        return self._evidence()[0]["keyword"]

    @property
    def search_type(self):
        return self._evidence()[0]["search_type"]

    @property
    def first_seen_at(self):
        return _time(self._evidence()[0]["first_seen_at"])

    @property
    def detail_attempt_id(self):
        return self._evidence()[2]["attempt_id"]

    @property
    def reference_snapshot(self):
        return self._evidence()[3]

    @property
    def image_count(self):
        return len(self._evidence()[3]["images"])

    def authorize_snapshot(self, fresh):
        candidate, baseline, detail, reference = self._evidence()
        # Canonical serialization both bounds the new metadata and makes a deep copy.
        fresh = json.loads(_canonical(fresh))
        _require(isinstance(fresh, dict), "A current candidate snapshot is required")
        try:
            classification = classify_candidate_detail(candidate, baseline, fresh)
        except CandidatePolicyError as error:
            raise CandidateSavePolicyError("Current candidate identity changed") from error
        _require(
            classification["time_status"] == "at_or_after_baseline"
            and classification["header_observed"] is True,
            "Current candidate publication time is not confirmed",
        )
        _require(
            fresh.get("post_url") == candidate["post_url"]
            and _time(fresh.get("observed_at")) >= _time(reference["observed_at"]),
            "Current candidate observation is stale",
        )
        _require(
            all(fresh.get(key) == reference.get(key) for key in _HEADER_FIELDS)
            and _time(fresh.get("published_at")) == _time(reference.get("published_at")),
            "Current candidate header changed",
        )
        _require(
            _image_signature(fresh) == _image_signature(reference),
            "Current candidate image set or exclusions changed",
        )
        fresh["layout_status"] = "candidate_reviewed"
        fresh["queue_eligible"] = True
        fresh["profile_evidence"] = dict(fresh.get("profile_evidence") or {}) | {
            "queue_validation": "reviewed_candidate_permit",
            "pilot_scope": {
                "source": "completed_candidate_detail",
                "detail_attempt_id": detail["attempt_id"],
                "permit_fingerprint": self.fingerprint,
                "post_identity": {
                    key: candidate[key] for key in ("gallery_type", "gallery_id", "post_id")
                },
                "save_scope": "one_frozen_candidate",
            },
        }
        return fresh


def make_candidate_save_permit(candidate, baseline, detail):
    """Freeze one completed observation without changing global site trust."""
    _require(isinstance(candidate, dict), "Candidate permit evidence is invalid")
    candidate = {
        key: candidate.get(key)
        for key in (*SCOPE_FIELDS, "post_id", "post_url", "first_scan_id", "first_seen_at")
    }
    return CandidateSavePermit(
        _canonical({"candidate": candidate, "baseline": baseline, "detail": detail})
    )


def classify_stored_candidate_image(candidate, baseline, detail):
    """Identify what this completed observation proves for the bounded body-image search."""
    try:
        snapshot, time_status = _confirmed_detail(candidate, baseline, detail)
        if time_status in {"unavailable", "before_baseline"}:
            return time_status, None
        images = snapshot.get("images")
        if isinstance(images, list) and not 1 <= len(images) <= _image_limit(candidate):
            # A listed attachment never establishes that an image appeared in the body.
            # Check every occurrence, including unresolved loads and excluded elements.
            included, excluded = _image_signature(snapshot)
            if included:
                return "outside_save_limit", None
            if not excluded and snapshot["diagnostics"].get("image_shapes"):
                # An earlier sample of this document already saw a body image.
                return "needs_review", None
            return ("excluded_body_images_only" if excluded else "no_body_images_observed"), None
        return "save_ready", make_candidate_save_permit(candidate, baseline, detail)
    except CandidateSavePolicyError:
        return "needs_review", None
