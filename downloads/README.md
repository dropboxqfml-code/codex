# ATIV Battery Guard — P05ACJ 응답 근거 반영판

**후속 개발 완료 — 실행 프로그램은 동일:** [외부 등록 추적·원본 검사 보강](../ATIVBatteryGuard/P05ACJ_EXTERNAL_REGISTRATION_REVIEW.md)을 진행했습니다. 사용자가 아래 프로그램 실행을 보고했으며 추가 업로드·시험·재다운로드는 필요하지 않습니다. 개발용 검사기만 관측 P05ACJ 길이/해시 pin으로 보강했고 Python46개가 통과했습니다. [새 개발 소스 ZIP](ATIVBatteryGuard-P05ACJ-REGISTRATION-SOURCE.zip) · [소스 체크섬](ATIVBatteryGuard-P05ACJ-REGISTRATION-SHA256SUMS.txt). 소스는 실행에 필요하지 않으며 기존 프로그램 ZIP을 덮어쓰지 않았습니다. 실제 충전 제어는 Unsupported입니다. 아래는 직전 실행판 안내입니다.

2026-11-05. [프로그램 ZIP](ATIVBatteryGuard-FIRMWARE-REPLY-EVIDENCE.zip) · [일치 소스 ZIP](ATIVBatteryGuard-FIRMWARE-REPLY-EVIDENCE-SOURCE.zip) · [SHA-256](ATIVBatteryGuard-FIRMWARE-REPLY-EVIDENCE-SHA256SUMS.txt) · [근거·변경·한계](../ATIVBatteryGuard/FIRMWARE_REPLY_EVIDENCE_UPDATE.md)

**프로그램 ZIP 하나만** 새 폴더에 전부 풀고 ATIVBatteryGuard.exe를 일반 권한으로 실행합니다. 소스 ZIP은 개발용이며 함께 풀지 않습니다. 기존 배터리 표시 앱에 P05ACJ의 공통 실패 응답 근거를 반영했습니다. 원하는 경우 이미 보유한 과거 콘솔 출력만 오프라인 검토에 붙여넣어 설명을 확인합니다. 새 노트북 시험·자료 재제출·관리자 비교·OEM 실험 재실행은 필요하지 않습니다.

분석한 이미지에는 여러 실패 조건이 ACK AA와 FF+0 데이터를 만드는 경로가 있습니다. 기존 결과는 첫FF만 있어 전체패턴·현재펌웨어일치·실패원인은 미확정입니다. 순수 디코더의 패턴 비교도 특정 오류나 보호 상태를 확정하지 않으며 실제 충전 제어는 Unsupported입니다.

C#434개·Python42개 통과, 7프로젝트와 portable tests 빌드 경고·오류0개, 실제 PE 매니페스트 asInvoker/uiAccess=false 확인. 새 GUI의 Windows 실기는 미검증인 미서명 개발판입니다. 삼성 원본 DLL·EXE·펌웨어·실험 실행 파일은 포함하지 않습니다. 과거 자료와 일회 예약은 보존합니다.

아래는 이전 배포 당시의 안내입니다. 기존 ZIP은 그대로 보존하며 과거 실행 절차를 다시 요구하지 않습니다.

# ACPI Literal Store 대상·구문 배치 요약 — Acpi-routing-v7

**실기 결과 수신·추가 실행 불필요:** Literal1/Integer가 입력/반환과 같은 SystemMemory·21바이트 Field/Region, 보조 Store와 다른 선언을 참조합니다. 같은 직접 목록의 소스 배치는 Literal Store → Arg2 Store → 보조 호출 → Return입니다. [분석과 다음 계획](../ATIVBatteryGuard/ACPI_V7_RESULT_AND_NEXT_PLAN.md)은 모델별 Windows 배터리 명령·응답 계약의 정적 근거 확보를 우선합니다. v7 반복·관리자 비교·기존 자료 재제출은 필요하지 않습니다. 이번에는 새 프로그램을 배포하지 않으며 아래 ZIP·소스·체크섬은 그대로 보존합니다. 아래는 이전 안내입니다.

2026-11-05 한국 시간. [프로그램 ZIP](ATIVBatteryGuard-ACPI-STORE-ROLES.zip) · [일치 소스 ZIP](ATIVBatteryGuard-ACPI-STORE-ROLES-SOURCE.zip) · [SHA-256](ATIVBatteryGuard-ACPI-STORE-ROLES-SHA256SUMS.txt) · [변경·해석·실행 안내](../ATIVBatteryGuard/ACPI_STORE_ROLE_UPDATE.md)

**실행에는 프로그램 ZIP 하나만 필요합니다.** 새 폴더에 그 ZIP 전체를 풀고 `ATIVBatteryGuard.AcpiRoutingCheck.exe`를 **일반 권한**으로 실행합니다. 소스 ZIP은 개발용이며 다운로드하거나 같은 폴더에 함께 풀 필요가 없습니다. **Acpi-routing-v7** 표시와 새 Literal Store 대상·구문 종류·관측 정의 관계·직접 구문 배치 요약만 전달합니다.

v6의 추가 Literal Store 대상이 입력/반환/보조 Store Field 및 Region과 어떤 관측 선언 관계인지 분류합니다. 직접 literal 종류는 Integer·String·Buffer·Package이며 원문 값은 보고하지 않습니다. 같은 후보 직접 구문 목록의 앞뒤 배치만 비교하고 분기·반복·중첩·복수 후보를 실제 실행 순서로 바꾸지 않습니다. 새 구문 기록은64개로 제한하며 기존 보고서의 의미와 수집 상한은 유지합니다.

같은 두 Windows 읽기 API와 고정 DSDT/첫 SSDT만 사용합니다. AML/OEM/삼성 DLL 실행·원본 저장·예약 접근·실제 영역 접근·하드웨어 쓰기는 없으며 원본 삼성 DLL·실험 EXE를 포함하지 않습니다. 새 v7 분석의 실제 노트북 결과와 FF 의미는 미확정이고 충전 제어는 Unsupported입니다. v6 반복·관리자 비교·기존 TXT/DLL/EXE·원본 ACPI 재제출·완료된 OEM 실험 재실행은 필요하지 않습니다. 아래는 각 단계 당시의 배포 기록이며 과거 실행 절차를 다시 수행하라는 안내가 아닙니다.

## 이전 배포 기록

## ACPI Field·프레임 통로 선언 요약 — Acpi-routing-v6

**실기 결과 수신·추가 실행 불필요:** 입력 저장/반환 Field의 SystemMemory·21바이트 선언 폭 일치, 보조 SystemIo Store와 다른 관측 Region 정의 관계를 확인했습니다. 후보 Store2회 중1회는 Literal 원천이며 [분석과 다음 계획](../ATIVBatteryGuard/ACPI_V6_RESULT_AND_NEXT_PLAN.md)에 남은 대상·literal 종류·구문 관계의 분석 조건을 기록했습니다. v6 반복·관리자 비교·기존 자료 재제출은 필요하지 않습니다. 새 프로그램은 배포하지 않으며 아래 ZIP·소스·체크섬은 배포 당시 그대로 보존합니다. 아래는 이전 안내입니다.

