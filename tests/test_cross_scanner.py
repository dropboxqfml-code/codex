import os
import random
import shutil
from dataclasses import replace
from threading import Event

import pytest
from PIL import Image

from image_duplicate_finder.cross_models import CrossDecision, RootRole
from image_duplicate_finder.cross_scanner import HammingIndex, scan_cross, validate_roots
from image_duplicate_finder.cross_storage import CrossStore
from image_duplicate_finder.scanner import read_image


@pytest.fixture
def roots(tmp_path):
    a, b = tmp_path / "기준 A", tmp_path / "대상 B"
    a.mkdir()
    b.mkdir()
    return a, b


@pytest.fixture
def matching(roots, image_factory):
    a, b = roots
    source = image_factory("기준 A/original.png")
    shutil.copyfile(source, b / "다른 이름.bin")
    return a, b


def test_byte_match_different_names_extensions_and_default_state(matching):
    result = scan_cross(*matching)
    assert (result.scanned_a, result.scanned_b) == (1, 1)
    assert len(result.candidates) == 1
    c = result.candidates[0]
    assert c.decision == CrossDecision.UNDECIDED
    assert c.representative.kind == "file"
    assert c.target.root_role == RootRole.TARGET
    assert c.representative.reference.root_role == RootRole.REFERENCE


def test_pixels_compression_and_resizing(roots, image_factory):
    a, b = roots
    source = image_factory("기준 A/original.png")
    with Image.open(source) as im:
        im.save(b / "same.bmp")
        im.resize((48, 36)).save(b / "compressed.jpg", quality=80)
    result = scan_cross(a, b, threshold=8)
    by_name = {c.target.path.name: c for c in result.candidates}
    assert by_name["same.bmp"].representative.kind == "pixel"
    assert by_name["compressed.jpg"].representative.kind == "similar"
    assert by_name["compressed.jpg"].representative.distance <= 8
    assert not scan_cross(a, b, similar=False).candidates[0].similar_only
    assert len(scan_cross(a, b, similar=False).candidates) == 1


@pytest.mark.parametrize("side", ["기준 A", "대상 B"])
def test_intra_folder_duplicates_never_reported(roots, image_factory, side):
    a, b = roots
    source = image_factory(f"{side}/one.png")
    shutil.copyfile(source, source.with_name("two.png"))
    other = b if side == "기준 A" else a
    # Nonmatching generated texture, not another flat image (pHash flat-image collision).
    image = Image.frombytes("RGB", (96, 72), random.Random(37).randbytes(96 * 72 * 3))
    image.save(other / "unrelated.png")
    result = scan_cross(a, b)
    assert result.candidates == []


def test_multiple_references_one_target_priority_and_no_transitivity(matching, image_factory):
    a, b = matching
    image_factory("기준 A/second.png")
    with Image.open(a / "original.png") as im:
        im.save(a / "same.bmp")
        im.save(a / "compressed.jpg", quality=80)
    result = scan_cross(a, b, threshold=8)
    assert len(result.candidates) == 1
    matches = result.candidates[0].matches
    assert [m.kind for m in matches] == ["file", "file", "pixel", "similar"]
    assert all(m.target.path.parent == b and m.reference.path.parent == a for m in matches)
    assert len({m.reference.path for m in matches}) == 4


def test_phash_zero_is_only_similar_for_different_pixels(roots):
    a, b = roots
    Image.new("RGB", (50, 40), "white").save(a / "white.png")
    Image.new("RGB", (50, 40), "gray").save(b / "gray.png")
    result = scan_cross(a, b, threshold=0)
    assert result.candidates[0].representative.kind == "similar"
    assert result.candidates[0].representative.distance == 0


@pytest.mark.parametrize("which", ["same", "nested_a", "nested_b"])
def test_equal_overlapping_paths_blocked(roots, which):
    a, b = roots
    if which == "same":
        b = a / ".." / a.name
    elif which == "nested_a":
        b = a / "child"
        b.mkdir()
    else:
        a = b / "child"
        a.mkdir()
    with pytest.raises(ValueError, match="상위·하위"):
        validate_roots(a, b)


