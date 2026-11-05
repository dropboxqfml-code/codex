"""Inert HII fixtures: no firmware/OEM/AML execution or external tools."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import inspect_p05acj_hii_references as hii


def op(code, body=b'', scoped=False):
    return bytes((code, (len(body) + 2) | (0x80 if scoped else 0))) + body


def statement(code=6, prompt=77, help_token=78, scoped=False):
    minimum = hii.STATEMENTS[code][1]
    return op(code, struct.pack('<HH', prompt, help_token) + bytes(minimum - 6), scoped)


def package(body, kind=2):
    return (len(body) + 4).to_bytes(3, 'little') + bytes((kind,)) + body


def resource(*packages):
    return struct.pack('<I', len(packages)) + b''.join(packages)


def inspect_fixture(data):
    return hii.inspect(data, hii.ResourceReference(len(data), hashlib.sha256(data).hexdigest()))


class HiiReferenceTests(unittest.TestCase):
    def assert_closed(self, result):
        for key in ('fullIfrSemanticsValidated', 'conditionsOrDefaultsEvaluated',
                    'currentFirmwareIdentityVerified', 'manufacturerAuthenticityVerified',
                    'batteryCommandContractVerified', 'canInferFeatureAbsence',
                    'canInferMenuVisibility', 'canReadHardware', 'canInvokeMethods',
                    'canWriteHardware', 'firmwareOrAmlExecuted'):
            self.assertIs(result[key], False, key)

    def assert_invalid(self, data):
        result = inspect_fixture(data)
        self.assertEqual('InvalidResource', result['status'])
        self.assertIsNone(result['references'])
        self.assertFalse(result['statementIndexComplete'])
        self.assertFalse(result['observedResourceMatched'])
        self.assertEqual(0, result['opcodeCount'])
        self.assert_closed(result)

    def test_paired_headers_are_counted_without_evaluating_conditional_scopes(self):
        data = resource(package(op(0x0a, scoped=True) + statement() + op(0x29)))
        result = inspect_fixture(data)
        self.assertEqual('ObservedResourceIndexed', result['status'])
        self.assertTrue(result['observedResourceMatched'])
        self.assertEqual(1, result['references']['batteryLifeCycleExtension']['pairedReferences'])
        self.assertEqual(['CheckBox'], result['references']['batteryLifeCycleExtension']['statementKinds'])
        self.assert_closed(result)

    def test_missing_battery_reference_is_bounded_and_positive_controls_are_distinct(self):
        data = resource(package(statement(6, 79, 80) + statement(0x0f, 93, 94)))
        result = inspect_fixture(data)
        self.assertEqual(0, result['references']['batteryLifeCycleExtension']['pairedReferences'])
        self.assertEqual(1, result['references']['usbChargeInSleepMode']['pairedReferences'])
        self.assertEqual(['Ref'], result['references']['smartBatteryCalibration']['statementKinds'])
        self.assert_closed(result)

    def test_prompt_only_help_only_and_pairs_are_not_conflated(self):
        data = resource(package(statement(prompt=77, help_token=0) +
                                statement(prompt=0, help_token=78) + statement()))
        result = inspect_fixture(data)['references']['batteryLifeCycleExtension']
        self.assertEqual((2, 2, 1), (result['promptReferences'], result['helpReferences'], result['pairedReferences']))
        self.assertEqual(['CheckBox'], result['statementKinds'])

    def test_all_supported_common_statement_headers_and_multiple_packages(self):
        data = resource(*(package(statement(code)) for code in hii.STATEMENTS))
        result = inspect_fixture(data)
        self.assertEqual(len(hii.STATEMENTS), result['formsPackageCount'])
        self.assertEqual(len(hii.STATEMENTS), result['supportedStatementCount'])
        self.assertEqual(len(hii.STATEMENTS), result['references']['batteryLifeCycleExtension']['pairedReferences'])
        self.assert_closed(result)

    def test_tokens_in_vendor_unknown_or_nonform_payloads_are_not_statements(self):
        token_bytes = struct.pack('<HH', 77, 78)
        data = resource(package(op(0x5f, token_bytes) + op(0x70, token_bytes)),
                        package(statement(), kind=4))
        result = inspect_fixture(data)
        self.assertEqual(1, result['vendorGuidOpcodeCount'])
        self.assertEqual(0, result['supportedStatementCount'])
        self.assertEqual(0, result['references']['batteryLifeCycleExtension']['pairedReferences'])
        self.assert_closed(result)

    def test_scope_errors_are_rejected_without_partial_positive_observations(self):
        for body in (statement(scoped=True), op(0x29), statement() + op(0x29),
                     op(0x70, scoped=True) + op(0x29, scoped=True),
                     op(0x70, scoped=True) + op(0x29, b'X')):
            with self.subTest(body=body):
                self.assert_invalid(resource(package(body)))
        self.assert_invalid(resource(package(statement(scoped=True)), package(op(0x29))))

    def test_package_counts_and_lengths_cannot_hide_suffixes_or_truncation(self):
        valid = resource(package(statement()))
        cases = [b'', b'\0' * 4, valid[:-1], valid + b'private',
                 b'\x01\0\0\0\x03\0\0\x02',
                 struct.pack('<I', 2) + valid[4:],
                 struct.pack('<I', 1) + valid[4:] * 2,
                 resource(package(b'inert', kind=4))]
        for data in cases:
            with self.subTest(length=len(data)):
                self.assert_invalid(data)

    def test_opcode_and_statement_bounds_reject_truncation_and_numeric_width_overrun(self):
        for code, (_, minimum) in hii.STATEMENTS.items():
            self.assert_invalid(resource(package(op(code, bytes(minimum - 3)))))
        for body in (b'\x06', b'\x06\x00', b'\x06\x01', b'\x06\x7f' + bytes(12)):
            self.assert_invalid(resource(package(body)))
        numeric = bytearray(statement(7));numeric[13] = 3
        self.assert_invalid(resource(package(numeric)))
        # A late malformed package discards the earlier battery-positive index.
        self.assert_invalid(resource(package(statement()), package(b'\x06\x7f')))

    def test_input_opcode_depth_and_package_caps_are_fail_closed(self):
        data = resource(package(statement()))
        with patch.object(hii, 'MAX_BYTES', 8):
            with patch.object(hii.hashlib, 'sha256', side_effect=AssertionError('must not hash')):
                self.assertEqual('InputTooLarge', hii.inspect(data)['status'])
        with patch.object(hii, 'MAX_OPCODES', 1):
            self.assert_invalid(resource(package(statement() * 2)))
        with patch.object(hii, 'MAX_DEPTH', 1):
            self.assert_invalid(resource(package(op(0x70, scoped=True) * 2 + op(0x29) * 2)))
        self.assert_invalid(struct.pack('<I', hii.MAX_PACKAGES + 1))
        self.assert_invalid(struct.pack('<I', 0xffffffff))

    def test_source_mismatch_precedes_parsing_and_reference_is_fixed_for_cli(self):
        data = resource(package(statement()))
        for ref, status in ((hii.REFERENCE, 'SourceSizeMismatch'),
                            (hii.ResourceReference(len(data), '0' * 64), 'SourceHashMismatch')):
            with patch.object(hii, 'index_headers', side_effect=AssertionError('must not index')) as parsed:
                result = hii.inspect(data, ref)
            parsed.assert_not_called()
            self.assertEqual(status, result['status'])
            self.assertIsNone(result['references'])
            self.assert_closed(result)
        self.assertEqual(333801, hii.REFERENCE.size)
        self.assertEqual('53ec78bfce49bf65858d64aaadee9fbb31abf79088ee0c9b60c28783a6ddf527', hii.REFERENCE.sha256)

    def test_cli_sanitizes_paths_errors_and_disallows_reference_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'PRIVATE-USER-unique-927361.bin'
            path.write_bytes(resource(package(statement())))
            for args, status in ((['--input', str(path)], 'SourceSizeMismatch'),
                                 (['--input', str(path) + '-missing'], 'InputUnavailable'),
                                 (['--input', str(path), '--expected-sha256', 'private'], 'InvalidArguments')):
                captured = io.StringIO()
                with redirect_stdout(captured):
                    self.assertEqual(1, hii.main(args))
                output = captured.getvalue();result = json.loads(output)
                self.assertEqual(status, result['status'])
                self.assert_closed(result)
                for secret in (str(path), 'PRIVATE-USER', '927361', 'private'):
                    self.assertNotIn(secret, output)
            with patch.object(hii.os, 'open', side_effect=AssertionError('no directory open')):
                self.assertEqual('InputUnavailable', hii.inspect_path(directory)['status'])

    def test_path_reads_remain_bounded_after_stat_race(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'inert';path.write_bytes(bytes(64))
            metadata = type('Metadata', (), {'st_mode': 0o100600, 'st_size': 1})()
            with patch.object(hii, 'MAX_BYTES', 16), patch.object(hii.os, 'stat', return_value=metadata):
                self.assertEqual('InputTooLarge', hii.inspect_path(path)['status'])
                with patch.object(hii.os, 'fstat', return_value=metadata), patch.object(
                        hii.hashlib, 'sha256', side_effect=AssertionError('must not hash grown input')):
                    grown = hii.inspect_path(path)
                    self.assertEqual('InputTooLarge', grown['status'])
                    self.assertEqual(17, grown['sourceByteCount'])  # cap plus one, not the full file
            symlink = Path(directory) / 'alias';symlink.symlink_to(path)
            self.assertEqual('InputUnavailable', hii.inspect_path(symlink)['status'])


if __name__ == '__main__':
    unittest.main()
