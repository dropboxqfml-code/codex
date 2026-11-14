"""Read-only validation of a completed local staging file; never downloads or rewrites."""

import hashlib
import os
import stat
import time
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

EXTENSIONS = {
    "PNG": "png",
    "JPEG": "jpg",
    "WEBP": "webp",
    "GIF": "gif",
    "BMP": "bmp",
    "TIFF": "tiff",
}


class VerificationError(ValueError):
    pass


class VerificationIncomplete(VerificationError):
    """Limits or unsupported formats need review, not an automatic corruption label."""


@dataclass(frozen=True)
class VerifiedImage:
    detected_format: str
    extension: str
    file_size: int
    sha256: str
    width: int
    height: int
    frames: int

    def to_dict(self) -> dict:
        return asdict(self)


def _file_state(info: os.stat_result) -> tuple[int, ...]:
    """Bind metadata to the opened file, excluding atime changed by our own reads."""
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def verify_image(
    path: Path,
    *,
    writer_finished: bool,
    max_bytes: int = 256 * 1024 * 1024,
    max_pixels: int = 80_000_000,
    max_frames: int = 300,
    max_seconds: float = 30,
) -> VerifiedImage:
    """writer_finished must come from the saver, not just a stable size or closed dialog.

    This verifies local bytes only. It cannot establish correspondence to a body element.
    The deadline is checked between Pillow operations, not a hard decoder process limit.
    """
    if not writer_finished:
        raise VerificationIncomplete("Writer completion has not been confirmed")
    if min(max_bytes, max_pixels, max_frames, max_seconds) <= 0:
        raise ValueError("Verification limits must be positive")
    start = time.monotonic()
    try:
        initial_path = path.lstat()
        if stat.S_ISLNK(initial_path.st_mode):
            raise VerificationError("Staging file must not be a symbolic link")
        if not stat.S_ISREG(initial_path.st_mode):
            raise VerificationError("Staging file must be a regular file")
        with path.open("rb") as stream, warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            before = os.fstat(stream.fileno())
            if _file_state(before) != _file_state(initial_path):
                raise VerificationIncomplete("File changed before verification")
            if not before.st_size:
                raise VerificationError("Empty file")
            if before.st_size > max_bytes:
                raise VerificationIncomplete("File exceeds byte limit")
            with Image.open(stream) as image:
                fmt = image.format
                if fmt not in EXTENSIONS:
                    raise VerificationIncomplete("Unsupported image format")
                image.verify()
            # Reopen for decoding, because verify invalidates the first Image object.
            stream.seek(0)
            with Image.open(stream) as image:
                width, height = image.size
                frames = getattr(image, "n_frames", 1)
                if frames > max_frames or width * height * frames > max_pixels:
                    raise VerificationIncomplete("Frame/pixel budget exceeded")
                pixels = 0
                for index in range(frames):
                    image.seek(index)
                    pixels += image.width * image.height
                    if pixels > max_pixels or time.monotonic() - start > max_seconds:
                        raise VerificationIncomplete("Decode budget exceeded")
                    image.load()
            stream.seek(0)
            digest = hashlib.sha256()
            while block := stream.read(1024 * 1024):
                if time.monotonic() - start > max_seconds:
                    raise VerificationIncomplete("Verification time budget exceeded")
                digest.update(block)
            after = os.fstat(stream.fileno())
            final_path = path.lstat()
            if _file_state(before) != _file_state(after) or _file_state(after) != _file_state(
                final_path
            ):
                raise VerificationIncomplete("File changed during verification")
            return VerifiedImage(
                fmt, EXTENSIONS[fmt], after.st_size, digest.hexdigest(), width, height, frames
            )
    except UnidentifiedImageError as error:
        raise VerificationIncomplete(
            "Unrecognized image data; review format or error response"
        ) from error
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise VerificationIncomplete("Image exceeds Pillow safety budget") from error
    except SyntaxError as error:
        raise VerificationError("Image structure verification failed") from error
    except OSError as error:
        raise VerificationError("File access or image decoding failed") from error
