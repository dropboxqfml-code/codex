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
        'distribution': 'WMI CLASS SCHEMA DIAGNOSTICS PREVIEW',
        'target': 'Windows10x64/.NETFramework4.8',
        'reconstructedSources': True,
        'sourceFingerprintSha256': fingerprint,
        'sourceZipSha256': sha(source_zip.read_bytes()),
        'actualWpfXamlCompiled': True,
        'portableTestsPassed': tests['passed'], 'portableTestsFailed': tests['failed'],
        'portableTestsSkipped': tests.get('skipped', 0),
        'currentWindowsGuiTested': False, 'currentWindowsWmiSchemaTested': False,
        'wmiClassMetadataOnly': True, 'oemMethodInvocationAllowed': False,
        'oemModuleExecutionAllowed': False, 'actualChargeControlSupported': False,
        'containsOriginalVendorBinaries': False, 'containsUserUploads': False,
        'automaticUpload': False, 'digitallySigned': False,
    }
    files['BUILD-INFO.json'] = json.dumps(info, ensure_ascii=False, indent=2).encode('utf-8')
    instructions = '''ATIV Battery Guard — 삼성 인터페이스 정의 진단판

1. ZIP 파일을 새 폴더에 모두 압축 해제하세요.
2. ATIVBatteryGuard.exe를 실행하세요. 관리자 권한은 필요하지 않습니다.
3. ‘읽기 전용 진단’ 영역의 ‘진단 파일 만들기’를 누르세요.
4. 완료 문구가 나오면 ‘진단 파일 위치 열기’를 누르세요.
5. 가장 최근에 생성된 diagnostics-로 시작하는 TXT 파일을 채팅에 첨부하세요.

이번에는 삼성 분석 ZIP을 추가로 만들 필요가 없습니다.
Windows가 보고한 배터리 0%는 그대로 표시합니다.
실제 80%/100% 충전 제한은 아직 지원하지 않습니다.
이 버전은 삼성 인터페이스의 정의만 읽으며 DLL이나 제어 메서드를 호출하지 않습니다.
자동 업로드, 드라이버 설치, 서비스 등록, 충전 설정 변경은 하지 않습니다.
실행 대상은 Windows 10 x64 및 .NET Framework 4.8입니다.
클라우드에서 빌드와 자동 회귀 테스트를 확인했으며, 이 새 버전의 Windows 실행 확인은 아직 필요합니다.
'''
    files['먼저 읽어주세요.txt'] = instructions.replace('\n', '\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(data) + '  ' + name + '\n' for name, data in sorted(files.items())).encode('utf-8')
    binary_zip = output / 'ATIVBatteryGuard-WMI-SCHEMA.zip'
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
