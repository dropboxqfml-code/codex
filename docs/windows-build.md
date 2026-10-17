# Windows 실행 파일 다운로드·빌드

## 일반 사용자: Python 설치 없이 다운로드

1. [저장소 Actions](https://github.com/dropboxqfml-code/codex/actions/workflows/windows-build.yml)를 엽니다.
   Artifact 다운로드에는 GitHub 로그인이 필요하며 비공개 저장소라면 저장소 접근 권한도 필요합니다.
2. **Windows executable** 워크플로에서 `main` 또는 새 기능의 `feature/cross-folder-compare` 브랜치에서 원하는 커밋을 찾습니다.
   녹색 체크로 완료된 실행을 선택하세요. 실행 중이거나 실패한 실행에서는 배포물을 받지 마세요.
3. 해당 실행 페이지 아래 **Artifacts**에서
   **ImageDuplicateFinder-Windows-x64-실행번호**를 클릭해 ZIP을 받습니다.
   `Windows-build-reports-실행번호`는 검사 기록이며 실행 프로그램이 아닙니다.
4. ZIP을 우클릭해 **모두 압축 풀기**로 완전히 풉니다. ZIP 내부에서 exe를 직접 실행하지 마세요.
5. `Image Duplicate Finder` 폴더 안의 **Image Duplicate Finder.exe**를 실행합니다.
   **Python·pip·uv를 설치할 필요가 없습니다.** `_internal`과 DLL 등 전체 폴더가 필요하므로
   exe 하나만 다른 곳으로 옮기지 마세요. 바로가기를 만드는 것은 가능합니다.
6. 폴더 선택 → 검색 시작 → 그룹 검토 → 이미지별 보관/보류/삭제 대상 선택 순서로 사용합니다.
   삭제할 그룹에서 보관할 이미지를 최소 한 장 지정한 뒤 휴지통 이동 확인에 **예**를 눌러야
   이동합니다. **아니요**를 누르면 이동하지 않습니다. 복원은 Windows 휴지통에서 합니다.

Artifact는 **30일** 보관합니다. 만료되면 저장소 관리자가 Actions에서 **Run workflow**를 누르고
`main`을 선택해 다시 빌드할 수 있습니다. 이 버튼은 쓰기 권한과 활성화된 Actions가 필요합니다.
워크플로 실행이 정책·승인을 기다리는 경우 관리자가 실행을 허용해야 합니다. 빌드 실패 시
실행 페이지의 빨간 단계를 열거나 reports Artifact의 `pytest.xml`, `frozen-smoke.json`, 경고 파일을
확인하세요. 새 워크플로를 푸시했다는 사실만으로 빌드 성공이나 Artifact 생성을 의미하지 않습니다.

ZIP에는 `BUILD-INFO.json`(커밋, Python·라이브러리 버전, 자동 검증 결과)과 `SHA256SUMS.txt`도
포함됩니다. 실행 페이지의 커밋과 BUILD-INFO의 commit을 대조하세요. 필요하면 PowerShell에서:

```powershell
Get-FileHash '.\Image Duplicate Finder\Image Duplicate Finder.exe' -Algorithm SHA256
```

출력값은 `SHA256SUMS.txt`의 같은 경로 항목과 같아야 합니다. 함께 배포한 체크섬은 손상 확인에
도움이 되지만 코드 서명이나 신뢰할 수 있는 배포 경로 확인을 대신하지 않습니다.

## 코드 서명·SmartScreen·Defender

이 빌드는 **코드 서명되지 않았으며**, 빌드 과정에서 Windows Defender 오탐이 없다고 인증하지
않습니다. 다운로드 수가 적은 새 실행 파일이나 PyInstaller 패키지는 SmartScreen의
‘Windows의 PC 보호’ 또는 백신 경고를 받을 수 있습니다. `onedir` 모드와 UPX 미사용은 불필요한
압축을 줄이지만 오탐 방지를 보장하지 않습니다.

**Defender 끄기, 폴더 전체 예외 등록, 조직 정책 우회를 권장하지 않습니다.** 탐지되면 실행을
중단하고 Windows 보안의 보호 기록에서 탐지 이름을 확인해 배포자에게 커밋·실행번호와 함께
전달하세요. 배포자는 재현·검사 후 Microsoft에 오탐 분석을 제출할 수 있습니다.
SmartScreen 경고만 있는 경우에도 공식 저장소·커밋·체크섬을 확인하고 회사 PC는 관리자 정책을
따르세요. 신뢰를 확인할 수 없는 파일은 실행하지 마세요.

일반 배포 전에 배포자 명의의 Authenticode 코드 서명 인증서 또는 신뢰 서명 서비스로 exe를
서명하고 타임스탬프를 남기는 것이 좋습니다. 인증서와 비밀번호는 Git에 넣으면 안 됩니다.
서명은 별도 유료 인증서·계정이 필요하므로 현재 워크플로에 임의 인증서나 자기 서명을 추가하지
않았습니다. 실제 서명 단계를 추가하면 **서명 후** frozen smoke와 체크섬 생성을 실행하세요.
서명도 평판 기반 경고나 악성코드 검출이 절대로 없음을 보장하지 않습니다.

## 개발자: 재현 가능한 빌드 절차

Windows 10/11 **x64**와 Python **3.12 x64**가 대상입니다. 빌드는 GitHub의 `windows-latest`
러너에서 수행합니다. 러너는 서버 OS이므로 Windows 10/11 사용자 PC의 수동 인수 테스트는
별도로 필요합니다. PyInstaller는 교차 컴파일 도구가 아닙니다.

PowerShell에서 저장소 루트로 이동한 후:

```powershell
uv python install 3.12.14
$idfPythonPath = uv python find --managed-python 3.12.14
uv sync --locked --python "$idfPythonPath"
uv run --locked ruff check .
uv run --locked ruff format --check .
$env:QT_QPA_PLATFORM = 'offscreen'
uv run --locked pytest -q --junitxml=reports/pytest.xml
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; stop before building.' }
Remove-Item Env:QT_QPA_PLATFORM
uv run --locked python scripts/build_windows.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
uv run --locked python scripts/verify_windows_build.py
if ($LASTEXITCODE -ne 0) { throw 'Frozen verification failed; do not distribute.' }
```

Actions는 각 단계 실패 시 다음 빌드·배포 단계를 실행하지 않습니다. 위 수동 명령에서는
오류가 발생하면 계속 진행하지 마세요. 결과물은 `dist` 전체입니다.
Windows CI는 managed CPython 3.12.14를 사용하고 CVE-2025-6965 때문에 SQLite 3.50.2 미만을
거부합니다. sqlite3.dll만 임의 공급자의 DLL로 덮어쓰지 않고 선택한 Python 런타임의 DLL을
PyInstaller로 함께 수집합니다. 실제 버전은 BUILD-INFO의 frozen smoke 결과에 기록합니다.

`packaging/windows.spec`가 QtWidgets 기반 windowed/onedir 빌드를 정의합니다. Qt의 PyInstaller
훅이 Qt DLL과 필요한 qwindows/qoffscreen 플랫폼 플러그인만 수집합니다. Pillow 이미지 코덱, ImageHash의
NumPy·SciPy·PyWavelets, SQLite, Send2Trash와 pywin32 COM 모듈을 명시적으로 포함합니다.
일반 실행은 앱의 `main()`을 호출하며 관리자 권한을 요구하지 않습니다. v0.1.1부터
Python 네트워크·외부 프로그램 호출 방어, 로컬 경로 검증 및 최소 SQLite 저장을 적용합니다.
PySide6-Essentials를 사용하고 Qt Network/WebEngine·외부 이미지 표시기·EPS 디코더를 제외합니다.
`bundle-inventory.json`에는 실제 수집한 모듈·네이티브 파일 목록이 기록되며 불필요한 Qt 통신
바이너리가 들어오면 빌드를 중단합니다. [보안 보고서](security-review.md)에 결과·제한을 기록합니다.

빌드 전 테스트는 Qt offscreen으로 실행합니다. 빌드 후에는 **실제 번들 exe**가 native qwindows
플러그인으로 창을 만들고, 스스로 생성한 임시 이미지로 비동기 검색·교차 포맷·유사도·SQLite·
‘아니요’와 ‘예’ 확인을 검사합니다. 이 진단 모드는 임의 사용자 폴더를 입력받지 않습니다.
‘예’ 테스트에서는 생성한 사본 한 장만 실제 휴지통으로 이동하고 Shell의 휴지통 항목에서
원본 바이트의 SHA-256까지 대조합니다. v0.2.0은 두 폴더 모드에서도 검색·좌우 미리보기·
B 단일 상태·아니요 보존·예 확인 후 B만 이동·A 보존·실제 휴지통 바이트를 검사합니다.
하나라도 실패하면 실행 파일 Artifact를 업로드하지
않고 검사 기록만 업로드합니다. CI는 Windows 휴지통 복원을 수행하지 않으며, 사용자 PC에서의
클릭·DPI·Defender·복원은 아래 수동 절차로 검증해야 합니다.

의존성 메타데이터와 wheel에 포함된 라이선스 파일도 번들에 수집합니다. 이는 모든 배포 의무를
법적으로 검토했다는 의미가 아닙니다. 공개 배포 전 PySide6/Qt 등 upstream 라이선스와 고지를
확인하세요. 현재 자동 빌드는 GitHub Release나 설치 프로그램을 만들지 않고 Artifact만 제공합니다.

[Windows 수동 인수 테스트](windows-acceptance.md) · [실제 검증 기록](validation.md)
