# ACPI Field·프레임 통로 선언 요약 — Acpi-routing-v6

2026-11-05 한국 시간. [v5 실기 분석과 다음 계획](ACPI_V5_RESULT_AND_NEXT_PLAN.md)에 따른 후속 구현입니다.

## 실제 관측과 이번 변경

v5 실기에서 후보의 이름 참조 3/3회가 Field로, 해석한 보조 본문의 참조 3/3회가 Mutex·Field로 분류됐습니다. 후보의 직접 `Store(Arg2, Name)` 대상과 `Return(Name)`은 같은 관측 Field 정의를 참조했습니다. 보조 Store 대상 Field의 선언 공간은 SystemIo였습니다. 참조 횟수는 고유 객체 수가 아니며, 보조의 SystemIo를 후보 Field에 적용할 수 없습니다. 후보 Field의 공간·폭과 두 본문의 Region 선언 관계는 v5 출력에 없었습니다.

v6는 같은 수집 범위에서 다음 구문 정보를 추가합니다.

| 새 항목 | 보고 범위 |
| --- | --- |
| 후보 입력 저장 / 반환 Field | 두 역할의 선언 주소 공간과 고정 21바이트 프레임에 대한 선언 폭 분류를 각각 표시합니다. |
| 후보 Field Store의 원천 | 직접 Arg0·Arg1·Arg2·literal·기타 표현식과 Store 구문 수를 표시합니다. |
| 보조 Field Store와의 관계 | 후보의 저장/반환 Field와 해석한 보조 Store Field가 같은 관측 Region 정의를 참조하는지 비교합니다. |
| 기존 연결 지표 설명 | 연결 구문 검사에서 객체 참조·호출 구분을 미확정으로 센 횟수와 선언 종류 분류가 별도 지표임을 명시합니다. 숫자·기존 Flow/객체/FF 판정 의미는 유지합니다. |

## 분류 해석

선언 폭은 원시 숫자로 내보내지 않습니다. 단일 관측 Field 정의의 폭이 고정 프레임과 같으면 `Matches21ByteFrame`, 다른 양의 폭이면 `DoesNotMatch21ByteFrame`입니다. 반복 참조는 같은 정의 하나로 취급합니다. 서로 다른 Field 정의가 여러 개이면 같은 폭이어도 `MultipleCandidates`, 서로 다른 폭이면 `Mixed`입니다. 0폭·미분류·모호함·불완전한 역할이 있으면 `Unknown`으로 남기며, 알려진 비Field 대상까지 제외한 뒤 하나의 일치로 만들지 않습니다. `NotObserved`는 분류 가능한 해당 역할에서 Field 선언을 관측하지 않았다는 범위의 결과입니다.

Store 원천은 **바로 그 피연산자 구문**만 분류합니다. 이름 객체의 값, Local, 계산식, SizeOf, 보조 메서드의 형식 인수를 원래 WMI 입력 값으로 대입하지 않습니다. Store 구문 수는 정적으로 관측한 발생 횟수이며 실행 횟수가 아닙니다.

Region 관계의 `SameObservedDefinition`과 `DifferentObservedDefinitions`는 관측 선언의 동일성만 뜻합니다. 서로 다른 선언도 같은 물리 주소를 사용할 수 있으므로 물리 영역의 동일·겹침·분리를 판단하지 않습니다. 여러 Region 후보는 `Mixed`, 해소되지 않거나 분석하지 못한 본문이 있으면 `Unknown`으로 남깁니다. 부분 namespace 안의 양성 관측도 전체 정의의 완전성·유일성을 보장하지 않습니다.

선언 폭 일치는 정확한 바이트 배치, 변환, 입력 보존, 실제 실행, SMI 여부, 프로토콜 의미나 충전 지원의 증거가 아닙니다. 불일치가 나와도 요청을 자동 수정하지 않습니다. 기존 실제 FF 응답의 생성 위치·의미는 미확정이고 실제 충전 제어는 **Unsupported**입니다.

## 수집·개인정보·안전 경계

기존 `EnumSystemFirmwareTables` / `GetSystemFirmwareTable` 두 Windows 읽기 API, 고정 DSDT 직접 읽기·첫 SSDT 수집만 사용합니다. 모든 SSDT 확보나 테이블 간 결합은 지원하지 않습니다. 목록 4096바이트·표당 4MiB·파서 100,000노드·구문 깊이32·보조 깊이2/정의8개/호출 표현식32개·관측 namespace 객체8192개·본문당 관계 이름64개의 상한과 부모/작업자 각각10초 제한을 유지합니다.

FieldList의 비트 수는 바이트 패키지 경계와 구분해 해독하고 전체 목록 해석 성공 후에만 임시 선언에 반영합니다. 보고서에는 고정 분류·수만 남기며 원시 폭·주소·오프셋·길이·객체 이름·사용자 경로·고유 식별자·원본 ACPI를 출력하거나 저장하지 않습니다. 실제 Field/OperationRegion·포트·물리 메모리를 읽거나 쓰지 않습니다.

AML/OEM/WMI 메서드·삼성 DLL 초기화/실행, 드라이버 설치·서비스 시작/중지, 레지스트리·보안 설정 변경·네트워크 통신을 추가하지 않습니다. 완료된 1회 OEM 실험과 예약 표식에 접근하지 않으며 재실행·초기화·우회도 하지 않습니다. 프로그램 ZIP에는 삼성 원본 DLL이나 실험 EXE를 포함하지 않습니다.

## 다운로드와 실제 노트북 확인

[프로그램 ZIP](../downloads/ATIVBatteryGuard-ACPI-FIELD-CHANNEL.zip) · [일치 소스 ZIP](../downloads/ATIVBatteryGuard-ACPI-FIELD-CHANNEL-SOURCE.zip) · [SHA-256](../downloads/ATIVBatteryGuard-ACPI-FIELD-CHANNEL-SHA256SUMS.txt)

1. **프로그램 ZIP 하나만** 새 폴더에 모두 풉니다. 소스 ZIP은 개발용이므로 실행에 필요하지 않으며 두 ZIP을 한 폴더에 함께 풀지 않습니다.
2. 그 폴더의 `ATIVBatteryGuard.AcpiRoutingCheck.exe`를 **일반 권한**으로 실행합니다. `Acpi-routing-v6` 표시를 확인합니다.
3. 이번에 추가한 Field 통로 선언·입력 역할·Region 관계가 포함된 **새 출력 요약만** 전달합니다. 기존 TXT/DLL/EXE·원본 ACPI를 다시 제출하거나 v5를 반복할 필요는 없습니다. 관리자 비교나 이전 OEM 실험 실행도 필요하지 않습니다.

v5에서는 없었던 선언 폭·후보 공간·Region 관계를 확인하기 위한 새 요약입니다. v6의 Windows 실기는 아직 미관측이며 자동 검증 결과는 [검증 기록](VALIDATION.md)에 별도로 기록합니다. 현재 일반 앱의 배터리 표시는 계속 사용할 수 있고 충전 제어는 활성화하지 않습니다.
