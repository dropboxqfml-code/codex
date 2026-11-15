from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from image_monitor.queue import QueueStore
from image_monitor.search_list import build_list_url, parse_list_snapshot
from image_monitor.watch_planner import WatchPlanError, next_poll_at, plan_scan
from image_monitor.watch_store import WatchScope, WatchStore

NOW = datetime(2026, 11, 15, 8, 0, tzinfo=UTC)
SCOPE = WatchScope("watch", "normal", "fixture", "그림", "search_subject_memo")
LIVE_SCOPE = WatchScope("reviewed watch", "normal", "comic_new6", "ai", "search_subject_memo")
EMPTY_STATE = {"generation": 0, "baseline": None, "checkpoint": None, "latest_scan": None}


def link(page=2, search_pos=None):
    return {
        "canonical_url": build_list_url("normal", "fixture", "그림", page, search_pos),
        "page": page,
        "search_pos": search_pos,
    }


def snapshot(ids, *, page=1, search_pos=None, links=(), terminal=False, **overrides):
    return {
        "scope": {
            "gallery_type": "normal",
            "gallery_id": "fixture",
            "search_type": "search_subject_memo",
            "keyword": "그림",
            "navigation": {},
        },
        "url": link(page, search_pos)["canonical_url"],
        "page": page,
        "search_pos": search_pos,
        "status": "observed" if ids else "empty",
        "layout_status": "fixture_validated",
        "queue_eligible": False,
        "rows": [
            {
                "post_id": str(post_id),
                "canonical_url": f"https://gall.dcinside.com/board/view/?id=fixture&no={post_id}",
                "title": f"title {post_id}",
                "author_raw": "shown author",
                "published_at_raw": "11.15",
                "row_order": index,
            }
            for index, post_id in enumerate(ids)
        ],
        "pagination_candidates": list(links),
        "excluded_rows": [],
        "end_of_results": terminal,
        "pagination_complete": terminal,
    } | overrides


def plan(pages, *, state=EMPTY_STATE, observed_at=NOW, **options):
    return plan_scan(SCOPE, state, pages, observed_at, synthetic_fixture=True, **options)


def established(ids=(100, 99)):
    initial = plan([snapshot(ids)])
    return {
        "generation": 1,
        "baseline": initial["baseline"],
        "checkpoint": initial["checkpoint"],
        "latest_scan": None,
    }


def cycle(pages, *, state=None, **options):
    return plan(
        pages,
        state=established() if state is None else state,
        observed_at=NOW + timedelta(minutes=1),
        **options,
    )


def live_link(page=2, search_pos=None):
    return {
        "canonical_url": build_list_url("normal", "comic_new6", "ai", page, search_pos),
        "page": page,
        "search_pos": search_pos,
    }


def survey_exclusion():
    return {
        "row_order": 0,
        "reason": "survey",
        "number_kind": "survey_label",
        "link_schemes": {"javascript": 1},
        "field_counts": {"number": 1, "author": 0, "date": 0, "title_links": 1},
        "role_flags": {"is_ad": False, "is_pinned": False},
    }


def live_snapshot(ids, *, page=1, search_pos=None, links=(), observed_at=NOW, **overrides):
    """Anonymous synthetic rows with the reviewed twenty-row list shape."""
    result = snapshot(ids, page=page, search_pos=search_pos, links=links)
    result["scope"] |= {"gallery_id": "comic_new6", "keyword": "ai"}
    result["url"] = live_link(page, search_pos)["canonical_url"]
    result["layout_status"] = "site_verified"
    result["observed_at"] = observed_at.isoformat()
    result["excluded_rows"] = [
        survey_exclusion(),
        {
            "row_order": 1,
            "reason": "pinned",
            "number_kind": "notice_label",
            "link_schemes": {"https": 1},
            "field_counts": {"number": 1, "author": 1, "date": 1, "title_links": 1},
            "role_flags": {"is_ad": False, "is_pinned": True},
        },
    ]
    for row in result["rows"]:
        row["row_order"] += 2
        row["canonical_url"] = row["canonical_url"].replace("id=fixture", "id=comic_new6")
    return result | overrides


def live_plan(pages, *, state=EMPTY_STATE, observed_at=NOW, **options):
    return plan_scan(LIVE_SCOPE, state, pages, observed_at, allow_verified_live=True, **options)


