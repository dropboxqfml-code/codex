"""Developer-only offline intake; never execute, extract, or authenticate OEM data.

The legacy reference is pinned LFS metadata; the P05ACJ reference is previously
observed download bytes, not authenticated manufacturer firmware. Neither a hash
match nor PE headers establish origin, model, signature, or command semantics.
"""
import argparse
from dataclasses import dataclass
import hashlib
import io
import json
import os
import re
import stat
import struct
from types import MappingProxyType
import zipfile
import zlib


MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_ZIP_ENTRIES = 4096
MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_PE_SECTIONS = 96
LFS_VERSION = b"version https://git-lfs.github.com/spec/"


@dataclass(frozen=True)
class ArtifactSpec:
    kind: str
    expected_size: int = None
    expected_sha256: str = None


# Source: Elc3r/drivers_NP-RV520, c20c758117b1410a5e486a7042fc004ac589287f,
# W7/32bit_64bit/Battery_Life_Extender_1.0.0.11.ZIP (Git LFS metadata).
# P05ACJ: ITEM_20140901_21421_WIN_P05ACJ.exe, observed after the user
# published the environment. HTTP source, Authenticode not verified. This pin
# binds subsequent analysis to the same bytes; it is not a trust anchor.
# SSC Amor3: BASW-A0141A02.ZIP 1.0.0.7, observed through the Model940X3G
# catalog and normal manufacturer download redirect. The pin is byte identity,
# not verified signature, current-model compatibility, or a battery contract.
SPECS = MappingProxyType({
    "legacy-ble": ArtifactSpec("legacy-ble", 13728500,
        "5e3be33df74283d00542777320519c3f5d5fb6a01bdcbd664d7d9e33ce2511fc"),
    "p05acj": ArtifactSpec("p05acj", 5822368,
        "374c768a09211ce8da6e0812bde870e3b90957bf8b38e2289cac4dc52857e7fd"),
    "ssconfig-amor3": ArtifactSpec("ssconfig-amor3", 3771257,
        "1681f1a5a10b3d758ce1b925efbe7ec4360d3ed33c7d3fb189a5bf69fff699c2"),
})


def _report(status, size=0, digest=None):
    return dict(status=status, sourceByteCount=size, sourceSha256=digest,
                containerEntryCount=0, containerUncompressedBytes=0,
                peSectionCount=0, sourcePayloadIntegrityVerified=False,
                authenticodeVerified=False, currentModelCompatibilityVerified=False,
                batteryCommandContractVerified=False, canInvokeMethods=False,
                canWriteHardware=False, extractedOrExecuted=False)


def _safe_member(info):
    name = info.orig_filename.replace("\\", "/")
    parts = name.rstrip("/").split("/")
    return (bool(name) and not name.startswith("/") and
            not any(part in ("", ".", "..") or ":" in part or
                    part.endswith((".", " ")) for part in parts) and
            not any(ord(char) < 32 or ord(char) == 127 for char in name) and
            not stat.S_ISLNK(info.external_attr >> 16))


