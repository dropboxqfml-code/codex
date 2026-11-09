# 고정7단계의 응답 대응·종료 인계 원형 — 2026-11-09 한국 시간

이번 구현은 **대역 source의 응답 판정과 실제 종료 약속을 전체 owner에 연결하는 internal 원형**입니다. 고정 역할·하나의 target 참조·단계별 자원의 로컬 대응을 검증합니다. firmware 주소를 고르거나 실제 WMI 요청을 만드는 adapter가 아니며, 새 SDK 호출·설정 명령·예약·App 연결은 없습니다. 충전 제어는 Unsupported입니다.

## 단계별 불변 대응

`WsabiWmiProtectionStageBinding`은 procedure·target과 단계별 source/input/observer/capture를 객체 참조로 보유합니다. 모든 단계는 같은 procedure와 target을 사용하되 각 단계 자원은 서로 달라야 합니다. 비교는 `ReferenceEquals`이며 device ID·경로·이름·객체의 사용자 정의 Equals를 사용하지 않습니다.

반환한 `WsabiWmiProtectionBoundReply`는 정확히 그 단계의 binding 참조를 포함해야 합니다. 정상 byte라도 다른 단계·procedure·target의 binding이면 거부합니다. 입력된 배열과 비교 내용은 복사해 보유하고,7개 단계의 비교8셀 tuple이 중복이면 시작 전에 거부합니다. 다른 단계의 응답을 같은 새 label로 재포장하거나 실제로 다른 주소를 사용한 공급자까지 이 검사로 인증할 수는 없습니다. 로컬 대응 검사와 firmware 대상·응답 신선도는 별개입니다.

coordinator의 원자적 일회용 claim에 operation/lifetime뿐 아니라 binding·source/input/observer/capture와 procedure 참조를 포함했습니다. 같은 자원을 새 wrapper와 lifetime으로 포장하거나, 같은 procedure로 새 자원을 구성해도 프로세스 내에서 재실행할 수 없습니다. target은 여러 독립 procedure에서 빌려 쓸 수 있는 대상이므로 소비하지 않습니다. 이 메모리 내 claim은 실기 영속 예약이나 새 호출 승인 예산이 아닙니다.

## 응답과 종료를 분리한 연결

BoundStage는 source의 Start를 owner thread에서 직접 한 번 호출합니다. direct throw나 null task를 async 예외로 감추지 않고 기존 coordinator의 종료 불명 경로에 전달합니다. 이후 응답 변환은 SDK 객체에 접근하지 않는 분리된 데이터만 검사합니다.

| source에서 인계할 종료 구성요소 | 원형의 수용 조건 |
| --- | --- |
| invocationEnd | 호출 stack·해당 terminal·capture·등록 join을 포함한 task의 정상 완료 |
| outputClose | handler·selected/related 출력·subscription 정리가 `Complete` |
| inputClose | 관련 입력 두 객체의 마지막 접근·정리가 `Complete` |

셋 모두 정상이어야 `ActualClose`를 확인합니다. 하나라도 `Failed`·`Unknown`·fault·cancel이면 즉시 불명 진단을 전달하고, 다른 구성요소가 끝나도 성공으로 바꾸지 않습니다. 표시 timeout·중단은 이 join을 대신하지 못하며, 뒤 단계도 진행하지 않습니다. 미래 SDK adapter는 task가 완료됐다는 이유만으로 cleanup 결과의 `Failed`를 지워서는 안 됩니다.

이 task들은 source가 제공한 수명 계약이며 원형이 독립적으로 측정한 Windows 종료 증거가 아닙니다. 대역 teardown의 명시적 `ConfirmActualClose`는 시험 자원이 모두 끝났다는 새 fake 근거입니다. 실제 SDK 복구·재시도 기능이나 정리 실패를 무시하는 실행 경로를 추가하지 않았습니다.

실제 source는 **Start 이전에 SDK 자원이나 작업이 없어야 합니다.** 원형의7개 준비 handle은 객체 참조와 비교 기대값뿐입니다.7개 SDK observer를 미리 등록하거나 입력을 미리 만들면 중단 뒤 미시작 단계의 정리가 빠질 수 있습니다. 실제 구현은 각 Start 안에서 lazy 준비하거나, 사용하지 않은 준비 자원까지 lease 해제 전 join하는 procedure barrier를 명시해야 합니다.

## receipt 뒤의 독립 readback

