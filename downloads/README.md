# Image Monitor Windows 개발판

[저장 이미지 확인 화면 v20 다운로드](image-monitor-windows-test-v20.zip)

사용자 v19 결과에서 감시 후보 한 글의 `001.jpg` 저장·검증·확정과 Chrome 종료·보류 해제를
확인했습니다. v20은 기존 `RUN_MONITOR.cmd` 화면에서 이미 저장한 파일을 읽기 전용으로
검증하고 보여줍니다. 이미지 재저장이나 새 게시글 요청 없이 저장 결과를 확인할 수 있습니다.

사용자 절차는 ZIP 안의 `image-monitor/WINDOWS_TEST_GUIDE.txt` 하나에 정리했습니다.
압축을 풀고 `RUN_MONITOR.cmd`를 더블클릭한 뒤 화면 아래 '저장 결과'에서 이미지 표시를
확인하고 '프로그램 종료'를 누릅니다. 결과 TXT 하나가 자동으로 열립니다. 화면 크기에 따라
아래로 조금 스크롤하면 됩니다. 감시 시작·후보 내용 확인·네이티브 저장을 반복할 필요는 없습니다.

현재 Windows 세션의 별도 `ImageMonitorMonitorSave` 루트와 `목록 감시`의 고정 선택을 사용합니다.
완료 작업·확정 저널·고정 원본·메타데이터·Pillow 정보와 파일 해시가 일치한 최대 두 파일만
보여줍니다. 기존 기준점·후보·상세·선택·파일·보류 상태를 변경하거나 복구하지 않습니다.

확인은 작업 스레드에서 실행합니다. 파일을 다시 읽지 않는 HTTP 이미지 요청은 검증한 원본
바이트의 메모리 캐시만 반환하며 임의 파일 경로·원본 이미지 URL을 받지 않습니다. 미리보기는
파일당 16MiB·총 32MiB 한도이고 TIFF나 한도 초과 파일은 검증한 메타정보만 표시합니다.
로컬 열람은 서버 대기·접근 차단과 독립적이며 목록 감시와 이미지 자동 저장은 시작하지 않습니다.

사용자 PC의 새 미리보기 연결은 새 결과 TXT와 화면 확인으로 인수합니다.
세부 검증 범위는 [프로젝트 검증 기록](../image-monitor/docs/validation.md)에 있습니다.
새 ZIP에는 프로젝트 폴더 안의 안내 TXT 하나만 넣으며 이전 ZIP은 변경하지 않습니다.

v20 검증: Linux 2,203개 통과·262개 건너뜀, [Windows CI #41](https://github.com/dropboxqfml-code/codex/actions/runs/44077645028) 2,461개 통과·4개 건너뜀.
ZIP은 157개 파일·561,212바이트이며 안내 TXT 하나와 모든 파일의 무결성을 확인했습니다.
SHA-256: `d6e856ba8df680768ef01022020590fbf85f25894b758724f05f7e17e8c551a5`

## 이전 고정 시험판

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
