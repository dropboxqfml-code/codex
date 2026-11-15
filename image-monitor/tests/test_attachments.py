import json
from dataclasses import FrozenInstanceError

import pytest

from image_monitor.attachments import AttachmentInfo, BodyReference, match_attachment


def attachment(key="attachment-a", filename="원본 그림.png", *, identity="file-a", complete=True):
    return AttachmentInfo(key, filename, complete, identity)


def assert_unmatched(result, status, reason):
    assert result["original_attachment_filename"] is None
    assert result["original_filename_match_status"] == status
    assert result["original_filename_match_method"] is None
    assert result["original_filename_match_reason"] == reason


def test_exact_shared_identifier_matches_public_name_without_path_conversion():
    filename = "../원본 <그림> & 'quoted'.PNG"
    result = match_attachment(BodyReference(identity="file-a"), [attachment(filename=filename)])
    assert result["original_attachment_filename"] == filename
    assert result["original_filename_match_status"] == "matched"
    assert result["original_filename_match_method"] == "shared_file_identifier"
    assert result["original_filename_match_reason"] is None
    assert json.loads(json.dumps(result, ensure_ascii=False)) == result


def test_explicit_dom_reference_can_match_when_inventory_identity_is_missing():
    result = match_attachment(
        BodyReference(attachment_key="attachment-a"), [attachment(identity=None)]
    )
    assert result["original_attachment_filename"] == "원본 그림.png"
    assert result["original_filename_match_method"] == "explicit_dom_reference"


def test_exact_dom_reference_disambiguates_repeated_identity():
    inventory = [attachment(), attachment("attachment-b", "other.png")]
    result = match_attachment(
        BodyReference(identity="file-a", attachment_key="attachment-b"), inventory
    )
    assert result["original_attachment_filename"] == "other.png"
    assert result["original_filename_match_method"] == "explicit_dom_reference"


@pytest.mark.parametrize("duplicate_name", ["원본 그림.png", "other.png"])
def test_repeated_identity_is_ambiguous_even_if_names_are_equal(duplicate_name):
    inventory = [attachment(), attachment("attachment-b", duplicate_name)]
    result = match_attachment(BodyReference(identity="file-a"), inventory)
    assert_unmatched(result, "ambiguous", "duplicate_shared_identifier")
    assert len(result["candidates"]) == 2


def test_duplicate_dom_reference_is_not_disambiguated_by_filename_or_identity():
    inventory = [attachment(), attachment(identity="file-b")]
    result = match_attachment(
        BodyReference(identity="file-a", attachment_key="attachment-a"), inventory
    )
    assert_unmatched(result, "ambiguous", "duplicate_attachment_reference")
    assert len(result["candidates"]) == 2


def test_conflicting_body_identity_does_not_silently_prefer_dom_reference():
    inventory = [attachment(), attachment("attachment-b", "other.png", identity="file-b")]
    result = match_attachment(
        BodyReference(identity="file-b", attachment_key="attachment-a"), inventory
    )
    assert_unmatched(result, "ambiguous", "attachment_reference_identity_conflict")
    assert [entry["key"] for entry in result["candidates"]] == ["attachment-a", "attachment-b"]


def test_reference_identity_conflict_is_preserved_without_alternative_candidate():
    result = match_attachment(
        BodyReference(identity="file-b", attachment_key="attachment-a"), [attachment()]
    )
    assert_unmatched(result, "ambiguous", "attachment_reference_identity_conflict")


def test_unidentified_referenced_entry_does_not_hide_identity_of_another_attachment():
    inventory = [attachment(identity=None), attachment("attachment-b", identity="file-b")]
    result = match_attachment(
        BodyReference(identity="file-b", attachment_key="attachment-a"), inventory
    )
    assert_unmatched(result, "ambiguous", "attachment_reference_identity_conflict")


def test_missing_dom_reference_does_not_fall_back_to_an_identity_of_another_entry():
    result = match_attachment(
        BodyReference(identity="file-a", attachment_key="missing"), [attachment()]
    )
    assert_unmatched(result, "ambiguous", "attachment_reference_identity_conflict")