def test_first_latest_page_sets_exact_baseline_without_backfill():
    pages = [snapshot([100, 99], links=[link()]), snapshot([98], page=2, terminal=True)]
    result = plan(pages)
    assert result["complete"] is True
    assert result["candidates"] == []
    assert result["baseline"] == result["checkpoint"] | {
        "mode": "new",
        "requires_published_at_filter": True,
    }
    assert result["checkpoint"] == {
        "anchor_ids": ["100", "99"],
        "observed_at": NOW.isoformat(timespec="microseconds"),
        "source_url": pages[0]["url"],
    }
    assert [row["post_id"] for row in result["scan_result"]["observations"]] == ["100", "99"]
    assert all(row["role"] == "baseline" for row in result["scan_result"]["observations"])


def test_empty_first_page_is_a_valid_empty_baseline():
    result = plan([snapshot([], terminal=True)])
    assert result["complete"] is True
    assert result["baseline"]["anchor_ids"] == []
    assert result["candidates"] == []


def test_fixture_evidence_and_explicit_fixture_flag_are_both_required():
    with pytest.raises(WatchPlanError, match="synthetic_fixture"):
        plan_scan(SCOPE, EMPTY_STATE, [snapshot([1])], NOW)
    for overrides in ({"layout_status": "unverified"}, {"queue_eligible": True}):
        with pytest.raises(WatchPlanError, match="fixture-validated"):
            plan([snapshot([1], **overrides)])


def test_reviewed_live_evidence_requires_its_explicit_exclusive_flag():
    page = live_snapshot([100, 99])
    with pytest.raises(WatchPlanError, match="allow_verified_live"):
        plan_scan(LIVE_SCOPE, EMPTY_STATE, [page], NOW)
    with pytest.raises(WatchPlanError, match="fixture-validated"):
        plan_scan(LIVE_SCOPE, EMPTY_STATE, [page], NOW, synthetic_fixture=True)
    with pytest.raises(WatchPlanError, match="site-verified"):
        live_plan([live_snapshot([100], layout_status="fixture_validated")])
    with pytest.raises(WatchPlanError, match="mutually exclusive"):
        live_plan([page], synthetic_fixture=True)
    with pytest.raises(WatchPlanError, match="booleans"):
        plan_scan(LIVE_SCOPE, EMPTY_STATE, [page], NOW, allow_verified_live=1)
    result = live_plan([page])
    assert result["complete"] is True
    assert result["candidates"] == []
    assert result["scan_result"]["layout_status"] == "site_verified"
    assert result["scan_result"]["synthetic_fixture"] is False
    assert result["scan_result"]["queue_eligible"] is False
    assert result["scan_result"]["save_approved"] is False
    with pytest.raises(WatchPlanError, match="non-queueable"):
        live_plan([live_snapshot([100], queue_eligible=True)])


@pytest.mark.parametrize(
    "changes",
    [
        {"gallery_type": "minor"},
        {"gallery_id": "other"},
        {"keyword": "AI"},
        {"search_type": "search_subject"},
    ],
)
def test_live_planning_rejects_every_unreviewed_scope(changes):
    scope = WatchScope(**(LIVE_SCOPE.__dict__ | changes))
    with pytest.raises(WatchPlanError, match="exact reviewed watch scope"):
        plan_scan(scope, EMPTY_STATE, [live_snapshot([100])], NOW, allow_verified_live=True)


