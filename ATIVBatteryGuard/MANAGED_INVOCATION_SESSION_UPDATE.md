# 공통 호출 세션과 닫기 경계 구현 — 2026-11-07

**후속:** [host 종료 대기 구현](INVOCATION_HOST_LIFETIME_UPDATE.md)에서 bounded 결과를 먼저 표시하고 close까지 기다리는 RunAndCloseAsync 소비 흐름을 추가했습니다. 새6개 포함490회귀·전체 빌드 경고/오류0이며 실제 SDK source·GUI 연결은 아직 없습니다. 아래는 당시 세션 구현 기록입니다.

**시험도구가 사용할 공통 관리 세션을 구현하고, 같은 코드에 가짜 호출 원본을 주입해 검증했습니다.** private 상태 모델만 두던 단계에서 기존 Bound/owner/FrameExchange가 소비하는 snapshot transport와 세션으로 옮겼습니다. 실제 System.Management source·OEM method·장치 profile·새 하드웨어 frame은 연결하지 않았으며 실제 보호 조회·충전 제어는 Unsupported입니다.

[이전 SDK 수명 증명](SDK_INVOCATION_LIFETIME_REVIEW.md)의 후속입니다. [정제 기록](reports/managed-invocation-session-audit.json)에 구현 파일·테스트·빌드·한계를 남겼습니다.

## 실제로 추가한 소비 경로

`InvocationSession → FrameExchange → cooperative owner → Bound → InvocationSnapshotTransport → 명시적으로 공급한 source`

source 인터페이스는 준비된 호출1회와 observer만 받습니다. 기본 SDK 구현·삼성 DLL 로딩·커널 접근·앱 등록은 없습니다. 소프트웨어의 source.Invoke 단발 제한은 실제 SDK 내부의 method 횟수·모델 적합성·권한을 인증하지 않습니다. 실제 source 구현은 별도 검토해야 합니다.

transport는 추적한 worker에서 Invoke를 수행하고 즉시 수명 Task를 돌려줍니다. 호출 스택 종료, 적용 가능한 method terminal, 선택 capture settled를 함께 기다리며 worker와 token registration 정리 뒤에만 그 Task가 끝납니다. 관련 terminal을 관측하지 못한 source의 직접 throw는 고정된 완료 불명 진단으로 남고, 정상 반환 뒤 terminal을 받지 못한 채 stop을 요청한 경우도 완료 불명으로 표시하며, terminal이 없으면 Task는 pending입니다. stop·UI timeout·닫기 요청은 종료 신호를 만들어 내지 않습니다.

같은 source 참조를 감싼 transport들은 단발 상태와 identity를 공유합니다. 새 래퍼로 다시 시작하거나 이전 snapshot을 재전달하지 않습니다. 다른 source 객체·직접 호출·모든 물리 endpoint alias까지 보호한다는 뜻은 아닙니다.

## 데이터와 통지 계약

- terminal은 int 상태만, capture는 이미 분리된 byte[] 또는 고정 실패 통지만 받습니다. SDK/COM 객체·EventArgs/Context·원문 예외·임의 getter/reader는 받지 않습니다.
- capture는 처음부터 unsettled입니다. terminal 전에 capture를 끝내거나 중복 capture·상충 terminal 통지가 오면 고정 오류를 기록하며, 그 오류만으로 Task를 조기 종료하지 않습니다. 필요한 종료 근거가 모두 도착해야 합니다.
- terminal status가 최종 ApiResult의 기준입니다. 비영 상태에서는 전달된 byte 배열을 조회·보유하지 않고 output 없는 snapshot을 만듭니다.
- 성공 상태의 배열은 최대4096바이트 보유 상한 안에서 복사하고 앱 소유의 고정 read-only map을 만듭니다. 상한은 decoder 허용 길이와 다릅니다. oversized·null을 자르거나 보정하지 않고 capture 실패로 끝냅니다. 짧은 배열도 정상 응답으로 padding하지 않습니다.
- 동일 terminal 중복은 false로 거부하며 첫 상태를 유지합니다. 상충 terminal·중복 capture는 결과 게시 전 실패로 남깁니다. 게시 뒤 통지로 결과를 바꾸거나 다음 호출을 열지 않습니다.

