"""Package only our build and reconstructed source. Never include user/vendor data."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--test-report', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output or root / 'reports'
    output.mkdir(parents=True, exist_ok=True)
    tests = json.loads(args.test_report.read_text(encoding='utf-8'))
    if tests['passed'] <= 0 or tests['failed'] != 0 or tests['passed'] + tests['failed'] + tests.get('skipped', 0) != tests['registered']:
        raise ValueError('A successful nonempty test report is required.')
    build = root / 'src/ATIVBatteryGuard.App/bin/Release/net48'
    names = ['ATIVBatteryGuard.exe', 'ATIVBatteryGuard.Core.dll', 'ATIVBatteryGuard.exe.config']
    files = {name: (build / name).read_bytes() for name in names}

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
    info = {
        'schemaVersion': 1, 'application': 'ATIV Battery Guard',
        'distribution': 'READ ONLY SAMSUNG FILE METADATA PREVIEW',
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
        'maxInspectionResultBytes': 524288,
        'wmiClassMetadataOnly': True, 'oemMethodInvocationAllowed': False,
        'oemModuleExecutionAllowed': False, 'actualChargeControlSupported': False,
        'containsOriginalVendorBinaries': False, 'containsUserUploads': False,
        'automaticUpload': False, 'digitallySigned': False,
    }
    files['BUILD-INFO.json'] = json.dumps(info, ensure_ascii=False, indent=2).encode('utf-8')
    instructions = '''ATIV Battery Guard — 삼성 파일 정보 확인판

1. ZIP 파일을 새 폴더에 모두 압축 해제하세요.
2. ATIVBatteryGuard.exe를 실행하세요. 관리자 권한은 필요하지 않습니다.
3. 창 아래쪽 ‘삼성 파일 정보 확인’에서 ‘삼성 파일 정보 만들기’를 누르세요.
4. ‘정보 파일 위치 열기’를 누르면 samsung-files-로 시작하는 새 TXT를 확인할 수 있습니다.
5. 결과를 전달할 때는 그 TXT만 사용합니다. 삼성 DLL·EXE 또는 폴더 전체는 필요하지 않습니다.

이번 기능은 Program Files (x86)의 Samsung\\Setting 또는 Samsung\\Settings에 설치된 네 파일의 정보를 읽습니다.
Sabi3.dll, wsabi.dll, BatteryToast.exe, PowerAudit.exe만 대상이며 제한된 하위 폴더도 확인합니다.
버전·회사/설명·PE 구조·SHA-256·정적 DLL 참조·이름으로 내보낸 함수를 표시합니다.
서명은 로컬 캐시로만 확인합니다. 온라인 폐기 확인·카탈로그 서명 검증은 하지 않습니다.
확인할 수 없는 서명은 별도로 표시하며 서명 불일치와 구분합니다.
관리 코드의 실제 실행 비트 수와 간접·지연 로드 등은 정적 PE 표시만으로 확정할 수 없습니다.

삼성 EXE/DLL 추출이나 추가 분석 ZIP은 필요하지 않습니다.
삼성 파일을 복사·로드·실행하거나 DLL의 초기화 함수를 호출하지 않습니다.
정보 확인은 이 버튼을 선택했을 때만 실행하며 앱 시작·주기적 배터리 조회에서는 실행하지 않습니다.
10초 제한 초과 시 자체 조회 프로세스에 종료를 요청합니다. 결과를 장치 미지원으로 바꾸지 않습니다.
전체 설치 경로·사용자 이름·시리얼번호·예외 원문은 보고하지 않습니다.
파일명·함수 이름·서명 성공은 배터리 제어 지원의 증거가 아닙니다.
배터리 잔량은 0%를 포함한 Windows의 유효한 현재 측정값을 그대로 표시합니다.
실제 80%/100% 충전 제한은 아직 지원하지 않습니다.
삼성 파일이나 제어 메서드를 실행하지 않습니다. 기존 원본 파일 수집기와 위치 탐색기는 컴파일에서 제외했습니다.
공식 지원 여부와 Samsung Settings 사용권 조건은 아직 확인 중입니다.
자동 업로드, 드라이버 설치, 서비스 등록, 충전 설정 변경은 하지 않습니다.
실행 대상은 Windows 10 x64 및 .NET Framework 4.8입니다.
이전 조회판은 사용자 노트북에서 정상 조회가 확인됐습니다. 결과 0x80000000에는 표준 충전·방전 요청 지원 비트가 없습니다.
이 사실을 삼성 OEM 기능 전체의 불가능으로 해석하지 않습니다.
이번 파일 정보 기능은 클라우드 빌드·자동 회귀 테스트를 확인했으며, Windows 노트북에서의 실제 조회는 아직 미검증입니다.
이전의 배터리 diagnostics TXT를 다시 수집할 필요는 없습니다.
'''
    files['먼저 읽어주세요.txt'] = instructions.replace('\n', '\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(data) + '  ' + name + '\n' for name, data in sorted(files.items())).encode('utf-8')
    binary_zip = output / 'ATIVBatteryGuard-SAMSUNG-FILE-INFO.zip'
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
