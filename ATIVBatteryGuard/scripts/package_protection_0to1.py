"""Package the separately approved, fixed Protection0To1-v1 trial.

This development script reads source and built PE bytes as data only. It never
loads/runs a program, queries WMI, accesses a notebook marker, or invokes OEM
code. Existing archives are not replaced.
"""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import pefile


PROGRAM_NAMES = (
    'ATIVBatteryGuard.ProtectionTransitionTrial.exe',
    'ATIVBatteryGuard.Core.dll',
    'ATIVBatteryGuard.WmiInterop.dll',
    'ATIVBatteryGuard.ProtectionTransitionTrial.exe.config',
)
PURPOSE = 'Protection0To1-v1'
RESULT_PREFIX = 'protection-0to1-result-'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_closure(root, project):
    """Hash project sources and declared links without importing their code."""
    root = root.resolve()
    pending, projects, collected = [project], set(), {}

    def add(path):
        if path.is_symlink():
            raise ValueError('A source link must resolve to an ordinary repository file.')
        path = path.resolve(strict=True)
        try:
            relative = path.relative_to(root)
        except ValueError as error:
            raise ValueError('A source dependency escaped the project root.') from error
        if not path.is_file() or {'bin', 'obj'} & set(relative.parts):
            raise ValueError('A source dependency must be an ordinary non-build file.')
        collected[relative.as_posix()] = path.read_bytes()
        return path

    while pending:
        path = add(pending.pop())
        if path in projects:
            continue
        projects.add(path)
        for source in sorted(path.parent.rglob('*')):
            if (source.is_file() and not {'bin', 'obj'} & set(source.relative_to(root).parts)
                    and source.suffix in ('.cs', '.csproj', '.xaml', '.manifest', '.config')):
                add(source)
        for item in ET.fromstring(path.read_bytes()).iter():
            tag = item.tag.rsplit('}', 1)[-1]
            include = item.get('Include')
            if tag not in ('Compile', 'ProjectReference') or include is None:
                continue
            if any(part in include for part in ('$', '*', '?', ';')):
                raise ValueError('Declare linked sources and project references with literal repository paths.')
            dependency = add(path.parent / include.replace('\\', '/'))
            if tag == 'ProjectReference':
                pending.append(dependency)
        # Repository-local compiler/build options are part of the source pin.
        parent = path.parent
        while parent == root or root in parent.parents:
            for name in ('Directory.Build.props', 'Directory.Build.targets'):
                options = parent / name
                if options.exists():
                    add(options)
            if parent == root:
                break
            parent = parent.parent
    return sorted(collected.items())


