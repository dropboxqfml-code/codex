# 세션 시작 전 WMI 등록 준비 분리 — 2026-11-08 한국 시간

**이벤트 등록 실패를 Core 호출의 Unknown으로 넘기던 정상 준비 경로를 분리했습니다.** 새 `WsabiWmiWindowsPreparation.PrepareAsync`가 등록과 필요한 실패 정리를 먼저 끝내고, 성공한 경우에만 `WsabiWmiWindowsPreparedInvocation`을 반환합니다. 기존 raw source는 internal로 바꿔 public 사용자가 준비를 건너뛰어 세션에 넣지 못하게 했습니다. [Windows 타입·이벤트 연결](WINDOWS_WMI_TYPED_BINDING_UPDATE.md)의 후속이며 실제 OEM 호출·앱 등록·보호 조회·충전 제어는 추가하지 않았습니다.

## 준비와 실행의 경계

factory는 observer/dispatch/binder/gate/timeout을 검증한 뒤 전용 observer를 한 번 소유하고 등록을 준비합니다. 이미 취소된 요청은 등록이나 observer claim을 시작하지 않습니다. 등록과 정리는 외부 caller 및 자체 lock 밖에서 실행합니다. `+=` 시도를 호출 전에 기록하므로 handler를 설치한 뒤 throw하는 경우에도 해당 `-=`를 시도합니다. 진행 중인 add가 끝나기 전에 정리하고 나중에 handler가 다시 남는 순서를 허용하지 않습니다.

결과는 다음 순서로 분류합니다. 이 값은 로컬 준비 상태이며 provider terminal이 아닙니다.

| 상태 | 의미 |
| --- | --- |
| Ready | 등록 준비 완료. 단발 handle 반환. 하드웨어 지원/권한/조회 성공은 아님 |
| Cancelled | 준비 commit 전에 관측한 취소. 실행 객체 없음 |
| ObserverUnavailable | 이미 다른 단발 binding에 소유된 observer. 재등록하지 않음 |
| RegistrationFailed | 등록 시도 오류. 정리 시도를 끝낸 뒤 실행 객체 없이 반환 |
| UnexpectedCallback | 준비·미사용 단계의 이벤트로 등록 신뢰 조건 위반. 다음 조회에 replay하지 않음 |
| CleanupFailed | 등록 해제 또는 준비 중 인수한 객체의 취득/정리 실패. 다른 준비 실패·취소보다 우선 보존 |

동시 원인의 우선순위는 CleanupFailed → RegistrationFailed → UnexpectedCallback → Cancelled → Ready입니다. 정상 Ready commit과 취소가 경쟁하면 commit에서 관측한 취소가 Ready보다 우선합니다. token은 준비 단계에서만 poll하며 취소 callback으로 SDK 정리를 실행하지 않습니다. Ready 뒤에는 준비 token이 등록 해제 권한을 갖지 않으며 실제 실행 token은 별도입니다.

비Ready 상태 결정과 primary callback 입장 차단도 같은 lock에서 게시합니다. 독립 검토에서 분류 뒤 입장 차단 전 callback이 들어오면 이전 Cancelled 분류를 그대로 반환할 수 있는 경합을 찾아 이 경계를 보강했습니다. 차단 전 이미 입장한 early callback은 취소보다 우선하며 차단 뒤 객체는 독립 로컬 정리 범위입니다. runtime 실패를 재현한 기록으로 세지 않고 코드 검토와 우선순위 회귀로 확인했습니다.

준비 중 이벤트는 현재 호출의 출력/terminal이 아닙니다. 객체는 metadata/bytes reader 없이 canonical root의 로컬 정리로 보내고, Completed는 Status/Context/StatusObject를 읽어 과거 상태를 다음 조회에 붙이지 않습니다. 이미 입장한 관련 getter/Dispose와 등록·해제 시도가 끝날 때까지 준비 실패/미사용 닫기가 기다립니다. 로컬 작업이 막히면 준비 Task도 pending일 수 있으며 강제 timeout이나 가짜 종료로 정리를 생략하지 않습니다. CleanupFailed면 실제 handler 제거 성공을 뜻하지 않고 같은 observer는 재사용할 수 없습니다.

## 성공 handle의 수명

public handle만 `RunAndCloseAsync`와 `RequestCloseAsync`를 제공합니다. Run과 미사용 닫기를 같은 lock에서 한 번 결정합니다. 닫기가 먼저면 Core 세션을 만들지 않고 로컬 등록만 정리합니다. Run이 먼저면 source의 준비 상태를 다시 확인하고 Core 세션을 생성·게시한 뒤 lock 밖에서 기존 RunAndCloseAsync를 소비합니다. 닫기가 세션 게시 사이의 빈틈을 보고 조기 완료하지 않습니다. raw source나 session을 외부에 꺼내지 않습니다.