def test_live_baseline_partial_scan_and_recent_overlap_use_complete_checkpoint(tmp_path):
    first = live_snapshot(range(300, 280, -1), links=[live_link()])
    second = live_snapshot(range(280, 260, -1), page=2)
    with QueueStore(tmp_path / "reviewed-watch.db") as queue:
        store = WatchStore(queue)
        initial = live_plan([first, second], state=store.get_state(LIVE_SCOPE))
        assert initial["complete"] is True
        assert initial["candidates"] == []
        assert len(initial["scan_result"]["observations"]) == 20
        store.persist_scan(LIVE_SCOPE, **initial)
        baseline = deepcopy(store.get_state(LIVE_SCOPE)["baseline"])
        scan_at = NOW + timedelta(minutes=1)
        pages = [
            live_snapshot(range(302, 282, -1), links=[live_link()], observed_at=scan_at),
            live_snapshot(range(282, 262, -1), page=2, observed_at=scan_at),
        ]
        partial = live_plan(
            pages, state=store.get_state(LIVE_SCOPE), observed_at=scan_at, max_pages=1
        )
        assert partial["complete"] is False
        assert partial["gap_reason"] == "max_pages"
        assert [row["post_id"] for row in partial["candidates"]] == ["302", "301"]
        assert store.persist_scan(LIVE_SCOPE, **partial)["candidates_added"] == 2
        state = store.get_state(LIVE_SCOPE)
        assert state["checkpoint"] == initial["checkpoint"]
        assert state["baseline"] == baseline
        final = live_plan(pages, state=state, observed_at=scan_at)
        assert final["complete"] is True
        assert final["scan_result"]["first_anchor_id"] == "300"
        assert final["scan_result"]["pages"][-1]["end_of_results"] is False
        assert final["scan_result"]["pages"][0]["excluded_rows"] == first["excluded_rows"]
        assert store.persist_scan(LIVE_SCOPE, **final)["candidates_added"] == 0
        assert store.get_state(LIVE_SCOPE)["baseline"] == baseline
        for candidate in store.list_candidates(LIVE_SCOPE):
            assert candidate["shown_metadata"]["baseline_observed_at"] == baseline["observed_at"]
            assert candidate["shown_metadata"]["requires_published_at_filter"] is True
        assert queue.summary()["posts"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"reason": "non_numeric"},
        {"number_kind": "other"},
        {"link_schemes": {"https": 1}},
        {"link_schemes": {"javascript": 1, "https": 1}},
        {"field_counts": {"number": 2, "title_links": 1}},
        {"field_counts": {"number": 1, "title_links": 0}},
        {"role_flags": {"is_ad": False, "is_pinned": True}},
    ],
)
def test_live_unresolved_survey_evidence_blocks_baseline_and_coverage(changes):
    excluded = survey_exclusion() | changes
    page = live_snapshot([104, 100], excluded_rows=[excluded])
    result = live_plan([page])
    assert result["complete"] is False
    assert result["baseline"] is None
    assert result["gap_reason"] == "excluded_rows_unverified"
    baseline = live_plan([live_snapshot([100, 99])])
    state = EMPTY_STATE | {
        "generation": 1,
        "baseline": baseline["baseline"],
        "checkpoint": baseline["checkpoint"],
    }
    result = live_plan([page], state=state)
    assert result["complete"] is False
    assert result["candidates"] == []
    assert result["scan_result"]["pages"][0]["excluded_rows"] == [excluded]


def test_survey_reason_without_exact_evidence_and_live_pinned_without_role_proof_block():
    for exclusion in (
        {"row_order": 0, "reason": "survey"},
        {"row_order": 0, "reason": "pinned"},
        {"row_order": 0, "reason": "ad"},
    ):
        result = live_plan([live_snapshot([100], excluded_rows=[exclusion])])
        assert result["complete"] is False
        assert result["gap_reason"] == "excluded_rows_unverified"
    page = snapshot([100], excluded_rows=[survey_exclusion() | {"row_order": 1}])
    assert plan([page])["complete"] is True


def test_live_terminal_booleans_and_historical_links_do_not_prove_coverage():
    initial = live_plan([live_snapshot([100, 99])])
    state = EMPTY_STATE | {
        "generation": 1,
        "baseline": initial["baseline"],
        "checkpoint": initial["checkpoint"],
    }
    result = live_plan(
        [live_snapshot([104], end_of_results=True, pagination_complete=True)], state=state
    )
    assert result["complete"] is False
    assert result["gap_reason"] == "pagination_missing"
    assert result["scan_result"]["pages"][0]["end_of_results"] is False
    cursor = live_link(1, "-100")
    result = live_plan(
        [live_snapshot([104], links=[cursor]), live_snapshot([100], search_pos="-100")],
        state=state,
    )
    assert result["complete"] is False
    assert result["gap_reason"] == "historical_cursor_unverified"
    assert len(result["scan_result"]["pages"]) == 1


def test_shared_live_scan_clock_accepts_only_aware_reads_within_two_minutes():
    initial = live_plan([live_snapshot([100, 99])])
    state = EMPTY_STATE | {
        "generation": 1,
        "baseline": initial["baseline"],
        "checkpoint": initial["checkpoint"],
    }
    scan_at = NOW + timedelta(minutes=1)
    pages = [
        live_snapshot([104, 100], links=[live_link()], observed_at=scan_at + timedelta(seconds=2)),
        live_snapshot([99, 98], page=2, observed_at=scan_at + timedelta(seconds=30)),
    ]
    for page in pages:
        page["scan_observed_at"] = scan_at.isoformat()
    result = live_plan(pages, state=state, observed_at=scan_at)
    assert result["complete"] is True
    assert result["observed_at"] == scan_at
    for offset in (-1, 121):
        page = live_snapshot([100], observed_at=scan_at + timedelta(seconds=offset))
        page["scan_observed_at"] = scan_at.isoformat()
        with pytest.raises(WatchPlanError, match="outside the scan observation window"):
            live_plan([page], observed_at=scan_at)
    page = live_snapshot([100])
    page["scan_observed_at"] = (NOW + timedelta(seconds=1)).isoformat()
    with pytest.raises(WatchPlanError, match="scan observation date differs"):
        live_plan([page])
    page["scan_observed_at"] = NOW.isoformat()
    page["observed_at"] = NOW.replace(tzinfo=None).isoformat()
    with pytest.raises(WatchPlanError, match="page observed_at"):
        live_plan([page])
    with pytest.raises(WatchPlanError, match="timezone-aware datetime"):
        live_plan([live_snapshot([100])], observed_at=NOW.isoformat())