새 adapter는 읽기 후보를 `BoundReadCandidate`, 정상 설정 형식을 `SetterReceiptAcceptedForReadback`으로 분리해 순수 전환 모델에 전달합니다. 기존 raw 판정기 자체는 여전히 현재 관측을 자동 생성하지 않습니다. 이 바인딩 원형도 `AcceptedCurrentRead`나 legacy `SetterAcknowledged`를 만들어 내지 않습니다.

모델 snapshot의 `SetterReceiptAccepted`와 `BoundReadCandidateCount`는 각각 receipt 수용과 순수 모델이 수용한 숫자 단계 수입니다. setter 실행·저장 변화·실제 하드웨어 읽기 횟수가 아닙니다. 새 정상7단계 결과는 receipt=true, legacy ACK=false, bound 후보6이며 모든 하드웨어 권한·충전 성공 표시는false입니다.

정상receipt가 먼저 도착해도 관련 실제 close 전에는 사후 모드·상한·하한 읽기를 시작하지 않습니다. close 뒤에만 독립 readback을 검토합니다. 사전 모드0, 사후1/80/75, 첫 실패·모호함에서 중단하는 조건은 유지합니다. setter 성공 코드를 새 필수조건으로 만들지 않으면서도 ACK/echo를 저장 상태로 오인하지 않는 전이입니다.

## 실제 SDK에 적용할 지점

기존 [InvocationSnapshotTransport](src/ATIVBatteryGuard.Core/Services/WsabiWmiInvocationSnapshotTransport.cs)는 worker/source 호출 stack, applicable terminal, capture settle, token registration과 publication 후 `InvocationCompletion`을 연결합니다. [WindowsCallbackSource](src/ATIVBatteryGuard.WmiInterop/WsabiWmiWindowsCallbackSource.cs)는 handler·출력 정리와 unsubscribe 상태를 보존하고, [OwnedInputPair](src/ATIVBatteryGuard.WmiInterop/WsabiWmiWindowsOwnedInputPair.cs)는 두 입력의 정리 결과를 합칩니다. 이 가운데 하나만 끝났다고 전체 종료로 표시하지 않습니다. 내부 `CallCanceled`의 기존 비종료 분류도 유지합니다.

[InvocationSession](src/ATIVBatteryGuard.Core/Services/WsabiWmiInvocationSession.cs)은 자체 per-frame owner를 만듭니다. 이를7개 반복하거나 외부 owner로 감싸지 않습니다. 실제 adapter에 필요한 것은 gate를 획득하지 않는 일회용 SDK leaf이며, frozen request와 같은 target/observer/input bundle을 고정한 뒤 분리된 결과와 위 종료 합성을 전체 coordinator에 인계해야 합니다. 그 실제 leaf와 고정 요청의 구현은 이번 변경에 포함하지 않았습니다.

## 검증·다음 작업

새 테스트는 바인딩·자원 재포장·비교 중복·잘못 라우팅된 정상 응답·세 종료 구성요소의 순서·정리 실패와 pending·receipt 이후 단계 전이·중단 뒤 늦은 결과를 가짜 source로 검사합니다. 수명 불명의 영구 보유와 source가 잘못된 종료 약속을 제공할 수 있다는 경계는 그대로 남깁니다. 새 Windows/SDK/firmware 관측이나 충전 제어 성공은 없습니다. 최종 수치와 source pin은 [정제 검증](reports/bound-stage-handoff-validation.json)에 기록합니다.

기존 gate 획득 자체의 throw/null·lease 해제 예외에서 영구 보유하는 분기는 여전히 소스 검토 범위이며, 회수할 실제 종료 근거가 없는 그 분기를 프로세스 내 실행 회귀로 검증했다고 주장하지 않습니다.

새 전이6개·바인딩12개를 포함해 **804통과·0실패·0skip**, portable와 전체 net48 참조 Release 빌드는 각각0경고·0오류입니다. 반복 조합을 별도 테스트나 firmware 분석률로 합산하지 않았습니다. 독립 소스·테스트 검토를 수행했고 실제 Windows/.NET48 런타임 실행은 하지 않았습니다.

다음은 고정 대상·요청 기대값을 위 SDK leaf에 인계하는 구체 구현안을 정하고, 실제 설정용 코드·도구와 사용자 시험의 별도 명시 승인 범위를 제시하는 작업입니다. 동결된 firmware/selector 검색을 반복하거나 모든 writer 부재·새 live hash를 조건으로 추가하지 않습니다. 기존 A·Access1·Query65 소모 상태와 marker 접근·삭제·초기화·재사용 금지는 유지합니다. 현재 추가 노트북 실행·자료 재제출·새 GUI ZIP은 필요 없습니다.
