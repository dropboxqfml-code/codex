"""Explicit, B-only recycling with independently revalidated A evidence."""

from threading import Event

from .cross_models import CrossDecision, RootRole
from .cross_scanner import validate_roots
from .privacy import local_path
from .recycling import recycle_file
from .scanner import Cancelled, check_cancel
from .trash import TrashResult, verify_unchanged


def _belongs(record, root, role, recursive):
    if record.root_role != role:
        raise ValueError("A는 보호된 기준 원본입니다. B 역할의 파일만 이동할 수 있습니다")
    path = local_path(record.path)
    if path != record.path or root not in path.parents:
        raise ValueError("검색한 폴더 범위 밖의 파일은 이동할 수 없습니다")
    if not recursive and path.parent != root:
        raise ValueError("하위 폴더를 포함하지 않은 검색 범위를 벗어났습니다")
    return path


def cross_deletion_plan(result):
    if result.cancelled:
        raise ValueError("취소된 검색 결과로는 파일을 이동할 수 없습니다")
    a, b = validate_roots(result.root_a, result.root_b)
    targets, seen = [], set()
    for candidate in result.candidates:
        if candidate.decision != CrossDecision.DELETE:
            continue
        path = _belongs(candidate.target, b, RootRole.TARGET, result.recursive_b)
        if a == path or a in path.parents:
            raise ValueError("A 폴더는 보호됩니다")
        if not candidate.matches:
            raise ValueError("유효한 A 매칭 근거가 없습니다. 다시 검색하세요")
        for match in candidate.matches:
            _belongs(match.reference, a, RootRole.REFERENCE, result.recursive_a)
            if match.target is not candidate.target:
                raise ValueError("매칭 대상이 검색 결과와 다릅니다")
        if path not in seen:
            targets.append(candidate)
            seen.add(path)
    return targets


def move_cross_to_trash(
    result,
    cancel=None,
    progress=None,
    trash=None,
    *,
    confirmed=False,
    similar_confirmed=False,
):
    if confirmed is not True:
        raise ValueError("명시적인 사용자 확인이 있어야 휴지통으로 이동할 수 있습니다")
    targets = cross_deletion_plan(result)
    if any(c.similar_only for c in targets) and similar_confirmed is not True:
        raise ValueError("유사 후보는 다른 사진일 수 있습니다. 추가 확인이 필요합니다")
    cancel = cancel if cancel is not None else Event()
    progress = progress or (lambda *_: None)
    trash = trash or recycle_file
    outcome = TrashResult()
    try:
        for index, candidate in enumerate(targets, 1):
            check_cancel(cancel)
            try:
                # Recheck root roles/boundaries and current paths immediately before moving.
                a, b = validate_roots(result.root_a, result.root_b)
                _belongs(candidate.target, b, RootRole.TARGET, result.recursive_b)
                verify_unchanged(candidate.target, cancel)
                evidence = False
                for match in candidate.matches:
                    check_cancel(cancel)
                    try:
                        if match.kind == "similar" and not similar_confirmed:
                            continue
                        _belongs(match.reference, a, RootRole.REFERENCE, result.recursive_a)
                        verify_unchanged(match.reference, cancel)
                        if match.reference.path.samefile(candidate.target.path):
                            continue
                        evidence = True
                        break
                    except (OSError, ValueError):
                        continue
                if not evidence:
                    raise ValueError(
                        "근거 A 파일이 삭제·변경되었거나 접근할 수 없습니다. 다시 검색하세요"
                    )
                verify_unchanged(candidate.target, cancel)
                check_cancel(cancel)
                trash(str(candidate.target.path))
                outcome.moved.append(candidate.target.path)
            except (OSError, ValueError) as error:
                outcome.errors.append(f"{candidate.target.path}: {error}")
                outcome.skipped.extend(c.target.path for c in targets[index:])
                break  # Fail safely; never fall back to permanent deletion.
            progress("B 휴지통 이동", index, len(targets))
    except Cancelled:
        outcome.cancelled = True
    return outcome
