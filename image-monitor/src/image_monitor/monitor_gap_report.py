"""Public page numbers and progress of a verified long-gap scan."""

from image_monitor.watch_store import MAX_MONITOR_SCAN_PAGES

# The site's validated list URLs accept at most nine digits for a page number.
_MAX_PAGE = 999_999_999

RECOVERY_MESSAGES = {
    "advanced": "지난번에 확인한 위치에서 다음 쪽까지 이어서 확인했습니다.",
    "completed": "이전 완료 지점과 그다음 쪽을 확인해 밀린 구간을 모두 연결했습니다.",
    "frontier_relocated": "목록의 연결을 확인해 복구 위치를 한 쪽 옮겼습니다.",
    "restart_pending": "이전 글을 찾지 못했습니다. 다음 주기에 첫 쪽부터 다시 확인합니다.",
    "restarted_from_head": "첫 쪽부터 네 쪽이 이어졌습니다. 여기서 과거 글을 계속 찾습니다.",
    "frontier_changed": "목록의 연결을 확인하지 못해 이전 복구 위치를 유지했습니다.",
    "successor_unconfirmed": "다음 쪽으로 이어지는 경로를 확인하지 못했습니다.",
    "overlap_pending": "연결 여부를 확정하려면 뒤쪽 목록을 더 확인해야 합니다.",
    "segment_rejoined": "중간에 새로 쌓인 구간이 이전 목록과 이어져 밀린 글을 계속 확인합니다.",
    "head_rejoined": "최근 목록과 지난 목록이 이어져 저장된 위치에서 복구를 계속합니다.",
    "segment_queued": "새로 쌓인 구간의 복구를 시작했습니다. 이전 복구 위치도 보관했습니다.",
    "held": "연결을 확인할 수 없어 이전 복구 위치를 보관했습니다.",
}


RECOVERY_REASON_MESSAGES = {
    "head_rejoined": {
        "recent_page_boundary": (
            "지난 첫 쪽 끝의 글 세 건과 다음 쪽 첫 글이 연속으로 확인돼 "
            "이전 복구 위치를 유지합니다."
        )
    },
    "restarted_from_head": {
        "recent_head_changed": (
            "지난 첫 쪽과의 연결을 확인할 수 없어 이번에 확인한 네 번째 쪽부터 다시 탐색합니다."
        )
    },
    "frontier_relocated": {
        "frontier_prefix_overlap": (
            "저장한 목록 앞부분의 글 순서를 바로 다음 쪽 끝에서 확인했습니다. "
            "이전 완료 지점까지 이어지는지는 다음 목록에서 계속 확인합니다."
        )
    },
    "segment_queued": {
        "recent_tail_overlap": (
            "최근 네 쪽의 끝에서 지난 첫 쪽의 일반 글 세 건 이상을 같은 순서로 확인했습니다. "
            "현재 네 번째 방문 지점부터 새 구간을 이어서 확인하며 이전 복구 위치도 보관합니다."
        ),
        "observed_frontier_shift": (
            "지난 첫 쪽의 일반 글 전체가 최근 목록 뒤쪽으로 밀렸고, "
            "이전 복구 페이지에서는 모두 더 새로운 글이 보였습니다. "
            "현재 네 번째 방문 지점에서 새 구간을 이어가도록 기록했습니다."
        ),
    },
    "held": {
        "recent_page_limit": "확인한 최근 목록이 네 쪽 미만이라 연결 여부를 판단할 수 없습니다.",
        "recent_chain_unverified": "최근 네 쪽의 링크와 글 순서가 이어지는지 확인하지 못했습니다.",
        "recent_overlap_unconfirmed": (
            "최근 네 쪽과 지난 첫 쪽 사이에서 글 순서를 충분히 대조하지 못했습니다."
        ),
        "deferred_limit": "보관 가능한 구간 수가 한도에 도달해 새 구간 추가를 보류했습니다.",
        "recent_plan_unconfirmed": "이번 확인 결과로는 밀린 구간을 이어갈 수 없습니다.",
        "frontier_rebase_unverified": "최근 목록과 이전 복구 위치를 다시 연결하지 못했습니다.",
    },
}


