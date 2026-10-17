import os
import shutil
from threading import Event

import pytest

from image_duplicate_finder.models import Decision
from image_duplicate_finder.scanner import read_image, scan
from image_duplicate_finder.storage import ReviewStore
from image_duplicate_finder.trash import deletion_plan, move_to_trash


@pytest.fixture
def reviewed_group(tmp_path, image_factory):
    first = image_factory()
    shutil.copyfile(first, tmp_path / "copy.png")
    group = scan(tmp_path).groups[0]
    group.images[0].decision = Decision.KEEP
    group.images[1].decision = Decision.DELETE
    return group


def test_sqlite_round_trip_and_changed_content(tmp_path, image_factory):
    path = image_factory()
    record = read_image(path, Event())
    db = tmp_path / "data" / "reviews.sqlite3"
    with ReviewStore(db) as store:
        assert store.get(record) == Decision.HOLD
        store.set(record, Decision.KEEP)
    with ReviewStore(db) as store:
        assert store.get(record) == Decision.KEEP
        image_factory(variant=5)
        assert store.get(read_image(path, Event())) == Decision.HOLD


def test_scan_restores_saved_decisions(tmp_path, reviewed_group):
    db = tmp_path / "reviews.sqlite3"
    with ReviewStore(db) as store:
        for record in reviewed_group.images:
            store.set(record, record.decision)
    result = scan(tmp_path, database=db)
    assert [r.decision for r in result.groups[0].images] == [Decision.KEEP, Decision.DELETE]


def test_requires_explicit_keep_and_never_moves_hold(reviewed_group):
    keep, delete = reviewed_group.images
    keep.decision = Decision.HOLD
    calls = []
    with pytest.raises(ValueError, match="보관"):
        move_to_trash([reviewed_group], trash=calls.append)
    assert calls == []
    keep.decision = Decision.KEEP
    assert deletion_plan([reviewed_group]) == [delete]
    result = move_to_trash([reviewed_group], trash=calls.append)
    assert calls == [str(delete.path)]
    assert result.moved == [delete.path]
    assert keep.path.exists()


@pytest.mark.parametrize("which", [0, 1])
def test_changed_keeper_or_target_prevents_removal(reviewed_group, which):
    reviewed_group.images[which].path.write_bytes(b"changed")
    calls = []
    result = move_to_trash([reviewed_group], trash=calls.append)
    assert calls == []
    assert result.moved == []
    assert len(result.errors) == 1


def test_sha_check_catches_same_size_and_restored_timestamp(reviewed_group):
    record = reviewed_group.images[1]
    stat = record.path.stat()
    data = bytearray(record.path.read_bytes())
    data[-1] ^= 1
    record.path.write_bytes(data)
    os.utime(record.path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    calls = []
    result = move_to_trash([reviewed_group], trash=calls.append)
    assert not calls
    assert "내용이 변경" in result.errors[0]


def test_missing_keeper_is_not_ignored(reviewed_group):
    reviewed_group.images[0].path.unlink()
    result = move_to_trash([reviewed_group], trash=lambda _: pytest.fail("must not move"))
    assert len(result.errors) == 1
    assert not result.moved


def test_trash_failure_has_no_unlink_fallback(reviewed_group):
    def unavailable(_):
        raise OSError("trash unavailable")

    result = move_to_trash([reviewed_group], trash=unavailable)
    assert not result.moved
    assert "trash unavailable" in result.errors[0]
    assert all(r.path.exists() for r in reviewed_group.images)


def test_trash_cancellation_between_files(tmp_path, reviewed_group):
    source = reviewed_group.images[0].path
    third = tmp_path / "third.png"
    shutil.copyfile(source, third)
    record = read_image(third, Event())
    record.decision = Decision.DELETE
    reviewed_group.images.append(record)
    cancelled = Event()
    calls = []

    def move(path):
        calls.append(path)
        cancelled.set()

    result = move_to_trash([reviewed_group], cancel=cancelled, trash=move)
    assert result.cancelled
    assert len(result.moved) == len(calls) == 1


def test_symlink_target_rejected(reviewed_group, tmp_path):
    target = reviewed_group.images[1]
    target.path.unlink()
    try:
        target.path.symlink_to(reviewed_group.images[0].path)
    except OSError:
        pytest.skip("symlink creation unavailable")
    result = move_to_trash([reviewed_group], trash=lambda _: pytest.fail("must not move"))
    assert "심볼릭" in result.errors[0]
