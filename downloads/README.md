# Image Monitor Windows 시험판

[중단 지점에서 이어서 저장하는 v10 다운로드](image-monitor-windows-test-v10.zip)

v10은 첫 파일 저장 후 입력 전 전경 검사에서 멈춘 v9 시험을 이어가는 소스 시험판입니다.
저장한 파일을 보존하고 이전 보고서·DB·브라우저 종료·빈 임시 폴더를 대조한 뒤 남은 작업을 재개합니다.
Chrome의 실제 우클릭·Windows 저장 창과 완료 상태·파일 검증·최종 파일·SQLite·메타데이터를 사용합니다.
정기 감시 프로그램이나 exe 설치 파일은 아닙니다.

사용자 작업은 ZIP 안의 `image-monitor/WINDOWS_TEST_GUIDE.txt` 하나에 정리했습니다.
이전 시험용 Chrome을 닫고 압축을 푼 뒤 `RETRY_POST_SAVE_TEST.cmd`를 더블클릭하고
전용 Chrome의 `저장 시작`을 누르면 됩니다. 이미지 사이에 전경을 잃으면 `계속 저장`으로 재개합니다.
uv·관리형 Python·잠금 의존성을 준비하고 결과 TXT를 자동으로 엽니다.
오류가 나면 반복 실행하지 않고 결과 TXT 하나를 전달하세요.

세부 검증 범위와 실행 결과는 [프로젝트 검증 기록](../image-monitor/docs/validation.md)에 있습니다.
실제 게시글의 사용자 환경 저장 결과는 별도로 확인합니다.
새 ZIP에는 폴더 바깥의 중복 안내를 넣지 않으며 이전 ZIP은 변경하지 않습니다.

v10 검증: Linux 727개 통과·52개 건너뜀, Windows 775개 통과·4개 건너뜀.
ZIP은 70개 파일·229,752바이트이며 안내 TXT 하나와 모든 파일의 무결성을 확인했습니다.
SHA-256: `ab51694b40ba4b89aa74a070869d16b8d153503df11a1196d88cfe7757852dfc`

## 이전 고정 시험판

- [v9 — 단일 실제 게시글의 Chrome 네이티브 저장·검증·최종 확정](image-monitor-windows-test-v9.zip)
- [v8 — 헤더·원본명 읽기 재확인, 안내 TXT를 프로젝트 폴더에 하나만 동봉](image-monitor-windows-test-v8.zip)
- [v7 — 실제 게시글 읽기 전용 구조 확인](image-monitor-windows-test-v7.zip)
- [v6 — Chrome 기본 네이티브 저장 시험](image-monitor-windows-test-v6.zip)
- [v5 — Edge 네이티브 저장 경로 수정](image-monitor-windows-test-v5.zip)
- [v4 — 준비 버튼·재시험 지원](image-monitor-windows-test-v4.zip)
- [v3 — 설치 후 갱신된 uv 경로 검색](image-monitor-windows-test-v3.zip)
- [v2 — uv·Python 자동 준비](image-monitor-windows-test-v2.zip)
- [최초 네이티브 저장 시험 소스](image-monitor-windows-probe.zip)
