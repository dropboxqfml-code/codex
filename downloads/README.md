# Image Monitor Windows 시험판

[수정 시험판 v3 다운로드](image-monitor-windows-test-v3.zip)

[사용자용 짧은 TXT 안내](WINDOWS_TEST_GUIDE.txt)

v3는 uv 설치가 성공한 뒤 새 위치를 찾지 못하던 오류를 수정했습니다.
이미 설치된 uv를 우선 재사용하고, 필요하면 Windows에 등록된 Machine/User PATH를
읽어 검색합니다. 실행 정책이나 레지스트리를 변경하지 않습니다.
Windows 파일 시각 정보의 API 차이로 정상 이미지를 거부하던 문제도 수정했습니다.

Windows 자동검사: 135개 통과·2개 건너뜀.
실제 CMD의 현재/새 등록 경로 검색을 포함하며, 브라우저 저장 UI의 성공 검증은 별도입니다.
[검사 실행](https://github.com/dropboxqfml-code/codex/actions/runs/43634792507)

## 이전 시험판 v2

[자동 준비 포함 시험판 v2 다운로드](image-monitor-windows-test-v2.zip)

[사용자용 짧은 TXT 안내](WINDOWS_TEST_GUIDE.txt)

v2는 `uv` 명령을 찾지 못한 첫 시험 오류를 위한 준비 절차를 포함합니다.
사용자가 할 일은 TXT에 정리했습니다. ZIP을 풀고 `RUN_WINDOWS_TEST.cmd`를 더블클릭하면
uv·관리형 Python·잠금 의존성을 준비한 뒤 시험하고, 결과 TXT를 메모장으로 엽니다.
WinGet이 없거나 설치가 실패하면 결과에 기록하고 중단합니다. 자동 재시도·복구는 하지 않습니다.
실행 정책·패키지 검증·인증서 검증을 끄지 않습니다.

v2의 실제 Windows 실행은 아직 미검증입니다. Linux 테스트 133개와 정적 명령 검토,
ZIP 무결성·CMD/TXT의 Windows 인코딩·줄바꿈을 확인했습니다.

## 이전 고정 시험판

[image-monitor-windows-probe.zip 다운로드](image-monitor-windows-probe.zip)

이 ZIP은 실제 Windows 브라우저 우클릭/저장 창을 검증하기 위한 **소스 시험판**입니다.
완성된 감시 프로그램이나 실행 파일(exe)이 아닙니다. Python 3.12와 uv가 필요합니다.
개인 프로필 대신 전용 시험 브라우저로 로컬 합성 이미지 한 장만 저장합니다.

압축을 풀고 `image-monitor` 디렉터리에서 PowerShell로 실행하세요.

```powershell
uv sync --locked --extra windows
uv run --locked --extra windows image-monitor native-probe --work-root C:/IMProbe --browser edge
```

자세한 절차와 실패 시 복구는 ZIP의 `docs/native-probe.md`에 있습니다.
실제 Windows UI 검증은 아직 완료되지 않았습니다.

SHA-256:
`f3194170e95ce644620171f873a9afdc0cd6aba2782c7128b659c3eb990112d7`

이 ZIP은 대기열 추가 전의 고정 스냅샷(독립 Linux 설치 시험 110개 통과, 파일 19개)입니다.
같은 브랜치의 `image-monitor/` 소스에는 이후 SQLite 대기열 구현(전체 133개 테스트 통과)이
추가되어 있습니다. 실제 사이트 감시·본문 파싱·Windows 저장 연동은 아직 제공하지 않습니다.