@pytest.mark.parametrize(
    "status",
    ["missing_list", "ambiguous_list", "unrecognized_empty", "conflicting_empty_marker"],
)
def test_unrecognized_list_evidence_fails_closed(status):
    with pytest.raises(WatchPlanError, match="list evidence"):
        plan([snapshot([], status=status)])


@pytest.mark.parametrize("page,search_pos", [(2, None), (1, "-100")])
def test_every_cycle_starts_at_latest_page_one(page, search_pos):
    with pytest.raises(WatchPlanError, match="latest page 1"):
        cycle([snapshot([104], page=page, search_pos=search_pos)])


def test_candidates_stop_at_exact_anchor_and_overlap_is_observations_only():
    pages = [
        snapshot([104, 103], links=[link()]),
        snapshot([100, 99, 98], page=2, links=[link(3)]),
        snapshot([97], page=3, terminal=True),
    ]
    result = cycle(pages)
    assert result["complete"] is True
    assert result["gap_reason"] is None
    assert result["baseline"] is None
    assert result["checkpoint"]["anchor_ids"] == ["104", "103"]
    assert [row["post_id"] for row in result["candidates"]] == ["104", "103"]
    assert [row["role"] for row in result["scan_result"]["observations"]] == [
        "candidate",
        "candidate",
        "anchor",
        "anchor",
        "overlap_recheck",
        "overlap_recheck",
    ]
    assert result["scan_result"]["first_anchor_id"] == "100"
    assert result["scan_result"]["follow_up"] is None
    for candidate in result["candidates"]:
        assert candidate["shown_metadata"]["requires_published_at_filter"] is True
        assert (
            candidate["shown_metadata"]["baseline_observed_at"]
            == established()["baseline"]["observed_at"]
        )
        assert candidate["shown_metadata"]["published_at_raw"] == "11.15"
        assert "published_at" not in candidate["shown_metadata"]


def test_same_page_rows_after_anchor_do_not_satisfy_required_further_page():
    result = cycle([snapshot([104, 100, 99, 98], links=[link()])])
    assert result["complete"] is False
    assert result["gap_reason"] == "overlap_incomplete"
    assert [row["post_id"] for row in result["candidates"]] == ["104"]
    assert result["scan_result"]["follow_up"] == link()


def test_overlap_page_can_finish_without_claiming_its_absent_links_are_terminal():
    result = cycle(
        [
            snapshot([104, 100], links=[link()]),
            snapshot([99, 98], page=2),
        ]
    )
    assert result["complete"] is True
    assert result["scan_result"]["pages"][-1]["end_of_results"] is False


def test_configured_overlap_requires_that_many_further_pages():
    result = cycle(
        [
            snapshot([104, 100], links=[link()]),
            snapshot([99], page=2, links=[link(3)]),
        ],
        overlap_pages=2,
    )
    assert result["complete"] is False
    assert result["gap_reason"] == "overlap_incomplete"


def test_explicit_terminal_evidence_can_finish_on_first_anchor_page():
    result = cycle([snapshot([104, 100, 98], terminal=True)])
    assert result["complete"] is True
    assert [row["post_id"] for row in result["candidates"]] == ["104"]


def test_numeric_threshold_alone_never_finishes_and_lower_ids_can_be_candidates():
    result = cycle([snapshot([98, 97], links=[link()])])
    assert result["complete"] is False
    assert result["gap_reason"] == "anchor_not_reached"
    assert result["scan_result"]["first_anchor_id"] is None
    assert [row["post_id"] for row in result["candidates"]] == ["98", "97"]
    assert all(
        row["shown_metadata"]["requires_published_at_filter"] for row in result["candidates"]
    )


