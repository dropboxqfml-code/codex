"""Korean descriptions shared by the session and offline list reports."""

from image_monitor.monitor_list_review import public_list_review

_STAGE_TEXT = {
    "preflight": "목록 확인을 시작할 때 설정이나 작업 폴더를 확인하지 못했습니다.",
    "baseline_check": "기존 목록 기록과 다음 실행 가능 시간을 읽는 중에 멈췄습니다.",
    "cursor_check": "이전 기록에서 이번에 이어갈 페이지를 정하는 중에 멈췄습니다.",
    "browser_scan": "Chrome 목록 작업에서 최종 결과를 받는 중에 멈췄습니다.",
    "browser_close": "목록 확인에 사용한 Chrome의 종료 여부를 확인하지 못했습니다.",
    "watch_result": "목록 작업이 실패를 보고했습니다.",
    "receipt_check": "이번 목록 작업의 최종 결과를 저장된 실행 기록과 대조하지 못했습니다.",
    "scan_record": "목록 확인 결과와 저장된 기록이 일치하는지 확인하지 못했습니다.",
    "route_check": "방문한 페이지가 이전 기록에서 허용한 경로와 일치하는지 확인하지 못했습니다.",
    "transport_check": "방문한 목록 페이지의 응답이나 이동 순서를 확인하지 못했습니다.",
    "planner_check": "저장된 목록으로 탐색 과정을 다시 계산한 결과를 확인하지 못했습니다.",
    "candidate_check": "목록에서 확인한 후보와 대기열의 후보를 대조하지 못했습니다.",
    "partial_check": "부분 확인한 목록을 다음 작업에 사용할 근거가 부족합니다.",
    "queue_check": "목록 확인 후 대기열과 실행 상태를 읽는 중에 멈췄습니다.",
    "stored_scan": "저장된 마지막 목록 기록에서 확인한 내용입니다.",
}


def describe_list_review(value):
    review = public_list_review(value)
    if not review:
        return None
    review["stage_ko"] = _STAGE_TEXT[review["stage"]]
    numbers = [
        page["page"]
        for page in review.get("pages", [])
        if page.get("page") is not None and page.get("layout_status") == "unverified"
    ]
    if numbers:
        pages = "·".join(str(number) for number in numbers)
        review["observation_ko"] = f"{pages}쪽의 목록 구조를 확인하지 못했습니다."
    elif review.get("transport") == "http_error" and "http_status" in review:
        review["observation_ko"] = f"목록 요청에서 HTTP {review['http_status']} 응답을 받았습니다."
    return review
