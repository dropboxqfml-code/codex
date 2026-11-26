"""Replace the short guide with a manual; retain the field-validated six files."""
import argparse
import json
import zipfile
from pathlib import Path

from final_release_030 import read_json_bytes, sha
from package_final_030 import read_plain
from package_manual_control_beta import PROGRAM_NAMES, validate
from package_personal_030 import write_package
from package_release_020 import gui_version

BASE_SHA256 = 'e300ea3ee3df643c966f1fb9ba3c51f4b938aa70afc62bcc7703924b19bf1f0c'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    base = root.parent/'downloads/ATIVBatteryGuard-0.3.1-WIN10-X64.zip'
    if sha(read_plain(base,32*1024*1024)) != BASE_SHA256:
        raise ValueError('Validated program ZIP differs.')
    with zipfile.ZipFile(base) as z:
        expected = set(PROGRAM_NAMES) | {'먼저 읽어주세요.txt','BUILD-INFO.json','SHA256SUMS.txt'}
        if z.testzip() is not None or len(z.namelist()) != 9 or set(z.namelist()) != expected:
            raise ValueError('Validated ZIP allowlist or CRC differs.')
        files = {n:z.read(n) for n in z.namelist()}
    sums = dict((n,h) for h,n in (line.split('  ',1) for line in files['SHA256SUMS.txt'].decode().splitlines()))
    if set(sums) != set(files)-{'SHA256SUMS.txt'} or any(sha(files[n]) != h for n,h in sums.items()):
        raise ValueError('Validated ZIP checksums differ.')
    info = read_json_bytes(files['BUILD-INFO.json'])
    evidence_raw = read_plain(root/'reports/field-031-personal/assessment.json',65536)
    evidence = read_json_bytes(evidence_raw)
    if (info['releaseVersion'] != '0.3.1' or evidence.get('personalUseValidationComplete') is not True
            or evidence.get('validatedProgramZipSha256') != BASE_SHA256
            or evidence.get('sourceFingerprintSha256') != info['productSourceFingerprintSha256']):
        raise ValueError('Completed personal 0.3.1 field evidence is required.')
    binaries = {n:files[n] for n in PROGRAM_NAMES}
    validate(binaries)
    gui_version(binaries['ATIVBatteryGuard.exe'],'0.3.1')
    manual_source = read_plain(root/'USER_MANUAL_031_KO.txt',65536)
    manual = manual_source.decode('utf-8-sig').replace('\r\n','\n').replace('\n','\r\n').encode('utf-8-sig')
    del files['먼저 읽어주세요.txt']
    manual_name = '사용자 매뉴얼.txt'
    files[manual_name] = manual
    info['previousUserGuideSourceSha256'] = info.pop('userGuideSourceSha256')
    info.update(releaseStage='personal-stable',personalReleaseApproved=True,windowsFinalFileGuiPassed=True,
                userManualFile=manual_name,userManualSourceSha256=sha(manual_source),userManualSha256=sha(manual),
                documentationOnlyRepackage=True,validatedProgramZipSha256=BASE_SHA256,
                programFilesByteIdenticalToValidated031=True,field031AssessmentSha256=sha(evidence_raw),
                newWindowsGuiRunClaimed=False)
    files['BUILD-INFO.json'] = (json.dumps(info,ensure_ascii=False,indent=2)+'\n').encode()
    files['SHA256SUMS.txt'] = ''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items()) if n != 'SHA256SUMS.txt').encode()
    if any(files[n] != binaries[n] for n in PROGRAM_NAMES):
        raise ValueError('Documentation update changed a program file.')
    target = args.output/'ATIVBatteryGuard-0.3.1-WIN10-X64-MANUAL.zip'
    write_package(target,files)
    print(json.dumps(dict(file=target.name,bytes=target.stat().st_size,sha256=sha(target.read_bytes()),entries=len(files),
                         programFilesByteIdentical=True,baseZipSha256=BASE_SHA256,userManualFile=manual_name),ensure_ascii=False))


if __name__ == '__main__':
    main()