def test_explicit_end_can_cover_results_when_all_previous_anchors_disappeared():
    result = cycle([snapshot([98, 97], terminal=True)])
    assert result["complete"] is True
    assert [row["post_id"] for row in result["candidates"]] == ["98", "97"]


def test_empty_baseline_remains_ambiguous_until_explicit_end():
    state = established(())
    result = cycle([snapshot([4, 3], links=[link()])], state=state)
    assert result["complete"] is False
    assert result["gap_reason"] == "empty_baseline_requires_end"
    assert all(
        row["shown_metadata"]["requires_published_at_filter"] for row in result["candidates"]
    )
    assert all(row["shown_metadata"]["empty_baseline_ambiguous"] for row in result["candidates"])
    assert cycle([snapshot([4, 3], terminal=True)], state=state)["complete"] is True


def test_absent_links_or_one_terminal_boolean_are_not_end_proof():
    for overrides in ({}, {"end_of_results": True}, {"pagination_complete": True}):
        result = cycle([snapshot([104], **overrides)])
        assert result["complete"] is False
        assert result["gap_reason"] == "pagination_missing"


def test_max_pages_retains_pending_cursor_and_latest_page_anchor_ids():
    result = cycle(
        [
            snapshot([104, 103], links=[link()]),
            snapshot([100], page=2, terminal=True),
        ],
        max_pages=1,
    )
    assert result["complete"] is False
    assert result["gap_reason"] == "max_pages"
    assert result["scan_result"]["last_cursor"] == link(1)
    assert result["scan_result"]["follow_up"] == link()
    assert result["checkpoint"]["anchor_ids"] == ["104", "103"]
    assert [row["post_id"] for row in result["candidates"]] == ["104", "103"]


def test_page_must_be_linked_from_immediately_preceding_page():
    result = cycle(
        [
            snapshot([104], links=[link()]),
            snapshot([100], page=2, links=[link(4)]),
            snapshot([99], page=3, terminal=True),
        ]
    )
    assert result["complete"] is False
    assert result["gap_reason"] == "pagination_unverified"
    assert len(result["scan_result"]["pages"]) == 2


def test_even_an_actual_page_link_cannot_prove_skipped_page_coverage():
    result = cycle(
        [
            snapshot([104], links=[link(5)]),
            snapshot([100], page=5, terminal=True),
        ]
    )
    assert result["complete"] is False
    assert result["gap_reason"] == "pagination_unverified"


@pytest.mark.parametrize("search_pos", ["-100", "100"])
def test_changed_cursor_direction_is_unverified_even_when_actually_linked(search_pos):
    result = cycle(
        [
            snapshot([104], links=[link(1, search_pos)]),
            snapshot([100], page=1, search_pos=search_pos, terminal=True),
        ]
    )
    assert result["complete"] is False
    assert result["gap_reason"] == "historical_cursor_unverified"
    assert len(result["scan_result"]["pages"]) == 1
    assert result["scan_result"]["unverified_cursor_candidates"] == [link(1, search_pos)]


def test_cursor_transition_cannot_skip_an_available_adjacent_page():
    result = cycle(
        [
            snapshot([104], links=[link(), link(1, "-100")]),
            snapshot([100], search_pos="-100", terminal=True),
        ]
    )
    assert result["complete"] is False
    assert result["gap_reason"] == "historical_cursor_unverified"
    assert result["scan_result"]["follow_up"] == link()


def test_pagination_cycle_is_a_gap():
    first = snapshot([104], links=[link()])
    result = cycle([first, snapshot([103], page=2, links=[link(1)]), first])
    assert result["complete"] is False
    assert result["gap_reason"] == "pagination_cycle"


def test_duplicate_boundary_rows_are_observed_but_candidate_ids_are_unique():
    result = cycle(
        [
            snapshot([104, 103], links=[link()]),
            snapshot([103, 102, 100], page=2, links=[link(3)]),
            snapshot([100, 99], page=3),
        ]
    )
    assert result["complete"] is True
    assert [row["post_id"] for row in result["candidates"]] == ["104", "103", "102"]
    assert [row["post_id"] for row in result["scan_result"]["observations"]].count("103") == 2


@pytest.mark.parametrize("ids", [[104, 105], [104, 104], [104, 102, 103]])
def test_unverified_numeric_order_is_a_gap_and_does_not_initialize_baseline(ids):
    result = plan([snapshot(ids)])
    assert result["complete"] is False
    assert result["gap_reason"] == "order_unverified"
    assert result["baseline"] is None
    assert result["candidates"] == []
    assert all(row["role"] == "order_unverified" for row in result["scan_result"]["observations"])


