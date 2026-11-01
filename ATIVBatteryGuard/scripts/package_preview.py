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
        'distribution': 'READ ONLY BATTERY DIAGNOSTIC ASSESSMENT PREVIEW',
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
        'wmiClassMetadataOnly': True, 'oemMethodInvocationAllowed': False,
        'oemModuleExecutionAllowed': False, 'actualChargeControlSupported': False,
        'containsOriginalVendorBinaries': False, 'containsUserUploads': False,
        'automaticUpload': False, 'digitallySigned': False,
    }
    files['BUILD-INFO.json'] = json.dumps(info, ensure_ascii=False, indent=2).encode('utf-8')
    instructions = '''ATIV Battery Guard — 배터리 진단 결과 해석판

1. ZIP 파일을 새 폴더에 모두 압축 해제하세요.
2. ATIVBatteryGuard.exe를 실행하세요. 관리자 권한은 필요하지 않습니다.
3. ‘읽기 전용 진단’의 ‘진단 파일 만들기’를 선택하면 새 조회 결과가 로컬 TXT에 포함됩니다.
4. ‘진단 파일 위치 열기’에서 diagnostics-로 시작하는 최신 TXT를 확인할 수 있습니다.
5. 메인 화면의 ‘표준 Windows 요청 지원’과 TXT의 ‘결과 해석’에서 조회의 의미를 확인할 수 있습니다.
6. 조회 결과는 이번 실행에서만 표시하며, 다시 조회할 때는 이전 결과를 지웁니다.

삼성 EXE/DLL 추출이나 추가 분석 ZIP은 필요하지 않습니다.
새 조회는 기본 배터리 정보만 읽으며 시리얼번호·고유 ID·장치 경로·태그는 보고하지 않습니다.
시간 초과 시 자체 조회 프로세스에 종료를 요청하고 결과를 알 수 없음으로 취급합니다.
이 결과의 지원 표시는 80% 충전 상한 지원이 아닙니다. 실제 제어는 활성화하지 않습니다.
배터리 잔량은 0%를 포함한 Windows의 유효한 현재 측정값을 그대로 표시합니다.
실제 80%/100% 충전 제한은 아직 지원하지 않습니다.
삼성 파일이나 제어 메서드를 실행하지 않습니다. OEM 파일 수집기와 위치 탐색기는 컴파일에서 제외했습니다.
공식 지원 여부와 Samsung Settings 사용권 조건은 아직 확인 중입니다.
자동 업로드, 드라이버 설치, 서비스 등록, 충전 설정 변경은 하지 않습니다.
실행 대상은 Windows 10 x64 및 .NET Framework 4.8입니다.
이전 조회판은 사용자 노트북에서 정상 조회가 확인됐습니다. 결과 0x80000000에는 표준 충전·방전 요청 지원 비트가 없습니다.
이 사실을 삼성 OEM 기능 전체의 불가능으로 해석하지 않습니다.
이번 해석 기능은 클라우드 빌드·자동 회귀 테스트를 확인했으며, 새 화면의 Windows 실행은 아직 미검증입니다.
이미 전달한 진단 파일은 다시 보낼 필요가 없습니다.
'''
    files['먼저 읽어주세요.txt'] = instructions.replace('\n', '\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(data) + '  ' + name + '\n' for name, data in sorted(files.items())).encode('utf-8')
    binary_zip = output / 'ATIVBatteryGuard-DIAGNOSTIC-ASSESSMENT.zip'
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