2026-11-05 한국 시간. [프로그램 ZIP](ATIVBatteryGuard-ACPI-FIELD-CHANNEL.zip) · [일치 소스 ZIP](ATIVBatteryGuard-ACPI-FIELD-CHANNEL-SOURCE.zip) · [SHA-256](ATIVBatteryGuard-ACPI-FIELD-CHANNEL-SHA256SUMS.txt) · [변경·해석·실행 안내](../ATIVBatteryGuard/ACPI_FIELD_CHANNEL_UPDATE.md)

**실행에는 프로그램 ZIP 하나만 필요합니다.** 새 폴더에 그 ZIP 전체를 풀고 `ATIVBatteryGuard.AcpiRoutingCheck.exe`를 **일반 권한**으로 실행합니다. 소스 ZIP은 개발용이며 다운로드하거나 같은 폴더에 함께 풀 필요가 없습니다. **Acpi-routing-v6** 표시와 새 Field 통로 선언·입력 역할·Region 관계 요약만 전달합니다.

v5 실기에서 확인한 Field 저장/반환 구문을 바탕으로 후보 Field의 선언 공간·고정21바이트 대비 폭 범주, 직접 Store 원천, 보조 Store와의 Region 선언 동일성을 추가합니다. 반복 참조와 고유 후보를 구분하고 복수·혼합·미확정을 단일 일치로 바꾸지 않습니다. 실제 값·주소·물리 영역·실행·FF 의미는 판단하지 않으며 충전 제어는 Unsupported입니다.

수집은 기존 두 Windows 읽기 API와 고정 DSDT/첫 SSDT·기존 상한을 유지합니다. AML/OEM/삼성 DLL 실행·원본 저장·예약 접근·하드웨어 쓰기는 없으며 원본 삼성 DLL·실험 EXE는 포함하지 않습니다. v6의 새 분석은 실제 노트북에서 아직 미관측입니다. v5 반복·관리자 비교·기존 TXT/DLL/EXE·원본 ACPI 재제출·완료된 OEM 실험 재실행은 필요하지 않습니다. 아래는 각 단계 당시의 배포 기록이며 이전 실행 절차를 다시 수행하라는 안내가 아닙니다.

## 이전 배포 기록

# ACPI 객체·참조 관계 요약 — Acpi-routing-v5

**실기 결과 수신·추가 실행 불필요:** 후보/보조 이름 참조 각 3/3회 분류와 후보 저장/반환의 동일 Field 참조, 보조 SystemIo Field Store 구문을 확인했습니다. [분석과 다음 계획](../ATIVBatteryGuard/ACPI_V5_RESULT_AND_NEXT_PLAN.md)을 기록했고 이번에는 새 프로그램을 배포하지 않습니다. v5 반복·관리자 비교·기존 자료 재제출은 필요하지 않습니다. 아래 ZIP·소스·체크섬은 배포 당시 그대로 보존합니다. 아래는 이전 안내입니다.

[프로그램 ZIP](ATIVBatteryGuard-ACPI-OBJECT-REFERENCES.zip) · [일치 소스 ZIP](ATIVBatteryGuard-ACPI-OBJECT-REFERENCES-SOURCE.zip) · [SHA-256](ATIVBatteryGuard-ACPI-OBJECT-REFERENCES-SHA256SUMS.txt) · [범위·해석·실행 안내](../ATIVBatteryGuard/ACPI_OBJECT_REFERENCE_UPDATE.md)

같은 테이블에서 관측한 Buffer/Mutex/Field 등의 선언 종류와 Store/Return의 동일 정의 참조 구문을 요약합니다. 실제 값·분기·별칭·데이터 전달·영역 접근은 평가하거나 실행하지 않습니다. **프로그램 ZIP 하나만** 새 폴더에 모두 풀고 `ATIVBatteryGuard.AcpiRoutingCheck.exe`를 **일반 권한**으로 실행해 **Acpi-routing-v5**의 새 요약만 전달합니다. 소스 ZIP은 실행에 필요하지 않습니다. v4 반복·관리자 비교·기존 TXT/DLL/원본 ACPI 재제출은 요청하지 않습니다.

수집 API·대상·상한은 유지하며 새 참조 관계 추적은 본문당 고유 이름64개까지입니다. 미분류/가림/한계는 관계 부재로 바꾸지 않고 이름·주소·오프셋·길이는 보고하지 않습니다. OEM/AML/삼성 DLL·실험 예약·하드웨어 쓰기는 없고 실제 충전 제어는 Unsupported입니다. v5의 새 분석 실기는 아직 미관측입니다. 이전 1회 실험·표식은 그대로 유지합니다.

## ACPI 보조 본문 구문 점검 v4 — 이전 배포 기록

**실기 결과 수신·추가 실행 불필요:** 보조 본문 해석 1개·미지원 0·실패 None·Acquire/Release를 확인했습니다. [분석과 다음 개발 계획](../ATIVBatteryGuard/ACPI_V4_RESULT_AND_NEXT_PLAN.md)을 기록했고 이번에는 새 프로그램을 배포하지 않습니다. v4 반복·관리자 비교·기존 자료 재제출은 필요하지 않습니다. 아래 ZIP·소스·체크섬은 배포 당시 그대로 보존합니다. 아래는 이전 안내입니다.

[프로그램 ZIP](ATIVBatteryGuard-ACPI-HELPER-SYNTAX.zip) · [일치 소스 ZIP](ATIVBatteryGuard-ACPI-HELPER-SYNTAX-SOURCE.zip) · [SHA-256](ATIVBatteryGuard-ACPI-HELPER-SYNTAX-SHA256SUMS.txt) · [결과·변경·해석 경계](../ATIVBatteryGuard/ACPI_HELPER_SYNTAX_UPDATE.md)

v3의 보조 본문 미지원 결과를 바탕으로 표준 확장 구문의 정적 읽기와 고정된 중단 원인 표시를 추가했습니다. **프로그램 ZIP 하나만** 새 폴더에 모두 풀고 `ATIVBatteryGuard.AcpiRoutingCheck.exe`를 **일반 권한**으로 실행해 **Acpi-routing-v4**의 새 요약만 전달합니다. 소스 ZIP은 실행에 필요하지 않습니다. 기존 TXT/DLL/원본 ACPI 재제출·v3 반복·관리자 비교는 요청하지 않습니다.

