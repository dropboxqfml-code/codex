from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

from .models import Decision, DuplicateGroup, ImageRecord
from .recycling import recycle_file
from .scanner import file_sha256, stat_signature


@dataclass
class TrashResult:
    moved: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


def deletion_plan(groups: list[DuplicateGroup]) -> list[ImageRecord]:
    targets = []
    seen = set()
    for group in groups:
        selected = [r for r in group.images if r.decision == Decision.DELETE]
        if selected and not any(r.decision == Decision.KEEP for r in group.images):
            raise ValueError("삭제할 그룹마다 최소 한 장을 ‘보관’으로 지정하세요")
        for record in selected:
            if record.path not in seen:
                targets.append(record)
                seen.add(record.path)
    return targets


def verify_unchanged(record: ImageRecord, cancel: Event) -> None:
    # Reject replaced files, symlinks (including swapped ancestor directories), and edits.
    if any(p.is_symlink() or p.is_junction() for p in [record.path, *record.path.parents]):
        raise ValueError("경로가 심볼릭 링크로 변경되었습니다. 다시 검색하세요")
    if stat_signature(record.path.stat()) != record.signature:
        raise ValueError("파일 정보가 변경되었습니다. 다시 검색하세요")
    if file_sha256(record.path, cancel) != record.sha256:
        raise ValueError("파일 내용이 변경되었습니다. 다시 검색하세요")
    if stat_signature(record.path.stat()) != record.signature:
        raise ValueError("검증 중 파일이 변경되었습니다. 다시 검색하세요")


def move_to_trash(
    groups: list[DuplicateGroup],
    cancel: Event | None = None,
    progress: Callable[[str, int, int], None] | None = None,
    trash: Callable[[str], None] | None = None,
) -> TrashResult:
    from .scanner import Cancelled

    cancel = cancel if cancel is not None else Event()
    progress = progress or (lambda *_: None)
    trash = trash or recycle_file
    targets = deletion_plan(groups)
    result = TrashResult()
    try:
        for index, record in enumerate(targets, 1):
            if cancel.is_set():
                raise Cancelled
            try:
                # Revalidate explicit keepers before each removal, as well as the target.
                group = next(g for g in groups if record in g.images)
                for keeper in group.images:
                    if keeper.decision == Decision.KEEP:
                        verify_unchanged(keeper, cancel)
                verify_unchanged(record, cancel)
                if cancel.is_set():
                    raise Cancelled
                trash(str(record.path))
                result.moved.append(record.path)
            except (OSError, ValueError) as error:
                result.errors.append(f"{record.path}: {error}")
            progress("휴지통 이동", index, len(targets))
    except Cancelled:
        result.cancelled = True
    return result
