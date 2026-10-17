"""Pairwise cross-folder results; no connected-component/transitivity inference."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from .models import ImageRecord


class RootRole(StrEnum):
    REFERENCE = "A"
    TARGET = "B"


class CrossDecision(StrEnum):
    UNDECIDED = "undecided"
    KEEP = "keep"
    HOLD = "hold"
    DELETE = "delete"


@dataclass
class CrossMatch:
    reference: ImageRecord
    target: ImageRecord
    kind: str
    distance: int


@dataclass
class CrossCandidate:
    target: ImageRecord
    matches: list[CrossMatch]
    decision: CrossDecision = CrossDecision.UNDECIDED

    @property
    def representative(self) -> CrossMatch:
        return self.matches[0]

    @property
    def similar_only(self) -> bool:
        return all(match.kind == "similar" for match in self.matches)


@dataclass
class CrossResult:
    root_a: Path
    root_b: Path
    recursive_a: bool = False
    recursive_b: bool = False
    threshold: int = 6
    similar: bool = True
    candidates: list[CrossCandidate] = field(default_factory=list)
    scanned_a: int = 0
    scanned_b: int = 0
    discovered: int = 0
    cache_hits: int = 0
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False
