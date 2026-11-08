"""Package the built read-only boot metadata UI, without OEM or experiment files.

Uses the existing development pefile parser on build bytes only. Does not run
the executable, invoke firmware, scan the notebook, or alter security settings.
"""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
import pefile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--test-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    suite = json.loads(args.test_report.read_text(encoding='utf-8'))
    if not (suite['passed'] > 0 and suite['failed'] == 0 and suite.get('skipped', 0) == 0
            and suite['registered'] == suite['passed']):
        raise ValueError('A complete successful test report is required.')

    build = root / 'src/ATIVBatteryGuard.App/bin/Release/net48'
    names = ('ATIVBatteryGuard.exe', 'ATIVBatteryGuard.Core.dll', 'ATIVBatteryGuard.exe.config')
    files = {name: (build/name).read_bytes() for name in names}
    pe = pefile.PE(data=files['ATIVBatteryGuard.exe'])
    if pe.FILE_HEADER.Machine != 0x8664 or not pe.OPTIONAL_HEADER.DATA_DIRECTORY[14].Size:
        raise ValueError('The managed Windows x64 build is required.')
    manifests = []
    for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if kind.id == 24:
            for item in kind.directory.entries:
                for language in item.directory.entries:
                    data = language.data.struct
                    manifests.append(ET.fromstring(pe.get_data(data.OffsetToData, data.Size)))
    levels = [level for manifest in manifests for level in manifest.iter()
              if level.tag.rsplit('}', 1)[-1] == 'requestedExecutionLevel']
    if len(levels) != 1 or levels[0].get('level') != 'asInvoker' or levels[0].get('uiAccess') != 'false':
        raise ValueError('The asInvoker/uiAccess=false executable manifest is required.')
    if b'GetFirmwareType' not in files['ATIVBatteryGuard.exe']:
        raise ValueError('The boot firmware metadata implementation is missing.')
    if '현재 Windows 부팅 방식'.encode('utf-16-le') not in files['ATIVBatteryGuard.Core.dll']:
        raise ValueError('The boot firmware report implementation is missing.')
    config = ET.fromstring(files['ATIVBatteryGuard.exe.config'])
    runtime = config.find('./startup/supportedRuntime')
    if runtime is None or runtime.get('sku') != '.NETFramework,Version=v4.8':
        raise ValueError('The .NET Framework 4.8 runtime configuration is required.')

    source_files = []
    for path in sorted((root/'src').rglob('*')):
        if (path.is_file() and not path.is_symlink() and not {'bin', 'obj'} & set(path.parts)
                and path.suffix in ('.cs', '.csproj', '.xaml', '.manifest', '.config')):
            source_files.append((path.relative_to(root).as_posix(), path.read_bytes()))
    fingerprint = sha(b''.join(name.encode() + b'\0' + data + b'\0' for name, data in source_files))
    info = {
        'schemaVersion': 1, 'application': 'ATIV Battery Guard',
        'distribution': 'READ-ONLY WINDOWS BOOT FIRMWARE METADATA',
        'target': 'Windows10x64/.NETFramework4.8',
        'productSourceFingerprintSha256': fingerprint,
        'portableTestsPassed': suite['passed'], 'portableTestsFailed': 0, 'portableTestsSkipped': 0,
        'actualWpfXamlCompiled': True, 'actualWindowsRuntimeOrGuiTested': False,
        'actualWindowsGetFirmwareTypeTested': False, 'digitallySigned': False,
        'windowsBootFirmwareApi': 'GetFirmwareType', 'maximumBootQueriesPerInspection': 1,
        'samsungFileProtocolVersion': 6, 'legacyProtocol5WithoutBootAcceptedAsNotCollected': True,
        'automaticallyElevates': False, 'firmwareVariableApisInvoked': False,
        'oemMethodInvocationAllowed': False, 'oemModulesIncludedOrLoaded': False,
        'driverServiceOrSecurityChangesAllowed': False, 'runtimeNetworking': False,
        'actualProtectionReadAndChargeControl': 'Unsupported',
        'publicSdkReadTrialEntry': 'ReadSpecificationUnavailable',
        'otherExperimentExecutablesIncluded': False,
        'programFiles': [{'file': name, 'bytes': len(files[name]), 'sha256': sha(files[name])} for name in names],
    }
    files['BUILD-INFO.json'] = (json.dumps(info, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    instructions = '''ATIV Battery Guard — Windows 부팅 방식 확인판

이 ZIP 하나를 새 폴더에 모두 풀고 ATIVBatteryGuard.exe를 일반 권한으로 실행하세요.
다른 분석 ZIP이나 삼성 DLL을 같은 폴더에 넣을 필요는 없습니다.
대상: Windows 10 x64 / .NET Framework 4.8. 미서명 개발 빌드이며 이번 Windows 실기는 아직 미확인입니다.

‘삼성 파일 정보 만들기’를 선택하면 기존 보고서에 ‘현재 Windows 부팅 방식’이 추가됩니다.
확인할 새 항목은 ‘조회 상태’와 ‘관측: BIOS / UEFI / Unknown’입니다.
전체 TXT·기존 진단·삼성 DLL·EXE를 다시 제출할 필요 없이 이 두 항목만 전달할 수 있습니다.

BIOS: 현재 Windows의 표준 EFI 변수 API 경로를 적용 대상에서 제외할 수 있습니다.
다른 firmware/SMM 호출자·드라이버의 부재나 배터리 보호 지원을 뜻하지 않습니다.
UEFI: 해당 경로를 배제하지 못하며 실제 통신 선택·보호 순서·충전 제어는 미확인입니다.
Unknown 또는 조회 오류: 부팅 방식과 경로 판단을 보류합니다. 실패를 BIOS로 추정하지 않습니다.

추가 API는 GetFirmwareType 읽기 1회뿐이며 EFI 변수 API를 호출하거나 권한을 조정하지 않습니다.
기존 파일 정보·커널 드라이버 등록·WMI 속성 조회는 기존 버튼에서 읽기 전용으로 유지합니다.
조회는 기존 별도 worker의 10초 제한을 따릅니다. 시작·주기적 배터리 조회에 새 수집을 연결하지 않습니다.
전체 경로·계정·시리얼·고유 식별자·예외 원문을 보고하거나 자동 전송하지 않습니다.

삼성 원본 DLL/EXE·실험 실행 파일은 포함하지 않았습니다.
삼성 DLL 초기화·OEM 명령·서비스/드라이버 변경·펌웨어 쓰기·보안 설정 변경을 수행하지 않습니다.
배터리 상태 표시는 기존 Windows 조회이며 실제 보호 설정 조회·80%/100% 충전 제어는 Unsupported입니다.
'''
    files['먼저 읽어주세요.txt'] = instructions.replace('\n', '\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(data)+'  '+name+'\n' for name, data in sorted(files.items())).encode()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output/'ATIVBatteryGuard-BOOT-FIRMWARE.zip'
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(files):
            raise ValueError('ZIP validation failed.')
        for name, data in files.items():
            if archive.read(name) != data:
                raise ValueError('ZIP build-byte validation failed.')
    print(json.dumps({'file': target.name, 'bytes': target.stat().st_size, 'sha256': sha(target.read_bytes()),
                      'entries': len(files), 'productSourceFingerprintSha256': fingerprint}))


if __name__ == '__main__':
    main()
