# Image Monitor Windows 시험판

[검색 감시 연결 시험 v13 다운로드](image-monitor-windows-test-v13.zip)

사용자 v12 결과에서 두 페이지의 게시글 40개와 실제 다음 페이지 이동을 확인했습니다.
v13은 화면 없는 Chrome으로 목록 기준점을 저장하고, 앞 관찰 종료 후 60초 이상 기다려
다시 확인하는 두 주기 한정 시험판입니다. 별도 SQLite에 기준점과 새 후보를 보존하며
재실행의 대기 시간과 중복 실행을 보호합니다. 이미지 저장과 계속 실행하는 정기 감시는 시작하지 않습니다.

사용자 작업은 ZIP 안의 `image-monitor/WINDOWS_TEST_GUIDE.txt` 하나에 정리했습니다.
압축을 푼 뒤 `RUN_WATCH_TEST.cmd`를 더블클릭하고 약 2분 기다리면 됩니다.
명령어 입력과 시작 버튼 조작 없이 다른 작업을 계속할 수 있습니다.
uv·관리형 Python·잠금 의존성을 준비하고 결과 TXT를 자동으로 엽니다.
대기 중이거나 오류가 나면 반복 실행하지 않고 결과 TXT 하나를 전달하세요.

세부 검증 범위와 실행 결과는 [프로젝트 검증 기록](../image-monitor/docs/validation.md)에 있습니다.
이 한정 시험의 실제 사이트 기준점 저장·반복 확인은 새 사용자 결과로 확인합니다.
새 ZIP에는 폴더 바깥의 중복 안내를 넣지 않으며 이전 ZIP은 변경하지 않습니다.

v13 검증: Linux 1,229개 통과·96개 건너뜀, [Windows CI #33](https://github.com/dropboxqfml-code/codex/actions/runs/43729241383) 1,321개 통과·4개 건너뜀.
ZIP은 94개 파일·326,887바이트이며 안내 TXT 하나와 모든 파일의 무결성을 확인했습니다.
SHA-256: `efc3f9b11af63e99b06659723a414587cb5c74bb78fde1f0ee16110001ad5692`

## 이전 고정 시험판

- [v12 — 검색 목록과 실제 인접 페이지의 읽기 전용 관찰](image-monitor-windows-test-v12.zip)
- [v11 — 검색 목록의 읽기 전용 구조 확인](image-monitor-windows-test-v11.zip)
- [v10 — 사용자 환경에서 이미지 4개 전체 저장·재개 완료](image-monitor-windows-test-v10.zip)
- [v9 — 단일 실제 게시글의 Chrome 네이티브 저장·검증·최종 확정](image-monitor-windows-test-v9.zip)
- [v8 — 헤더·원본명 읽기 재확인, 안내 TXT를 프로젝트 폴더에 하나만 동봉](image-monitor-windows-test-v8.zip)
- [v7 — 실제 게시글 읽기 전용 구조 확인](image-monitor-windows-test-v7.zip)
- [v6 — Chrome 기본 네이티브 저장 시험](image-monitor-windows-test-v6.zip)
- [v5 — Edge 네이티브 저장 경로 수정](image-monitor-windows-test-v5.zip)
- [v4 — 준비 버튼·재시험 지원](image-monitor-windows-test-v4.zip)
- [v3 — 설치 후 갱신된 uv 경로 검색](image-monitor-windows-test-v3.zip)
- [v2 — uv·Python 자동 준비](image-monitor-windows-test-v2.zip)
- [최초 네이티브 저장 시험 소스](image-monitor-windows-probe.zip)
