"""Build a local Windows check kit for RC3 or the unsigned personal 0.3.0."""
import argparse
import json
import zipfile
from pathlib import Path
from package_manual_control_beta import PROGRAM_NAMES, execution_level, sha, source_closure
from package_release_020 import gui_version

VERSION = '0.3.0-rc.3'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate-zip', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--release-version', choices=(VERSION, '0.3.0', '0.3.1'), default=VERSION)
    args = parser.parse_args()
    version = args.release_version
    personal = version in ('0.3.0', '0.3.1')
    root = Path(__file__).resolve().parents[1]
    with zipfile.ZipFile(args.candidate_zip) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != 9 or set(archive.namelist()) != set(PROGRAM_NAMES) | {'BUILD-INFO.json', '먼저 읽어주세요.txt', 'SHA256SUMS.txt'}:
            raise ValueError('Candidate ZIP CRC or file count is invalid.')
        files = {name: archive.read(name) for name in archive.namelist()}
    info = json.loads(files['BUILD-INFO.json'])
    stage = 'personal-validation-pending' if personal else 'validation-candidate'
    if info['releaseVersion'] != version or info['releaseStage'] != stage or info['final030ReleaseApproved']:
        raise ValueError('The input must match the pending candidate or personal build.')
    if personal and (info.get('digitallySigned') is not False or info.get('personalReleaseApproved') is not False
                     or info.get('windowsFinalFileGuiPassed') is not False):
        raise ValueError('The personal check cannot claim final-file Windows success in advance.')
    gui_version(files['ATIVBatteryGuard.exe'], version)
    if len(info['programFiles']) != 6 or {entry['file'] for entry in info['programFiles']} != set(PROGRAM_NAMES):
        raise ValueError('Candidate program allowlist differs.')
    for line in files['SHA256SUMS.txt'].decode().splitlines():
        expected, name = line.split('  ', 1)
        if name not in files or sha(files[name]) != expected:
            raise ValueError('Candidate internal checksum differs.')
    for record in info['programFiles']:
        if record['file'] not in PROGRAM_NAMES or len(files[record['file']]) != record['bytes'] or sha(files[record['file']]) != record['sha256']:
            raise ValueError('Candidate build information differs from program bytes.')
    build = root/'validation/ATIVBatteryGuard.ValidationCheck/bin/Release/net48'
    tool = build/'ATIVBatteryGuard.ValidationCheck.exe'
    execution_level(tool.read_bytes())
    gui_version(tool.read_bytes(), version)
    for name in ('ATIVBatteryGuard.ValidationCheck.exe', 'ATIVBatteryGuard.ValidationCheck.exe.config'):
        files[name] = (build/name).read_bytes()
    manifest = {
        'SchemaVersion': 1, 'ReleaseVersion': version,
        'SourceFingerprintSha256': info['productSourceFingerprintSha256'],
        'ProgramFiles': [{'Name': name, 'Bytes': len(files[name]), 'Sha256': sha(files[name])} for name in PROGRAM_NAMES]
    }
    files['VALIDATION-MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode()
    sources = sorted(source_closure(root, root/'validation/ATIVBatteryGuard.ValidationCheck/ATIVBatteryGuard.ValidationCheck.csproj'))
    tool_fingerprint = sha(b''.join(name.encode()+b'\0'+data+b'\0' for name,data in sources))
    validation_info = dict(releaseVersion=version, stage='personal-final-file-check-pending' if personal else 'validation-in-progress', finalReleaseApproved=False,
                           candidateZipSha256=sha(args.candidate_zip.read_bytes()),
                           validatorSourceFingerprintSha256=tool_fingerprint,
                           validatorSha256=sha(tool.read_bytes()),
                           windowsGuiExecutedInCloud=False, defenderScanExecuted=False, digitallySigned=False,
                           prior0211TextVisibleConfirmedByUser=True, prior0211HeaderClippingConfirmedByUser=False)
    files['VALIDATION-INFO.json'] = (json.dumps(validation_info, indent=2)+'\n').encode()
    if personal:
        guide = 'FINAL_031_PERSONAL_CHECK_USER_STEPS.txt' if version == '0.3.1' else 'FINAL_030_PERSONAL_CHECK_USER_STEPS.txt'
        files['최종 확인 순서.txt'] = (root/guide).read_text().replace('\r\n','\n').replace('\n','\r\n').encode('utf-8-sig')
    else:
        files['검증시작.cmd'] = ('@echo off\r\nsetlocal\r\n"%~dp0ATIVBatteryGuard.ValidationCheck.exe"\r\necho.\r\npause\r\n').encode('ascii')
        files['실사용 검증 순서.txt'] = (root/'VALIDATION_030_USER_STEPS.txt').read_text().replace('\r\n','\n').replace('\n','\r\n').encode('utf-8-sig')
        for name in ('sample-a.ativrecord', 'sample-b.ativrecord'):
            files['예제/'+name] = (root/'validation/samples'/name).read_bytes()
    # The kit has its own checksum list covering both the exact candidate and the local checker.
    files['SHA256SUMS.txt'] = ''.join(sha(data)+'  '+name+'\n' for name,data in sorted(files.items()) if name != 'SHA256SUMS.txt').encode()
    args.output.mkdir(parents=True, exist_ok=True)
    suffix = 'FINAL-CHECK' if personal else 'VALIDATION-KIT'
    target = args.output/f'ATIVBatteryGuard-{version}-{suffix}.zip'
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()): archive.writestr(name,data)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None and set(archive.namelist()) == set(files)
        for name,data in files.items(): assert archive.read(name) == data
    print(json.dumps(dict(file=target.name, bytes=target.stat().st_size, sha256=sha(target.read_bytes()),
                          entries=len(files), releaseVersion=version,
                          candidateZipSha256=validation_info['candidateZipSha256'],
                          validatorSourceFileCount=len(sources), validatorSourceFingerprintSha256=tool_fingerprint)))


if __name__ == '__main__':
    main()