def test_new_rows_cannot_increase_across_page_boundaries():
    result = cycle(
        [
            snapshot([104, 103], links=[link()]),
            snapshot([105, 100], page=2, terminal=True),
        ]
    )
    assert result["complete"] is False
    assert result["gap_reason"] == "order_unverified"
    assert [row["post_id"] for row in result["candidates"]] == ["104", "103"]


@pytest.mark.parametrize(
    "reason",
    [
        "ambiguous_row_fields",
        "ambiguous_post_identity",
        "invalid_post_link",
        "ambiguous_title",
        "post_number_mismatch",
        "missing_title",
        "duplicate_post_id",
        "mixed_gallery_identity",
        "non_numeric",
        "unknown_reason",
    ],
)
def test_unresolved_excluded_rows_block_baseline_and_terminal_checkpoint_advancement(reason):
    page = snapshot([104, 100], terminal=True, excluded_rows=[{"row_order": 2, "reason": reason}])
    initial = plan([page])
    assert initial["complete"] is False
    assert initial["baseline"] is None
    assert initial["gap_reason"] == "excluded_rows_unverified"
    result = cycle([page])
    assert result["complete"] is False
    assert result["gap_reason"] == "excluded_rows_unverified"
    assert result["candidates"] == []
    assert result["scan_result"]["pages"][0]["excluded_rows"] == page["excluded_rows"]
    assert result["scan_result"]["follow_up"] == link(1)
    assert all(
        row["role"] == "excluded_rows_unverified" for row in result["scan_result"]["observations"]
    )


@pytest.mark.parametrize("reason", ["ad", "pinned", "wrong_gallery"])
def test_explicit_safe_exclusions_do_not_block_coverage(reason):
    page = snapshot([104, 100], terminal=True, excluded_rows=[{"row_order": 2, "reason": reason}])
    assert plan([page])["complete"] is True
    assert cycle([page])["complete"] is True
    assert [row["post_id"] for row in cycle([page])["candidates"]] == ["104"]


def test_observed_page_with_only_safe_exclusions_can_establish_empty_baseline():
    page = snapshot([], status="observed", excluded_rows=[{"row_order": 1, "reason": "pinned"}])
    result = plan([page])
    assert result["complete"] is True
    assert result["baseline"]["anchor_ids"] == []


def test_unresolved_exclusions_on_required_overlap_page_keep_the_scan_partial():
    result = cycle(
        [
            snapshot([104, 100], links=[link()]),
            snapshot(
                [99],
                page=2,
                terminal=True,
                excluded_rows=[{"row_order": 1, "reason": "ambiguous_row_fields"}],
            ),
        ]
    )
    assert result["complete"] is False
    assert result["gap_reason"] == "excluded_rows_unverified"
    assert [row["post_id"] for row in result["candidates"]] == ["104"]


@pytest.mark.parametrize(
    "number_raw,number_count,author_count",
    [
        ("103", 1, 2),
        (None, 0, 1),
        (None, 2, 1),
        ("unknown", 1, 1),
        ("0", 1, 1),
        ("103*", 1, 1),
    ],
)
def test_parser_ambiguity_does_not_permanently_skip_a_later_repaired_post(
    tmp_path, number_raw, number_count, author_count
):
    def parsed(when, ambiguous):
        rows = [
            {
                "number_raw": number_raw if ambiguous and post_id == 103 else str(post_id),
                "is_ad": False,
                "is_pinned": False,
                "field_counts": {
                    "number": number_count if ambiguous and post_id == 103 else 1,
                    "author": author_count if ambiguous and post_id == 103 else 1,
                    "date": 1,
                },
                "link_total": 1,
                "links": [
                    {
                        "href": f"https://gall.dcinside.com/board/view/?id=fixture&no={post_id}",
                        "text_raw": f"title {post_id}",
                    }
                ],
                "author_raw": "shown author",
                "published_at_raw": "11.15",
            }
            for post_id in (104, 103, 100)
        ]
        return parse_list_snapshot(
            {
                "document_url": link(1)["canonical_url"],
                "list_count": 1,
                "row_total": 3,
                "rows": rows,
                "empty_marker_count": 0,
                "pagination_total": 0,
                "pagination": [],
                "fixture_end_of_results": True,
            },
            expected_url=link(1)["canonical_url"],
            observed_at=when,
            layout_status="fixture_validated",
        )

    with QueueStore(tmp_path / "ambiguity.db") as queue:
        store = WatchStore(queue)
        store.persist_scan(SCOPE, **plan([snapshot([100])], state=store.get_state(SCOPE)))
        old_checkpoint = deepcopy(store.get_state(SCOPE)["checkpoint"])
        ambiguous = cycle([parsed(NOW + timedelta(minutes=1), True)], state=store.get_state(SCOPE))
        assert ambiguous["complete"] is False
        store.persist_scan(SCOPE, **ambiguous)
        assert store.get_state(SCOPE)["checkpoint"] == old_checkpoint
        repaired = plan(
            [parsed(NOW + timedelta(minutes=2), False)],
            state=store.get_state(SCOPE),
            observed_at=NOW + timedelta(minutes=2),
        )
        assert repaired["complete"] is True
        assert [row["post_id"] for row in repaired["candidates"]] == ["104", "103"]


