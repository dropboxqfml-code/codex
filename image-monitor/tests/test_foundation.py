import errno
import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image

from image_monitor.paths import FolderPlan, component, destination, plan_folder
from image_monitor.retry import retry_after, schedule_retry
from image_monitor.validation import VerificationError, VerificationIncomplete, verify_image

NOW = datetime(2026, 11, 14, 14, 59, tzinfo=UTC)


def plan(**overrides):
    return plan_folder(
        **(
            {
                "watch_name": "만화",
                "gallery_id": "comic_new6",
                "post_id": "123456",
                "nickname": "ㅇㅇ",
                "ip_display": "123.45",
                "first_seen_at": NOW,
                "published_at": NOW - timedelta(days=1),
            }
            | overrides
        )
    )


def test_date_basis_and_missing_published_date():
    assert plan().folder_date == "2026-11-13"
    fallback = plan(published_at=None)
    assert fallback.folder_date == "2026-11-14"
    assert fallback.folder_date_basis == "first_seen_at"
    assert fallback.fallback_reason == "published_at_unavailable"
    assert plan(basis="first_seen_at").folder_date == "2026-11-14"
    assert (
        plan(first_seen_at=NOW + timedelta(minutes=2), published_at=None).folder_date
        == "2026-11-15"
    )


def test_path_reconstruction_preserves_assigned_date(tmp_path):
    assigned = plan()
    restored = FolderPlan(**assigned.to_dict())
    assert destination(tmp_path, restored) == destination(tmp_path, assigned)
    parts = restored.relative_directory.split("/")
    assert parts[1:3] == ["comic_new6", "2026-11-13"]
    assert parts[-1] == "123456"


@pytest.mark.parametrize("raw", ["CON", "nul.txt", "COM¹", "a/../b", "a:b", "..", "x. ", "한글😀"])
def test_windows_safe_components(raw):
    name = component(raw)
    assert not any(c in name for c in '<>:"/\\|?*')
    assert not name.endswith((" ", "."))
    assert name.split(".")[0].upper() not in {"CON", "NUL", "COM¹"}
    assert name == component(raw)


def test_sanitized_and_case_only_collisions():
    assert component("a:b") != component("a?b")
    assert component("Alice").casefold() != component("alice").casefold()


@pytest.mark.parametrize("relative", ["../escape", "/absolute", "a\\..\\b", "C:/escape"])
def test_reject_unsafe_restored_path(tmp_path, relative):
    with pytest.raises(ValueError):
        destination(tmp_path, FolderPlan("2026-11-14", "first_seen_at", None, relative))


def test_symlink_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    try:
        (root / "link").symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        if (
            isinstance(error, NotImplementedError)
            or getattr(error, "winerror", None) == 1314
            or getattr(error, "errno", None)
            in {errno.EPERM, errno.EACCES, errno.ENOSYS, errno.EOPNOTSUPP}
        ):
            pytest.skip("Creating symlinks is not permitted in this environment")
        raise
    with pytest.raises(ValueError, match="escapes"):
        destination(root, FolderPlan("2026-11-14", "first_seen_at", None, "link/escape"))


@pytest.mark.parametrize(
    "override",
    [{"gallery_id": "../bad"}, {"post_id": "../1"}, {"first_seen_at": NOW.replace(tzinfo=None)}],
)
def test_reject_bad_identifiers_and_naive_dates(override):
    with pytest.raises(ValueError):
        plan(**override)


@pytest.mark.parametrize("gallery_id", ["CON", "con", "NUL", "aux", "PRN", "COM1", "lpt9"])
def test_reject_reserved_gallery_path_names(gallery_id):
    with pytest.raises(ValueError, match="reserved Windows"):
        plan(gallery_id=gallery_id)


def test_retry_after_formats_and_invalid_value():
    assert retry_after("600", NOW) == NOW + timedelta(seconds=600)
    assert retry_after("Sat, 14 Nov 2026 15:59:00 GMT", NOW) == NOW + timedelta(hours=1)
    assert retry_after("nonsense", NOW) is None
    assert retry_after("-3", NOW) is None


@pytest.mark.parametrize(
    "attempt,delay,status",
    [
        (1, 15, "retry_wait"),
        (2, 30, "retry_wait"),
        (3, 60, "retry_wait"),
        (4, 120, "retry_wait"),
        (5, 300, "retry_wait"),
        (6, 1800, "deferred"),
        (7, 7200, "deferred"),
    ],
)
def test_retry_schedule(attempt, delay, status):
    result = schedule_retry(
        attempt_count=attempt, first_failure_at=NOW, now=NOW, jitter_fraction=0.2
    )
    assert result.status == status
    assert result.next_retry_at == NOW + timedelta(seconds=delay * 1.2)


def test_server_and_service_wait_are_never_capped():
    result = schedule_retry(
        attempt_count=1,
        first_failure_at=NOW,
        now=NOW,
        jitter_fraction=0,
        server_not_before=NOW + timedelta(hours=8),
        service_not_before=NOW + timedelta(hours=9),
    )
    assert result.next_retry_at == NOW + timedelta(hours=9)
    assert (
        schedule_retry(
            attempt_count=1,
            first_failure_at=NOW,
            now=NOW,
            jitter_fraction=0,
            server_not_before=NOW + timedelta(days=2),
        ).status
        == "manual_review"
    )


def test_attempt_and_age_limits():
    assert (
        schedule_retry(attempt_count=8, first_failure_at=NOW, now=NOW, jitter_fraction=0).status
        == "manual_review"
    )
    assert (
        schedule_retry(
            attempt_count=1, first_failure_at=NOW, now=NOW + timedelta(days=1), jitter_fraction=0
        ).status
        == "manual_review"
    )


def test_file_format_from_bytes_and_no_modification(tmp_path):
    path = tmp_path / "browser-name.png"
    Image.new("RGB", (24, 16), "red").save(path, format="WEBP")
    original = path.read_bytes()
    result = verify_image(path, writer_finished=True)
    assert result.detected_format == "WEBP"
    assert result.extension == "webp"
    assert (result.width, result.height, result.frames) == (24, 16, 1)
    assert result.sha256 == hashlib.sha256(original).hexdigest()
    assert path.read_bytes() == original


def test_writer_must_be_finished(tmp_path):
    with pytest.raises(VerificationIncomplete, match="completion"):
        verify_image(tmp_path / "unfinished", writer_finished=False)


@pytest.mark.parametrize("data", [b"", b"<html>Busy</html>", b"\x89PNG\r\n\x1a\n"])
def test_reject_empty_error_page_and_truncated_data(tmp_path, data):
    path = tmp_path / "bad.png"
    path.write_bytes(data)
    with pytest.raises(VerificationError):
        verify_image(path, writer_finished=True)


def test_animation_and_limits(tmp_path):
    path = tmp_path / "animated.gif"
    first = Image.new("RGB", (24, 16), "red")
    second = Image.new("RGB", (24, 16), "blue")
    first.save(path, save_all=True, append_images=[second], duration=100)
    assert verify_image(path, writer_finished=True).frames == 2
    with pytest.raises(VerificationIncomplete):
        verify_image(path, writer_finished=True, max_frames=1)
    with pytest.raises(VerificationIncomplete):
        verify_image(path, writer_finished=True, max_pixels=10)


def test_truncated_pixel_data_fails_decode(tmp_path):
    path = tmp_path / "broken.bmp"
    Image.new("RGB", (100, 100)).save(path)
    path.write_bytes(path.read_bytes()[:-100])
    with pytest.raises(VerificationError):
        verify_image(path, writer_finished=True)
