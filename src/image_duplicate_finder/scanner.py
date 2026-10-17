import hashlib
import io
import os
import warnings
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from threading import Event

import imagehash
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import DuplicateGroup, ImageRecord, ScanResult
from .storage import ReviewStore

# Inspect all regular files by content, even when the extension is missing or misleading.
# Animated/multi-page formats are deliberately excluded from this first version.
Progress = Callable[[str, int, int], None]


class Cancelled(Exception):
    pass


def check_cancel(cancel: Event) -> None:
    if cancel.is_set():
        raise Cancelled


def stat_signature(stat: os.stat_result) -> tuple[int, int, int, int]:
    return stat.st_size, stat.st_mtime_ns, stat.st_dev, stat.st_ino


def file_sha256(path: Path, cancel: Event) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            check_cancel(cancel)
            digest.update(chunk)
    check_cancel(cancel)
    return digest.hexdigest()


def read_image(path: Path, cancel: Event) -> ImageRecord:
    check_cancel(cancel)
    before = path.stat(follow_symlinks=False)
    if path.is_symlink():
        raise ValueError("심볼릭 링크는 검색하지 않습니다")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as source:
            if getattr(source, "n_frames", 1) != 1:
                raise ValueError("애니메이션·다중 페이지 이미지는 지원하지 않습니다")
            normalized = ImageOps.exif_transpose(source).convert("RGBA")
            check_cancel(cancel)
            width, height = normalized.size
            digest = hashlib.sha256(f"{width}x{height}:RGBA:".encode())
            digest.update(normalized.tobytes())
            # Composite alpha on white for visual similarity; pixel equality retains alpha.
            visual = Image.new("RGBA", normalized.size, "white")
            visual.alpha_composite(normalized)
            visual = visual.convert("RGB")
            perceptual = int(str(imagehash.phash(visual, hash_size=8)), 16)
            visual.thumbnail((160, 120))
            thumbnail = io.BytesIO()
            visual.save(thumbnail, format="PNG")
    checksum = file_sha256(path, cancel)
    after = path.stat(follow_symlinks=False)
    if stat_signature(before) != stat_signature(after) or path.is_symlink():
        raise ValueError("검색 중 파일이 변경되었습니다")
    return ImageRecord(
        path=path,
        size=before.st_size,
        mtime_ns=before.st_mtime_ns,
        device=before.st_dev,
        inode=before.st_ino,
        width=width,
        height=height,
        sha256=checksum,
        pixel_hash=digest.hexdigest(),
        phash=perceptual,
        thumbnail=thumbnail.getvalue(),
    )


def group_images(
    records: list[ImageRecord], threshold: int, cancel: Event, progress: Progress
) -> list[DuplicateGroup]:
    if not 0 <= threshold <= 64:
        raise ValueError("pHash 거리는 0~64여야 합니다")
    parent = list(range(len(records)))
    kinds: dict[int, set[str]] = {i: set() for i in parent}

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def join(left, right, kind):
        a, b = root(left), root(right)
        if a != b:
            parent[b] = a
            kinds[a].update(kinds[b])
        kinds[a].add(kind)

    # Exact comparisons are linear using hash indexes.
    for attribute, kind in [("sha256", "file"), ("pixel_hash", "pixel")]:
        seen = {}
        for i, record in enumerate(records):
            check_cancel(cancel)
            key = getattr(record, attribute)
            if key in seen:
                join(seen[key], i, kind)
            else:
                seen[key] = i

    # Collapse equal pHashes before comparing unique hashes; bound memory to O(n).
    representatives = {}
    for i, record in enumerate(records):
        check_cancel(cancel)
        if record.phash in representatives:
            join(representatives[record.phash], i, "similar")
        else:
            representatives[record.phash] = i
    unique = list(representatives.items())
    total = len(unique) * (len(unique) - 1) // 2
    count = 0
    for i, (left_hash, left) in enumerate(unique):
        for j in range(i + 1, len(unique)):
            check_cancel(cancel)
            right_hash, right = unique[j]
            if (left_hash ^ right_hash).bit_count() <= threshold:
                join(left, right, "similar")
            count += 1
            if count % 4096 == 0:
                progress("유사도 비교", count, total)
    progress("유사도 비교", total, total)
    components = defaultdict(list)
    for i, record in enumerate(records):
        check_cancel(cancel)
        components[root(i)].append(record)
    groups = [
        DuplicateGroup(images=images, kinds=kinds[index])
        for index, images in components.items()
        if len(images) > 1
    ]
    groups.sort(key=lambda group: str(group.images[0].path).casefold())
    return groups


def scan(
    folder: Path,
    recursive: bool = True,
    threshold: int = 6,
    cancel: Event | None = None,
    progress: Progress | None = None,
    database: Path | None = None,
) -> ScanResult:
    cancel = cancel if cancel is not None else Event()
    progress = progress or (lambda *_: None)
    folder = folder.resolve(strict=True)
    if not folder.is_dir():
        raise ValueError("검색할 폴더를 선택하세요")
    if not 0 <= threshold <= 64:
        raise ValueError("pHash 거리는 0~64여야 합니다")
    result = ScanResult()
    records = []
    paths = []

    def walk_error(error):
        result.errors.append(f"폴더 접근 실패: {error}")

    try:
        for current, directories, files in os.walk(folder, followlinks=False, onerror=walk_error):
            check_cancel(cancel)
            directories[:] = (
                sorted(
                    d
                    for d in directories
                    if not (Path(current) / d).is_symlink()
                    and not (Path(current) / d).is_junction()
                )
                if recursive
                else []
            )
            for name in sorted(files):
                check_cancel(cancel)
                path = Path(current) / name
                if not path.is_symlink() and path.is_file():
                    paths.append(path)
            progress("파일 수집", len(paths), 0)
        result.discovered = len(paths)
        for index, path in enumerate(paths, 1):
            check_cancel(cancel)
            try:
                records.append(read_image(path, cancel))
                result.scanned += 1
            except UnidentifiedImageError:
                # Ordinary non-image files are normal in a mixed folder.
                # Report image-looking corrupt files while still sniffing all extensions.
                if path.suffix.lower() in {
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".webp",
                    ".bmp",
                    ".gif",
                    ".tif",
                    ".tiff",
                }:
                    result.errors.append(f"{path}: 이미지를 해석할 수 없습니다")
            except (
                OSError,
                ValueError,
                Image.DecompressionBombError,
                Image.DecompressionBombWarning,
            ) as error:
                result.errors.append(f"{path}: {error}")
            progress("이미지 분석", index, len(paths))
        result.groups = group_images(records, threshold, cancel, progress)
        check_cancel(cancel)
        if database is not None:
            with ReviewStore(database) as store:
                for group in result.groups:
                    for record in group.images:
                        check_cancel(cancel)
                        record.decision = store.get(record)
    except Cancelled:
        result.cancelled = True
        result.groups = []  # Never offer incomplete groups for deletion.
    return result