구문 이름 Acquire/Wait/Sleep/Fatal 등을 읽더라도 실제 동작은 실행하지 않습니다. 수집 API·대상·시간/크기 제한은 그대로이며 AML/OEM/DLL 실행·원본 저장·예약 접근·하드웨어 쓰기는 없습니다. 해석 완료한 일부 본문의 FF 미관측은 전체 연결이나 실제 응답의 부재가 아닙니다. 새 v4 분석은 실기 미관측이고 충전 제어는 Unsupported입니다. 기존 1회 실험·표식은 그대로 유지합니다.

## ACPI 메서드 연결 구문 요약 v3 — 이전 배포 기록

[프로그램 ZIP](ATIVBatteryGuard-ACPI-METHOD-FLOW.zip) · [일치 소스 ZIP](ATIVBatteryGuard-ACPI-METHOD-FLOW-SOURCE.zip) · [SHA-256](ATIVBatteryGuard-ACPI-METHOD-FLOW-SHA256SUMS.txt) · [실기 관측·변경·해석 한계](../ATIVBatteryGuard/ACPI_METHOD_FLOW_UPDATE.md)

v2에서 DSDT 직접 읽기와 알려진 설명자/메서드 각 1개·인수 3개·본문 Parsed를 확인했습니다. v3는 **같은 수집 범위에서** 후보의 반환 형태·직접 Arg2 전달·제한된 보조 정의 연결을 정적으로 요약합니다. **프로그램 ZIP 하나만** 새 폴더에 모두 풀고 `ATIVBatteryGuard.AcpiRoutingCheck.exe`를 **일반 권한**으로 실행해 **Acpi-routing-v3**의 새 요약만 전달합니다. 소스 ZIP은 실행에 필요하지 않습니다. 기존 TXT/DLL/원본 ACPI 재제출이나 v2 반복·관리자 비교는 요청하지 않습니다.

AML/OEM 실행·변수/조건 계산·레지스트리 읽기·원본 저장·예약 접근·하드웨어 쓰기는 없습니다. 구문 존재가 실제 실행 경로/FF 의미/충전 기능을 입증하지 않으며 실제 제어는 Unsupported입니다. 새 v3 분석의 실기는 아직 미관측입니다. 기존 1회 실험 재실행·표식 삭제는 하지 않습니다.

## DSDT 직접 읽기 수정본 v2 — 이전 배포 기록

[프로그램 ZIP](ATIVBatteryGuard-ACPI-DSDT-DIRECT.zip) · [일치 소스 ZIP](ATIVBatteryGuard-ACPI-DSDT-DIRECT-SOURCE.zip) · [SHA-256](ATIVBatteryGuard-ACPI-DSDT-DIRECT-SHA256SUMS.txt) · [변경 근거·범위·실행 안내](../ATIVBatteryGuard/ACPI_DSDT_DIRECT_READ_UPDATE.md)

v1에서 목록 미관측 때문에 건너뛴 DSDT를 고정 ID로 직접 읽는 수정본입니다. 공개 ACPICA 구현에 근거해 미열거 gate를 제거했습니다. **프로그램 ZIP 하나만** 새 폴더에 모두 풀고 `ATIVBatteryGuard.AcpiRoutingCheck.exe`를 **일반 권한**으로 실행해 **Acpi-routing-v2** 요약만 전달합니다. 소스 ZIP은 개발용이며 실행에 필요하지 않습니다. 기존 TXT/DLL/원본 ACPI는 다시 제출하지 않습니다.

기존 두 Windows 읽기 API와 크기·시간 제한을 유지합니다. AML/OEM 실행·레지스트리 읽기·원본 저장·예약 접근은 없으며 실제 충전 제어는 Unsupported입니다. 모든 SSDT를 읽거나 FF 의미를 확정한 결과는 아닙니다. v2의 실제 Windows 직접 읽기는 아직 미검증입니다. 기존 1회 실험 재실행·표식 삭제는 하지 않습니다.

## ACPI 정적 WMI 연결 점검 v1 — 이전 배포 기록

**실기 결과 수신·추가 실행 불필요:** [결과 분석](../ATIVBatteryGuard/ACPI_ROUTING_LAPTOP_RESULT.md)에서 목록 Complete·DSDT 0·SSDT 4·첫 SSDT Partial을 확인했습니다. WMI 정의와 FF 의미는 아직 미확정입니다. 기존 점검을 반복하거나 관리자 실행·기존 자료 재제출을 할 필요는 없습니다. 배포 ZIP·일치 소스·체크섬은 그대로 보존합니다. 아래는 배포 당시 안내입니다.

[새 점검 도구 ZIP](ATIVBatteryGuard-ACPI-ROUTING-CHECK.zip) · [일치 소스 ZIP](ATIVBatteryGuard-ACPI-ROUTING-CHECK-SOURCE.zip) · [SHA-256](ATIVBatteryGuard-ACPI-ROUTING-CHECK-SHA256SUMS.txt) · [범위·한계·실행 안내](../ATIVBatteryGuard/ACPI_STATIC_ROUTING_CHECK.md)

현재 노트북의 WMI 펌웨어 연결 정의를 Windows 내장 API로 읽는 별도 도구입니다. **AML 실행·OEM 호출·예약 접근·원본 테이블 저장은 없습니다.** DSDT/첫 SSDT의 제한된 구문만 요약하며 전체 펌웨어 해석이나 FF 의미 해결을 보장하지 않습니다. 실제 충전 제어는 미지원입니다.

ZIP 전체를 새 로컬 폴더에 풀고 **ATIVBatteryGuard.AcpiRoutingCheck.exe를 일반 권한으로 실행**합니다. `(Acpi-routing-v1)` 표시가 있는 새 출력 요약만 전달하면 됩니다. 기존 배터리 진단/TXT/DLL을 다시 제출하지 않으며 원본 ACPI도 제출하지 않습니다. 이전 1회 실험은 재실행하지 않고 예약 표식을 유지합니다. 새 도구의 Windows 실기는 미검증입니다.

## 현재 일반 앱 — 계속 사용 가능

**실기 확인:** 사용자가 현재 앱의 일반 권한 실행과 배터리 정상 표시를 확인했습니다. 붙여넣기 검토까지 확인한 것으로 확대하지 않습니다. 일반 앱은 아래 배포를 계속 사용합니다. 이번에 추가한 별도 ACPI 점검 도구의 실행 방법과 필요한 새 요약은 위 안내를 따릅니다. [이전 정적 조사 기록](../ATIVBatteryGuard/WMI_MODEL_CONTRACT_FOLLOWUP.md)도 보존합니다.

[새 프로그램 ZIP](ATIVBatteryGuard-WMI-RESULT-REVIEW.zip) · [일치 소스 ZIP](ATIVBatteryGuard-WMI-RESULT-REVIEW-SOURCE.zip) · [SHA-256](ATIVBatteryGuard-WMI-RESULT-REVIEW-SHA256SUMS.txt) · [실제 결과·해석·개발 내용](../ATIVBatteryGuard/WMI_ONE_SHOT_QUERY_RESULT.md)

