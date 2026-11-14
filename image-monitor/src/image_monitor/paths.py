"""Deterministic Windows-safe path planning, independent of the host OS."""

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo("Asia/Seoul")
RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in "123456789¹²³"
}


def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return value


def component(raw: str) -> str:
    """Always suffix raw input to distinguish sanitization and case-only collisions."""
    if not raw:
        raise ValueError("Empty path component")
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw).rstrip(" .")
    cleaned = cleaned[:40].rstrip(" .") or "_"
    if cleaned.split(".")[0].upper() in RESERVED:
        cleaned = "_" + cleaned
    suffix = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{cleaned}~{suffix}"


@dataclass(frozen=True)
class FolderPlan:
    folder_date: str
    folder_date_basis: str
    fallback_reason: str | None
    relative_directory: str
    timezone: str = "Asia/Seoul"

    def to_dict(self) -> dict:
        return asdict(self)


def plan_folder(
    *,
    watch_name: str,
    gallery_id: str,
    post_id: str,
    nickname: str,
    ip_display: str | None,
    first_seen_at: datetime,
    published_at: datetime | None = None,
    basis: str = "published_at",
) -> FolderPlan:
    if basis not in {"published_at", "first_seen_at"}:
        raise ValueError("Unsupported folder date basis")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", gallery_id):
        raise ValueError("Invalid gallery ID")
    if gallery_id.upper() in RESERVED:
        raise ValueError("Gallery ID is a reserved Windows path name")
    if not re.fullmatch(r"[0-9]{1,20}", post_id):
        raise ValueError("Invalid post ID")
    aware(first_seen_at)
    if published_at is not None:
        aware(published_at)
    fallback = basis == "published_at" and published_at is None
    actual_basis = "first_seen_at" if fallback else basis
    timestamp = published_at if actual_basis == "published_at" else first_seen_at
    date = aware(timestamp).astimezone(SEOUL).date().isoformat()
    author = f"{nickname}({ip_display})" if ip_display else nickname
    relative = str(
        PurePosixPath(component(watch_name), gallery_id, date, component(author), post_id)
    )
    return FolderPlan(
        date, actual_basis, "published_at_unavailable" if fallback else None, relative
    )


def destination(root: Path, plan: FolderPlan) -> Path:
    """Reject traversal, symlink escapes, and paths exceeding a conservative Windows budget."""
    relative = PurePosixPath(plan.relative_directory)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {".", ".."} or "\\" in part or ":" in part for part in relative.parts)
    ):
        raise ValueError("Unsafe relative directory")
    resolved_root = root.resolve()
    result = resolved_root.joinpath(*relative.parts).resolve()
    if not result.is_relative_to(resolved_root):
        raise ValueError("Path escapes storage root")
    # Reserve room for a sequential filename; count UTF-16 units as Windows does.
    if len(str(result).encode("utf-16-le")) // 2 + 16 > 240:
        raise ValueError("Storage root/path too long; choose a shorter root")
    return result
