"""Prepare the authorized unsigned personal build; preserve the signed release gate."""
import argparse
import json
import os
import zipfile
from pathlib import Path

from final_release_030 import FINAL_VERSION, read_json_bytes, sha, verify_source_identity
from package_final_030 import read_plain
from package_manual_control_beta import PROGRAM_NAMES, source_closure, validate
from package_release_020 import gui_version


def prepare(root, build, test_report):
    tests = read_json_bytes(read_plain(test_report, 65536))
    if (any(type(tests.get(k)) is not int for k in ('passed', 'registered', 'failed', 'skipped'))
            or tests['passed'] < 1272 or tests['registered'] != tests['passed']
            or tests['failed'] != 0 or tests['skipped'] != 0):
        raise ValueError('Complete passing product regression evidence is required.')
    baseline = read_json_bytes(read_plain(root/'reports/release-030-rc3-validation.json', 65536))
    rc3 = root.parent/'downloads/ATIVBatteryGuard-0.3.0-rc.3-WIN10-X64.zip'
    if sha(read_plain(rc3, 32*1024*1024)) != baseline['package']['sha256']:
        raise ValueError('Validated RC3 archive differs.')
    with zipfile.ZipFile(rc3) as z:
        if z.testzip() is not None:
            raise ValueError('Validated RC3 CRC differs.')
        candidate = read_json_bytes(z.read('BUILD-INFO.json'))
    close = read_json_bytes(read_plain(root/'reports/field-ime-close-rc3/assessment.json', 65536))
    if close.get('startupAndFocusedClosePassed') is not True or close.get('sourceFingerprintMatchesReleasedRc3') is not True:
        raise ValueError('Validated RC3 close evidence is required.')
    sources = dict(source_closure(root, root/'src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj'))
    sources.update(source_closure(root, root/'src/ATIVBatteryGuard.ManualProtectionHelper/ATIVBatteryGuard.ManualProtectionHelper.csproj'))
    fingerprint = verify_source_identity(sources, candidate)
    files = {name: read_plain(build/name, 32*1024*1024) for name in PROGRAM_NAMES}
    helper = root/'src/ATIVBatteryGuard.ManualProtectionHelper/bin/Release/net48'
    for name in PROGRAM_NAMES[2:]:
        if files[name] != read_plain(helper/name, 32*1024*1024):
            raise ValueError('App and helper shared build bytes differ.')
    audit = validate(files)
    version = gui_version(files['ATIVBatteryGuard.exe'], FINAL_VERSION)
    info = dict(schemaVersion=1, application='ATIV Battery Guard', releaseVersion=FINAL_VERSION,
                releaseStage='personal-validation-pending', distributionScope='personal-use',
                target='Windows10x64/.NETFramework4.8/940X3G/P05ACJ', digitallySigned=False,
                final030ReleaseApproved=False, personalReleaseApproved=False,
                signedDistributionApproved=False, windowsFinalFileGuiPassed=False,
                sourceFileCount=len(sources), productSourceFingerprintSha256=fingerprint,
                sourceFiles=[dict(file=n,sha256=sha(d)) for n,d in sorted(sources.items())],
                validatedRc3ZipSha256=baseline['package']['sha256'], onlyVersionChangedSinceValidatedRc3=True,
                manualEvidenceInheritedFromRc3=True, newManualImeRunClaimed=False,
                newDefenderScanClaimed=False, securitySettingsChanged=False,
                portableTests=tests, testReportSha256=sha(read_plain(test_report,65536)),
                guiVersionResource=version, compiledReleaseAudit=audit,
                programFiles=[dict(file=n,bytes=len(files[n]),sha256=sha(files[n])) for n in PROGRAM_NAMES])
    guide = read_plain(root/'RELEASE_030_PERSONAL_USER_STEPS.txt', 65536)
    info['userGuideSourceSha256'] = sha(guide)
    files['BUILD-INFO.json'] = (json.dumps(info,ensure_ascii=False,indent=2)+'\n').encode()
    files['먼저 읽어주세요.txt'] = guide.decode('utf-8-sig').replace('\r\n','\n').replace('\n','\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(d)+'  '+n+'\n' for n,d in sorted(files.items())).encode()
    return files, info


def write_package(target, files):
    if target.exists():
        raise ValueError('A previous personal archive must not be overwritten.')
    target.parent.mkdir(parents=True,exist_ok=True)
    staging = target.with_suffix('.zip.pending')
    owns_staging = False
    try:
        with zipfile.ZipFile(staging,'x',zipfile.ZIP_DEFLATED) as z:
            owns_staging = True
            for n,d in sorted(files.items()):
                z.writestr(n,d)
        with zipfile.ZipFile(staging) as z:
            if z.testzip() is not None or len(z.namelist()) != 9 or set(z.namelist()) != set(files):
                raise ValueError('Personal ZIP allowlist or CRC differs.')
            if any(z.read(n) != d for n,d in files.items()):
                raise ValueError('Personal ZIP bytes differ.')
        os.link(staging,target)
        staging.unlink()
    finally:
        if owns_staging and staging.exists():
            staging.unlink()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--test-report',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    files,info = prepare(root, root/'src/ATIVBatteryGuard.App/bin/Release/net48', args.test_report)
    target = args.output/'ATIVBatteryGuard-0.3.0-WIN10-X64.zip'
    write_package(target, files)
    print(json.dumps(dict(file=target.name,bytes=target.stat().st_size,sha256=sha(target.read_bytes()),
                         entries=len(files),sourceFileCount=info['sourceFileCount'],
                         productSourceFingerprintSha256=info['productSourceFingerprintSha256'],
                         windowsFinalFileGuiPassed=False,personalReleaseApproved=False)))


if __name__ == '__main__':
    main()