승인된1회 실험에서 WMI 응답과 ValidFrame을 확인했으며 후보 표식은FF입니다. 이는 보호OFF/ON이나 하드웨어미지원 판정이 아닙니다. **기존 실험은 완료됐으므로 다시 실행하지 않고 예약 표식을 그대로 유지합니다.**

새 ZIP 전체를 새 로컬 폴더에 풀고 **ATIVBatteryGuard.exe를 일반 권한으로 실행**합니다. 새 '과거 WMI 실험 결과 검토'에 원하는 경우 이미 받은 콘솔 출력을 붙여넣어 확인합니다. 검토는 추가 장치/WMI/OEM/예약 접근 없이 텍스트만 처리하며 원문 입력을 비우고 저장하지 않습니다. 현재 장치 일치나 텍스트 진위는 검증하지 않습니다.

이 일반 앱의 오프라인 검토를 위해 새 OEM 시험이나 기존 자료 재제출은 필요하지 않습니다. 기존 Windows 배터리 표시와 읽기 전용 진단은 유지하며 실제 충전 제어는 계속 Unsupported입니다. 삼성 원본 DLL·실험 EXE·사용자 원문 보고서는 포함하지 않습니다. 붙여넣기 검토 GUI의 Windows 실기는 아직 미검증입니다. 아래는 과거 배포 기록이며 실험 실행 절차를 다시 수행하지 않습니다.

## 완료된 1회 조회 수정본 — 보관용·재실행 금지

[새 실험 프로그램 ZIP](ATIVBatteryGuard-WMI-ONE-SHOT-LOCATOR.zip) · [일치 소스 ZIP](ATIVBatteryGuard-WMI-ONE-SHOT-LOCATOR-SOURCE.zip) · [SHA-256](ATIVBatteryGuard-WMI-ONE-SHOT-LOCATOR-SHA256SUMS.txt) · [실기 결과·변경·정확한 실행 범위](../ATIVBatteryGuard/WMI_QUERY_LOCATOR_READY_RESULT.md)

사용자 노트북의 Locator-v2가 Ready까지 통과해, 같은 경로 정보 옵션을 기존 승인 조회 도구에 적용했습니다. **이 수정본은 실제 OEM 조회 후보0x65를 최대1회 요청할 수 있는 한정 실험입니다.** 원래 요청·안전 조건과 같은 WmiQuery65-v1.attempt 예약을 유지하며 표식이 있으면 호출하지 않습니다. 새 폴더/버전은 횟수를 초기화하지 않습니다.

ZIP 전체를 새 로컬 폴더에 풀고 **그 안의 ATIVBatteryGuard.WmiOneShotQuery.exe만 같은 Windows 계정에서 수동 관리자 권한으로 한 번 실행**합니다. **Query65-locator-v2** 표시와 새 출력만 전달한 후 재실행하지 않습니다. 기존 표식이 있다는 결과도 그대로 전달하며 삭제·초기화·다른 계정 우회를 하지 않습니다. 다른 계정의 암호가 필요하거나 보호 기능이 차단하면 중단합니다.

후보 의미와 예상하지 못한 펌웨어 부작용은 아직 미검증이며 새 수정본의 실제 OEM 결과도 미관측입니다. 어떤 표식도 보호 ON/OFF나 충전 제한 성공으로 표시하지 않습니다. 실제 충전 제어는 계속 Unsupported입니다. 삼성 원본 DLL·이전 EXE·원문 보고서는 새 ZIP에 포함하지 않습니다. 같은 무호출 점검·과거 TXT/DLL/EXE·파일 목록·권한 비교는 다시 필요하지 않습니다. 아래는 이전 배포 기록입니다.

## 무호출 경로 정보 점검판 — 이전 배포 기록

[새 프로그램 ZIP](ATIVBatteryGuard-WMI-PREFLIGHT-LOCATOR.zip) · [일치 소스 ZIP](ATIVBatteryGuard-WMI-PREFLIGHT-LOCATOR-SOURCE.zip) · [SHA-256](ATIVBatteryGuard-WMI-PREFLIGHT-LOCATOR-SHA256SUMS.txt) · [변경 내용·결과 해석](../ATIVBatteryGuard/WMI_PREFLIGHT_LOCATOR_UPDATE.md)

메서드 대상 쿼리에만 경로 정보 확보 옵션을 추가하고 객체·경로 문제와 명시적 Active=false를 구분한 새 무호출 점검판입니다. 기존 단일 활성 대상과 입력 검증은 유지합니다. **OEM 호출·예약 파일 접근·삼성 DLL 실행은 없고 충전 제어는 미지원**입니다. 새 점검판의 Windows 실기 실행은 아직 미검증입니다.

ZIP 전체를 새 로컬 폴더에 풀고 그 안의 **ATIVBatteryGuard.WmiPreflightCheck.exe만 같은 계정에서 수동 관리자 실행**합니다. `(Locator-v2)` 표시와 단계·원인 분류가 있는 새 출력만 전달하세요. 다른 관리자 계정의 암호가 필요하면 중단합니다. 과거 TXT·삼성 DLL·EXE·파일 목록·권한 비교는 다시 제출할 필요가 없습니다.

이전 **WmiOneShotQuery.exe는 재실행하지 않고 기존 예약 표식도 건드리지 않습니다.** 삼성 원본 DLL과 이전 실험 EXE는 새 ZIP에 포함하지 않습니다. 아래는 이전 배포 기록입니다.

## 최초 사전 검증 점검 도구 — 이전 배포 기록

**실기 결과 수신:** [MethodEnumeration 대상 조건 불일치 분석](../ATIVBatteryGuard/WMI_PREFLIGHT_ENUMERATION_RESULT.md)을 기록했습니다. 이번에는 새 실행 파일을 배포하지 않으며 아래 기존 점검 도구를 반복 실행할 필요가 없습니다. 다음 수정 범위는 오류 분류와 경로 정보 확보 방식입니다. 아래는 해당 배포 당시의 안내입니다.

[새 점검 프로그램 ZIP](ATIVBatteryGuard-WMI-PREFLIGHT-ONLY.zip) · [일치 소스 ZIP](ATIVBatteryGuard-WMI-PREFLIGHT-ONLY-SOURCE.zip) · [SHA-256](ATIVBatteryGuard-WMI-PREFLIGHT-ONLY-SHA256SUMS.txt) · [변경 내용·결과 해석](../ATIVBatteryGuard/WMI_PREFLIGHT_ONLY_CHECK.md)

이전 Elevated 사전 검증 실패의 단계와 고정 오류 분류를 확인하는 별도 도구입니다. **OEM 메서드 실행과 기존 예약 표식의 읽기·쓰기·삭제가 없습니다.** 실제 충전 제어는 계속 Unsupported이며 새 도구의 Windows 실기는 아직 미검증입니다. 삼성 원본 DLL과 이전 실험 EXE는 포함하지 않습니다.

