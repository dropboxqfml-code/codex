# Image Monitor Windows 시험판

[저장 완료 파일 확인·종료 정리 v16 다운로드](image-monitor-windows-test-v16.zip)

사용자 v15 결과에서 JPEG·PNG 두 파일의 저장·검증·최종 확정을 확인했습니다.
미완료 이미지는 0개이며 마지막 Chrome 종료 확인 단계에서 완료 표시가 남았습니다.
v16은 기존 파일과 메타데이터를 다시 검사하고, 정확히 소유한 시험 브라우저의 종료를
확인한 뒤 그 완료 표시를 정리합니다. 이미지를 다시 저장하지 않습니다.

사용자 작업은 ZIP 안의 `image-monitor/WINDOWS_TEST_GUIDE.txt` 하나에 정리했습니다.
압축을 푼 뒤 `RUN_CANDIDATE_FINISH.cmd`를 더블클릭하고 자동으로 열리는 결과 TXT
하나를 보내면 됩니다. '저장 시작'과 주소·명령어 입력은 필요하지 않습니다.
확인한 이미지의 저장 위치도 결과 TXT에 표시합니다. 문제가 나면 반복 실행하지 않고
같은 TXT 하나를 전달하세요.

기존 감시·저장 DB는 읽기 전용으로 대조하고 이미지·메타데이터·이전 보고서는 유지합니다.
이전 시험 Chrome이 남았다면 PID·생성 시각·세션·프로필·소유 디버깅 포트를 확인한 뒤
정상 종료만 요청합니다. 새로운 게시글 접속·브라우저 실행·네이티브 저장이나 프로세스 강제 종료는
없습니다. 소유 관계·파일·종료 근거가 불확실하면 보류 표시를 유지합니다.
세부 검증 범위는 [프로젝트 검증 기록](../image-monitor/docs/validation.md)에 있습니다.
사용자 PC의 종료 정리는 새 결과 TXT로 확인합니다.
새 ZIP에는 폴더 바깥의 중복 안내를 넣지 않으며 이전 ZIP은 변경하지 않습니다.

v16 검증: Linux 1,715개 통과·169개 건너뜀과 수정 파일 48개 재검사 통과, [Windows CI #37](https://github.com/dropboxqfml-code/codex/actions/runs/43895624283) 1,880개 통과·4개 건너뜀.
ZIP은 125개 파일·437,301바이트이며 안내 TXT 하나와 모든 파일의 무결성을 확인했습니다.
SHA-256: `310878338e16fc95824fbb317b641253bd1f295fdea402b72ab8082502be03d1`

## 이전 고정 시험판

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
