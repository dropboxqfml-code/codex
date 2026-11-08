"""Package the explicitly approved Access1 additional fixed-read trial.

No binary is loaded or executed. This development script does not query WMI,
touch a notebook reservation, invoke firmware or include an OEM module.
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
    if not (suite['passed'] > 700 and suite['failed'] == 0 and suite.get('skipped', 0) == 0
            and suite['registered'] == suite['passed']):
        raise ValueError('The complete fixed-read regression suite must pass.')
    build = root/'src/ATIVBatteryGuard.FixedReadTrial/bin/Release/net48'
    names = ('ATIVBatteryGuard.FixedReadTrial.exe', 'ATIVBatteryGuard.Core.dll',
             'ATIVBatteryGuard.WmiInterop.dll', 'ATIVBatteryGuard.FixedReadTrial.exe.config')
    files = {name: (build/name).read_bytes() for name in names}
    if ('FixedModeReadA-Access1'.encode('utf-16-le') not in files[names[0]] or
            'fixed-read-a-access1-result-'.encode('utf-16-le') not in files[names[0]]):
        raise ValueError('The Access1 purpose and distinct TXT prefix are required.')
    for name in names[:3]:
        pe = pefile.PE(data=files[name])
        if pe.FILE_HEADER.Machine != 0x8664 or not pe.OPTIONAL_HEADER.DATA_DIRECTORY[14].Size:
            raise ValueError('A managed Windows x64 build is required.')
        if pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].Size:
            raise ValueError('Unexpected signed bytes: update the distribution disclosure before packaging.')
    pe = pefile.PE(data=files[names[0]])
    levels = []
    for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if kind.id == 24:
            for item in kind.directory.entries:
                for language in item.directory.entries:
                    data = language.data.struct
                    manifest = ET.fromstring(pe.get_data(data.OffsetToData, data.Size))
                    levels += [element for element in manifest.iter()
                               if element.tag.rsplit('}', 1)[-1] == 'requestedExecutionLevel']
    if len(levels) != 1 or levels[0].get('level') != 'asInvoker' or levels[0].get('uiAccess') != 'false':
        raise ValueError('The asInvoker/uiAccess=false executable manifest is required.')
    config = ET.fromstring(files[names[3]])
    runtime = config.find('./startup/supportedRuntime')
    if runtime is None or runtime.get('sku') != '.NETFramework,Version=v4.8':
        raise ValueError('The .NET Framework 4.8 runtime configuration is required.')

    sources = []
    for name in ('ATIVBatteryGuard.Core', 'ATIVBatteryGuard.WmiInterop', 'ATIVBatteryGuard.FixedReadTrial'):
        for path in sorted((root/'src'/name).rglob('*')):
            if (path.is_file() and not path.is_symlink() and not {'bin', 'obj'} & set(path.parts)
                    and path.suffix in ('.cs', '.csproj', '.manifest', '.config')):
                sources.append((path.relative_to(root).as_posix(), path.read_bytes()))
    # This SDK tool links the existing read-only token probe from the App tree.
    linked_probe = root/'src/ATIVBatteryGuard.App/Diagnostics/ProcessElevationProbe.cs'
    sources.append((linked_probe.relative_to(root).as_posix(), linked_probe.read_bytes()))
    fingerprint = sha(b''.join(name.encode()+b'\0'+data+b'\0' for name, data in sorted(sources)))
    info = {
        'schemaVersion': 1, 'application': 'ATIV Battery Guard Additional Fixed Read Trial Access1',
        'purpose': 'FixedModeReadA-Access1', 'target': 'Windows10x64/.NETFramework4.8',
        'productSourceFingerprintSha256': fingerprint,
        'portableTestsPassed': suite['passed'], 'portableTestsFailed': 0, 'portableTestsSkipped': 0,
        'actualWindowsRuntimeSdkOrNotebookTested': False, 'digitallySigned': False,
        'manualInteractiveStartRequired': True, 'maximumWmiMethodInvocations': 1,
        'maximumAdditionalPreparationsAfterStart': 1,
        'currentElevatedTokenRequiredBeforeStartReservationAndWmi': True,
        'manualSameAccountElevationIsUserProcedure': True,
        'accountNamesGroupsOrSidsRead': False,
        'maximumFixedStoredByteSamples': 1, 'handshakes': 0, 'oemInitializations': 0,
        'retries': 0, 'settingWrites': 0, 'fallbackB': 0,
        'ownerAcquireSecondsMaximum': 2, 'responseDisplayDeadlineSeconds': 10,
        'displayTimeoutTerminatesFirmwareOrProcess': False,
        'newPurposeDurableReservation': True, 'previousExperimentReservationAccessed': False,
        'consumedPreviousBudgetRestored': False, 'automaticThirdTrialOrFallback': False,
        'communicationBufferAndMailboxExchange': True,
        'normalPlatformApplicabilityAssumptionsRequired': True,
        'storedCandidateConfirmsThresholdOrCharging': False,
        'automaticallyElevates': False, 'runtimeNetworking': False,
        'driverServiceSecurityOrFlashChanges': False,
        'oemOriginalModulesIncludedOrLoaded': False, 'otherExperimentExecutablesIncluded': False,
        'chargeControl': 'Unsupported', 'genericSdkReadTrialEntry': 'ReadSpecificationUnavailable',
        'programFiles': [{'file': name, 'bytes': len(files[name]), 'sha256': sha(files[name])} for name in names],
    }
    files['BUILD-INFO.json'] = (json.dumps(info, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    instructions = '''ATIV Battery Guard — 승인된 추가 단발 조회 Access1

이 ZIP 하나를 새 로컬 폴더에 모두 풀고 ATIVBatteryGuard.FixedReadTrial.exe만 같은 Windows 계정에서 수동 관리자 실행하세요.
실행 파일을 오른쪽 클릭해 ‘관리자 권한으로 실행’을 선택합니다. 자동 UAC/runas는 없습니다.
다른 계정의 암호 입력이 필요하거나 보안 기능이 차단하면 중단하고 우회하지 마세요.
기존 프로그램/다른 ZIP/삼성 DLL을 같은 폴더에 합치지 마세요.
Windows 10 x64, .NET Framework 4.8, 기존 940X3G/930X3G · P05ACJ.128.140819.dg profile 전용입니다.
미서명 개발 빌드입니다. 보안 설정 변경·백신 예외·서명 우회는 요구하지 않습니다.

이전 A는 일반 실행의 MethodEnumeration/AccessDenied로 종료됐고 기존 예약은 그대로입니다.
이번 도구는 별도로 승인된 추가 준비1회입니다. 기존 EXE 재실행이나 예약 복구가 아닙니다.
현재 TokenElevation을 먼저 읽으며 Elevated가 아니거나 불명이면 START·예약·WMI 준비 전에 종료합니다.
토큰이 Elevated여도 WMI 접근·firmware/gate·충전 제어 성공을 보장하지 않습니다.
실행만으로 펌웨어를 호출하지 않습니다. 화면의 Access1 이름과 토큰 Elevated를 확인한 뒤 START를 직접 입력합니다.
그 시점에 추가1회 전용 영속 예약을 먼저 기록합니다. 이후 준비 실패·권한 거부·시간 초과도 재시도하지 않습니다.
모델/BIOS/고정 WMI 형식 불일치·불명은 method 호출 없이 종료합니다.
START 뒤에는 재실행·예약 삭제·다른 계정/폴더를 이용해 시험을 반복하지 마세요. 과거 예약을 조회/변경하지 않습니다.
자동 추가 시험·세 번째 예약·대체 명령은 없습니다.

WMI method 최대1회, 고정 저장 byte 샘플0~1회입니다.
초기화·handshake·재시도·다른 명령·설정/임계값 쓰기·B fallback은 없습니다.
보호 설정을 바꾸지 않지만 기존 통신 buffer와 EC mailbox의 입력 게시·응답 교환은 수행합니다.
정상 초기화·inline 처리·같은 비재진입 SMM 실행 흐름이라는 명시적 플랫폼 전제를 사용합니다.
이 전제의 실제 실행 상태를 직접 관측한 도구는 아닙니다. gate가 닫혀 있으면 값을 얻지 못할 수 있습니다.

owner 획득 한도2초, 응답 표시10초는 펌웨어의 강제 중단 시간이 아닙니다.
시간 초과/취소/실제 종료 불명 시 관련 정리나 준비 반환을 계속 기다릴 수 있습니다.
Pending이면 창을 강제로 닫거나 프로세스를 종료하지 말고 그대로 둡니다. Ctrl+C는 중단 의사만 전달합니다.
SDK Cancel·합성 완료·watchdog/프로세스 강제 종료·자동 재시작은 없습니다.
‘관련 정리: Complete’ 또는 호출 전 종료 안내 뒤 Enter를 눌러 닫으세요.

같은 폴더의 fixed-read-a-access1-result-*.txt에 토큰·고정 상태/세부 오류·정리 분류와 후보0/1만 기록합니다.
이번 새 TXT 결과만 전달하면 됩니다. 기존 진단·삼성 DLL·EXE 재제출은 필요 없습니다.
raw frame/비교 내용·전체 경로·계정·고유 ID·예외 원문은 기록하지 않고 네트워크로 보내지 않습니다.
TXT 저장 실패는 재시도나 자원 조기 해제의 이유가 되지 않습니다.

후보0/1은 저장 모드 후보입니다. 현재80/75임계값·80% 제한 적용·충전 성공을 입증하지 않습니다.
기존 앱의 실제 보호 조회/충전 제어는 Unsupported로 유지됩니다.
삼성 원본 DLL·firmware·과거 실험 EXE·드라이버/서비스 설치·보안 변경은 포함하지 않았습니다.
실제 Windows SDK/노트북에서 이 새 도구를 실행한 검증은 아직 없습니다.
'''
    files['먼저 읽어주세요.txt'] = instructions.replace('\n', '\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(data)+'  '+name+'\n' for name, data in sorted(files.items())).encode()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output/'ATIVBatteryGuard-FIXED-READ-A-ACCESS1.zip'
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
                      'entries': len(files), 'sourceFingerprintSha256': fingerprint}))


if __name__ == '__main__':
    main()