def validate_programs(files):
    exe = files[PROGRAM_NAMES[0]]
    if PURPOSE.encode('utf-16-le') not in exe or RESULT_PREFIX.encode('utf-16-le') not in exe:
        raise ValueError('The new fixed purpose and distinct result prefix are required.')
    core = files['ATIVBatteryGuard.Core.dll']
    if ('Protection0To1-v1.attempt'.encode('utf-16-le') not in core or
            b'WsabiWmiProtectionTransitionAttempt\0' not in core):
        raise ValueError('The new fixed attempt and its distinct reservation implementation are required.')
    for name in PROGRAM_NAMES[:3]:
        pe = pefile.PE(data=files[name])
        if pe.FILE_HEADER.Machine != 0x8664 or not pe.OPTIONAL_HEADER.DATA_DIRECTORY[14].Size:
            raise ValueError('All program assemblies must be managed Windows x64 builds.')
        if pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].Size:
            raise ValueError('Unexpected signed bytes: update the disclosure before packaging.')
        if b'.NETFramework,Version=v4.8' not in files[name]:
            raise ValueError('The .NET Framework 4.8 assembly target is required.')
    pe = pefile.PE(data=exe)
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
        raise ValueError('The executable must remain asInvoker with uiAccess=false.')
    config = ET.fromstring(files[PROGRAM_NAMES[3]])
    runtime = config.find('./startup/supportedRuntime')
    if runtime is None or runtime.get('sku') != '.NETFramework,Version=v4.8':
        raise ValueError('The .NET Framework 4.8 runtime configuration is required.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--test-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    suite = json.loads(args.test_report.read_text(encoding='utf-8'))
    if not (suite['passed'] > 804 and suite['failed'] == 0 and suite.get('skipped', 0) == 0
            and suite['registered'] == suite['passed']):
        raise ValueError('The complete approved transition regression suite must pass.')
    project = root / 'src/ATIVBatteryGuard.ProtectionTransitionTrial/ATIVBatteryGuard.ProtectionTransitionTrial.csproj'
    build = project.parent / 'bin/Release/net48'
    files = {name: (build / name).read_bytes() for name in PROGRAM_NAMES}
    validate_programs(files)
    sources = source_closure(root, project)
    if any(name.startswith('tests/') or '/tests/' in name for name, _ in sources):
        raise ValueError('Test stand-ins cannot be part of a notebook program build.')
    fingerprint = sha(b''.join(name.encode() + b'\0' + data + b'\0' for name, data in sources))
    info = {
        'schemaVersion': 1,
        'application': 'ATIV Battery Guard Fixed Protection 0 to 1 Trial',
        'purpose': PURPOSE,
        'target': 'Windows10x64/.NETFramework4.8',
        'productSourceFingerprintSha256': fingerprint,
        'sourceFileCount': len(sources),
        'sourceFiles': [{'file': name, 'sha256': sha(data)} for name, data in sources],
        'portableTestsPassed': suite['passed'],
        'portableTestsFailed': 0,
        'portableTestsSkipped': 0,
        'actualWindowsRuntimeSdkOrNotebookTested': False,
        'digitallySigned': False,
        'manualInteractiveStartRequired': True,
        'currentElevatedTokenRequiredBeforeStartReservationAndWmi': True,
        'manualSameAccountElevationIsUserProcedure': True,
        'accountNamesGroupsOrSidsRead': False,
        'maximumAdditionalPreparationsAfterStart': 1,
        'maximumCallSabiFunctionSdkEntries': 7,
        'maximumFixedReadEntries': 6,
        'maximumSemanticSet1Entries': 1,
        'maximumAcceptedStoredByteCandidates': 6,
        'settingRequiresAcceptedPreModeZeroAndPreThresholds': True,
        'settingInputFixedOneOnly': True,
        'settingMayOverwritePreviousThresholdsWith80And75': True,
        'offReverseTransitionOrRestoreIncluded': False,
        'rebootOrSleepRestoresPreviousStateGuaranteed': False,
        'handshakes': 0,
        'oemInitializations': 0,
        'retries': 0,
        'randomResamples': 0,
        'directThresholdWrites': 0,
        'fallbackB': 0,
        'ownerAcquireSecondsMaximum': 2,
        'wholeProcedureDisplayDeadlineSeconds': 10,
        'displayTimeoutTerminatesFirmwareOrProcess': False,
        'actualCloseRequiresInvocationOutputAndInputJoin': True,
        'settingReceiptIsExecutionOrStoredStateProof': False,
        'storedCandidateMatchConfirmsElectricalChargingLimit': False,
        'newPurposeDurableReservation': True,
        'previousExperimentReservationAccessed': False,
        'consumedPreviousBudgetRestored': False,
        'normalPlatformApplicabilityAssumptionsRequired': True,
        'automaticallyElevates': False,
        'runtimeNetworking': False,
        'driverServiceSecurityOrFlashChanges': False,
        'oemOriginalModulesIncludedOrLoaded': False,
        'otherExperimentExecutablesIncluded': False,
        'mainApplicationChargeControl': 'Unsupported',
        'genericSdkReadTrialEntry': 'ReadSpecificationUnavailable',
        'programFiles': [{'file': name, 'bytes': len(files[name]), 'sha256': sha(files[name])}
                         for name in PROGRAM_NAMES],
    }
    files['BUILD-INFO.json'] = (json.dumps(info, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    instructions = '''ATIV Battery Guard — 승인된 보호 설정0→1 단발 시험

이 ZIP 하나를 새 로컬 폴더에 모두 풀고 ATIVBatteryGuard.ProtectionTransitionTrial.exe만 같은 Windows 계정에서 수동 관리자 실행하세요.
실행 파일을 오른쪽 클릭해 ‘관리자 권한으로 실행’을 선택합니다. 자동 UAC/runas는 없습니다.
다른 계정 암호가 필요하거나 보안 기능이 차단하면 중단하고 우회하지 마세요.
다른 ZIP·기존 프로그램·삼성 DLL을 같은 폴더에 합치지 마세요.
대상은 Windows 10 x64 / .NET Framework 4.8 / 기존940X3G/930X3G·P05ACJ.128.140819.dg profile입니다.
미서명 개발 빌드이며 실제 Windows SDK/이 새 도구의 노트북 실행 검증은 아직 없습니다.

중요: 이 시험은 보호 모드와 기존 임계값을 바꿀 수 있습니다.
선택 setter의 정상0→1 경로는 모드1·상한80·하한75를 기록합니다.
이번 도구에는 끄기·역방향1→0·이전 임계값 복원·자동 rollback 기능이 없습니다.
재부팅이나 절전으로 원복된다고 보장하지 않습니다. 일시적으로 켠 뒤 자동 원복하는 시험이 아닙니다.
이 영향을 받아들인 경우에만 화면의 Protection0To1-v1 목적과 Elevated 토큰을 확인하고 START를 직접 입력하세요.
토큰이 NotElevated/Unknown이면 START·예약·WMI 전에 종료합니다. Elevated만으로 접근·설정 성공을 보장하지 않습니다.

START 뒤 새 목적의 준비1회를 영속 예약합니다. 준비 실패·권한 거부·중단·시간 초과도 이1회를 소모합니다.
그 뒤에는 재실행·예약 삭제·버전/계정/폴더 변경으로 시험을 반복하지 마세요.
과거 A·Access1·Query65 예약과 도구는 조회·변경·재사용하지 않습니다.

고정 순서는 사전 모드·상한·하한 읽기 → 의미상 설정1 최대1회 → 사후 모드·상한·하한 읽기입니다.
총 CallSabiFunction SDK 진입 최대7회(읽기최대6+설정최대1), 수용된 읽기 후보 최대6개입니다.
새 사전 모드 후보가0이 아니거나 사전 읽기가 실패/불명/입력echo와 구별 불가면 설정0회로 중단합니다.
설정 정상 응답은 ReceiptOnly이며 실제 종료와 독립 사후 읽기 전에는 상태 변경 성공이 아닙니다.
사후 모드1·상한80·하한75를 각각 비교하고 첫 불일치/오류에서 중단합니다.
초기화·handshake·재시도·다른 명령/B·직접 임계값 쓰기·추가 조회·자동 repair는 없습니다.
여러 읽기는 원자적 snapshot이나 compare-and-set이 아니며, 정상 플랫폼·동일 비재진입 stream의 기존 적용 전제를 사용합니다.

owner 획득 최대2초·전체 절차 표시10초는 펌웨어의 강제 중단 시간이 아닙니다.
호출·출력/관찰자·입력의 관련 정리를 별도로 기다리며, timeout/중단이 실제 종료를 보장하지 않습니다.
setter 입장/진입 뒤 실패나 중단이면 ‘변경 안 됨’이 아니라 변경 여부Unknown일 수 있습니다.
Pending이면 창/프로세스를 강제로 종료하거나 재실행하지 말고 그대로 두세요. Ctrl+C는 중단 의사만 전달합니다.
SDK Cancel·합성 final·watchdog·프로세스 강제 종료·자동 재시작은 없습니다.
관련 정리Complete 또는 호출 전 종료 안내 뒤에만 Enter로 닫으세요.

같은 폴더의 protection-0to1-result-*.txt에 역할 입장수·SDK 진입수·수용 후보수·receipt·사전/사후 후보·정리 상태를 구분해 기록합니다.
새 TXT 결과만 전달하면 됩니다. 옛 진단·삼성 DLL·EXE 재제출은 필요 없습니다.
raw frame·비교 내용·전체 경로·계정명·SID·고유 식별자·예외 원문을 기록하거나 네트워크로 전송하지 않습니다.
TXT 저장 실패도 재시도나 자원 조기 해제의 이유가 되지 않습니다.

1/80/75의 일치는 저장 후보 비교이며 충전기 적용·전기적 충전 제한 성공이 아닙니다.
역할 입장·SDK InvokeMethod 진입도 EC 처리 성공 횟수가 아닙니다.
일반 앱의 실제 충전 제어는 Unsupported로 유지됩니다.
삼성 원본 DLL·firmware·과거 실험 EXE·PDB는 없으며 driver/service/보안 설정 변경·BIOS flash를 수행하지 않습니다.
'''
    files['먼저 읽어주세요.txt'] = instructions.replace('\n', '\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(data) + '  ' + name + '\n'
                                     for name, data in sorted(files.items())).encode('utf-8')
    if len(files) != 7:
        raise ValueError('Only the four program files and three review files may be packaged.')
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / 'ATIVBatteryGuard-PROTECTION-0TO1.zip'
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(files):
            raise ValueError('ZIP CRC or allowlist validation failed.')
        for name, data in files.items():
            if archive.read(name) != data:
                raise ValueError('ZIP build-byte validation failed.')
    print(json.dumps({'file': target.name, 'bytes': target.stat().st_size,
                      'sha256': sha(target.read_bytes()), 'entries': len(files),
                      'sourceFingerprintSha256': fingerprint, 'sourceFileCount': len(sources)}))


if __name__ == '__main__':
    main()
