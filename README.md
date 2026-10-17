# Image Duplicate Finder

Windows에서 중복·유사 이미지를 검토하고, 사용자가 선택한 파일만 휴지통으로 이동하는
Python 3.12 / PySide6 데스크톱 프로그램입니다. 첫 버전(v0.1.0)입니다.

일반 Windows 사용자는 Python·uv 설치 없이 **Actions의 실행 파일 Artifact**를 받을 수 있습니다.
[다운로드 및 실행 단계](docs/windows-build.md#일반-사용자-python-설치-없이-다운로드)를 참고하세요.
Artifact는 해당 Windows 빌드와 번들 검사가 성공한 실행에서만 제공됩니다.

## 실행

아래는 소스 개발 환경의 실행 방법입니다. 실행 파일 사용자는 위 다운로드 안내를 따르세요.

Windows 10/11 64비트와 Python 3.12 64비트를 권장합니다. PowerShell에서 저장소 폴더로 이동한 뒤:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m image_duplicate_finder
```

의존성은 `pyproject.toml`에 선언되어 있습니다. PySide6, Pillow, ImageHash, Send2Trash를 사용하며
SQLite는 Python 표준 라이브러리입니다. Windows에서는 pywin32도 설치하여 Send2Trash의
현대식 휴지통 API를 필수로 사용합니다. 정확한 의존성 버전은 `uv.lock`에 고정합니다.
위 pip 명령은 호환 범위 내 버전을 설치합니다. 잠금 버전을 재현하려면 [uv](https://docs.astral.sh/uv/)로:

```powershell
uv sync --locked
uv run --locked python -m image_duplicate_finder
```

Linux 개발 환경에서도 `uv sync --locked` 후 `uv run --locked python -m image_duplicate_finder`로
실행합니다. 데스크톱 세션과 Qt 시스템 라이브러리가 필요합니다. 서버의 GUI 테스트는 아래처럼
`QT_QPA_PLATFORM=offscreen`을 사용합니다. 앱은 서버나 API 키를 요구하지 않습니다.

## 사용 순서

1. 검색 폴더를 선택하고 하위 폴더 포함 여부를 지정합니다.
2. pHash 허용 거리를 선택합니다. 기본값은 6(64비트 중 다른 비트 수), 0은 가장 엄격하며
   64는 모든 이미지를 연결하므로 일반적인 사용에는 권장하지 않습니다.
3. 검색을 시작합니다. 파일 수집 중에는 진행 표시가 움직이고, 분석·비교 중에는 처리 수가 나옵니다.
4. 왼쪽 그룹을 선택해 썸네일, 파일명, 전체 경로, 파일 크기, 해상도를 확인합니다.
5. 각 이미지에 보관 / 보류 / 삭제 대상을 지정합니다. 최초 검색은 전부 **보류**입니다.
6. 삭제할 그룹에서 최소 한 장을 **보관**으로 지정합니다.
7. ‘삭제 대상을 휴지통으로…’를 누르고 자세히 보기에서 전체 경로를 확인합니다.
   확인 대화상자의 기본 응답은 아니요입니다. 예를 선택해야 이동합니다.
8. 실패는 ‘문제 보기’에서 확인합니다. 이동 후 다시 검색하면 그룹이 재계산됩니다.

검색, 해시 계산, 이미지 해석, 썸네일 생성, 휴지통 이동은 작업 스레드에서 수행합니다.
취소는 파일 수집·파일 해시 블록·이미지 사이·유사도 비교 사이에서 확인합니다. Pillow의 단일
이미지 디코딩과 운영체제 휴지통 호출은 진행 중 강제 중단할 수 없습니다. 창을 닫으면 취소를
요청하고 스레드 종료를 기다립니다. 휴지통 이동 중 취소해도 이미 이동한 파일은 그대로입니다.

## 판별 방식과 범위

- **파일 동일**: 파일 바이트의 SHA-256이 같습니다.
- **픽셀 동일**: EXIF 회전을 적용한 크기와 RGBA 픽셀의 SHA-256이 같습니다.
  PNG/BMP/무손실 WebP처럼 확장자가 달라도 실제 픽셀이 같으면 찾습니다. JPEG 재압축은
  픽셀을 바꾸므로 일반적으로 유사 판정 대상입니다. 알파 값도 비교하며 ICC 색상 프로필 변환은
  하지 않습니다.
- **유사**: 흰 배경 위에 알파 합성한 영상의 64비트 pHash 해밍 거리가 설정값 이하입니다.
  단색 이미지 등은 오탐이 가능하므로 사용자가 반드시 시각적으로 검토해야 합니다.
- 그룹은 이 관계들의 **연결 요소**입니다. A~B, B~C가 유사해도 A~C는 설정 거리를 초과할 수
  있습니다. 그룹 전체가 완전히 같은 이미지라는 뜻은 아닙니다. 자동 선택·자동 삭제는 없습니다.
- 확장자 필터 대신 Pillow로 파일 내용을 확인합니다. 지원 코덱은 설치된 Pillow에 따릅니다.
  손상된 알려진 이미지 확장자는 오류로 표시하고 일반 비이미지 파일은 건너뜁니다.
  이름을 바꾼 손상 파일은 비이미지 파일과 구분하지 못할 수 있습니다.
- 애니메이션 GIF/WebP, 다중 페이지 TIFF 등은 프레임 누락 방지를 위해 제외하고 문제로 표시합니다.
  심볼릭 링크와 디렉터리 junction은 따라가지 않습니다. RAW/HEIC 전용 코덱, 영상은 지원하지 않습니다.
- 정확한 해시는 선형 색인으로 연결합니다. 서로 다른 pHash가 u개면 유사도 비교는 O(u²),
  기록·썸네일 메모리는 O(n)입니다. 최초 버전은 수천 장 정도의 폴더를 대상으로 합니다.
  대규모 폴더는 나누어 검색하세요. 대형 파일은 메모리를 많이 쓸 수 있으며 Pillow의 이미지 폭탄
  보호 한도를 유지합니다.

## 선택 저장과 삭제 보호

SQLite는 Qt의 사용자별 `AppLocalDataLocation` 아래 `reviews.sqlite3`에 저장됩니다.
Windows에서는 일반적으로 `%LOCALAPPDATA%\ImageDuplicateFinder\Image Duplicate Finder`입니다.
선택은 전체 경로와 파일 SHA-256에 연결되어 앱을 다시 열고 검색해도 복원됩니다. 파일 내용이
변하면 기본 보류로 돌아갑니다. 검색 폴더/임계값/검색 결과 전체를 저장하는 기능은 아직 없습니다.

삭제 직전 파일 크기, 수정 시각, 파일 식별자, SHA-256과 보관 파일의 상태를 재검증합니다.
바뀌거나 사라진 파일, 심볼릭 링크로 바뀐 경로는 이동하지 않습니다. 이 검증과 운영체제 이동은
원자적 연산이 아니므로 검토·삭제 중 다른 프로그램에서 대상 폴더를 수정하지 마세요.
Windows에서는 pywin32 기반 IFileOperation의 recycle-on-delete 경로만 사용하며,
pywin32가 없으면 이동을 차단합니다. 구형 SHFileOperation으로 대체하지 않습니다.
Send2Trash가 실패하면 오류를 표시하며 영구 삭제로 전환하지 않습니다. 네트워크 드라이브·일부
파일시스템은 휴지통을 지원하지 않을 수 있습니다. 복원은 Windows 휴지통에서 직접 수행합니다.
중요한 원본에는 별도 백업을 유지하세요. 중복 그룹에서 보관을 하나 요구하는 것은 검사 보조 장치이며
내용의 동등성이나 백업을 보장하지 않습니다.

## 개발 및 테스트

```powershell
uv sync --locked
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```

GUI가 없는 Linux에서는 `QT_QPA_PLATFORM=offscreen uv run --locked pytest -q`를 사용합니다.
테스트는 실제 이미지 생성·검색, 교차 포맷 픽셀 일치, 유사도 연결, SQLite 선택 복원, 취소,
변경 파일 보호, GUI 스레드 작업 및 확인 대화상자를 검사합니다. 일반 테스트의 휴지통 backend는
대체하여 개인 파일을 이동하지 않습니다. Linux 임시 파일 휴지통 실검증은 별도 수행하며,
Windows 네이티브 동작은 Windows에서 추가 검증해야 합니다.

Windows 실행 파일 제작은 [docs/windows-build.md](docs/windows-build.md)를 참고하세요.
요구사항별 구현·검증 범위는 [docs/requirements.md](docs/requirements.md)에 정리했습니다.
현재 환경의 실제 검사 결과는 [docs/validation.md](docs/validation.md)에 기록했습니다.
