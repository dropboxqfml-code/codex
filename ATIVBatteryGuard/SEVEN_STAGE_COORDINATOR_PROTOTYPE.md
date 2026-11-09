# 보호 전환의 고정 명세와 전체 소유권 원형 — 2026-11-08

**최신 후속 — 2026-11-09 한국 시간:** [단계별 응답·종료 인계](BOUND_STAGE_HANDOFF_PROTOTYPE.md)를 대역으로 연결했습니다. 자원·procedure claim을 보강하고 receipt와 legacy ACK를 분리하며804회귀·두 Release 빌드0경고·0오류를 확인했습니다. 실제 SDK leaf와 고정 요청은 아직 없습니다.

**2026-11-09 한국 시간 후속:** [조회·설정 응답의 순수 분류](PROTECTION_REPLY_CONTRACTS.md)를 구현해786회귀·두 Release 빌드0경고·0오류를 확인했습니다. 읽기의 입력echo 겹침과 설정 `ReceiptOnly`를 구분하며 현재 관측·전환 입력으로 자동 승격하지 않습니다. 이 원형과 실제 SDK의 연결은 여전히 남았습니다.

이번 개발은 **순수 판정 모델과 internal coordinator의 대역 검증**입니다. SDK adapter, 설정 명령 인코딩, 새 예약, 프로그램 진입점은 추가하지 않았습니다. 실제 노트북의 새 관측이나 설정 변경은 없으며 충전 제어는 Unsupported입니다.

## 고정 판정 순서

`WsabiWmiProtectionTransitionReview`는 아래 순서를 한 번만 수용합니다. 예상값과 관측값은 별도 불변 snapshot에 보존합니다.

| 순서 | 필요한 관측 | 불일치 시 동작 |
| --- | --- | --- |
| 1 | 이번 사전 모드 후보0 | 나머지 단계 중단, 설정 역할0회 |
| 2–3 | 이번 사전 상한·하한의 byte 후보 | 불명·거부·범위 오류이면 중단 |
| 4 | 의미상 설정1 역할의 ACK | 실패·불명에서 중단. ACK를 저장값으로 취급하지 않음 |
| 5–7 | 이번 사후 모드1·상한80·하한75 | 첫 불일치에서 중단, 추가 변경 없음 |

사전 임계값은0..255의 비교 기준이며 이미80/75여야 한다는 조건을 두지 않습니다. 사전 상한보다 하한이 커도 유효 byte 관측으로 보존합니다. 값이 실제 정책에 적합하다고 인증하는 모델은 아닙니다. 과거 Access1의 후보0은 `HistoricalRead`이며 새 사전 읽기로 수용하지 않습니다.

`AcceptedCurrentRead`는 공급자가 정규화해 전달할 분류입니다. 숫자 모델은 과거 값을 현재 값이라고 잘못 붙인 입력을 구별하거나 응답의 생성 시점을 입증하지 못합니다. 실제 요청·응답 귀속 검증은 향후 고정 adapter의 책임입니다. 현재 모델에는 실제 결과로부터 이 분류를 만드는 adapter가 없습니다.

## 한 번의 owner와 실제 종료

`WsabiWmiSevenStageCoordinator`와 operation·lifetime·stop view는 모두 internal입니다. 현재 참조자는 대역 테스트뿐이며, App·WmiInterop·기존 단발 도구에서 호출하지 않습니다. 입력은 역할·숫자 관측·가짜 수명이며 명령·주소·frame·nonce가 없습니다.

전용 owner thread가 gate를 한 번 획득하고, 같은 thread에서 각 역할을 시작하며, 마지막 관련 정리 후 같은 thread에서 lease를 해제합니다. 각 역할의 **결과와 실제 종료를 둘 다** 확인한 뒤 다음 역할을 검토합니다. 이전 per-frame owner를 중첩하지 않습니다. 이는 향후 같은 협력 경로의 요청 사이를 보호할 구조이며 EC 정책 전체를 동결하거나 모든 writer를 통제한다는 뜻이 아닙니다.

한 coordinator는 single-use이고, 같은 operation 또는 lifetime을 다른 coordinator로 감싸도 프로세스 내에서 다시 소비할 수 없습니다. 역할 입장과 중단 판정은 같은 lock 아래에서 결정합니다. 입장 뒤 중단이 도착하면 이미 입장한 역할은 읽기 전용 stop view로 이를 관찰하며, 후속 역할은 시작하지 않습니다. `StartedStages`와 `SetterRoleStarted`는 역할 입장 기록으로서 실제 method 호출 수가 아닙니다.

표시 deadline은 전체 절차에 한 번 적용하고 실제 종료와 분리합니다. 시간 초과·사용자 중단은 늦은 성공으로 취소되지 않습니다. `RunAsync`의 표시 결과만 기다린 host는 실제 종료를 보장받지 못합니다. 향후 host는 `RunAndCloseAsync` 또는 `RequestCloseAsync`/`ActualCompletion`을 반드시 join해야 합니다. 결과 표시 callback이 예외를 던져도 join하며, 동시 실행의 `AlreadyUsed` 패자는 진행 중인 승자를 중단하지 않습니다.