def test_foreign_noncanonical_or_conflicting_row_identity_fails_closed():
    for url in (
        "https://gall.dcinside.com/board/view/?id=other&no=104",
        "https://gall.dcinside.com/board/view/?id=fixture&no=103",
        "https://gall.dcinside.com/board/view/?id=fixture&no=104&page=1",
        "https://gall.dcinside.com/mgallery/board/view/?id=fixture&no=104",
    ):
        page = snapshot([104])
        page["rows"][0]["canonical_url"] = url
        with pytest.raises(WatchPlanError, match="identity"):
            cycle([page])


@pytest.mark.parametrize(
    "field,value",
    [
        ("keyword", "other"),
        ("gallery_id", "other"),
        ("search_type", "search_name"),
        ("navigation", {"search_head": "1"}),
    ],
)
def test_snapshot_scope_cannot_disagree_with_url(field, value):
    page = snapshot([104])
    page["scope"][field] = value
    with pytest.raises(WatchPlanError, match="scope"):
        cycle([page])


def test_snapshot_and_pagination_cursor_must_agree_with_canonical_url():
    page = snapshot([104])
    page["page"] = 2
    with pytest.raises(WatchPlanError, match="identity"):
        cycle([page])
    page = snapshot([104], links=[link()])
    page["pagination_candidates"][0]["search_pos"] = "-100"
    with pytest.raises(WatchPlanError, match="Pagination candidate"):
        cycle([page])


def test_additional_url_filters_are_not_collapsed_into_watch_identity():
    page = snapshot([104])
    page["url"] += "&search_head=1"
    with pytest.raises(WatchPlanError, match="distinct watch scope"):
        cycle([page])


def test_latest_partial_scan_does_not_supply_coverage_anchors():
    state = established()
    state["latest_scan"] = {"checkpoint": {"anchor_ids": ["104"]}, "complete": False}
    result = cycle([snapshot([105, 104], links=[link()])], state=state)
    assert result["complete"] is False
    assert result["scan_result"]["coverage_anchor_ids"] == ["100", "99"]
    assert [row["post_id"] for row in result["candidates"]] == ["105", "104"]


def test_observation_dates_must_be_aware_and_cannot_precede_baseline():
    with pytest.raises(WatchPlanError, match="timezone-aware"):
        plan([snapshot([1])], observed_at=NOW.replace(tzinfo=None))
    with pytest.raises(WatchPlanError, match="precede"):
        plan([snapshot([104])], state=established(), observed_at=NOW - timedelta(seconds=1))
    page = snapshot([104], observed_at=(NOW + timedelta(minutes=2)).isoformat())
    with pytest.raises(WatchPlanError, match="date differs"):
        cycle([page])


def test_planning_is_deterministic_and_leaves_inputs_unchanged():
    state = established()
    pages = [snapshot([104, 100], links=[link()]), snapshot([99], page=2)]
    original = deepcopy((state, pages))
    assert cycle(pages, state=state) == cycle(pages, state=state)
    assert (state, pages) == original


