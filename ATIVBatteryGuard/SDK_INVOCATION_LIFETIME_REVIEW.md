# SDK 호출 오류와 관련 작업 수명 계약 — 2026-11-07

**호출 결과의 오류와 관련 작업의 종료를 별도로 다루는 계약을 구체화했습니다.** 기존 정상 경로의 긍정 근거는 유지하고, SDK 오류 뒤 완료 알림을 반드시 받을 수 있다는 가정은 제외합니다. 실제 adapter·하드웨어 호출은 추가하지 않았으며 보호 설정 조회·충전 제어는 여전히 미구현·Unsupported입니다.

[이전 Bound 직접 실패 격리 수정](BOUND_TRANSPORT_FAILURE_QUARANTINE_UPDATE.md)의 후속입니다. 그 수정은 반환 Task 자체가 없는 직접 실패를 보존합니다. SDK 내부 오류가 이미 ordinary faulted Task가 된 경우의 실제 수명은 별도입니다. [정제 기록](reports/sdk-invocation-lifetime-audit.json)은 새 참조 텍스트·가짜 SDK 증명·이전 앱 검증을 구분합니다.

## 이미 있는 정상 경계와 새 참조 근거

기존 WindowsOneShotBackend의 정상 경로는 InvokeMethod의 정상 반환 뒤 선택 completion Task를 await합니다. 선택 snapshot이 먼저 준비돼도 SDK 호출이 돌아오기 전 성공 Task를 게시하지 않습니다. pending 중 취소 요청만으로 observer.Cancel을 호출하거나 그 Task를 끝내지도 않습니다. 이 정상 join을 다시 구현하기 위해 사용처 없는 Core/public 상태 모델을 추가하지 않았습니다.

새로 읽은 Microsoft dotnet/runtime v8.0.0의 ManagementObject 참조 소스는 선택 observer overload에서 sink 등록 → 하위 비동기 dispatch 호출 → 후속 처리/즉시 상태 검사 순서를 보입니다. 음수 상태 분기는 RemoveSink로 collection entry와 stub을 정리한 뒤 예외를 던집니다. 재사용한 observer/sink 소스의 Completed 전달은 SDK 호출의 정상 반환 여부를 기다리는 gate가 없습니다.

따라서 호출 함수 복귀와 final/capture를 독립 신호로 다룹니다. 같은 observer가 SDK throw 뒤에 나중 완료를 **반드시** 받을 수 있다고 가정하지 않습니다. sink 정리는 provider 중단 증거도, 모든 늦은 callback의 불가능 증거도 아닙니다. private helper가 사라진 완료 알림을 만들어 낼 수는 없습니다.

이것은 **현재 Windows10/.NET Framework4.8 구현 일치나 실제 노트북의 예외/호출 순서를 관측한 결과가 아닙니다.** callback-before-return과 callback 뒤 예외는 검토할 조건부 순서이며 conforming target에서 그런 immediate error가 실제 발생했다는 주장이 아닙니다. 후속 Reset 호출 위치만 확인했고 실제 throw 가능성은 입증하지 않았습니다. 정확한 Framework 원문 미확보를 별도 blocker로 되돌리지 않습니다.

## 종료 Task의 최소 계약

종료 근거는 다음 둘 중 하나입니다.

- SDK 호출 지점에 진입하지 않았음이 확인된 로컬 종료.
- **호출 스택 종료 AND 적용 가능한 method terminal AND 선택 snapshot 처리 settled.**

snapshot의 settled는 성공뿐 아니라 검증 실패·읽기 실패·불필요도 포함합니다. terminal도 출처와 계약상 관련 접근 종료를 설명하는 상태여야 하며, 클라이언트 취소로 생성된 알림을 임의로 포함하지 않습니다. 모든 callback·독립 Dispose·전체 EC effect의 종료를 요구하지 않습니다.