@pytest.mark.parametrize("count", [1, 2])
def test_equal_counts_or_order_never_supply_missing_evidence(count):
    inventory = [attachment(f"attachment-{index}", identity=None) for index in range(count)]
    result = match_attachment(BodyReference(), inventory)
    assert_unmatched(result, "ambiguous", "no_verifiable_correspondence")
    assert len(result["candidates"]) == count


def test_inventory_order_does_not_change_the_selected_attachment():
    inventory = [attachment(), attachment("attachment-b", "second.gif", identity="file-b")]
    body = BodyReference(identity="file-b")
    assert match_attachment(body, inventory) == match_attachment(body, list(reversed(inventory)))


def test_a_missing_identifier_match_is_not_declared_external():
    result = match_attachment(BodyReference(identity="different"), [attachment()])
    assert_unmatched(result, "unavailable", "shared_identifier_not_found")


def test_a_missing_reference_is_unavailable_without_identity_evidence():
    result = match_attachment(BodyReference(attachment_key="missing"), [attachment()])
    assert_unmatched(result, "unavailable", "attachment_reference_not_found")


@pytest.mark.parametrize("filename", [None, "", "   "])
def test_a_unique_attachment_with_missing_name_is_unavailable(filename):
    result = match_attachment(BodyReference(identity="file-a"), [attachment(filename=filename)])
    assert_unmatched(result, "unavailable", "attachment_filename_missing")
    assert result["candidates"][0]["filename"] == filename


def test_truncated_name_is_retained_as_candidate_and_never_used_as_original_name():
    result = match_attachment(
        BodyReference(identity="file-a"), [attachment(filename="긴 파일…", complete=False)]
    )
    assert_unmatched(result, "unavailable", "attachment_filename_incomplete")
    assert result["candidates"][0]["filename"] == "긴 파일…"


def test_a_verified_complete_filename_can_literally_contain_ellipsis():
    result = match_attachment(
        BodyReference(identity="file-a"), [attachment(filename="literal...name.png")]
    )
    assert result["original_attachment_filename"] == "literal...name.png"


def test_missing_inventory_is_unavailable():
    assert_unmatched(
        match_attachment(BodyReference(), []), "unavailable", "attachment_inventory_unavailable"
    )


def test_explicit_external_classification_is_required_for_not_applicable():
    result = match_attachment(BodyReference(external=True), [attachment()])
    assert_unmatched(result, "not_applicable", "explicit_external_image")


@pytest.mark.parametrize(
    "body",
    [
        BodyReference(identity="file-a", external=True),
        BodyReference(attachment_key="attachment-a", external=True),
        BodyReference(attachment_key="missing", external=True),
    ],
)
def test_external_classification_does_not_discard_internal_attachment_evidence(body):
    result = match_attachment(body, [attachment()])
    assert_unmatched(result, "ambiguous", "external_attachment_evidence_conflict")


def test_inventory_and_repeated_body_uses_are_preserved():
    inventory = [attachment(), attachment("attachment-b", "unused.png", identity="file-b")]
    before = list(inventory)
    first = match_attachment(BodyReference(identity="file-a"), inventory)
    second = match_attachment(BodyReference(identity="file-a"), inventory)
    assert first == second
    assert inventory == before
    assert len(inventory) == 2
    with pytest.raises(FrozenInstanceError):
        inventory[0].filename = "changed.png"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: AttachmentInfo("", "name.png", True),
        lambda: AttachmentInfo("a", 123, True),
        lambda: AttachmentInfo("a", "name.png", 1),
        lambda: AttachmentInfo("a", "name.png", True, " "),
        lambda: BodyReference(identity=""),
        lambda: BodyReference(attachment_key=""),
        lambda: BodyReference(external=1),
    ],
)
def test_invalid_evidence_is_rejected_at_the_adapter_boundary(factory):
    with pytest.raises(ValueError):
        factory()