RECOVERY_OBSERVATION_MESSAGES = {
    "disjoint_recent_rows": (
        "최근 네 쪽의 일반 글 번호가 모두 이전 첫 쪽의 가장 큰 글 번호보다 컸습니다. "
        "이전 복구 위치를 보관하고 이번에 읽은 네 번째 목록에서 새 구간을 이어갑니다."
    )
}


def public_recovery_pages(numbers, limit=MAX_MONITOR_SCAN_PAGES):
    """Bound the displayed page numbers for recent visits and a possible bookmarked pair."""
    if (
        type(limit) is not int
        or not 2 <= limit <= MAX_MONITOR_SCAN_PAGES
        or not isinstance(numbers, list)
        or not 1 <= len(numbers) <= limit
        or any(type(n) is not int or not 1 <= n <= _MAX_PAGE for n in numbers)
        or numbers[0] != 1
        or (len(numbers) >= 2 and numbers[1] not in (1, 2))
        or (len(numbers) == 4 and numbers[3] not in (numbers[2] + 1, 1))
    ):
        return None
    return numbers.copy()


def search_window_start_visits(record):
    """Identify the verified adjacent visits that used the site's next-search link."""
    marker = record.get("gap_recovery", {})
    outcome = record["private_observation"]
    if not marker and outcome.get("gap_seed_route") is not True:
        return []
    pages = outcome["pages"]
    return [
        visit
        for visit, (previous, page) in enumerate(zip(pages, pages[1:], strict=False), 2)
        if page["search_pos"] != previous["search_pos"]
        and page["page"] == 1
        and (
            marker.get("route") != "bookmark"
            or visit == 2
            or (visit == 4 and marker["crossed_search_range"])
        )
    ]


def checked_window_starts(turn, numbers, limit, *, bookmark=False):
    starts = turn.get("search_window_start_visits", [])
    if (
        public_recovery_pages(numbers, limit) is None
        or not isinstance(starts, list)
        or len(starts) > limit - 1
        or any(
            type(i) is not int or not 2 <= i <= len(numbers) or numbers[i - 1] != 1 for i in starts
        )
        or starts != sorted(set(starts))
        or (bookmark and 3 in starts)
    ):
        raise ValueError("Invalid search range transition")
    for i in range(2, len(numbers) + 1):
        if bookmark and i >= 3:
            continue
        if numbers[i - 1] != (1 if i in starts else numbers[i - 2] + 1):
            raise ValueError("Observed pages do not follow the verified search ranges")
    return {"search_window_start_visits": starts.copy()} if starts else {}


def _checked_frontier_overlap(value):
    from image_monitor.search_list import MAX_ROWS

    if not isinstance(value, dict):
        raise ValueError("Invalid frontier row counts")
    old, matched, shape = (value.get(key) for key in ("previous_rows", "matched_rows", "shape"))
    if (
        type(old) is not int
        or type(matched) is not int
        or not 0 <= matched <= old <= MAX_ROWS
        or not old
        or shape not in ("none", "prefix_at_end", "other")
        or (shape == "none") != (matched == 0)
        or (shape == "prefix_at_end" and matched == old)
    ):
        raise ValueError("Invalid frontier row counts or alignment")
    return {"previous_rows": old, "matched_rows": matched, "shape": shape}


