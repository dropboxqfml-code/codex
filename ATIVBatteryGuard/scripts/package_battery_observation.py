"""Package the ordinary GUI's offline review and passive battery observation.

Reads repository source and built managed PE bytes as data only. Does not run
the application, load OEM modules, access a trial marker or invoke firmware.
"""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import dnfile
import pefile

from package_protection_0to1 import sha, source_closure


PROGRAM_NAMES = ('ATIVBatteryGuard.exe', 'ATIVBatteryGuard.Core.dll',
                 'ATIVBatteryGuard.exe.config')
ARCHIVE_NAME = 'ATIVBatteryGuard-BATTERY-OBSERVATION.zip'


def validate_programs(files):
    app, core = files[PROGRAM_NAMES[0]], files[PROGRAM_NAMES[1]]
    for method in ('ReviewProtectionResult', 'StartBatteryObservation',
                   'StopBatteryObservation', 'SaveBatteryObservation'):
        if (method + '\0').encode() not in app:
            raise ValueError('The offline review and passive observation actions are required.')
    for kind in ('WsabiWmiProtection0To1Review', 'WsabiWmiProtection0To1ReviewParser',
                 'BatteryObservationSession'):
        if (kind + '\0').encode() not in core:
            raise ValueError('The historical review and bounded observation models are required.')
    for name in PROGRAM_NAMES[:2]:
        program = files[name]
        pe = pefile.PE(data=program)
        if pe.FILE_HEADER.Machine != 0x8664 or not pe.OPTIONAL_HEADER.DATA_DIRECTORY[14].Size:
            raise ValueError('Managed Windows x64 program bytes are required.')
        if pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].Size:
            raise ValueError('Unexpected signed bytes: update the disclosure before packaging.')
        if b'.NETFramework,Version=v4.8' not in program:
            raise ValueError('The .NET Framework 4.8 assembly target is required.')
        metadata = dnfile.dnPE(data=program)
        types = {str(row.TypeName) for row in metadata.net.mdtables.TypeDef.rows}
        methods = {str(row.Name) for row in metadata.net.mdtables.MethodDef.rows}
        if any('FakeManagement' in kind for kind in types) or methods & {'ConfirmDetachedForTests', 'PrepareForTests'}:
            raise ValueError('Portable SDK stand-ins must be absent from the release assemblies.')
        references = {str(row.Name) for row in metadata.net.mdtables.AssemblyRef.rows}
        if 'ATIVBatteryGuard.WmiInterop' in references:
            raise ValueError('The ordinary GUI distribution must not depend on the trial SDK bridge.')
        if name == PROGRAM_NAMES[1] and 'System.Management' in references:
            raise ValueError('The pure Core must remain independent of System.Management.')
        if name == PROGRAM_NAMES[0]:
            type_refs = {str(row.TypeName) for row in metadata.net.mdtables.TypeRef.rows}
            member_refs = {str(row.Name) for row in metadata.net.mdtables.MemberRef.rows}
            if type_refs & {'WsabiWmiProtectionTransitionSession', 'WsabiWmiProtectionTransitionAttempt',
                            'WsabiWmiProtection0To1Reservation', 'WsabiWmiWindowsProtectionTrial'}:
                raise ValueError('The ordinary GUI must not reference a live setting trial.')
            if member_refs & {'PrepareFixedReadAAsync', 'PrepareProtection0To1Async'}:
                raise ValueError('The ordinary GUI must not call trial preparation APIs.')
    pe = pefile.PE(data=app)
    levels = []
    for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if kind.id == 24:
            for item in kind.directory.entries:
                for language in item.directory.entries:
                    data = language.data.struct
                    manifest = ET.fromstring(pe.get_data(data.OffsetToData, data.Size))
                    levels.extend(element for element in manifest.iter()
                                  if element.tag.rsplit('}', 1)[-1] == 'requestedExecutionLevel')
    if len(levels) != 1 or levels[0].get('level') != 'asInvoker' or levels[0].get('uiAccess') != 'false':
        raise ValueError('The GUI must remain asInvoker/uiAccess=false.')
    runtime = ET.fromstring(files[PROGRAM_NAMES[2]]).find('./startup/supportedRuntime')
    if runtime is None or runtime.get('sku') != '.NETFramework,Version=v4.8':
        raise ValueError('The .NET Framework 4.8 runtime configuration is required.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--test-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    suite = json.loads(args.test_report.read_text(encoding='utf-8'))
    if not (suite['passed'] >= 887 and suite['failed'] == 0 and suite.get('skipped', 0) == 0
            and suite['registered'] == suite['passed']):
        raise ValueError('The complete historical review and observation suite must pass.')
    project = root / 'src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj'
    build = project.parent / 'bin/Release/net48'
    files = {name: (build / name).read_bytes() for name in PROGRAM_NAMES}
    validate_programs(files)
    sources = source_closure(root, project)
    if any(name.startswith('tests/') or '/tests/' in name for name, _ in sources):
        raise ValueError('Test stand-ins must be absent from the product source closure.')
    fingerprint = sha(b''.join(name.encode() + b'\0' + data + b'\0' for name, data in sources))
    info = {
        'schemaVersion': 1, 'application': 'ATIV Battery Guard',
        'distribution': 'HISTORICAL STORED TRANSITION REVIEW AND PASSIVE WINDOWS BATTERY OBSERVATION',
        'target': 'Windows10x64/.NETFramework4.8',
        'productSourceFingerprintSha256': fingerprint, 'sourceFileCount': len(sources),
        'sourceFiles': [{'file': name, 'sha256': sha(data)} for name, data in sources],
        'portableTestsPassed': suite['passed'], 'portableTestsFailed': 0, 'portableTestsSkipped': 0,
        'actualWpfXamlCompiled': True, 'actualWindowsRuntimeOrGuiTested': False,
        'digitallySigned': False, 'ordinaryUserAsInvoker': True,
        'historicalProtection0To1Review': True, 'reviewUsesPastedHistoricalTextOnly': True,
        'reviewAuthenticatesTextDeviceAccountOrTime': False,
        'reviewRevalidatesRawFirmwareResponse': False,
        'reviewSavesOriginalTextOrChangesActualMode': False,
        'startupHardcodesUserCandidate': False,
        'observationStartsManually': True, 'observationUsesExistingBatteryRefreshOnly': True,
        'observationProvider': 'GetSystemPowerStatus', 'existingBatteryPollSeconds': 10,
        'additionalBatteryTimersOrProviderReads': 0,
        'minimumAcceptedSampleIntervalSeconds': 10, 'maximumObservationElapsedSeconds': 7200,
        'maximumObservationSamples': 721, 'gapThresholdSeconds': 30,
        'mockSamplesRecorded': False, 'unknownAndGapsArePreserved': True,
        'observationSavesOnlyOnExplicitUserCommand': True,
        'observationResultPrefix': 'battery-observation-',
        'absoluteTimesPathsAccountsIdentifiersOrRawErrorsInObservation': False,
        'electricalCurrentOrChargerRegistersMeasured': False,
        'automaticChargeLimitSuccessClassification': False,
        'newWmiOemInitializationOrReservationAccess': False,
        'automaticallyElevates': False, 'runtimeNetworking': False,
        'driverServiceSecurityFirmwareOrTrialMarkerChanges': False,
        'oemOriginalModulesIncludedOrLoaded': False, 'experimentalExecutablesIncluded': False,
        'mainApplicationActualProtectionReadAndChargeControl': 'Unsupported',
        'programFiles': [{'file': name, 'bytes': len(files[name]), 'sha256': sha(files[name])}
                         for name in PROGRAM_NAMES],
    }
    files['BUILD-INFO.json'] = (json.dumps(info, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    instructions = '''ATIV Battery Guard — 저장 전환 기록과 Windows 배터리 관찰

이 ZIP 하나를 새 폴더에 모두 풀고 ATIVBatteryGuard.exe를 일반 권한으로 실행하세요.
다른 ZIP이나 삼성 DLL을 합칠 필요가 없습니다. 대상: Windows 10 x64 / .NET Framework 4.8.
미서명 개발 빌드이며 이 GUI 버전의 실제 Windows 실행은 아직 확인하지 않았습니다.

이미 생성한 Protection0To1-v1 TXT는 ‘보호 설정 전환 기록’에 선택적으로 붙여넣어 확인합니다.
원문은 검토 후 비우며 자동 저장하지 않습니다. 처음에는 과거 값이 비어 있습니다.
표시되는 값은 과거 텍스트의 도구 보고입니다. 현재 장치·시각·actualMode를 인증하거나
원문 frame·응답 귀속을 다시 검증하는 기능이 아닙니다. 기록 검토 없이도 관찰할 수 있습니다.

‘Windows 배터리 상태 관찰’에서 ‘새 관찰 시작’을 누르고 일상적으로 사용하세요.
다음 기존 배터리 갱신부터 약 10초 주기의 상태를 기록합니다. 추가 조회나 새 타이머는 없습니다.
새 관찰 시작은 이전 메모리 기록을 비우므로 보관하려면 먼저 ‘관찰 TXT 저장’을 누르세요.
최대 2시간·721개이며 절전 등 긴 갱신 간격과 Unknown을 그대로 구분하고 보간하지 않습니다.
시뮬레이션 중에는 시작할 수 없고, 시뮬레이션을 켜면 실제 관찰을 중단합니다.
‘관찰 중단’ 뒤 ‘관찰 TXT 저장’을 누르면 새 battery-observation-*.txt가 생성됩니다.
저장 위치는 기존 %LOCALAPPDATA%\\ATIVBatteryGuard 폴더입니다. ‘정보 파일 위치 열기’로 확인하세요.
저장을 누르기 전에는 관찰 파일을 만들지 않으며, 앱을 닫으면 미저장 메모리 기록은 사라집니다.
샘플에는 상대 경과초·잔량·AC·Windows 충전 표시·오류 유무·긴 간격 여부만 포함합니다.
전체 경로·계정·고유 식별자·절대 시각·예외 원문을 관찰 내용에 넣거나 자동 전송하지 않습니다.

보호 저장 후보 전환과 실제 충전기의 전기적 동작은 별개입니다.
80% 유지 또는 NotCharging 표시가 반복되어도 충전 제한 성공으로 자동 판정하지 않습니다.
이 기능은 전류·충전기 레지스터를 측정하지 않으며, 강제 방전·충전·재부팅 시험을 요구하지 않습니다.
기존 배터리 표시와 희망 설정은 유지하지만 실제 보호 조회·80%/100% 제어는 Unsupported입니다.

이미 사용한 Protection0To1-v1/A/Access1/Query65 시험은 끝났습니다.
예전 시험 EXE를 다시 실행하거나 예약을 삭제·수정·재사용하지 마세요.
이번 ZIP에는 실험 EXE·WmiInterop.dll·삼성 원본 DLL/EXE·firmware·PDB를 넣지 않았습니다.
새 OEM 읽기/쓰기·DLL 초기화·드라이버/서비스·보안 변경·예약 접근을 추가하지 않았습니다.
이전 TXT·진단·삼성 DLL·EXE를 다시 제출할 필요가 없습니다.
'''
    files['먼저 읽어주세요.txt'] = instructions.replace('\n', '\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(data) + '  ' + name + '\n'
                                    for name, data in sorted(files.items())).encode()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / ARCHIVE_NAME
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(files):
            raise ValueError('ZIP CRC or entry allowlist validation failed.')
        for name, data in files.items():
            if archive.read(name) != data:
                raise ValueError('ZIP build-byte validation failed.')
    print(json.dumps({'file': target.name, 'bytes': target.stat().st_size,
                      'sha256': sha(target.read_bytes()), 'entries': len(files),
                      'productSourceFingerprintSha256': fingerprint, 'sourceFileCount': len(sources)}))


if __name__ == '__main__':
    main()