invalid request·실행 전 취소·gate 거부로 source.Invoke가 호출되지 않아도, Core 정리가 끝난 다음 미사용 구독을 정리합니다. 결과 표시 예외도 그 정리 뒤에만 밖으로 나옵니다. 해제 실패가 있으면 close는 Failed를 반환하고 실행 Task도 고정 오류로 실패합니다. 같은 close Task를 공유하며 재실행·자동 재등록·다른 observer fallback은 없습니다.

실제 source.Invoke/dispatch에 진입한 경우는 기존 경계를 유지합니다. handle은 먼저 Core의 source/owner/lease 정리를 기다리고, Unknown에서는 임의 unsubscribe·새 terminal·강제 완료를 만들지 않습니다. 준비 성공 후 Run 예약 전에 외부 이벤트가 오면 준비를 무효화해 세션 없이 거부할 수 있습니다. **Run 예약 이후 실제 Invoke 전의 외부 이벤트 위반까지 Session0으로 확장하지 않습니다.** 이때 Core에 들어온 실패는 여전히 Unknown/pending일 수 있습니다. dedicated observer 계약이나 공급된 dispatch의 실제 SDK method 수를 상태 머신이 인증하지 않습니다.

## 검증

factory9개·수명6개, **새 회귀15개 포함 전체541개 통과·실패0·skip0**입니다. 먼저 새 기본9개 포함535개가 통과했고 수명6개 통합·실패 시 finally join 및 분류/입장 cutoff 보강 뒤541개를 다시 통과했습니다. 기존 binding12개는 등록을 명시적으로 준비·예약한 후 호출하도록 적응했으며 신규 수에 합산하지 않았습니다.

before-add/after-mutation throw, 진행 중 add 취소, cleanup 실패 우선순위, early object/status의 미사용·비재생, 막힌 early Dispose, Ready 무효화, unused close, 정상 실행과 별도 준비 token, 요청/권한 gate 거부, Run/Close 경합, Unknown 뒤 timeout/caller stop과 보고 예외를 검증했습니다. prepare failure의 null handle·gate/dispatch0은 runtime 관측이며 Core 세션 생성0은 factory/handle API와 생성 위치의 별도 코드 근거입니다. 의미 없는 미연결 observer 카운터를 provider 종료 증거로 쓰지 않습니다.

같은 production Windows 소스4파일을 테스트 전용 SDK stand-in과 컴파일했습니다. fake에 mutate-then-throw를 위한 AfterAdd를 추가했고 모든 제어 gate·실행 callback Task를 정리했습니다. Unknown 정리에 넣은 합성 SDK terminal은 실제 늦은 완료 보장이 아닙니다. **실제 Framework4.8 참조 전체 Release 빌드는 경고0·오류0**이며 실제 SDK/provider/COM을 실행한 검증이 아닙니다. 기존 SDK/cache와 IL task 설정을 사용했고 새 설치·패키지 버전·SDK 패치·XAML 생략은 없습니다. 이전 private 검산 수는 앱541개에 합산하지 않습니다.

[정제 기록](reports/windows-wmi-preparation-audit.json)에 source/test hash·실행 결과·남은 한계를 기록했습니다. Core의 provider 종료/NoDispatch protocol을 바꾸거나 미확인 하드웨어 근거를 추가한 작업은 아닙니다.

## 다음 작업과 제공 범위

다음은 검토할 단발 조회안의 대상·호출 상한·준비 조건과 이 prepared 실행 경로를 대응시키는 일입니다. 실제 SDK event/getter/COM threading·cutoff 뒤 객체 정리의 독립성·실행 승인은 별도입니다. [A/B 시험안](FIXED_MODE_READ_PROPOSAL.md)의 횟수·gate 상태 영향·승인 상태와 사용 완료된 과거 예약은 유지합니다. old SDK Backend를 재연결하거나 새 호출/프레임을 생성하지 않았습니다.

Windows 소스2파일·테스트6파일(새2/기존binding·fake/등록·프로젝트)과 문서/정제 기록을 변경했습니다. Core·앱 UI/기본 backend·old Program/encoder/예약·배포 ZIP은 그대로입니다. 실제 WMI/OEM/하드웨어/Global 객체·삼성 원본에 접근하거나 드라이버/서비스/보안/펌웨어·클라우드 환경을 변경하지 않았습니다. 새 노트북 실행이나 동일 자료 제출은 필요하지 않습니다.