def test_store_keeps_complete_checkpoint_and_baseline_across_gap_and_retry(tmp_path):
    with QueueStore(tmp_path / "watch.db") as queue:
        store = WatchStore(queue)
        initial = plan([snapshot([100, 99])], state=store.get_state(SCOPE))
        store.persist_scan(SCOPE, **initial)
        state = store.get_state(SCOPE)
        original_baseline = deepcopy(state["baseline"])
        original_checkpoint = deepcopy(state["checkpoint"])
        pages = [
            snapshot([104, 103], links=[link()]),
            snapshot([100, 99], page=2, links=[link(3)]),
            snapshot([98], page=3, terminal=True),
        ]
        partial = cycle(pages, state=state, max_pages=1)
        assert store.persist_scan(SCOPE, **partial)["candidates_added"] == 2
        state = store.get_state(SCOPE)
        assert state["checkpoint"] == original_checkpoint
        assert state["baseline"] == original_baseline
        finished = plan(pages, state=state, observed_at=NOW + timedelta(minutes=2))
        assert store.persist_scan(SCOPE, **finished)["candidates_added"] == 0
        state = store.get_state(SCOPE)
        assert state["checkpoint"]["anchor_ids"] == ["104", "103"]
        assert state["baseline"] == original_baseline
        assert len(store.list_candidates(SCOPE)) == 2
        assert len(store.list_gaps(SCOPE)) == 1
        assert queue.summary()["posts"] == 0


def test_known_candidates_refresh_as_anchors_and_overlap_without_inserting_baseline_posts(tmp_path):
    def pages_with_title(pages, post_id, title):
        for page in pages:
            for row in page["rows"]:
                if row["post_id"] == str(post_id):
                    row["title"] = title
                    row["published_at_raw"] = "updated display date"
        return pages

    with QueueStore(tmp_path / "candidate-refresh.db") as queue:
        store = WatchStore(queue)
        store.persist_scan(SCOPE, **plan([snapshot([100, 99])], state=store.get_state(SCOPE)))
        discovery = cycle(
            [
                snapshot([104, 103], links=[link()]),
                snapshot([100, 99], page=2, links=[link(3)]),
                snapshot([98], page=3),
            ],
            state=store.get_state(SCOPE),
        )
        assert discovery["complete"] is True
        store.persist_scan(SCOPE, **discovery)
        original = {row["post_id"]: row for row in store.list_candidates(SCOPE)}
        assert set(original) == {"104", "103"}
        for minute, candidate_id, title, expected_role, pages in (
            (
                2,
                104,
                "edited anchor title",
                "anchor",
                [snapshot([105, 104], links=[link()]), snapshot([103, 100, 99], page=2)],
            ),
            (
                3,
                103,
                "edited overlap title",
                "overlap_recheck",
                [snapshot([106, 105], links=[link()]), snapshot([104, 103, 100, 99], page=2)],
            ),
        ):
            pages_with_title(pages, candidate_id, title)
            observed_at = NOW + timedelta(minutes=minute)
            scan = plan(pages, state=store.get_state(SCOPE), observed_at=observed_at)
            assert scan["complete"] is True
            assert str(candidate_id) not in {row["post_id"] for row in scan["candidates"]}
            observed = next(
                row
                for row in scan["scan_result"]["observations"]
                if row["post_id"] == str(candidate_id)
            )
            assert observed["role"] == expected_role
            saved = store.persist_scan(SCOPE, **scan)
            current = {row["post_id"]: row for row in store.list_candidates(SCOPE)}
            refreshed = current[str(candidate_id)]
            assert refreshed["title"] == title
            assert refreshed["shown_metadata"]["published_at_raw"] == "updated display date"
            assert refreshed["first_seen_at"] == original[str(candidate_id)]["first_seen_at"]
            assert refreshed["first_scan_id"] == original[str(candidate_id)]["first_scan_id"]
            assert refreshed["last_seen_at"] == observed_at.isoformat(timespec="microseconds")
            assert refreshed["latest_scan_id"] == saved["scan_id"]
            assert not {"100", "99", "98"} & set(current)
        assert queue.summary()["posts"] == 0


def test_foreign_watch_state_cannot_supply_coverage():
    state = established()
    state["watch_name"] = "another watch"
    with pytest.raises(WatchPlanError, match="different scope"):
        cycle([snapshot([104])], state=state)


def test_next_poll_time_uses_finished_time_and_service_delay():
    assert next_poll_at(NOW) == NOW + timedelta(seconds=60)
    assert next_poll_at(NOW, 90) == NOW + timedelta(seconds=90)
    assert next_poll_at(NOW, service_not_before=NOW + timedelta(minutes=3)) == (
        NOW + timedelta(minutes=3)
    )
    assert next_poll_at(NOW, service_not_before=NOW) == NOW + timedelta(seconds=60)


@pytest.mark.parametrize("interval", [0, 59, -1, True, float("inf"), float("nan"), "60"])
def test_poll_interval_cannot_enable_a_fast_or_invalid_loop(interval):
    with pytest.raises(WatchPlanError, match="at least 60"):
        next_poll_at(NOW, interval)
