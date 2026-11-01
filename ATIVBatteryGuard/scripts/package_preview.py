"""Package only our build and reconstructed source. Never include user/vendor data."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from release_validation import validate_release


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--test-report', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--windows-release-report', type=Path)
    parser.add_argument('--require-windows-release', action='store_true')
    args = parser.parse_args()
    if not args.source_only and args.require_windows_release and args.windows_release_report is None:
        parser.error('Executable distribution is blocked: signed-build Windows Defender evidence is required. Use --source-only for review.')
    root = Path(__file__).resolve().parents[1]
    output = args.output or root / 'reports'
    output.mkdir(parents=True, exist_ok=True)
    tests = json.loads(args.test_report.read_text(encoding='utf-8'))
    if tests['passed'] <= 0 or tests['failed'] != 0 or tests['passed'] + tests['failed'] + tests.get('skipped', 0) != tests['registered']:
        raise ValueError('A successful nonempty test report is required.')
    build = root / 'src/ATIVBatteryGuard.App/bin/Release/net48'
    names = ['ATIVBatteryGuard.exe', 'ATIVBatteryGuard.Core.dll', 'ATIVBatteryGuard.exe.config']

    # An explicit source allowlist prevents inclusion of OEM binaries, local logs,
    # build outputs, Git internals, or user diagnostics in a source backup.
    sources = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root)
        if any(part in {'bin', 'obj', 'reports', 'dist', '.git', '.vs', '__pycache__'} for part in rel.parts):
            continue
        if path.suffix.lower() not in {'.cs', '.csproj', '.sln', '.xaml', '.md', '.config', '.manifest', '.ps1', '.py'} and path.name != '.gitignore':
            continue
        sources.append((rel.as_posix(), path.read_bytes()))
    if not any(name.endswith('MainWindow.xaml') for name, _ in sources):
        raise ValueError('Reconstructed UI source is missing.')
    fingerprint = sha(b''.join(name.encode('utf-8') + b'\0' + data + b'\0' for name, data in sources))
    source_zip = output / 'ATIVBatteryGuard-SOURCE.zip'
    with zipfile.ZipFile(source_zip, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sources:
            archive.writestr('ATIVBatteryGuard/' + name, data)
    if args.source_only:
        print(json.dumps({'file': str(source_zip), 'bytes': source_zip.stat().st_size, 'sha256': sha(source_zip.read_bytes()), 'sourceFingerprintSha256': fingerprint, 'executableDistribution': False}))
        return
    files = {name: (build / name).read_bytes() for name in names}
    evidence = None
    if args.windows_release_report is not None:
        evidence = json.loads(args.windows_release_report.read_text(encoding='utf-8-sig'))
        validate_release(evidence, files, fingerprint)
    info = {
        'schemaVersion': 1, 'application': 'ATIV Battery Guard',
        'distribution': 'PASSIVE SAMSUNG WMI INSTANCE VERSION AND ACTIVE CHECK',
        'target': 'Windows10x64/.NETFramework4.8',
        'reconstructedSources': True,
        'sourceFingerprintSha256': fingerprint,
        'sourceZipSha256': sha(source_zip.read_bytes()),
        'actualWpfXamlCompiled': True,
        'portableTestsPassed': tests['passed'], 'portableTestsFailed': tests['failed'],
        'portableTestsSkipped': tests.get('skipped', 0),
        'currentWindowsGuiTested': False, 'currentWindowsSupportInquiryTested': False,
        'previousWmiSchemaWindowsTested': True,
        'oemFileCollectionEnabled': False,
        'legacyCollectorConnectedToStartup': False,
        'oemExtractionCodeIncluded': False,
        'requiresExtractedVendorDll': False,
        'supportInquiryClipboardOnly': True,
        'windowsBatteryQueryReadOnly': True,
        'windowsBatteryQueryIoctls': ['QUERY_TAG', 'QUERY_INFORMATION_BatteryInformation'],
        'batteryProbeWorkerTimeoutMs': 10000,
        'currentWindowsBatteryQueryTested': False,
        'previousWindowsBatteryQueryTested': True,
        'previousWindowsBatteryQueryObservation': 'Complete; one system battery; Capabilities=0x80000000',
        'batteryRequestAssessmentIncluded': True,
        'currentWindowsAssessmentUiTested': False,
        'previousWindowsAssessmentTxtTested': True,
        'samsungFileMetadataInspectionIncluded': True,
        'samsungFileInspectionTargets': ['Sabi3.dll', 'wsabi.dll', 'BatteryToast.exe', 'PowerAudit.exe'],
        'copiesVendorBinaries': False, 'loadsVendorModules': False,
        'offlineAuthenticodeOnly': True, 'catalogSignatureChecked': False,
        'currentWindowsFileInspectionTested': False,
        'fileInspectionWorkerTimeoutMs': 10000,
        'maxInspectionResultBytes': 2097152,
        'fileImportFunctionsIncluded': True,
        'sabi3MetadataAssessmentIncluded': True,
        'sabi3X64BinaryStaticallyReviewed': True,
        'sabi3CallerPayloadBytes': 11,
        'samsungFileProtocolVersion': 5,
        'passiveSabiDriverNameCheck': True,
        'currentSabiDriverNameWindowsTested': False,
        'previousSabiDriverNameWindowsObserved': True,
        'previousSabiDriverNameObservation': 'NotFound; absence is not proof of uninstalled driver or unsupported firmware',
        'samsungKernelDriverInventoryReadOnly': True,
        'samsungKernelDriverQueryNamespace': 'ROOT\\CIMV2',
        'samsungKernelDriverQueryClass': 'Win32_SystemDriver',
        'samsungKernelDriverQueryFields': ['Name', 'DisplayName', 'State', 'StartMode', 'ServiceType'],
        'samsungKernelDriverServiceTypeFilter': 'Kernel Driver',
        'samsungKernelDriverCandidateCategories': ['SabiName', 'SamsungName'],
        'samsungKernelDriverExportsOriginalNames': False,
        'samsungKernelDriverMaximumRows': 1024,
        'samsungKernelDriverMaximumEntries': 32,
        'samsungKernelDriverWmiTimeoutMs': 2000,
        'samsungKernelDriverCooperativeBudgetMs': 3000,
        'currentWindowsKernelDriverInventoryTested': False,
        'driverServiceModificationAllowed': False,
        'driverStateEnablesChargeControl': False,
        'previousWindowsFileMetadataObserved': True,
        'wmiClassMetadataOnly': False, 'oemWmiClassMetadataOnly': False,
        'samsungWmiInstancePropertiesReadOnly': True,
        'samsungWmiInstanceNamespace': r'ROOT\WMI',
        'samsungWmiInstanceQueries': ['SELECT Active,version FROM WmiAcpiVersion', 'SELECT Active FROM WmiAcpiMethod'],
        'samsungWmiInstanceMaximumEntriesPerClass': 8,
        'samsungWmiInstanceQueryTimeoutMs': 2000,
        'samsungWmiInstanceCooperativeBudgetMs': 4000,
        'samsungWmiInstanceExportsKeysOrPaths': False,
        'currentWindowsWmiInstanceQueryTested': False,
        'previousDriverBuildLaunchedOnLaptop': True,
        'previousDriverBuildSamsungTxtCreated': True,
        'previousDriverInventoryContentsReviewed': False,
        'oemMethodInvocationAllowed': False,
        'oemModuleExecutionAllowed': False, 'actualChargeControlSupported': False,
        'containsOriginalVendorBinaries': False, 'containsUserUploads': False,
        'automaticUpload': False, 'digitallySigned': evidence is not None,
        'windowsReleaseEvidence': evidence,
    }
    files['BUILD-INFO.json'] = json.dumps(info, ensure_ascii=False, indent=2).encode('utf-8')
    instructions = '''ATIV Battery Guard — 삼성 WMI 인스턴스·버전·활성 속성 확인판

1. ZIP 파일을 새 폴더에 모두 압축 해제하세요.
2. ATIVBatteryGuard.exe를 실행하세요. 관리자 권한은 필요하지 않습니다.
Windows 보안이 차단하면 실행을 보류하세요. 예외 등록이나 보안 기능 해제를 하지 않습니다.
3. 새 WMI 항목을 로컬에서 확인하려면 창 아래쪽 ‘삼성 파일 정보 확인’에서 ‘삼성 파일 정보 만들기’를 선택하세요.
4. 화면과 ‘정보 파일 위치 열기’의 samsung-files TXT에서 ‘삼성 WMI 인스턴스’ 항목을 확인할 수 있습니다.
이는 새 기능을 선택적으로 확인하는 절차입니다. 같은 진단·기존 TXT·삼성 DLL·EXE를 다시 제출할 필요는 없습니다.

기존 파일 식별은 Program Files (x86)의 Samsung\\Setting 또는 Samsung\\Settings에 설치된 네 파일의 정보를 읽습니다.
Sabi3.dll, wsabi.dll, BatteryToast.exe, PowerAudit.exe만 대상이며 제한된 하위 폴더도 확인합니다.
버전·회사/설명·PE 구조·SHA-256·정적 DLL 참조와 함수 이름·내보낸 함수를 표시합니다.
Sabi3 x64 후보를 해시로 구분하고 공개 함수 이름 일치 여부를 표시합니다.
이미 제공받은 x64 DLL의 정적 분석 기록을 사용하며 동일 DLL을 다시 요구하지 않습니다.
현재 Windows의 SABI 연결 이름은 QueryDosDevice로 조회합니다. 장치 핸들을 열거나 IOCTL을 실행하지 않습니다.

새 드라이버 항목은 로컬 Windows의 커널 드라이버 등록에서 이름 또는 표시 이름에 SABI/Samsung이 포함된 후보를 읽습니다.
결과는 고정된 이름 일치 범주, 등록 관측, 실행 상태, 시작 방식으로 표시합니다. 원래 서비스 이름은 보고하지 않습니다.
실행 상태는 실행 중·중지·전환 대기·알 수 없음 등을 구분하고 시작 방식은 부팅·시스템·자동·수동·사용 안 함 등을 구분합니다.
이름 조건만으로 삼성 제조사, 해당 모델의 SABI 연결 제공 여부, 배터리 기능을 확인한 것은 아닙니다.
정상 조회에서 후보 미관측과 권한 거부·조회 오류·시간 초과·일부 관측은 별도로 표시합니다.
미관측은 드라이버 미설치나 배터리 보호 기능 부재 판정이 아닙니다. 불완전한 조회에서 누락을 부재로 해석하지 않습니다.
기존 ‘SABI 장치 연결 이름’ 결과와 함께 비교합니다. 드라이버가 관측돼도 SABI 이름이 없을 수 있으며 두 조회의 범위는 다릅니다.
연결 이름이 있어도 장치 접근·초기화·펌웨어 지원이 확인된 것은 아닙니다. 드라이버가 실행 중이어도 충전 제어를 활성화하지 않습니다.
커널 드라이버 등록 조회는 최대 1,024행·후보 32개로 제한하며 WMI 제한과 별도 조회 프로세스의 10초 제한을 적용합니다.

새 WMI 항목은 로컬 ROOT\\WMI에서 WmiAcpiVersion의 Active·version과 WmiAcpiMethod의 Active만 읽습니다.
클래스 정의만 있는지와 실제 인스턴스가 있는지를 구분하며 클래스별 결과를 독립적으로 표시합니다.
Active는 제공자의 활성 속성이지 배터리 보호 ON/OFF가 아닙니다. 버전 값의 모델별 의미도 미검증입니다.
인스턴스가 여러 개면 하나를 자동 선택하거나 서로 다른 클래스의 행을 연결하지 않습니다.
InstanceName·개체 경로·고유 식별자는 조회하거나 기록하지 않습니다. DataBuffer 값이나 CallSabiFunction은 실행하지 않습니다.
클래스별 최대 8개, 조회별 2초와 두 클래스 합계의 협력적 4초 제한 및 기존 전체 작업자 10초 제한을 적용합니다.
클래스 부재·정상 0개·일부 조회·형식 불일치·권한 거부·시간 초과를 미지원 기능으로 단정하지 않습니다.

드라이버·파일·동적 로드 관련 함수 이름의 참조를 별도로 표시합니다. 실제 실행됐다는 뜻은 아닙니다.
서명은 로컬 캐시로만 확인합니다. 온라인 폐기 확인·카탈로그 서명 검증은 하지 않습니다.
확인할 수 없는 서명은 별도로 표시하며 서명 불일치와 구분합니다.
관리 코드의 실제 실행 비트 수와 간접·지연 로드 등은 정적 PE 표시만으로 확정할 수 없습니다.

삼성 원본 DLL·EXE와 사용자 업로드 파일은 이 ZIP에 포함하지 않습니다. 추가 추출이나 분석 ZIP은 필요하지 않습니다.
삼성 파일을 복사·로드·실행하거나 DLL의 초기화 함수를 호출하지 않습니다.
정보 확인은 이 버튼을 선택했을 때만 실행하며 앱 시작·주기적 배터리 조회에서는 실행하지 않습니다.
10초 제한 초과 시 자체 조회 프로세스에 종료를 요청합니다. 결과를 장치 미지원으로 바꾸지 않습니다.
전체 설치 경로·사용자 이름·시리얼번호·고유 식별자·드라이버 원래 이름·예외 원문은 보고하지 않습니다.
파일명·함수 이름·서명 성공은 배터리 제어 지원의 증거가 아닙니다.
배터리 잔량은 0%를 포함한 Windows의 유효한 현재 측정값을 그대로 표시합니다.
실제 80%/100% 충전 제한은 아직 지원하지 않습니다.
삼성 DLL 초기화·OEM 명령·제어 메서드·펌웨어 쓰기를 실행하지 않습니다. 기존 원본 파일 수집기와 위치 탐색기는 컴파일에서 제외했습니다.
공식 지원 여부와 Samsung Settings 사용권 조건은 아직 확인 중입니다.
자동 업로드, 드라이버 설치, 서비스 등록·시작·중지·시작 방식 변경, 충전 설정 변경은 하지 않습니다.
실행 대상은 Windows 10 x64 및 .NET Framework 4.8입니다.
이전 조회판은 사용자 노트북에서 정상 조회가 확인됐습니다. 결과 0x80000000에는 표준 충전·방전 요청 지원 비트가 없습니다.
이 사실을 삼성 OEM 기능 전체의 불가능으로 해석하지 않습니다.
이전 드라이버 확인판은 실제 노트북에서 실행과 TXT 생성이 확인됐습니다. TXT의 드라이버 상태 내용은 전달받지 않았습니다.
이번 WMI 인스턴스 조회와 새 빌드의 Windows 실기 동작은 아직 미검증입니다.
'''
    files['먼저 읽어주세요.txt'] = instructions.replace('\n', '\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(data) + '  ' + name + '\n' for name, data in sorted(files.items())).encode('utf-8')
    binary_zip = output / 'ATIVBatteryGuard-WMI-INSTANCE-CHECK.zip'
    with zipfile.ZipFile(binary_zip, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    for path in (binary_zip, source_zip):
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError('ZIP CRC validation failed.')
        print(json.dumps({'file': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes())}))


if __name__ == '__main__':
    main()
