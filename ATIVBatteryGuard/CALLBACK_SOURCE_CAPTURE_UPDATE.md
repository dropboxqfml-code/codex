# 결과 객체의 선택·복사·정리 연결 — 2026-11-07

**결과 객체를 기존 세션에 전달하는 callback source를 구현했습니다.** `WsabiWmiCallbackInvocationSource<T>`는 명시적으로 공급한 dispatch와 reader를 받아 객체 선택·bounded byte 복사·정리를 담당합니다. [host 종료 대기 구현](INVOCATION_HOST_LIFETIME_UPDATE.md)의 다음 단계이며 실제 System.Management 구현·WMI/OEM 호출·모델/명령/프레임은 추가하지 않았습니다. 실제 보호 설정 조회와 충전 제어는 Unsupported입니다.

## 연결한 경로

`RunAndCloseAsync → Session/FrameExchange → cooperative owner → Bound → InvocationSnapshotTransport → CallbackInvocationSource<T> → supplied dispatch`

dispatch는 준비된 요청과 객체/terminal callback을 받고, reader는 선택된 T에서 byte[]를 반환합니다. 두 의존성은 필수이며 생성 자체는 dispatch나 reader를 실행하지 않습니다. source 직접 Invoke도 인스턴스당 한 번만 허용하고 새 transport 래퍼가 결과를 재전달하지 않습니다. 이것은 supplied delegate 호출 수의 제한이지 delegate 내부 SDK method 횟수·장치 적합성·실행 권한의 인증이 아닙니다.

T는 class/IDisposable이며 객체 callback은 그 객체의 소유권을 source에 넘깁니다. 실제 SDK 타입·CIM property 형식 확인은 미래의 Windows reader가 담당합니다. 이번 generic source가 SDK 객체 구조를 자동 인증하는 것은 아닙니다. source는 reader의 byte view가 복사 중 안정적이라는 계약 아래 null/4096 초과를 거부하고, 선택 Dispose **전에** 자기 배열로 복사합니다. Dispose가 원래 배열을 변경해도 전달 배열은 보존됩니다. transport도 기존 보유 상한과 복사·decoder 계약을 유지합니다. 짧은 배열은 padding하지 않고 긴 배열은 자르지 않습니다.

## 선택과 정리

- 첫 terminal이 선택 window를 닫습니다. 그 전 객체 통지는 null·같은 객체의 반복까지 개수에 포함하며 정확히 한 개의 비null T와 첫 terminal의 성공 상태일 때만 reader를 최대 한 번 호출합니다. 이후 객체는 후보값을 바꾸거나 reader를 다시 호출하지 않습니다.
- 첫 T는 중복 통지가 와도 terminal까지 보유합니다. 나머지 객체의 정리는 lock 안에서 먼저 등록하고 lock 밖에서 실행합니다. 선택 reader/Dispose와 결과 게시 claim 전에 등록한 정리가 끝날 때까지 capture를 settle하지 않습니다.
- 같은 객체가 reader/Dispose 도중 재진입해도 동시에 Dispose하지 않습니다. 약한 reference identity 기록으로 정리가 끝난 뒤 다시 전달된 같은 T도 Dispose 시도를 반복하지 않습니다. T의 Equals/GetHashCode/ToString을 호출하지 않으며 모든 과거 객체를 강한 참조로 보유하지 않습니다. 이 source 밖의 정리나 native 자원 소멸까지 보장하는 것은 아닙니다.
- 첫 terminal을 observer에 전달한 뒤에만 capture를 게시할 수 있습니다. 같은 terminal 중복은 상태를 바꾸지 않고, 결과 게시 전 관측된 상충 terminal은 고정 실패로 남깁니다. 이미 게시된 결과를 늦은 통지로 철회하거나 다음 시도를 열지 않습니다.
- 첫 terminal이 비영이면 reader를 호출하지 않고 출력 없는 상태를 유지합니다. reader의 예외·null/oversize·관련 Dispose 예외는 원문/InnerException 없이 고정 capture 실패로 정리합니다. Dispose가 throw로 끝난 것은 모든 native 부수 효과가 끝났다는 인증이 아닙니다.

최종 claim은 `terminalForwarded AND selectedWorkEnded AND pendingDisposals == 0`을 같은 lock에서 확인합니다. 정리 중 terminal이 재진입해도 동기로 자신을 기다리지 않으며 마지막 정리가 끝난 경로가 게시를 이어받습니다. dispatch·reader·Dispose·observer 통지는 source lock 밖에서 실행합니다.

## 늦은 callback과 완료 불명의 한계

