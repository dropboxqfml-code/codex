"""Match public attachment names using explicit, verified DOM evidence only.

The caller must obtain identities and references from a validated site adapter.
This module does not derive identifiers from URLs, compare filenames, consume
inventory entries or infer correspondence from their count or display order.
"""

from collections.abc import Sequence
from dataclasses import asdict, dataclass


def _optional_identifier(value: str | None, name: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{name} must be a nonempty string or None")


@dataclass(frozen=True)
class AttachmentInfo:
    """One public DOM inventory entry; filenames remain metadata, never paths."""

    key: str
    filename: str | None
    filename_complete: bool
    identity: str | None = None

    def __post_init__(self):
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("key must be a nonempty string")
        if self.filename is not None and not isinstance(self.filename, str):
            raise ValueError("filename must be a string or None")
        if type(self.filename_complete) is not bool:
            raise ValueError("filename_complete must be a boolean")
        _optional_identifier(self.identity, "identity")


@dataclass(frozen=True)
class BodyReference:
    """Verified body-image evidence, with optional explicit external classification."""

    identity: str | None = None
    attachment_key: str | None = None
    external: bool = False

    def __post_init__(self):
        _optional_identifier(self.identity, "identity")
        _optional_identifier(self.attachment_key, "attachment_key")
        if type(self.external) is not bool:
            raise ValueError("external must be a boolean")


def match_attachment(body: BodyReference, inventory: Sequence[AttachmentInfo]) -> dict:
    """Return a JSON-safe name result; uncertainty never blocks the body image.

    An explicit DOM reference takes precedence over a nonunique shared identity,
    provided its known identity does not conflict. Duplicate references remain
    ambiguous even if their names happen to be equal. Missing or incomplete
    names never replace a native dialog's suggested filename.
    """
    if not isinstance(body, BodyReference):
        raise TypeError("body must be a BodyReference")
    entries = tuple(inventory)
    if any(not isinstance(entry, AttachmentInfo) for entry in entries):
        raise TypeError("inventory must contain AttachmentInfo entries")

    references = [entry for entry in entries if entry.key == body.attachment_key]
    identities = [
        entry for entry in entries if body.identity is not None and entry.identity == body.identity
    ]

    def result(status, reason, candidates, method=None):
        return {
            "original_attachment_filename": (
                candidates[0].filename if status == "matched" else None
            ),
            "original_filename_match_status": status,
            "original_filename_match_method": method if status == "matched" else None,
            "original_filename_match_reason": reason,
            "original_filename_match_evidence": {
                "body_reference": asdict(body),
                "candidate_keys": [entry.key for entry in candidates],
                "candidate_identities": [entry.identity for entry in candidates],
            },
            "candidates": [asdict(entry) for entry in candidates],
        }

    if body.external:
        if body.attachment_key is not None or identities:
            candidates = [entry for entry in entries if entry in references or entry in identities]
            return result("ambiguous", "external_attachment_evidence_conflict", candidates)
        return result("not_applicable", "explicit_external_image", [])

    if body.attachment_key is not None:
        if not references:
            if identities:
                return result("ambiguous", "attachment_reference_identity_conflict", identities)
            return result("unavailable", "attachment_reference_not_found", [])
        if len(references) != 1:
            return result("ambiguous", "duplicate_attachment_reference", references)
        candidate = references[0]
        if body.identity is not None and (
            (candidate.identity is not None and candidate.identity != body.identity)
            or (candidate.identity is None and identities)
        ):
            candidates = [entry for entry in entries if entry in references or entry in identities]
            return result("ambiguous", "attachment_reference_identity_conflict", candidates)
        candidates, method = references, "explicit_dom_reference"
    elif body.identity is not None:
        if not identities:
            return result("unavailable", "shared_identifier_not_found", [])
        if len(identities) != 1:
            return result("ambiguous", "duplicate_shared_identifier", identities)
        candidates, method = identities, "shared_file_identifier"
    elif entries:
        return result("ambiguous", "no_verifiable_correspondence", entries)
    else:
        return result("unavailable", "attachment_inventory_unavailable", [])

    candidate = candidates[0]
    if candidate.filename is None or not candidate.filename.strip():
        return result("unavailable", "attachment_filename_missing", candidates)
    if not candidate.filename_complete:
        return result("unavailable", "attachment_filename_incomplete", candidates)
    return result("matched", None, candidates, method)
