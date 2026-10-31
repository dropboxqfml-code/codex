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
        'distribution': 'SAMSUNG SETTINGS MISSING LOCATION FIX PREVIEW',
        'target': 'Windows10x64/.NETFramework4.8',
        'reconstructedSources': True,
        'sourceFingerprintSha256': fingerprint,
        'sourceZipSha256': sha(source_zip.read_bytes()),
        'actualWpfXamlCompiled': True,
        'portableTestsPassed': tests['passed'], 'portableTestsFailed': tests['failed'],
        'portableTestsSkipped': tests.get('skipped', 0),
        'currentWindowsGuiTested': False, 'currentWindowsSettingsCollectionTested': False,
        'previousWmiSchemaWindowsTested': True,
        'settingsCollectionRequiresConsent': True,
        'settingsCollectionUsesRegisteredDedicatedDirectory': True,
        'missingLocationFallbackRequiresMatchedRegistrationAndBothFieldsAbsent': True,
        'wmiClassMetadataOnly': True, 'oemMethodInvocationAllowed': False,
        'oemModuleExecutionAllowed': False, 'actualChargeControlSupported': False,
        'containsOriginalVendorBinaries': False, 'containsUserUploads': False,
        'automaticUpload': False, 'digitallySigned': False,
    }
    files['BUILD-INFO.json'] = json.dumps(info, ensure_ascii=False, indent=2).encode('utf-8')
    instructions = '''ATIV Battery Guard — Samsung Settings 앱 분석판

1. ZIP 파일을 새 폴더에 모두 압축 해제하세요.
2. ATIVBatteryGuard.exe를 실행하세요. 관리자 권한은 필요하지 않습니다.
3. 아래쪽 ‘Samsung Settings 앱 분석 자료’에서 ‘Settings 분석 파일 만들기’를 누르세요.
4. 포함 내용 안내를 읽고 자료를 만들려면 ‘예’를 선택하세요.
5. 완료 문구가 나오면 ‘파일 위치 열기’를 누르세요.
6. 가장 최근에 생성된 samsung-analysis-로 시작하는 ZIP 파일을 채팅에 첨부하세요.

위치나 파일을 확인하지 못해 점검 보고서만 들어 있는 ZIP이 만들어져도 그 ZIP을 전달하세요.
이번에는 기존 진단 TXT를 다시 만들 필요가 없습니다.
배터리 잔량은 0%를 포함한 Windows의 유효한 현재 측정값을 그대로 표시합니다.
실제 80%/100% 충전 제한은 아직 지원하지 않습니다.
이 버전은 설치된 Samsung Settings 앱의 EXE/DLL을 분석 데이터로만 복사합니다.
삼성 파일이나 제어 메서드를 실행하지 않습니다. 설정·로그·개인 문서·드라이버는 포함하지 않습니다.
일반 사용자 권한으로 읽을 수 있는 전용 설치 폴더만 확인하며 권한 상승은 요청하지 않습니다.
자동 업로드, 드라이버 설치, 서비스 등록, 충전 설정 변경은 하지 않습니다.
실행 대상은 Windows 10 x64 및 .NET Framework 4.8입니다.
클라우드에서 빌드와 자동 회귀 테스트를 확인했으며, 이 새 수집 기능의 Windows 실행 확인은 아직 필요합니다.
'''
    files['먼저 읽어주세요.txt'] = instructions.replace('\n', '\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(data) + '  ' + name + '\n' for name, data in sorted(files.items())).encode('utf-8')
    binary_zip = output / 'ATIVBatteryGuard-SETTINGS-ANALYSIS.zip'
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
