"""Package the main application's offline Access1 record review.

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
    if not (suite['passed'] > 709 and suite['failed'] == 0 and suite.get('skipped', 0) == 0
            and suite['registered'] == suite['passed']):
        raise ValueError('A complete successful test report is required.')

    build = root / 'src/ATIVBatteryGuard.App/bin/Release/net48'
    names = ('ATIVBatteryGuard.exe', 'ATIVBatteryGuard.Core.dll', 'ATIVBatteryGuard.exe.config')
    files = {name: (build/name).read_bytes() for name in names}
    if b'ReviewFixedReadResult\0' not in files[names[0]]:
        raise ValueError('The offline Access1 review action is required.')
    if any((name+'\0').encode() not in files[names[1]] for name in
           ('WsabiWmiFixedReadAccess1Review', 'WsabiWmiFixedReadAccess1ReviewParser')):
        raise ValueError('The Access1 record model and parser are required.')
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
        'distribution': 'OFFLINE ACCESS1 STORED-CANDIDATE RECORD REVIEW',
        'target': 'Windows10x64/.NETFramework4.8',
        'productSourceFingerprintSha256': fingerprint,
        'portableTestsPassed': suite['passed'], 'portableTestsFailed': 0, 'portableTestsSkipped': 0,
        'actualWpfXamlCompiled': True, 'actualWindowsRuntimeOrGuiTested': False,
        'actualWindowsGetFirmwareTypeTested': False, 'digitallySigned': False,
        'offlineAccess1RecordReview': True, 'reviewUsesPastedHistoricalTextOnly': True,
        'reviewAuthenticatesTextCurrentDeviceAccountOrTime': False,
        'reviewRevalidatesRawResponseOrComparisonContent': False,
        'reviewPerformsNewWmiOemOrReservationAccess': False,
        'reviewSavesOriginalTextOrChangesActualMode': False,
        'startupHardcodesUserCandidate': False,
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
    instructions = '''ATIV Battery Guard — Access1 조회 기록 검토판

이 ZIP 하나를 새 폴더에 모두 풀고 ATIVBatteryGuard.exe를 일반 권한으로 실행하세요.
다른 분석 ZIP이나 삼성 DLL을 같은 폴더에 넣을 필요는 없습니다.
대상: Windows 10 x64 / .NET Framework 4.8. 미서명 개발 빌드이며 이번 Windows 실기는 아직 미확인입니다.

‘고정 보호 저장값 조회 기록 · Access1’에 이미 만든 fixed-read-a-access1-result TXT 내용을 붙여넣고
‘Access1 기록 확인’을 누르면 과거 도구의 판정 기록을 확인할 수 있습니다.
현재값 조회나 새 실험이 아닙니다. 새 TXT·진단·삼성 DLL·EXE를 다시 제출할 필요가 없습니다.
원래 A/Access1/Query65 시험은 끝났고 예약은 소모됐습니다. 기존 실험 EXE를 다시 실행하거나 예약을 변경하지 마세요.

정확한 Access1 제목·필수 상태·후보0/1·관련 정리 Complete가 모두 맞는 경우만 기록을 표시합니다.
누락·모순·중복·오류·Pending을 저장값 성공으로 표시하지 않습니다. 입력한 원문은 검토 뒤 비우며 저장하지 않습니다.
화면의 후보는 제출된 텍스트에 적힌 판정입니다. 원문 frame/비교 내용이 없어 응답 귀속을 재검증하지 않습니다.
텍스트의 진위·현재 장치·계정·실행 시각을 인증하거나 지금의 보호 상태로 표시하지 않습니다.
후보0/1은 현재 임계값·80% 제한 적용·충전기 동작의 증거가 아니며 제어 버튼을 활성화하지 않습니다.
처음 실행하면 기록은 비어 있습니다. 실제 관측이나 사용자 원문을 빌드에 넣지 않았습니다.

기존 배터리 표시·로컬 희망 설정·읽기 전용 파일/드라이버/WMI/부팅 방식 보고는 유지합니다.
새 기록 검토는 추가 WMI·OEM 호출·관리자 권한·예약 파일 접근·네트워크 통신을 하지 않습니다.
기존 Query65 기록 검토와 Access1 기록은 별도이며 서로 대체하지 않습니다.
전체 경로·계정·시리얼·고유 식별자·예외 원문을 결과에 보관하거나 자동 전송하지 않습니다.

삼성 원본 DLL/EXE·실험 실행 파일은 포함하지 않았습니다.
삼성 DLL 초기화·OEM 명령·서비스/드라이버 변경·펌웨어 쓰기·보안 설정 변경을 수행하지 않습니다.
배터리 상태 표시는 기존 Windows 조회이며 실제 보호 설정 조회·80%/100% 충전 제어는 Unsupported입니다.
'''
    files['먼저 읽어주세요.txt'] = instructions.replace('\n', '\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(data)+'  '+name+'\n' for name, data in sorted(files.items())).encode()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output/'ATIVBatteryGuard-ACCESS1-RECORD-REVIEW.zip'
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
