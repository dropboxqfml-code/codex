from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Decision(StrEnum):
    KEEP = "keep"
    HOLD = "hold"
    DELETE = "delete"


@dataclass
class ImageRecord:
    path: Path
    size: int
    mtime_ns: int
    device: int
    inode: int
    width: int
    height: int
    sha256: str
    pixel_hash: str
    phash: int
    thumbnail: bytes = b""
    decision: Decision = Decision.HOLD

    @property
    def signature(self) -> tuple[int, int, int, int]:
        return self.size, self.mtime_ns, self.device, self.inode


@dataclass
class DuplicateGroup:
    images: list[ImageRecord]
    # A connected group may contain similarity chains; not every pair must match.
    kinds: set[str] = field(default_factory=set)


@dataclass
class ScanResult:
    groups: list[DuplicateGroup] = field(default_factory=list)
    scanned: int = 0
    discovered: int = 0
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False
