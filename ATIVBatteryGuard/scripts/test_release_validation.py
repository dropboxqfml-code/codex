import copy
import hashlib
import unittest
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from release_validation import validate_release


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
