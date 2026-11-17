# Image Monitor Windows 개발판

[남은 감시 후보 저장 v21 다운로드](image-monitor-windows-test-v21.zip)

사용자 v20 결과에서 기존 JPEG 한 개의 재검증·미리보기 캐시 준비·정상 종료를 확인했습니다.
v21은 기존 완료 파일을 재검증해 등록하고, 내용을 확인한 다른 후보를 최대 두 글 저장합니다.
기존 파일은 저장 작업자에 다시 보내지 않습니다. 전체 새 글의 무인 자동 저장은 아직 연결하지 않았습니다.

사용자 절차는 ZIP 안의 `image-monitor/WINDOWS_TEST_GUIDE.txt` 하나에 정리했습니다.
압축을 풀고 `RUN_MONITOR_BATCH.cmd`를 더블클릭한 뒤 전용 Chrome의 '저장 시작'을 누릅니다.
저장 중에는 그 창을 앞에 유지하고 자동으로 열린 결과 TXT 하나를 전달합니다.
현재 기록 기준으로 미저장 확인 후보는 한 글이며, 목록 감시나 내용 확인을 반복할 필요는 없습니다.
버튼 없이 TXT가 열리거나 대기·오류가 나오면 해당 TXT만 전달하고 반복 실행하지 않습니다.

별도 `monitor-save-ledger.sqlite`에 후보·허가·출력 위치·Windows 세션과 단일 시도 이력을 고정합니다.
이미 완료한 단일 저장은 원자적으로 등록하며 새 결과는 `ImageMonitorBatch/tasks/<작업ID>/session-N`
아래의 후보별 별도 DB와 폴더를 사용합니다. 기존 단일 선택·이미지·메타데이터·기준점·상세 기록은
유지합니다. 시작을 먼저 커밋하고 실패·중단 작업은 자동 재시도하지 않습니다.

서비스 대기와 접근 차단을 기존 목록·상세·단일 저장 경로와 공유합니다. 저장 전 404/410을 받고
브라우저 종료·미해결 없음·빈 이미지 DB가 확인된 글만 개별적으로 건너뜁니다. 새 배치 파일은
기존 미리보기에 아직 연결하지 않았으며 `RUN_MONITOR_SAVE.cmd`는 이전 한 글 선택을 유지합니다.
`RUN_MONITOR_BATCH_FINISH.cmd`는 완료 근거가 있는 작업의 파일·브라우저 종료를 재검증하는
지원용 명령으로, 이번 시험에서 추가 실행할 필요가 없습니다.

사용자 PC의 새 배치 저장은 결과 TXT로 확인합니다.
세부 검증 범위는 [프로젝트 검증 기록](../image-monitor/docs/validation.md)에 있습니다.
새 ZIP에는 프로젝트 폴더 안의 안내 TXT 하나만 넣으며 이전 ZIP은 변경하지 않습니다.

v21 검증: Linux 2,373개 통과·332개 건너뜀, [Windows CI #43](https://github.com/dropboxqfml-code/codex/actions/runs/44138122138) 2,701개 통과·4개 건너뜀.
ZIP은 169개 파일·612,136바이트이며 안내 TXT 하나와 모든 파일의 무결성을 확인했습니다.
SHA-256: `c15cf1a2de4da3fbd6098fc4caa8e09f90ca7391db8606877b73ba3f15d5fb86`

## 이전 고정 시험판

- [v20 — 검증한 기존 저장 이미지의 로컬 미리보기](image-monitor-windows-test-v20.zip)
- [v19 — 감시 후보 한 글의 이미지 네이티브 저장](image-monitor-windows-test-v19.zip)
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
