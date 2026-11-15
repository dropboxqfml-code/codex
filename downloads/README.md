# Image Monitor Windows 시험판

[Chrome 실제 게시글 저장 시험 v9 다운로드](image-monitor-windows-test-v9.zip)

v9는 확인한 예제 게시글 한 개의 본문 이미지를 Chrome의 실제 우클릭·Windows 저장 창으로
저장하고, 완료 상태·파일 검증·최종 파일·SQLite·메타데이터까지 연결하는 소스 시험판입니다.
정기 감시 프로그램이나 exe 설치 파일은 아닙니다.

사용자 작업은 ZIP 안의 `image-monitor/WINDOWS_TEST_GUIDE.txt` 하나에 정리했습니다.
압축을 풀고 `RUN_POST_SAVE_TEST.cmd`를 더블클릭한 뒤 전용 Chrome의 `저장 시작`을 누르면 됩니다.
uv·관리형 Python·잠금 의존성을 준비하고 결과 TXT를 자동으로 엽니다.
오류가 나면 반복 실행하지 않고 결과 TXT 하나를 전달하세요.

세부 검증 범위와 실행 결과는 [프로젝트 검증 기록](../image-monitor/docs/validation.md)에 있습니다.
실제 게시글의 사용자 환경 저장 결과는 별도로 확인합니다.
새 ZIP에는 폴더 바깥의 중복 안내를 넣지 않으며 이전 ZIP은 변경하지 않습니다.

v9 검증: Linux 607개 통과·39개 건너뜀, Windows 642개 통과·4개 건너뜀.
ZIP은 66개 파일·204,132바이트이며 안내 TXT의 위치·유일성·내용과 전체 파일 무결성을 확인했습니다.
SHA-256: `adcafe522b1fdee103b62fb1eaa396581656b6416103a85b3d4d83aed8099777`

## 이전 고정 시험판

- [v8 — 헤더·원본명 읽기 재확인, 안내 TXT를 프로젝트 폴더에 하나만 동봉](image-monitor-windows-test-v8.zip)
- [v7 — 실제 게시글 읽기 전용 구조 확인](image-monitor-windows-test-v7.zip)
- [v6 — Chrome 기본 네이티브 저장 시험](image-monitor-windows-test-v6.zip)
- [v5 — Edge 네이티브 저장 경로 수정](image-monitor-windows-test-v5.zip)
- [v4 — 준비 버튼·재시험 지원](image-monitor-windows-test-v4.zip)
- [v3 — 설치 후 갱신된 uv 경로 검색](image-monitor-windows-test-v3.zip)
- [v2 — uv·Python 자동 준비](image-monitor-windows-test-v2.zip)
- [최초 네이티브 저장 시험 소스](image-monitor-windows-probe.zip)
