# ACPI Literal Store 대상·구문 배치 요약 — Acpi-routing-v7

2026-11-05 한국 시간. [v6 실기 결과와 다음 계획](ACPI_V6_RESULT_AND_NEXT_PLAN.md)에 따른 후속 구현입니다.

## 실제 관측과 이번 변경

v6 실기에서 후보 Arg2 저장·직접 반환 Field의 선언 공간은 모두 SystemMemory였고, 선언 폭은 고정21바이트와 일치했습니다. 같은 입력/반환 Field 정의를 참조하는 구문도 유지됐습니다. 보조 Store 대상 Field는 SystemIo이며 후보와의 Region 비교는 DifferentObservedDefinitions였습니다. 이 비교는 관측 선언의 동일성만 다룹니다.

후보의 Field Store 구문은2회였고 직접 원천은 Arg2와 Literal이었습니다. 기존 Literal은 정수·문자열·Buffer·Package를 합친 분류이므로 추가 Store의 대상 역할·literal 종류·구문 배치는 알 수 없었습니다. v7는 이 빈 부분을 같은 수집 범위에서 요약합니다.

| 새 항목 | 보고 범위 |
| --- | --- |
| 후보의 직접 Literal Store | Field 여부와 관계없이 직접 literal 원천인 Store 구문 횟수와 Integer·String·Buffer·Package 구문 종류를 보고합니다. 실행 횟수나 원문 값은 아닙니다. |
| Literal Store 대상 Field | 관측한 Field의 선언 주소 공간과 고정21바이트 대비 폭 범주를 보고합니다. |
| 대상의 관측 정의 관계 | Literal 대상 Field와 후보 Arg2 저장·반환·해석한 보조 Store Field의 정의 및 Region 정의를 각각 비교합니다. |
| 후보의 직접 구문 목록 배치 | Arg2 Store·Literal Store·알려진 보조 호출·Return이 같은 직접 구문 목록에서 앞뒤에 나타나는지 고정된 분류로 표시합니다. |

## 분류 해석

Literal 구문 종류는 **바로 그 Store 원천의 문법**입니다. 이름 객체의 값이나 Local·계산식·보조 인수 값을 대입하지 않습니다. 정수 구문을 보더라도 값 자체를 내보내거나 FF 초기화·상태 초기화·명령 selector·I/O 트리거로 해석하지 않습니다. Literal Store 구문 횟수는 관측한 발생 횟수이며, Field·Region의 후보 수는 서로 다른 관측 정의로 구분합니다.

Field의 폭은 v6와 같은 고정 범주를 사용합니다. 단일 양의 폭은 `Matches21ByteFrame` 또는 `DoesNotMatch21ByteFrame`, 복수의 같은 폭은 `MultipleCandidates`, 서로 다른 폭은 `Mixed`입니다. 0폭·미분류·모호함·불완전한 역할은 `Unknown`으로 남깁니다. 미분류·비Field·비명명 대상을 버려서 남은 하나를 일치로 확정하지 않습니다.

Field/Region 관계의 `SameObservedDefinition`과 `DifferentObservedDefinitions`는 관측 선언의 동일성만 뜻합니다. 여러 정의 후보는 `Mixed`, 미해소·가림·불완전한 비교는 `Unknown`입니다. 같은 선언이 실제 실행 중 객체나 같은 데이터를 보장하지 않으며, 다른 Region 선언도 실제 물리 주소의 분리·겹침 여부를 입증하지 않습니다. 부분 namespace에서 보존한 관측 관계는 전체 정의의 완전성·유일성 보장이 아닙니다.

구문 배치는 후보 본문의 **같은 직접 구문 목록**에 Arg2 Store·Literal Store·알려진 보조 호출·Return이 각각 하나씩 관측되고 역할을 분류할 수 있을 때만 비교합니다. `BeforeInSameList` / `AfterInSameList`는 소스에 나타난 앞뒤 관계입니다. 분기·반복·중첩 Store/호출·복잡한 피연산자가 있으면 `Unknown`, 역할 후보가 여러 개이면 `MultipleCandidates`로 남깁니다. 실제 실행 순서·조건·반복 횟수·값 전파·초기화·트리거 효과를 계산하지 않습니다.

