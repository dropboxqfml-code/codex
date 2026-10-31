# ATIV Battery Guard

Samsung ATIV Book 9 Plus 계열을 위한 Windows 10 x64 배터리 상태·로컬 설정·읽기 전용 진단 앱입니다. C# / WPF / MVVM / .NET Framework 4.8을 사용합니다.

**현재 실제 80%/100% 충전 제한은 지원하지 않습니다.** 사용자 선택값, 실제 하드웨어 상태, Windows가 보고한 배터리 잔량은 별도로 표시합니다. Mock 모드는 메모리 안에서만 동작하는 시뮬레이션입니다.

이 디렉터리는 기존 자체 배포본의 C# 코드를 복원하고 프로젝트·화면·테스트·문서를 재구성한 작업본입니다. 원본 주석·테스트·문서 전체를 복구한 것은 아닙니다. 출처와 제한은 [RECOVERY.md](RECOVERY.md)에 기록합니다.

## Windows 10 빌드

개발용 PC에 다음 구성이 필요합니다.

- Visual Studio 2022의 **.NET 데스크톱 개발** 워크로드
- **.NET Framework 4.8 개발자 팩/대상 팩**
- .NET 8 SDK (SDK 형식 프로젝트와 portable 테스트용)

Visual Studio에서 `ATIVBatteryGuard.sln`을 열고 Release 구성을 빌드합니다. 개발자 터미널에서는 이 디렉터리를 기준으로 실행합니다.

```powershell
dotnet build ATIVBatteryGuard.sln -c Release
```

빌드된 `ATIVBatteryGuard.exe`와 같은 폴더의 앱 DLL·구성 파일을 함께 유지해 실행합니다. 일반 사용자 권한으로 실행하며, 관리자 권한 실행이나 드라이버 설치는 요구하지 않습니다.

Windows에서 빌드·회귀 테스트·제한 시간 90초의 GUI self-test를 함께 실행하려면 다음 명령을 사용합니다. 이 스크립트는 현재 Linux 환경에서 실행하지 않았습니다.

```powershell
powershell -File scripts/Test-Windows.ps1
```

## 동작 범위

- Windows 내장 배터리 API로 잔량·AC 연결·충전 상태 조회
- 사용자 희망 설정을 `%LOCALAPPDATA%\ATIVBatteryGuard\settings.json`에 저장
- 기본 실제 제어 어댑터의 모든 쓰기 요청 거부
- Mock 모드의 80%/100% 선택 시뮬레이션
- 모델·BIOS·Windows 정보와 읽기 전용 진단의 로컬 저장
- 삼성 WMI 클래스 `WmiAcpiVersion`, `WmiAcpiMethod`, `DataBuffer`의 **정의만** 확인하는 진단

진단은 삼성 DLL을 로드하거나 WMI 제어 메서드를 호출하지 않습니다. 클래스가 발견되어도 충전 제한 지원으로 판단하지 않습니다. 배터리 0%가 Windows 측정값이면 0%를 그대로 표시합니다.

## 검증

2026-10-31(한국 시간) 복원된 소스의 .NET Framework 4.8 x64 WPF/XAML 빌드가 성공했고, 실제 Core·ViewModel 코드를 공유하는 .NET 8 portable 테스트 **78개 통과, 실패 0개, 건너뜀 0개**를 확인했습니다. 이전 배포본의 `149개 테스트 통과` 기록을 재사용한 결과가 아닙니다.

```powershell
dotnet run --project tests/ATIVBatteryGuard.PortableTests.csproj -c Release -- --report reports/portable-tests.json
```

새 빌드의 Windows GUI 실행과 실제 노트북의 WMI 메타데이터 조회는 아직 검증하지 않았습니다. Linux의 빌드·portable 테스트는 이를 대신하지 않습니다. 검증 범위와 Windows 수동 확인 절차는 [TEST_PLAN.md](TEST_PLAN.md)를 참고하세요.

사용법은 [USER_GUIDE.md](USER_GUIDE.md), 계층 구조는 [ARCHITECTURE.md](ARCHITECTURE.md), 하드웨어 근거는 [HARDWARE_RESEARCH.md](HARDWARE_RESEARCH.md), 개인정보와 권한은 [SECURITY.md](SECURITY.md)에 설명합니다.