ZIP 전체를 새 로컬 폴더에 풀고 **ATIVBatteryGuard.WmiPreflightCheck.exe만 같은 Windows 계정에서 수동 관리자 실행**합니다. 창의 `사전검증 전용 · OEM 호출 없음`을 확인하고 새 출력만 복사해 전달하세요. 과거 TXT·삼성 DLL·EXE·파일 목록·권한 비교를 다시 제출할 필요는 없습니다.

**이전 ATIVBatteryGuard.WmiOneShotQuery.exe는 다시 실행하지 않고 기존 예약 표식도 삭제·초기화하지 않습니다.** 아래는 보존된 과거 배포 기록이며 해당 실행 안내를 다시 수행하지 않습니다.

## 기존 1회 실험 도구 — 보관용·재실행 금지

**2026-11-04 결과 수신:** Elevated·PreflightFailed·Unavailable·OEM 호출 요청 없음으로 사전 검증에서 중단됐습니다. [분석과 보고 전용 수정](../ATIVBatteryGuard/WMI_ONE_SHOT_PREFLIGHT_RESULT.md)을 기록했습니다. 이번에는 새 실험 EXE를 배포하지 않으며 아래 기존 ZIP을 재실행하거나 예약 표식을 삭제하지 않습니다.

[실험 프로그램 ZIP 다운로드](ATIVBatteryGuard-WMI-ONE-SHOT-QUERY.zip) · [같은 버전 소스 ZIP](ATIVBatteryGuard-WMI-ONE-SHOT-SOURCE.zip) · [승인·제한·실행 안내](../ATIVBatteryGuard/WMI_ONE_SHOT_QUERY_APPROVAL.md)

사용자가 미검증 조회후보0x65를 별도 도구·같은 계정의 수동 관리자 실행으로 최대1회 시험하는 범위를 명시적으로 승인했습니다. 같은 승인 재요청 없이 구현·검증했습니다. 모델/BIOS·상승토큰·고정규약/번호1·전체조회완료의 단일Active대상·입력준비·영속예약이 모두 맞아야 요청합니다. 같은 계정의 로컬1회표식이 있거나 안전하게 예약하지 못하면 호출하지 않으며 초기화·삭제·재시도 기능은 없습니다.

ZIP 전체를 메인 앱과 다른 새 로컬 폴더에 풀고 **ATIVBatteryGuard.WmiOneShotQuery.exe**를 오른쪽 클릭해 **같은 계정에서 관리자 권한으로 한 번만 실행**합니다. 자동 권한 상승은 없습니다. 다른 계정의 암호를 요구하거나 보안 제품이 차단하면 중단하고 우회하지 않습니다. 출력만 복사해 전달한 뒤 Enter로 닫습니다. 이전 TXT·DLL·파일 목록·권한 비교는 다시 필요하지 않습니다. 호출 요청·시간 초과·결과 불명 뒤에는 재실행하거나 예약 표식을 삭제하지 않습니다.

고정0x65·payload80+15개00만 사용하며 설정명령0x66·다른명령·삼성DLL·SABI장치/포트IO·driver/service/ACL/보안변경·메인앱연결은 없습니다. 비동기 완료상태0과정확히1개출력후에만제한된Bytes를읽고 후보표식만분류합니다. 표식0/1/FF를실제보호OFF/ON/미지원으로판정하지않습니다. 부모와작업자의10초종료가이미시작된펌웨어동작의취소·복구를보장하지는않습니다.

전체322개 테스트 및 Python6개 통과,5개프로젝트빌드경고·오류0개입니다. 자동검증은가상backend/메모리콜백/더미예약파일을사용했습니다. **새 도구의 Windows 실기는 미검증인 미서명 개발판이며 후보 의미·예상하지 못한 펌웨어 부작용은 아직 검증되지 않았습니다.** 실제 충전 제어는 계속 Unsupported입니다. 삼성 원본 DLL·EXE·사용자 원문 보고서는 포함하지 않습니다.

SHA-256:

- 실행 ZIP: 47cd8a0669fe7822aa7f9173ce84347d2ed3cb0658b091028f64182e08524d8e
- 소스 ZIP: dc087c9f72ab6c57855f6c20cb2a3e2df01fb359310163722c81043c36c036d0

아래는 이전 승인 전 검토서와 배포 이력입니다.

## 이전 다음 실제 단계 검토서 — OEM 조회 후보 실험 미승인

[후보·입력·중단 조건·위험 검토서](../ATIVBatteryGuard/WMI_ONE_SHOT_QUERY_REVIEW.md) · [현재 검증된 개발 소스 ZIP](ATIVBatteryGuard-WMI-PIPELINE-SOURCE.zip)

추가 공개자료를 조사했지만 현재 모델의 Windows WMI 배터리 명령 계약은 확정하지 못했습니다. 다음 실제 단계로 미검증 조회후보0x65를 별도 도구·같은 계정의 수동 관리자 실행으로 최대1회 시험할지 검토하는 문서를 준비했습니다. 이 제안은 기존 OEM 실행 제외 범위를 바꾸는 것이므로 명시적 승인 전에는 구현·실행하지 않습니다.

실제 OEM 코드·새 EXE·실기 시도는 아직 없습니다. 기존 프로그램과 소스 ZIP은 그대로 보존하며 새 실행이나 이전 TXT/DLL/권한 비교 재제출은 요청하지 않습니다. 후보 의미가 검증되지 않아 예상하지 못한 펌웨어 동작 가능성을 배제할 수 없습니다. 실제 충전 제어는 계속 Unsupported입니다.

이번 변경은 조사·검토 문서입니다. 아래297개 테스트·빌드0은 이전 코드의 검증 기록이며 이번에 다시 실행한 결과가 아닙니다.

## 이전 WMI 메모리 채널·통합 경로 개발 소스

[최신 개발 소스 ZIP](ATIVBatteryGuard-WMI-PIPELINE-SOURCE.zip) · [구현·검증·남은 조건](../ATIVBatteryGuard/WMI_BOUND_CHANNEL_AND_PIPELINE.md) · [기존 실기 확인 프로그램](ATIVBatteryGuard-WMI-PARAMETER-CHECK.zip)

요청 인코더·비동기 조정기·메서드 바인더·응답 검증기를 명시적으로 주입한 메모리 snapshot 경계로 연결했습니다. 잘못된 요청의 무호출, 중첩 필드 오류/byte 오류 구분, 취소·시간 초과 뒤 실제 작업 종료 전 Busy와 늦은 응답 처리를 통합 검증했습니다. 기존 byte decoder와 bool validator의 동작을 유지합니다.

전체297개 테스트 통과·실패/건너뜀0개, 4개 프로젝트 빌드 경고·오류0개입니다. 가짜 transport만 사용했으며 실제 WMI/native/OEM 구현·인스턴스 자동 선택·앱 등록은 없습니다. 이번에는 개발 소스를 제공하고 노트북에서 새로 실행·제출할 항목은 없습니다. 기존 실행판은 그대로 보존합니다.