observer의 사실은 공급자 계약입니다. 이 계층이 실제 SDK 종료·현재 펌웨어 identity·샘플 신선함을 스스로 인증하지 않습니다. client 취소로 만들어진 알림을 관련 method terminal이라고 보고해서도 안 됩니다. 실제 source가 선택 capture 접근을 끝낸 뒤 통지해야 하며 모든 독립 SDK cleanup·EC effect 종료를 요구하는 것은 아닙니다.

## 닫기와 공유 자원

Session은 시작과 닫기를 같은 lock으로 정렬합니다. `RequestCloseAsync`는 새 시작을 막고 stop 의도를 보낸 뒤 다음을 모두 기다립니다.

1. source의 관련 작업 Task와 token/worker 정리.
2. 자기 FrameExchange의 owner·취소·lease·slot 정리.
3. 같은 canonical source를 쓰는 이미 승인된 시도의 공유 정리 barrier.

admission과 해당 정리 barrier는 한 번에 게시됩니다. 닫기가 먼저면 새 admission을 거부하고, 기존 admission이 먼저면 그 정리를 기다립니다. transport가 끝났어도 실제 owner의 lease.Dispose가 막혀 있다면 같은 source의 peer 세션도 CloseReady가 되지 않습니다.

이 경계를 확인하는 추가 회귀는 수정 전 **482통과·1실패/483개**, 수정 뒤 **483통과·0실패·0skip**입니다. 이후 정상 반환했지만 terminal을 받지 못한 호출도 stop 뒤 완료 불명으로 표시하도록 진단을 보강했습니다. 그 회귀는483통과1실패/484개로 재현한 뒤 수정했습니다. 수명/lease는 원래도 pending이었으며 진단 분류만 바로잡았습니다. 닫기 뒤 admission 차단과 quarantine은 남을 수 있으므로 Busy=true 자체를 provider 진행 중으로, Busy=false를 종료 증명으로 사용하지 않습니다.

`IsCloseReady`는 이 managed 세션과 알려진 source 범위의 추적 자원에 대한 사실입니다. 실제 GUI close/ProcessExit hook은 연결하지 않았습니다. 미래 host는 bounded UI 결과 대신 RequestCloseAsync를 기다려야 합니다. terminal이 영원히 없으면 닫기도 pending이며, 강제 process 종료·OS mutex 해제를 provider 중단으로 해석하지 않습니다.

## 검증

새 회귀15개는 source별 단발·출력 복사, early final/blocked Invoke, 늦은 capture, unknown 뒤 timeout/caller cancel·close, final 뒤 throw, 통지 순서/중복, terminal 상태 우선·보유 cap·짧은 출력, source alias 차단, 자기/peer의 막힌 lease 해제를 검증합니다. 모두 같은 새 세션/transport 코드를 사용하며 source/gate/lease는 가짜이고 기존 synthetic 요청·응답 fixture만 재사용합니다.

이전469개에15개를 추가해 **전체484개 통과**, 전체 net48 솔루션 Release 빌드는 **경고0·오류0**입니다. 별도 private8case/48검산이나 데이터 경계 관찰 수를 합산하지 않았습니다. 기존 SDK/cache와 IL task 설정을 사용했고 새 dependency·SDK 패치·XAML 단계 생략은 없습니다.

## 제공 범위와 다음 단계

Core6파일·테스트3파일과 문서/정제 기록을 변경했습니다. 실제 source·SDK 호출·UI 등록·old OneShot backend/Program/예약·encoder·배포 ZIP은 그대로입니다. 전체 빌드는 우리 EXE를 컴파일했으며 실행하지 않았습니다. 회귀는 우리 코드와 가짜 전송, 기존 unnamed mutex 범위이며 OEM Global 객체는 열지 않았습니다.

다음은 이 세션을 사용할 단발 조회 도구의 구체적인 source/host 계약과 A/B 중 단일 시험안을 확정하는 작업입니다. 선택한 실제 호출 source가 terminal의 출처·소실·capture 종료를 어떻게 보고할지, host가 닫기를 어떻게 기다릴지 검토해야 합니다. 기존 SDK backend를 그대로 연결하거나 이번 fake 통과를 실기 준비 완료로 승격하지 않습니다.

[A/B 시험안](FIXED_MODE_READ_PROPOSAL.md)의 method 상한·gate 상태 영향·승인 상태는 유지합니다. 삼성 원본 실행·로딩·에뮬레이션, 실제 WMI/OEM/hardware/소모 예약 접근, driver/service/security/firmware 변경은 없습니다. 새 노트북 실행이나 동일 자료 제출은 필요하지 않습니다.
