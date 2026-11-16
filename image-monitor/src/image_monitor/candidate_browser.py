"""Observe one persisted candidate's public DOM in an owned headless browser."""

import json
from datetime import UTC, datetime

from image_monitor.dcinside import DCSnapshotError, inspect_post, validate_post_url
from image_monitor.paths import aware
from image_monitor.site_inspection import MAX_SNAPSHOT_BYTES, _error_code, _report_copy
from image_monitor.watch_browser import HeadlessWatchBrowser

# The durable detail result also wraps this outcome with classification/control.
DETAIL_RESULT_RESERVE_BYTES = 16 * 1024
MAX_OBSERVATION_BYTES = MAX_SNAPSHOT_BYTES - DETAIL_RESULT_RESERVE_BYTES


def _candidate_target(candidate: dict) -> dict:
    if not isinstance(candidate, dict):
        raise ValueError("Candidate must be a persisted identity record")
    target = validate_post_url(candidate.get("post_url"))
    if (
        (candidate.get("gallery_type"), candidate.get("gallery_id")) != ("normal", "comic_new6")
        or candidate.get("gallery_type") != target["gallery_type"]
        or candidate.get("gallery_id") != target["gallery_id"]
        or candidate.get("post_id") != target["post_id"]
        or candidate.get("post_url") != target["canonical_url"]
    ):
        raise ValueError("Candidate identity does not match the reviewed watch scope")
    return target


def _metadata_size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


class HeadlessCandidateBrowser(HeadlessWatchBrowser):
    """Reuse owned browser lifecycle while leaving scheduling and storage to the caller."""

    @staticmethod
    def _inspection_failure(result: dict, error: Exception, status: str) -> dict:
        result.update(status=status, error_type=type(error).__name__, error_code=_error_code(error))
        if isinstance(error, DCSnapshotError):
            try:
                diagnostics = _report_copy(error.diagnostics, public=False)
                if _metadata_size(result | {"diagnostics": diagnostics}) <= MAX_OBSERVATION_BYTES:
                    result["diagnostics"] = diagnostics
                else:
                    result["diagnostics_omitted"] = "metadata_limit"
            except Exception:
                result["diagnostics_omitted"] = "invalid_metadata"
        return result

    def inspect(self, candidate: dict, observed_at: datetime) -> dict:
        """Navigate once, inspect the existing body DOM, and return metadata only.

        No list refresh, attachment navigation, image saving, or retry occurs.
        An observed snapshot retains its existing validation status: reading a
        candidate never expands the set of posts approved for native saving.
        """
        if self._page is None:
            raise ValueError("Candidate inspection requires an open browser context")
        target = _candidate_target(candidate)
        if not isinstance(observed_at, datetime):
            raise ValueError("observed_at must be a timezone-aware datetime")
        started = aware(observed_at).astimezone(UTC)
        result = {
            "status": "observed",
            "url": target["canonical_url"],
            "http_status": None,
            "retry_after": None,
            "navigation_attempts": 1,
            "error_type": None,
            "error_code": None,
        }
        try:
            response = self._page.goto(
                target["canonical_url"], wait_until="domcontentloaded", timeout=30_000
            )
            status = response.status if response is not None else None
            result["http_status"] = status
            if response is not None:
                retry_after = response.header_value("retry-after")
                if isinstance(retry_after, str):
                    result["retry_after"] = retry_after[:256]
        except Exception as error:
            return self._inspection_failure(result, error, "network_error")
        if status is None or status >= 400:
            result.update(status="http_error", error_type="HTTPStatusError")
            return result
        try:
            snapshot = _report_copy(
                inspect_post(
                    self._page,
                    expected_url=target["canonical_url"],
                    observed_at=self._observation_time(started),
                    include_dccon=False,
                    timeout_ms=20_000,
                ),
                public=False,
            )
            if not isinstance(snapshot, dict):
                raise ValueError("Candidate inspection did not return a metadata object")
            if _metadata_size(result | {"snapshot": snapshot}) > MAX_OBSERVATION_BYTES:
                raise ValueError("Candidate inspection metadata exceeds report limit")
            result["snapshot"] = snapshot
        except Exception as error:
            return self._inspection_failure(result, error, "inspection_error")
        return result
