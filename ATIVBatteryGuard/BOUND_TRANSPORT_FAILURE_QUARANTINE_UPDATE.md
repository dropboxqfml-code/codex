# 비동기 래퍼의 직접 호출 실패 격리 수정 — 2026-11-07

**후속:** [SDK 호출 수명 계약과 private 증명](SDK_INVOCATION_LIFETIME_REVIEW.md)에서 이미 반환된 Task 안의 SDK 오류를 구분했습니다. 앱 코드 변경 없이 private8case/48검산으로 unknown 진단과 실제-end를 분리했으며, 아래469개는 이 코드 수정의 검증 기록입니다.

**Bound 래퍼를 거치면 사라지던 협력 owner의 재진입 차단을 수정했습니다.** supplied snapshot transport가 직접 예외를 던지거나 Task를 반환하지 않은 경우, 같은 전송 자원과 협력 gate를 격리합니다. 새 하드웨어 호출·실제 backend·배터리 명령은 추가하지 않았으며 실제 보호 조회·충전 제어는 Unsupported입니다.

[이전 WMI·ACPI 반환/EC 재사용 검토](WMI_ACPI_RETURN_AND_EC_REUSE_REVIEW.md)의 후속입니다. 실제 SDK 오류의 완료 여부를 임의로 판정하는 대신, 현재 소프트웨어 안에서 이미 있는 정책이 래퍼 때문에 빠지는 지점을 고쳤습니다. [정제 검증 기록](reports/bound-transport-quarantine-audit.json)에 코드·테스트·빌드와 정적 검토를 구분합니다.

## 문제와 변경

기존 cooperative owner는 channel이 직접 throw하거나 null Task를 돌려주면 재사용을 차단합니다. 그러나 async인 BoundFrameChannel은 snapshot transport의 같은 실패를 자신의 faulted/cancelled Task로 변환합니다. owner는 이를 일반적인 반환 Task의 종료로 처리해, 같은 transport를 새 Bound 래퍼로 감싸거나 같은 gate에 다른 자원을 연결했을 때 재진입을 허용했습니다.

Bound는 **transport 호출 자체**의 throw와 null Task만 내부 고정 표식으로 보존합니다. 직접 OperationCanceledException도 포함합니다. owner는 이 표식을 취소 분류보다 먼저 처리해 canonical resource와 gate 양쪽을 sticky quarantine합니다. 기존 동일 thread의 lease 해제1회와 해제 뒤 결과 게시 순서는 유지합니다. 표식은 원래 예외·InnerException·provider의 오류 문자열을 보관하지 않습니다. 새 public API나 reset 기능은 없습니다.

| 결과 경계 | 변경 뒤 정책 |
| --- | --- |
| transport가 직접 throw·직접 취소 예외·null Task 반환 | cooperative owner가 resource와 gate를 격리. 같은 identity의 새 래퍼·plain peer·gate peer는 다시 호출하지 못함 |
| 실제로 반환한 Task의 fault/cancel | 기존 완료 계약 아래 정상 정리. 이번 표식으로 바꾸지 않음 |
| 완료 뒤 null snapshot·출력 구조 오류 | 기존 결과 오류 처리 유지. 결과가 잘못됐다는 이유만으로 격리하지 않음 |
| transport 진입 전 로컬 검증 거부·선행 취소 | snapshot transport 호출 없음. 이번 격리 대상이 아님 |
| 직접 호출이 막혀 있는 동안 caller가 중단한 뒤 직접 예외 발생 | caller stop이 격리 표식을 숨기지 않음. 기존 UI 중단 우선순위는 유지 |

try/catch 범위에 await·후속 token 검사·decode를 포함하지 않았습니다. bare Bound/noncooperative FrameExchange의 기존 transport-failure 후 재사용 의미도 바꾸지 않았습니다. 격리는 opt-in cooperative 경계와 알려진 canonical identity 범위이며 직접 transport 호출이나 임의 alias 전체를 막는 기능은 아닙니다.

## 실제 완료와의 구분

이 수정은 **기존 보수적인 직접 실패 정책의 전파**입니다. 공급자가 계약을 위반한 뒤 계속하는 실제 작업을 강제로 중단하거나, OS lease 해제로 provider가 멈췄음을 보장하지 않습니다. 반환된 Task가 fault/cancel일 때 실제 관련 작업이 끝나야 한다는 하위 계약은 그대로입니다.

