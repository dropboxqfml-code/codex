# DSDT 직접 읽기 수정 — Acpi-routing-v2

**실기 결과 수신:** DSDT 본문 Complete·설명자/메서드 각 1개·인수 3개·본문 Parsed를 확인했습니다. 후속 [Acpi-routing-v3](ACPI_METHOD_FLOW_UPDATE.md)는 반환/보조 연결 구문을 요약합니다. 아래는 v2 배포 당시 기록이며 v2 같은 출력의 반복이나 관리자 비교는 필요하지 않습니다.

## 확인된 원인과 구현 근거

[v1 실기 결과](ACPI_ROUTING_LAPTOP_RESULT.md)는 목록 Complete·DSDT 0·SSDT 4·첫 SSDT Partial이었습니다. v1은 목록에 DSDT가 없으면 본문 조회를 건너뛰었습니다. 이 조건 때문에 직접 읽기 가능성을 확인하지 못한 것이 확인된 구현 한계입니다. DSDT 자체나 배터리 기능의 부재는 확인되지 않았습니다.

추가 조사에서 ACPICA의 실제 Windows 구현 근거를 확보했습니다.

- [OslTableInitialize](https://github.com/acpica/acpica/blob/e85aa3bebaae81ed1e6d163511ac7e1eafe732cf/source/os_specific/service_layers/oswintbl.c#L231)는 Windows 목록 조회가 DSDT/XSDT를 보고하지 않는다고 설명하고 서명을 직접 추가합니다.
- [AcpiOsGetTableByName](https://github.com/acpica/acpica/blob/e85aa3bebaae81ed1e6d163511ac7e1eafe732cf/source/os_specific/service_layers/oswintbl.c#L516)는 DSDT 등 테이블을 고정 서명의 GetSystemFirmwareTable로 읽습니다.
- 대조 파일은 커밋 `e85aa3bebaae81ed1e6d163511ac7e1eafe732cf`의 `source/os_specific/service_layers/oswintbl.c`이며 SHA-256은 `e3df678cde326239e8261b3ebca33bd929baff544823610369faa50cf44f3930`입니다. 고정 raw 파일과 조사 시점 파일의 바이트 일치를 확인했습니다. ACPICA 프로그램이나 AML을 실행한 것은 아닙니다.

이는 목록 포함 여부를 DSDT 본문 읽기의 필수 조건으로 삼지 않을 구체적인 근거입니다. 현재 노트북에서 직접 읽기나 WMI 정의 해석이 반드시 성공한다는 보장은 아닙니다.

## 바뀐 동작

v2는 정상 목록 조회 뒤 **DSDT 목록 항목이 0이어도 고정 DSDT ID를 직접 조회**합니다. 크기 조회와 본문 읽기를 각각 한 번만 하며 재시도하지 않습니다. 목록 항목 수·직접 읽기 방식·읽기 결과·정적 구문 해석 결과를 분리합니다. 본문 읽기의 Complete가 전체 AML 해석 완료를 뜻하지 않도록 문구도 구분했습니다.

직접 읽기에서 NotFound·AccessDenied·NotSupported·Unavailable·Incomplete가 나오면 해당 고정 종류만 보고합니다. DSDT 읽기가 미확보되더라도 정상 반환된 오류 분류는 뒤의 첫 SSDT 확인과 구분됩니다. 잘못된 테이블 서명·선언 길이·체크섬은 기존 파서에서 InvalidTable로 처리합니다. 예외·시간 초과에는 부분 출력을 완성된 결과로 승격하지 않습니다.

사용하는 네이티브 API는 기존의 EnumSystemFirmwareTables/GetSystemFirmwareTable 두 개입니다. 공급자 ACPI·대상 DSDT/첫 SSDT, 테이블당 4MiB·목록 4096바이트·부모/작업자 각 10초 제한을 유지합니다. 정상 목록에 없는 SSDT를 새로 조회하거나 같은 SSDT ID를 항목 수만큼 반복하지 않습니다.

테스트는 가짜 읽기 콜백으로 목록 누락·직접 읽기·오류·길이 변화와 버퍼 삭제를 검증합니다. 실제 실행 경로는 고정 Windows API를 연결하며 외부에서 API·공급자·ID·입력 경로를 선택할 수 없습니다. 파서·일반 앱·OEM 요청·응답 디코더·예약·충전 제어 정책은 변경하지 않습니다.

## 이번에 포함하지 않은 범위와 미검증 항목

ACPICA는 여러 SSDT를 읽기 위해 Windows ACPI 레지스트리 캐시도 사용합니다. 하지만 같은 구현에 미제공·이름 충돌 한계가 기록돼 있으며 Microsoft가 보장하는 전체 활성 테이블 계약은 아닙니다. 이번 수정은 먼저 구체적으로 확인된 DSDT 누락을 해소하는 데 한정하고 레지스트리 읽기는 추가하지 않습니다. 여전히 첫 SSDT만 확인하며 전체 SSDT 확보나 테이블 간 결합을 보장하지 않습니다.

제한된 AML 정적 파서의 지원 범위도 그대로입니다. DSDT가 읽혀도 Partial이나 미관측일 수 있으며, 그 경우 기능 부재나 FF의 배터리 의미로 바꾸지 않습니다. 삼성 DLL 로드·AML 평가·OEM 호출·원본 테이블 저장·실험 예약 접근·물리 메모리/포트/드라이버 접근·서비스/보안 변경·펌웨어 쓰기는 없습니다. 실제 충전 제어는 계속 Unsupported입니다.

## 새 수정본 확인 방법

1. [프로그램 ZIP](../downloads/ATIVBatteryGuard-ACPI-DSDT-DIRECT.zip) **하나만** 새 폴더에 모두 압축 해제합니다. 소스 ZIP은 실행에 필요하지 않습니다.
2. `ATIVBatteryGuard.AcpiRoutingCheck.exe`를 **일반 권한**으로 실행합니다. 관리자 비교나 기존 v1/1회 OEM 실험 도구 실행은 필요하지 않습니다.
3. **Acpi-routing-v2** 표시가 있는 출력 요약만 전달합니다. 기존 TXT·삼성 DLL·원본 ACPI는 다시 제출하지 않습니다.

이는 이전 결과에서 건너뛴 DSDT 본문 읽기를 추가한 수정본입니다. 같은 v1을 반복하는 절차가 아닙니다. 기존 1회 실험 표식은 유지하고 재실행·삭제·초기화하지 않습니다.

자동 검증 수치와 Windows 실기 미검증 범위는 [VALIDATION](VALIDATION.md)에 기록합니다. 이전 v1의 실행 관측을 v2의 실제 DSDT 읽기 성공으로 보고하지 않습니다. 프로그램 ZIP에는 삼성 원본 바이너리·사용자 보고서·원본 ACPI가 없습니다.
