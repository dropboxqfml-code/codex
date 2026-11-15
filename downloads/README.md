# Image Monitor Windows 시험판

[검색 목록 읽기 시험 v11 다운로드](image-monitor-windows-test-v11.zip)

사용자 v10 결과에서 기존 파일을 유지한 채 4개 전체 저장과 재개를 완료했습니다.
v11은 다음 단계인 검색 목록 한 페이지의 구조를 화면 없는 Chrome으로 읽는 소스 시험판입니다.
목록 분석과 감시 기준점·영구 후보 기록을 개발했으며 실제 정기 감시는 아직 시작하지 않습니다.

사용자 작업은 ZIP 안의 `image-monitor/WINDOWS_TEST_GUIDE.txt` 하나에 정리했습니다.
압축을 푼 뒤 `RUN_LIST_INSPECTION.cmd`를 더블클릭하고 기다리면 됩니다.
이번 읽기 검사는 시작 버튼 조작 없이 진행합니다.
uv·관리형 Python·잠금 의존성을 준비하고 결과 TXT를 자동으로 엽니다.
오류가 나면 반복 실행하지 않고 결과 TXT 하나를 전달하세요.

세부 검증 범위와 실행 결과는 [프로젝트 검증 기록](../image-monitor/docs/validation.md)에 있습니다.
실제 목록 구조는 이번 결과 TXT를 검토해 확인합니다.
새 ZIP에는 폴더 바깥의 중복 안내를 넣지 않으며 이전 ZIP은 변경하지 않습니다.

v11 검증: Linux 961개 통과·73개 건너뜀, Windows 1,030개 통과·4개 건너뜀.
ZIP은 83개 파일·277,501바이트이며 안내 TXT 하나와 모든 파일의 무결성을 확인했습니다.
SHA-256: `d48ebb6878ddd7876c25acaff2c607fb44bbe30714a93591f148632b44b584ef`

## 이전 고정 시험판

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
