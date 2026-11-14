"""Pure scheduling policy. Callers must persist returned times and attempt counts."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from image_monitor.paths import aware

DELAYS = (15, 30, 60, 120, 300, 1800, 7200)


def retry_after(value: str | None, observed_at: datetime) -> datetime | None:
    aware(observed_at)
    if value is None:
        return None
    value = value.strip()
    if value.isascii() and value.isdigit():
        try:
            return observed_at + timedelta(seconds=int(value))
        except OverflowError as error:
            raise ValueError("Retry-After exceeds supported timestamp range") from error
    try:
        return max(aware(parsedate_to_datetime(value)), observed_at)
    except (ValueError, TypeError, OverflowError):
        return None


@dataclass(frozen=True)
class RetryDecision:
    status: str
    next_retry_at: datetime | None
    reason: str


def schedule_retry(
    *,
    attempt_count: int,
    first_failure_at: datetime,
    now: datetime,
    jitter_fraction: float,
    server_not_before: datetime | None = None,
    service_not_before: datetime | None = None,
) -> RetryDecision:
    """attempt_count includes the just-failed network attempt, initially one.

    UI/session/disk failures must not call this function or consume network attempts.
    jitter_fraction is an injected random sample in [0, .2], allowing deterministic tests.
    """
    aware(now)
    aware(first_failure_at)
    if attempt_count < 1 or not 0 <= jitter_fraction <= 0.2 or first_failure_at > now:
        raise ValueError("Invalid retry inputs")
    constraints = [aware(t) for t in (server_not_before, service_not_before) if t is not None]
    deadline = first_failure_at + timedelta(hours=24)
    if attempt_count >= 8 or now >= deadline:
        return RetryDecision("manual_review", None, "automatic_retry_limit")
    target = (
        max(
            now + timedelta(seconds=DELAYS[attempt_count - 1] * (1 + jitter_fraction)),
            *constraints,
        )
        if constraints
        else now + timedelta(seconds=DELAYS[attempt_count - 1] * (1 + jitter_fraction))
    )
    if target >= deadline:
        return RetryDecision("manual_review", None, "wait_exceeds_retry_deadline")
    status = "retry_wait" if attempt_count <= 5 else "deferred"
    return RetryDecision(status, target, "network_failure")
