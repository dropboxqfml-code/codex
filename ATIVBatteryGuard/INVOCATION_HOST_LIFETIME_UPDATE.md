# 단발 호출의 결과 표시와 host 종료 대기 — 2026-11-07

**기존 세션을 끝까지 기다리는 실행 흐름을 구현했습니다.** `WsabiWmiInvocationSession.RunAndCloseAsync`는 제한 시간 안에 얻은 결과를 표시한 뒤에도 관련 정리가 끝나기 전에는 반환하지 않습니다. 시간 초과 결과를 출력한 직후 Main이 끝나 background owner와 잠금이 사라지는 사용을 피하기 위한 실제 소비 경로입니다. [이전 세션 구현](MANAGED_INVOCATION_SESSION_UPDATE.md)의 후속이며 새 수명 tracker를 만들지 않았습니다.

## 구현한 흐름

1. 결과 표시 callback의 null 여부를 호출 진입 전에 검증합니다. 잘못된 callback은 새 세션을 소비하거나 닫지 않습니다.
2. 기존 `ExchangeAsync`의 bounded 결과를 받습니다. 실제 호출 권한이나 응답 의미를 추가하지 않습니다.
3. `RequestCloseAsync`로 admission 차단과 stop 의도를 먼저 확정한 뒤 동기 callback에 결과를 한 번 전달합니다.
4. `finally`에서 같은 close Task를 기다립니다. 호출자의 취소 토큰이나 두 번째 제한 시간으로 이 대기를 취소하지 않습니다. 결과 표시가 예외를 던져도 정리 뒤에만 실행 Task가 실패합니다.

완료 불명이면 **결과는 표시되고 실행 Task는 pending**입니다. 나중에 정리가 끝나도 이미 표시한 시간 초과·취소 결과를 성공으로 바꾸지 않습니다. 반환 가능한 실패와 실제 진행 중인 관련 작업을 구분하며, 원문 SDK 예외·경로·식별자를 표시하는 기능은 없습니다.

host Main은 이 method를 한 번만 호출하고 반환 Task를 자신의 수명으로 기다려야 합니다. callback은 짧은 동기 표시용입니다. async void 작업·UI 자동 전환·예약된 화면 작업의 완료까지 추적하지 않습니다. 같은 세션에서 method를 다시 호출하면 Busy/Cancelled 결과가 그 호출에도 표시될 수 있으므로 전역 report-once 보장이 아닙니다. source별 단발 제한과 canonical 공유 정리는 기존 세션이 담당합니다.

## 콘솔과 창 종료 계약

콘솔 host의 Ctrl+C handler는 기본 종료를 막고 짧은 stop 신호만 남깁니다. Main의 정상 흐름이 취소와 close를 처리하며, handler는 그 대기가 끝난 뒤에 해제합니다. 두 번째 Ctrl+C를 강제 종료나 잠금 해제의 지름길로 사용하지 않습니다. 출력 실패도 close 대기를 거칩니다. 정상 종료코드가 생기는 시점은 정리 뒤이며 시간 초과 표시 시점과 다릅니다.

WPF에서는 첫 Closing을 보류하고 비동기로 close를 기다린 뒤 실제 창 닫기를 허용하는 방식이 필요합니다. UI thread에서 Wait/Result로 막지 않습니다. 현재 앱에 이 hook을 연결한 것은 아닙니다.

창 X·OS 로그오프/종료·강제 kill·crash·Environment.Exit/FailFast는 협력 종료 보장 밖입니다. ProcessExit를 처음 정리를 시작하는 barrier로 쓰거나 OS mutex 해제를 provider 중단 증거로 보지 않습니다. 이를 위해 서비스·보안·OS 종료 정책을 변경하지 않습니다. terminal이 오지 않으면 협력 종료도 무기한 pending일 수 있습니다.

## 실제 WMI source의 선택

저장된 SDK 참조와 기존 Backend를 비교해 **기존 비동기 Completed.Status 계약을 유지하는 방향**으로 좁혔습니다. 동기 typed-output overload는 정상 스택을 단순하게 만들 수 있지만 참조 구현이 비음수 즉시 상태를 출력하지 않습니다. 정상 반환을 임의로 원래 terminal status 0과 같다고 해석하는 변경은 하지 않습니다. 이것은 구현 선택이며 새 장치 관측이나 현재 Framework 구현의 실증이 아닙니다.

다음 source의 구체 책임은 다음과 같습니다.

