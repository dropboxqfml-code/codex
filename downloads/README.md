# Image Monitor Windows 개발판

[후보 내용 확인 화면 v18 다운로드](image-monitor-windows-test-v18.zip)

사용자 v17 결과에서 목록 확인 2회·새 후보 3개 기록·정상 종료를 확인했습니다.
v18은 같은 화면의 정지 상태에서 기존 후보의 작성 시각과 본문 이미지 정보를 확인합니다.
한 번에 최대 두 후보를 읽고 멈추며, 이미지 자동 저장은 다음 연결 단계입니다.

사용자 작업은 ZIP 안의 `image-monitor/WINDOWS_TEST_GUIDE.txt` 하나에 정리했습니다.
압축을 푼 뒤 `RUN_MONITOR.cmd`를 더블클릭하고 열린 화면에서 '후보 내용 확인'을 한 번
누르면 됩니다. 이번 시험에는 '감시 시작'을 누를 필요가 없습니다. 다른 작업을 계속할 수
있으며 확인이 끝나 멈춘 뒤 '프로그램 종료'를 누르면 결과 TXT 하나가 자동으로 열립니다.
버튼을 누를 수 없거나 오류가 나오면 반복 실행하지 말고 종료 후 결과 TXT를 전달합니다.

기존 '목록 감시' 범위의 기준점과 후보를 이어 사용하며 목록을 새로 읽거나 기준점을
초기화하지 않습니다. 후보 사이에는 앞 확인 종료 후 최소 60초와 기존 서비스·서버 대기를
지킵니다. 실패·중단을 포함한 상세 시도는 자동 재시도하지 않습니다. 목록 감시를 자동으로
재개하지 않으며 이전 시험의 기록·고정 저장 허가·저장 파일과 메타데이터를 유지합니다.

상태 화면과 TXT는 익명 결과의 작성 시각 비교·본문 이미지 개수와 대기·완료·실패 수를
표시합니다. 실제 사용자 PC의 새 버튼 실행 결과는 새 TXT로 확인합니다.
세부 검증 범위는 [프로젝트 검증 기록](../image-monitor/docs/validation.md)에 있습니다.
새 ZIP에는 폴더 바깥의 중복 안내를 넣지 않으며 이전 ZIP은 변경하지 않습니다.

v18 검증: Linux 1,973개 통과·197개 건너뜀, [Windows CI #39](https://github.com/dropboxqfml-code/codex/actions/runs/44045628887) 2,166개 통과·4개 건너뜀.
ZIP은 140개 파일·502,801바이트이며 안내 TXT 하나와 모든 파일의 무결성을 확인했습니다.
SHA-256: `e38fb8b7fd9bcceb0f93fd03d3e4b8cc389d3b96f6f2c837136331f6becee6c4`

## 이전 고정 시험판

- [v17 — 시작·일시정지·중지하는 로컬 목록 감시 화면](image-monitor-windows-test-v17.zip)
- [v16 — 완료 파일 재검증과 Chrome 종료·보류 정리](image-monitor-windows-test-v16.zip)
- [v15 — 확인한 후보 한 글의 실제 이미지 저장](image-monitor-windows-test-v15.zip)
- [v14 — 기존 후보의 작성 시각·본문 구조 확인](image-monitor-windows-test-v14.zip)
- [v13 — 기준점 저장과 두 주기의 새 후보 발견](image-monitor-windows-test-v13.zip)
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