def _zip_counts(data):
    # Reject unsupported multipart/ZIP64 and excessive counts before ZipFile
    # builds its entry list, then bound decompression before any CRC reads.
    end = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if end < 0 or end + 22 > len(data):
        raise ValueError()
    _, disk, start_disk, count_disk, count, size, offset, comment = (
        struct.unpack_from("<4s4H2LH", data, end))
    if (disk or start_disk or count_disk != count or not 0 < count <= MAX_ZIP_ENTRIES
            or end + 22 + comment != len(data) or offset + size != end):
        raise ValueError()
    cursor, observed_count, declared_total = offset, 0, 0
    while cursor < end:
        if cursor + 46 > end or data[cursor:cursor + 4] != b"PK\x01\x02":
            raise ValueError()
        lengths = struct.unpack_from("<3H", data, cursor + 28)
        declared_total += struct.unpack_from("<L", data, cursor + 24)[0]
        cursor += 46 + sum(lengths)
        observed_count += 1
        if (cursor > end or observed_count > MAX_ZIP_ENTRIES or
                declared_total > MAX_UNCOMPRESSED_BYTES):
            raise ValueError()
    if observed_count != count:
        raise ValueError()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        total = sum(item.file_size for item in entries)
        if len(entries) != count or total > MAX_UNCOMPRESSED_BYTES:
            raise ValueError()
        names = set()
        for item in entries:
            normalized = item.orig_filename.replace("\\", "/").casefold()
            if (not _safe_member(item) or normalized in names or item.flag_bits & 1
                    or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                raise ValueError()
            names.add(normalized)
        ranges = sorted(_check_zip_member(data, item, offset) for item in entries)
        if any(left[1] > right[0] for left, right in zip(ranges, ranges[1:])):
            raise ValueError()
        return count, total


def _check_zip_member(data, item, central_offset):
    start = item.header_offset
    if start < 0 or start + 30 > central_offset or data[start:start + 4] != b"PK\x03\x04":
        raise ValueError()
    flags, method = struct.unpack_from("<HH", data, start + 6)
    crc, compressed, uncompressed = struct.unpack_from("<3L", data, start + 14)
    name_size, extra_size = struct.unpack_from("<HH", data, start + 26)
    payload = start + 30 + name_size + extra_size
    end = payload + item.compress_size
    encoding = "utf-8" if flags & 0x800 else "cp437"
    if (flags != item.flag_bits or method != item.compress_type or end > central_offset or
            data[start + 30:start + 30 + name_size] != item.orig_filename.encode(encoding)):
        raise ValueError()
    expected = (item.CRC, item.compress_size, item.file_size)
    if any(actual != wanted and not (flags & 8 and actual == 0)
           for actual, wanted in zip((crc, compressed, uncompressed), expected)):
        raise ValueError()
    occupied_end = end
    if flags & 8:
        candidates = (end + 4, end) if data[end:end + 4] == b"PK\x07\x08" else (end,)
        for descriptor in candidates:
            if (descriptor + 12 <= central_offset and
                    struct.unpack_from("<3L", data, descriptor) == expected):
                occupied_end = descriptor + 12
                break
        else:
            raise ValueError()
    decoder = zlib.decompressobj(-15) if method == zipfile.ZIP_DEFLATED else None
    observed, checksum = 0, 0
    while payload < end:
        pending = data[payload:min(end, payload + 65536)]
        payload += len(pending)
        while pending:
            chunk = decoder.decompress(pending, min(65536, item.file_size - observed + 1)) if decoder else pending
            pending = decoder.unconsumed_tail if decoder else b""
            observed += len(chunk)
            checksum = zlib.crc32(chunk, checksum)
            if observed > item.file_size or (decoder and decoder.unused_data):
                raise ValueError()
    # A capped decompression call may consume its final input while retaining
    # output internally; drain that output without relaxing the byte bound.
    while decoder and not decoder.eof:
        chunk = decoder.decompress(b"", min(65536, item.file_size - observed + 1))
        if not chunk:
            break
        observed += len(chunk)
        checksum = zlib.crc32(chunk, checksum)
        if observed > item.file_size:
            raise ValueError()
    if observed != item.file_size or checksum != item.CRC or (decoder and not decoder.eof):
        raise ValueError()
    return start, occupied_end


def _pe_sections(data):
    if len(data) < 64:
        raise ValueError()
    offset = struct.unpack_from("<L", data, 60)[0]
    if not 64 <= offset <= min(1024 * 1024, len(data) - 24):
        raise ValueError()
    if data[offset:offset + 4] != b"PE\0\0":
        raise ValueError()
    machine, count = struct.unpack_from("<HH", data, offset + 4)
    optional_size = struct.unpack_from("<H", data, offset + 20)[0]
    optional = offset + 24
    table = optional + optional_size
    if (not machine or not 0 < count <= MAX_PE_SECTIONS or
            not 96 <= optional_size <= 4096 or table + count * 40 > len(data)):
        raise ValueError()
    magic = struct.unpack_from("<H", data, optional)[0]
    minimum = {0x10b: 96, 0x20b: 112}.get(magic)
    if minimum is None or optional_size < minimum:
        raise ValueError()
    directories = struct.unpack_from("<L", data, optional + minimum - 4)[0]
    header_size = struct.unpack_from("<L", data, optional + 60)[0]
    if directories > 16 or minimum + directories * 8 > optional_size:
        raise ValueError()
    if not table + count * 40 <= header_size <= len(data):
        raise ValueError()
    ranges = []
    for index in range(count):
        length, start = struct.unpack_from("<LL", data, table + index * 40 + 16)
        if length:
            if start < header_size or start + length > len(data):
                raise ValueError()
            ranges.append((start, start + length))
    ranges.sort()
    if any(left[1] > right[0] for left, right in zip(ranges, ranges[1:])):
        raise ValueError()
    return count


def inspect(data, spec):
    """Pure byte inspection; custom specs are for synthetic unit fixtures only."""
    if len(data) > MAX_INPUT_BYTES:
        return _report("InputTooLarge", len(data))
    report = _report("UnrecognizedData", len(data), hashlib.sha256(data).hexdigest())
    if (len(data) <= 4096 and data.startswith(LFS_VERSION) and
            all(char in (9, 10, 13) or 32 <= char <= 126 for char in data)):
        report["status"] = "GitLfsPointerOnly"
        if spec.kind == "legacy-ble":
            match = re.fullmatch(
                rb"version https://git-lfs.github.com/spec/v1\r?\n"
                rb"oid sha256:([0-9a-f]{64})\r?\nsize ([0-9]{1,20})\r?\n?", data)
            report["pointerMatchesExpected"] = bool(match and
                match[1].decode("ascii") == spec.expected_sha256 and
                int(match[2]) == spec.expected_size)
        return report
    zip_kind = spec.kind in ("legacy-ble", "ssconfig-amor3")
    if zip_kind or (spec.kind == "p05acj" and spec.expected_size is not None):
        if len(data) != spec.expected_size:
            report["status"] = "SourceSizeMismatch"
            return report
        elif report["sourceSha256"] != spec.expected_sha256:
            report["status"] = "SourceHashMismatch"
            return report
    if zip_kind:
        try:
            count, total = _zip_counts(data)
        except Exception:
            report["status"] = "InvalidZipContainer"
        else:
            status = "SourcePayloadVerified" if spec.kind == "legacy-ble" else "ObservedSourcePayloadMatched"
            report.update(status=status, containerEntryCount=count,
                          containerUncompressedBytes=total,
                          sourcePayloadIntegrityVerified=True)
    elif spec.kind == "p05acj" and data.startswith(b"MZ"):
        try:
            report["peSectionCount"] = _pe_sections(data)
        except Exception:
            report["status"] = "InvalidPeContainer"
        else:
            if spec.expected_size is None:
                report["status"] = "PeHeaderObserved"
            else:
                report.update(status="ObservedSourcePayloadMatched",
                              sourcePayloadIntegrityVerified=True)
    return report


def inspect_path(path, spec):
    """Stat first and read at most the cap plus one byte, including on a race."""
    try:
        metadata = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode):
            return _report("InputUnavailable")
        if metadata.st_size > MAX_INPUT_BYTES:
            return _report("InputTooLarge", metadata.st_size)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as source:
            metadata = os.fstat(source.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                return _report("InputUnavailable")
            if metadata.st_size > MAX_INPUT_BYTES:
                return _report("InputTooLarge", metadata.st_size)
            data = source.read(MAX_INPUT_BYTES + 1)
        return inspect(data, spec)
    except (OSError, ValueError):
        return _report("InputUnavailable")


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError()


def main(argv=None):
    parser = _Parser(description=__doc__)
    parser.add_argument("--kind", required=True, choices=tuple(SPECS))
    parser.add_argument("--input", required=True, metavar="PATH")
    try:
        arguments = parser.parse_args(argv)
    except ValueError:
        report = _report("InvalidArguments")
    else:
        report = inspect_path(arguments.input, SPECS[arguments.kind])
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] in ("SourcePayloadVerified", "ObservedSourcePayloadMatched", "PeHeaderObserved") else 1


if __name__ == "__main__":
    raise SystemExit(main())
