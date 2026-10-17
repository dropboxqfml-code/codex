"""A-index/B-query matching. Images on the same side are never compared."""

import os
from contextlib import nullcontext
from pathlib import Path
from threading import Event

from PIL import Image, UnidentifiedImageError

from .cross_models import CrossCandidate, CrossMatch, CrossResult, RootRole
from .cross_storage import CrossStore
from .privacy import local_path
from .scanner import Cancelled, check_cancel, file_sha256, read_image, stat_signature

MAX_FILES_PER_ROOT = 100_000
MAX_MATCH_PAIRS = 200_000


class ResultLimitError(RuntimeError):
    pass


class HammingIndex:
    """BK-tree of unique 64-bit hashes; equal hashes share a bucket."""

    def __init__(self):
        self.root = None

    def add(self, value, record, cancel):
        if self.root is None:
            self.root = (value, [record], {})
            return
        node = self.root
        while True:
            check_cancel(cancel)
            distance = (node[0] ^ value).bit_count()
            if distance == 0:
                node[1].append(record)
                return
            if distance not in node[2]:
                node[2][distance] = (value, [record], {})
                return
            node = node[2][distance]

    def query(self, value, radius, cancel):
        pending = [self.root] if self.root else []
        while pending:
            check_cancel(cancel)
            node = pending.pop()
            distance = (node[0] ^ value).bit_count()
            if distance <= radius:
                yield from node[1]
            pending.extend(
                child
                for edge, child in node[2].items()
                if distance - radius <= edge <= distance + radius
            )


def validate_roots(root_a: Path, root_b: Path) -> tuple[Path, Path]:
    a = local_path(root_a).resolve(strict=True)
    b = local_path(root_b).resolve(strict=True)
    if not a.is_dir() or not b.is_dir():
        raise ValueError("존재하는 로컬 폴더 A와 B를 선택하세요")
    # normcase includes Windows case insensitivity; samefile catches root aliases.
    na, nb = Path(os.path.normcase(str(a))), Path(os.path.normcase(str(b)))
    if a.samefile(b) or na == nb or na in nb.parents or nb in na.parents:
        raise ValueError("A와 B는 같거나 상위·하위 폴더일 수 없습니다")
    return a, b


def collect_files(root, recursive, role, cancel, progress, errors):
    paths = []

    def failure(error):
        errors.append(f"{role} 폴더 접근 실패: {error}")

    for current, directories, files in os.walk(root, followlinks=False, onerror=failure):
        check_cancel(cancel)
        allowed = []
        for name in sorted(directories) if recursive else []:
            try:
                allowed.append(local_path(Path(current) / name).name)
            except (OSError, ValueError) as error:
                errors.append(f"{role} 제외 {Path(current) / name}: {error}")
        directories[:] = allowed
        for name in sorted(files):
            check_cancel(cancel)
            try:
                path = local_path(Path(current) / name)
                if path.is_file():
                    paths.append(path)
                    if len(paths) > MAX_FILES_PER_ROOT:
                        raise ResultLimitError(
                            "폴더당 파일 한도 100,000개를 초과했습니다. 범위를 줄이세요"
                        )
            except (OSError, ValueError) as error:
                errors.append(f"{role} 제외 {Path(current) / name}: {error}")
        progress(f"{role} 파일 수집", len(paths), 0)
    return paths