특히 기존 WindowsOneShotBackend의 SDK 내부 예외가 이미 ordinary faulted Task로 바뀌는 문제는 이 표식으로 새로 식별되지 않습니다. 그 backend를 그대로 새 owner에 연결하지 않습니다. 실제 adapter는 미게시·관련 완료·불명 dispatch를 구분하고 관련 참여자의 전체 교환·EC admission 조건을 지켜야 합니다. 정상 WMI→AML 반환의 이미 동결한 모델 가정을 다시 전체 SDK drain·모든 IRQ 탐색 요구로 바꾸지 않습니다.

## 알려진 OEM 참여자의 보호 범위

저장된 WSABI 원본4개의 정상 Call은 같은 협력 객체를 획득한 뒤 입력 준비부터 method와 응답 복사까지 보호합니다. 이는 재사용한 기존 근거이며 현재 설치·실행·잠금 상태를 관측한 것은 아닙니다. 알려진 ModuleSABI prelude/query도 각각의 Call 단위입니다. 그 두 호출 사이에 연속 잠금이 유지된다고 새로 입증하지 않았습니다.

이번에는 **선택한 문자열 할당 실패1개**의 예외 경계를 추가로 대조했습니다. 저장된 기본 오류 handler가 throw하는 조건에서, 해당 Call 함수 자체의 완전한 unwind action에는 BSTR/메모리 정리만 있고 mutex 해제 guard는 없습니다. 이전 WMI 열거는 진행될 수 있지만 이 선택 실패는 OEM method 호출 전이며 부분 OEM/EC 실행·공유 프레임 손상 증거가 아닙니다. 상위 catch/수동 해제나 모든 예외는 감사하지 않았으며 현재 lock 보유·abandon 발생을 단정하지 않습니다. 정상 전체 교환 구간의 긍정 근거를 취소하는 것도 아닙니다.

native SABI 경로는 별도 mutex/버퍼 규약이고 같은 WMI host 프레임을 쓰는 관계가 미확정입니다. Runtime 후크의 확인된 공유 범위는 downstream EC selector/command이며 Windows WMI 프레임·Global 협력 참여를 뜻하지 않습니다. 전체 외부 writer의 부재를 새 조건으로 추가하지 않고 관련 자원별 참여 범위를 유지합니다. OEM의 예외·해제 처리를 그대로 안전한 owner 구현으로 복사하지 않습니다.

이 정적 검산은 관계1개를 뒷받침하는 선택134개와 이전 일반 구간12개·identity8개를 구분합니다. 앱 회귀469개에 합산하거나 새로운 참여자134개로 세지 않습니다. 원본 해시·선택 함수의 metadata/정리 closure는 private cache에서만 데이터로 검산했습니다.

## 회귀와 빌드

가짜 transport/gate와 기존 synthetic fixture만 사용하는 검사6개를 추가했습니다.

- 직접 throw·null Task·직접 취소 예외의 세 경우에서 wrapper 뒤에도 격리가 유지됨.
- 실제 반환된 fault/cancel Task와 null snapshot은 정상 정리 후 재사용됨.
- 로컬 거부·선행 취소는 snapshot transport를 부르지 않고 자원을 격리하지 않음.
- 막힌 직접 호출 중 caller stop이 발생해도 뒤의 직접 취소 예외를 숨기지 않음.

같은 transport의 새 Bound/plain peer와 같은 gate의 다른 자원은 차단되고 독립 자원·gate는 진행합니다. owner thread의 lease 해제1회도 확인합니다.

새 검사를 변경 전 코드에 실행한 결과 **465통과·4실패/469개**, 수정 뒤 **469통과·0실패·0skip**입니다. 전체 net48 솔루션 Release 빌드는 **경고0·오류0**입니다. 기존 SDK의 IL task 경로 설정과 기존 NuGet cache를 사용했고 dependency 추가·SDK 패치·XAML 단계 생략은 없습니다.

## 제공 범위

Core3파일과 테스트1파일, 문서·정제 기록을 변경했습니다. 앱 등록·UI·encoder·기존 단발 backend/Program/예약·실제 조회 정책·배포 ZIP은 그대로입니다. 전체 빌드는 EXE를 컴파일했으며 실행하지 않았습니다. portable 회귀는 우리 테스트와 가짜 전송, 기존 unnamed mutex 검사 범위이고 OEM Global 객체는 열지 않았습니다.

실제 WMI/OEM·하드웨어·사용 완료된 예약 접근, 삼성 원본 실행·로딩·에뮬레이션, driver/service/security/firmware 변경은 없습니다. 새 주소·frame·표식 값·하드웨어 generator·실기 backend도 만들지 않았습니다. [기본 A와 비실행 대안 B](FIXED_MODE_READ_PROPOSAL.md)의 호출 수·상태 영향·승인 상태는 유지합니다. 새 노트북 실행이나 동일 자료 제출은 필요하지 않습니다.