**내부 capture-publication claim 뒤의 새 객체는 독립적인 로컬 정리만 필요해야 한다는 supplied-dispatch 계약**이 있습니다. claim 전에는 terminal 뒤 도착한 객체의 등록된 정리도 기다립니다. claim 뒤에는 늦은 객체를 정리하지만 과거 lifetime을 다시 열지 않습니다. 이 경계는 실제 observer의 SettleCapture 반환 시점과 다르며 SDK의 미래 callback 부재·모든 COM cleanup·provider 종료를 증명하지 않습니다. 실제 adapter는 늦은 객체 정리가 관련 공유 입력/응답에 다시 접근하지 않는 조건을 검토해야 합니다.

dispatch throw는 원문을 버린 고정 호출 실패로 transport에 전달합니다. catch/finally에서 선택 객체나 callback 상태를 임의로 닫지 않습니다. terminal이 없으면 source는 선택 객체를 보유하고 transport/owner/lease/host close는 기존처럼 Unknown/pending입니다. terminal을 확인한 뒤 dispatch가 throw하면 관련 수명 종료와 결과 실패를 함께 보존합니다. callback 보유만으로 SDK가 제거한 sink나 소실된 terminal을 복구하지 않습니다.

source 입력·observer의 null 검증은 단발 진입 전에 수행합니다. 실제 SDK 준비 실패는 가능한 한 세션 시작 전에 분류해야 하며 source 진입 뒤 예외를 미호출이나 임의 terminal code로 바꾸지 않습니다. 이 코드는 COM thread/apartment 적합성·실제 terminal 출처·모든 물리 alias·persistent 예약을 새로 인증하지 않습니다.

## 검증

기본9개와 수명6개, **새 회귀15개 포함 전체505개 통과·실패0·skip0**입니다. 전체 net48 솔루션 Release 빌드는 **경고0·오류0**입니다. 같은 production source/transport/session/host 코드에 가짜 객체·dispatch·reader·gate를 공급하고 기존 synthetic 요청·응답 fixture를 재사용했습니다.

복사 뒤 원본 변경, 0/null/중복/복수 결과, nonzero reader0회, reader/Dispose 실패, cap과 decoder 길이 구분, 같은 T의 재진입·후속 중복, terminal-before-object와 동시 상충 전달 순서를 검증했습니다. 수명 회귀는 source.Invoke의 실제 종료를 완료 불명 상태로 확인한 뒤 **독립 callback Task**에서 reader/Dispose를 막습니다. 기존 call-exit 대기만으로 새 정리 join을 검증한 것으로 세지 않습니다. terminal 뒤·claim 전 late Dispose와 duplicate Dispose 안의 terminal 재진입도 host/lease가 유지됨을 확인했습니다.

unknown 뒤 timeout/caller stop은 먼저 표시되지만 가짜 terminal을 명시적으로 공급하기 전에는 close가 끝나지 않습니다. 테스트의 합성 정리는 실제 SDK의 늦은 완료 보장이 아닙니다. 모든 테스트 gate와 callback Task를 finally에서 정리했습니다. 이전 private 콘솔48검산/child2나 SDK8case/48검산을 앱505개에 합산하지 않았습니다.

[정제 기록](reports/callback-source-capture-audit.json)에 변경 파일 hash·검증 결과·범위를 남겼습니다. 새 SDK 원문·실기 사실·펌웨어 분석률을 추가한 작업이 아닙니다.

## 다음 작업과 제공 범위

다음은 실제 SDK 타입의 outData/Bytes 형식 검사·복사를 담당하는 Windows reader와 이벤트 연결 경계를 준비하는 작업입니다. 실제 연결 전 terminal의 적용성·신호 소실·준비 실패와 late 정리의 독립성을 확인해야 합니다. 기존 consumed Backend를 그대로 재연결하거나 현재 fake 통과를 실기 승인으로 바꾸지 않습니다. [A/B 시험안](FIXED_MODE_READ_PROPOSAL.md)의 호출 수·gate 상태 영향·승인 상태는 그대로입니다.

Core 새1파일·테스트4파일(새2/등록/프로젝트), 문서·정제 기록을 변경했습니다. 앱 UI/기본 backend·기존 SDK Backend/Program·encoder·사용 완료된 예약·배포 ZIP은 그대로입니다. 실제 WMI/OEM/하드웨어/Global 객체·삼성 원본에 접근하지 않았고 드라이버/서비스/보안/펌웨어·클라우드 환경을 변경하지 않았습니다. 새 노트북 실행이나 동일 자료 제출은 필요하지 않습니다.