def scan_cross(
    root_a: Path,
    root_b: Path,
    recursive_a=False,
    recursive_b=False,
    threshold=6,
    similar=True,
    cancel=None,
    progress=None,
    database=None,
) -> CrossResult:
    cancel = cancel if cancel is not None else Event()
    progress = progress or (lambda *_: None)
    if not 0 <= threshold <= 12:
        raise ValueError("두 폴더 비교의 pHash 거리는 0~12여야 합니다")
    a, b = validate_roots(root_a, root_b)
    if database is not None:
        database = local_path(database)
        if any(root == database or root in database.parents for root in (a, b)):
            raise ValueError("앱 데이터·캐시 위치는 A/B 폴더 밖이어야 합니다. 검색 범위를 줄이세요")
    result = CrossResult(a, b, recursive_a, recursive_b, threshold, similar)
    exact, pixels = {}, {}
    perceptual = HammingIndex()
    identities = set()
    total_pairs = 0
    try:
        with CrossStore(database) if database is not None else nullcontext() as store:
            paths_a = collect_files(a, recursive_a, "A", cancel, progress, result.errors)
            paths_b = collect_files(b, recursive_b, "B", cancel, progress, result.errors)
            result.discovered = len(paths_a) + len(paths_b)
            for role, root, recursive, paths in (
                (RootRole.REFERENCE, a, recursive_a, paths_a),
                (RootRole.TARGET, b, recursive_b, paths_b),
            ):
                for index, path in enumerate(paths, 1):
                    check_cancel(cancel)
                    try:
                        before = stat_signature(path.stat(follow_symlinks=False))
                        identity = before[2:]
                        if role == RootRole.TARGET and identity in identities:
                            raise ValueError(
                                "A와 같은 실파일(하드 링크)은 B 정리 대상에서 제외합니다"
                            )
                        checksum = file_sha256(path, cancel) if store else None
                        key = (
                            store.cache_id(root, recursive, role, path, before, checksum)
                            if store
                            else None
                        )
                        record = store.cached(key, path, checksum, before, role) if store else None
                        if record is None:
                            record = read_image(
                                path, cancel, max_pixels=40_000_000, include_thumbnail=False
                            )
                            record.root_role = role
                            if checksum and record.sha256 != checksum:
                                raise ValueError("캐시 검사 중 파일이 변경되었습니다")
                            # Cross-mode previews are generated only for the displayed pair.
                            record.thumbnail = b""
                            if store:
                                store.cache(key, record)
                        else:
                            result.cache_hits += 1
                        if stat_signature(path.stat(follow_symlinks=False)) != before:
                            raise ValueError("검색 중 파일이 변경되었습니다")
                        if role == RootRole.REFERENCE:
                            result.scanned_a += 1
                            identities.add(identity)
                            exact.setdefault((record.size, record.sha256), []).append(record)
                            pixels.setdefault(record.pixel_hash, []).append(record)
                            if similar:
                                perceptual.add(record.phash, record, cancel)
                        else:
                            result.scanned_b += 1
                            found = {}
                            for reference in exact.get((record.size, record.sha256), []):
                                check_cancel(cancel)
                                found[reference.path] = CrossMatch(
                                    reference,
                                    record,
                                    "file",
                                    (reference.phash ^ record.phash).bit_count(),
                                )
                            for reference in pixels.get(record.pixel_hash, []):
                                check_cancel(cancel)
                                found.setdefault(
                                    reference.path,
                                    CrossMatch(
                                        reference,
                                        record,
                                        "pixel",
                                        (reference.phash ^ record.phash).bit_count(),
                                    ),
                                )
                            if similar:
                                for reference in perceptual.query(record.phash, threshold, cancel):
                                    check_cancel(cancel)
                                    found.setdefault(
                                        reference.path,
                                        CrossMatch(
                                            reference,
                                            record,
                                            "similar",
                                            (reference.phash ^ record.phash).bit_count(),
                                        ),
                                    )
                            if found:
                                total_pairs += len(found)
                                if total_pairs > MAX_MATCH_PAIRS:
                                    raise ResultLimitError(
                                        "매칭 쌍 한도 200,000개 초과. 검색 범위를 줄이세요"
                                    )
                                matches = sorted(
                                    found.values(),
                                    key=lambda m: (
                                        {"file": 0, "pixel": 1, "similar": 2}[m.kind],
                                        m.distance,
                                        str(m.reference.path).casefold(),
                                    ),
                                )
                                candidate = CrossCandidate(record, matches)
                                if store:
                                    candidate.decision = store.get_cross(result, candidate)
                                result.candidates.append(candidate)
                    except UnidentifiedImageError:
                        if path.suffix.lower() in {
                            ".png",
                            ".jpg",
                            ".jpeg",
                            ".bmp",
                            ".webp",
                            ".tif",
                            ".tiff",
                            ".gif",
                            ".eps",
                            ".svg",
                        }:
                            result.errors.append(f"{role} {path}: 이미지를 해석할 수 없습니다")
                    except (
                        OSError,
                        ValueError,
                        Image.DecompressionBombError,
                        Image.DecompressionBombWarning,
                    ) as error:
                        result.errors.append(f"{role} {path}: {error}")
                    progress(f"{role} 이미지 분석·매칭", index, len(paths))
            if store:
                store.prune()
            check_cancel(cancel)
    except Cancelled:
        result.cancelled = True
        result.candidates.clear()
    return result