- SDK 결과 객체는 source 안에서만 소유합니다. 단일 선택 결과만 형식 확인·bounded 분리·선택 정리를 거쳐 observer의 int status와 byte[] 또는 고정 capture 실패로 변환합니다. SDK/COM 객체·EventArgs/Context·지연 reader·원문 예외를 transport에 넘기지 않습니다.
- terminal status가 비영이면 출력 필드를 읽지 않습니다. 성공 통지도 결과 없음·여러 결과·형식/읽기 실패를 유효 보호 값으로 바꾸지 않습니다. 같은 terminal의 중복과 상충 상태를 구분하고 capture를 두 번 게시하지 않습니다.
- 선택 capture는 처음부터 미완료이며 terminal 뒤 reader/선택 정리가 끝난 다음 settle합니다. SDK 호출 스택이 아직 남아 있으면 transport가 계속 기다립니다. 독립 SDK cleanup이나 모든 EC 활동의 종료를 요구하는 뜻은 아닙니다.
- SDK throw만으로 terminal을 만들거나 callback을 복구했다고 하지 않습니다. Core callback bridge를 추가해도 SDK의 sink 제거를 막거나 소실된 완료를 만들어낼 수 없습니다. 확인되지 않은 완료는 pending으로 보존합니다.
- 준비·검증 실패는 가능한 한 SDK source 진입 전에 분류합니다. source 진입 뒤의 throw는 현재 인터페이스에서 미호출의 증명이 아닙니다. 실패를 임의 terminal로 바꾸거나 기존 consumed Backend를 그대로 연결하지 않습니다.

이번에는 실제 SDK source·event adapter·새 명령/프로파일/프레임을 추가하지 않았습니다. 위 출력 소유·선택·분리 코드를 준비한 뒤 실제 연결 범위를 별도로 검토합니다.

## 검증과 범위

새 회귀6개를 포함해 **전체490개 통과·실패0·skip0**, 전체 net48 솔루션 Release 빌드 **경고0·오류0**입니다. callback 진입 전 admission 차단, 로컬 거부/사전 취소, 완료 불명 뒤 시간 초과/반복 취소, 표시 예외와 막힌 lease 해제, Busy peer의 실제 owner 정리를 검증했습니다. source/gate/lease는 가짜이고 기존 synthetic 요청·응답만 사용했습니다.

독립 검토가 fake Returned 신호와 transport의 실제 call-exit 게시 사이에 있는 테스트의 타이밍 의존성을 찾았습니다. transport 상태를 명시적으로 기다리도록 테스트만 보강한 뒤490개를 다시 통과했습니다. 수명 종료 조건이나 소유권을 완화한 수정은 아닙니다.

private 콘솔 harness는 변경하지 않은 production Core96파일을 링크하고 이 method를 실제 Main에서 기다렸습니다. 시간 초과와 호출자 stop의 두 child 프로세스에서 결과가 먼저 표시되고 반복 stop 뒤에도 Main/잠금/source1회가 유지됨을 확인했습니다. 명시적 합성 terminal/capture 뒤에만 owner thread의 해제1회와 handler 해제·프로세스 종료를 관측했습니다. **48개 검산·child2개 join**, restore/build/run 종료코드0, 시험 build 경고/오류0입니다. 명시적 finish 소비를 확인하므로 EOF만으로 정리된 case는 통과하지 않으며 이전 pass 기록을 실패 때 재사용하지 않습니다. 앱490개에 합산하지 않습니다.

실제 OS Ctrl+C 신호는 보내지 않았습니다. handler 등록과 주입 신호 경로를 검토했으며 Win10 이벤트 전달·실제 SDK/provider 종료를 실증한 것이 아닙니다. 우리 .NET 개발 SDK와 fake 프로그램만 실행했고 강제 kill/Exit는 사용하지 않았습니다. [정제 기록](reports/invocation-host-lifetime-audit.json)은 앱 검증과 이 관찰을 분리합니다.

## 다음 작업

다음 구현은 선택 결과 객체의 소유·분리·정리를 담당할 callback source입니다. 실제 WMI 호출 전에는 그 adapter의 terminal 출처·소실·준비 실패와 단발 도구 Main의 연결을 검토합니다. A의 호출 상한1회·handshake0, B의 별도 handshake1회+조건부 읽기1회·최대2method·gate 상태 영향·승인 상태는 [기존 시험안](FIXED_MODE_READ_PROPOSAL.md)을 유지합니다. 현재 단일 교환을 두 세션으로 연속 호출해 B의 두 호출 사이 소유권을 대신하지 않습니다.

Core2파일(세션 method와 기존 주석), 테스트3파일, 문서·정제 기록을 변경했습니다. 실제 SDK/하드웨어·OEM Global 객체·사용 완료된 예약·삼성 원본에 접근하지 않았고 드라이버/서비스/보안/펌웨어·UI 등록·배포 ZIP도 변경하지 않았습니다. 배터리 보호 설정 조회·충전 제어는 미구현·Unsupported입니다. 새 노트북 실행이나 동일 자료 제출은 필요하지 않습니다.
