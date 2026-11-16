# Image Monitor Windows 시험판

[확인한 새 글의 이미지 저장 시험 v15 다운로드](image-monitor-windows-test-v15.zip)

사용자 v14 결과에서 후보 두 글의 작성 시각을 확인했고 한 글에서 정상 이미지 두 개를 읽었습니다.
v15는 그 기존 상세 기록을 사용해 이미지가 있는 글 하나를 고정하고 실제 우클릭과 Windows
저장 창으로 저장합니다. 원본 첨부명 두 개의 대응은 불명확하므로 미확정으로 보존하며,
파일은 순번 이름과 실제 형식의 확장자로 저장합니다. 계속 실행하는 감시는 아직 연결하지 않습니다.

사용자 작업은 ZIP 안의 `image-monitor/WINDOWS_TEST_GUIDE.txt` 하나에 정리했습니다.
압축을 푼 뒤 `RUN_CANDIDATE_SAVE_TEST.cmd`를 더블클릭합니다. 열린 Chrome에서
'저장 시작'을 한 번 누르고 완료까지 창을 그대로 두면 결과 TXT가 자동으로 열립니다.
저장 중에는 다른 창을 클릭하지 않습니다. 오류가 나면 반복 실행하지 않고 창을 그대로 둔 채
결과 TXT 하나를 전달하세요. 주소와 명령어 입력은 필요하지 않습니다.

기존 감시 DB의 기준점·후보·상세 기록을 유지하고, 별도 저장 DB와 이미지 폴더를 사용합니다.
이후 실행도 같은 후보에 고정하며 정상 저장 파일을 다시 받지 않습니다. 현재 제목·작성자·
정확한 이미지 주소·크기·순서가 이전 기록과 다르면 다른 글로 바꾸지 않고 확인을 위해 중단합니다.
세부 검증 범위는 [프로젝트 검증 기록](../image-monitor/docs/validation.md)에 있습니다.
이 후보의 실제 사용자 저장은 새 결과 TXT로 확인합니다.
새 ZIP에는 폴더 바깥의 중복 안내를 넣지 않으며 이전 ZIP은 변경하지 않습니다.

v15 검증: Linux 1,588개 통과·143개 건너뜀, [Windows CI #35](https://github.com/dropboxqfml-code/codex/actions/runs/43837544563) 1,727개 통과·4개 건너뜀.
ZIP은 115개 파일·405,197바이트이며 안내 TXT 하나와 모든 파일의 무결성을 확인했습니다.
SHA-256: `e389ef0156162576c1b8febd1fe94fa7450015a359d077da268d73f24ac526ed`

## 이전 고정 시험판

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