숫자 비교가 모두 일치한 뒤 마지막 lease 해제에서 deadline이 지나도 전체 결과는 `TimedOut`입니다. 이때 snapshot의 숫자 판정이 일치일 수 있지만 outcome을 성공으로 승격하지 않으며, 실제 종료는 해제 완료까지 pending입니다. 이 경계도 가짜 lease를 지연하는 별도 회귀로 확인합니다.

`ActualClose`의 계약은 Start 호출 stack, 작업자, 입력 접근, 출력 복사와 관련 정리를 모두 포함합니다. 이 task가 끝난 뒤 도착하는 결과는 보호 대상에 접근하지 않는 분리된 숫자 데이터여야 합니다. 결과가 먼저 오면 실제 close까지 보유하고, 실제 close가 먼저 왔는데 결과가 사라졌다면 중단 뒤 결과를 추가로 기다리지 않고 정리를 마칠 수 있습니다.

## 불명·실패 처리와 검증 한계

실패한 결과라도 실제 close가 입증되면 후속 역할 없이 정상 정리가 가능합니다. 반면 Start throw/null이나 close 진단 실패는 실제 종료 증거가 아닙니다. 표시 결과를 정제해 반환해도 owner와 수명은 보유합니다. `ReportUncertainClose`는 진단 신호이며 `ActualClose`를 완료하지 않습니다. 테스트의 명시적 fake close는 합성 대역 증거로서 실제 SDK 복구 절차가 아닙니다. 새 적용 가능한 실제 종료 근거가 없다면 pending입니다.

gate 획득 자체의 throw/null은 소유권을 알 수 없고, lease 해제 예외도 안전한 해제를 입증하지 못합니다. 이 경로는 격리 상태와 owner를 영구 보유하며 완료를 꾸미지 않습니다. 복구 근거를 주입하는 실행 API가 없으므로 이번 프로세스 내 자동 테스트에서는 영구 대기 경로를 실행하지 않았고 소스로 독립 검토했습니다. 명시적인 gate 거부·abandoned 소유권 반환은 대역으로 검증합니다. owner thread 시작 전 로컬 준비 실패는 소스 시작0회가 확실하므로 로컬 종료합니다.

대역 회귀는 고정 순서·사전 조건·단계별 거부, 결과와 close의 앞뒤 순서, stop/deadline 후 후속0, 같은 thread의 해제, 동시 실행·별도 peer 경합, 결과 표시 예외와 수명 alias를 확인합니다. 이는 Windows/.NET48 런타임·SDK·OEM·펌웨어·실제 충전기의 동작 시험이 아닙니다. 최종 상태가 `StoredReadbackMatchedCandidate`여도 저장 후보 비교의 대역 결과이며 전기적 충전 제한 성공이 아닙니다. 모든 하드웨어 실행 권한은 false입니다.

## 다음 개발 경계

현재 root 검증은 새 순수 모델15개·coordinator17개를 포함해 **759통과·0실패·0skip**입니다. 단계별 parameter 반복은 별도 테스트 수로 합산하지 않았습니다. Portable와 전체 net48 참조 Release 빌드는 각각0경고·0오류입니다. 독립 소스 검토에서 발견한 mutable stop 노출과 owner 시작 전 준비 실패 정리를 보완한 뒤 통과했습니다. 실제 Windows 런타임 실행은 하지 않았습니다. 정제 검증 기록은 [reports/seven-stage-coordinator-validation.json](reports/seven-stage-coordinator-validation.json)입니다.

1. 저장된 근거로 두 임계값의 고정 읽기 응답 명세를 정합니다. 새 selector 탐색이나 원본 재수집을 반복하지 않습니다.
2. 의미상 설정1의 입력·응답 계약을 읽기 응답과 구별합니다. ACK/echo가 저장 모드나 임계값을 대신하지 못하게 합니다.
3. 실제 SDK 단계와 위 owner를 연결할 구체 설계에서 요청·응답 귀속, 입력 보호와 실제 종료 인계를 검토합니다. 현재 원형을 실제 호출 준비 완료로 표시하지 않습니다.
4. 중요한 미완료를 닫은 구체 시험안을 바탕으로 실제 설정용 코드·도구·별도 사용자 시험의 명시 승인 범위를 제시합니다. 현 단계의 실제 쓰기 예산은0입니다.

기존 A·Access1·Query65의 소모 예약은 그대로 유지하며 조회·삭제·초기화·재사용하지 않습니다. 새 노트북 실행이나 자료 재제출은 필요 없습니다. App 변경이 없어 새 실행 ZIP은 만들지 않았고, 기존 배포 ZIP은 당시 byte로 보존했습니다. 이전 배포 Core.dll과 이번 소스 재빌드의 byte 동일성을 주장하지 않습니다.
