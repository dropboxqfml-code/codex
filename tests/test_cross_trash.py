import os
import shutil
from dataclasses import replace

import pytest

from image_duplicate_finder.cross_models import CrossDecision, RootRole
from image_duplicate_finder.cross_scanner import scan_cross
from image_duplicate_finder.cross_trash import cross_deletion_plan, move_cross_to_trash
from image_duplicate_finder.models import Decision, DuplicateGroup
from image_duplicate_finder.trash import move_to_trash


@pytest.fixture
def cross_result(tmp_path, image_factory):
    a, b = tmp_path / "A", tmp_path / "B"
    source = image_factory("A/original.png")
    b.mkdir()
    shutil.copyfile(source, b / "copy.png")
    return scan_cross(a, b)


def test_confirmation_required_and_only_explicit_delete_moves(cross_result):
    c = cross_result.candidates[0]
    for decision in (CrossDecision.UNDECIDED, CrossDecision.KEEP, CrossDecision.HOLD):
        c.decision = decision
        assert not move_cross_to_trash(
            cross_result, confirmed=True, trash=lambda _: pytest.fail()
        ).moved
    c.decision = CrossDecision.DELETE
    with pytest.raises(ValueError, match="명시적인"):
        move_cross_to_trash(cross_result, trash=lambda _: pytest.fail())
    calls = []
    outcome = move_cross_to_trash(cross_result, confirmed=True, trash=calls.append)
    assert calls == [str(c.target.path)]
    assert outcome.moved == [c.target.path]
    assert c.representative.reference.path.exists()


@pytest.mark.parametrize("bypass", ["role", "path", "single_service"])
def test_reference_protection_in_service_api(cross_result, bypass):
    c = cross_result.candidates[0]
    c.decision = CrossDecision.DELETE
    if bypass == "role":
        c.target.root_role = RootRole.REFERENCE
    elif bypass == "path":
        c.target.path = c.representative.reference.path
    else:
        a = c.representative.reference
        a.decision = Decision.DELETE
        c.target.decision = Decision.KEEP
        with pytest.raises(ValueError, match="보호된"):
            move_to_trash(
                [DuplicateGroup([a, c.target])],
                confirmed=True,
                trash=lambda _: pytest.fail("A must not move"),
            )
        return
    with pytest.raises(ValueError):
        move_cross_to_trash(cross_result, confirmed=True, trash=lambda _: pytest.fail())


