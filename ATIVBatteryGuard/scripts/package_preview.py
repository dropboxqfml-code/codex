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
        'distribution': 'OFFICIAL SUPPORT REVIEW PREVIEW',
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
        'supportInquiryClipboardOnly': True,
        'wmiClassMetadataOnly': True, 'oemMethodInvocationAllowed': False,
        'oemModuleExecutionAllowed': False, 'actualChargeControlSupported': False,
        'containsOriginalVendorBinaries': False, 'containsUserUploads': False,
        'automaticUpload': False, 'digitallySigned': False,
    }
    files['BUILD-INFO.json'] = json.dumps(info, ensure_ascii=False, indent=2).encode('utf-8')
    instructions = '''ATIV Battery Guard — 공식 지원 검토판

1. ZIP 파일을 새 폴더에 모두 압축 해제하세요.
2. ATIVBatteryGuard.exe를 실행하세요. 관리자 권한은 필요하지 않습니다.
3. 장치 정보 조회가 끝나면 아래쪽 ‘공식 지원 확인’에서 문의 초안을 볼 수 있습니다.
4. 필요할 때 ‘공식 문의문 복사’를 눌러 내용을 복사할 수 있습니다.
5. 문의문은 검토 후 사용자가 직접 전달할 수 있습니다. 앱은 외부에 전송하지 않습니다.

이번 버전은 삼성 프로그램 파일 수집을 보류하고 생성 버튼을 비활성화합니다.
추가 삼성 EXE/DLL이나 분석 ZIP을 업로드할 필요가 없습니다.
배터리 잔량은 0%를 포함한 Windows의 유효한 현재 측정값을 그대로 표시합니다.
실제 80%/100% 충전 제한은 아직 지원하지 않습니다.
삼성 파일이나 제어 메서드를 실행하지 않습니다. OEM 파일 수집기는 제품 시작 구성에 연결하지 않았습니다.
공식 지원 여부와 Samsung Settings 사용권 조건은 아직 확인 중입니다.
자동 업로드, 드라이버 설치, 서비스 등록, 충전 설정 변경은 하지 않습니다.
실행 대상은 Windows 10 x64 및 .NET Framework 4.8입니다.
클라우드에서 빌드와 자동 회귀 테스트를 확인했으며, 이 새 문의 복사 기능의 Windows 실행은 아직 검증하지 않았습니다.
'''
    files['먼저 읽어주세요.txt'] = instructions.replace('\n', '\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(data) + '  ' + name + '\n' for name, data in sorted(files.items())).encode('utf-8')
    binary_zip = output / 'ATIVBatteryGuard-SUPPORT-REVIEW.zip'
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
