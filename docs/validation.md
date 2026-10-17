# v0.1 검증 기록

## Windows 배포 자동화 추가 검증

- Linux 로컬 테스트: **37 passed**, 실패·skip 없음. 기존 기능 회귀 테스트 34개와 빌드 도구 테스트
  3개를 실행했습니다. `ruff check`, `ruff format --check`도 통과했습니다.
- 번들 진단 드라이버의 소스 모드 테스트: 이미지 검색·픽셀/유사 판별·SQLite·GUI 확인 대화상자를
  실제로 실행했습니다. 이 테스트의 휴지통은 대체 backend이고 Qt는 offscreen입니다.
  Windows 네이티브/동결 exe 검증 통과를 의미하지 않습니다.
- Windows x64 호환 wheel이 잠금 파일의 PySide6·Pillow·NumPy·SciPy·PyWavelets·pywin32에
  포함된 것을 확인했습니다. Windows spec·버전 리소스의 Python 문법을 확인했습니다.
- 현재 클라우드 머신은 Linux입니다. Windows exe 자체는 GitHub Actions `windows-latest`의
  테스트 → 빌드 → frozen smoke가 완료돼야 검증할 수 있습니다. 워크플로의 존재만으로
  성공을 주장하지 않습니다. 실행별 `pytest.xml`, `frozen-smoke.json`, `BUILD-INFO.json`이
  실제 결과의 근거입니다.
- Windows 10/11 일반 사용자 PC, Python 미설치 환경, DPI·Defender·휴지통 복원 수동 검증은
  **미실행**입니다. [수동 인수 테스트](windows-acceptance.md)에 미검증 상태로 기록했습니다.
- 앱의 기존 `src/image_duplicate_finder` 파일은 이 배포 작업에서 변경하지 않았습니다.

## 최초 MVP 검증

검증 환경: 클라우드 Linux, Python 3.12.14, PySide6 6.12.0, Pillow 12.3.0,
ImageHash 4.3.2, Send2Trash 2.1.0. 정확한 전체 버전은 `uv.lock`을 참고하세요.

| 검사 | 결과 |
| --- | --- |
| `uv sync --locked` (반복 실행 포함) | 성공 |
| `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` | 34 passed, 실패·skip 없음 |
| `.venv/bin/ruff check .` | 통과 |
| `.venv/bin/ruff format --check .` | 17개 Python 파일 통과 |
| `.venv/bin/python -m pip check` | 의존성 충돌 없음 |
| `uv build --wheel --out-dir /tmp/idf-build-check` | Python wheel 생성 성공 |
| 앱 `main()` 진입점 offscreen 시작 후 Qt 타이머로 정상 종료 | 종료 코드 0 |
| Send2Trash 실제 Linux 휴지통 이동 | 시험용 사본만 이동, 보관 파일 유지, 이동 파일 SHA-256 일치, 시험 파일 복원 |
| `scripts/build_windows.py` Linux 실행 | 의도대로 종료 코드 1, Windows 빌드 요구 안내 |
| Windows 네이티브 GUI·휴지통·exe 빌드 | 미실행, Windows 수동 검증 필요 |

Send2Trash 실검증은 `/tmp`의 새 임시 폴더에 생성한 이미지 두 장만 사용했습니다.
처음에는 `XDG_DATA_HOME/Trash`에 이동했을 것으로 예상했지만, 실제 backend는 별도 마운트인
`/tmp`의 `.Trash-1000`을 사용했습니다. 따라서 최초 위치 확인 assertion은 실패했습니다.
`.trashinfo`에 기록된 원래 경로를 대조해 해당 시험 파일만 찾아 바이트를 검증하고 복원했습니다.
이는 검색·이동 실패가 아닌 검증 스크립트의 휴지통 위치 가정 문제였습니다.

Offscreen 플러그인의 `propagateSizeHints` 및 쓰기 불가능한 시스템 fontconfig 캐시 경고는
앱 시작을 막지 않았습니다. 가상 화면 검증은 Windows의 실제 창·DPI·휴지통 검증을 대신하지 않습니다.

Windows의 modern backend 선택, pywin32 미설치 차단, COM 예외 처리 테스트는 Linux에서
backend를 대체하여 경로 선택과 실패 동작을 검사한 것입니다. Windows API 자체가 검증됐다는 뜻은 아닙니다.
