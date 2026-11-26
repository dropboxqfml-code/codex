"""Exercise the real final personal build without executing Windows binaries."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from package_personal_030 import prepare, write_package


class PersonalRelease030Tests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.build = self.root/'src/ATIVBatteryGuard.App/bin/Release/net48'
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.work = Path(self.directory.name)
        self.report = self.work/'tests.json'
        self.report.write_text(json.dumps(dict(passed=1272,registered=1272,failed=0,skipped=0)))

    def test_real_unsigned_personal_package_preserves_pending_windows_status_and_exact_files(self):
        files, info = prepare(self.root,self.build,self.report)
        self.assertEqual('0.3.0',info['releaseVersion'])
        self.assertEqual('personal-validation-pending',info['releaseStage'])
        for flag in ('digitallySigned','personalReleaseApproved','signedDistributionApproved','windowsFinalFileGuiPassed'):
            self.assertIs(info[flag],False)
        target = self.work/'personal.zip'
        write_package(target,files)
        with zipfile.ZipFile(target) as z:
            self.assertEqual(9,len(z.namelist()))
            self.assertEqual(set(files),set(z.namelist()))
            for name, raw in files.items():
                self.assertEqual(raw,z.read(name))
        self.assertTrue(info['onlyVersionChangedSinceValidatedRc3'])
        self.assertTrue(info['manualEvidenceInheritedFromRc3'])
        self.assertIn('코드 서명이 없습니다',files['먼저 읽어주세요.txt'].decode('utf-8-sig'))
        self.assertFalse(any(n.endswith(('.cmd','.ps1')) for n in files))

    def test_old_or_incomplete_product_regression_report_cannot_prepare_personal_package(self):
        for changes in (dict(passed=1271,registered=1271),dict(failed=1),dict(skipped=1),dict(failed=False)):
            report=dict(passed=1272,registered=1272,failed=0,skipped=0)
            report.update(changes)
            self.report.write_text(json.dumps(report))
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    prepare(self.root,self.build,self.report)

    def test_existing_archive_and_foreign_staging_are_preserved(self):
        target=self.work/'personal.zip'
        target.write_bytes(b'previous archive')
        with self.assertRaises(ValueError):
            write_package(target,{})
        self.assertEqual(b'previous archive',target.read_bytes())
        target.unlink()
        staging=target.with_suffix('.zip.pending')
        staging.write_bytes(b'other writer')
        with self.assertRaises(FileExistsError):
            write_package(target,{})
        self.assertEqual(b'other writer',staging.read_bytes())
        self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