@pytest.mark.parametrize(
    "ra,rb,count", [(False, False, 0), (True, False, 0), (False, True, 0), (True, True, 1)]
)
def test_independent_recursion(roots, image_factory, ra, rb, count):
    a, b = roots
    source = image_factory("기준 A/sub/nested.png")
    (b / "sub").mkdir()
    shutil.copyfile(source, b / "sub" / "copy.png")
    result = scan_cross(a, b, recursive_a=ra, recursive_b=rb)
    assert len(result.candidates) == count
    assert result.scanned_a == int(ra)
    assert result.scanned_b == int(rb)


def test_corrupt_animation_and_large_images_are_errors(roots, image_factory, monkeypatch):
    a, b = roots
    image_factory("기준 A/good.png")
    (b / "broken.png").write_bytes(b"broken")
    (b / "readme.txt").write_text("ordinary text")
    Image.new("RGB", (10, 10)).save(
        b / "animated.gif", save_all=True, append_images=[Image.new("RGB", (10, 10), "red")]
    )
    result = scan_cross(a, b)
    assert len(result.errors) == 2
    with pytest.raises(ValueError, match="리소스"):
        read_image(a / "good.png", Event(), max_pixels=100)


def test_cancel_during_matching_offers_no_partial_results(matching):
    cancel = Event()

    def progress(phase, current, total):
        if phase.startswith("B 이미지"):
            cancel.set()

    result = scan_cross(*matching, cancel=cancel, progress=progress)
    assert result.cancelled and not result.candidates


def test_symlink_and_shared_hardlink_excluded(matching):
    a, b = matching
    try:
        (b / "linked.png").symlink_to(a / "original.png")
        os.link(a / "original.png", b / "hard.png")
    except OSError:
        pytest.skip("link creation unavailable")
    result = scan_cross(a, b)
    assert len(result.candidates) == 1
    assert len(result.errors) == 2
    with pytest.raises(ValueError):
        validate_roots(b / "linked.png", a)


def test_permission_error_recorded_without_aborting(matching, monkeypatch):
    from image_duplicate_finder import cross_scanner

    a, b = matching
    original = cross_scanner.file_sha256

    def denied(path, cancel):
        if path.parent == b:
            raise PermissionError("test permission denied")
        return original(path, cancel)

    monkeypatch.setattr(cross_scanner, "file_sha256", denied)
    result = scan_cross(a, b, database=a.parent / "db.sqlite3")
    assert not result.candidates
    assert "permission denied" in result.errors[0]


def test_bk_tree_matches_exhaustive_oracle_and_duplicate_buckets():
    rng, cancel = random.Random(101), Event()
    values = [rng.getrandbits(64) for _ in range(500)] + [123, 123]
    values += [(1 << bits) - 1 for bits in range(65)]
    tree = HammingIndex()
    for i, value in enumerate(values):
        tree.add(value, i, cancel)
    for value in [0, 123, *values[:15], *values[-10:]]:
        for radius in [0, 3, 6, 12]:
            expected = {i for i, h in enumerate(values) if (h ^ value).bit_count() <= radius}
            assert set(tree.query(value, radius, cancel)) == expected


def test_cache_avoids_decode_but_rehashes_and_scopes_review(matching, tmp_path, monkeypatch):
    from image_duplicate_finder import cross_scanner

    db = tmp_path / "state/reviews.sqlite3"
    result = scan_cross(*matching, database=db)
    c = result.candidates[0]
    with CrossStore(db) as store:
        store.set_cross(result, c, CrossDecision.HOLD)
    monkeypatch.setattr(cross_scanner, "read_image", lambda *_a, **_kw: pytest.fail("cache miss"))
    cached = scan_cross(*matching, database=db)
    assert cached.cache_hits == 2
    assert cached.candidates[0].decision == CrossDecision.HOLD
    # A threshold-only change reuses analyses, but not the review context.
    changed = scan_cross(*matching, database=db, threshold=3)
    assert changed.cache_hits == 2
    assert changed.candidates[0].decision == CrossDecision.UNDECIDED
    data = db.read_bytes()
    assert str(c.target.path).encode() not in data
    assert c.target.sha256.encode() not in data
    assert b"cross_cache" in data


