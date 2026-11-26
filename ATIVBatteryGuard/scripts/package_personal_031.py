"""Package the state-emphasis patch against the field-validated personal 0.3.0."""
import argparse
import json
import zipfile
from pathlib import Path

from final_release_030 import read_json_bytes, sha
from package_final_030 import read_plain
from package_manual_control_beta import PROGRAM_NAMES, source_closure, validate
from package_personal_030 import write_package
from package_release_020 import gui_version

VERSION = '0.3.1'
ALLOWED_CHANGES = {
    'src/ATIVBatteryGuard.App/ViewModels/MainViewModel.cs',
    'src/ATIVBatteryGuard.App/Views/MainWindow.xaml',
    'src/ATIVBatteryGuard.App/Diagnostics/WindowsSmokeTest.cs',
    'src/ATIVBatteryGuard.Core/Models/ApplicationRelease.cs',
}


def prepare(root, build, test_report):
    tests = read_json_bytes(read_plain(test_report, 65536))
    if (any(type(tests.get(k)) is not int for k in ('passed','registered','failed','skipped'))
            or tests['passed'] < 1275 or tests['registered'] != tests['passed']
            or tests['failed'] != 0 or tests['skipped'] != 0):
        raise ValueError('Complete passing product regression evidence is required.')
    baseline = root.parent/'downloads/ATIVBatteryGuard-0.3.0-WIN10-X64.zip'
    baseline_hash = sha(read_plain(baseline,32*1024*1024))
    if baseline_hash != 'c5611d281d45ff316f30212291eb94bc485bc261f02452a088770601d83d1e2d':
        raise ValueError('Validated personal 0.3.0 archive differs.')
    with zipfile.ZipFile(baseline) as z:
        if z.testzip() is not None:
            raise ValueError('Baseline CRC differs.')
        candidate = read_json_bytes(z.read('BUILD-INFO.json'))
    field = read_json_bytes(read_plain(root/'reports/field-030-personal/assessment.json',65536))
    if (field.get('personal030FinalFileGuiPassed') is not True or field.get('validatedZipSha256') != baseline_hash
            or field.get('sourceFingerprintSha256') != candidate['productSourceFingerprintSha256']):
        raise ValueError('Field-validated personal 0.3.0 evidence is required.')
    sources = dict(source_closure(root,root/'src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj'))
    sources.update(source_closure(root,root/'src/ATIVBatteryGuard.ManualProtectionHelper/ATIVBatteryGuard.ManualProtectionHelper.csproj'))
    expected = {e['file']:e['sha256'] for e in candidate['sourceFiles']}
    if set(sources) != set(expected) or len(sources) != 207:
        raise ValueError('Product source closure differs.')
    changed = {n for n,b in sources.items() if sha(b) != expected[n]}
    if changed != ALLOWED_CHANGES:
        raise ValueError('Changes exceed the reviewed presentation/version/self-test patch.')
    fingerprint = sha(b''.join(n.encode()+b'\0'+b+b'\0' for n,b in sorted(sources.items())))
    files = {n:read_plain(build/n,32*1024*1024) for n in PROGRAM_NAMES}
    helper = root/'src/ATIVBatteryGuard.ManualProtectionHelper/bin/Release/net48'
    for n in PROGRAM_NAMES[2:]:
        if files[n] != read_plain(helper/n,32*1024*1024):
            raise ValueError('App/helper shared bytes differ.')
    audit = validate(files)
    version = gui_version(files['ATIVBatteryGuard.exe'],VERSION)
    info = dict(schemaVersion=1,application='ATIV Battery Guard',releaseVersion=VERSION,
                releaseStage='personal-validation-pending',distributionScope='personal-use',
                target='Windows10x64/.NETFramework4.8/940X3G/P05ACJ',digitallySigned=False,
                final030ReleaseApproved=False,personalReleaseApproved=False,signedDistributionApproved=False,
                windowsFinalFileGuiPassed=False,sourceFileCount=len(sources),productSourceFingerprintSha256=fingerprint,
                sourceFiles=[dict(file=n,sha256=sha(b)) for n,b in sorted(sources.items())],
                validatedPersonal030ZipSha256=baseline_hash,productSourceChangesComparedTo030=sorted(changed),
                hardwareImplementationAndDataFormatsUnchanged=True,stateEmphasisUsesLastAcceptedReadOnlySnapshot=True,
                manualEvidenceInheritedFromRc3=True,newManualImeRunClaimed=False,newDefenderScanClaimed=False,
                securitySettingsChanged=False,portableTests=tests,guiVersionResource=version,
                compiledReleaseAudit=audit,programFiles=[dict(file=n,bytes=len(files[n]),sha256=sha(files[n])) for n in PROGRAM_NAMES])
    guide = read_plain(root/'RELEASE_031_PERSONAL_USER_STEPS.txt',65536)
    info['userGuideSourceSha256'] = sha(guide)
    files['BUILD-INFO.json'] = (json.dumps(info,ensure_ascii=False,indent=2)+'\n').encode()
    files['먼저 읽어주세요.txt'] = guide.decode('utf-8-sig').replace('\r\n','\n').replace('\n','\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    return files,info


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--test-report',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();root=Path(__file__).resolve().parents[1]
    files,info=prepare(root,root/'src/ATIVBatteryGuard.App/bin/Release/net48',args.test_report)
    target=args.output/f'ATIVBatteryGuard-{VERSION}-WIN10-X64.zip'
    write_package(target,files)
    print(json.dumps(dict(file=target.name,bytes=target.stat().st_size,sha256=sha(target.read_bytes()),entries=len(files),
                         sourceFileCount=info['sourceFileCount'],productSourceFingerprintSha256=info['productSourceFingerprintSha256'])))


if __name__ == '__main__':
    main()
