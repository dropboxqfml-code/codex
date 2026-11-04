# OEM 호출 없는 사전 검증 점검 도구 — 2026-11-04

## 이전 결과에서 보완하는 점

[이전 실제 결과](WMI_ONE_SHOT_PREFLIGHT_RESULT.md)는 Elevated·PreflightFailed·Unavailable·InvocationRequested=false였습니다. 해당 실행은 사전 검증에서 끝났고 후보 요청이나 예약 시도에 진입하지 않았습니다. 이는 기존 예약 표식의 존재 여부를 알려주지는 않습니다. 기존의 공통 오류 문구로는 실패 위치를 특정할 수 없습니다.

새 `ATIVBatteryGuard.WmiPreflightCheck.exe`는 **같은 준비 조건을 읽기 전용으로 확인하고 단계와 고정 오류 분류만 출력**합니다. 기존 1회 실험 실행 파일은 다시 배포하거나 실행하도록 요청하지 않습니다. 기존 실험의 조건을 제거하거나 더 넓은 OEM 시험을 구현하지 않습니다.

## 구현 범위

새 프로젝트는 Core와 읽기 전용 토큰·메타데이터 판독기만 참조합니다. 기존 WindowsOneShotBackend, 실험 runner, 후보 프레임, 예약 객체를 연결하지 않습니다. 실제 실행 ZIP에도 기존 실험 EXE나 삼성 DLL이 없습니다.

- 같은 계정의 Elevated 토큰, Windows 10 x64 조건을 확인합니다. asInvoker이며 자동 권한 상승은 없습니다.
- 기존과 같은 고정 로컬 모델/BIOS 속성, 상세 클래스·메서드 정의와 MethodId=1을 검사합니다. 원래 값은 출력하지 않습니다.
- 기존 옵션으로 WmiAcpiMethod.Active를 전체 열거하여 정확히 한 행이고 활성 상태인지 확인하고 그 대상을 다시 읽습니다. 키와 상대 경로는 로컬 메모리에만 남고 출력하지 않습니다.
- `GetMethodParameters`의 입력 구조와 CIMTYPE를 검사하고 `DataBuffer.CreateInstance`로 메모리 객체만 준비한 뒤 모두 해제합니다. 속성 대입, Put, OEM 메서드 실행은 없습니다.
- 기존 DirectRead 옵션·검사 조건·6초 예산을 유지합니다. 부모와 작업자에 각각 10초 제한이 있으며 완료되지 않은 중간 출력은 성공으로 쓰지 않습니다.
- OEM 호출, 예약 표식의 읽기·쓰기·삭제, 드라이버·서비스·ACL·보안 정책·펌웨어 변경, 삼성 DLL 초기화, 네트워크 통신은 없습니다.

`WsabiWmiPreflightInspectionReport`는 토큰·상태·단계·원인 enum만 보관합니다. HRESULT는 허용 목록의 오류 종류로 변환하고 원문 오류나 숫자·경로·계정·장치 식별자를 보고하지 않습니다. 모든 호출·쓰기·예약 capability는 false입니다.

## 결과 해석

| 항목 | 의미 |
| --- | --- |
| 사전 검증 단계 | 마지막으로 시도한 고정 준비 위치. 실제 OEM 실행 위치가 아닙니다. |
| 원인 분류 | 필드 미관측, CIMTYPE 누락·형식·불일치, 권한 거부, 시간 초과, 알려진 WMI 오류 종류 또는 기타 오류입니다. |
| Complete + 문제 분류 | 해당 단계의 판정은 끝났지만 준비 조건은 충족되지 않았습니다. |
| Ready + None + Complete + Elevated | 이번 준비 검사는 통과했습니다. OEM 호출·보호 상태·충전 제한 성공은 관측하지 않았습니다. |
| 부모/작업자 제한 초과 | TimedOut이며 단계는 Unknown입니다. 중간 결과는 채택하지 않습니다. |

현재 실패 원인은 아직 미확정입니다. 인스턴스 입력 객체의 qualifier, 쿼리 옵션 지원 또는 메모리 객체 생성 등을 원인으로 단정하지 않습니다. 새 결과가 통과해도 이전 실패의 원인이 고쳐졌다는 증거가 되지는 않습니다. 어떤 결과도 드라이버 미설치나 배터리 보호 기능 부재를 뜻하지 않으며 실제 충전 제어는 계속 Unsupported입니다.

## 새 도구 확인 방법

1. [다운로드 안내](../downloads/README.md)의 **WMI-PREFLIGHT-ONLY ZIP** 전체를 이전 프로그램과 다른 새 로컬 폴더에 압축 해제합니다.
2. 같은 Windows 계정에서 **ATIVBatteryGuard.WmiPreflightCheck.exe만** 오른쪽 클릭해 수동 관리자 실행합니다. 이전 결과의 Elevated 조건을 맞추기 위한 읽기 전용 준비 점검입니다. 다른 관리자 계정의 암호가 필요하면 중단합니다.
3. 창 제목의 `사전검증 전용 · OEM 호출 없음`과 출력의 단계·원인 분류를 확인하고 출력만 복사해 전달합니다. Enter로 닫습니다.

이전 `WmiOneShotQuery.exe`는 재실행하지 않으며 기존 예약 표식도 삭제·초기화하지 않습니다. 과거 TXT·삼성 DLL·EXE·파일 목록·일반/관리자 비교 결과를 다시 제출할 필요가 없습니다. 새 도구는 결과 파일도 생성하지 않습니다.

## 빌드와 검증

기존 .NET Framework 4.8 x64/WPF 개발 도구와 캐시를 사용하며 새 런타임 패키지는 필요하지 않습니다. 솔루션의 여섯 프로젝트와 portable 테스트 프로젝트를 Release 빌드합니다. 테스트는 실제 Windows WMI나 펌웨어를 사용하지 않습니다. 새 도구의 Windows 실기 실행은 아직 미검증입니다.

```text
dotnet build ATIVBatteryGuard.sln -c Release
dotnet build tests/ATIVBatteryGuard.PortableTests.csproj -c Release
dotnet tests/bin/Release/net8.0/ATIVBatteryGuard.PortableTests.dll --report reports/wmi-preflight-only-tests.json
python -m unittest discover -s scripts -p 'test_*.py'
python scripts/package_preview.py --source-only --test-report reports/wmi-preflight-only-tests.json --output reports/preflight-only-package
python scripts/package_wmi_preflight_check.py --test-report reports/wmi-preflight-only-tests.json --source-zip reports/preflight-only-package/ATIVBatteryGuard-SOURCE.zip --output reports/preflight-only-package
```

전체 329개 테스트가 통과했고 여섯 프로젝트와 테스트 프로젝트 빌드는 각각 경고·오류 0개입니다. 새 네 테스트 그룹은 오류 분류, 엄격한 준비 완료 조건, 잘못된 enum의 보수적 처리, 출력의 불변성·개인정보 제한을 검사합니다. 패키저는 고정 파일 목록, 실제 PE의 x64/asInvoker와 호출·예약 참조 부재, 전체 소스 대응, SHA-256과 ZIP CRC를 확인합니다.