def test_changed_file_same_metadata_invalidates_cache_and_decision(matching, tmp_path):
    db = tmp_path / "db.sqlite3"
    first = scan_cross(*matching, database=db)
    c = first.candidates[0]
    with CrossStore(db) as store:
        store.set_cross(first, c, CrossDecision.KEEP)
    stat = c.target.path.stat()
    content = bytearray(c.target.path.read_bytes())
    content[-1] ^= 1  # A PNG trailer edit keeps decoded pixels, but changes SHA.
    c.target.path.write_bytes(content)
    os.utime(c.target.path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    second = scan_cross(*matching, database=db)
    assert second.cache_hits == 1
    assert second.candidates[0].representative.kind == "pixel"
    assert second.candidates[0].decision == CrossDecision.UNDECIDED


def test_delete_queue_never_restored_and_swapped_scope_not_restored(matching, tmp_path):
    db = tmp_path / "db.sqlite3"
    result = scan_cross(*matching, database=db)
    c = result.candidates[0]
    with CrossStore(db) as store:
        store.set_cross(result, c, CrossDecision.DELETE)
        assert store.get_cross(result, c) == CrossDecision.UNDECIDED
        store.set_cross(result, c, CrossDecision.KEEP)
        assert store.get_cross(result, c) == CrossDecision.KEEP
        assert (
            store.get_cross(replace(result, root_a=result.root_b, root_b=result.root_a), c)
            == CrossDecision.UNDECIDED
        )


@pytest.mark.parametrize("value", [-1, 13, 64])
def test_cross_threshold_restricted(roots, value):
    with pytest.raises(ValueError, match="0~12"):
        scan_cross(*roots, threshold=value)


def test_long_unicode_space_paths_and_many_candidates(roots, image_factory):
    a, b = roots
    source = image_factory("기준 A/original.png")
    nested = b
    for i in range(5):
        nested /= f"한글 공백 {i} " + "x" * 45
    nested.mkdir(parents=True)
    for i in range(80):
        shutil.copyfile(source, nested / f"다른 이름 {i}.bin")
    result = scan_cross(a, b, recursive_b=True)
    assert len(result.candidates) == 80
    assert not result.errors
    assert all(c.representative.kind == "file" for c in result.candidates)


def test_result_limit_aborts_without_returning_partial_deletion_candidates(matching, monkeypatch):
    from image_duplicate_finder import cross_scanner

    monkeypatch.setattr(cross_scanner, "MAX_MATCH_PAIRS", 0)
    with pytest.raises(cross_scanner.ResultLimitError, match="매칭 쌍"):
        scan_cross(*matching)


def test_changed_reference_invalidates_restored_review_even_when_another_matches(
    matching, tmp_path
):
    a, b = matching
    shutil.copyfile(a / "original.png", a / "alternative.png")
    db = tmp_path / "state.sqlite3"
    result = scan_cross(a, b, database=db)
    c = result.candidates[0]
    with CrossStore(db) as store:
        store.set_cross(result, c, CrossDecision.KEEP)
    (a / "original.png").unlink()
    rescanned = scan_cross(a, b, database=db)
    assert rescanned.candidates[0].decision == CrossDecision.UNDECIDED
    assert len(rescanned.candidates[0].matches) == 1


def test_windows_case_aliases_are_the_same_root(roots):
    import sys

    if sys.platform != "win32":
        pytest.skip("Windows path case semantics")
    a, _ = roots
    with pytest.raises(ValueError, match="상위·하위"):
        validate_roots(a, type(a)(str(a).swapcase()))


def test_cache_cannot_write_inside_protected_or_target_folder(matching):
    for root in matching:
        database = root / "state" / "reviews.sqlite3"
        with pytest.raises(ValueError, match="A/B 폴더 밖"):
            scan_cross(*matching, database=database)
        assert not database.parent.exists()
