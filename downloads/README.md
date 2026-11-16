# Image Monitor Windows 개발판

[목록 감시 화면 v17 다운로드](image-monitor-windows-test-v17.zip)

사용자 v16 결과에서 저장된 JPEG·PNG 두 파일과 메타데이터가 유지됐고, 이미 종료된 Chrome의
보류 표시까지 정리된 것을 확인했습니다. v17은 시작·일시정지·중지·종료와 확인 간격을
화면에서 조작하는 정기 목록 감시를 추가합니다. 현재는 새 글 후보 기록까지 연결했으며
이미지 자동 저장은 다음 연결 단계입니다.

사용자 작업은 ZIP 안의 `image-monitor/WINDOWS_TEST_GUIDE.txt` 하나에 정리했습니다.
압축을 푼 뒤 `RUN_MONITOR.cmd`를 더블클릭하고 열린 화면에서 '감시 시작'을 누르면 됩니다.
감시 중에는 다른 작업을 계속할 수 있습니다. 원하는 때에 화면의 '프로그램 종료'를 누르면
결과 TXT 하나가 자동으로 열립니다. 주소나 명령어 입력은 필요하지 않습니다.

실행 직후에는 멈춘 상태이며 기본 간격은 60초입니다. 중지 상태에서 60~300초로 바꿀 수
있습니다. 새 '목록 감시'는 별도 기준점을 만들고 시작 이후 새로 보이는 후보를 기록합니다.
이전 시험 범위의 기준점·후보·저장 이미지와 메타데이터는 유지합니다. 감시를 다시 실행하면
자신의 기존 기준점을 이어 사용하며, 확인 범위가 부족하면 임의로 초기화하지 않고 알립니다.
서비스 대기와 접근 차단은 지키고 중지·종료는 진행 중인 확인을 안전하게 마친 뒤 적용합니다.

로컬 상태 화면은 이 PC에서만 접근하며 시작 전에는 게시글을 읽지 않습니다.
세부 검증 범위는 [프로젝트 검증 기록](../image-monitor/docs/validation.md)에 있습니다.
사용자 PC의 새 감시 화면은 실제 실행 결과로 확인합니다.
새 ZIP에는 폴더 바깥의 중복 안내를 넣지 않으며 이전 ZIP은 변경하지 않습니다.

v17 검증: Linux 1,894개 통과·197개 건너뜀, [Windows CI #38](https://github.com/dropboxqfml-code/codex/actions/runs/43905636651) 2,087개 통과·4개 건너뜀.
ZIP은 135개 파일·478,651바이트이며 안내 TXT 하나와 모든 파일의 무결성을 확인했습니다.
SHA-256: `b2a1b66a4c1c3c02a984b2c8026b8b0800717dc6a89475737a11c4c42d0496f3`

## 이전 고정 시험판

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