def checked_gap_route(turn, numbers, limit):
    """Keep public fields only and reject inconsistent route/status combinations."""
    route = turn.get("recovery_route")
    status = turn.get("recovery_status")
    depth = turn.get("recovery_depth")
    crossed = turn.get("recovery_crossed_search_range")
    if (
        limit != MAX_MONITOR_SCAN_PAGES
        or not public_recovery_pages(numbers, limit)
        or route not in ("recent", "bookmark")
        or not isinstance(status, str)
        or status not in RECOVERY_MESSAGES
        or type(depth) is not int
        or depth < 1
        or type(crossed) is not bool
        or (route == "bookmark" and len(numbers) < 3)
        or (crossed and (route != "bookmark" or len(numbers) != 4 or numbers[3] != 1))
        or (turn["status"] == "complete") != (status == "completed")
        or turn["status"] not in ("complete", "partial")
    ):
        raise ValueError("Invalid recovery page sequence or progress")
    if status in {"restart_pending", "restarted_from_head"} and (
        len(numbers) not in ((3, 4) if status == "restart_pending" else (4,))
        or turn["status"] != "partial"
        or route != ("bookmark" if status == "restart_pending" else "recent")
        or (status == "restarted_from_head" and depth != MAX_MONITOR_SCAN_PAGES)
    ):
        raise ValueError("Invalid frontier restart route")
    relocated = status == "frontier_relocated"
    if relocated and (
        route != "bookmark"
        or len(numbers) != MAX_MONITOR_SCAN_PAGES
        or crossed
        or numbers[3] != numbers[2] + 1
        or turn.get("recovery_reason") != "frontier_prefix_overlap"
    ):
        raise ValueError("Invalid relocated frontier route")
    reason_fields = {}
    if "recovery_reason" in turn:
        reason = turn["recovery_reason"]
        if (
            (route != "recent" and not relocated)
            or not isinstance(reason, str)
            or reason not in RECOVERY_REASON_MESSAGES.get(status, {})
            or (reason == "recent_page_limit" and len(numbers) >= MAX_MONITOR_SCAN_PAGES)
            or (
                reason not in {"recent_page_limit", "recent_plan_unconfirmed"}
                and len(numbers) != MAX_MONITOR_SCAN_PAGES
            )
        ):
            raise ValueError("Invalid recovery reason for the observed route")
        reason_fields["recovery_reason"] = reason
    if "recovery_observation" in turn:
        if (
            turn["recovery_observation"] != "disjoint_recent_rows"
            or reason_fields
            or status != "segment_queued"
            or route != "recent"
            or depth != MAX_MONITOR_SCAN_PAGES
            or len(numbers) != MAX_MONITOR_SCAN_PAGES
        ):
            raise ValueError("Invalid recovery observation for the observed route")
        reason_fields["recovery_observation"] = "disjoint_recent_rows"
    if "frontier_overlap" in turn:
        if (
            status not in ("frontier_changed", "frontier_relocated", "restart_pending")
            or route != "bookmark"
            or len(numbers) != 4
        ):
            raise ValueError("Invalid frontier observation for the reported route")
        overlap = _checked_frontier_overlap(turn["frontier_overlap"])
        if status == "restart_pending" and overlap["matched_rows"] != 0:
            raise ValueError("Unexpected surviving rows for frontier restart")
        if relocated and not 3 <= overlap["matched_rows"] < overlap["previous_rows"]:
            raise ValueError("Inconsistent overlap for a relocated frontier")
        reason_fields["frontier_overlap"] = overlap
    if "candidate_eligible_visits" in turn:
        eligible = turn["candidate_eligible_visits"]
        expected = {
            "frontier_changed": 2,
            "restart_pending": 2,
            "frontier_relocated": MAX_MONITOR_SCAN_PAGES,
        }
        if type(eligible) is not int or route != "bookmark" or eligible != expected.get(status):
            raise ValueError("Invalid candidate page count for the verified frontier")
        reason_fields["candidate_eligible_visits"] = eligible
    return {
        **reason_fields,
        **checked_window_starts(turn, numbers, limit, bookmark=route == "bookmark"),
        "recovery_status": status,
        "recovery_depth": depth,
        "recovery_route": route,
        "recovery_crossed_search_range": crossed,
    }


