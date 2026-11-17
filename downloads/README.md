# Image Monitor Windows 개발판

[감시 후보 한 글의 이미지 저장 v19 다운로드](image-monitor-windows-test-v19.zip)

사용자 v18 결과에서 기존 감시 후보 두 개의 작성 시각과 본문 이미지 정보 확인·정상 종료를
확인했습니다. 두 후보 모두 최초 기준 시각 이후 작성됐고 수집 대상 이미지는 각각 한 개였으며
로딩 미완료는 없었습니다. v19는 이 `목록 감시` 범위에서 완료된 관찰 한 개와 네이티브 저장
작업자를 연결합니다. 전체 후보의 이미지 자동 저장은 아직 연결하지 않았습니다.

사용자 절차는 ZIP 안의 `image-monitor/WINDOWS_TEST_GUIDE.txt` 하나에 정리했습니다.
압축을 푼 뒤 `RUN_MONITOR_SAVE.cmd`를 더블클릭하고 전용 Chrome의 '저장 시작'을 한 번
누릅니다. 저장이 끝날 때까지 그 창을 앞에 유지하며 자동으로 열린 결과 TXT 하나를 전달합니다.
목록 감시나 후보 내용 확인을 다시 실행하거나 명령어를 입력할 필요는 없습니다.

선택은 `monitor-save-selection.json`에 한 후보로 고정합니다. 다시 실행해도 다른 후보로
넘어가지 않으며 완료 작업은 재저장하지 않습니다. 출력은 별도 `ImageMonitorMonitorSave`
루트를 사용하고 기존 시험의 선택 파일·이미지·메타데이터와 감시 기준점·후보·상세 기록을
유지합니다. 현재 게시글의 헤더와 이미지 원본 URL·크기·출현·제외 정보가 관찰과 일치해야 합니다.

실제 우클릭과 Windows 저장 창, Chrome 완료 기록, 파일 검증과 최종 확정을 재사용합니다.
서버·서비스 대기와 접근 차단, 전경 및 소유 창 보호를 유지하며 모호한 미해결 저장은 자동
복구하지 않습니다. `RUN_MONITOR_FINISH.cmd`는 이미 완료된 파일과 메타데이터를 재검증하고
종료 상태를 확인하는 지원 명령이며 이번 사용자 시험에서 추가 실행할 필요는 없습니다.

사용자 PC의 새 저장 연결은 새 결과 TXT로 확인합니다.
세부 검증 범위는 [프로젝트 검증 기록](../image-monitor/docs/validation.md)에 있습니다.
새 ZIP에는 프로젝트 폴더 안의 안내 TXT 하나만 넣으며 이전 ZIP은 변경하지 않습니다.

v19 검증: Linux 2,065개 통과·257개 건너뜀, [Windows CI #40](https://github.com/dropboxqfml-code/codex/actions/runs/44061251492) 2,318개 통과·4개 건너뜀.
ZIP은 148개 파일·527,027바이트이며 안내 TXT 하나와 모든 파일의 무결성을 확인했습니다.
SHA-256: `6e130f7b1ab0e439b141eab9989c3cb2403d6324628a16159d25728cf3abbc18`

## 이전 고정 시험판

- [v18 — 로컬 화면에서 기존 후보의 작성 시각·본문 이미지 확인](image-monitor-windows-test-v18.zip)
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