| 발생한 신호 | 진단과 수명 처리 |
| --- | --- |
| 확실한 pre-call 거부·취소 | 새 호출 없음. provider terminal 없이 로컬 종료 가능 |
| SDK 함수 정상 반환만 | method/capture 종료 근거를 더 기다림 |
| final/capture가 먼저 끝남 | SDK 호출 스택이 끝날 때까지 소유권 유지 |
| SDK throw, 관련 terminal 미관측 | 진단은 Unknown. 종료 Task는 pending |
| UI timeout·dispatch 이후 stop 요청 | UI 대기는 끝낼 수 있으나 관련 종료 근거로 쓰지 않음 |
| 관련 terminal 뒤 snapshot 처리 중 | 처음부터 미완료로 관리한 capture가 settled될 때까지 유지 |
| 관련 종료를 확인했지만 호출/출력 결과는 실패 | 수명 종료와 결과 실패를 함께 보존. 보호 값 성공으로 바꾸지 않음 |

final bit를 먼저 게시하고 나중에 snapshot 작업을 등록하는 빈틈을 두지 않습니다. no-dispatch·call exit·terminal·capture는 한 시도에 귀속되고 중복·늦은 신호로 다음 시도를 열지 않습니다. 오류 진단과 UI 반환을 소유권이 기다릴 종료 Task와 같은 의미로 만들지 않습니다.

## 가짜 SDK 검증과 한계

private .NET8 prototype는 가짜 호출·신호를 기존 Core owner/FrameExchange와 연결했습니다. **8개 case·48개 검산 통과**, 시험 프로젝트 Release 빌드 **경고0·오류0**, restore/build/run 종료코드는 모두0입니다. 변경하지 않은 Core93파일을 링크했고 package source를 clear한 package reference0 구성으로 실행했습니다. 우리 prototype와 .NET 개발 SDK를 실행했으며 실제 System.Management/WMI SDK·provider는 실행하지 않았습니다.

early final/late call exit, early exit/late final와 capture, unknown throw 뒤 timeout과 caller stop, early final 뒤 throw, capture 실패와 불필요한 capture의 명시 오류 완료, pre-stop/no-dispatch를 확인했습니다. unknown 두 case에서는 UI 반환 뒤에도 lease·slot이 유지되고 같은 channel peer가 Busy로 끝나 추가 호출하지 못하는 상태를 기록했습니다. 정리 때 owner thread의 해제1회와 모든 fake task join도 확인했습니다. 새 응답 frame·하드웨어 값은 만들지 않고 기존 synthetic 요청만 썼습니다.

실제 WMI/Global 객체·기존 단발 예약·삼성 원본은 사용하지 않았습니다. 공개 Core에 새 helper나 public protocol을 연결하지 않았으며 앱 전체 테스트·net48 솔루션 빌드는 반복하지 않았습니다. **앱469개·전체 빌드 경고/오류0은 이전fc14fea 기록**이고 이번 private48개를 합산하지 않습니다.

terminal이 오지 않으면 종료 Task·owner·lease·slot이 계속 남을 수 있습니다. 이는 완료를 꾸며내지 않는 정책의 실제 한계입니다. process 종료·OS lease 해제를 provider 정지로 해석하지 않으며, callback 소실을 해결했다고 보고하지 않습니다. 시험 정리용으로 나중에 공급하는 합성 종료 신호는 실제 SDK에서 그 신호를 얻을 수 있다는 증거가 아닙니다.

## 연결 판단과 다음 작업

기존 consumed backend를 그대로 새 owner에 연결하지 않습니다. 실제 adapter는 어떤 신호가 관련 작업 종료 근거인지와, 신호를 잃은 dispatch를 어떻게 불명 상태로 유지할지 명시해야 합니다. 지금은 그 계약을 private fake proof로 구체화하는 단계입니다. 동일 normal mapping·OEM 참여자·SDK 참조를 반복해 새 하드웨어 근거로 세지 않고, 실제 adapter의 다른 관측 계약이나 구체 반례가 있을 때만 다시 검토합니다.

[A/B 비실행 시험안](FIXED_MODE_READ_PROPOSAL.md)의 호출 수·gate 상태 영향·승인 상태는 그대로입니다. 원본 실행·로딩·에뮬레이션, 실제 WMI/OEM·하드웨어·사용 완료된 예약 접근, driver/service/security/firmware 변경은 없습니다. 새 노트북 실행이나 같은 자료 제출을 요구하지 않습니다.