새 Store·호출·Return 추적 이벤트는 본문당64개까지만 기록합니다. 이 상한을 넘으면 새 Store 역할 보고서를 한계 초과로 닫고 기존 Flow·ObjectReferences·FieldChannel·FF 표식의 의미는 바꾸지 않습니다. 기존 본문 해석 실패·관계/연결 한계도 새 분석에서 성공이나 관계 부재로 바꾸지 않습니다.

이 정보를 얻더라도 실제 FF의 생성 위치·모델별 Windows 배터리 명령·보호 ON/OFF는 별도 근거가 필요합니다. 실제 충전 제어는 계속 **Unsupported**입니다.

## 수집·개인정보·안전 경계

기존 `EnumSystemFirmwareTables` / `GetSystemFirmwareTable` 두 Windows 읽기 API와 고정 DSDT 직접 읽기·첫 SSDT만 사용합니다. 목록4096바이트·표당4MiB·파서100,000노드·구문 깊이32·보조 깊이2/정의8개/호출 표현식32개·관측 namespace 객체8192개·본문당 관계 이름64개의 상한과 부모/작업자 각각10초 제한을 유지합니다. 모든 SSDT 확보나 테이블 간 결합을 추가하지 않습니다.

보고서에는 고정 분류·수만 남깁니다. 원문 상수·버퍼·Field 폭·주소·오프셋·길이·객체 이름·구문 위치 번호·사용자 경로·고유 식별자·원본 ACPI는 출력하거나 저장하지 않습니다. 실제 Field/OperationRegion·포트·물리 메모리를 읽거나 쓰지 않습니다.

AML/OEM/WMI 메서드·삼성 DLL 초기화/실행, 드라이버 설치·서비스 시작/중지, 레지스트리·보안 설정 변경·네트워크 통신을 추가하지 않습니다. 완료된1회 OEM 실험과 예약 표식에 접근하지 않으며 재실행·초기화·우회도 하지 않습니다. 프로그램 ZIP에는 삼성 원본 DLL이나 실험 EXE를 포함하지 않습니다.

## 다운로드와 실제 노트북 확인

[프로그램 ZIP](../downloads/ATIVBatteryGuard-ACPI-STORE-ROLES.zip) · [일치 소스 ZIP](../downloads/ATIVBatteryGuard-ACPI-STORE-ROLES-SOURCE.zip) · [SHA-256](../downloads/ATIVBatteryGuard-ACPI-STORE-ROLES-SHA256SUMS.txt)

1. **프로그램 ZIP 하나만** 새 폴더에 전부 풉니다. 소스 ZIP은 개발용이며 실행에 필요하지 않습니다. 두 ZIP을 한 폴더에 함께 풀 필요가 없습니다.
2. 그 폴더의 `ATIVBatteryGuard.AcpiRoutingCheck.exe`를 **일반 권한**으로 실행하고 `Acpi-routing-v7` 표시를 확인합니다.
3. Literal Store 대상·구문 종류·Field/Region 관계·직접 구문 배치가 포함된 **새 출력 요약만** 전달합니다. 기존 TXT/DLL/EXE·원본 ACPI 재제출이나 v6 반복·관리자 비교·완료된 OEM 실험 재실행은 필요하지 않습니다.

새 요약은 v6에 없었던 Literal Store 대상 역할과 제한된 구문 배치를 확인하기 위한 것입니다. v7의 Windows 실기는 아직 미관측이며 자동 검증 결과는 [검증 기록](VALIDATION.md)에 별도로 기록합니다. 현재 일반 앱의 배터리 표시는 계속 사용할 수 있고 실제 충전 제어는 활성화하지 않습니다.