현재 모델의 배터리 명령 의미·읽기 안전성·실제 응답 계약은 여전히 미확정이고 실제 보호 상태 조회·충전 제어는 미구현·Unsupported입니다. 공개 포크·이슈 후속 조사에서도 새 근거는 확보하지 못했습니다. 소스 ZIP에는 자체 소스·문서만 있으며 원본 삼성 바이너리·사용자 TXT·외부 코드·빌드 출력은 없습니다.

소스 ZIP SHA-256: 366d08d2f96634630c5af72c0cdbe0179993533e4e2a273980fd7c4a1bd8c0fa

아래는 이전 프로그램과 개발 이력입니다.

## 이전 WMI 형식 확인 완료·메모리용 바인더 개발 소스

[최신 개발 소스 ZIP](ATIVBatteryGuard-WMI-BINDING-SOURCE.zip) · [실제 결과·구현·남은 조건](../ATIVBatteryGuard/WMI_MATCHED_BINDING_AND_OFFLINE_ENVELOPE.md) · [노트북에서 확인한 판독기2 프로그램](ATIVBatteryGuard-WMI-PARAMETER-CHECK.zip)

판독기2의 실제 결과로 GUID 후보·메서드·입출력 DataBuffer·Bytes UInt8[]의 형식 일치를 확인했습니다. 기존 Unknown은 해소됐고 같은 규약 진단·파일 목록·관리자 비교는 다시 필요하지 않습니다. WindowsMethodId1은 관측값 그대로 유지합니다.

최신 내부 코드는 상세 메타데이터를 바탕으로 inData/Bytes 요청 포장과 outData/Bytes 응답 추출을 기존 프레임 인코더·검증기에 연결합니다. 분리된 메모리 snapshot만 처리하며 WMI/native 객체 생성·OEM 호출·실제 전송 채널은 없습니다. 이번에는 소스 ZIP을 제공하고 새 노트북 실행을 요청하지 않습니다. 기존 프로그램 ZIP은 실기 확인에 사용한 판독기2로 보존하며 이번 코드가 들어간 새 실행판으로 표시하지 않습니다.

전체286개 테스트 통과·실패/건너뜀0개, Core·WPF·두 별도 도구 빌드 경고·오류0개입니다. 현재 모델의 실제 배터리 명령 의미·읽기 안전성·응답 계약은 여전히 미확정이고 실제 충전 제어는 Unsupported입니다. 소스 ZIP에는 자체 소스·문서만 있으며 삼성 바이너리·사용자 원문 TXT·외부 코드·실행 파일은 없습니다.

소스 ZIP SHA-256: 22739035c1aaee8e3a53fa4ffd05fb136f2d878580fadf70f8783bb288192f78

아래는 이전 프로그램과 관측 이력입니다.

## 이전 WMI 입출력 형식 판독 보완판 — 판독기 2

[새 프로그램 ZIP 다운로드](ATIVBatteryGuard-WMI-PARAMETER-CHECK.zip) · [같은 버전 소스 ZIP](ATIVBatteryGuard-WMI-PARAMETER-SOURCE.zip) · [실제 결과·공식 근거·수정 범위](../ATIVBatteryGuard/WMI_PARAMETER_RESULT_AND_CIMTYPE_REVIEW.md)

사용자 결과에서 공개 GUID 후보 일치·메서드 존재·Windows 메서드 번호1·Bytes UInt8[]를 확인했습니다. 입출력 Unknown은 미확정으로 보존합니다. 기존 도구에서 누락한 표준 CIMTYPE 표기를 읽도록 고쳤으며 실제 노트북 CIMTYPE와 이번 실행의 권한 수준은 아직 미관측입니다. 번호1을 Linux0이나 배터리 명령으로 치환하지 않습니다.

ZIP 전체를 메인 앱과 다른 새 로컬 폴더에 풀고 **ATIVBatteryGuard.WmiContractCheck.exe**를 일반적으로 실행합니다. 상단의 **메타데이터 판독기: 2 (CIMTYPE 포함)**과 inData/outData의 **CIMTYPE·판정**이 새 확인 대상입니다. 고정 정의의 qualifier 누락·다른 정의·잘못된 형식·충돌을 독립 표시하며 원문 클래스명은 내보내지 않습니다. 이전 TXT·삼성 DLL·권한 비교는 다시 필요하지 않습니다. 관리자 실행은 요청하지 않습니다.

전체274개 테스트와 Python6개 통과, 4개 프로젝트 빌드 경고·오류0개입니다. 이전 도구의 클래스 조회는 이번 사용자 출력으로 실기 확인됐지만 수정 판독기2의 Windows 실행은 미검증입니다. 실제 OEM 호출·배터리 보호 설정 조회·충전 제어는 미구현이며 Unsupported를 유지합니다. 삼성 원본 바이너리·사용자 원문 출력은 포함하지 않습니다.

SHA-256:

- 실행 ZIP: 49e410aa46ee55423ad44d4f9213ea7a4e1c34d64fcddae448b65997af9a608a
- 소스 ZIP: b4f555baae75802ec3914c48e835acd7bc4069513183f3e1ce6e71b9b56c4723

아래 이전 프로그램과 관측 이력은 그대로 보존합니다.

## 이전 WMI 정적 클래스 규약 확인 도구

[새 도구 ZIP 다운로드](ATIVBatteryGuard-WMI-CONTRACT-CHECK.zip) · [같은 버전 소스 ZIP](ATIVBatteryGuard-WMI-CONTRACT-SOURCE.zip) · [구현·확인 항목·한계](../ATIVBatteryGuard/WMI_EXCHANGE_AND_BINDING_CHECK.md)

ZIP 전체를 메인 앱과 다른 새 로컬 폴더에 풀고 **ATIVBatteryGuard.WmiContractCheck.exe**를 일반적으로 더블클릭합니다. 새 WmiAcpiMethod/DataBuffer 클래스 정의의 조회 상태·공개 GUID 후보 일치·WmiMethodId·입출력/Bytes 형식만 확인하고 출력 내용을 복사한 뒤 Enter로 닫습니다. 기존 배터리 진단·삼성 파일 TXT·삼성 DLL·일반/관리자 비교를 다시 제출할 필요는 없습니다.

asInvoker 도구이며 관리자 실행을 요청하지 않습니다. 권한 거부·시간 초과가 나오면 그대로 사용합니다. 실제 GUID·인스턴스·토큰·사용자 이름·SID·경로는 출력하지 않습니다. OEM 메서드 실행·삼성 DLL 로드·서비스/드라이버/ACL·펌웨어 변경과 네트워크 통신은 없습니다. 정의 일치는 배터리 명령의 안전성·실제 응답 계약·충전 제어 지원의 증거가 아닙니다.

