# ATIV Battery Guard

삼성 **940X3G / Windows 10 x64**에서 사용하는 개인용 배터리 충전 관리 프로그램입니다. 현재 최종 안정판은 **0.3.1**이며, 사용자 Windows 검사와 버튼 강조 확인을 마쳤습니다. 필요한 문제가 생겼을 때 유지보수합니다.

## 프로그램과 사용법

- [사용자 매뉴얼 동봉 프로그램 ZIP](../downloads/ATIVBatteryGuard-0.3.1-WIN10-X64-MANUAL.zip)
- [사용자 매뉴얼](USER_MANUAL_031_KO.txt)
- [0.3.1 변경 내용](RELEASE_031.md) · [사용자 검증 결과](FIELD_031_PERSONAL_RESULT.md)

ZIP 전체를 풀고 `ATIVBatteryGuard.exe`를 실행합니다. 매뉴얼 동봉본은 검증된 프로그램6파일을 그대로 사용합니다. 미서명 개인용 안내는 매뉴얼에 있으며 일반 사용에 개발/검사 도구는 필요 없습니다.

충전 제한 현재 설정 확인과 수동80% 제한/해제, 배터리 상태 모니터링, 관찰 TXT·그래프·키보드/마우스 표본 선택, A/B 비교, 기록별 메모, `.ativrecord` 내보내기/불러오기와 읽기 전용 진단을 제공합니다. 표시된 보호 상태는 마지막 확인 결과입니다.

## 새 대화에서 유지보수하기

1. [새 대화 시작문](NEW_CHAT_START.txt)의 문제 항목을 채워 새 대화에 붙여넣습니다.
2. [유지보수 인수인계](MAINTENANCE_HANDOFF.md), [현재 재개 메모](NEXT_DEVELOPMENT.md), [파일 색인](FILE_INDEX.md)을 먼저 읽습니다.
3. [개발 환경](DEV_ENVIRONMENT.md)에 따라 환경을 확인하고 보고된 문제에 필요한 부분만 수정합니다.

[인수인계 문서 ZIP](../downloads/ATIVBatteryGuard-0.3.1-MAINTENANCE-NOTES.zip)도 보관할 수 있습니다. 문서 묶음이며 전체 소스나 사용자 개인 기록의 백업은 아닙니다. 실제 소스와 검증 기록은 이 GitHub 브랜치에 있습니다.

```text
저장소: dropboxqfml-code/codex
브랜치: feature/ativ-acpi-routing-readonly-20261104
프로젝트: ATIVBatteryGuard
제품 기준: 522acdebb9c4fb8ac09611a31f00385a8ba94239
매뉴얼 기준: 0ed9eea9e5e4a897ffd34111323b420da78fc5f6
```

현재 브랜치 HEAD와 미커밋 작업을 먼저 확인합니다. 제품/매뉴얼 기준 커밋 뒤에는 이 문서 정리 및 이후 유지보수 커밋이 추가될 수 있습니다.

## 개발자 빌드

Visual Studio 2022의 **.NET 데스크톱 개발** 워크로드, **.NET Framework 4.8 개발자/대상 팩**, .NET 8 SDK가 필요합니다. 검증된 SDK는8.0.428입니다. 이 폴더에서 다음 명령으로 앱을 빌드합니다.

```powershell
dotnet build src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj -c Release
dotnet run --project tests/ATIVBatteryGuard.PortableTests.csproj -c Release -- --report reports/portable-maintenance.json
```

새 보고서 이름으로 원본을 보존합니다. Linux 교차 빌드와 Python 패키징 준비는 [DEV_ENVIRONMENT.md](DEV_ENVIRONMENT.md)를 따릅니다. Linux에서의 빌드를 실제 Windows GUI/IME/하드웨어 실행으로 표시하지 않습니다.

## 보존 기준

- [AGENTS.md](AGENTS.md)의 하드웨어·보안·개인정보 규칙을 유지합니다. 기존 수동 제어 경로 외 자동 쓰기/재시도, 부팅 적용, 서비스/드라이버/보안 정책 변경, 런타임 네트워크를 추가하지 않습니다.
- 앱 소스·최종 ZIP·사용자 검증 원본은 GitHub에 보존합니다. 실제 개인 설정/기록/메모는 사용자 PC의 `%LOCALAPPDATA%\ATIVBatteryGuard`에 있고 자동 업로드되지 않습니다.
- 이전 README/재개 메모는 [docs/history](docs/history/)에 보존했습니다. 과거 실패/대기/단발 시험을 현재 할 일로 가져오거나 이미 통과한 시험을 반복하지 않습니다.
