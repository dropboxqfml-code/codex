"""Select an unattempted post first discovered in the latest verified two-page scan."""

from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.search_list import MAX_ROWS
from image_monitor.watch_runtime import confirmed_monitor_scan, verified_recent_plan
from image_monitor.watch_store import MONITOR_SCOPE, _record


def recent_scan_candidates(queue, scope, state):
    """Read newly recorded rows in verified display order under the shared lease."""
    plan = verified_recent_plan(queue, scope, state)
    if plan is None:
        return None, []
    return scan_plan_candidates(queue, scope, state, plan)


def scan_plan_candidates(queue, scope, state, plan):
    """Match a replayed list plan to durable candidate identities in display order."""
    latest = state["latest_scan"]
    scan_id = latest["scan_id"]
    # A previously known post may have been seen again. First and latest scan
    # identities distinguish it from a newly discovered candidate.
    rows = queue.connection.execute(
        "SELECT c.*, d.attempt_id FROM watch_candidates c "
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
    candidates = []
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
            candidates.append(_record(row))
    pages = latest["result"]["private_observation"]["pages"]
    summary = {
        "generation": state["generation"],
        "coverage": "complete" if plan["complete"] else "partial",
        "gap_reason": plan["gap_reason"],
        "page_count": len(pages),
        "ordinary_rows": sum(len(page["rows"]) for page in pages),
        "new_candidates": len(candidates),
        "unattempted_candidates": sum(row["attempt_id"] is None for row in candidates),
    }
    # The planner preserves verified descending list order.
    return summary, candidates


def recent_scan_candidate(queue, scope, state, *, post_id=None):
    """Pick one unattempted identity, optionally pinned by the bounded image search."""
    summary, candidates = recent_scan_candidates(queue, scope, state)
    for row in candidates:
        if row["attempt_id"] is None and (post_id is None or row["post_id"] == post_id):
            del row["attempt_id"]
            row["unattempted"] = 1
            return summary, [row]
    return summary, []


def monitor_detail_scan_id(database, queue, state):
    """Identify a closed monitor scan whose next automatic detail turn is still unspent."""
    latest = state["latest_scan"]
    if (
        queue.schema_version < 5
        or not latest
        or not confirmed_monitor_scan(database, latest)
        or verified_recent_plan(queue, MONITOR_SCOPE, state) is None
        or not CandidateDetailStore(queue).list_pending(MONITOR_SCOPE, limit=1)
    ):
        return None
    # Detail start times from CandidateDetailStore are normalized to UTC microseconds.
    # An interrupted attempt also owns its turn; it cannot authorize another post here.
    attempted = queue.connection.execute(
        "SELECT 1 FROM candidate_details WHERE watch_name=? AND gallery_type=? AND gallery_id=? "
        "AND keyword=? AND search_type=? AND started_at>=? LIMIT 1",
        (*MONITOR_SCOPE.key(), latest["observed_at"]),
    ).fetchone()
    return latest["scan_id"] if attempted is None else None