@pytest.mark.parametrize("side", ["A", "B"])
@pytest.mark.parametrize("change", ["missing", "content", "same_metadata"])
def test_changed_or_missing_evidence_and_target_blocked(cross_result, side, change):
    c = cross_result.candidates[0]
    c.decision = CrossDecision.DELETE
    record = c.target if side == "B" else c.representative.reference
    if change == "missing":
        record.path.unlink()
    elif change == "content":
        record.path.write_bytes(b"changed")
    else:
        stat = record.path.stat()
        data = bytearray(record.path.read_bytes())
        data[-1] ^= 1
        record.path.write_bytes(data)
        os.utime(record.path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    outcome = move_cross_to_trash(cross_result, confirmed=True, trash=lambda _: pytest.fail())
    assert not outcome.moved and len(outcome.errors) == 1


def test_alternative_valid_reference_can_support_move(cross_result):
    a, b = cross_result.root_a, cross_result.root_b
    shutil.copyfile(a / "original.png", a / "second.png")
    result = scan_cross(a, b)
    c = result.candidates[0]
    c.decision = CrossDecision.DELETE
    c.matches[0].reference.path.unlink()
    calls = []
    outcome = move_cross_to_trash(result, confirmed=True, trash=calls.append)
    assert len(c.matches) == 2 and len(calls) == len(outcome.moved) == 1


def test_duplicate_target_recycled_once(cross_result):
    c = cross_result.candidates[0]
    c.decision = CrossDecision.DELETE
    cross_result.candidates.append(c)
    calls = []
    assert len(cross_deletion_plan(cross_result)) == 1
    outcome = move_cross_to_trash(cross_result, confirmed=True, trash=calls.append)
    assert len(outcome.moved) == len(calls) == 1


def test_failure_stops_following_targets_and_no_permanent_delete(cross_result):
    a, b = cross_result.root_a, cross_result.root_b
    shutil.copyfile(b / "copy.png", b / "copy2.png")
    result = scan_cross(a, b)
    for c in result.candidates:
        c.decision = CrossDecision.DELETE
    calls = []

    def unavailable(path):
        calls.append(path)
        raise OSError("Recycle Bin unavailable")

    outcome = move_cross_to_trash(result, confirmed=True, trash=unavailable)
    assert len(calls) == len(outcome.errors) == len(outcome.skipped) == 1
    assert not outcome.moved
    assert all(c.target.path.exists() for c in result.candidates)


def test_similar_requires_additional_consent(cross_result):
    c = cross_result.candidates[0]
    c.decision = CrossDecision.DELETE
    c.matches[0].kind = "similar"
    with pytest.raises(ValueError, match="추가 확인"):
        move_cross_to_trash(cross_result, confirmed=True, trash=lambda _: pytest.fail())
    calls = []
    outcome = move_cross_to_trash(
        cross_result, confirmed=True, similar_confirmed=True, trash=calls.append
    )
    assert len(outcome.moved) == len(calls) == 1


def test_cancelled_result_and_precancelled_move_are_safe(cross_result):
    from threading import Event

    cross_result.candidates[0].decision = CrossDecision.DELETE
    with pytest.raises(ValueError, match="취소된"):
        cross_deletion_plan(replace(cross_result, cancelled=True))
    cancel = Event()
    cancel.set()
    outcome = move_cross_to_trash(
        cross_result, cancel=cancel, confirmed=True, trash=lambda _: pytest.fail()
    )
    assert outcome.cancelled and not outcome.moved


def test_replaced_path_symlink_is_rejected(cross_result):
    c = cross_result.candidates[0]
    c.decision = CrossDecision.DELETE
    c.target.path.unlink()
    try:
        c.target.path.symlink_to(c.representative.reference.path)
    except OSError:
        pytest.skip("symlink unavailable")
    with pytest.raises(ValueError):
        move_cross_to_trash(cross_result, confirmed=True, trash=lambda _: pytest.fail())


@pytest.mark.parametrize("invalid_consent", [False, 1, "yes"])
def test_weak_alternative_cannot_bypass_additional_confirmation(cross_result, invalid_consent):
    c = cross_result.candidates[0]
    c.decision = CrossDecision.DELETE
    weak_path = cross_result.root_a / "alternative.png"
    shutil.copyfile(c.representative.reference.path, weak_path)
    # Read the real identity, rather than reusing the first file's inode.
    from threading import Event

    from image_duplicate_finder.scanner import read_image

    weak = read_image(weak_path, Event())
    weak.root_role = RootRole.REFERENCE
    c.matches.append(replace(c.representative, reference=weak, kind="similar"))
    c.representative.reference.path.unlink()
    calls = []
    outcome = move_cross_to_trash(
        cross_result, confirmed=True, similar_confirmed=invalid_consent, trash=calls.append
    )
    assert not calls and outcome.errors
    outcome = move_cross_to_trash(
        cross_result, confirmed=True, similar_confirmed=True, trash=calls.append
    )
    assert len(outcome.moved) == len(calls) == 1


@pytest.mark.parametrize("side", ["A", "B"])
def test_service_checks_nonrecursive_scan_boundaries(cross_result, side):
    from threading import Event

    from image_duplicate_finder.scanner import read_image

    c = cross_result.candidates[0]
    original = c.target if side == "B" else c.representative.reference
    sub = original.path.parent / "nested"
    sub.mkdir()
    new_path = sub / original.path.name
    shutil.copyfile(original.path, new_path)
    nested = read_image(new_path, Event())
    nested.root_role = original.root_role
    if side == "B":
        c.target = nested
        c.matches[0].target = nested
    else:
        c.matches[0].reference = nested
    c.decision = CrossDecision.DELETE
    with pytest.raises(ValueError, match="하위 폴더"):
        move_cross_to_trash(cross_result, confirmed=True, trash=lambda _: pytest.fail())
