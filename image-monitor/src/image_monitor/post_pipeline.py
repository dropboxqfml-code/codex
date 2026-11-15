"""Connect a validated DOM observation to durable jobs, without starting a saver."""

from datetime import datetime

from image_monitor.queue import ImageDiscovery, PostDiscovery, QueueStore


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
    observed = datetime.fromisoformat(snapshot["observed_at"])
    post = PostDiscovery(
        post_id=snapshot["post_id"],
        nickname=snapshot["nickname"],
        ip_display=snapshot.get("ip_display"),
        first_seen_at=observed,
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
