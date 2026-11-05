"""Synthetic offline fixtures; never load OEM code or extract archive members."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

import inspect_command_research_artifact as intake


def zip_bytes(name="payload.bin", payload=b"synthetic inert payload", symlink=False):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:
        entry = zipfile.ZipInfo(name)
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16 if symlink else 0
        archive.writestr(entry, payload)
    return output.getvalue()


def fixture_spec(data):
    return intake.ArtifactSpec("legacy-ble", len(data), hashlib.sha256(data).hexdigest())


def pe_bytes(plus=False):
    data = bytearray(1024)
    data[:2] = b"MZ"
    struct.pack_into("<L", data, 60, 64)
    data[64:68] = b"PE\0\0"
    struct.pack_into("<HH", data, 68, 0x8664 if plus else 0x14c, 1)
    optional_size = 240 if plus else 224
    struct.pack_into("<H", data, 84, optional_size)
    struct.pack_into("<H", data, 88, 0x20b if plus else 0x10b)
    struct.pack_into("<L", data, 148, 512)
    struct.pack_into("<L", data, 88 + (108 if plus else 92), 16)
    table = 88 + optional_size
    data[table:table + 8] = b"private\0"
    struct.pack_into("<LL", data, table + 16, 512, 512)
    return bytes(data)


class ArtifactIntakeTests(unittest.TestCase):
    def assert_closed(self, report):
        for key in ("authenticodeVerified", "currentModelCompatibilityVerified",
                    "batteryCommandContractVerified", "canInvokeMethods",
                    "canWriteHardware", "extractedOrExecuted"):
            self.assertIs(report[key], False, key)

    def test_pinned_lfs_metadata_is_never_the_payload_or_its_hash(self):
        spec = intake.SPECS["legacy-ble"]
        pointer = ("version https://git-lfs.github.com/spec/v1\n"
                   "oid sha256:" + spec.expected_sha256 + "\nsize " +
                   str(spec.expected_size) + "\n").encode("ascii")
        report = intake.inspect(pointer, spec)
        self.assertEqual(report["status"], "GitLfsPointerOnly")
        self.assertTrue(report["pointerMatchesExpected"])
        self.assertEqual(report["sourceSha256"], hashlib.sha256(pointer).hexdigest())
        self.assertNotEqual(report["sourceSha256"], spec.expected_sha256)
        self.assertFalse(report["sourcePayloadIntegrityVerified"])
        self.assert_closed(report)

    def test_wrong_and_malformed_pointer_metadata_remains_pointer_only(self):
        for pointer in (
            b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"0" * 64 + b"\nsize 13728500\n",
            b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"0" * 64 + b"\nsize 1\n",
            b"version https://git-lfs.github.com/spec/v1\nprivate malformed text\n",
            b"version https://git-lfs.github.com/spec/v1\nsize 13728500\nsize 13728500\n",
        ):
            with self.subTest(pointer=pointer):
                report = intake.inspect(pointer, intake.SPECS["legacy-ble"])
                self.assertEqual(report["status"], "GitLfsPointerOnly")
                self.assertFalse(report["pointerMatchesExpected"])
                self.assertFalse(report["sourcePayloadIntegrityVerified"])
        report = intake.inspect(pointer, intake.SPECS["p05acj"])
        self.assertNotIn("pointerMatchesExpected", report)

    def test_source_size_and_digest_must_match_before_zip_parsing(self):
        data = zip_bytes()
        for spec, expected in (
            (intake.SPECS["legacy-ble"], "SourceSizeMismatch"),
            (intake.ArtifactSpec("legacy-ble", len(data), "0" * 64), "SourceHashMismatch"),
        ):
            with patch.object(intake, "_zip_counts", side_effect=AssertionError("must not parse")):
                self.assertEqual(intake.inspect(data, spec)["status"], expected)

    def test_valid_zip_verifies_only_source_payload_and_has_no_raw_names(self):
        data = zip_bytes("PRIVATE-USER/serial-unique-927361.bin")
        report = intake.inspect(data, fixture_spec(data))
        self.assertEqual(report["status"], "SourcePayloadVerified")
        self.assertTrue(report["sourcePayloadIntegrityVerified"])
        self.assertEqual(report["containerEntryCount"], 1)
        self.assertEqual(report["containerUncompressedBytes"], len(b"synthetic inert payload"))
        self.assert_closed(report)
        rendered = json.dumps(report)
        for secret in ("PRIVATE-USER", "serial-unique-927361", "payload.bin"):
            self.assertNotIn(secret, rendered)

    def test_truncated_crc_tampered_and_non_zip_payloads_are_rejected(self):
        original = zip_bytes(payload=b"unique payload marker")
        damaged = original.replace(b"unique payload marker", b"tamper payload marker", 1)
        for data in (original[:-1], original[:20], damaged, b"not a ZIP"):
            with self.subTest(data=data[:20]):
                report = intake.inspect(data, fixture_spec(data))
                self.assertEqual(report["status"], "InvalidZipContainer")
                self.assertFalse(report["sourcePayloadIntegrityVerified"])

    def test_unsafe_paths_and_symlinks_are_rejected_without_exporting_names(self):
        for name in ("../secret", "a/../../secret", "/absolute", "C:/secret",
                     "a\\..\\secret", "\\\\server\\secret", "a//secret", "a/./secret",
                     "secret:stream", "secret. "):
            data = zip_bytes(name)
            report = intake.inspect(data, fixture_spec(data))
            with self.subTest(name=name):
                self.assertEqual(report["status"], "InvalidZipContainer")
                self.assertNotIn("secret", json.dumps(report))
        data = zip_bytes(symlink=True)
        self.assertEqual(intake.inspect(data, fixture_spec(data))["status"], "InvalidZipContainer")
        data = zip_bytes("secret_ignored").replace(b"secret_ignored", b"secret\x00ignored")
        self.assertEqual(intake.inspect(data, fixture_spec(data))["status"], "InvalidZipContainer")

    def test_duplicate_and_case_colliding_zip_entries_are_rejected(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("same.bin", b"first")
            archive.writestr("SAME.bin", b"second")
        data = output.getvalue()
        self.assertEqual(intake.inspect(data, fixture_spec(data))["status"], "InvalidZipContainer")
        # Concatenating otherwise valid ZIPs must not hide an earlier archive.
        data = zip_bytes() + zip_bytes()
        self.assertEqual(intake.inspect(data, fixture_spec(data))["status"], "InvalidZipContainer")

    def test_zip_count_and_decompression_caps_precede_crc_reads(self):
        original = zip_bytes()
        excessive = bytearray(original)
        end = excessive.rfind(b"PK\x05\x06")
        struct.pack_into("<HH", excessive, end + 8, intake.MAX_ZIP_ENTRIES + 1,
                         intake.MAX_ZIP_ENTRIES + 1)
        with patch.object(intake, "_check_zip_member", side_effect=AssertionError("no member read")) as opened:
            self.assertEqual(intake.inspect(bytes(excessive), fixture_spec(excessive))["status"],
                             "InvalidZipContainer")
            with patch.object(intake, "MAX_UNCOMPRESSED_BYTES", 1):
                self.assertEqual(intake.inspect(original, fixture_spec(original))["status"],
                                 "InvalidZipContainer")
            opened.assert_not_called()
        # EOCD count must not hide a larger central directory before allocation.
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("one", b"1")
            archive.writestr("two", b"2")
        hidden = bytearray(output.getvalue())
        struct.pack_into("<HH", hidden, hidden.rfind(b"PK\x05\x06") + 8, 1, 1)
        with patch.object(intake.zipfile, "ZipFile", side_effect=AssertionError("no allocation")) as parsed:
            self.assertEqual(intake.inspect(bytes(hidden), fixture_spec(hidden))["status"],
                             "InvalidZipContainer")
            parsed.assert_not_called()

    def test_deflate_stream_must_reach_eof_and_have_its_full_length_and_crc(self):
        noisy = b"".join(hashlib.sha256(str(index).encode("ascii")).digest() for index in range(4096))
        for payload in (b"\0" * 65537, b"\0" * 1048576, b"abcd" * 65537, noisy):
            for level in (1, 6, 9):
                output = io.BytesIO()
                with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=level) as archive:
                    archive.writestr("inert.bin", payload)
                data = output.getvalue()
                with self.subTest(length=len(payload), level=level):
                    self.assertEqual(intake.inspect(data, fixture_spec(data))["status"], "SourcePayloadVerified")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("inert.bin", b"hello" * 10000)
        data = output.getvalue()
        self.assertEqual(intake.inspect(data, fixture_spec(data))["status"], "SourcePayloadVerified")
        forged = bytearray(data)
        central = forged.find(b"PK\x01\x02")
        for offset in (14, central + 16):
            struct.pack_into("<L", forged, offset, zlib.crc32(b"h"))
        for offset in (22, central + 24):
            struct.pack_into("<L", forged, offset, 1)
        self.assertEqual(intake.inspect(bytes(forged), fixture_spec(forged))["status"],
                         "InvalidZipContainer")
        # A truncated raw stream cannot pass even with matching payload bytes.
        damaged = bytearray(data)
        compressed_size = struct.unpack_from("<L", damaged, 18)[0]
        struct.pack_into("<L", damaged, 18, compressed_size - 1)
        struct.pack_into("<L", damaged, central + 20, compressed_size - 1)
        self.assertEqual(intake.inspect(bytes(damaged), fixture_spec(damaged))["status"],
                         "InvalidZipContainer")

    def test_streamed_zip_descriptors_must_match_with_or_without_the_signature(self):
        class NonSeekable(io.BytesIO):
            def seek(self, *arguments):
                raise io.UnsupportedOperation()

        output = NonSeekable()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("inert.bin", b"hello" * 1000)
        original = output.getvalue()
        descriptor = original.find(b"PK\x07\x08")
        self.assertGreater(descriptor, 0)
        self.assertEqual(intake.inspect(original, fixture_spec(original))["status"], "SourcePayloadVerified")
        unsigned = bytearray(original[:descriptor] + original[descriptor + 4:])
        eocd = unsigned.rfind(b"PK\x05\x06")
        struct.pack_into("<L", unsigned, eocd + 16,
                         struct.unpack_from("<L", unsigned, eocd + 16)[0] - 4)
        self.assertEqual(intake.inspect(bytes(unsigned), fixture_spec(unsigned))["status"], "SourcePayloadVerified")
        for offset in (4, 8, 12):
            damaged = bytearray(original)
            struct.pack_into("<L", damaged, descriptor + offset, 0)
            self.assertEqual(intake.inspect(bytes(damaged), fixture_spec(damaged))["status"],
                             "InvalidZipContainer")
        damaged = bytearray(original[:descriptor] + original[descriptor + 16:])
        eocd = damaged.rfind(b"PK\x05\x06")
        struct.pack_into("<L", damaged, eocd + 16,
                         struct.unpack_from("<L", damaged, eocd + 16)[0] - 16)
        self.assertEqual(intake.inspect(bytes(damaged), fixture_spec(damaged))["status"], "InvalidZipContainer")

    def test_pe32_and_pe32plus_are_observations_without_identity_claims(self):
        for plus in (False, True):
            data = pe_bytes(plus)
            report = intake.inspect(data, intake.SPECS["p05acj"])
            self.assertEqual(report["status"], "PeHeaderObserved")
            self.assertEqual(report["peSectionCount"], 1)
            self.assertFalse(report["sourcePayloadIntegrityVerified"])
            self.assert_closed(report)
            self.assertNotIn("private", json.dumps(report))
            self.assertEqual(report, intake.inspect(data, intake.SPECS["p05acj"]))

    def test_pe_header_optional_header_section_and_truncation_bounds(self):
        original = pe_bytes()
        mutations = [(60, "<L", 63), (60, "<L", 0xffffffff),
                     (68, "<H", 0), (70, "<H", 0),
                     (70, "<H", intake.MAX_PE_SECTIONS + 1),
                     (84, "<H", 95), (84, "<H", 4097), (88, "<H", 0),
                     (180, "<L", 17), (148, "<L", 100),
                     (328, "<L", 513), (332, "<L", 1)]
        for offset, format_, value in mutations:
            damaged = bytearray(original)
            struct.pack_into(format_, damaged, offset, value)
            with self.subTest(offset=offset, value=value):
                self.assertEqual(intake.inspect(bytes(damaged), intake.SPECS["p05acj"])["status"],
                                 "InvalidPeContainer")
        for data in (b"MZ", original[:63], original[:350], original[:-1]):
            self.assertEqual(intake.inspect(data, intake.SPECS["p05acj"])["status"], "InvalidPeContainer")
        self.assertEqual(intake.inspect(b"arbitrary inert data", intake.SPECS["p05acj"])["status"],
                         "UnrecognizedData")

    def test_oversized_input_is_not_hashed_or_read_and_input_races_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private-serial-927361.bin"
            path.write_bytes(b"MZ" + b"0" * 30)
            with patch.object(intake, "MAX_INPUT_BYTES", 16):
                with patch.object(intake.os, "open", side_effect=AssertionError("must not open")) as opened:
                    report = intake.inspect_path(path, intake.SPECS["p05acj"])
                    self.assertEqual(report["status"], "InputTooLarge")
                    opened.assert_not_called()
                with patch.object(intake.hashlib, "sha256", side_effect=AssertionError("must not hash")):
                    self.assertEqual(intake.inspect(path.read_bytes(), intake.SPECS["p05acj"])["status"],
                                     "InputTooLarge")
                with patch.object(intake.os, "stat", return_value=type("Metadata", (), {
                        "st_mode": stat.S_IFREG, "st_size": 1})()):
                    self.assertEqual(intake.inspect_path(path, intake.SPECS["p05acj"])["status"],
                                     "InputTooLarge")

    def test_cli_fixed_specs_sanitized_failures_and_repeated_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "PRIVATE-USER-serial-927361.bin"
            path.write_bytes(pe_bytes())
            for arguments, expected, code in (
                (["--kind", "p05acj", "--input", str(path)], "PeHeaderObserved", 0),
                (["--kind", "legacy-ble", "--input", str(path)], "SourceSizeMismatch", 1),
                (["--kind", "private-invalid-kind", "--input", str(path)], "InvalidArguments", 1),
                (["--kind", "legacy-ble", "--input", str(path), "--expected-sha256", "private"],
                 "InvalidArguments", 1),
                (["--kind", "p05acj", "--input", str(path) + "-missing"], "InputUnavailable", 1),
            ):
                with self.subTest(expected=expected):
                    outputs = []
                    for _ in range(2):
                        captured = io.StringIO()
                        with redirect_stdout(captured):
                            self.assertEqual(intake.main(arguments), code)
                        outputs.append(captured.getvalue())
                    self.assertEqual(outputs[0], outputs[1])
                    report = json.loads(outputs[0])
                    self.assertEqual(report["status"], expected)
                    self.assert_closed(report)
                    for secret in (str(path), "PRIVATE-USER", "serial-927361", "private-invalid-kind"):
                        self.assertNotIn(secret, outputs[0])
        self.assertEqual(intake.SPECS["legacy-ble"].expected_size, 13728500)
        self.assertEqual(intake.SPECS["legacy-ble"].expected_sha256,
                         "5e3be33df74283d00542777320519c3f5d5fb6a01bdcbd664d7d9e33ce2511fc")


if __name__ == "__main__":
    unittest.main()
