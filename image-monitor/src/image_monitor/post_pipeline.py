"""Connect a validated DOM observation to durable jobs, without starting a saver."""

from datetime import datetime
from typing import TYPE_CHECKING

from image_monitor.queue import ImageDiscovery, PostDiscovery, QueueStore

if TYPE_CHECKING:
    from image_monitor.candidate_save_policy import CandidateSavePermit


class PostPipelineError(ValueError):
    pass


def enqueue_snapshot(
    store: QueueStore,
    snapshot: dict,
    *,
    watch_name: str,
    keyword: str,
    search_type: str = "search_subject_memo",
    synthetic_fixture: bool = False,
) -> dict:
    """The watch scope is caller supplied; this is not evidence of a search-list match."""
    layout = snapshot.get("layout_status")
    if snapshot.get("queue_eligible") is not True:
        raise PostPipelineError("The observation is not eligible for image jobs")
    if layout == "fixture_validated":
        if not synthetic_fixture:
            raise PostPipelineError("Synthetic observations require explicit fixture mode")
    elif layout != "site_verified":
        raise PostPipelineError("An unverified site layout must not enter the save queue")
    return _persist_snapshot(
        store,
        snapshot,
        watch_name=watch_name,
        keyword=keyword,
        search_type=search_type,
    )


def enqueue_candidate_snapshot(
    store: QueueStore, snapshot: dict, *, permit: "CandidateSavePermit"
) -> dict:
    """Queue one previously inspected candidate through its explicit frozen permit."""
    from image_monitor.candidate_save_policy import CandidateSavePermit

    if not isinstance(permit, CandidateSavePermit):
        raise PostPipelineError("A reviewed candidate save permit is required")
    authorized = permit.authorize_snapshot(snapshot)
    return _persist_snapshot(
        store,
        authorized,
        watch_name=permit.watch_name,
        keyword=permit.keyword,
        search_type=permit.search_type,
        first_seen_at=permit.first_seen_at,
    )


def _persist_snapshot(
    store,
    snapshot,
    *,
    watch_name,
    keyword,
    search_type,
    first_seen_at=None,
):
    observed = datetime.fromisoformat(snapshot["observed_at"])
    post = PostDiscovery(
        post_id=snapshot["post_id"],
        nickname=snapshot["nickname"],
        ip_display=snapshot.get("ip_display"),
        first_seen_at=observed if first_seen_at is None else first_seen_at,
        published_at=(
            datetime.fromisoformat(snapshot["published_at"])
            if snapshot.get("published_at")
            else None
        ),
        title=snapshot.get("title"),
        post_url=snapshot["post_url"],
    )
    images = [
        ImageDiscovery(
            stable_key=image["stable_key"],
            body_order=image["body_order"],
            display_url=image["display_url"],
            service_scope="dcinside",
        )
        for image in snapshot["images"]
    ]
    return store.persist_post_snapshot(
        watch_name=watch_name,
        gallery_type=snapshot["gallery_type"],
        gallery_id=snapshot["gallery_id"],
        keyword=keyword,
        search_type=search_type,
        post=post,
        images=images,
        snapshot=snapshot,
        observed_at=observed,
    )
