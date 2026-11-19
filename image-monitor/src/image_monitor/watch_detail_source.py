"""Select an unattempted post first discovered in the latest verified two-page scan."""

from image_monitor.search_list import MAX_ROWS
from image_monitor.watch_runtime import verified_recent_plan
from image_monitor.watch_store import _record


def recent_scan_candidate(queue, scope, state):
    """Read the committed evidence under the caller's discovery/detail lease."""
    plan = verified_recent_plan(queue, scope, state)
    if plan is None:
        return None, []
    latest = state["latest_scan"]
    scan_id = latest["scan_id"]
    # A previously known post may have been seen again. First and latest scan
    # identities distinguish it from a newly discovered candidate.
    rows = queue.connection.execute(
        "SELECT c.*, d.attempt_id IS NULL AS unattempted FROM watch_candidates c "
        "LEFT JOIN candidate_details d USING (watch_name,gallery_type,gallery_id,"
        "keyword,search_type,post_id) WHERE c.watch_name=? AND c.gallery_type=? "
        "AND c.gallery_id=? AND c.keyword=? AND c.search_type=? "
        "AND (c.first_scan_id=? OR c.latest_scan_id=?) LIMIT ?",
        (*scope.key(), scan_id, scan_id, MAX_ROWS * 2 + 1),
    ).fetchall()
    if len(rows) > MAX_ROWS * 2:
        return None, []
    stored = {row["post_id"]: row for row in rows}
    planned = {candidate["post_id"]: candidate["post_url"] for candidate in plan["candidates"]}
    if any(row["first_scan_id"] == scan_id and row["post_id"] not in planned for row in rows):
        return None, []
    pending = []
    new_candidates = 0
    for post_id, url in planned.items():
        row = stored.get(post_id)
        if (
            row is None
            or row["post_url"] != url
            or row["latest_scan_id"] != scan_id
            or row["last_seen_at"] != latest["observed_at"]
        ):
            return None, []
        if row["first_scan_id"] == scan_id:
            if row["first_seen_at"] != latest["observed_at"]:
                return None, []
            new_candidates += 1
            if row["unattempted"]:
                pending.append(row)
    pages = latest["result"]["private_observation"]["pages"]
    summary = {
        "generation": state["generation"],
        "coverage": "complete" if plan["complete"] else "partial",
        "gap_reason": plan["gap_reason"],
        "page_count": len(pages),
        "ordinary_rows": sum(len(page["rows"]) for page in pages),
        "new_candidates": new_candidates,
        "unattempted_candidates": len(pending),
    }
    # The planner preserves verified descending list order.
    return summary, [_record(row) for row in pending[:1]]