개발 소스에는 비동기 프레임 처리도 포함했지만 가짜 채널만 검증했고 실제 OEM 채널이나 앱 호출 경로는 없습니다. 전체262개 테스트와 Python6개 통과, Core·WPF·두 별도 도구 빌드 경고·오류0개입니다. 새 도구의 Windows 실기는 미검증인 미서명 개발판이며 실제 충전 제어는 계속 미지원입니다. 삼성 원본 바이너리·사용자 원문 보고서는 포함하지 않습니다.

SHA-256:

- 실행 ZIP: 5fb0dee6779294c21b4c64c5b8000a4672a65c64394795b51099379189c67f3a
- 소스 ZIP: 3b3cea3677f8181e1625894a2d20a413b77f949534ab4010f72af076c0bb1c13

아래는 이전 실행판과 관측 이력입니다. 새 파일은 별도 이름으로 제공하고 이전 ZIP은 보존합니다.

## 이전 WMI 응답 디코더 개발 소스

[최신 개발 소스 ZIP](ATIVBatteryGuard-WMI-REPLY-SOURCE.zip) · [구현과 추가 공개 근거](../ATIVBatteryGuard/WMI_REPLY_DECODER_AND_PUBLIC_EVIDENCE.md)

이번 변경은 API 미완료·응답 형식·배열 경계·길이·ACK를 구분하는 순수 응답 처리 코드입니다. 기존 bool 인터페이스를 유지하며 실제 OEM 호출이나 배터리 제어를 추가하지 않았습니다. 현재 모델의 배터리 조회 명령·실제 응답 계약은 여전히 미검증입니다.

전체 테스트244개 통과, Core·WPF·비교 도구 빌드 경고·오류0개입니다. 추가 공개 두 소스는 프레임 구조만 교차 확인했으며 드라이버 코드를 제품에 복사·실행하지 않았습니다. 소스 ZIP에는 실행 파일·원본 삼성 바이너리·사용자 원문 보고서가 없습니다. 같은 진단을 다시 실행할 필요는 없습니다.

소스 ZIP SHA-256: 3d09947e26109f84637fbe97822f28512812a0e42e9ede5d8b5b409dcd2f615d

기존 실행판과 관측 이력은 아래에 보존합니다.

## 이전 별도 WMI 권한 비교 도구 — 검토 준비판

**비교 결과 수신 완료:** 일반 토큰은 버전 속성(Active=True/version16)을 읽고 메서드 클래스 열거에서 0x80041003으로 거부됐습니다. 상승 토큰은 두 클래스의 속성을 읽었습니다. [결과와 해석 범위](../ATIVBatteryGuard/WMI_PERMISSION_COMPARISON_RESULT.md)에 기록했으며 같은 비교를 다시 요청하지 않습니다. 실제 충전 제어는 계속 미지원입니다. 기존 ZIP은 그 관측에 사용한 파일로 보존합니다.


**2026-11-03 승인 반영:** 사용자가 같은 Windows 계정에서 고정된 두 WMI 속성의 일반 권한/한 번의 관리자 권한 읽기 비교를 승인했습니다. [실행 순서](../ATIVBatteryGuard/WMI_PERMISSION_COMPARISON_RUN.md)를 따릅니다. 기존 ZIP을 그대로 사용하며 ZIP 내부의 승인 대기 표시는 패키징 시점의 기록입니다. 실제 결과는 아직 받지 않았습니다. 아래 보류 설명은 승인 전 이력입니다.

[별도 도구 ZIP](ATIVBatteryGuard-WMI-PERMISSION-REVIEW.zip) · [같은 버전 소스](ATIVBatteryGuard-WMI-PERMISSION-SOURCE.zip) · [범위·승인 조건](../ATIVBatteryGuard/WMI_PERMISSION_COMPARISON_REVIEW.md)

PacketPrivacy 적용 뒤에도 두 WMI 조회가 AccessDenied로 끝난 결과를 확인했습니다. 같은 TXT를 반복 요청하지 않고, 현재 토큰 상승 여부와 Connect/Query/Enumerate/ReadProperties 실패 단계를 확인할 별도 고정 조회 도구를 준비했습니다.

asInvoker 프로그램이며 자동 UAC·runas·메인 앱의 도구 실행이 없습니다. 메인 프로그램과 다른 로컬 폴더에 모두 압축 해제해 파일이 섞이지 않게 합니다. 관리자 비교 실행은 아직 승인받거나 수행하지 않았으므로 그 실행은 보류합니다. 같은 계정에서 한 번의 관리자 읽기 비교에 대한 별도 동의가 필요합니다.

두 고정 로컬 Active/version 속성만 읽으며 표준 출력뿐이고 임의 경로·쿼리·명령을 받지 않습니다. 사용자 이름·SID·장치 식별자·경로·원문 오류를 기록하지 않습니다. 서비스·드라이버·ACL·삼성 DLL·OEM·펌웨어 쓰기는 없으며 실제 충전 제어는 계속 미지원입니다.

현재 전체 테스트237개, 별도 배포 검증6개 통과, 메인 앱·Core·새 도구 빌드 경고·오류0개입니다. 미서명 개발 도구이며 Windows 실기·실제 토큰 API·관리자 비교는 미검증입니다. 삼성 원본 파일·사용자 TXT는 포함하지 않았습니다.

실행 ZIP SHA-256: e843210c5f79e0c8a130451e8586befcfd924e4afaa7ff1e7614d889bcaa72e8

이전 다운로드 파일은 아래에 그대로 보존합니다.

## 이전 WMI 암호화 연결·전송 경로 해석판

[실행 ZIP 다운로드](ATIVBatteryGuard-WMI-ACCESS-REVIEW.zip) · [같은 버전 소스 ZIP](ATIVBatteryGuard-WMI-ACCESS-SOURCE.zip) · [관측·수정 근거와 한계](../ATIVBatteryGuard/WMI_ACCESS_RESULT_AND_TRANSPORT_REVIEW.md)

기존 TXT에서 삼성 이름 후보 7개 Stopped/Manual, SABI NotFound, WMI 두 클래스 AccessDenied를 확인했습니다. 새 연결은 일반 사용자 권한으로 PacketPrivacy 암호화 인증을 명시합니다. 이 설정으로 노트북의 권한 거부가 해소되는지는 아직 미검증입니다. 관리자 권한·ACL 수정·드라이버 시작은 추가하지 않았습니다.

화면에 TXT 저장과 별개인 전송 경로 요약을 표시합니다. 순수 wsabi 요청 바이트 인코더도 준비했지만 실제 호출에는 연결하지 않았으며 충전 제어는 계속 미지원입니다. ZIP 전체를 새 폴더에 풀고 ATIVBatteryGuard.exe를 일반 권한으로 실행합니다. 같은 삼성 파일 정보 만들기에서 요약과 WMI 결과를 볼 수 있으며 이전 TXT·삼성 바이너리를 다시 제출할 필요는 없습니다.

