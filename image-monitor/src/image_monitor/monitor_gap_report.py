"""Public page numbers and progress of a verified long-gap scan."""

from image_monitor.watch_store import MAX_MONITOR_SCAN_PAGES

# The site's validated list URLs accept at most nine digits for a page number.
_MAX_PAGE = 999_999_999

RECOVERY_MESSAGES = {
    "advanced": "지난번에 확인한 위치에서 다음 쪽까지 이어서 확인했습니다.",
    "completed": "이전 완료 지점과 그다음 쪽을 확인해 밀린 구간을 모두 연결했습니다.",
    "frontier_changed": "지난 위치의 글 순서가 달라져 연결을 확인하지 못했습니다.",
    "successor_unconfirmed": "다음 쪽으로 이어지는 경로를 확인하지 못했습니다.",
    "overlap_pending": "연결 여부를 확정하려면 뒤쪽 목록을 더 확인해야 합니다.",
    "segment_rejoined": "중간에 새로 쌓인 구간이 이전 목록과 이어져 밀린 글을 계속 확인합니다.",
    "head_rejoined": "최근 목록과 지난 목록이 이어져 저장된 위치에서 복구를 계속합니다.",
    "segment_queued": "새로 쌓인 구간의 복구를 시작했습니다. 이전 복구 위치도 보관했습니다.",
    "held": "연결을 확인할 수 없어 이전 복구 위치를 보관했습니다.",
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
    return {
        **checked_window_starts(turn, numbers, limit, bookmark=route == "bookmark"),
        "recovery_status": status,
        "recovery_depth": depth,
        "recovery_route": route,
        "recovery_crossed_search_range": crossed,
    }


def gap_route_details(record):
    """Project only public progress from a successful replay of the private marker."""
    marker = record["gap_recovery"]
    numbers = [page["page"] for page in record["private_observation"]["pages"]]
    return checked_gap_route(
        {
            "status": "complete" if record["complete"] else "partial",
            "search_window_start_visits": search_window_start_visits(record),
            "recovery_status": marker["status"],
            "recovery_route": marker["route"],
            "recovery_depth": marker["depth"],
            "recovery_crossed_search_range": marker["crossed_search_range"],
        },
        numbers,
        record["control"]["follow_up_page_limit"],
    )
