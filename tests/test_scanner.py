import os
import shutil
from dataclasses import replace
from threading import Event

import pytest
from PIL import Image

from image_duplicate_finder.scanner import group_images, read_image, scan


def test_identical_bytes_with_unrelated_extension_and_thumbnail(tmp_path, image_factory):
    original = image_factory()
    renamed = tmp_path / "renamed.bin"
    shutil.copyfile(original, renamed)
    progress = []
    result = scan(tmp_path, progress=lambda *args: progress.append(args))
    assert result.scanned == 2
    assert len(result.groups) == 1
    assert result.groups[0].kinds == {"file", "pixel", "similar"}
    first, second = result.groups[0].images
    assert first.sha256 == second.sha256
    assert first.thumbnail.startswith(b"\x89PNG")
    assert (first.width, first.height) == (96, 72)
    assert first.size == original.stat().st_size
    assert any(phase == "이미지 분석" and n == total == 2 for phase, n, total in progress)


def test_pixel_equality_across_formats(tmp_path, image_factory):
    png = image_factory()
    with Image.open(png) as image:
        image.save(tmp_path / "other.bmp")
    result = scan(tmp_path)
    group = result.groups[0]
    assert "pixel" in group.kinds
    assert "file" not in group.kinds
    assert group.images[0].sha256 != group.images[1].sha256
    assert group.images[0].pixel_hash == group.images[1].pixel_hash


def test_jpeg_recompression_is_similar(tmp_path, image_factory):
    png = image_factory()
    with Image.open(png) as image:
        image.save(tmp_path / "compressed.jpg", quality=75)
    result = scan(tmp_path, threshold=8)
    assert len(result.groups) == 1
    assert result.groups[0].kinds == {"similar"}


def test_alpha_is_part_of_pixel_equality(tmp_path):
    first = Image.new("RGBA", (20, 20), (255, 0, 0, 100))
    second = Image.new("RGBA", (20, 20), (255, 0, 0, 200))
    first.save(tmp_path / "a.png")
    second.save(tmp_path / "b.png")
    result = scan(tmp_path)
    assert "pixel" not in result.groups[0].kinds


def test_exif_orientation_normalizes_pixels(tmp_path, image_factory):
    png = image_factory()
    with Image.open(png) as image:
        exif = Image.Exif()
        exif[274] = 6
        image.transpose(Image.Transpose.ROTATE_90).save(tmp_path / "rotated.png", exif=exif)
    result = scan(tmp_path)
    assert len(result.groups) == 1
    assert "pixel" in result.groups[0].kinds


def test_recursive_and_non_images_and_corrupt(tmp_path, image_factory):
    original = image_factory()
    nested = image_factory("child/another.png")
    (tmp_path / "notes.txt").write_text("not an image")
    (tmp_path / "broken.png").write_bytes(b"broken")
    shallow = scan(tmp_path, recursive=False)
    assert shallow.scanned == 1
    assert shallow.groups == []
    assert len(shallow.errors) == 1
    recursive = scan(tmp_path)
    assert recursive.scanned == 2
    assert {r.path for r in recursive.groups[0].images} == {original, nested}


def test_animated_image_excluded(tmp_path):
    frames = [Image.new("RGB", (12, 12), c) for c in ("red", "blue")]
    frames[0].save(tmp_path / "animated.gif", save_all=True, append_images=frames[1:])
    result = scan(tmp_path)
    assert result.scanned == 0
    assert len(result.errors) == 1
    assert "다중 페이지" in result.errors[0]


def test_symlinks_not_followed(tmp_path, image_factory):
    original = image_factory()
    try:
        (tmp_path / "link.png").symlink_to(original)
        (tmp_path / "loop").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    assert scan(tmp_path).scanned == 1


def test_cancellation_before_and_during_analysis(tmp_path, image_factory):
    image_factory()
    image_factory("second.png")
    cancelled = Event()
    cancelled.set()
    assert scan(tmp_path, cancel=cancelled).cancelled
    cancelled.clear()

    def progress(phase, current, total):
        if phase == "이미지 분석":
            cancelled.set()

    result = scan(tmp_path, cancel=cancelled, progress=progress)
    assert result.cancelled
    assert result.scanned == 1
    assert result.groups == []


def test_similarity_threshold_and_transitive_groups(image_factory):
    record = read_image(image_factory(), Event())
    a = replace(record, sha256="a", pixel_hash="a", phash=0)
    b = replace(record, sha256="b", pixel_hash="b", phash=1)
    c = replace(record, sha256="c", pixel_hash="c", phash=3)
    assert group_images([a, b, c], 0, Event(), lambda *_: None) == []
    group = group_images([a, b, c], 1, Event(), lambda *_: None)
    assert len(group) == 1
    assert len(group[0].images) == 3
    assert (a.phash ^ c.phash).bit_count() == 2
    assert group[0].kinds == {"similar"}


def test_comparison_cancellation(image_factory):
    from image_duplicate_finder.scanner import Cancelled

    record = read_image(image_factory(), Event())
    records = [replace(record, phash=i, sha256=str(i), pixel_hash=str(i)) for i in range(100)]
    cancelled = Event()

    def progress(*_):
        cancelled.set()

    with pytest.raises(Cancelled):
        group_images(records, 1, cancelled, progress)


@pytest.mark.parametrize("threshold", [-1, 65])
def test_invalid_threshold(tmp_path, threshold):
    with pytest.raises(ValueError):
        scan(tmp_path, threshold=threshold)


def test_file_change_during_read_is_rejected(image_factory, monkeypatch):
    from image_duplicate_finder import scanner

    path = image_factory()
    real_hash = scanner.file_sha256

    def changed(path, cancel):
        value = real_hash(path, cancel)
        os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 10_000))
        return value

    monkeypatch.setattr(scanner, "file_sha256", changed)
    with pytest.raises(ValueError, match="변경"):
        read_image(path, Event())
