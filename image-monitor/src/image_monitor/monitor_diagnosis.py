"""Recover the last list-profile failure without opening a site or changing the watch DB."""

import json

from image_monitor.watch_diagnosis import diagnose_list_scan, public_list_diagnosis

PROFILE_GAP = "list_profile_unverified_or_incomplete"
MAX_DIAGNOSIS_BYTES = 4 * 1024 * 1024


def read_latest_list_diagnosis(queue, scope, *, max_generation=2**63 - 1):
    """Look through gap metadata and project at most one bounded scan payload."""
    if queue.schema_version < 4:
        return None
    key = scope.key()
    row = queue.connection.execute(
        """WITH last_gap AS (
            SELECT scan_id,generation,observed_at FROM watch_gaps
            WHERE watch_name=? AND gallery_type=? AND gallery_id=? AND keyword=? AND search_type=?
              AND reason=? AND generation<=?
            ORDER BY generation DESC LIMIT 1
        )
        SELECT CASE WHEN length(CAST(s.result_json AS BLOB))<=? THEN s.result_json END
        FROM last_gap g JOIN watch_scans s ON s.scan_id=g.scan_id AND s.generation=g.generation
            AND s.observed_at=g.observed_at
        WHERE s.watch_name=? AND s.gallery_type=? AND s.gallery_id=? AND s.keyword=?
          AND s.search_type=? AND s.complete=0 AND s.gap_reason=?""",
        (*key, PROFILE_GAP, max_generation, MAX_DIAGNOSIS_BYTES, *key, PROFILE_GAP),
    ).fetchone()
    if row is None or not isinstance(row[0], str):
        return None
    try:
        result = json.loads(row[0])
        if not isinstance(result, dict) or result.get("gap_reason") != PROFILE_GAP:
            return None
        return public_list_diagnosis(
            diagnose_list_scan({"complete": False, "gap_reason": PROFILE_GAP, "result": result})
        )
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        # Optional legacy evidence never grants or revokes a monitoring permission.
        return None
