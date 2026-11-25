import copy
import hashlib
import unittest
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from release_validation import validate_release, validate_final_release


class ReleaseValidationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.files = {n: n.encode() for n in ('ATIVBatteryGuard.exe', 'ATIVBatteryGuard.Core.dll', 'ATIVBatteryGuard.exe.config')}
        self.report = dict(schemaVersion=1, sourceFingerprintSha256='abc', completedUtc=self.now.isoformat(),
                           defenderEnabled=True, realTimeProtectionEnabled=True, scanCompleted=True, scanPassed=True,
                           detections=0, defenderSignatureVersion='1.2.3',
                           fileHashes={n: hashlib.sha256(b).hexdigest() for n, b in self.files.items()},
                           signatures={n: dict(status='Valid', thumbprint='a' * 40) for n in ('ATIVBatteryGuard.exe', 'ATIVBatteryGuard.Core.dll')})

    def check_report(self, report):
        validate_release(report, self.files, 'abc', self.now)

    def test_matching_evidence(self):
        self.check_report(self.report)

    def test_changed_build(self):
        for name in self.files:
            changed = dict(self.files, **{name: b'changed'})
            with self.assertRaises(ValueError):
                validate_release(self.report, changed, 'abc', self.now)

    def test_missing_protection_or_detection(self):
        for key, value in [('scanPassed', False), ('scanCompleted', False), ('defenderEnabled', False),
                           ('realTimeProtectionEnabled', False), ('detections', 1), ('detections', False), ('defenderSignatureVersion', '')]:
            report = dict(self.report, **{key: value})
            with self.assertRaises(ValueError): self.check_report(report)

    def test_unsigned_or_different_publisher(self):
        for key, value in [('status', 'NotSigned'), ('thumbprint', ''), ('thumbprint', 'b' * 40)]:
            report = copy.deepcopy(self.report)
            report['signatures']['ATIVBatteryGuard.exe'][key] = value
            with self.assertRaises(ValueError): self.check_report(report)

    def current_app_evidence(self):
        files = dict(self.files)
        files.update({name: name.encode() for name in (
            'ATIVBatteryGuard.WmiInterop.dll', 'ATIVBatteryGuard.ManualProtectionHelper.exe',
            'ATIVBatteryGuard.ManualProtectionHelper.exe.config')})
        report = copy.deepcopy(self.report)
        report['fileHashes'] = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
        for name in ('ATIVBatteryGuard.WmiInterop.dll', 'ATIVBatteryGuard.ManualProtectionHelper.exe'):
            report['signatures'][name] = dict(status='Valid', thumbprint='a' * 40)
        return files, report

    def test_current_six_file_app_matching_evidence(self):
        files, report = self.current_app_evidence()
        validate_release(report, files, 'abc', self.now)

    def test_current_helper_and_wmi_require_signature_and_same_publisher(self):
        for name in ('ATIVBatteryGuard.WmiInterop.dll', 'ATIVBatteryGuard.ManualProtectionHelper.exe'):
            for mutation in ('missing', 'unsigned', 'other-publisher'):
                with self.subTest(file=name, mutation=mutation):
                    files, report = self.current_app_evidence()
                    if mutation == 'missing':
                        del report['signatures'][name]
                    elif mutation == 'unsigned':
                        report['signatures'][name]['status'] = 'NotSigned'
                    else:
                        report['signatures'][name]['thumbprint'] = 'b' * 40
                    with self.assertRaises(ValueError):
                        validate_release(report, files, 'abc', self.now)

    def test_current_helper_library_and_config_bytes_must_match_scan(self):
        files, report = self.current_app_evidence()
        for name in ('ATIVBatteryGuard.WmiInterop.dll', 'ATIVBatteryGuard.ManualProtectionHelper.exe',
                     'ATIVBatteryGuard.ManualProtectionHelper.exe.config'):
            with self.subTest(file=name):
                changed = dict(files, **{name: b'changed after scan'})
                with self.assertRaises(ValueError):
                    validate_release(report, changed, 'abc', self.now)

    def timestamped_current_app_evidence(self):
        files, report = self.current_app_evidence()
        for entry in report['signatures'].values():
            entry.update(timestamped=True, timestampThumbprint='c' * 40)
        return files, report

    def test_final_signed_evidence_requires_timestamp_for_all_four_pe_files(self):
        files, report = self.timestamped_current_app_evidence()
        validate_final_release(report, files, 'abc', self.now)
        for name in report['signatures']:
            for field, value in [('timestamped', False), ('timestamped', 1),
                                 ('timestampThumbprint', ''), ('timestampThumbprint', 'x' * 40)]:
                with self.subTest(file=name, field=field, value=value):
                    changed = copy.deepcopy(report)
                    changed['signatures'][name][field] = value
                    with self.assertRaises(ValueError):
                        validate_final_release(changed, files, 'abc', self.now)

    def test_final_signing_does_not_accept_old_signature_only_evidence(self):
        files, report = self.current_app_evidence()
        validate_release(report, files, 'abc', self.now)
        with self.assertRaises(ValueError):
            validate_final_release(report, files, 'abc', self.now)

    def test_final_signing_rejects_the_legacy_three_file_scope(self):
        report = copy.deepcopy(self.report)
        for entry in report['signatures'].values():
            entry.update(timestamped=True, timestampThumbprint='c' * 40)
        with self.assertRaises(ValueError):
            validate_final_release(report, self.files, 'abc', self.now)

    def test_timestamp_does_not_override_detections_or_changed_file_bytes(self):
        files, report = self.timestamped_current_app_evidence()
        for changes in [dict(detections=1), dict(realTimeProtectionEnabled=False), dict(sourceFingerprintSha256='other')]:
            with self.assertRaises(ValueError):
                validate_final_release(dict(report, **changes), files, 'abc', self.now)
        changed = dict(files, **{'ATIVBatteryGuard.ManualProtectionHelper.exe': b'changed'})
        with self.assertRaises(ValueError):
            validate_final_release(report, changed, 'abc', self.now)

    def test_stale_future_wrong_source(self):
        for key, value in [('completedUtc', (self.now - timedelta(days=2)).isoformat()),
                           ('completedUtc', (self.now + timedelta(minutes=1)).isoformat()),
                           ('sourceFingerprintSha256', 'other')]:
            with self.assertRaises(ValueError): self.check_report(dict(self.report, **{key: value}))

    def test_cli_without_evidence_creates_no_distribution(self):
        script = Path(__file__).with_name('package_preview.py')
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(script), '--require-windows-release', '--test-report', 'not-needed.json', '--output', directory], capture_output=True)
            self.assertEqual(2, result.returncode)
            self.assertIn(b'Executable distribution is blocked', result.stderr)
            self.assertEqual([], list(Path(directory).iterdir()))


if __name__ == '__main__':
    unittest.main()