테스트 228개·별도 배포 검증 6개 통과, WPF/XAML 빌드 경고·오류 0개. 미서명 개발판이며 새 Windows 연결·화면의 실기 동작은 아직 미검증입니다. 삼성 원본 DLL·EXE·사용자 원본 TXT는 포함하지 않습니다.

실행 ZIP SHA-256: e2cb5023c667549ac00e3fb9397d669c2cde938d0ad792a50345df75d8d6f8cc

이전 파일과 이력은 보존합니다.

## 이전 삼성 WMI 인스턴스·버전·활성 속성 확인판

[실행 ZIP 다운로드](ATIVBatteryGuard-WMI-INSTANCE-CHECK.zip) · [같은 버전 소스 ZIP](ATIVBatteryGuard-WMI-INSTANCE-SOURCE.zip) · [구현·확인 항목](../ATIVBatteryGuard/SAMSUNG_WMI_INSTANCE_INSPECTION.md)

ZIP 전체를 새 폴더에 풀고 ATIVBatteryGuard.exe를 일반 권한으로 실행합니다. 기존 삼성 파일 정보 만들기의 새 삼성 WMI 인스턴스 섹션에서 클래스별 조회 상태와 Active/version을 확인할 수 있습니다. Active=True는 배터리 보호 ON이 아니며 실제 충전 제어는 계속 미지원입니다.

이전 드라이버 확인판의 실제 노트북 실행과 TXT 생성은 확인됐습니다. 이번 WMI 조회의 실기 결과는 아직 미검증입니다. 앱 테스트 217개, 별도 배포 검증 6개 통과, WPF/XAML 빌드 경고·오류 0개입니다. 미서명 개발판이며 삼성 원본 DLL·EXE와 사용자 자료는 포함하지 않습니다. 기존 진단·TXT·삼성 바이너리의 재제출은 요구하지 않습니다.

파일 페이지에서 Download raw file로 내려받을 수 있습니다. 실행 ZIP SHA-256: 9c26bc1db4ac7ef77e7c3aaa8c759aa0c64f7008ae5b2a95062f33345ddfbfd5

이전 파일은 아래 이력과 함께 보존합니다.

## 이전 삼성/SABI 커널 드라이버 상태 확인판

[실행용 ZIP 다운로드](ATIVBatteryGuard-DRIVER-STATUS-CHECK.zip) · [같은 버전 소스 ZIP](ATIVBatteryGuard-DRIVER-STATUS-SOURCE.zip) · [구현·실기 확인 항목](../ATIVBatteryGuard/SAMSUNG_KERNEL_DRIVER_INSPECTION.md)

이 파일들은 채팅의 클라우드 로컬 경로 대신 GitHub 저장소에서 다운로드할 수 있습니다. ZIP 파일 페이지에서는 **Download raw file**을 선택합니다. 비공개 저장소라면 접근 가능한 GitHub 계정으로 로그인해야 합니다.

Windows 10 x64 / .NET Framework 4.8용 미서명 개발 미리보기입니다. 새 폴더에 ZIP 전체를 압축 해제하고 `ATIVBatteryGuard.exe`를 일반 권한으로 실행합니다. **삼성 파일 정보 만들기**에서 이름 후보의 등록·실행 상태·시작 방식과 SABI 연결 이름 비교를 확인합니다. 같은 진단·파일 목록·삼성 DLL의 재제출은 필요하지 않습니다.

정상 완료의 후보 미관측과 오류·권한 거부·시간 초과·일부 조회를 구분합니다. 후보 미관측을 드라이버 미설치로 단정하지 않으며 Running 관측도 실제 충전 제어를 활성화하지 않습니다. 실제 충전 제한은 계속 미지원입니다. 드라이버·서비스 변경·삼성 DLL 초기화·OEM 명령은 하지 않습니다.

검증 기록: 앱 테스트 204개 통과, 별도 배포 검증 테스트 6개 통과, WPF/XAML 빌드 경고·오류 0개. 새 Windows WMI 조회의 실기 동작은 아직 미검증입니다. 삼성 원본 DLL과 사용자 진단은 포함하지 않습니다.

SHA-256:

- 실행 ZIP: `cf7174470d50510085bb33b676fb193f6871c9bb0b9beb79011f0198a5a1c6b9`
- 소스 ZIP: `f02f79b4df6f560e31bac162cd0f3e375501e3cbb2b804d55907d236c678680b`

아래는 이전 배포 이력입니다. 새 확인판은 위의 고유 파일명을 사용하며 이전 ZIP은 보존합니다.

## 이전 Sabi3 x64 규약 수정·SABI 연결 확인판

[실행용 ZIP](ATIVBatteryGuard-SABI-LINK-CHECK.zip) · [같은 버전의 자체 소스](ATIVBatteryGuard-SOURCE.zip) · [정적 분석 기록](../ATIVBatteryGuard/SABI3_NATIVE_ABI_REVIEW.md)

제공받은 Sabi3.dll이 x64 파일임을 확인했습니다. 정적 분석에서 공개 예제의 4바이트와 다른 실제 11바이트 버퍼 접근을 확인해 관련 코드를 수정했습니다. 원본 DLL은 실행하거나 배포에 포함하지 않았습니다. x86 DLL은 이번 단계에 필요하지 않습니다.

새 실행판은 Windows의 SABI 연결 이름만 조회합니다. 삼성 DLL을 로드하거나 장치를 열거나 드라이버 명령을 보내지 않습니다. 연결 이름의 존재만으로 배터리 제어 지원을 판정하지 않으며, 실제 충전 제한은 계속 미지원입니다.

1. 이전 프로그램을 닫고 실행용 ZIP을 새 폴더에 모두 압축 해제합니다.
2. ATIVBatteryGuard.exe를 실행해 **삼성 파일 정보 만들기**를 누릅니다.
3. **정보 파일 위치 열기**에서 새 samsung-files-*.txt를 찾아 채팅에 첨부합니다. 이번에 확인할 항목은 **SABI 장치 연결 이름**입니다.

전체 소스 테스트 184개 통과, 실패·건너뜀 0개입니다. x64 net48 WPF/XAML 빌드와 실행 파일 정적 검사는 통과했으며 빌드 경고·오류는 0개입니다. 이번 SABI 이름 조회 기능은 실제 Windows에서 아직 시험하지 않았습니다.

SHA-256:

- 실행 ZIP: `e75e3b9cc386d804ff12c23da670dd6bbab7c41e8f7536d6506553b4908edf43`
- 소스 ZIP: `7458d5189c5ff6bb93a467dae8bd18d49aa6e425b4e39ee73a87dc50c78ec39d`

이전 배포본은 이력으로 보관합니다. 현재 실행판과 일치하는 소스는 위 ATIVBatteryGuard-SOURCE.zip입니다. 원본 삼성 파일·사용자 진단·외부 분석 자료는 저장소와 배포 ZIP에 포함하지 않습니다.
