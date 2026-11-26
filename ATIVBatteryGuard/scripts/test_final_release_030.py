import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import test_release_validation as legacy
from final_release_030 import VERSION_SOURCE, read_json_bytes, verify_source_identity, verify_final_evidence


class Final030Tests(unittest.TestCase):
    def setUp(self):
        fixture = legacy.ReleaseValidationTests(); fixture.setUp()
        self.now = fixture.now
        self.files, self.report = fixture.timestamped_current_app_evidence()
        self.gui = dict(schemaVersion=1,status='passed',guiPassed=True,hardwareWritesPerformed=False,
                        bindingErrors=0,errors=[],nativePowerStatus='available',nativeWmiStatus='complete')
        self.raw = json.dumps(self.gui).encode()
        self.report.update(releaseVersion='0.3.0',guiExecuted=True,guiExitCode=0,
                           guiFileHashes=copy.deepcopy(self.report['fileHashes']),
                           guiReportSha256=hashlib.sha256(self.raw).hexdigest(),guiCompletedUtc=self.now.isoformat())

    def validate(self, report=None, raw=None, version='0.3.0'):
        return verify_final_evidence(self.files,'abc',version,report or self.report,raw or self.raw,self.now)

    def test_matching_synthetic_final_evidence(self):
        result=self.validate()
        self.assertTrue(result['signedFinalFileGatePassed'])
        self.assertNotIn('finalReleaseApproved',result)
        self.assertNotIn('publicationPerformed',result)

    def test_rc_and_scan_only_reports_cannot_become_final(self):
        with self.assertRaises(ValueError): self.validate(version='0.3.0-rc.3')
        for key,value in [('releaseVersion','0.3.0-rc.3'),('guiExecuted',False),('guiExitCode',False),
                          ('guiExitCode',1),('guiFileHashes',{}),('schemaVersion',True)]:
            with self.subTest(field=key):
                changed=copy.deepcopy(self.report);changed[key]=value
                with self.assertRaises(ValueError): self.validate(changed)

    def test_every_program_file_matches_both_scan_and_gui(self):
        for name in self.files:
            with self.subTest(file=name):
                changed=copy.deepcopy(self.report);changed['guiFileHashes'][name]='0'*64
                with self.assertRaises(ValueError):self.validate(changed)
                mutated=dict(self.files,**{name:b'changed'})
                with self.assertRaises(ValueError):verify_final_evidence(mutated,'abc','0.3.0',self.report,self.raw,self.now)

    def test_gui_bytes_exit_binding_writes_and_schema_are_not_ignored(self):
        with self.assertRaises(ValueError):self.validate(raw=self.raw+b' ')
        for key,value in [('schemaVersion','1'),('guiPassed','true'),('status','failed'),
                          ('hardwareWritesPerformed',True),('bindingErrors',1),('bindingErrors',False),('errors',['FAIL'])]:
            changed=dict(self.gui,**{key:value});raw=json.dumps(changed).encode()
            report=copy.deepcopy(self.report);report['guiReportSha256']=hashlib.sha256(raw).hexdigest()
            with self.subTest(field=key):
                with self.assertRaises(ValueError):self.validate(report,raw)

    def test_gui_and_security_timestamps_must_be_current_and_ordered(self):
        for stamp in [(self.now-timedelta(days=2)).isoformat(),(self.now+timedelta(seconds=1)).isoformat(),self.now.replace(tzinfo=None).isoformat()]:
            changed=dict(self.report,guiCompletedUtc=stamp)
            with self.assertRaises(ValueError):self.validate(changed)

    def test_missing_signatures_timestamps_and_detection_remain_blocking(self):
        for key,value in [('detections',1),('scanPassed',False),('realTimeProtectionEnabled',False)]:
            with self.assertRaises(ValueError):self.validate(dict(self.report,**{key:value}))
        for name in self.report['signatures']:
            changed=copy.deepcopy(self.report);changed['signatures'][name]['timestamped']=False
            with self.assertRaises(ValueError):self.validate(changed)

    def test_strict_evidence_reader_rejects_duplicates_extra_json_and_nonfinite_values(self):
        self.assertEqual({'a':1},read_json_bytes(b'\xef\xbb\xbf{"a":1}'))
        for raw in [b'{"a":1,"a":2}',b'{}{}',b'{"a":NaN}',b'[]',b'x'*65537]:
            with self.subTest(raw=raw[:30]):
                with self.assertRaises((ValueError,UnicodeError)):read_json_bytes(raw)

    def source_case(self):
        candidate={f'source-{i}.cs':str(i).encode() for i in range(206)}
        candidate[VERSION_SOURCE]=b'public const string Version = "0.3.0-rc.3";\n'
        current=dict(candidate);current[VERSION_SOURCE]=b'public const string Version = "0.3.0";\n'
        metadata={'sourceFiles':[dict(file=n,sha256=hashlib.sha256(b).hexdigest()) for n,b in candidate.items()]}
        return current,metadata

    def test_functional_candidate_identity_allows_only_exact_version_change(self):
        current,metadata=self.source_case();self.assertEqual(64,len(verify_source_identity(current,metadata)))
        for mutate in [lambda x:x.update({'extra.cs':b'x'}),lambda x:x.pop('source-0.cs'),
                       lambda x:x.update({'source-1.cs':b'new behavior'}),
                       lambda x:x.update({VERSION_SOURCE:x[VERSION_SOURCE]+b'other change'})]:
            changed=dict(current);mutate(changed)
            with self.assertRaises(ValueError):verify_source_identity(changed,metadata)

    def test_unversioned_rc_sources_are_not_final(self):
        current,metadata=self.source_case();current[VERSION_SOURCE]=b'public const string Version = "0.3.0-rc.3";\n'
        with self.assertRaises(ValueError):verify_source_identity(current,metadata)

    def test_actual_rc_preserves_unsigned_audit_and_cannot_pass_signed_audit(self):
        import zipfile
        from package_manual_control_beta import PROGRAM_NAMES, validate
        root=Path(__file__).resolve().parents[1]
        with zipfile.ZipFile(root.parent/'downloads/ATIVBatteryGuard-0.3.0-rc.3-WIN10-X64.zip') as z:
            files={name:z.read(name) for name in PROGRAM_NAMES}
        audit=validate(files)
        self.assertTrue(audit)
        self.assertTrue(all(entry['signed'] is False for entry in audit.values()))
        with self.assertRaises(ValueError):validate(files,signed=True)

    def test_actual_current_rc_cannot_emit_a_signed_review_package(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'output'
            tests=Path(directory)/'tests.json';tests.write_text(json.dumps(dict(passed=1272,registered=1272,failed=0,skipped=0)))
            result=subprocess.run([sys.executable,str(root/'scripts/package_final_030.py'),
                '--build-directory',str(root/'src/ATIVBatteryGuard.App/bin/Release/net48'),
                '--test-report',str(tests),'--windows-report',str(Path(directory)/'absent-windows.json'),
                '--gui-report',str(Path(directory)/'absent-gui.json'),'--output',str(target)],capture_output=True)
            self.assertNotEqual(0,result.returncode)
            self.assertIn(b'final source version must be exactly 0.3.0',result.stderr)
            self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