def _disjoint_recent_rows(record):
    """Compare the replayed four documents with the prior head retained by this exact scan."""
    from image_monitor.watch_history import _descending, _ids, _joined_rows
    from image_monitor.watch_planner import _cursor

    marker = record["gap_recovery"]
    pages = record["private_observation"]["pages"]
    if (
        record["complete"] is not False
        or marker.get("status") != "segment_queued"
        or marker.get("route") != "recent"
        or "recovery_reason" in marker
        or type(marker.get("eligible_pages")) is not int
        or marker["eligible_pages"] != MAX_MONITOR_SCAN_PAGES
        or marker.get("depth") != MAX_MONITOR_SCAN_PAGES
        or len(pages) != MAX_MONITOR_SCAN_PAGES
    ):
        return False
    try:
        current = marker["bookmark"]
        prior_head = current["deferred"][0]["head_ids"]
        checks = record["pages"]
        rows = [_ids(page) for page in pages]
        return (
            len(checks) == len(pages)
            and all(
                check["rows_complete"] is True
                and all(check[key] == value for key, value in _cursor(page).items())
                for check, page in zip(checks, pages, strict=True)
            )
            and _descending(prior_head)
            and all(
                _joined_rows(first, second) for first, second in zip(rows, rows[1:], strict=False)
            )
            and rows[0] == current["head_ids"]
            and rows[-1] == current["frontier_ids"]
            and _cursor(pages[-1]) == current["frontier"]
            and int(rows[-1][-1]) > int(prior_head[0])
        )
    except (AttributeError, IndexError, KeyError, TypeError):
        return False


def _frontier_overlap(record, prior):
    """Compare the two checked frontier documents to this scan's certified starting bookmark."""
    from image_monitor.monitor_gap_store import _reference, _valid_ref
    from image_monitor.watch_history import _descending, _ids, _joined_rows
    from image_monitor.watch_planner import _cursor

    marker = record["gap_recovery"]
    pages = record["private_observation"]["pages"]
    ref = record["control"].get("gap_bookmark_before")
    if (
        record["complete"] is not False
        or marker.get("status") not in ("frontier_changed", "frontier_relocated", "restart_pending")
        or marker.get("route") != "bookmark"
        or len(pages) != 4
        or not isinstance(prior, dict)
        or not _valid_ref(ref)
    ):
        return None
    try:
        old = prior["frontier_ids"]
        checks = record["pages"]
        if (
            type(prior.get("source_generation")) is not int
            or _reference(prior) != ref
            or not _descending(old)
            or _cursor(pages[2]) != prior["frontier"]
            or len(checks) != len(pages)
            or not all(
                check["rows_complete"] is True
                and all(check[key] == value for key, value in _cursor(page).items())
                for check, page in zip(checks, pages, strict=True)
            )
        ):
            return None
        joined = _joined_rows(_ids(pages[2]), _ids(pages[3]))
        if not joined:
            return None
        matched = len(set(old).intersection(joined))
        shape = "none" if not matched else "other"
        if 0 < matched < len(old) and joined[-matched:] == old[:matched]:
            shape = "prefix_at_end"
        return {"previous_rows": len(old), "matched_rows": matched, "shape": shape}
    except (AttributeError, IndexError, KeyError, TypeError):
        return None


def gap_route_details(record, *, prior_bookmark=None):
    """Project only public progress from a successful replay of the private marker."""
    marker = record["gap_recovery"]
    numbers = [page["page"] for page in record["private_observation"]["pages"]]
    if marker["status"] == "frontier_relocated":
        from image_monitor.watch_runtime import FRONTIER_OVERLAP_SCHEMA

        schema = record["control"].get("historical_route_schema")
        if type(schema) is not int or schema != FRONTIER_OVERLAP_SCHEMA:
            raise ValueError("Unverified relocation policy")
    overlap = _frontier_overlap(record, prior_bookmark)
    return checked_gap_route(
        {
            **({"frontier_overlap": overlap} if overlap is not None else {}),
            **(
                {"candidate_eligible_visits": marker["eligible_pages"]}
                if marker["status"] in {"frontier_changed", "frontier_relocated", "restart_pending"}
                else {}
            ),
            "status": "complete" if record["complete"] else "partial",
            "search_window_start_visits": search_window_start_visits(record),
            "recovery_status": marker["status"],
            "recovery_route": marker["route"],
            **(
                {"recovery_reason": marker["recovery_reason"]}
                if "recovery_reason" in marker
                else {}
            ),
            **(
                {"recovery_observation": "disjoint_recent_rows"}
                if _disjoint_recent_rows(record)
                else {}
            ),
            "recovery_depth": marker["depth"],
            "recovery_crossed_search_range": marker["crossed_search_range"],
        },
        numbers,
        record["control"]["follow_up_page_limit"],
    )
