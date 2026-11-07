# 다음 개발 재개 메모

## 최신 — SDK 호출 수명 계약과 private 증명 / 2026-11-07

[SDK_INVOCATION_LIFETIME_REVIEW.md](SDK_INVOCATION_LIFETIME_REVIEW.md), [판정](FIXED_MODE_READ_DECISION.md), [시험안](FIXED_MODE_READ_PROPOSAL.md)을 먼저 읽습니다. 기존 Backend의 정상 경로는 이미 SDK 정상 반환과 선택 completion을 함께 기다립니다. 사용처 없는 Core/public tracker를 추가하는 대신, 불명 오류 진단과 소유권이 기다릴 종료 Task를 분리하는 private prototype를 만들었습니다.

최소 종료 조건은 확실한 SDK 미진입, 또는 call stack 종료 AND 적용 가능한 method terminal AND 선택 snapshot 처리 settled입니다. capture는 처음부터 unsettled로 두어 final 게시와 reader 등록 사이에 빈틈이 없게 합니다. 선택 처리 실패·불필요도 settled가 될 수 있습니다. SDK throw·UI stop·timeout은 그 자체로 terminal이 아닙니다. final 뒤 throw가 발생하면 이미 확인한 종료 근거와 결과 실패를 함께 보존합니다. 모든 callback·독립 Dispose·전체 EC effect 종료를 요구하지 않습니다.

private .NET8 harness는 변경하지 않은 Core93파일을 링크했습니다.8개 joined case·48개 assertion 통과, 시험 빌드 경고/오류0, restore/build/run 종료코드0입니다. early final/late call, early call/late final+capture, unknown throw와 timeout/caller stop, final 뒤 throw, capture 실패/알려진 오류의 불필요 capture, pre-stop를 검산했습니다. unknown 두 case는 UI 반환 뒤 lease/slot 유지와 peer Busy를 기록했습니다. 그 뒤 finally에서 합성 terminal/capture를 공급해 모든 fake Task를 join했습니다. 이 cleanup은 실제 SDK의 늦은 완료 보장이 아닙니다. 강제 종료·실제 SDK·WMI/OEM/Global 객체는 사용하지 않았습니다.

새 공식 ManagementObject(v8.0.0) 원문1개는 observer 등록→하위 dispatch→후속 처리/status와 negative HR→RemoveSink→ReleaseStub→throw를 보입니다. 재사용 observer는 SDK 정상 반환 gate 없이 Completed를 전달합니다. 정상 Backend는 호출 다음 await를 거치지만 SDK throw는 그 await를 건너뜁니다. 새 관계1개에 대한 text check17·재사용13·source pin6을 구분했습니다. 조기 callback/callback 뒤 throw는 조건부 source 순서이며 conforming target의 실제 발생·현재.NET48 동일성·Reset의 실제 throw 근거는 아닙니다. 정확한 Framework 원문 미확보를 독립 blocker로 추가하지 않습니다.

같은 observer가 throw 뒤 terminal을 반드시 받을 수 있는 것은 아닙니다. 신호가 없으면 helper도 pending이고 owner thread·lease·slot이 무기한 남을 수 있습니다. 제거나 process 종료를 provider stop으로 바꾸지 않고 기존 단발 backend를 그대로 연결하지 않습니다. 실제 adapter는 terminal의 출처와 소실 시 소유권·프로세스 수명 정책을 구체화해야 합니다. 같은 SDK/normal mapping/참여자 검색은 반복하지 않으며 다른 실제 관측 계약이나 구체 반례가 있을 때 재개합니다.

private cache는 20261107/invocation-lifetime-proof-next, sdk-dispatch-phase-boundary-next, invocation-lifetime-contract-next, invocation-lifetime-feasibility-next입니다. proof 폴더에 own4파일/Core93 pins, proof.private.json, root-execution-record, final source/artifact pins와 restore/build/run 로그를 보존했습니다. 초기 agent 준비 기록은 유지하고 실제 root 실행 기록을 별도로 남겼습니다. root는 명시한 CLI home·telemetry opt-out, source clear/package reference0, no-restore build로 .NET 개발 SDK와 우리 prototype를 실행했습니다. 실제 System.Management/provider는 실행하지 않았습니다.

공개 변경은 문서·정제 기록뿐이며 앱/Core/public API·기존 tests/EXE/ZIP은 그대로입니다. 전체 suite/net48 solution 빌드는 반복하지 않았습니다. 앱469개·전체 빌드0은fc14fea 기록이며 private48개를 합산하지 않습니다. 실제 WMI/OEM/hardware/소모 예약 접근·삼성 원본 실행/로딩/에뮬레이션·driver/service/security/firmware 변경은 없습니다. A/B의 호출 수·gate 영향·승인 상태를 유지하며 실제 제어는 Unsupported입니다. 새 실행이나 동일 자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — Bound 전송 직접 실패 격리 코드 수정 / 2026-11-07

[BOUND_TRANSPORT_FAILURE_QUARANTINE_UPDATE.md](BOUND_TRANSPORT_FAILURE_QUARANTINE_UPDATE.md), [판정](FIXED_MODE_READ_DECISION.md), [시험안](FIXED_MODE_READ_PROPOSAL.md)을 먼저 읽습니다. 기존 cooperative owner는 직접 channel throw/null만 격리했는데 async Bound가 lower snapshot transport의 같은 실패를 ordinary faulted/cancelled Task로 감춰 wrapper별 정책이 달랐습니다. transport 호출 자체만 내부 fixed-text marker로 보존하고 owner가 취소 분류 전에 canonical resource+gate를 sticky quarantine하도록 Core3파일을 수정했습니다. 원본 예외/InnerException/detail은 보관하지 않습니다. await·후속 token검사·null snapshot/decode·이미 반환된 task fault/cancel은 기존 완료 의미를 유지하며 plain/unowned 경계까지 전역 격리하지 않습니다.

테스트1파일에6개 등록을 추가했습니다. direct throw/null/direct OCE3개는 peer wrapper/plain/gate 차단·독립자원진행·동일 thread release1회를 검증합니다. 반환된 fault/cancel/null snapshot 대조1개, local reject/precancel no-call1개, blocked direct invocation 중 stop 뒤 OCE1개가 추가됐습니다. 실제 baseline465pass4fail/469total, 수정 뒤469pass0fail0skip입니다. 전체 net48 Release 빌드 경고0/오류0도 현재 완료했습니다. 기존 SDK8.0.427·기존cache·R2R IL 설정·no-restore·UseSharedCompilation=false·m1이며 새 dependency/SDK패치/XAMLskip없음입니다.

격리는 기존 직접 실패의 보수정책 전파이며 untracked provider를 종료하거나 외부 전체를 보호하지 않습니다. 특히 old WindowsOneShotBackend 내부 SDK 예외가 이미 ordinary async fault가 된 경우에는 새 marker가 생기지 않습니다. 실제 adapter가 미게시/관련 완료/불명 dispatch를 구분해야 하는 조건은 유지하며 old backend를 그대로 연결하지 않습니다. lease 해제나 프로세스 종료를 provider 정지로 간주하지 않습니다.

알려진 WSABI4개의 정상 acquire→입력준비→method→응답copy→release는 이전 문맥입니다. 새 정적 관계1개는 소유 이후 선택 BSTR 할당 실패가 saved default handler로 throw할 때 해당 함수의 unwind closure에 mutex guard가 없다는 것입니다. 선택134개/재사용normal12/identity8을 구분합니다. 실패는 OEM method 전이며 이전 WMI 열거는 가능하지만 부분 OEM/EC 실행·프레임훼손 증거가 아니며 상위catch/모든예외/currentruntime참여/actualabandon을 확정하지 않습니다. ModuleSABI의 두 lower Call을 연속 잠금으로 묶었다고 하지 않습니다. native는 같은WMIhostframe미확정, Runtime은downstreamEC wire공유이며 모두Global협력참여로합치지않습니다.

다음은 실제 adapter의 불명 SDK dispatch·관련 마지막 접근을 보존하는 계약과 관련 실제 참여 범위를 고정하는 작업입니다. 정상 WMI→AML 반환은 기존 모델 가정 아래 동결하며 같은원문/404/GUID검색을 반복하지 않습니다. A=최대1read/handshake0, B=별도비실행handshake1+조건부read1/최대2calls/상태영향명시라는 범위와 승인 상태는 유지합니다. 새 public outcomeprotocol/실기 backend/frame/tag값/하드웨어 generator/승인질문은 없습니다.

private cache: 20261107/bound-dispatch-quarantine-fix(baseline/after json·logs,solution-build.log), known-wmi-participant-scope-next, uncertain-outcome-contract-review-next, uncertain-outcome-feasibility-next. 공개 변경은 Core3+tests1+문서/정제기록이며 앱등록/UI/encoder/oldOneShot backend/Program/예약·배포ZIP은 그대로입니다. portable tests는우리코드/가짜전송과기존unnamedmutex이며OEMGlobal을열지않았습니다. WMI/OEM/하드웨어/소모예약 접근·삼성원본실행/로딩/에뮬레이션·driver/service/security/firmware 변경없음입니다. 실제제어Unsupported·새노트북실행/동일자료제출불필요입니다. 아래는 이전 기록입니다.

## 최신 — WMI·ACPI 정상 반환과 EC 재사용 계약 / 2026-11-07

[WMI_ACPI_RETURN_AND_EC_REUSE_REVIEW.md](WMI_ACPI_RETURN_AND_EC_REUSE_REVIEW.md), [시험안](FIXED_MODE_READ_PROPOSAL.md), [판정](FIXED_MODE_READ_DECISION.md)을 먼저 읽습니다. Microsoft 공식 Wmiacpi mapper 역할·WMI IRP method 입출력·ACPI 평가 계약을 저장 모델의 metadata/선언/AML과 대응했습니다. 정상 mapper의 object/method 선택·인수·반환 buffer 대응을 가정으로 명시하고 정상 평가/반환은 조건부 연결됨으로 동결합니다. exact WMxx/Arg2 규격의 공식 원문은 미확보지만 이것만을 독립 blocker로 두지 않습니다. 동일404·GUID·metadata 검색을 반복하지 않고 새 원문/provider 코드·관련 trace·구체 반례가 있을 때만 다시 엽니다.

EC source outcome은 미게시/게시 후 zero/게시 후 wait 오류로 분리합니다. 첫 준비 실패는 upload/post0이므로 새 요청 drain을 요구하지 않지만 두 번째 wait가 오류를 가려 stale가 나올 수 있습니다. 정상 reader는 입력 소비·결과 쓰기 후 dispatcher clear로 반환하며, reader 전 clear는 조회를 폐기할 수 있습니다. 게시 후 wait 오류는 종료 증거가 아니지만 다음 동일 규약 sender도 zero 전에는 upload/post0이므로 입력 재사용을 지연·실패시킬 근거가 있습니다. 모든 EC effect 종료/모든 status·IRQ 생산자 발견을 추가하지 않습니다. 실제 관련 외부 참여자의 규약 준수·사전 대상 무결성은 별도입니다. 새 source edge 발견은0이며 기존 source 재대조를 coverage로 세지 않습니다.

source의 gate/준비 실패는 그 branch에서 EC 게시0이나 외부 FF/ACK만으로 실제 branch를 식별할 수 없습니다. 새로 만든 관측 classifier가 없고, 불명 응답을 ProvenNotPosted로 승격하지 않습니다. 기존 backend의 로컬 dispatch 예약은 SDK call 전에 설정되므로 실제 call 증거가 아니며 SDK 예외도 async faulted Task가 될 수 있습니다. 실제 adapter는 SDK 전 미게시·정상 관련 완료·불명 dispatch를 구분해야 하고 관리 drain counter/기존 owner만으로 이를 만들 수 없습니다. old backend/실기 예약은 변경·접근하지 않습니다.

기본 A는 최대1WMI 읽기·고정 대상 샘플0~1·handshake0입니다. 새 B는 사전선택하는 별도 비실행 비교: gate handshake1→API/응답 검증 후 조건부 고정read1, 최대2WMI/샘플0~1/실패·불명시read0입니다. handshake는EChelper0이지만 공유 image-data gate에 열린 값을 쓰고 후속 generic 기능에도 영향을 주며 복원/지속시간은미관측입니다. B는아무상태변경없는조회가 아니고 두 호출·사이의 관련 소유권/마지막접근을 검토해야 합니다. DLL/boot초기화·retry·FF후fallback·사후reset0이며 A/실행권한변경·승인질문·request/frame/tag/generator/backend생성은없습니다.

다음 연결 판단은 관련 실제 참여자의 admission/전체교환 규약, 불명 dispatch에서 소유권과 마지막 접근을 보존하는 adapter 계약, A/B의 유용성·상태 영향을 고정하는 작업에 집중합니다. 정상 반환의 이미 연결된 근거를 다시 전체 kernel/실기trace 요구로 되돌리지 않습니다. 코드 추가 승인은 실제 연결 조건·구체 안이 검토될 때 별도이며 지금은 실행을 요청하지 않습니다.

private cache: 20261107/wmi-acpi-provider-contract-next, ec-mailbox-outcome-contract-next, managed-outcome-boundary-next, provider-outcome-proportionality-next. 공식 문서와 선택 source는 데이터로만 읽고 원본·C# 프로그램·SDK/provider를 실행하지 않았습니다. 문서·정제 기록만 변경, 앱/Core/테스트/EXE/ZIP 미변경·전체 빌드/단위 테스트 미반복이며 C#463/빌드0은1790a4b 과거 기록입니다. 실제 WMI/OEM/하드웨어/사용완료예약 접근·원본 실행/로딩/에뮬레이션·driver/service/security/firmware 변경 없음. 실제 제어 Unsupported·새 실행/동일 자료 제출 불필요입니다. 아래는 이전 기록입니다.

## 최신 — 선택 WMI 경로 분리와 완료 계약 / 2026-11-07

[SELECTED_WMI_ROUTE_AND_COMPLETION_REVIEW.md](SELECTED_WMI_ROUTE_AND_COMPLETION_REVIEW.md), [시험안](FIXED_MODE_READ_PROPOSAL.md), [판정](FIXED_MODE_READ_DECISION.md)을 먼저 읽습니다. 보존된 WMI→AML→PCH legacy SW→SABI callback 경로를 교차 대조했습니다. 별도 Runtime SetVariable proxy의 표준 typed 통신 미연결을 조회 진입 자체의 필수조건에서 제외합니다. 그 분기는 관련 Runtime EC 게시자의 실행 순서와 입력 보존에 영향을 주는 범위만 남깁니다. 새 typed provider 발견이나 현재 전달 성공 관측으로 세지 않습니다.

저장된 keyboard/jog OnIdle caller가 조건을 만족하면 imported query가 매번 사전 local handshake→API/서명 검증→별도 generic query를 수행합니다. Initialize의 성공 stub을 gate-open으로 보지 않습니다. 이 caller는 배터리 명령 근거가 아니고 사후 handshake도 직전 gate 통과·EC 실행·신선함을 소급 인증하지 못합니다. 현재 gate는 미관측이며 old FF 원인을 새로 확정하지 않습니다.

host WMI 프레임과 EC command/data mailbox를 구분합니다. 선택 callback은 snapshot/upload/download/copy 후 반환하며 확인한 closure에 host frame을 EC로 넘기거나 반환 뒤 재접근하도록 예약하는 경로가 없습니다. 선택 entry thunk도 callback 반환 뒤 복귀하지만 실제 전달 trace는 아닙니다. 미게시의 stale 결과와 게시 후 EC mailbox 재사용을 구분하고, 무효 응답 거부를 남은 공유 접근 종료로 취급하지 않습니다. 모든 callback/private Dispose/IRQ 종료를 독립 조건으로 추가하지 않습니다.

Microsoft 공식 WMI API 문서3개·선택 텍스트 관계6개를 검산하고 독립 검토했습니다. 즉시 반환/출력/최종 상태는 다르며, method CancelAsyncCall은 client만 취소하고 provider는 통지 없이 계속할 수 있습니다. WMI가 생성한 취소 SetStatus도 provider 정지 증거가 아닙니다. 정상 최종 성공은 API 완료의 유용한 근거로 유지합니다. 현재.NET48 구현·provider/AML/EC 종료는 이 문서로 직접 입증하지 않습니다. 기존 backend에는 observer.Cancel 호출이 없고 experiment는 CancellationToken.None이며 old 실기의 취소 발생을 추정하지 않습니다.

다음은 선택 provider의 method→AML 반환 계약과 미게시/지연/생략·모호한 dispatch fault에서 마지막 공유 접근/다음 재사용의 경계를 검토합니다. 기존 source의 정상 순서를 활용하고 현재 trace나 모든 Runtime/IRQ 해명을 절대조건으로 만들지 않습니다. gate를 여는 추가 호출은 유용성·상태 영향·횟수를 별도로 검토할 대상이며 현재 최대1WMI/고정 대상 샘플0~1/초기화0 안에 숨겨 넣지 않습니다. 실제 backend/프레임/표식/시험·승인 요청은 추가하지 않았습니다.

private cache: 20261107/selected-provider-path-next, gate-caller-lifecycle-next, wmi-shared-completion-next, wmi-api-completion-contract-next. 이번 source 재검산과 이전 문맥·공식 텍스트 검산을 구분하며 앱 테스트 수·분석률에 합산하지 않습니다. 문서·정제 기록만 변경, 앱/Core/테스트/EXE/배포 ZIP 미변경·전체 suite/solution 빌드 미반복입니다. C#463/빌드0은1790a4b 기록입니다. 원본 실행/로딩/에뮬레이션·실제 WMI/OEM/하드웨어/기존 실기 예약 접근·드라이버/서비스/보안/펌웨어 변경은 없습니다. 실제 제어 Unsupported·새 노트북 실행/동일 자료 제출 불필요입니다. 아래는 이전 기록입니다.

## 최신 — provider 완료 경계·조건부 시험안 구체화 / 2026-11-07 한국 시간

[PROVIDER_COMPLETION_AND_READ_TRIAL_REVIEW.md](PROVIDER_COMPLETION_AND_READ_TRIAL_REVIEW.md), [FIXED_MODE_READ_PROPOSAL.md](FIXED_MODE_READ_PROPOSAL.md), [판정](FIXED_MODE_READ_DECISION.md)을 먼저 읽습니다. **비실행 제안 검토 가능 / 실제 backend 연결·호출 보류**로 정밀화했습니다. 실행 준비 조건을 제안 작성 자체에 확대하지 않습니다. 미확인 status/IRQ 전체나 모든 외부 활동 정지는 독립 필수조건이 아닙니다. 조회 명령/주소/계속 쓰는 입력/결과에 직접 영향을 주는 연결이 생긴 범위만 조사합니다. 이미 연결한 inline 소비·buffer 분리·known ISR 보존을 전체 hardware 미확인으로 되돌리지 않습니다.

기존 Backend는 SDK dispatch 반환+Completed의 선택 snapshot detach/Dispose 시도 후 Task를 게시하지만 다른 callback/disposal 전체 drain은 없습니다. private fake A/B event 하네스13assert로 A completion+Capture.Dispose 뒤 late B.Dispose 진행 중인 상태를 재현하고 모든 작업을 끝냈습니다. 이것은 managed lifetime이며 실제 SDK/provider/AML/EC 활성 증거가 아닙니다. SDK 동기 dispatch 예외도 async Backend에서는 faulted Task라서 겉의 direct throw/null Q만으로 보완되지 않습니다. 공유 준비·trigger·응답 회수 관련 host 작업 종료 계약이 필요하며 old Backend를 단순 연결하지 않습니다.

dotnet/runtime v8.0.0의 observer/sink/eventargs/baseobject4개를 정상 proxy/TLS로 읽어6텍스트 관계를 검산했습니다. 실제 DynamicInvoke/Completed→RemoveSink/new Dispose 관계와 comment를 구분합니다. .NET8 참조를 현재 Win10.NET48 구현·generic IDisposable target·COM 효과·callback/provider/EC 종료 보증으로 쓰지 않습니다. framework 참조 candidate404는 source 부재 증명이 아닙니다. 원문/경로/정확한 source byte는 private에만 보존합니다.

시험안의 계수는 최대1WMI/OEM 읽기 시도·EC byte 읽기0~1·gate handshake/DLL 초기화0·retry/fallback0·firmware 설정/charger 쓰기0입니다. generic gate는 저장 원본 initial 닫힘/현재 미관측, 여는 local handshake는 별도 WMI 호출+image-data 상태변경이므로 숨겨 포함하지 않습니다. 이 gate를 과거 실기 FF 원인으로 단정하지 않습니다. closed/FF/echo/오류/귀속 불명은 판정불가로 끝내며 보호 해제/기능 부재 추정은 하지 않습니다. 실제 fresh 값/주소/frame/generator는 만들지 않았습니다. 유의미한 값을 얻을 준비나 실기 승인 요청 단계로 승격하지 않습니다.

남은 조건은3묶음: 선택 경로/고정 대상/gate와 프로파일, 관련 전체 교환 참여/순차 규약, 관련 완료/입력 비훼손/결과 분류입니다. fresh host content는 endpoint 전제이지 EC 완료ID나 소비 역사 인증이 아닙니다. echo 거부도 입력/result-domain 분리 근거가 필요합니다. 선택하지 않는 모든 대안 통신 경로·live 전체 EC hash/host pointer·모든 writer 부재/Global ACL 사전 수집을 필수화하지 않습니다.

private cache: 20261107/provider-completion-boundary-next(하위 managed-harness), provider-reference-source-next, read-trial-evidence-proportionality-next(독립 검토 기록). 앱/Core/기존 테스트/EXE/배포 ZIP 미변경·전체 suite/solution 빌드 미반복입니다. C#463/빌드0은1790a4b, Python88은e7b067a 과거 기록입니다. 이번 새 실행은 우리 collector2파일을 링크한 private fake 하네스(13pass·하네스 build0경고0오류)이며 참조 text6과 앱463에 합산하지 않습니다. source/OEM 원본 실행/로딩/에뮬레이션·실제 WMI/provider/hardware/기존 예약 접근·드라이버/서비스/보안/펌웨어 변경·과거 차단 PE 시도 재현은 없습니다. 새 노트북 실행·동일 자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 협력 gate/owner 구현·실기 조회 보류 / 2026-11-07 한국 시간

[COOPERATIVE_EXCHANGE_OWNERSHIP_UPDATE.md](COOPERATIVE_EXCHANGE_OWNERSHIP_UPDATE.md), [FIXED_MODE_READ_DECISION.md](FIXED_MODE_READ_DECISION.md), [조건표](FIXED_MODE_READ_PROPOSAL.md)를 먼저 읽습니다. opt-in CooperativeFrameChannel과 GateAttempt/lease를 추가했습니다. 전용 owner가 유한 획득(최대2초)→정상 획득만 lower 호출→실제 pending/owner 직접 Cancel callback 완료→same-thread 해제를 수행합니다. native 고정 Global adapter는 lazy·이름/권한 fallback 없음·정상 OS 권한이며 앱/old OneShot에는 연결하지 않았습니다. 테스트는 fake 및 unnamed만, 실제 Global/하드웨어/예약은 열지 않았습니다.

FrameExchange는 attempt별 stop 신호를 queue 전에 만들고 caller/timeout에서 즉시 비차단 신호한 뒤 기존 off-thread Cancel을 예약합니다. dispatch CAS보다 stop이 먼저면 zero lower call, CAS가 먼저면 이미 admit된 작업의 취소/완료입니다. private CTS.Cancel은 owner가 직접 실행해 blocked callback이 있으면 lease/task를 유지합니다. success/fault/cancel task=실제 종료·sync throw/null=미추적 work0 계약을 명시했고 위반은 Q 처리합니다. Q가 잘못된 provider의 실제 작업 종료를 보장하지는 않습니다. 공유 준비·staging·응답 정리가 하위 call/task 안에 있어야 합니다. abandon/unknown acquire/release fail은 canonical resource+gate identity sticky Q이며 새 wrapper/고정 adapter로 우회하지 못합니다. reset API 없음. process/owner 종료 뒤 외부 work는 별도 미확정입니다.

새22검사(coordinator15/native7)+기존441=463pass/0fail/0skip·전체 net48 Release 빌드0경고0오류입니다. SDK8.0.427·writable DOTNET_CLI_HOME·기존 NuGet cache·DOTNET_ReadyToRun=0/COMPlus_ReadyToRun=0·no-restore·UseSharedCompilation=false·m1로 빌드합니다. SDK 패치/XAML skip/새 package 없음. Python 도구 미변경·88개는e7b067a 과거 기록입니다.

source 상태 생산자 조사는0새 actual producer로 동결했습니다. 요청 인수 기록 field와 고정 status 소비 주소를 구분했고 인접 OR-helper를 busy/ready/error producer로 부를 근거 없음입니다. ordinary/uninterfered byte readback 가정은 MMIO/외부 효과의 부재 증명이 아닙니다. 실제 missing edge는 control 게시→external/controller/IRQ→future status입니다. main1새 check/4문맥, child1field관계/3checks/7문맥은 생산자 발견이나 앱 테스트가 아닙니다.

private cache: 20261107/cooperative-owner-validation(463 tests·solution-build.log), cooperative-owner-design-next, deferred-status-producer-next(하위 consumer-selection-independent). 현재 판정은 **실제 조회 시험 보류**입니다. 실제 Global 상호 운용/관련 참여자, provider 완료/수명, 표준 typed 진입·관련 외부 status/IRQ를 줄이는 새 근거가 필요합니다. 같은 source 후보/락/내용 비교/metadata를 반복해 준비 완료로 승격하지 않습니다. live 전체 hash/모든 writer 부재를 절대 조건으로 추가하지 않습니다. 현재 Unsupported와 앱 흐름·배포 ZIP 유지, old OneShot/Program/정책/encoder/예약 변경·새 hardware backend/frame/tag/배터리 명령·실기 호출 없음입니다. synthetic fixture만 사용했고 원본 실행/로딩/에뮬레이션·OEM/하드웨어/기존 예약 접근·드라이버/서비스/보안/펌웨어 변경·과거 차단 실행 시도 재현은 없습니다. 추가 노트북 실행·동일 자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 같은 자원 재진입 수정·worker 입력 수명 / 2026-11-07 한국 시간

[SHARED_CHANNEL_COORDINATION_UPDATE.md](SHARED_CHANNEL_COORDINATION_UPDATE.md)와 [FIXED_MODE_READ_PROPOSAL.md](FIXED_MODE_READ_PROPOSAL.md)를 먼저 읽습니다. FrameExchange의 인스턴스별 active는 같은 channel을 새 교환 객체로 감싸 우회할 수 있어 CWT reference별 공유 slot으로 수정했습니다. sealed BoundFrameChannel은 내부 readonly snapshot transport reference, 다른 channel은 자기 reference가 key입니다. 기존 pending+취소 callback 모두 끝난 뒤 release·late fault 관측을 유지합니다. metadata가 같은 별도 transport는 독립적입니다. 직접 channel 호출/임의 다른 wrapper/외부 프로세스·OEM/물리 endpoint 전체의 lock은 아닙니다.

회귀4개(같은 channel timeoutpeer, 늦은 취소 callbackpeer, 같은 transport의 두 wrapper, 별도 transport)를 추가했습니다. 기존 취소 검사2개는 off-thread 취소 관측을 기다리도록 정밀화했습니다. 안정화한 수정 전 baseline438pass/3fail(441total), 수정 후441pass/0fail/0skip입니다. 전체 솔루션 Release 빌드 경고0·오류0도 현재 재검증했습니다. 개발 SDK8.0.427의 WindowsDesktop task는 ReadyToRun 이미지 오류가 있어 빌드에 DOTNET_ReadyToRun=0·COMPlus_ReadyToRun=0을 적용하고 쓰기 가능한 DOTNET_CLI_HOME·기존 NuGet cache를 사용합니다. SDK 패치/XAML 단계 생략·새 package 설치 없이 IL 경로로 빌드합니다. Python 도구는 미변경·88개는e7b067a 과거 기록입니다.

선택 CF34-active worker는 원본 input→local staging→byte/bit 계산을 inline 실행한 뒤 terminal request가return1합니다. 확인한 입력 범위는 query upload와 분리됩니다. 반환 이후 실제 입증된 software continuation은 기존 readiness-gated polled finalizer이며 새 IRQ를 발견한 것이 아닙니다. helper가 바꾼DPTR 때문에 statuswriter로 볼 수 없던 후보도 정정했습니다. 실제 외부status/IRQ 생산과 관련 hardware/alias/scratch 수명은 미완료이며 전체 worker/전역writer 부재를 요구하거나 성공으로 주장하지 않습니다.

private cache: 20261107/shared-exchange-slot-fix(테스트 전후·solution-build-il.log), deferred-worker-input-lifecycle-next(하위 irq-entry-independent), wmi-exchange-coordination-code-audit-next. source14새/8문맥·pointer불변식1개를지지하는2검사/15문맥은 앱 테스트·고유 coverage가 아닙니다. source/코드 독립 검토와 실제 테스트·빌드 결과를 구분합니다. 변경은 Core2파일·테스트2파일·문서/정제 기록이며 기존 배포ZIP은 미갱신입니다. 실제 OneShot backend/Program·사용 완료 예약·정책/encoder·앱 등록·새 OEM/frame/배터리 명령·실기 호출은 추가하지 않았습니다. synthetic fixture만 테스트합니다.

다음은 외부 참여자의 전체 WMI 교환 보호와 관련 hardware/status/IRQ 입력 수명·응답 귀속에 실제 새 연결이 있는지 판단합니다. 같은 slot/inline 소비/기존 tag·GUID검색 반복을 새 성공으로 세지 않습니다. live pointer/EC전체hash/모든writer 부재를 절대조건으로 추가하지 않습니다. 실제 제어는 Unsupported이며 현재 앱 흐름·기존 실기 결과는 그대로입니다. 원본 실행/로딩/에뮬레이션·하드웨어/OEM/기존 실기 예약 접근·드라이버/서비스/보안/펌웨어 변경 없음, 과거 차단 실행 시도 재현 없음. 새 노트북 실행·동일 자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — late-clear gate·주소 소비·전체 교환 경계 / 2026-11-07 한국 시간

[EC_QUERY_INPUT_AND_CLEANUP_REVIEW.md](EC_QUERY_INPUT_AND_CLEANUP_REVIEW.md)와 [FIXED_MODE_READ_PROPOSAL.md](FIXED_MODE_READ_PROPOSAL.md)를 먼저 읽습니다. descriptor 하위 작업의 시작 성공→active·완료 대기 상태 생산→readiness/정리 gate를 새로 연결했습니다. 같은 byte의 다른 ISR bit와 active bit를 혼동하지 않으며 실패 rollback도 구분합니다. 선택 staging/알려진 복사는 query mailbox와 다른 영역이나 관련 하위 작업이 계속 소비할 입력을 조회 upload가 훼손하지 않는지는 미완료입니다. 현재 Windows overlap·하드웨어 기능명·startup/flash/shutdown 전용을 단정하지 않습니다.

고정 reader는 주소 두 성분을 순차 소비→target sample→첫 성분을 결과로 대체합니다. known stable-command ISR의 실제 register 보존을 이 구간에 결합했습니다. 사후 비교는 endpoint 보존이며 덮어쓴 첫 성분의 과거값·두 소비시점의 지속 안정성·EC실행identity를 인증하지 않습니다. 송신생략/실행전clear/완료후clear를 분리하며 기존 tag·오류가림·ISR entry를 새 성과로 재집계하지 않습니다.

두 raw DSDT는 Field AnyAcc/Lock/Preserve이면서 WM00/SAWS는 NotSerialized입니다. explicit MTX1은 trigger만 보호합니다. Field Lock만으로 전체 교환·firmware Global Lock 참여를 증명하지 않고 NotSerialized만으로 Windows의 실제 race도 주장하지 않습니다. 필요한 것은 관련 전체 교환의 무결성/소유권이며 특정 협력 mutex만 강제하지 않습니다.

최소 계약은 기존 정상 작업의 명령/상태/계속 소비할 입력의 비훼손과 고정 조회의 사전 대상 안전성·오귀속 방지·실제 하위 정리입니다. 새 조회 자체의 취소는 안전한 실패/판정불가로 허용하며 양쪽의 무조건 성공을 요구하지 않습니다. 다음은 특정 deferred 작업의 계속되는 buffer 소비와 입력 준비~snapshot 경계의 실제 참여 규약에 집중합니다. 표준 통신은 구체 provider/caller→typed dispatch가 생길 때만 갱신하며 같은 GUID 검색/legacy/내용 비교 반복은 하지 않습니다. live pointer/전체 EC hash/모든 writer의 전역 부재를 절대 조건으로 추가하지 않습니다.

private cache: 20261107/ec-late-clear-gates-next, fixed-read-response-attribution-next, wmi-field-lock-boundary-next. response16관계/80재사용문맥·Field5관계는 앱 테스트나 분석률이 아니며 원본 hash/동일 byte decode와 새 관계를 구분합니다. 문서·정제 기록만 변경, C#/WPF·Python 개발 도구·EXE·기존 ZIP 미변경·이번 빌드/단위 테스트 미실행입니다. C#437/빌드경고오류0은5d77df5, Python88은e7b067a 과거 기록입니다. 실제 query backend/frame/tag값/시험 추가·원본 실행/로딩/에뮬레이션·OEM/하드웨어/기존예약 접근·드라이버/서비스/보안/펌웨어 변경 없음. 과거 차단 실행 시도는 보존하며 재현하지 않았습니다. 추가 노트북 실행·동일 자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 부팅 알림 선행·legacy domain·EC 준비 규약 / 2026-11-07 한국 시간

[EC_READ_HANDOFF_AND_BOOT_ORDER.md](EC_READ_HANDOFF_AND_BOOT_ORDER.md)와 갱신한 [FIXED_MODE_READ_PROPOSAL.md](FIXED_MODE_READ_PROPOSAL.md)를 먼저 읽습니다. NvramSmi는 복합 SMM/DXE FFS이며 DXE DEPEX는 SmmBase2만 요구합니다. 별도 SMM DEPEX와 합치지 않습니다. CORE의 복합 모듈 열거·DXE DEPEX 처리·dispatch 반환→BDS receiver를 연결했습니다. 발견·의존성·비재진입 Load/Start·notify 등록 성공 조건이면 BDS marker보다 등록이 선행합니다. dispatch 완료는 미발견/미충족/시작 실패 모듈 성공을 보장하지 않습니다. 정상 소스 조건과 현재 포인터 미관측은 구분하며 live pointer/전체 EC hash 하나를 절대 proposal blocker로 되돌리지 않습니다.

Nvram legacy SW fallback은 정확한 PCH GUID/interface·context 생산/비교·동기 child→같은 default-root legacy 순회→server의 선택 privateRT로 연결했습니다. Runtime의 legacy SMST 게시와 Nvram native SMST 조회는 실제 공유 config backing으로 결합합니다. lookup이0으로 이전 포인터를 유지한 경우는 private 성공이 아닙니다. SmmBase legacy Communicate의 shared input·deferred job→leader 특별 callback→같은 legacy-list buffer/size 입력도 연결했습니다. 이 별도 legacy job은 typed GUID 선택을 하지 않으며 Nvram legacySW나 표준 communication과 합치지 않습니다. 표준 제공자→normal entry→typed handler는 여전히 미완료, 동일 GUID/분할 검색 반복은 하지 않았습니다.

Runtime/조회의 8개 complete helper pair는 call역할·localbranch 기준 정규화 동일이며 같은 indexed endpoint·command slot·zero-ready·오류 admission을 씁니다. 같은 정상 비재진입 domain 조건이면 CPU selector 중첩·후크 postwait 부재만을 근거로 한 overwrite 추론을 좁힙니다. readyzero는 효과 완료 token이 아니며 EC의 늦은 clear·이전/다음 작업 보존은 별도입니다. WMI staging/snapshot/return 소유권·첫 송신 오류 가림·응답 귀속도 미완료입니다.

다음은 고정 조회의 실행 전 입력·EC 명령 인계·양쪽 작업 보존·응답 귀속의 구체 예외에 집중합니다. 표준 통신은 제공자/caller→typed dispatch의 실제 새 연결이 있을 때만 갱신하며 기존 legacy/준비 규약/부팅 성공 조건을 반복 성과로 세지 않습니다. 모든 플랫폼 writer 부재·전체 live EC hash를 필수화하지 않습니다. 실제 요청/frame/tag값/backend/하드웨어시험·기존예약 접근·새 승인 없이 Unsupported입니다.

private cache: 20261107/nvram-bds-notify-order-next, communication-entry-dataflow-next(하위 leader-subset), nvram-legacy-sw-domain-next, runtime-query-handoff-next. 기존 개별 source/helper 검산과 새 cross-module 관계를 분리하며 전체 분석률로 합산하지 않습니다. 문서·정제 기록만 변경, C#/WPF·Python 개발 도구·EXE·기존ZIP 미변경, 이번 빌드·단위 테스트 미실행. C#437/빌드경고오류0은5d77df5, Python88은e7b067a 과거 기록입니다. 원본 실행/로딩/에뮬레이션·하드웨어/OEM/예약·드라이버/서비스/보안/펌웨어 변경 없음. 과거 차단된 실행 시도 기록은 보존하며 재현하지 않았습니다. 새 노트북 실행·동일 자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — Runtime 중계 수명과 고정 조회 비실행 검토 / 2026-11-07 한국 시간

[RUNTIME_PROXY_AND_FIXED_READ_REVIEW.md](RUNTIME_PROXY_AND_FIXED_READ_REVIEW.md)와 [FIXED_MODE_READ_PROPOSAL.md](FIXED_MODE_READ_PROPOSAL.md)를 먼저 읽습니다. 저장된 CORE_PEI의 정상 HOB producer는 초기화된 결정 바이트로 flash 계열을 선택합니다. Runtime 후반 초기화의 할당 성공은 주소 보정 adapter, 실패는 직접 flash adapter를 선택하며 둘의 begin/end는 기존 flash 후크로 연결됩니다. 주소 보정 adapter를 SMM 전용이라고 부르던 표현은 정정했습니다.

NvramSmi의 알림 callback은 실제 host SetVariable을 proxy로 교체하고 CRC를 다시 계산합니다. 게시된 BDS entry의 고정 함수 목록에서 같은 알림 marker 생산자를 연결했습니다. VA 전환은 그때 현재 슬롯 값을 변환하며 초기 함수를 복원하지 않습니다. 실제 알림 순서·등록/lookup 성공·최종 target은 미관측입니다. host proxy→GUID별 SMM handler→private RT core 연결과 normal entry의 같은 순차 domain 증명은 구분합니다. normal default 순회는 nonNULL typed handler를 직접 호출하지 않습니다. 표준 통신 제공자→normal entry→typed manage edge는 미완료입니다. 별도 legacy SW fallback을 표준 통신·SWDispatch2와 합치지 않습니다.

PchInitDxe의 조건부 SMI_LOCK 위치 writer와 같은 notify GUID의 임시 publisher는 source positive이나 현재 policy/lock/마스크 수용 여부·이미 실행 중인 SMM 정지·모든 CPU 배제를 입증하지 않습니다. 알림을 ReadyToLock/flash lock으로 바꾸어 부르지 않습니다. 선택한 두 EC 후크의 전체 body는 같은 상태 플래그 한 비트 RMW 후 반환하며 payload/result를 소비·쓰기하지 않습니다. 따라서 알려진 RT 게시자를 범용 주소 writer로 가정하지 않습니다. sender는 준비 후 명령만 게시하고 완료를 기다리지 않으며 local flag도 실제 완료 증거가 아닙니다. 후크 명령·정상 전이 보존과 CPU indexed selector 무결성은 별도로 남습니다.

임시 CandidateProfile로 고정 저장 모드 한 바이트 1회 비실행 제안을 검토할 근거는 충분합니다. 현재 EC 전체 hash를 제안 검토의 절대조건으로 요구하지 않습니다. 하지만 실제 backend 조건은 미완료이며 원인은 최종 host 경로·통신 domain·관련 indexed 접근·다른 정상 작업 보존입니다. 다음은 저장 원본의 실제 통신 provider→GUID별 dispatch 및 BDS 알림 순서를 좁게 검토합니다. 닫지 못한 edge는 그대로 남기고 같은 GUID/표/기존 decode를 반복 성과로 세지 않습니다. broad continue는 새 실기 승인도 기존 단발 재사용 허가도 아닙니다. 새 호출 code/요청값/시험/수집/자료 재제출 없이 Unsupported입니다.

private cache: 20261107/runtime-backend-configuration-next(하위 runtime-field-subset), runtime-service-lifetime-next(하위 nvram-consumer-independent/smm-server-followup), smi-guard-lock-lifecycle-next, ec-flash-hook-effects-next, communication-root-domain-next, smm-communication-provider-split-guid-next. 구성322/하위84는 겹치는 byte+decode, 수명31block/134동일block decode, 하위installer67/server43, guard52, EC효과8새/11문맥을 합산·기능수·분석률로 바꾸지 않습니다. 문서·정제 기록만 변경, C#/WPF·Python 도구·EXE·기존ZIP 미변경, 이번 빌드·단위 테스트 미실행입니다. 437/경고오류0은5d77df5, Python88은e7b067a 과거 검증입니다.

분석 중 bare PE 경로를 셸 명령으로 잘못 전달한 시도1건이 Permission denied로 차단됐습니다. 원본 실행·권한 변경·재시도는 없으며 숫자 종료코드는 미확보라 추정하지 않습니다. exact command·stat/hash는 runtime-service-lifetime-next/blocked-attempt.private.json/md에만 보존합니다. 실행을 재현해서 검증하지 않습니다. 이후 trusted parser의 바이트 읽기만 수행했습니다. 하드웨어/OEM·기존예약·드라이버/서비스/보안·펌웨어 변경 없음. 아래는 이전 기록입니다.

## 최신 — Runtime OS 소비자·현재 EC 이미지 근거 / 2026-11-07 한국 시간

[RUNTIME_VARIABLE_AND_EC_IDENTITY_REVIEW.md](RUNTIME_VARIABLE_AND_EC_IDENTITY_REVIEW.md)를 먼저 읽습니다. 실제 host RuntimeServices SetVariable wrapper 게시부터 NV 속성·구성 선택·backend 전달·flash receiver를 연결했습니다. NV flash adapter와 RAM adapter·SMM 별도 adapter를 혼합하지 않습니다. 새 변수 append가 주 경로이고 RAM staging 뒤 persistence backend를 쓰는 것은 선택 rebuild fallback이며 모든 기존 변수 수정의 일반 경로가 아닙니다. 현재 Windows 호출·probe·구성·동시 실행은 미관측입니다. 이전 Runtime 보존/EC hook 분석 수치를 새 성과로 다시 세지 않습니다.

외부 flash 소비자는 SBDXE entry의 정확한 첫 게시 GUID→receiver→begin/end 연속 호출과 SMIFlash의 InSmm 초기화→다른 게시 GUID→등록된 SW callback→같은 표의 메서드로 연결했습니다. SMIFlash의 flash 조회는 InSmm 안의 BootServices 조회이고 SW registry 조회는 SMST이므로 receiver를 혼동하지 않습니다. 같은 GUID·offset 출현 수는 소비자 수가 아닙니다.

host/SMM 변수 wrapper의 공유 busy pointer와 PIC·제어 필드의 guard는 source positive이나 plain admission을 atomic lease로 해석하지 않습니다. 공개 coreboot4.20 Lynxpoint 헤더를 정상 proxy/TLS로 한 번 받아 SMI 제어 역할을 교차 확인했습니다. coreboot default base 대신 저장된 Samsung ACPI base를 사용했습니다. 현재 register lock/쓰기 효과·이미 진행 중인 SMM 배제·새 SMI delivery·공통 EC 소유권은 입증하지 못했습니다. 실제 변수 저장/flash/마스크 변경으로 시험하지 않습니다.

현재 EC identity 감사는 보존 실기 TXT17개 ECversion 관련 명시 필드 미관측·현 앱/준비/단발 도구의 BIOS 문자열 전용 수집을 확인했습니다. SMBiosBoard는 ECRev1/2를 RuntimeServices GetVariable로 읽고 typed SMBIOS 제공자 finder(Type0,instance1)와 update 메서드를 통해 EC release 필드를 채웁니다. PE 진입점과 명명 변수 read body를 구분하며 실제 주소는 private 기록만 봅니다. 정확한 이름/좁은 변형 검색에서 명명 변수 생산자는 미연결입니다. 계산된 이름·비PE·다른 이미지·외부 updater 부재를 주장하지 않습니다. live EC 기원/정적 default/updater cache·갱신 주기·현재 값·EC본문 동일성은 미확정입니다. 단순 버전 수집을 추가해도 이 간극은 닫히지 않아 새 collector·자료 재제출을 요구하지 않았습니다.

다음은 이 구체적인 host NV 저장의 flash/RAM 구성 선택·후속 RuntimeServices 표 교체와 guard의 실제 동기화 범위를 우선합니다. 정상 SMM 순차화·WMI 협력 잠금을 direct OS RuntimeServices까지 자동 확장하지 않습니다. EC 이미지 적합성은 현재 BIOS 문자열·SMBIOS cache 값만으로 승격하지 않습니다. 고정 조회 입력·실행 전 소유권·응답 귀속 계약은 여전히 미완료이므로 실제 backend·제어 권한 추가 없이 Unsupported입니다.

private cache: 20261107/runtime-os-services-consumer-next(하위 rt-entry-subset), flash-protocol-consumers-next(하위 smm-consumer-independent), current-ec-identity-evidence-next, ec-revision-variable-producers-next, smbios-ec-version-source-next, smi-mask-register-crosscheck-next. 새 source 검산은 문맥/중복 decode와 분리합니다. 문서·정적 기록만 변경, C#/WPF·Python 도구·EXE·기존 ZIP 미변경, 이번 빌드·단위 테스트 미실행입니다. C#437/빌드경고오류0은5d77df5, Python88은e7b067a 과거 기록입니다. 원본 실행·하드웨어/OEM·단발 예약·드라이버/서비스/보안·펌웨어 변경 없음. 아래는 이전 기록입니다.

## 최신 — 명령 게시·선택 무결성과 최소 조회 설계 / 2026-11-07 한국 시간

[EC_COMMAND_OWNERSHIP_REVIEW.md](EC_COMMAND_OWNERSHIP_REVIEW.md)를 먼저 읽습니다. EC의 포인터 writer는 명령 슬롯에 쓸 capability가 있지만 복원한 진입에서는 자신의 선택 뒤에 store합니다. 대체 poll도 같은 main scheduler 후속 경로로 연결돼 독립적인 ISR 재진입으로 세지 않습니다. 직접 literal 목록의 zero clear·기존 class/index 두 읽기는 문맥이며 새 nonzero 자율 재게시자를 확보한 것이 아닙니다. 다른 handler가 reader의 미사용 입력을 쓰기 데이터로 해석할 수 있으므로 사후 응답 거부로 실행 전 명령·대상 안전성을 대체하지 않습니다.

펌웨어 게시자는 초기화·등록·제공자·실제 helper를 연결해 boot와 SMM 문맥을 분류했습니다. SecEcDxe는 dual-domain이며 EC event registry와 SW registry를 혼합하지 않습니다. SecEcSmiDispatch의 새 handler는 GPI Dispatch2 등록이지 SW 호출로 분류하지 않습니다. SecSwSmiDispatch 등록·게시와 SABI 제공자, SetupValueToEc/TouchPad의 boot lifecycle, Legacy의 같은 SABI forwarder를 구분합니다. 같은 literal·helper 사본·모듈 수는 동시 작성자 수가 아닙니다. busy 대기는 흐름 제어이며 소유권 예약이 아닙니다.

새 정상 SMM 세대 논증은 초기화 entry 상태 완료·private control 안정·고유하고 비재진입인 CPU context가 전제입니다. 늦은 CPU나 전체 도착 대기 한도 소진만으로 두 번째 root가 만들어지는 것은 아닙니다. 초기화 gate는 root 전체를 잠그지 않으므로 reset/stale-init 상태까지 같은 정리로 확대하지 않습니다. 새 Base2 getter→실제 child 서비스 테이블→root 등록→같은 callback 목록→child SW/GPI 분기의 연결도 별도 검산했습니다. 등록 성공과 정상 세대가 전제인 source positive이며 WMI 입력/반환·다른 직접 host 접근을 포함하지 않습니다. 정상 framework 전제를 악성 memory writer 전역 부재 요구로 바꾸지도 않습니다.

Runtime은 실제 boot/SMM 초기화가 flash interface를 게시하고 그 메서드가 선택 flash 장치의 전후 hook을 거쳐 EC 명령을 게시합니다. virtual-address-change callback이 hook을 포함한 함수 포인터 표를 변환하므로 단순 boot dead library로 제외하지 않습니다. 현재 probe 선택·OS Runtime Services/Windows 소비자→해당 메서드·실제 동시 실행은 이번에 연결하지 못했습니다. 이 다음에는 이 구체 소비자 경계와 현재 EC 이미지 적합성을 우선하며 같은 literal 스캔이나 이미 분류한 SMM handler를 반복 성과로 세지 않습니다. firmware flash 기능을 실제 시험·대체 조회로 사용하지 않습니다.

제조사에서 확보한 서비스 WSABI의 정확한 SHA564b 원본을 새로 잠금 범위까지 검산했습니다. Call export는 helper에 CALL하는 wrapper이며 direct JMP가 아닙니다. 같은 Global mutex를 쓰는 저장 원본은 기존 세 개와 합해 네 개입니다. 정상 획득에서만 일반 교환에 들어가 응답 copy 뒤 해제하지만 무한 대기·abandoned 처리 누락은 그대로 재현하지 않습니다. runtime DLL·권한·실제 참여는 미관측이고 native의 다른 잠금·직접 WMI/ACPI는 자동 포함되지 않습니다.

최소 조회 설계는 고정 저장 모드 한 바이트, 실행 전 입력·소유권 검증, 응답 귀속, 같은 worker의 유한 lock 대기·실제 하위 완료까지 소유권 유지, 저장 후보값과 충전기 적용 구분입니다. 현재 조건 미확정이면 메서드 호출을 하지 않습니다. 실행용 요청·표식·frame generator·실제 backend는 추가하지 않았습니다. 추가 실기·동일 자료 재제출·기존 단발 재사용 없이 Unsupported를 유지합니다.

private cache: 20261107/ec-command-slot-writers-next(하위 alternate-poll-independent), firmware-command-publishers-next(하위 setup-legacy), service-wsabi-coordination-next, normal-epoch-command-serialization-next, root-domain-binding-next, runtime-command-publisher-lifecycle-next. 새 호출 관계와 기존 문맥 재검산은 정제 audit에 분리합니다. 문서·정적 기록만 변경, C#/WPF·Python 도구·EXE·기존 ZIP 미변경, 이번 빌드·단위 테스트 미실행입니다. C#437/빌드경고오류0은5d77df5, Python88은e7b067a 과거 기록입니다. 하드웨어/OEM·단발 예약·드라이버/서비스/보안·펌웨어 변경 없음. 아래는 이전 기록입니다.

## 최신 — 조회 간섭 후보의 실행 순서·역할 연결 / 2026-11-07 한국 시간

[EC_QUERY_INTERFERENCE_REVIEW.md](EC_QUERY_INTERFERENCE_REVIEW.md)를 먼저 읽습니다. 다른 첫 바이트 작성자는 같은 분배표의 별도 명령 handler로 연결됐으며 자율 background writer로 입증한 것이 아닙니다. 조회 명령이 유지되는 단일 분배에서는 선택 reader를 실행합니다. 다른 완료 clear는 같은 main thread의 조건부 scheduler 후처리입니다. 새 host post를 나중에 지울 조건부 취소 구간은 남지만 선택 clear block은 결과 바이트·tail을 바꾸지 않으며 단순 취소는 input echo 거부 대상입니다. 실제 race·상위 전체 간접 효과는 미입증입니다. 정확한 주소·명령값·호출 관계는 비공개 원본 기록에 보존합니다.

알려진 ISR 형태의 진입에서 안정된 조회 명령 분기는 low-command clear를 우회하고 결과를 바꾸지 않으며 사용 register를 복구합니다. 실제 hardware binding은 조건부입니다. 중복 pending만으로 완료 후 다른 handler를 실행하지 않습니다. 반면 분배기는 명령 종류와 index를 위해 공유 명령을 두 번 읽으므로 그 값의 안정성이 필요합니다. 사후 응답 거부는 잘못된 명령의 부작용 취소가 아닙니다.

실제 AP 소비자는 CpuSpSMI/PowerMgmtS3/DigitalThermalSensorSmm/MicrocodeUpdate의 여섯 호출·열 고정 작업으로 CPU/cache/MTRR·전력 register·thermal/APIC·microcode 역할입니다. 선택 작업에서 EC/SABI 연결 미확보이지 전체 간접·runtime 작업 부재가 아닙니다. old/new SMST의 다른 method offset을 혼동하지 않습니다. 동일 displacement나 GUID 포함 후보 수는 실제 AP caller 수가 아니며 IA32에 x64 offset을 적용한 완전 탐색도 아닙니다.

선택 일반 callback을 포함한 13함수의 CFG를 새로 검산했습니다. 이 사슬은 직접 호출·tail 분기만 있고 AP pump가 아니며, 입력 snapshot 뒤 local 명령·메시지를 씁니다. snapshot 자체의 원자성·다른 CPU/ISR/indexed I/O·최종 frame 교체는 증명하지 못했습니다. timer poll은 타이머 진행이 전제이며 앱 timeout을 SMM 중단 보장으로 쓰지 않습니다. 실행 요청·표식 값·frame·실제 backend는 만들지 않았습니다.

다음 최소 계약은 선택 고정 조회의 의미를 바꾸는 간섭의 비중첩·규약·안전 검출입니다. 전역 writer 부재를 요구하지 않습니다. 공유 명령 게시→종류 판정→handler 선택, WMI 입력 snapshot·응답 반환의 충돌 가능한 실제 작성자에 집중합니다. 이미 분류한 CPU 작업·다른 명령 handler·clear 본문 존재만으로 자율 덮어쓰기 반례를 다시 세지 않습니다. 현재 모델·이미지·읽기 부작용·IRQ·간접 진입은 여전히 미확정입니다.

private cache: 20261107/ec-producer-attribution-next(하위 result154ad-independent), smm-ap-mailbox-callers-next(하위 cpu-subset), generic-callback-call-closure-next. 새 source checks·독립 검토는 정제 audit에 분리 기록합니다. 문서·정적 기록만 변경, C#/WPF·Python 도구·EXE·기존 ZIP 미변경, 이번 빌드·단위 테스트 미실행입니다. C# 437개·빌드 경고/오류 0개는 5d77df5, Python 88개는 e7b067a 과거 기록입니다. 실제 보호 조회 미완료·제어 Unsupported입니다. 추가 실기·재제출·OEM/단발 예약·하드웨어/보안 변경 없음. 아래는 이전 기록입니다.

## 최신 — 보호 상태 조회 경로의 성립 조건 / 2026-11-07 한국 시간

[BOUNDED_READ_ROUTE_FEASIBILITY.md](BOUNDED_READ_ROUTE_FEASIBILITY.md)를 먼저 읽습니다. WMI→일반 callback→조건부 EC 모드 저장값 읽기의 정적 경로는 이미 있습니다. ‘경로 없음’과 ‘현재 장치의 안전한 최신 응답 계약 미완료’를 구분합니다. 전용 OEM getter는 유일한 해법이 아니며 기존 범용 읽기를 고정 대상에 제한해 같은 계약을 입증할 가능성도 열어 둡니다. 아래 과거 메모의 고정 getter 조건을 배타적인 요구로 적용하지 않습니다.

선택 reader의 미갱신 tail을 이용한 새 표식은 기존 mailbox에 없고 재사용·경쟁 작성자가 없다는 전제에서 업로드 생략 stale 응답을 거부할 수 있습니다. echo 거부도 무변화 입력을 닫습니다. 비재사용만으로 기존 내용 불일치를 보장하지 않으며 tag는 EC 생성 완료번호가 아닙니다. 다른 결과 생산자의 동시 개입은 실제 도달·race를 입증한 것이 아니고, 배제도 미완료입니다. 요청·tag값·프레임·실제 backend는 만들지 않았습니다.

새 SmmDispatcher 소스는 CPU rendezvous·같은 handler 목록의 동기 순회를 보여주지만 모든 CPU 도착을 기다리는 두 구간은 한도 소진 뒤 계속 진행합니다. 참여 AP도 작업 슬롯 함수를 실행할 수 있습니다. 실제 EC writer의 해당 API 사용은 미입증입니다. WM00 입력 저장/반환은 SMM 바깥이므로 전체 교환 독점으로 확대하지 않습니다. 다음 근거는 고정 대상/처리자와 현재 이미지의 적합성, 요청 준비→선택 처리→결과 복사 사이 작성자 관계·결과 귀속입니다. 특정 미해결 분기만 반복 분류해 기능 진전으로 세지 않습니다.

모드 한 바이트 조회와 여러 임계값 조회의 비원자성을 구분합니다. 이미 같은 활성 모드인 setter는 임계값을 다시 쓰지 않고 일부 충전기 쓰기 성공도 미검사이므로 저장값을 실제 적용으로 승격하지 않습니다. 남은 지원 패키지 세 개는 새 배터리 API 근거가 없고, 기존 Support Center caller는 설치 파일·창 활성화·프로그램 실행입니다. 새 다운로드나 OEM 실행은 하지 않았습니다.

private cache: 20261107/bounded-route-feasibility-next, smm-route-serialization-next, current-model-route-sources-next, route-feasibility-independent-review-next, bounded-route-integration-next. 문서·정적 감사만 변경, C#/WPF·Python 도구·EXE·기존 ZIP 미변경, 이번 빌드/단위 테스트 미실행. C#437/빌드경고오류0은5d77df5, Python88은e7b067a 이전 기록입니다. 실제 조회·제어 Unsupported. 추가 실기·동일 자료 재제출·OEM/예약 접근·드라이버/서비스/보안·펌웨어 변경 없음. 아래는 이전 기록입니다.

## 최신 — 새 Amor3 공식 원본 확보·오프라인 pin 추가 / 2026-11-07 한국 시간

[AMOR3_OEM_SOURCE_ACQUISITION.md](AMOR3_OEM_SOURCE_ACQUISITION.md)를 먼저 읽습니다. 기존 펌웨어 후보 반복 대신 모델 일치 목록 6개와 미검토 구성요소를 대조했습니다. WB 두 BOM이 같은 SamsungSystemConfiguration for Amor3 1.0.0.7/BASW-A0141A02.ZIP을 가리켜 정상 제조사 redirect로 새로 받았습니다. 3,771,257바이트/SHA1681f1a5a10b3d758ce1b925efbe7ec4360d3ed33c7d3fb189a5bf69fff699c2, 10파일/비압축7,585,067·CRC·안전 경로 일치. 원본·카탈로그는 비공개이며 사용자 시리얼/장치정보 전송·환경 설정 변경 없음.

WSABI22920/SHA564b는 과거 서비스 DLL 기록과 같으나 과거 Monitor 해시가 없어 Monitor까지 동일하다고 하지 않습니다. 새 Monitor1.0.0.7의 loader는 GetModuleFileNameW(NULL) 기반 디렉터리+wsabi.dll 경로 구성→LoadLibraryW/동적함수입니다. bare DLL 이름만 전달한다고 하지 않으며 현재 runtime DLL 선택도 미관측입니다. 선택한 query/setter 문맥은 팬 제어이고 준비 결과·BIOSmode·80은 배터리 보호 성공/80%가 아닙니다. SSC 설치 설정의 서비스/idle task는 데이터로만 읽었고 실행 안 했습니다.

기존 W7 SettingsChargingOnlyMode는 실제 USB/태블릿 충전 전용 경로, A1/V21의 추가 Settings_OSD_Win10.exe+INI는 EventHandler 알림 소비자로 연결했습니다. 정확한 OS 선택 조건·현 노트북 선택은 미확인입니다. 현재 2.2.0.18의 33언어 BLE 도움말은 모델 허용 목록이 아니며 검토한 MSI component 선택 조건은 OS 분기이고 custom action에는 설치 상태 조건도 있습니다. SettingsDeployer의 모델 정보 원천은 CommandSystemInfo.dll이지 SUS가 아닙니다. 선택한 V18/V21 코드 차이도 새 보호 query로 연결되지 않았습니다. 이 기능들을 충전 제한 진전으로 세지 않습니다.

개발 scripts/inspect_command_research_artifact.py에 ssconfig-amor3 고정 pin을 추가했습니다. 크기·해시 불일치/누락을 ZIP 해석 전에 거부하며 관측 일치는 ObservedSourcePayloadMatched, 인증/모델/배터리계약/하드웨어 권한 false입니다. 실제 새 ZIP 검사·독립 코드 검토 통과, 신규 3개 포함 전체 Python 88개 통과. C#/WPF·EXE·기존 ZIP은 미변경이며 C# 테스트/빌드 미실행; 437개·경고오류0은 이전5d77df5 기록입니다.

private cache는 20261107/ssconfig-source-acquisition-next, target-catalog-source-gap-next(하위 monitor-review), oem-model-config-next, alternate-oem-source-gap-next(하위 v21-component-diff)입니다. 다음 채택 조건은 현재 모델의 보호 상태 생산자→고정 조회→실패 보존·새 요청 대응→Windows 반환입니다. 현재 새 보호 계약 미확보·실제 제어 Unsupported. 원본 실행·하드웨어/OEM 호출·단발 예약·드라이버/서비스/보안·펌웨어 변경·추가 실기·동일 자료 재제출 없음. 아래는 이전 기록입니다.

## 최신 — 외부·간접 후보 검토와 구현 보류 경계 / 2026-11-07 한국 시간

[EXTERNAL_INDIRECT_CONTRACT_BOUNDARIES.md](EXTERNAL_INDIRECT_CONTRACT_BOUNDARIES.md)를 먼저 읽습니다. 이번에도 새 보호 조회 계약은 확보하지 못했습니다. 34개 PE의 동일 192바이트 .data 구간은 공통 창이며 완전한 객체·등록표·미사용 증명이 아닙니다. 선택 참조 83개 중 19개는 기존 SABI 직접 참조 6개 모듈, 64개는 이웃 GUID입니다. 구간의 첫 호출 전 별칭 복사 등을 못 찾은 것은 전역 부재가 아닙니다. 과거 20261106 pointer/affine 음성 분석은 반복 성과로 세지 않았습니다.

게시 간접 호출은 기존 초기화로 연결했고 새 late 등록은 미확정입니다. 일반 native wrapper의 그룹 고정과 별도 CallBIOSInterfaceEx의 호출자 UInt16 main을 구분합니다. 현재 WSABI 세 변형에는 named Ex export가 없지만 다른 모든 그룹 불가능/임의 그룹 시험의 근거로 삼지 않습니다. 좁은 data-record 탐색 0건도 stack/다른 배치/계산된 소비자 부재가 아닙니다.

간접 반환 EC 후보의 페이지 교환은 old byte를 반환하기 전에 새 byte를 써 조회에서 제외했습니다. 순수 읽기 본문들의 저장된 요청 포인터·응답 callback 공급자는 미연결입니다. 선택한 표 기반 초기화 11개 wrapper/41개 mask-update 기록은 다른 페이지 쓰기이며 모드·반환 포인터 생산자는 아닙니다. 전체 초기화·외부 ROM 부재를 주장하지 않습니다.

현재 확인 범위로 실제 조회·제어 코드를 추가할 근거가 부족해 구현을 보류합니다. 다음 착수는 현재 모델의 보호 상태 생산자→고정 조회→실패 보존·새 요청 대응→Windows 반환을 직접 잇는 새 등록/호출자/응답 근거 확보입니다. 동일 GUID·flag·범용 읽기의 반복 분류는 기능 진전으로 세지 않습니다. 새 연결 없으면 보류 유지, 하드웨어 영구 미지원 판정 아님. 추가 실기·동일 자료 재제출·OEM/단발 예약 접근은 하지 않습니다.

private cache는 20261107/external-guid-alias-next(하위 shared-pool-independent), sabi-registration-publishers-next, indirect-ec-state-getters-next(하위 pointer-independent), external-indirect-integration-next입니다. 앱·테스트·EXE·기존 ZIP 미변경, 이번 빌드·단위 테스트 미실행이며 437/85·경고오류0은 이전 5d77df5 기록입니다. 실제 제어 Unsupported, 드라이버/서비스/보안·펌웨어 변경 없음. 아래는 이전 기록입니다.

## 최신 — 고정 조회의 소비자·실패 경계 대조 / 2026-11-07 한국 시간

[FIXED_QUERY_CONSUMER_REVIEW.md](FIXED_QUERY_CONSUMER_REVIEW.md)를 먼저 읽습니다. 이번에는 새 보호 조회 계약을 확보하지 못했습니다. 현재 Settings 2.2.0.18의 ModuleSABI EcoMode_GetPowerData와 CommandMNPowerManagement의 CmdGetCurrentPowerData를 export·동적 API·RTTI/vtable/import로 연결했습니다. 고정 query의 두 word는 SBS 전류·전압 캐시이며 숫자 소비자는 조회 반환을 무시합니다. gate 서명은 물리 기능 지원이 아닙니다. 이 전력 표시 경로를 보호 모드 후보로 다시 세지 않습니다.

저장된 DSDT ECON==0의 byte/word wrapper→SSDB 제공자→SecEcDxe callback→EC 고정 페이지 읽기를 연결했습니다. byte callback은 하위 상태를 버리고 초기/결과 byte를 복사해 0을 반환합니다. word callback은 두 번 따로 읽고 상태를 모두 버리며 동일 임시 byte를 재사용합니다. 현재 fallback 선택·잘못된 실제 표시를 관측한 것은 아닙니다. 레거시 SABI와 번호만으로 합치지 않습니다. 다른 대상의 성공 bus word 캐시도 충전기 옵션 의미가 확보되지 않았습니다.

위 후보는 식별 완료/미해결로 보류하고 반복 세분화하지 않습니다. 다음은 아직 보호 상태 생산자를 연결하지 못한 외부 등록·간접 전달 경로에 한정합니다. 새 생산자→고정 조회→실패 보존·새 요청 대응→Windows 반환을 채택 기준으로 삼습니다. 연결이 없으면 미해결로 남기며 기능 진전으로 보고하지 않습니다. 새 요청·live backend·제어·OEM 시험·단발 예약 접근 없이 Unsupported입니다.

private cache는 20261107/oem-fixed-read-consumers-next, readback-producer-callers-next(하위 independent-word-index), fixed-word-query-routes-next(하위 external-ec), fixed-consumer-source-integration-next입니다. 독립 통합 검산 37개 통과. 앱·테스트·EXE·기존 ZIP 미변경, 이번 빌드·단위 테스트 미실행이며 437/85·경고오류0은 이전 5d77df5 기록입니다. 추가 실기·재제출·드라이버/서비스/보안·펌웨어 변경 없음. 아래는 이전 기록입니다.

## 최신 — 버스 응답 조회 후보와 활동 스냅샷 분리 / 2026-11-07 한국 시간

[CHARGER_READBACK_AND_PROJECTION.md](CHARGER_READBACK_AND_PROJECTION.md)를 먼저 읽습니다. 조건부 EC 모델에서 장치·레지스터를 받아 word 읽기 상태가 성공일 때 수신값을 복사해 반환하는 별도 후보를 분배표·bank stub과 연결했습니다. 실패는 모두 1인 word로 축약돼 정상 같은 값과 구분하지 못하며 요청 순번·상세 상태가 없습니다. 기존 일반 중계의 첫 송신 오류 가림·신선도 문제는 여전합니다. 고정 보호 getter·실행 승인·현재 부품 식별이 아니며 범용 조회 요청은 만들지 않았습니다.

정책 동작 비트→갱신 표시→상태 생산자→EC 페이지 읽기의 활동값 투영도 연결했습니다. 앞선 충전기 쓰기는 상태 미검사이며 여러 조건이 같은 값을 만들어 보호 모드/80·75 임계값이나 적용 성공을 역산할 수 없습니다. 알려진 엄격 Windows callback 네 개는 다른 필드를 선택합니다. ACPI 일반 배터리 상태 정규화는 별도 비교이며 host offset을 내부 주소로 가정하지 않습니다. 겉보기 모드 포인터 하나는 코드 메모리용으로 분리했습니다.

다음은 보호 모드 또는 충전기 읽기 결과를 오류 보존 조회에 제공하는 기존 고정 생산자/처리자 연결입니다. 고정 제조사 ID 조회의 scratch 소비는 옵션 read-back이 아닙니다. 소비자가 미확정인 별도 callback 기록표는 항목 위치로 명령 번호를 정하지 않습니다. 새 요청·live backend·제어·OEM 시험·단발 예약 접근 없이 Unsupported를 유지하며 같은 FF/잠금 후보 재분석보다 새 상태 생산자 근거를 우선합니다.

private cache는 20261107/protection-state-projection-next(하위 policy-flags-independent), charger-state-readback-next(하위 read-index), legacy-charge-dispatch-next, charge-state-source-integration-next입니다. 통합 독립 검산 25개 통과. 앱·테스트·EXE·기존 ZIP 미변경, 이번 빌드·단위 테스트 미실행이며 437/85·경고오류0은 이전 5d77df5 기록입니다. 추가 실기·재제출·드라이버/서비스/보안·펌웨어 변경 없음. 아래는 이전 기록입니다.

## 최신 — 오류 보존 경로와 보호 모드 생산자 분리 / 2026-11-07 한국 시간

[EC_FRESHNESS_AND_ERROR_PATHS.md](EC_FRESHNESS_AND_ERROR_PATHS.md)를 먼저 읽습니다. 일반 중계는 첫 대기 EFI_NOT_READY로 새 게시를 하지 못한 뒤 이전 작업이 끝나 두 번째 대기가 성공하면 기존 데이터를 정상으로 복사할 수 있습니다. 소스가 허용하는 조건부 사건 순서이며 실행·에뮬레이션·실기 관측이 아닙니다. EC의 선택한 바이트 읽기는 결과 한 바이트만 갱신하고 독립 요청 순번이 없습니다. 중계 복사 10바이트를 전부 신선한 상태로 해석하지 않습니다.

첫·두 번째 대기 오류를 모두 보존하는 별도 helper와 등록 callback 네 개를 연결했습니다. 보호 모드의 범용 주소 읽기와 다르게 고정 상태 페이지를 읽습니다. 고정 비트 하나는 EC 생산자·DSDT ACEX/PWRS/_PSR에 맞는 AC 전원 상태입니다. 공통 제공자의 오류 축약·외부 ACK는 여전하며 읽기 후 쓰기 경로는 제외합니다. 현재 WSABI 세 변형의 같은 Global mutex는 협력 호출자의 일반 전체 교환을 감싸지만 모든 native/ACPI/펌웨어 호출자 배제나 응답 신선도·송신 오류 복구는 아닙니다. 원본의 무한 대기·일부 해제 누락을 앱에 복제하지 않습니다.

다음은 오류 보존 조회가 읽는 페이지에 보호 모드가 반영되는 생산자 또는 별도 전용 조회 생산자를 찾는 것입니다. 모드·임계값의 독립 상태와 현재 경로 적합성이 연결되기 전 요청·live backend·제어·OEM 시험을 추가하지 않습니다. host offset과 내부 주소를 숫자로 대응시키지 않고 기존 단발 예약은 접근하지 않습니다. 같은 FF/잠금 후보의 반복 세분화보다 새 보호 상태 생산자 근거를 우선합니다.

private cache는 20261107/bridge-status-alternatives-next(하위 strict-reader-callbacks), ec-mailbox-lifecycle-next(하위 independent-xrefs), windows-exchange-coordination-next(하위 native-independent), readback-freshness-integration-next입니다. 통합 독립 검산 46개 통과. 앱·테스트·EXE·기존 ZIP 미변경, 이번 빌드·단위 테스트 미실행이며 437/85·경고오류0은 이전 5d77df5 기록입니다. 실제 제어 Unsupported, 추가 실기·재제출·드라이버/서비스/보안·펌웨어 변경 없음. 아래는 이전 기록입니다.

## 최신 — 저장값 조회 후보와 WMI 중계 소스 연결 / 2026-11-07 한국 시간

[EC_READBACK_AND_WINDOWS_BRIDGE.md](EC_READBACK_AND_WINDOWS_BRIDGE.md)를 먼저 읽습니다. 조건부 EC 모델에서 범용 저장 바이트 읽기 경로를 찾아 보호 모드·임계값 조회 후보를 확보했습니다. 전용 보호 getter·충전기 적용 read-back·실행 승인이 아니며 인접 쓰기와 구분합니다. 특정 초기화 분기의 범위 지우기는 모드·임계값을 포함하지만 이후 복원이나 Windows 재부팅 지속성을 입증하지 않습니다. host EC offset과 내부 주소를 숫자로 대응시키지 않습니다.

저장된 P05 WMI→공유 프레임→dispatcher→등록 generic callback을 연결했습니다. 278바이트 할당의 17바이트 header 뒤 261바이트 backing이 있어 25바이트 frame 접근은 할당 안입니다. WMI Field는 21바이트/payload16 그대로이고 선택한 입력 10바이트·반환 10바이트가 들어갑니다. 추가 snapshot 4바이트는 WMI 제어 밖이며 항상 0이라고 가정하거나 프레임을 확대하지 않습니다. 공개 같은 모델 DSDT 길이도 맞지만 현재 장치 정체성은 아닙니다. Settings 2.2.0.18에 포함된 ModuleSABI의 LED·키보드 백라이트 JogMode 호출자는 형식을 지지할 뿐 새 EC 보호 setter의 sender·현재 DLL 선택의 증거는 아닙니다.

gate는 소프트웨어 상태이며 ACK·정상 반환도 신선한 응답이 아닙니다. 송신 결과가 다음 대기에 가려질 수 있고 ACPI mutex는 트리거만 감싸 전체 교환 직렬화를 보장하지 않습니다. 다음은 이 오류 전달·신선도·동시 접근 문제를 해결하는 기존 경로 추적입니다. 현재 경로 적합성과 독립 상태 조회가 입증되기 전 새 요청·live backend·제어·OEM 시험을 추가하지 않습니다. 기존 단발 예약은 접근하지 않고 앱은 Unsupported입니다.

private cache는 20261107/ec-mode-readback-next(하위 initialization-independent), windows-ec-contract-next(하위 gate-review), oem-ec-charge-sender-next, charge-contract-integration-next입니다. 통합 독립 검산 52개 통과. 앱·테스트·EXE·기존 ZIP 미변경, 이번 빌드·단위 테스트 미실행이며 437/85·경고오류0은 이전 5d77df5 기록입니다. 새 노트북 시험·자료 제출·드라이버/서비스/보안·펌웨어 변경은 없습니다. 아래는 이전 기록입니다.

## 최신 — 조건부 EC 해석에서 80/75 충전 보호 사슬 연결 / 2026-11-07 한국 시간

[EC_CHARGE_PROTECTION_CANDIDATE.md](EC_CHARGE_PROTECTION_CANDIDATE.md)를 먼저 읽습니다. 8051 호환 ISA와 하위48KiB 공통/상위16KiB bank 모델을 가정한 데이터 전용 해석입니다. 전환 stub, 업데이트 주소, 버전 응답, 별도로 확인한 USBwake sender의 역할이 모델과 맞지만 공식 chip/ISA 정의나 live image 검증은 아닙니다. 원본 명령어 실행·에뮬레이션은 하지 않았습니다.

내부 mailbox setter의 모드1→상한80/하한75, SBS0D 수치 polling→field0 cache, 동일 field0의>=80 억제/<=75+상태조건 재개, charger option/current/voltage 요청까지 연결했습니다. F151은 별도DesignCapacity/FCC 비율 경로라SOC와 구분합니다. charger word 바이트 순서를 독립 확인했고 공개 Linux v6.6 SBS/BQ24735 레지스터 정의와 대조했으나 해당 부품/Windows 호환성을 확정하지 않습니다. 쓰기 status를 검사하지 않는 software last-action flags는 실제 적용/read-back 증거가 아닙니다.

내부EC 메시지와WMI/SABI 번호는다릅니다. 현재SABI의generic 중계callback도등록지도와연결했지만 gate/길이/실행경로/신선한read-back은미확정입니다. 새 프레임·live backend·실험·제어코드를 추가하지 않았고 기존 단발예약은 접근하지 않습니다. 모드echo/ACK/일반완료를 보호상태로 표시하지 않습니다.

private cache는20261107/charge-payload-evidence-next,charge-smbus-trace-next(하위sbs-table-crosscheck),charge-controller-identity-next,charge-bios-ec-bridge-next,charge-version-anchor-next,charge-public-controller-sources-next입니다. 선택 구문 검산은모드27단언/312행,버스19/522,poll50/464,root통합66입니다. 앱·테스트·EXE·기존ZIP은미변경,이번빌드·단위테스트미실행,437/85 및경고오류0은직전5d77df5기록입니다. 실제제어Unsupported,추가노트북시험·재제출·OEM·예약·드라이버/서비스/보안·펌웨어변경없음. 다음은정확한Windows전달계약과안전한독립상태재조회가핵심입니다. 아래는이전기록입니다.

## 최신 — 미분류 영역의 EC 업데이트 분류 연결 / 2026-11-07 한국 시간

[EC_UPDATE_REGION_RESULT.md](EC_UPDATE_REGION_RESULT.md)를 먼저 읽습니다. 보유 P05 wrapper의 CAP 선택/전체 파일 전달→실제 AFU EC 옵션의 type3 선택과, 펌웨어 SMIFlash/1의16B header+1280개9B block-info 생산을 연결했습니다. type3인31개4KiB 페이지는 별도24B ROM-layout의124KiB 영역과 정확히 같고 분석대상96KiB를 포함합니다. 두 표는 독립 생산자이며24B→9B변환으로 부르지 않습니다. 주소관계도 원본16개entry에서 독립 검산했습니다. 실제 노트북의 runtime block-info/현재이미지 동일성은 미검증입니다.

AMITSE는 같은 영역을복사하고 현재getter의6+3바이트를raw P05ACJ062와직접비교한뒤조건부갱신합니다. 갱신버퍼내바이트변환과I/O쓰기·조각처리가있어원본전체가그대로기록된다고가정하지않고읽기전용query로실행하지않습니다. 6+3 getter는구성요소버전이지보호설정이아닙니다. helper112A8의300/301은graphics좌표문맥이며HII토큰으로해석하지않습니다.

Wrapper의ENE/SMSC라벨이나8051유사열은chip/ISA/bank/codebase증명이아닙니다. 실제AFU EC option callback은인접AMIEC검사함수가아니므로CAP의marker부재로갱신실패를판정하지않습니다. 현재자료로충전보호handler/read-back/Windows안전명령은미확정이며실제제어구현은막혀있습니다. 추측명령·갱신으로공백을채우거나유사자료재세분화를제어성공으로보고하지않습니다.

private cache는20261107/updater-component-selection-next,payload-component-consumers-next,firmware-component-consumers-next,updater-component-independent-next입니다. wrapper834행/22단언,AFU364행및독립261행,SBIOSIO559행,AMITSE7함수368행과ROM/block-info producer근거를보존했습니다. 제품/테스트/EXE/ZIP미변경,이번빌드·단위테스트미실행,437/85와경고오류0은직전5d77df5기록입니다. 추가실기·업로드·OEM/예약/드라이버·서비스/보안·BIOS변경없이Unsupported입니다. 아래는 이전 기록입니다.

## 최신 — 보유 x64 native SABI 드라이버 본문 검토 / 2026-11-07 한국 시간

[NATIVE_SABI_DRIVER_REVIEW.md](NATIVE_SABI_DRIVER_REVIEW.md)를 먼저 읽습니다. 같은 940X3G W7 Settings2.0.0.78의 SABI3x64/Sabi.sys(13,824B/SHA7a53b3fba3f82ede6fa688e531fbe7ec9e1ae329090c0afe0dcd64f65bd90f21)는 이미 보유한 원본이며 이번에는 미검토 driverbody를 분석했습니다. x64 Sabi3 DLL의 IOCTL과 연결한 분기는 입력>=26/출력>=16, 프레임16복사이며 정상 복사 경로의 Information16/완료 NTSTATUS는 buffer retrieval 성공 결과입니다. 길이·버퍼 조회 실패는 별도 오류로 완료됩니다. ACK/main/sub/배터리 상태는 driver가 판정하지 않습니다. DLL26/16/11과 WMI21/16을 구분합니다.

선택된 DeviceAdd/dispatch518행 독립 재생성, root의 exactsource3개 해시·기계어·DLL경로 검산 완료. caller가 port/selector/공유주소를 공급하는 일반 privileged 중계이며 실제 P05legacyselector binding은 미증명입니다. 설치/서비스 시작/driver로드/물리메모리·I/O 대체 조회를 하지 않습니다. INF의 자동시작 선언도 현 설치 상태·Win10 지원이 아닙니다.

현재2.2.0.18 명령 후보 중 미복구6개는 문자열 helper였고 GetCommand의 inline object/RTTI를 새로 복원했습니다. Settings 실행/LED/ExpressCache/OTP/CameraMic/절전 진입으로 배터리 계약은 없습니다. 기존287 직접대상/281 RTTI는 당시의 후보 집계이며 전체289슬롯·동적 등록 증명이 아닙니다. private cache: 20261107/driver-catalog-next,native-driver-boundary-next,native-driver-independent-next,inline-command-correction-next.

앱·테스트·EXE·ZIP은 미변경이고 이번 빌드·단위 테스트는 미실행입니다. 437/85 및 경고·오류0은 직전5d77df5의 기록입니다. 새 배터리 처리자·응답·read-back은 없어 Unsupported이며 추가 실기·업로드·OEM·예약·드라이버/서비스/보안 변경 없이 기존 프로그램을 유지합니다. 아래는 이전 기록입니다.

## 최신 — 전송 취소 callback 차단 수정 / 2026-11-07 한국 시간

[WMI_CANCELLATION_BOUNDARY_UPDATE.md](WMI_CANCELLATION_BOUNDARY_UPDATE.md)를 먼저 읽습니다. 순수 FrameExchange의 동기 Cancel이 채널 callback에서 막혀 timeout/cancel 결과를 반환하지 못하는 결함을 재현했습니다(새 회귀만 추가한 기존 코드 436통과/1실패). 채널 취소는 worker로 분리하고 `WhenAll(pending,cancellation)` 뒤에 token source와 busy 슬롯을 정리합니다. 결과 게시 전 관측한 caller 취소만 우선하며 늦은 callback 부수 효과를 기다리지 않습니다. 입력·응답·단발 정책·예약·권한·어댑터·앱 연결은 미변경입니다.

최종 C#437/Python85 통과, 전체 WPF 포함 솔루션 빌드 경고·오류0입니다. Linux WindowsDesktop task의 기본 MSB4062/BadImageFormat은 빌드 명령의 COMPlus_ReadyToRun=0 및 DOTNET_ReadyToRun=0으로 해소했습니다. 기존 workspace SDK와 NuGet cache를 재사용하고 DOTNET_CLI_HOME은 workspace 안의 쓰기 가능한 cache로 지정합니다. 독립 코드 검토 완료, fresh 로그는 reports/wmi-cancellation에 보존합니다. 개발 소스만 배포하며 현재 앱은 이 채널에 연결되지 않아 기존 프로그램 교체·새 노트북 시험·업로드가 필요하지 않습니다.

병행 확인한 raw 영역의 P04/P05 차이 10바이트는 새 배터리 명령 근거가 아닙니다. 비공개 cache는 20261107/raw-gap-identity-next 및 cancellation-fix입니다. MICOM/8051/칩 정체성을 추정으로 확정하지 않습니다. 실제 보호 상태·제어는 미구현/Unsupported이며 다음 구현에는 적용 가능한 처리자와 신뢰할 응답·재조회 근거가 필요합니다. 아래는 이전 기록입니다.

## 최신 — 실제 P04ACJ 원본과 P05ACJ 비교 / 2026-11-06

[P04_P05_FIRMWARE_COMPARISON.md](P04_P05_FIRMWARE_COMPARISON.md)를 먼저 읽습니다. 실제 940X3G W7 목록의 BAIN-A0010A03.ZIP을 확보했습니다. 13,355,153바이트/SHA `7433986a2e29b9ff806300272e6293762227839e3f497d2555550d69a5e0c62f`이며 ZIP CRC·경로와 CAP/BIN/wrapper의 동일 payload를 확인했습니다. 목록 2개와 컨테이너 3개를 독립 펌웨어로 세지 않습니다. Version 공백·NoVerify·BOM 날짜는 현재 설치 BIOS·Windows 10 지원의 검증이 아닙니다. 비공개 원본은 `20261106/manual-catalog-delta-next`, 비교 출력은 `firmware-history-source-next` / `p04-hii-delta-next`, 독립 검산은 `p04-comparison-root`에 있습니다.

Provider/Legacy/AlwaysOn/SwSmi의 선택 코드·데이터와 provider 초기화 포인터 21개가 같지만 전체 이미지에는 timestamp·버전 문자열·unwind 정보 차이가 있습니다. 전체 의미 동일성을 주장하지 않습니다. 실제 코드가 달라진 Wireless와 SetupWin은 P04 경로를 새로 복원했으며 기존 12/13/69/6A 및 7C 등록입니다. 검토한 경로에 새 65/66 처리자나 typed bit3 writer는 없습니다.

P04 HII는 독립 token 복원 후 11 package / 12,415 opcode / 2,640 statement를 확인했고, 보호 문구의 표준 statement 참조는 P05와 같이 0개입니다. Varstore 선언 121개·vendor 원시 opcode 34개는 같고, P05의 544바이트/32 opcode 증가는 PCIe LTR 질문 8개입니다. 동적 화면·callback·현재 변수·전체 기능 부재는 미검증입니다. MHT의 저전압 복귀 항목은 상한 계약이 아니며 개인명·승인 명단·원문은 공개하지 않습니다.

새 버전 자료는 확보했지만 현재 모델 보호 조회·쓰기 계약은 여전히 미확정입니다. code/tests/EXE/ZIP은 미변경이고 이번 빌드·단위 테스트는 미실행입니다. 436/85와 경고·오류 0은 코드 커밋 750994c의 이전 기록입니다. 새 실기 시험·업로드·OEM 호출·예약 접근·BIOS 설치/다운그레이드 없이 Unsupported를 유지합니다. 다음 실제 구현에는 적용 가능한 배터리 처리자와 신뢰할 응답·재조회 근거가 필요합니다. 아래는 이전 기록입니다.

## 최신 — 남은 직접 호출·삭제 호출자·SSDT 대응 감사 / 2026-11-06

[REMAINING_QUERY_PATHS_REVIEW.md](REMAINING_QUERY_PATHS_REVIEW.md)를 먼저 읽습니다. provider의 열린직접함수8개(DB4,1B94,2150,230C,4C74,5AEC,5B2C,5CC4)를 buffer쓰기/주소유래/호출순서로대조했습니다. 5B2C의30B수신은caller의descriptor와분리돼등록뒤에수행되며,내부30B는WMI16payload규약이아닙니다. sourceI/O함수는실행하지않았습니다. 4C74 key의producer는SecMemoryInfo의기존/25B구성데이터게시로연결했으나전체runtime producer별칭의부재는미검증입니다.

기존5모듈에새typed unregister/65·66삭제descriptor는없어공개삭제API가능성과실제삭제관측을구분합니다. SecLagacy외부80/82는구성I/O보존·변경/복원,81은기존interface+20이며frame5843sub와다른namespace입니다. actualWindowsdriver경로를입증한것이아니고대체query로실행하지않습니다.

publicSSDT4↔capsuleCpu0Ist/CpuPm/SataTabl/IsctTabl의54MethodOp쌍을독립검산했습니다. 전체표차이227/35/0/7byte는CPU Package데이터도포함하므로전체의미동일X. ECMD는public에도있지만caller가Store후호출하므로읽기전용보호조회로채택못하며본문/binding미해결입니다. privatecache: initializer-direct-callees-next,unregister-caller-next,legacy-gateway-next,vendor-config-next,acpi-template-selection-next.

새배터리handler/read-back/실제설정관측은없습니다. 검토한직접경로의같은자료재세분화를기능진전으로보고하지않고,실제구현에는새현재모델/BIOS별handler·응답근거가필요합니다. code/tests/EXE/ZIP미변경,이번빌드·단위테스트미실행(436/85는직전기록),새실기/자료재제출/OEM/예약접근없이Unsupported입니다. 아래는이전기록입니다.

## 최신 — 조회 테이블·캡슐 ACPI와 요청 범위 보강 / 2026-11-06

[FIRMWARE_QUERY_BOUNDARY_UPDATE.md](FIRMWARE_QUERY_BOUNDARY_UPDATE.md)를 먼저 읽습니다. provider 생성자A04는 main-group capacity1/그룹당256슬롯을 준비하고 lookup8F4는 sub WORD 상한 검사 없이 계산합니다. 공개unregister954는 callback/context 일치 후 슬롯을 지우며, 실패 데이터FF/ACKAA와 펌웨어 정상0은 Windows HRESULT와 별도입니다. 선택된SecLagacySabi81 중계에도 sub상위byte검사는 없습니다. 실기취약점/실제이미지/전체alias 증명으로 확대하지 않습니다.

이 근거로 순수 encoder의 MaximumSupportedCommand를0xFF로 줄였습니다. UInt16 wire field·payload16·frame21·WMI MethodId32는 유지하고 binder/raw frame/FrameExchange의 공유 준비 경계에서0x100/165/FFFF를 가짜 의존성 호출 전에 거부합니다. 새 통합 회귀1개를 추가했고 기존 범위 밖 성공 fixture만 허용 범위로 바꿨습니다. decoder/단발정책/예약/권한/컨트롤러/앱 연결은 미변경입니다. 허용 범위가 명령 승인이나 실제 지원을 뜻하지 않습니다.

캡슐 ACPI DSDT1/SSDT15를 새로 분리했으며 공개 DSDT와 전체133byte가 달라도 배터리7+WMI2 MethodOp packet9쌍은 정확히 같습니다. PNOT는CPU알림,ECMD는미해결입니다. GUID 미복구28개에 대한 포인터/RIP/한정상수주소 전파에서도 새 소비자는 없습니다. 기존범위/복구를 실제 조회 성공으로 재보고하지 않습니다. private cache: provider-table-mutations-next,guid-indirection-next,battery-acpi-alternative-next(iasl은tools/iasl).

최종C#436/Python85통과,솔루션/portable빌드경고오류0입니다. 현재 보호 상태와65 handler/read-back은 여전히 미확정입니다. source-only 배포로 기존 프로그램을 유지하고 추가 노트북 시험·재제출·OEM 호출·예약 접근 없이 Unsupported입니다. 아래435/85 등은 이전 기록입니다. 아래는 이전 작업입니다.

## 최신 — 간접 등록·flag 별칭·동적 화면 후속 감사 / 2026-11-06

**추가 공식 원본:** 같은 Model940X3G의 실제 A1/W7 목록4개에서 Settings2.2.0.21/BASW-84270A5H 및2.0.0.78/BASW-83876A1L을 확보했습니다. 원본2개·추출912파일 해시 재검산 완료. private cache는 `20261106/target-legacy-catalog-next` 아래입니다. W7의 CmdServer/SUS1.0.5.7은 SHAaf60885562766d1cbc8d5886b986b9918738dae084c934e511438c7381c3628f로 기존 비교650f와 실제 코드가 다릅니다. 새getter FEC0→CC20의16byte/0B bit3·AL gate→같은buffer65, 정상반환1·소프트웨어0/1/2·Cmd지원메뉴/캐시를 직접 연결했습니다. 동일 버전의 다른 변형/RVA를 혼합하지 않습니다. 새현재계열 과거caller는 확보했지만 Win10/P05ACJ handler/read-back은 여전히 미확정입니다.

A1의 SUS/Sabi3/wsabi는 WB2.2.0.18과 같은 SHA입니다. 바뀐 ModuleBatteryMgr의 새ReInstall은 Windows전원계획/manager복구이며, CommandMNPowerManagement26 factory는 동일하고 관련text차이는rdata주소이동으로 대조했습니다. 원본/서버응답/디스어셈블리는 저장소·배포에 넣지 않습니다. 원본앱의SetCountFile에는조건부setter경로가있어 읽기전용진단으로실행하지않습니다.

[BATTERY_PROTECTION_ACCESS_FOLLOWUP.md](BATTERY_PROTECTION_ACCESS_FOLLOWUP.md)를 먼저 읽습니다. provider 초기화21개+helper2개 본문의 typed 등록 호출21곳에서 main5843 descriptor 후보56개를 복원했고65/66은 없습니다. opaque call/별칭/다른 하위 함수·외부·동적 경계가 남아 실제/전체 등록 부재를 뜻하지 않습니다. d32 프로토콜은 SecSwSmiDispatch의 byte-selector/24바이트 테이블로 SABI의 UInt16 main/sub/16바이트 테이블과 구분했습니다.

known4consumer의 lookup출력11개와 다른6모듈8개 same-offset 호출을 감사했지만 새 typed bit3 writer는 없습니다. flags=interface+30..34=parent+40..44이며 parent+30은dispatch slot입니다. AMITSE의 GUID stack조립 consumer와 HII vendor34개/Setup 동적문자열 helper를 추적했지만 배터리 question/필드/handler 연결은 없습니다. 현재2.2.0.18의158PE ordinary/delay import에도 BLE 이름은 미관측이나 동적/ordinal 부재 증명은 아닙니다.

정적 후보를 실제 설정·지원으로 승격하지 않습니다. 앱/EXE/기존ZIP 미변경, 이번 빌드·단위 테스트 미실행, 기존435/85는 이전 기록입니다. 추가 노트북 시험·재제출·OEM 호출·예약 접근 없이 Unsupported입니다. 다음 실제 구현에는 새 모델별 handler/응답·재조회 계약을 연결하는 구체적 근거가 필요하며, 같은 후보를 반복 세분화해 기능 진전으로 보고하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 현재 SUS 후속 처리·전체 FV·제조사 매뉴얼 대조 / 2026-11-06

[CONTROL_CONTRACT_CLOSURE_REVIEW.md](CONTROL_CONTRACT_CLOSURE_REVIEW.md)를 먼저 읽습니다. 현재 Settings 2.2.0.18의 SUS 1.0.6.1 x86/x64를 각각 해시로 고정해 후속 helper를 대조했습니다. `conf.ini`의 팝업 카운터·다시 묻지 않기 읽기/쓰기이며 setter 반환1·wrapper 0x63은 검증된 보호 상태 재조회에 조건부가 아닙니다. SOSI는 배포 디렉터리이고 실제 로더 선택 이름은 SABI3/WSABI/SABI2.dll입니다. 비교 SUS 1.0.5.7의16바이트 배치를 혼합하지 않습니다.

P05ACJ 전체7 FV/466 FFS를 검사했고 기존 FV04 밖232파일·46개 IA32 PE를 추가 확인했습니다. 390개 표준 압축 섹션을 별도 디코더로 해제해 전체231개 PE 섹션 해시를 7-Zip 출력과 맞췄습니다(고유 PE 해시229개). 새65/66 등록·bit3 writer는 미확정입니다. 기존34/6/10은 새 발견이 아니며 raw262144바이트·간접/동적/외부 경계는 남습니다. USB bit4/67/68의 양측 관계는 한정 대조됐지만 배터리 근거로 확대하지 않습니다.

같은 Model940X3G WB 배포 목록의 공통 Win8.1 매뉴얼을 확보해 전원 안내·잔량 보정과 충전 상한을 구분했습니다. 추출 텍스트와 관련 영문2쪽에서 상한 설명을 찾지 못한 것은 기능 부재의 증명이 아닙니다. 원본·전체 텍스트·디스어셈블리는 저장소 밖 비공개 캐시에만 보존합니다.

앱/테스트 코드/EXE/기존 ZIP은 미변경이고 이번 빌드·단위 테스트는 미실행입니다. 435/85와 경고·오류0은 직전 프로그램 검증 기록입니다. 문서·정적 근거만 갱신하며 새 프로그램·노트북 시험·자료 재제출·OEM 호출·예약 접근·드라이버/서비스/보안 변경 없이 Unsupported를 유지합니다. 다음 실제 제어 구현에는 현재 모델 배터리 처리자·선행 조건·응답 의미·신뢰할 설정 read-back을 연결하는 새 근거가 필요합니다. 아래는 이전 기록입니다.

## 최신 — 현재 계열2.2.0.18 원본 확보·설명 반영판 / 2026-11-06

[CURRENT_MODEL_OEM_EVIDENCE_UPDATE.md](CURRENT_MODEL_OEM_EVIDENCE_UPDATE.md)를 먼저 읽습니다. 실제 OS응답A1/W7/WB를근거로문서화된WB카탈로그를조회해 Model940X3G의 Settings2.2.0.18→BASW-84270A4N.ZIP을받았습니다. 원본73237618바이트/SHAa709e49804b02f3441ef063a849c11c4c16a632a3cdf2eb6c5667bfe30d5a216. privatecache는 /workspace/.cache/ativ-command-research/20261106/target-settings-2.2.0.18, 카탈로그원문은인접swupdate/target-os-resolution입니다. 원본실행·기기/SN/예약접근·환경변경없음.

x64Sabi3는기존사용자제공SHA09a971...와일치합니다. ModuleBatteryMgr는Windows전원계획/설치/WOL,ModuleBatteryToast는타이머ID관리,ModuleSABI는별도lazyCore전송으로확인범위에서BLE처리계약을복구하지못했습니다. server/eventplugin13/16개·289명령중일부미해결은전체기능부재로확대하지않습니다. 새배포원본과현장치지원·실제Win10선택은별도입니다.

앱기본오프라인설명에현재계열원본연결과비교2.0분석을표시하고검증된FF의분류/입력동등성미확정설명을추가했습니다. parser/상태/opaque디코더/요청/하드웨어권한/실험/제어는미변경. 최종C#435·Python85통과,솔루션/portable빌드경고오류0. 새프로그램/일치소스/체크섬은OEM-CALLER-EVIDENCE 이름으로제공,원본DLL은제외합니다.

P05새추적에서도bit3 writer/배터리처리자는확정못했고generic5byte setter가열려초기7F불변을입증못합니다. 다음제어구현에는현재firmware처리·지원flag·신뢰할read-back의추가정적근거가필요합니다. 기존자료/노트북/OEM반복·예약·드라이버/서비스/보안변경을요청하지않고Unsupported유지. 아래는이전기록입니다.

## 최신 — OEM 메뉴·상태·전송의 한정 연결 완료 / 2026-11-06

[OEM_UI_SUPPORT_CONTRACT_REVIEW.md](OEM_UI_SUPPORT_CONTRACT_REVIEW.md)를 먼저 읽습니다. 저장ZIP과주요모듈SHA일치·SUS실바이트독립감사를완료했습니다. 지원판정은getter반환/상태2→지원캐시→SUB_PM_BLE→PROGRAM_PRIVILIGE/MUITEST 로컬속성→PM_BLE비영의child뷰/헤더생성으로연결됩니다. PROGRAM_PRIVILIGE 생성자는미확정이며관리자조건으로명명하지않습니다. 상태2는ViewUpdate와별도nonzero-flag setter분기에서다르게그려질수있고(후자의lifecycle미확정), UI선택값도명령핸들없어도로컬에기록돼read-back증거가아닙니다.

정밀화: tail15는0B뒤호출자가덮지않는내용일뿐비영/다른payload라는증거가아닙니다. setter반환1은read-back비교에조건부가아니지만후속6000/6310helper전체는미완료여서부수효과/모든읽기부재를주장하지않습니다. Server/Wrapper의자체Init반환1도module/hardware성공동치아닙니다. 실제Win10검색/보고버전과현재모델65/66처리계약은미확정입니다.

이번사용자요청은분석재개라코드/테스트/EXE/기존ZIP을변경하지않고문서만갱신했습니다. 빌드·테스트미반복,435/85는이전기록. 다음정적근거는현재모델적용OEM버전또는P05ACJ처리계약이어야합니다. 같은기록/첫FF/모델문자열로빈간극을메우지않고추가OEM/업로드/관리자반복/예약/드라이버/서비스/보안변경없이Unsupported유지. 아래는이전기록입니다.

## 최신 — 원본 확보·호출자 중간 분석 저장 / 2026-11-06

사용자 요청으로 작업을 중지·저장했습니다. [SETTINGS_CALLER_ANALYSIS_HANDOFF.md](SETTINGS_CALLER_ANALYSIS_HANDOFF.md)를 먼저 읽습니다. downloadcenter 허용 적용 후 BASW-83876A21.ZIP을HTTP200/126414820바이트/SHAa501fde3b9870e3840d1b4561255c70e3cece4e9426c1070ff8481446d8ba3b7로 확보했습니다. ZIP CRC/경로와 Win7·실제Win8 MSI/파일 버전2.0.0.89를 확인했습니다. 원본과 모든 중간 디스어셈블리는 저장소 밖 비공개 캐시에 보존하며 새 환경 초안이나 환경 게시를 하지 않았습니다.

SUS/Cmd의 배터리 getter·setter·지원 메뉴 캐시와 조건부 쓰기를 정적으로 찾았습니다. 중요한 차이는 선행0B 응답의 같은 버퍼에서 첫byte만80으로 바꿔65를 호출한다는 점입니다. 과거80+zeros 단발과 입력/순서 동등성을 확정하지 않습니다. FF/선행 조건 오류를 합친OEM상태2는 현재장치지원판정이 아니고, setter성공반환·소프트웨어캐시는read-back이 아닙니다. 940X3G 문자열의 일반모델분류도 BLE지원allowlist로 입증되지 않았습니다.

다음은 저장한 hash/RVA/변형의 독립 교차 검토와 UI 메뉴/상태 연결을 마무리하는 작업입니다. 사용자 재제출·노트북 반복·추가OEM·예약 접근 없이 진행합니다. 원본실행/드라이버/서비스/보안변경금지, 실제제어Unsupported. 앱/도구/테스트/EXE/기존 ZIP은 미변경이고 빌드·테스트를 이번에 실행하지 않았습니다(435/85는이전기록). 아래는 이전 단계 기록입니다.

## 최신 — 실제 ZIP 최종 호스트·접근 초안 / 2026-11-06

[SETTINGS_BOM_PACKAGE_UPDATE.md](SETTINGS_BOM_PACKAGE_UPDATE.md)의 최상단 후속을 먼저 읽습니다. 게시 후 org.downloadcenter 허용은 정상 적용됐고 기록된 실제 요청은302로 downloadcenter.samsung.com의 정확 BASW-83876A21.ZIP 경로를 반환했습니다. 최종 URL은 쿼리 없는 공개 주소이며 비공개 redirect/access 기록과 문서에 보존했습니다. 최종 호스트 HEAD는CONNECT403, ZIP·부분파일·바이트/해시·내부caller는 미확보입니다. 정확 파일명 GitHub 질의4개도 새 고정 미러 연결을 제공하지 않았습니다. 코드 검색은 로그인 요구이므로 완전 검색 결과로 취급하지 않습니다.

기존 게시된6호스트를 보존하고 downloadcenter.samsung.com 하나만 추가한 초안을 저장·재조회했습니다(saved/requires_publish=true, revision2). 프리셋/스크립트/저장소/요구사항 보존, 환경미게시. 사용자 게시 후 현재 적용 확인 → 문서/캐시에 이미 기록된 최종 ZIP 목적지 정상 취득 → 수신 길이/SHA/컨테이너 → 원본 비공개 정적 분석으로 재개합니다. 같은 ORCA/BOM 조회·추측 URL·중계·삼성 코드 실행을 반복할 필요가 없습니다.

이번에는 문서·접근 증거만 변경했고 앱/개발도구/테스트/EXE/기존 ZIP은 유지합니다. 빌드·테스트를 반복하지 않았으며85/435는 이전 기록입니다. 새 다운로드·노트북/OEM 시험·업로드·예약 삭제 불필요. 실제 제어Unsupported. 아래는 이전 기록입니다.

## 최신 — Settings2.0.0.89 실제 BOM·정확 ZIP 식별 / 2026-11-06

[SETTINGS_BOM_PACKAGE_UPDATE.md](SETTINGS_BOM_PACKAGE_UPDATE.md)를 먼저 읽습니다. 게시 후 appmanager 허용 적용을 확인했고 실제 BOM2개를200으로 확보했습니다. 길이426679/488124, SHAac93fcf335218ad1a5b34cb57a92b58a2fb9e67be3d415683c229bac79848f46 / 116e0e2d84bd44d2d4024bd10c17f281b78717e61a03e6e3fad094c55d6509dc입니다. 둘 다 비교930X5J/Win7 문맥의 Easy Settings2.0.0.89 → BASW-83876A21.ZIP을 가리킵니다. 동일 Settings 항목의 중복이며 독립 바이너리 두 개의 증거가 아닙니다. FileVer/크기/TestYes는 원본 무결성·시험 통과·현재 모델 지원을 뜻하지 않습니다.

개발용 stdin 응답 검사기에 별도 BOM16,384노드/깊이16/Item256 상한과 구조·privacy·전체 성공 후 수치 보고를 구현했습니다. 기존 SOAP/JSON 상한은 유지합니다. 실제 BOM의 전체 Item40/45·직접 위치25/30·비교 후보1/1이며, FURL missing15개씩과 빈Version17개씩·레이블 XML 줄바꿈을 허용하고 URL 내부 공백은 거부합니다. 새11개 포함 전체Python85개·실제응답10개 대조·독립검토 통과. 원본 XML·식별자·설치 인수는 저장소/배포물에 넣지 않습니다.

실제 ORCA ZIP 링크는302로 org.downloadcenter.samsung.com에 같은 파일명을 전달합니다. 목적지 HEAD는CONNECT403이고 ZIP바이트/해시·내부Win8모듈·caller는 미확보입니다. 실제 목적지 한 호스트를 추가한 새 초안을 저장·재조회했습니다(saved/requires_publish=true, revision2). 기존 게시된5호스트/프리셋/스크립트/저장소/요구사항 보존, 환경미게시. 사용자 게시 후 적용 확인 → 기록된 원본 ZIP 정상 취득·길이/해시/컨테이너 → 비공개 정적 분석으로 재개합니다. 추측 URL·중계·설치/삼성코드 실행을 사용하지 않습니다.

C#/EXE와 기존 ZIP을 유지하고 새 개발 소스만 별도 제공합니다. 추가 노트북 시험·TXT/DLL 재제출·시리얼·Samsung Update/Export·관리자/OEM 반복·예약 삭제는 필요하지 않습니다. 현재 충전 제어Unsupported. 아래는 이전 기록입니다.

## 최신 — 공개 모델 카탈로그·오프라인 응답 검사 / 2026-11-06

[SAMSUNG_UPDATE_CATALOG_REVIEW.md](SAMSUNG_UPDATE_CATALOG_REVIEW.md)를 먼저 읽습니다. 게시 후 ORCA 허용을 확인했고, 실행 없이 공개 모델 검색 → 공개 ModelCode → 레거시 카탈로그 경로를 검증했습니다. 사용자 시리얼/DMI는 사용하지 않았습니다. NP940X3G 모델116개·NP930X5J 모델36개 검색은 성공했습니다. 현재 계열의 지원 OS 및 시도한 W8 카탈로그는 서비스404이고, 비교 NP930X5J-S02US의 W7 카탈로그는 SUCC/HDM.ITEM2입니다. 후자는 목록 XML 위치이며 Settings2.0.0.89 실파일이나 현재 ATIV의 충전 지원을 확보한 결과가 아닙니다.

새 stdin 전용 개발 도구는 HTTP 상태와 서비스 성공·명시적 빈 목록·HDM null·오류를 구분합니다. 입력2MiB/깊이32/노드8192/항목2048, 중복/DTD/entity 거부, 부분 수치 폐기, 원문·식별자·URL 비노출, 모든 하드웨어 권한false입니다. 합성 fixture 테스트14개를 포함해 전체 Python74개 통과, 실제 캐시 응답8개 분류·수치·해시 대조와 독립 코드 리뷰 완료. 원본 응답은 비공개 캐시에만 보존합니다.

실제 BOM 링크의 호스트 appmanager.samsungmobile.com은 현재 미허용/HEAD403입니다. 이 한 호스트만 추가하는 초안을 저장·재조회했습니다(saved/requires_publish=true, revision3). 이번에 임시로 추가했던 미게시 bootstrapper용 org.downloadcenter 호스트는 제외하고, 기존 게시된 네 호스트/프리셋/스크립트/저장소/요구사항을 보존했습니다. 에이전트는 환경을 게시하지 않았습니다. 사용자 게시 후 적용 확인 → 실제 XML 두 개의 정상 읽기 → 버전/모델/파일명 확인 → 관련 원본만 실행 없는 정적 분석으로 이어갑니다.

C#/EXE와 기존 ZIP은 유지합니다. 새 개발 소스는 별도 ZIP으로 제공하며 실행에 필요하지 않습니다. 추가 노트북 시험·TXT/DLL 재제출·시리얼·Samsung Update 실행/Export·관리자/OEM 반복·예약 삭제는 필요하지 않습니다. 실제 충전 제어Unsupported. 아래는 이전 기록입니다.

## 최신 — NBR 원문 확보·2.0.0.89 비교 후보·삼성 인입 대기 / 2026-11-06

[SETTINGS_VERSION_SOURCE_REVIEW.md](SETTINGS_VERSION_SOURCE_REVIEW.md)를 먼저 읽습니다. 게시 후www.nbrchive.net 허용은current/enforced로 적용됐고 원문2페이지를200으로 확보했습니다. 기본 Python 헤더는HTTP403/1010, 같은HTTPS/호스트/프록시/TLS에서 일반브라우저헤더는200이며 로그인/챌린지/우회없음. 파일/해시와독립주장범위검토를비공개캐시에보존했습니다. 기존차단설정은재적용하지않았습니다.

#1은NP940X3G에Settings2.1.0.20이제공된다는기록, #39의2.0BLE탭/2.1·2.2UI제거는구형NP700Z3A문맥, #49하드웨어호출차이는저자추측입니다. #62/#63은NP930X5J-S02US Win7목록의EasySettings2.0.0.89 외부패키지→내부Win8 Settings2.0.0.89, 시험은구형Series7입니다. NP940X3K≠940X3G, NP930X5J≠930X3G이며현재모델/BIOS/Win10충전성공·명령계약은미확정입니다. 메뉴부재만으로지원부재/구버전설치성공을추정하지않습니다.

원문은정확Settings파일URL대신 http://orcaservice.samsungmobile.com/SWUpdate.aspx 와모델검색/Export를제시합니다. 독립공개검색16개에서도해당ZIP/파일명/SHA미확보. bootstrapper HEAD403이고현재호스트미허용이어서orcaservice.samsungmobile.com 한호스트만추가한새초안을저장·재조회했습니다(saved/requires_publish=true). 기존3호스트/프리셋/스크립트/저장소/요구사항보존, 환경미게시. 사용자게시후적용확인→원본응답/인입검증→실행없는배포메타데이터/패키지정적분석으로진행합니다.

앱/테스트/EXE/기존ZIP미변경, 빌드·테스트미반복. 새노트북실험/업로드/Export요청/설치/보안변경/OEM호출/예약삭제불필요. 현재제어Unsupported. 아래는이전기록입니다.

## 최신 — OEM 원문 접근 초안 저장·게시 후 재개 / 2026-11-06

[OEM_SOURCE_ACCESS_STATUS.md](OEM_SOURCE_ACCESS_STATUS.md)를 먼저 읽습니다. 새 공개 저장소/이슈/README 조사11질의와 후보 확인에서는 현재 모델 OEM 배터리 caller를 얻지 못했습니다. 명칭만 맞는 다운로드·신형/Android 도구를 사용하지 않았습니다. peilim/SamsungUpdate는 빈 저장소이고 BIOS 서비스 WSDL은 서버 오류 본문이어서 배포 기능을 확인하지 못했습니다.

기존 사용자 제공 NBRchive Settings/Easy Settings 원문의 정상HTTPS는CONNECT403. 현재 custom2호스트를 보존하고www.nbrchive.net 한 호스트만 환경 초안에 추가·재조회했습니다(saved/requires_publish=true). 설치/시작/저장소/프리셋/변수·비밀 요구사항은 보존했고 환경을 게시하지 않았습니다. 초안은 현재 적용이 아닙니다. 사용자 환경 게시 후 runtime/호스트 적용 확인→원문 날짜·모델/OS/Settings 지원/패키지 출처 검토→적용 가능한 원본만 비공개 정적 분석으로 이어갑니다. 포럼 실행/보안 변경 지시는 따르지 않습니다.

앱/테스트/EXE/ZIP은 미변경, 빌드·테스트를 새로 수행한 것으로 보고하지 않습니다. 현재 명령 계약미확정·제어Unsupported입니다. 원문/삼성파일 재제출·노트북 반복/관리자/OEM 시험·예약 삭제는 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — HII 표준 헤더 참조·시험 경로 구분 / 2026-11-06

[P05ACJ_HII_REFERENCE_UPDATE.md](P05ACJ_HII_REFERENCE_UPDATE.md)를 먼저 읽습니다. 고정 Setup HII 리소스333801/SHA53ec78bfce49bf65858d64aaadee9fbb31abf79088ee0c9b60c28783a6ddf527에 대해 개발용 bounded 인덱서를 구현했습니다. package11/Forms10/opcode12447/지원 statement2648/vendor GUID34이며11종 공통 헤더에서 배터리 수명 연장 참조0, USB CheckBox1·보정Ref1을 확인했습니다. vendor payload/동적/다른리소스 미폐쇄이고 visibility/부재/명령을 판정하지 않습니다.

입력1MiB/package64/opcode32768/depth64, 고정 hash 선검사·scope/길이 오류의 전체 결과 폐기·cap+1 파일 읽기·경로 비노출·모든 권한false를 적용했습니다. Python60개 통과. OFBD 배터리 신뢰성 시험 문자열 분기는 포트쓰기 helper로 연결되며 상한 계약이 아니므로 실행/포팅/대체 조회하지 않습니다.

C#/앱/기존 ZIP은 미변경이며 C# 빌드/테스트를 이번에 반복하지 않았습니다. CALLER-CONTRACT-REVIEW 유지, 새 개발 소스만 제공. 제한적인 새 공개검색3건도 모델별 계약을 제공하지 않았습니다. 보유 자료에서 현재 모델 caller→처리자→응답의 연결을 찾지 못해 제어 구현은 근거 부족으로 보류합니다. 다음 실제 구현 조건은 적용 모델이 확인되는 새 OEM 배터리 caller/지원 조건 또는 펌웨어 처리 계약입니다. 같은 기록/진단 반복·추가 OEM/업로드/예약 초기화 없이 Unsupported를 유지합니다. 아래는 이전 기록입니다.

## 최신 — Windows 호출자 대조·native11 의미 추정 제거

[WINDOWS_CALLER_CONTRACT_UPDATE.md](WINDOWS_CALLER_CONTRACT_UPDATE.md)를 먼저 읽습니다. 구형 OEM의 DLL 선택은 보고major>=6&&minor==1이고 두 DLL 모두5843/65·66을 전달합니다. 설치 ImageState/INI는 모델 가드가 아닙니다. 구형0B bit3 gate는 P05ACJ callback3908→flag getter7DC→초기7F와 조건부 연결되지만, 동적 setter/현재실기값은 미확정입니다. 0B gate는65조회·조건부66쓰기보다 뒤여서 OEM EXE를 진단으로 실행하지 않습니다. 사용자 과거FF는65응답이며0B flag와 혼합하지 않습니다.

확인한 실제 모델 caller는 여전히 없고, ConfigurationMonitor는 팬/정숙 기록, BatteryToast/PowerAudit는 메타데이터, Sabi3/wsabi는 일반 중계입니다. 제3자 hotkeys의 USB67/68·무선69/6A·키보드78 일부 일치는 배터리65/66 등록을 증명하지 않습니다. 모델명 표시도 지원 allowlist가 아닙니다. 같은 기록 재독으로 이 누락을 채우지 않습니다.

기존 Sabi3ReplyDecoder의0/1/FF 보호/지원 추정을 제거했습니다. API0·정확11바이트는UninterpretedPayload+Zero/One/FF/Other, 실패는NotInspected. 보호/상한null·권한false이며 public semantic enum 생성은Unknown으로 정규화합니다. enum 이름/숫자·시그니처는 유지하지만 동작은 의도적으로 변경했습니다. 앱/어댑터 참조는 없고 실제 OEM/WMI/요청/예약/제어 경로는 추가하지 않았습니다. C#435·Python48, 빌드0경고/오류입니다.

새 CALLER-CONTRACT-REVIEW ZIP에 수정 Core를 포함했고 이전 ZIP은 보존합니다. 새 노트북 시험/업로드는 불필요합니다. 다음 근거는 현재 모델/BIOS에 적용되는 OEM 배터리 caller·모델 선택 조건·처리 계약이어야 하며, 그전까지 실제 제어Unsupported를 유지합니다. 아래는 이전 단계 기록입니다.

## 최신 — 외부 등록 10개 복구·관측 원본 pin

[P05ACJ_EXTERNAL_REGISTRATION_REVIEW.md](P05ACJ_EXTERNAL_REGISTRATION_REVIEW.md)를 먼저 읽습니다. GUID 바이트 포함 34개 파일에서 직접 참조 6개(provider/bridge/외부 등록자4개)를 복구했습니다. 나머지28개는 직접 참조 미관측입니다. descriptor → LocateProtocol → register 흐름을 복구한 외부 등록10개는 Wireless12/13/69/6A, SwSmi78·67/68, AlwaysOn6D/6E, SetupWin7C입니다. 런타임 등록 성공은 미관측이며 계산/다른 볼륨/동적 등록을 닫지 못해65/66 미지원·미등록을 확정하지 않습니다.

67/68의 USB 문맥과6D/6E의 SecSleepType/설정은 배터리80/100의 근거가 아닙니다. 7C callback은498이며 협상/공유 구조 발견용입니다. 별도3408→4FC→ED4 경로는 인증·UEFI GetVariable/SetVariable을 포함하므로 읽기 전용 대체 조회로 사용하지 않습니다. HII 배터리 문자열 연결은 미확정입니다. 다음은 등록 지도를 기준으로 기존 Windows 호출자 기록과 적용 모델의 OEM 계약을 대조합니다. 유사 명령을 시험하지 않습니다.

개발용 p05acj 인입 검사는 관측 EXE의 길이5,822,368/SHA374c768a09211ce8da6e0812bde870e3b90957bf8b38e2289cac4dc52857e7fd를 먼저 대조한 뒤 PE를 검사합니다. ObservedSourcePayloadMatched는 제조사 진위·모델·명령 검증이 아니며 권한은 false입니다. 별도 오프라인 서명 수학검증과 이미지 digest 일치는 통과했지만 시스템 CA 체인·타임스탬프/폐기·Windows 정책이 미완료여서 전체 authenticodeVerified는 false로 유지합니다.

Python46개 통과. C#/프로그램/기존 ZIP은 미변경이므로 C# 빌드·테스트는 이번에 반복하지 않았습니다. 사용자의 직전판 실행을 수신했고 추가 업로드/시험/OEM 재호출/예약 삭제는 불필요합니다. 실제 제어는 Unsupported입니다. 아래는 이전 단계 기록입니다.

## 최신 — 원본 확보·P05ACJ 공통 실패 접두부 구현

[FIRMWARE_REPLY_EVIDENCE_UPDATE.md](FIRMWARE_REPLY_EVIDENCE_UPDATE.md)를 먼저 읽습니다. 사용자 환경 게시 후 두 원본을 정상 요청으로 확보하고 정적 분석했습니다. P05ACJ dispatch RVA9E6–9F8은 여러 실패 조건에 데이터20바이트를 FF+19zero로 만들고 ACK AA를 씁니다. 순수 디코더는 지원한 데이터16바이트의 FF+15zero 접두부만 비배타적으로 비교합니다. 과거 결과는 첫FF만 있어 전체패턴/실패원인/현재펌웨어 일치를 확정할 수 없습니다.

구형 OEM 호출자는65/80+10zero와66/81·80을 사용하지만 조회 오류를 무시해 FF도100% UI로 흐릅니다. 이를 상태 계약으로 적용하지 않습니다. HII의80/100 도움말은 있으나 해당토큰을 사용하는 표준 question은 관측하지 못했고 실제사용가능성을 입증하지 못했습니다. 다음은 확보한 이미지의 콜백 등록·연결 처리자를 정적으로 추적하는 것입니다. 새진단/재제출/OEM재호출/예약삭제/쓰기 없이 진행하며 실제제어는Unsupported입니다. 아래는 이전 단계의 기록입니다.

## P05ACJ/구형 BLE 원본 위치 확보·정상 접근 대기

[최신 원본 후보·검증·접근 조건](COMMAND_SOURCE_ARTIFACTS_AND_ACCESS.md)을 먼저 읽습니다. ACJ의 정확한 파일명은 ITEM_20140901_21421_WIN_P05ACJ.exe이며 고정SamsungBIOSTools 매핑/수집로그에서 확인했습니다. 같은 계통의 목록을 독립근거로 세거나 목록 해시를 EXE 해시로 오인하지 않습니다. 원본EXE·내부빌드·서명·모델목록은 미확보입니다.

별도NP-RV520 Battery Life Extender1.0.0.11은 고정LFS 포인터133바이트만 확보했고 실제객체는13,728,500바이트/SHA5e3be33df74283d00542777320519c3f5d5fb6a01bdcbd664d7d9e33ce2511fc입니다. 포인터는 바이너리가 아니며 현재ATIV 호환근거도 아닙니다. 개발용 오프라인 인입 검사기는 원본 무결성/컨테이너 구조만 확인하고 OEM진위·모델·명령 계약은 확정하지 않습니다.

현재sbuservice.samsungmobile.com·media.githubusercontent.com이 차단돼 두 호스트 추가 초안만 저장·재조회했습니다(status=saved/requires_publish=true). 설치/시작/저장소/프리셋 등은 보존했고 환경을 게시하지 않았습니다. 사용자 검토·저장·게시 후 원본 정상요청 재확인 → 바이트/해시/구조검증 → 실행 없는 정적분석으로 이어갑니다. 프록시 우회·설치/플래시·원본재제출·노트북반복/OEM추가실험은 없습니다. 앱·기존ZIP·요청/디코더/예약/제어는 유지하며 실제제어는Unsupported입니다. 아래는 이전 작업 당시의 기록입니다.

## 동일 P05ACJ 공개 ACPI 확보·명령 경로 분리

[새 정적 근거](P05ACJ_BATTERY_COMMAND_EVIDENCE.md)를 먼저 읽습니다. farjump/fwtr54ed1c555423babd4c4aa6c69ce95cdf0a4a68f4의 같은 수집 실행 metadata가940X3G/930X3G·NP940X3G-K03FR·P05ACJ.128.140819.dg를 명시합니다. 공개 Linux 자료로 현재 사용자 장치의 원문/Windows 실행과 구분합니다. DSDT71849바이트·SSDT4개 길이/체크섬을 확인하고 정적 디스어셈블·기존v7 바이트 파서로 검사했습니다. 원본/주소/식별자는 저장소·배포물에 넣지 않습니다.

공개WQ본문은 상수0x10, 중계는 같은168비트 Field에 Zero→Arg2→helper→Return입니다. 그 본문에는 명령 선택·FF 의미 판정이 없습니다. 표준 배터리 정보/상태의 별도GSSB/GSSW 경로와 _BTP 알림 임계값은 충전 상한으로 사용하지 않습니다. 다른SAM0428의0x7A/E9/91 계약도 현재ATIV에 대입하지 않습니다. 미해소 외부 메서드·동적 표 로드·다른 공개 장치라는 한계를 유지합니다.

다음은 적용 모델이 확인되는 OEM 배터리 호출자의 명령/응답 선택 또는 같은BIOS의 관련 처리 계약을 입증하는 출처입니다. 일반 중계/표준 상태 경로만으로 새 요청·디코더 의미·제어 어댑터를 추가하지 않습니다. 이번에는 정적 조사·기록만 변경했으며 실제 제어는 Unsupported, 기존실험/예약/앱/ZIP은 유지합니다. 원본 재제출·진단 반복·추가 OEM 호출은 요청하지 않습니다. 아래는 이전 작업 당시의 기록입니다.

## v7 실기 관측 수신·모델별 명령 계약 근거 확보

[최신 분석과 다음 계획](ACPI_V7_RESULT_AND_NEXT_PLAN.md)을 먼저 읽습니다. Literal Store1/Integer·SystemMemory·Matches21ByteFrame이며 입력/반환과 같은 Field/Region, 보조 Store와 다른 Field/Region 선언입니다. SingleDirectList의 앞뒤를 합치면 소스 배치는 Literal Store → Arg2 Store → 보조 호출 → Return입니다. 실제 초기화·덮어쓰기·입력 보존·SMI·FF 원인으로 확대하지 않습니다. 후보/보조 Parsed·실패 None, 기존 Partial과 참조6회는 유지됩니다.

다음 우선순위는 현재 모델·BIOS의 Windows 배터리 명령/selector/입력/응답 의미를 입증하는 정적 출처입니다. 저장된 서비스 wsabi는 호출자 명령을 포장하는 일반 중계이고 ConfigurationMonitor의 확인 문맥은 팬·정숙 모드입니다. 배터리 호출자의 선택·응답 분기를 적합한 보유 기록/공개 자료에서 추적하고 전송/모델/명령/입출력/상태 의미의 출처 대조표를 작성합니다. 실제 응답의 echo/전체 payload를 복원하거나 다른 모델·Linux 후보를 적용하지 않습니다. 근거가 확보된 부분만 순수 명세·합성 테스트로 고정하며 근거 없이 요청·디코더·제어 정책이나 새 반복 진단 도구를 추가하지 않습니다.

이번에는 분석·문서만 변경했고 v7 반복·관리자 비교·기존 자료 재제출·추가 OEM 시험은 필요하지 않습니다. 완료된 실험·예약 표식을 유지하며 제어는 Unsupported입니다. 아래는 이전 작업 당시의 기록입니다.

## 현재 구현 — Literal Store 대상·직접 구문 배치 v7 / 2026-11-05 한국 시간

[현재 구현·해석·실행 안내](ACPI_STORE_ROLE_UPDATE.md)를 먼저 읽습니다. v6 실기에서는 후보 입력/반환 Field의 SystemMemory·21바이트 선언 폭 일치, 보조 SystemIo와 다른 Region 선언, Store2회 중 Arg2/Literal 원천을 확인했습니다. v7는 남은 Literal Store의 직접 Integer/String/Buffer/Package 종류와 대상 Field의 공간·폭 범주, 입력/반환/해석한 보조 Store와의 Field/Region 관측 정의 관계를 분류합니다. Literal Store 수는 Field 여부와 관계없는 직접 구문 발생 횟수이고 정의 비교는 고유 후보를 사용합니다.

후보의 Arg2 Store·Literal Store·알려진 보조 호출·Return이 같은 직접 구문 목록에 각각 하나씩 관측될 때 앞뒤 관계를 요약합니다. 분기·반복·중첩 Store/호출·복잡한 피연산자는 Unknown, 복수 역할 후보는 MultipleCandidates이며 실제 실행 순서나 값/인수 대입·초기화·트리거 효과를 추론하지 않습니다. 원문 값·주소·이름·폭·구문 위치 번호는 내보내지 않습니다. 새64개 구문 기록 한계는 새 Store 역할 보고서에만 적용하고 기존 Flow·객체·Field 통로·FF 의미는 유지합니다.

새 배포 ACPI-STORE-ROLES의 **프로그램 ZIP 하나만** 새 폴더에 전부 풀어 일반 권한으로 실행하고 **Acpi-routing-v7 새 요약만** 확인합니다. 소스 ZIP은 실행에 필요하지 않으며 함께 풀지 않습니다. 기존 자료 재제출·v6 반복·관리자 비교·완료된 OEM 실험 재실행은 요청하지 않습니다. 같은 두 읽기 API·고정 DSDT/첫 SSDT·기존 상한과 무실행/무쓰기 경계를 유지합니다. v7의 실제 노트북 결과와 모델별 명령/FF 의미는 미확정이고 제어는 Unsupported입니다. 아래는 이전 작업 당시의 기록입니다.

## v6 실기 관측 수신·추가 Store 역할 분석 계획

[현재 결과와 다음 수용 조건](ACPI_V6_RESULT_AND_NEXT_PLAN.md)을 먼저 읽습니다. 사용자 v6 출력에서 root Arg2 저장/반환 Field 모두 SystemMemory·Matches21ByteFrame, helper Store SystemIo, 양쪽 Region 관계 DifferentObservedDefinitions를 확인했습니다. root Store2회/직접 Arg2 1회·Sources Arg2,Literal이며 같은 입력/반환 Field 정의 참조도 유지됩니다. 선언 비교는 실제 메모리/I/O·SMI·물리 영역 분리·FF 의미를 입증하지 않습니다.

다음 최소 구현은 남은 literal Store의 대상 역할·입력/반환/보조 Field 및 Region과의 관측 정의 관계, 직접 literal 구문 종류를 분류하는 것입니다. 필요하면 같은 직접 구문 목록에서 Store/보조 호출/Return의 위치 관계만 요약하고 분기·반복·중첩은 미확정으로 닫습니다. 실행 순서·값/인수 대입·초기화·트리거 효과는 추론하지 않습니다. 원문 상수·주소·이름·버퍼는 보고하지 않고 기존 수집/API/상한·무실행/무쓰기 경계를 유지합니다.

이번에는 결과 분석·문서만 변경했습니다. v6 반복·관리자 비교·기존 자료 재제출·새 OEM 시험은 필요하지 않습니다. Partial과 기존 Flow6회는 새 오류나 고유 객체 수가 아니며 충전 제어는 Unsupported입니다. 아래는 이전 작업 당시의 기록입니다.

## 현재 구현 — Field 통로 선언·입력 역할 v6 / 2026-11-05 한국 시간

[현재 구현과 실행 안내](ACPI_FIELD_CHANNEL_UPDATE.md)를 먼저 읽습니다. 사용자 승인에 따라 [v5 후속 계획](ACPI_V5_RESULT_AND_NEXT_PLAN.md)의 후보 Arg2 저장/직접 반환 Field 주소 공간·21바이트 선언 폭 범주, 후보 Store 원천 Arg0/1/2/literal/Other, 보조 Store와의 관측 Region 정의 관계를 구현했습니다. 반복 참조와 고유 후보를 구분하며 복수 동일 폭은 MultipleCandidates, 서로 다른 폭은 Mixed, 불완전·모호함은 Unknown으로 남깁니다. 비Field·미분류 대상을 버려 단일 일치를 만들지 않습니다.

기존 Flow 지표·ObjectReferences·직접 FF 의미는 유지합니다. 폭 일치나 같은 Region 선언을 바이트 배치·입력 보존·실행·물리 주소 동일성·SMI·충전 지원으로 확대하지 않습니다. 원시 폭·이름·주소·오프셋·길이·값을 보고하지 않고 실제 영역 접근·OEM/AML/DLL 실행·예약 접근을 추가하지 않습니다. 수집은 같은 두 읽기 API와 고정 DSDT/첫 SSDT이며 기존 상한을 유지합니다.

새 배포 ACPI-FIELD-CHANNEL의 **프로그램 ZIP 하나만** 새 폴더에 풀어 일반 권한으로 실행하고 **Acpi-routing-v6 새 요약만** 확인합니다. 소스 ZIP은 개발용입니다. 새 요약은 v5에서 없던 후보 공간·폭·Region 관계를 추가하므로 의미가 있으며 기존 자료 재제출·v5 반복·관리자 비교·완료된 OEM 실험 재실행은 요청하지 않습니다. 새 v6 실기는 미관측이고 제어는 Unsupported입니다. 이후 새 정적 근거를 기존 Windows/SABI 규약과 대조하되 모델별 명령 계약·FF 의미가 입증되지 않으면 제어를 활성화하지 않습니다. 아래는 이전 작업 당시의 기록입니다.

## 이전 개발 기록

## v5 실기 결과·필드 선언과 정적 프레임 통로 계획

[현재 분석과 계획](ACPI_V5_RESULT_AND_NEXT_PLAN.md)을 먼저 읽습니다. v5 사용자 출력에서 root 이름 참조 3/3 Field, helper 3/3 Mutex/Field·Store Field SystemIo, root Store(Arg2)/Return 동일 관측 Field 정의 참조를 확인했습니다. 두 root/helper 직접 참조 관계는 미확정입니다. 선언 종류 6/6 분류는 고유 객체 6개나 실제 데이터 전달 증거가 아니며 기존 Flow 미확정6 지표는 별도 보수적 검사로 유지됩니다.

사용자는 이번에 분석·보고·계획을 요청했습니다. 실행 코드/ZIP은 바꾸지 않았고 빌드/테스트도 반복하지 않았습니다. 다음 구현은 root 저장/반환 Field의 Region 종류·고정21바이트 프레임 대응 분류, directStore의Arg0/1/2/상수/기타 source-role, root/helper의same-observedRegion 정의 관계와 보고문구 정리입니다. raw주소/offset/length/값은 내보내거나 실제영역접근하지 않고 physicalalias/실행/값전파를 추정하지 않습니다. 구조 확인 뒤에도 모델Windows 배터리 명령/FF 의미는 별도 근거가 필요합니다. v5 반복/관리자 비교/원본 재제출·새 OEM 시험은 없고 제어는 Unsupported입니다. 아래는 이전 기록입니다.

## 이름 객체·Store/Return 참조 관계 구현 — v5

[구현 범위와 실행 안내](ACPI_OBJECT_REFERENCE_UPDATE.md)를 먼저 읽습니다. v4에서 관측한 root/helper의 이름 참조를 same-table 선언 종류와 정적 참조 관계로 분류합니다. 새 ObjectReferences는 기존 Flow/UnresolvedNameReferences/FF 의미와 분리합니다. kind 분류가 실제 runtime 형식·값·별칭·동일 데이터·실행 효과를 보장하지 않습니다.

관측 Buffer/단순 Name/Mutex/Event/OperationRegion 및 지원한 단순 FieldList만 읽고 원래 이름/주소/offset/length/rawspaceId는 출력하지 않습니다. 중복/Alias/External/object-vs-method/동적CreateField 가림은 보수적으로 미확정입니다. FieldList 전체 성공 전 typed prefix는 확정하지 않고 byte재검색도 없습니다. 새 본문 고유 참조 상한64는 새보고서LimitExceeded만 만들며 기존 root 구문/Flow/직접 FF를 폐기하지 않습니다.

수집은 같은 두 Windows API·DSDT/첫 SSDT이고 실제 I/O·영역/포트/driver/물리 메모리/registry·OEM/AML·예약·값/분기평가·하드웨어 쓰기는 없습니다. 새 배포 ACPI-OBJECT-REFERENCES/Acpi-routing-v5는 프로그램 ZIP 하나만 일반 권한으로 실행합니다. v4 반복/관리자 비교/기존 자료 재제출은 필요하지 않습니다. 새 v5 분석의 실기는 미관측이고 실제 충전 제어는 Unsupported입니다. 아래는 이전 기록입니다.

## v4 보조 본문 실기 확인·다음 구현 계획

[이번 분석과 계획](ACPI_V4_RESULT_AND_NEXT_PLAN.md)을 먼저 읽습니다. v4는 보조 해석 1/미지원 0/실패 None, Acquire·Release, helper Return 0/None·그 본문 범위의 literal FF 미관측입니다. v4의 구문 지원 목표는 실기 관측됐고 실제 FF 의미/충전 제어는 미확정입니다. root Return UnresolvedName·직접 Arg2 인수 0은 입력 미전달/잘못된 반환이 아닙니다. 미해결 6은 root+성공helper의 참조 횟수이지 객체 6개가 아니며 연결 Partial과 전체 namespace Partial을 구분합니다.

사용자는 이번에 분석·보고·계획을 요청했습니다. 실행 코드/배포물은 바꾸지 않았고 빌드/테스트를 반복하지 않았습니다. 다음 구현 우선순위는 same-table 관측 객체 Buffer/Mutex/Event/Field/OperationRegion의 종류 분류와 Store/Return의 정적 참조 관계입니다. 값/분기/별칭 평가·실제 I/O·주소 출력·OEM 호출은 없습니다. v4 반복/관리자 비교/원본 재제출은 필요하지 않습니다. 구체적인 수용 조건과 안전 경계는 새 계획을 따릅니다. 아래는 이전 기록입니다.

## v3 보조 본문 미지원 수신·확장 구문 v4

[현재 관측·구현·범위](ACPI_HELPER_SYNTAX_UPDATE.md)를 먼저 읽습니다. v3는 root Parsed·호출 1·직접 Arg2 인수 0·Return 1/UnresolvedName·보조 1/해석 0/미지원 1·미해결 참조 3입니다. 입력 미전달이나 잘못된 반환이 아니며 미해결 3은 root의 관측입니다. 현재 중단 opcode는 미확정이고 특정 Acquire로 단정하지 않습니다.

v4는 같은 수집/상한 안에서 표준 확장 AML 구문을 정적으로 소비하고 고정 실패 종류/공개 구문 이름만 보고합니다. raw opcode/위치/이름/주소/값/예외 원문은 출력하지 않습니다. Acquire timeout은 raw WORD2바이트이며 실제 대기/동기화/변환/필드 생성/Fatal/AML/OEM을 실행하지 않습니다. 동적 Load/LoadTable/Unload/namespace 정의는 미지원으로 닫습니다.

Root/기존 전체 연결 FF 의미는 유지하며 완전히 구문 해석한 보조 N개 범위의 반환/확장 구문/FF를 별도 집계합니다. N=0은 미확정, 실패 prefix는 폐기하고 scoped false를 전체 부재/실제 FF 위치로 전이하지 않습니다. 새 배포 ACPI-HELPER-SYNTAX/Acpi-routing-v4는 일반 권한·프로그램 ZIP 하나만 사용합니다. v3 반복/관리자 비교/과거 자료 재제출은 필요하지 않습니다. 실제 v4 분석은 아직 미관측이고 충전 제어는 Unsupported입니다. 이전 1회 실험·예약 표식은 유지합니다. 아래는 이전 기록입니다.

## v2 DSDT 관측 수신·연결 구문 요약 v3

[v2 관측과 v3 구현 경계](ACPI_METHOD_FLOW_UPDATE.md)를 먼저 읽습니다. DSDT 본문 Complete·namespace Partial·알려진 설명자 1·대응 메서드 1·인수 3·본문 Parsed를 관측했습니다. 직접 비교/FF 반환 미관측은 보조 본문의 부재가 아닙니다. 수집 확대 대신 후보 Return 형태·알려진 호출 수·직접 Arg2 인수·같은 테이블의 보조 정의를 깊이 2/최대 8개/전체 호출 표현식 32개 안에서 순수 정적으로 요약합니다.

중복/명시 경로/관측 객체의 shadow를 보수적으로 구분하고 unresolved 이름은 객체/무인수 호출을 단정하지 않아 Partial입니다. helper의 형식 인수를 원래 WMI 입력으로 대입하거나 실행 경로·변수 값·배터리 의미를 계산하지 않습니다. 루트 FF와 보조 FF 표식은 별개이며 불완전한 연결에서 보조 FF 여부는 미확정입니다.

새 배포는 ACPI-METHOD-FLOW / Acpi-routing-v3입니다. v2와 동일한 두 읽기 API·DSDT/첫 SSDT를 사용하며 registry/AML eval/OEM/DLL/예약/드라이버/물리 메모리/포트/쓰기/보안 변경은 없습니다. 실제 제어는 Unsupported이고 완료된 1회 실험 표식은 유지합니다. 새 v3 분석의 실기는 미관측입니다. 프로그램 ZIP 하나만 일반 권한으로 실행하며 v2 반복·관리자 비교·과거 자료/원본 ACPI 재제출은 요청하지 않습니다. 아래는 이전 기록입니다.

## DSDT 직접 읽기 수정본 — Acpi-routing-v2

[수정 근거와 범위](ACPI_DSDT_DIRECT_READ_UPDATE.md)를 먼저 읽습니다. ACPICA 고정 커밋 e85aa3b의 Windows 구현에서 DSDT 미열거를 직접 Get으로 보완하는 근거를 확보했습니다. 기존 두 읽기 API·고정 provider/ID를 유지하고 정상 목록 조회 뒤 DSDT 0이어도 직접 크기/본문을 한 번씩 읽습니다. 목록 관측·본문 읽기·구문 해석은 별도로 보고하며 첫 SSDT만 읽는 한계와 제한된 파서는 그대로입니다.

이번에는 registry SSDT 캐시 경로를 추가하지 않습니다. OEM/AML/DLL 실행·드라이버/물리 메모리/포트·예약 접근·보안 변경·펌웨어 쓰기는 없습니다. 기존 앱/요청/decoder/예약/제어 정책도 유지합니다. 새 실행 패키지는 ACPI-DSDT-DIRECT이며 예전 v1 ZIP은 그대로 보존합니다. 프로그램 ZIP 하나만 일반 권한으로 실행해 v2의 새 요약을 확인하며 소스 ZIP·기존 자료 재제출은 필요하지 않습니다. v2 실제 Windows 직접 읽기는 미검증이고 실제 충전 제어는 Unsupported입니다. 아래는 이전 기록입니다.

## ACPI 실기 결과 수신 — 정의 확보 범위 부족

[실기 결과와 다음 경계](ACPI_ROUTING_LAPTOP_RESULT.md)를 먼저 읽습니다. 사용자 요약은 Acpi-routing-v1, 목록 Complete, DSDT 0, SSDT 4, 첫 SSDT Partial, 설명자/메서드 0, 본문 NotObserved입니다. DSDT는 미열거 gate로 본문 조회를 하지 않았고 SSDT는 첫 것만 읽었습니다. Partial의 원인 구문은 출력에 없으며 기능 부재나 FF 의미를 입증하지 못했습니다.

현재 도구의 같은 실행·관리자 비교·과거 자료 재제출을 요청하지 않습니다. 같은 서명 반복 조회로 다른 SSDT를 읽을 수도 없습니다. 다음 구현 전에 현재 모델 정적 정의를 얻을 읽기 전용 Windows 자료의 실제 제공 범위와 문서 근거를 검토해야 합니다. 근거 없이 직접 DSDT 조회 성공·새 registry 경로·파서 수정 효과를 단정하거나 OEM/드라이버/포트/물리 메모리 접근으로 우회하지 않습니다.

이번 변경은 실기 관측 문서뿐이며 새 EXE·빌드·테스트 실행은 없습니다. 353+22 및 빌드 0경고/0오류는 직전 기록입니다. 기존 요청/디코더/예약/제어 정책과 다운로드 ZIP은 그대로이며 완료된 1회 OEM 실험 재실행·표식 초기화·추가 후보는 없습니다. 충전 제어는 Unsupported입니다. 아래는 이전 기록입니다.

## ACPI 정적 연결 점검 구현

[이번 범위·출력 해석·새 자료](ACPI_STATIC_ROUTING_CHECK.md)를 먼저 읽습니다. 기존전송코드감사에서FF를만드는명백한결함없음, exactmodel공개README검색에서도펌웨어정의없음이므로 현재DSDT/첫SSDT의WMI연결정의를읽는새별도normal-asInvoker도구를준비했습니다. Windows두read API만사용, AML eval/OEM/예약/원본저장X입니다. 과거자료재제출아닌새정의요약만필요합니다.

Core제한AMLreader는static_WDG knownGUID→동일scope WMxx 후보와인수수·직접ID1/Size21비교·literalFF반환구문만요약합니다. opaqueBuffer/Package/String/Field에재동기화하지않고unknownNamespace는Partial, methodunsupported는표식폐기합니다. Partial/관측수/부정표식은전체부재·유일성·배터리의미증거가아닙니다. 모든SSDT/cross-table/보조메서드/SMM해석미지원이며FF원인해결을보장하지않습니다.

새ACPI-ROUTING-CHECK만일반권한으로실행하며oldOneShot재실행/markerreset/추가OEM/0x66없음. 현재일반앱·원래정책/decoder/예약은유지합니다. 원본테이블/GUID원문/주소/이름/경로/식별자는보고하지않습니다. 실제Windows수집경로는아직미검증이고실제충전제어는Unsupported입니다. 아래는이전기록입니다.

## 일반 앱 실기 확인·모델 계약 추가 정적 조사

[이번 조사 범위와 남은 조건](WMI_MODEL_CONTRACT_FOLLOWUP.md)을 먼저 읽습니다. 사용자가 일반 권한 시작/현재 배터리 표시를 확인했고 파일 재제출은 하지 않았습니다. 과거 결과 붙여넣기까지 확인한 것으로 확대하지 않습니다.

Linux v6.12도 조회 입력data[0]=0x80을 명시하므로 FF를근거로0으로바꾸지않습니다. SABI2 표의0xFFFF와응답FF, Windows version16과SABI2/3도구분합니다. 공개linuxhw/ACPI 커밋d6d30c6ef6f45506567f25a302c64f009d8f5f4e를blob없는실제tree로조사했으나940/930X경로없음, 다른모델AML은대입하지않았습니다. 현재모델Windows명령/selector/FF계약은여전히미확정입니다.

새계약근거없이충전어댑터/쓰기/추가OEM시도/입력보정/의미없는wrapper나반복진단을추가하지않습니다. 승인1회는완료됐고marker유지/packager폐쇄그대로입니다. 이번에는문서만변경했으며342+19/경고오류0은직전검증기록입니다. 새EXE/시험/자료재제출은없고기존일반앱을그대로사용합니다. 아래는이전기록입니다.

## 실제 응답 수신·표식FF·1회 완료·일반 앱 오프라인 검토

[이번 결과·정적 대조·프로그램 개발](WMI_ONE_SHOT_QUERY_RESULT.md)을 먼저 읽습니다. 사용자 출력 Query65-locator-v2/Elevated/ResponseReceived/Complete/Ready/requested/FrameChecked/ValidFrame/FF를 확인했습니다. 비동기완료0·출력1개·정확히21바이트/ACKAA 구조는 통과했고 payload첫바이트만FF로분류했습니다. 전체payload/명령echo/배터리의미/보호상태·충전상한은 미확정입니다. FF를OFF/ON/하드웨어미지원으로 변환하지 않습니다.

승인된1회는 소비됐으며 기존v1예약과backend/정책/decoder를그대로보존합니다. 실험재실행·표식삭제/리셋·다른계정/위치우회·추가읽기후보·0x66쓰기는없습니다. 완료기록이있는동안새OEM EXE패키징도닫았습니다. 같은자료/준비점검을다시요청하지않습니다.

이번에는 메인WPF앱에 기존consoleTEXT를user가paste해검토하는오프라인기능을추가했습니다. Core의bounded고정형식parser→고정enumreview만보관하고 원문은검토후비웁니다. 과거텍스트진위/currentdevice일치는검증하지않고 FF/0/1/Other도현재actualmode로쓰지않습니다. VM은설정/모드/로그/하드웨어와분리하고 입력변경·실패·초과·dispose를닫습니다. 새기능은추가WMI/OEM/예약접근없고기존battery/readonly진단만유지합니다.

새 RESULT-REVIEW 일반앱/소스만공유하며 실험EXE/삼성원본은포함하지않습니다. 새노트북실험/자료재제출은필요없고현재실제제어는Unsupported입니다. 다음핵심은현재모델Windows배터리명령의미·응답해석근거이며 공개hotkeys/LinuxFF처리를그대로전이하지않습니다. 아래는이전기록입니다.

## Locator-v2 Ready 실기 수신·기존 승인 조회 수정본 준비

[이번 결과·변경·실행 범위](WMI_QUERY_LOCATOR_READY_RESULT.md)를 먼저 읽습니다. 사용자 출력은 Locator-v2/Elevated/Complete/Ready/None이며 OEM/예약접근은 없습니다. 이번에 단일 활성 대상·경로와 대상 재읽기·입력CIMTYPE·메모리 버퍼까지 통과했습니다. 같은 준비 점검/자료를 반복 요청하지 않습니다.

기존 명시 승인 exact0x65/payload80+15zero/max1은 유지되고 옛 실험은 PreflightFailed로 claim/channel 전에 끝났습니다. 같은 승인을 재요청하지 않고 승인 범위의 실행을 완수하도록 기존 backend의 methodquery에만 EnsureLocatable을 반영합니다. 새 표식이나 횟수를 만들지 않고 원래 v1 예약과 위치를 그대로 사용합니다. 기존 표식이 있거나 안전하게 확보하지 못하면 무호출입니다. Ready TXT를 허가 토큰/선택 대상 근거로 입력받지 않습니다.

기존 실제 호출/콜백/출력해석·정책·예약·가드·worker/시간 제한은 그대로이며 메인 앱 미연결입니다. 새 Query65-locator-v2 판별 표시가 있는 ONE-SHOT-LOCATOR ZIP만 해당 절차로 한 번 확인합니다. 후보의 의미/펌웨어 부작용은 아직 미검증이고 실제 충전 제어는 Unsupported입니다. 호출 요청·시간 초과·결과 불명 뒤 재시도, 표식 삭제/리셋, 다른 계정/경로 우회, 0x66/다른 명령은 없습니다. 아래는 이전 기록입니다.

## 경로 정보 확보 옵션·고정 오류 분류 구현 후

[Locator-v2 구현과 확인 범위](WMI_PREFLIGHT_LOCATOR_UPDATE.md)를 먼저 읽습니다. 새 무호출 점검판은 MethodEnumeration의 고정 SELECT에만 EnsureLocatable=true를 적용하고 모델/BIOS 조회 옵션은 기존대로 유지합니다. 객체/경로 문제 여섯 종류와 정상 Boolean Active=false를 구분합니다. 과거 enum 값과 모호한 결과는 그대로 남깁니다.

단일 활성 대상·경로·입력 검증, DirectRead와 6초 예산·부모/작업자 각10초 제한을 유지합니다. 기존 실험 backend/정책/예약/메인 앱은 변경하지 않았습니다. Ready에서도 OEM 호출·예약 접근은 없고 충전 제어는 Unsupported입니다. 새 LOCATOR ZIP을 별도 공유하며 삼성 원본/이전 실험 EXE는 제외합니다.

다음 실기 확인은 새 점검판 `(Locator-v2)`의 단계와 세부 원인 분류뿐입니다. 과거 자료나 같은 이전 실행 결과를 다시 요청하지 않습니다. 기존 실험 EXE 재실행·표식 삭제·추가 OEM 시험으로 이어가지 않습니다. 경로 정보 확보가 실제 이전 실패를 해결했는지는 아직 미확정입니다. 아래는 이전 기록입니다.

## 무호출 점검 결과 수신 — 메서드 대상 열거 조건 불일치

[이번 결과와 다음 수정 범위](WMI_PREFLIGHT_ENUMERATION_RESULT.md)를 먼저 읽습니다. 사용자 출력은 Elevated·Complete·MethodEnumeration·InactiveOrInvalidTarget입니다. 이번 실행은 고정 모델/BIOS·상세 metadata/binder/id1·ROOT\WMI 연결을 통과했고 TargetRead/입력CIMTYPE/버퍼 준비에는 도달하지 않았습니다. OEM 호출과 예약 접근은 없습니다.

이 분류는 반환 객체/경로 구조 실패와 명시적 Active=false를 합치므로 Active=false·한 행·전체 열거 완료를 단정하지 않습니다. SELECT Active 결과에 경로를 요구하면서 EnsureLocatable을 지정하지 않은 점을 우선 검토합니다. 공식 API 문서에서 옵션 의미와 기본 false를 확인했으나 실제 경로 누락은 아직 미확정입니다. 이전 Unavailable과도 맞는 구조 실패 가설이며 동일 원인을 확정하지 않습니다.

다음은 무호출 도구의 고정 오류 분류 세분화와 메서드 대상 쿼리의 EnsureLocatable 적용 검토입니다. 기존 단일 활성 대상/경로 검증을 삭제하지 않고 원문 경로도 보고하지 않습니다. 이번에는 문서만 반영했으며 기존 EXE 재실행·자료 재제출·표식 삭제·추가 OEM 실행은 요청하지 않습니다. 329개/6프로젝트0경고오류는 이전 배포 기록이고 이번에는 빌드/테스트를 재실행하지 않았습니다. 아래는 이전 기록입니다.

## 무호출 사전 검증 점검 도구 구현 후

[이번 구현과 실행 범위](WMI_PREFLIGHT_ONLY_CHECK.md)를 먼저 읽습니다. 이전 Elevated·PreflightFailed·Unavailable·InvocationRequested=false 결과의 실패 위치를 확인하기 위해 별도 WmiPreflightCheck를 추가했습니다. 고정 준비 조건과 DirectRead 옵션·6초 예산을 그대로 재현하며 단계와 오류 enum만 출력합니다. 기존 실험 프로젝트와 예약/호출 정책은 변경하지 않았습니다.

새 EXE는 OEM 메서드 실행·후보 프레임·실험 runner·예약 접근이 전혀 없습니다. 메모리 입력 객체 생성까지만 하고 모두 해제합니다. 부모/작업자 각각10초 제한, asInvoker·같은 계정 수동 관리자 실행, 고정 쿼리와 개인정보 제한을 유지합니다. Ready도 실제 보호 상태나 충전 제어를 뜻하지 않습니다.

새 확인은 WMI-PREFLIGHT-ONLY ZIP의 새 EXE 출력뿐입니다. 이전 WmiOneShotQuery를 재실행하거나 표식을 삭제하지 않습니다. 기존 TXT/DLL/파일 목록·권한 비교 재제출도 필요 없습니다. 실패 원인을 확인하기 전에 조건/쿼리 옵션을 완화하지 않습니다. 이번 준비가 통과해도 이전 실패 원인 해결이나 추가 OEM 시험 승인을 추정하지 않습니다.

현재 전체329개 통과·6개 프로젝트와 테스트 프로젝트 빌드 경고/오류0개입니다. Windows 실기와 OEM 호출은 클라우드에서 수행하지 않았고 실제 충전 제어는 Unsupported입니다. 새 실행 ZIP은 삼성 원본과 기존 실험 EXE를 제외하고 별도로 공유합니다. 환경 설정 게시는 없습니다. 아래는 이전 기록입니다.

## 1회 도구 결과 수신 — 사전 검증 중단·무호출

[실제 결과와 보고 전용 보완](WMI_ONE_SHOT_PREFLIGHT_RESULT.md)을 먼저 읽습니다. 2026-11-04 사용자 출력은 Elevated·PreflightFailed·Unavailable·InvocationRequested=false·응답/표식 미관측입니다. 이 상태 조합에서는 Prepare가Complete가되기전에끝나고 예약/채널에진입하지않았습니다. 이번실행의후보요청은없었지만기존예약파일부재나추가실행허가를단정하지않습니다.

기존 '메타데이터확인불가'는공통Unavailable문구라 실패위치를증명하지않습니다. 고정사전검증단계만보고하는패치를구현했고 모든호출가드/쿼리옵션/예약/1회제한/실행메서드는유지합니다. 정확한원인을찍어조건을제거하지않고 이번에는새실험EXE·재실행·표식삭제를요청하지않습니다. 이전자료재제출도필요없습니다. 전체325개통과·5개프로젝트빌드경고오류0개이며 actualWindows/OEM실행은추가하지않았습니다. 아래는이전이력입니다.

## 한정 OEM 후보 실험 명시 승인·도구 구현 후

사용자가 “그래 이번 테스트를 위해서 승인할게. 반드시 필요한 작업만 수행하도록해. 노트북의 보안을 위해서 하드웨어 안전 규칙을 꼭 지켜야해.”라고 검토서 범위를 승인했습니다. [승인 기록·구현·실행 안내](WMI_ONE_SHOT_QUERY_APPROVAL.md)를 먼저 읽습니다. 같은 승인 재요청 없이 이 한정 실험의 구현/검증/프로그램 공유를 완료합니다. 후보가 안전하거나 모델 적합성이 입증됐다는 결과는 아닙니다.

새 WmiOneShotQuery는 별도 asInvoker·같은 계정 수동 관리자·fixed0x65 payload80+15zero·최대1회입니다. 모델Product.Name/BIOS exact·token·상세metadata/id1·전체완료1rowActiveTrue·입력준비·영속CreateNew예약이 모두 맞아야 요청합니다. 원래 앱은 연결하지 않고 0x66/다른명령·DLLinit·driver/service/ACL/보안변경·포트IO·자동상승은 없습니다.

Native는 managed async InvokeMethod 한 지점만 있고 Completed.Status0+정확히1개일 때만 고정output을읽습니다. 이 상태는 즉시ExecMethod HR을 확보했다는 뜻이 아닙니다. generic콜백collector를portable로검증하고 늦은/중복/실패/cancel/정리경합을닫습니다. 부모와내부worker각10s감시·6s사전검증예산이있고native종료/복구를보장하지않습니다. 예약표식을삭제/리셋/우회하지않습니다.

새 도구의 Windows 실기 결과는 아직없으며 다음은 승인된1회출력만받는 단계입니다. 이전TXT/DLL/파일목록/권한비교재제출은필요없습니다. 어떤후보표식도 actualMode/ONOFF/충전상한지원으로바꾸지않고 Unsupported를 유지합니다.

현재전체322개+Python6개통과,5개프로젝트빌드경고/오류0개입니다. 실제OEM/Windows실기미실행입니다. 소스와미서명실험ZIP만검증해공유합니다. 승인된1회결과를받기전다른명령/추가실험/예약표식초기화를추가하지않습니다. 아래는 이전 개발 이력입니다.

## 다음 실제 단계의 범위 변경 검토서 준비

[한정 OEM 조회 후보 실험 검토서](WMI_ONE_SHOT_QUERY_REVIEW.md)를 먼저 읽습니다. 내부 메모리 통합은 완료됐고 추가voria/hotkeys callsite조사에서도 현재모델WMI 배터리명령 의미·안전성·응답계약은확정하지못했습니다. 새로운일반추상화/반복진단을추가하지않았습니다.

조회후보0x65·payload80+0x00*15·한정1회·별도asInvoker/같은계정수동관리자실행·시간초과/무호출/출력제한을 검토서로 구체화했습니다. 경로간 전이 가설과 예기치않은 firmware동작 가능성을명시했으며 실제OEM실행구현·EXE·실험은 아직미승인·미구현·미실행입니다. 원래사용자의OEM금지와AGENTS의명시승인/검증조건을 개발계속지시나 이전속성관리자비교승인으로 덮지 않습니다.

다음 사용자답변은 이 미검증 후보의 한정 실험으로 범위를변경할지입니다. 승인전에는 InvokeMethod·드라이버/포트IO·DLL초기화 등실제경로를추가하지않습니다. 승인받으면같은범위에승인을반복요청하지않고구현·검증·다운로드공유를완료합니다. 설정/쓰기명령의구현과0x66/다른OEM명령·메인앱관리자실행·자동상승은범위밖입니다. 미검증펌웨어부작용의부재를보장하지않습니다.

이번에는문서와연구만변경했습니다. 297개·빌드경고오류0은이전검증기록이며 재실행하지않았습니다. 이전원본자료제출과같은규약진단은필요하지않습니다. 아래는이전개발이력입니다.

## 메모리 채널 연결·통합 검증 후

[이번 채널·전체 경로·연구 한계](WMI_BOUND_CHANNEL_AND_PIPELINE.md)를 먼저 읽습니다. 바인더와 명시 snapshot transport를 연결하는 BoundFrameChannel을 추가했으며 기존 FrameExchange를 그대로 사용합니다. TryWrapFrame은21/magic/예약0을 복사 후 검증합니다. MethodReplyStatus와 InvalidEnvelope로 중첩 오류를 보존하고 기존byte decoder 상세는null·bool수락조건은 그대로 유지합니다. 이미 결합한 응답의 재포장은 거부합니다.

실제 Windows/native/OEM 구현·기본 transport·인스턴스 선택·앱 등록은 없습니다. 취소token을 전달하고 늦은 snapshot을 성공 게시하지 않으며 실제 작업 완료까지 기존 조정기의 Busy를 유지합니다. 이는 인스턴스별 협조적 제한이고 공유 transport 전역 잠금이나 native 강제 종료가 아닙니다.

노트북에서 새로 실행·제출할 항목은 없습니다. 클래스 형식 확인은 완료됐고 내부 경로가 모의 통합 검증으로 연결됐습니다. 다음 개발 우선순위는 현재 모델 배터리 명령 의미·읽기 안전성·실제 응답 계약 근거입니다. 공개 포크/이슈 후속 조사에서도 새 근거는 확보하지 못했습니다. Windows1/Linux0/firmwareopcode를 치환하지 않고 실제 읽기·쓰기는 Unsupported를 유지합니다.

전체297개 통과·실패/건너뜀0개, 4개 프로젝트 빌드 경고/오류0개입니다. Python배포suite는이번에반복하지않았고 이전6개는이전기록입니다. 새소스ZIP을별도검증합니다. 아래는 이전 개발 이력입니다.

## 형식 일치 실기 결과 수신·오프라인 메서드 바인더 구현 후

[이번 실제 관측·코드·남은 조건](WMI_MATCHED_BINDING_AND_OFFLINE_ENVELOPE.md)을 먼저 읽습니다. 판독기2에서 두 클래스Complete, GUID후보일치, CallSabiFunction존재, WindowsMethodId1, in/out ScalarObject+CIMTYPE DataBuffer, BytesUInt8[]=True를 확인했습니다. EmbeddedInstance는 미관측/없음으로 보존하고 권한 수준은 새로 단정하지 않습니다. 이전 Unknown이 해소됐으므로 같은 메타데이터·파일 목록·관리자 비교를 반복 요청하지 않습니다.

WsabiWmiMethodBinder는 상세 근거가 모두 있는 Complete 보고서에서만 만들어지고 bool만 true인 호환 보고서는 거부합니다. 고정 inData/Bytes 요청 포장과 outData/Bytes 추출을 기존 codec에 연결하지만 메모리 snapshot만 다룹니다. HRESULT 우선, 실패 시 데이터 제거, 깊은 복사·읽기 전용 map과 false capability를 유지합니다. CreateInstance/InvokeMethod/liveWMI/OEM채널/앱등록은 없습니다.

이번에는 내부 계층의 검증된 소스를 전달하며 새 노트북 실행 항목은 없습니다. 저장 기록과 공개 ACPI 인덱스 조사에서도 현재 모델 배터리 명령의 의미·읽기 안전성·실제 응답 계약은 추가 확보하지 못했습니다. Windows1을 Linux0/펌웨어opcode로 치환하거나 Sabi3후보를 WMI에 대입하지 않습니다. 실제 읽기·쓰기는 미구현이며 Unsupported를 유지합니다.

이번 전체286개 통과·실패/건너뜀0개, 4개 프로젝트 빌드 경고/오류0개입니다. 이전Python6개는 이번에 반복 실행하지 않았으며 소스ZIP만 별도로 검증합니다. 아래는 이전 단계 이력입니다.

## 실제 규약 결과 반영·CIMTYPE 보완 후

[이번 실제 관측과 수정](WMI_PARAMETER_RESULT_AND_CIMTYPE_REVIEW.md)을 먼저 읽습니다. 공개 GUID 후보 일치, CallSabiFunction 존재, Windows WmiMethodId=1, DataBuffer.Bytes UInt8[]=True를 확인했습니다. in/out Unknown이므로 입력/출력의 구체 클래스는 미확정입니다. 도구에 토큰 표시가 없어 이번 권한 수준도 새로 단정하지 않습니다. 원본 TXT는 저장소·배포물에 넣지 않습니다.

단일 Object의 구체 클래스를 EmbeddedInstance만으로 검사했던 한계를 공식 CIMTYPE object:EmbedClass 근거로 보완했습니다. 실제 CIMTYPE는 아직 미관측입니다. 새 판독기2는 두 qualifier의 독립 상태·충돌·형식 오류를 enum으로 보관하고 부분/실패를 일치로 승격하지 않습니다. 메서드 번호1은 그대로 보존하며 Linux0이나 프레임 내부 펌웨어 명령으로 치환하지 않습니다. 모든 상태에서 호출·하드웨어 기능은 차단합니다.

274개 및 Python6개 통과, 4개 프로젝트 빌드 경고/오류0개입니다. 수정 도구의 Windows 실기는 미검증입니다. 새 확인은 in/out CIMTYPE·판정이며 기존 진단·DLL·권한 비교 재요청이나 관리자 실행을 하지 않습니다. 실제 배터리 명령의 모델 적합성·읽기 안전성·응답 계약은 아직 미확보이며 OEM 채널 미연결과 Unsupported를 유지합니다. 아래는 이전 이력입니다.

## 비동기 프레임 처리와 정적 클래스 규약 도구 구현 후

[이번 코드·규약·새 실기 확인 항목](WMI_EXCHANGE_AND_BINDING_CHECK.md)을 먼저 읽습니다. 비동기 조정기는 가짜 채널만으로 검증했으며 실제 WMI/OEM 채널이나 앱 등록 경로는 없습니다. 시간 초과·취소 후 실제 작업 완료까지 Busy를 유지합니다. 협조적 제한을 native 강제 종료로 해석하지 않습니다.

별도 asInvoker WmiContractCheck는 WmiAcpiMethod/DataBuffer 클래스 정의만 읽습니다. 공개 GUID 후보 일치, CallSabiFunction의 WmiMethodId, inData/outData EmbeddedInstance와 Bytes의 UInt8[] 정의를 확인합니다. 실제 GUID 원문·인스턴스·토큰·보안 설명자는 수집하지 않습니다. 메서드 ID는 펌웨어 배터리 명령이 아니며 형식 일치도 실제 배열 길이·ACK·호출 안전성·배터리 지원을 입증하지 않습니다.

전체262개 및 Python6개 통과·4개 프로젝트 빌드 경고/오류0개입니다. 새 도구의 Windows 결과는 아직 받지 않았습니다. 다음 사용자 확인은 새 정적 필드의 일반 실행 출력뿐이며 기존 진단·원본 DLL·한 번의 관리자 비교를 반복 요청하지 않습니다. 새 도구도 관리자 실행을 요청하지 않습니다. 권한 거부·시간 초과는 그대로 보존합니다.

추가 공개 모델 자료3건도 현재 모델의 Windows 배터리 조회 계약을 확정하지 못했습니다. 실제 배터리 읽기는 모델별 명령 의미·읽기 안전성·응답 계약이 남아 있으며 Unsupported와 기존 쓰기 차단을 유지합니다. 이전 한정 비교 승인은 완료됐고 OEM·권한 상승·드라이버/서비스/ACL 변경으로 확장하지 않습니다. 아래는 이전 개발 이력입니다.

## 구조적 WMI 응답 디코더 구현 후

[추가 공개 근거와 코드](WMI_REPLY_DECODER_AND_PUBLIC_EVIDENCE.md): gh2o/samsung-wmi와 djpohly/samsung-wmi의 고정 원문에서 21바이트 프레임·payload16 구조를 독립 확인했습니다. 현재 모델, Windows 클래스·메서드와의 동일성, 배터리 조회0x65, version16 의미를 입증하는 자료는 아니므로 새 호출 대상이나 명령으로 사용하지 않았습니다.

순수 WsabiWmiReplyDecoder와 불변 결과 객체를 구현하고 기존 bool 검증기를 호환 위임으로 바꿨습니다. API 미완료·없음·형식·차원·길이·ACK를 구분하며 payload0/1/FF를 배터리 상태로 해석하지 않습니다. 정확한21바이트만 지원하는 기존 범위와 Sabi3 x64 ABI 분리를 유지합니다.

전체244개 통과·빌드 경고/오류0개입니다. 이번에는 소스 구현과 정적 연구를 전달하며 새 OEM 실행 파일이나 반복 노트북 진단은 요구하지 않습니다. 다음 실제 배터리 읽기의 미검증 조건은 여전히 모델별 명령 의미·안전성·정확한 응답 계약입니다. 이전 한정 관리자 비교 승인을 OEM 호출로 확대하지 않습니다.

## 일반·관리자 비교 결과 수신 — 비교 완료

[두 실행의 실제 결과](WMI_PERMISSION_COMPARISON_RESULT.md)를 확인했습니다. 일반 토큰은 WmiAcpiVersion Active=True/version=16을 읽고 WmiAcpiMethod를 Enumerate에서 0x80041003으로 거부받았습니다. 상승 토큰은 두 클래스 모두 Complete이고 각각 활성 행 1개, version=16입니다. 이번 승인은 한정된 속성 비교였으며 결과 수신으로 완료됐습니다.

이는 메서드 실행 허가·배터리 보호 상태·명령 지원을 확인한 결과가 아닙니다. version16은 해석하지 않은 UInt32이며 두 클래스의 행도 키로 연결하지 않았습니다. 이전 메인 앱의 양쪽 AccessDenied와 이번 새 도구의 일반 토큰 버전 성공은 별도 빌드·시점 관측으로 보존합니다. PacketPrivacy나 Connect의 인과를 단정하지 않습니다.

다음 검증 대상은 새로운 잔량/파일/권한 반복 진단이 아니라 현재 모델의 배터리 조회 명령 의미·입력/응답 계약·실제 read-back 근거입니다. 현재 자료 대조로는 그 연결 고리를 확정하지 못했습니다. 승인 범위를 OEM 호출·상시 관리자·자동 상승·서비스/드라이버/ACL 변경으로 확대하지 않습니다.

단일 조회의 관리자 관련 설명을 좁히고 합성 회귀 사례를 추가했습니다. 전체238개 통과·빌드 경고/오류0개이며 새 OEM 실행 파일은 만들지 않았습니다. 아래는 이전 이력입니다.

## 한정된 관리자 읽기 비교 승인

2026-11-03 사용자가 같은 Windows 계정에서 별도 WmiAccessCheck로 일반 권한과 한 번의 관리자 권한으로 고정 두 WMI 속성만 읽어 비교하는 절차를 승인했습니다. [실행 안내](WMI_PERMISSION_COMPARISON_RUN.md)에 범위를 기록했습니다. 프로그램 공유나 이 한정 비교에 같은 승인을 다시 요청하지 않습니다.

실제 Windows 노트북 결과는 아직 받지 않았습니다. 기존 검증된 asInvoker ZIP을 그대로 사용하고 메인 앱의 관리자 실행·서비스/드라이버·ACL 변경·OEM 메서드·삼성 DLL 실행은 하지 않습니다. 다른 계정 자격 증명이 필요하거나 토큰 상태가 불분명하면 비교를 확대하지 않습니다. 아래 승인 대기 설명은 당시 이력입니다.

## PacketPrivacy 적용 후에도 권한 거부 지속

사용자 TXT samsung-files-20261102T154749에서도 두 WMI 클래스가 AccessDenied입니다. SABI NotFound와 Samsung 후보 7개 Stopped/Manual도 같습니다. 암호화 명시만으로 해결되지 않았음을 기록하고 같은 파일 목록·기존 TXT·삼성 원본을 다시 요청하지 않습니다.

[별도 asInvoker 권한 비교 도구](WMI_PERMISSION_COMPARISON_REVIEW.md)를 소스·실행 파일·테스트까지 준비했습니다. 현재 토큰 상승 여부와 고정 읽기의 Connect/Query/Enumerate/ReadProperties 단계를 확인하지만 UAC·runas·ACL 변경·임의 쿼리·파일 쓰기는 없습니다. 메인 앱에서 실행하지 않으며 관리자 비교 실행은 아직 승인받거나 수행하지 않았습니다.

다음 필요한 결정은 이 한정된 별도 도구로 일반 권한과 한 번의 관리자 권한에서 같은 두 속성을 읽어 비교할지입니다. 프로젝트 AGENTS.md의 명시적 승인 조건을 따릅니다. 비교 성공을 보장하지 않으며, 충전 명령·삼성 DLL·서비스/드라이버 변경은 범위 밖입니다. 이번 테스트237개 및 전체 솔루션 빌드 경고·오류 0개이며 Windows 실기는 미검증입니다.

## 실제 WMI 권한 결과 반영 후

사용자 TXT samsung-files-20261102T152127에서 SABI NotFound, Samsung 후보 7개 모두 Stopped/Manual, 두 WMI 클래스 AccessDenied를 확인했습니다. 앱 실행·TXT 생성 성공을 인스턴스 조회 성공으로 바꾸지 않습니다. 같은 자료나 삼성 DLL/EXE를 다시 요청하지 않습니다.

[이번 근거·구현](WMI_ACCESS_RESULT_AND_TRANSPORT_REVIEW.md)에 따라 현재 사용자 권한으로 PacketPrivacy를 명시하고, 관측을 독립적으로 설명하는 화면/보고서 요약과 순수 wsabi 요청 프레임 인코더를 추가했습니다. 기본 Impersonate를 명시하는 것만이 수정 근거가 아닙니다. RequiresEncryption이 실제 원인인지, ACL·제공자 권한 문제인지, 새 연결에서 해결되는지는 아직 미검증입니다.

전체 228개 테스트와 별도 배포 검증 6개 통과, WPF/XAML 빌드 경고·오류 0개입니다. 인코더는 실행에 연결하지 않았으며 OEM 메서드·삼성 DLL·드라이버/서비스 변경은 하지 않습니다. 실제 제어는 계속 Unsupported입니다. 다음 실제 읽기는 모델·명령·응답 계약과 접근 권한 검증이 선행되어야 하며 권한 상승·ACL 수정은 자동 진행하지 않습니다.

## WMI 인스턴스 속성 조회 구현 후

사용자가 커널 드라이버 확인판의 실제 노트북 실행과 samsung-files TXT 생성을 확인했습니다. TXT 내용은 업로드되지 않았으므로 조회 성공·드라이버 상태까지 확인했다고 해석하지 않습니다. 같은 자료나 삼성 DLL/EXE를 다시 요청하지 않습니다.

저장된 다음 방향에 따라 [WMI 인스턴스·버전·활성 속성 조회](SAMSUNG_WMI_INSTANCE_INSPECTION.md)를 구현했습니다. ROOT\WMI의 WmiAcpiVersion.Active/version과 WmiAcpiMethod.Active만 읽고 클래스별 결과를 구분합니다. InstanceName·키·경로·식별자·DataBuffer는 읽지 않으며 OEM 메서드·삼성 DLL·서비스 변경은 실행하지 않습니다. 버전 원값·Active는 모델 호환성이나 배터리 보호 상태가 아닙니다.

이번 전체 소스 테스트 217개 및 별도 배포 검증 6개 통과, WPF/XAML 빌드 경고·오류 0개입니다. 실제 Windows 제공자의 새 속성 조회는 미검증입니다. 다음 실제 상태 읽기/제어는 명령 의미·모델 적합성·응답 계약이 확보되는 별도 단계이며 Unsupported 쓰기 차단을 유지합니다. 아래는 이전 단계 이력입니다.

## 커널 드라이버 읽기 전용 조회 구현 후

기준 커밋 `4492bbaa6f9cb87a9fb7c24969c6f1efcf6b6bd9`에서 이어서 [삼성/SABI 커널 드라이버 상태 조회](SAMSUNG_KERNEL_DRIVER_INSPECTION.md)를 구현했습니다. 기존 삼성 파일 정보 버튼에 로컬 `Win32_SystemDriver`의 이름 후보 등록·실행 상태·시작 방식과 SABI 이름 결과 비교를 통합했습니다. 이름 후보만 분류하며 원래 서비스 이름·전체 경로·사용자 이름·고유 식별자는 내보내지 않습니다. 정상 완료의 미관측, 일부 관측, 권한 거부, 오류와 시간 초과를 구분합니다.

이번 환경에서 공유 소스 204개 통과, WPF/XAML x64 net48 빌드 경고·오류 0개입니다. Windows의 새 드라이버 조회는 아직 실기 미검증입니다. 기존 SABI 이름 NotFound를 드라이버 미설치나 배터리 기능 부재로 확정하지 않으며, 등록·Running 관측도 충전 제어 가능으로 승격하지 않습니다. 드라이버 설치·시작·중지, 삼성 DLL 초기화, OEM 명령, 펌웨어 쓰기는 연결하지 않았습니다.

다음 실기 확인은 새 드라이버 섹션의 로컬 관측을 확인하는 범위입니다. 이전 배터리 진단·파일 목록·DLL을 다시 요청하지 않습니다. 기존 WMI 전송 구조·순수 응답 검증 코드와 알려진 DLL 분석은 유지합니다. 실제 상태 조회/제어는 호출 규약과 모델 적합성 근거가 확보되는 별도 단계입니다. 아래 메모들은 이전 작업 이력입니다.

## SABI 이름 결과 수신·WMI 규약 검토 후

`samsung-files-20261101T132149`에서 SABI 연결 이름 NotFound를 확인했습니다. 기존 파일들의 해시·버전은 직전 보고서와 같습니다. [이번 관측과 별도 WMI 전송 분석](SABI_LINK_RESULT_AND_WMI_REVIEW.md)을 우선 읽으세요. Sabi3 초기화로 바로 진행하지 않습니다. 기존 서비스 wsabi는 WMI에 21바이트 입력·16바이트 payload를 전달하며 SABI 장치 이름 조회와 독립된 경로입니다. 정확한 제공자 응답 길이와 모델별 배터리 명령 지원은 아직 미검증입니다.

같은 진단·파일 목록·DLL을 다시 요청할 필요는 없습니다. 이번 변경은 Sabi3 선행 조건 설명과 순수 WMI 응답 검증 코드이며 새 실행용 ZIP을 만들지 않습니다. 다음 구현은 기존 WMI 경로의 인스턴스/버전/활성 상태와 호출·응답 조건을 확인하는 방향입니다. 실제 보호 상태 조회와 모든 쓰기는 아직 연결하지 않습니다.

## 제공받은 Sabi3 x64 분석 후

요청한 x64 DLL을 받아 해시 일치를 확인하고 정적으로 분석했습니다. [확정된 규약과 구현](SABI3_NATIVE_ABI_REVIEW.md)을 우선 읽으세요. 실제 버퍼 접근은 11바이트이므로 기존 공개 예제 기반 4바이트 decoder를 수정했습니다. 이 DLL이나 x86을 다시 요청할 필요는 없습니다. 다음 실제 관측은 새 TXT의 **SABI 장치 연결 이름**입니다. QueryDosDevice는 이름 조회만 하며 장치를 열거나 DLL/IOCTL을 실행하지 않습니다.

## 초기화 규약 검토 단계

최신 import 함수 TXT의 Windows 결과를 확인했습니다. [초기화 규약 검토 및 다음 대상](SABI3_INITIALIZATION_REVIEW.md)을 우선 읽으세요. 공개 자료와 기존 분석 ZIP에 현재 Sabi3 초기화 구현이 없어 다음 분석에는 크기 28,976바이트인 x64 Sabi3.dll 자체가 필요합니다. 동일 TXT를 다시 만들 단계가 아닙니다.

공개 참조 계약의 응답을 해석하는 순수 decoder를 구현했습니다. 미지원(0xFF), OFF(0), ON(1), 기타·API 오류·길이 오류를 구분하고 실제 하드웨어 관측이나 80% 상한으로 승격하지 않습니다. 실제 DLL 호출은 아직 연결하지 않았습니다.

## 실제 파일 식별 결과 수신 후

`samsung-files-20261101T105906`에서 Sabi3 3.2.0.0 x64/x86 및 예상 함수 5개, 여러 wsabi 변형과 두 EXE를 확인했습니다. [이번 분석 및 구현](SABI3_COMPATIBILITY_REVIEW.md)을 우선 읽으세요. 현재 단계는 DLL 전체를 다시 찾는 것이 아니라 정적 함수 참조로 초기화·드라이버 연결을 검토하는 것입니다. 현재 앱에서 삼성 파일 정보 버튼의 결과에 import 함수와 후보 판정을 추가했습니다. 실제 OEM 함수는 호출하지 않습니다.

## 작업 재개 후 구현

사용자가 개발 재개를 요청해 파일 식별과 표준 PE 참조/함수 조회를 구현했습니다. [삼성 파일 정보 기능](SAMSUNG_FILE_INSPECTION.md)은 명시적 버튼으로 원본 복사·삼성 코드 실행 없이 로컬 TXT를 만듭니다. 아래 메모와 이전 배포 기준은 재개 전 이력입니다. 새 기능의 Windows 실기 실행은 아직 미검증입니다.

다음 확인 자료는 새 버튼으로 생성되는 `samsung-files-*.txt`입니다. 기존 배터리 진단이나 삼성 바이너리를 반복 제출할 필요는 없습니다. 그 결과로 현재 DLL의 ABI·초기화 부작용·모델 적합성을 검토한 뒤 근거가 확보될 때 실제 설정 조회 단계로 진행합니다.

## 재개 기준

사용자는 남은 사용량을 고려해 이번에는 파일 역할 정리와 다음 개발 준비만 요청했습니다. 설치 경로는 `C:\Program Files (x86)\Samsung\Setting`이며 참고 정보입니다. 클라우드에서 직접 접근한 경로가 아닙니다. 삼성 파일을 이번 단계에서 추출·로드·실행하지 않았습니다.

- 실제 기기: Samsung 940X3G/930X3G, BIOS P05ACJ.128.140819.dg, Windows 10 Home 19045 x64, Samsung Settings 2.2.0.
- Settings와 BIOS에는 배터리 보호 메뉴가 없다는 사용자 보고가 있음. 다시 점검하도록 요구하지 않음.
- 배터리 표시·읽기 전용 진단은 확인됨. 최신 TXT는 52%, AC 연결, 충전 중이며 두 잔량 조회가 일치함.
- 표준 요청 지원 값은 `0x80000000`. 표준 충전·방전 요청 지원 비트가 없으며 이 경로를 제어에 사용하지 않음.
- 실제 80%/100% 제어는 Unsupported. 잔량·사용자 선택값·실제 설정은 계속 분리함.
- 현재 앱 소스/배포 기준 커밋: `9a9e1a7db16fe705a42236c366e027c5a41b91e1`. 이후 변경은 조사 문서뿐임.
- [현재 실행용 ZIP](https://github.com/dropboxqfml-code/codex/raw/9a9e1a7db16fe705a42236c366e027c5a41b91e1/downloads/ATIVBatteryGuard-DIAGNOSTIC-ASSESSMENT.zip). 138개 테스트 통과·빌드 경고/오류 0개는 해당 앱 버전의 기록이며 이번 문서 정리에서 재실행한 결과가 아님.

## 이번에 확보한 파일 단서

사용자는 위 폴더에서 `Sabi3.dll`, `wsabi.dll`, `BatteryToast.exe`, `PowerAudit.exe`의 존재를 보고했습니다. `charge` 키워드 일치 파일은 없었습니다. 실제 버전·비트 수·서명·함수·참조 관계는 아직 확인하지 않았습니다.

- `Sabi3.dll`: 공개 Windows 원본에 배터리 보호 조회·변경 호출 근거가 있음. 가장 먼저 조사할 대상.
- `wsabi.dll`: 삼성 WMI/COM 중계 후보. 이전 팬·정숙 모드 분석과 이번 설치 파일의 동일성부터 구분해야 함.
- `BatteryToast.exe`: 배터리 알림 보조 프로그램일 가능성. 이름에 따른 추정이며 기능을 확인한 결과가 아님.
- `PowerAudit.exe`: 전원 점검 보조 프로그램일 가능성. 이름에 따른 추정이며 읽기 전용인지도 미확인.

[DLL 후보 목록과 출처](SAMSUNG_DLL_CANDIDATES.md), [공개 제어 규약 검토](PUBLIC_CONTROL_PROTOCOL_REVIEW.md)를 함께 읽을 것. 공개 소스의 명령 후보를 현재 DLL의 ABI나 WMI 입력으로 곧바로 취급하지 않음.

## 다음 작업 순서

1. **실행하지 않는 로컬 파일 식별 기능부터 준비한다.** 위 네 파일의 파일명·버전·제품 설명·32/64비트 구조·서명 상태를 확인하는 범위를 설계한다. 원본 바이너리를 복사·업로드하는 기존 수집 기능을 다시 켜지 않는다. 서명 확인도 앱의 네트워크 통신 0건 조건을 지키며, 오프라인에서 확인되지 않은 상태와 서명 불일치를 구분한다.
2. **참조 관계와 내보낸 함수 정보를 정적으로 확인한다.** Sabi3의 필요한 함수가 있는지, EXE가 어느 DLL을 참조하는지 확인한다. 정적 참조가 없더라도 간접 로드·프로세스 간 통신 가능성을 배제하지 않는다. 이름·함수 존재·서명만으로 제어 가능하다고 표시하지 않는다.
3. **현재 DLL에 맞는 호출 계약과 조회의 부작용을 검토한다.** 공개 예제와 버전·호출 규약·드라이버 의존성을 대조한다. DLL이 x86이면 현재 x64 앱에서 직접 호출할 수 없으므로 향후 분리 구성을 검토한다. 이 단계까지는 DLL 초기화·OEM 메서드 호출을 추가하지 않는다.
4. **근거가 확보되면 실제 상태 읽기 어댑터를 먼저 구현한다.** 조회 성공, 미지원, 오류, 상태 불명을 구분한다. 공개 예제처럼 미지원 응답을 ‘보호 OFF’로 바꾸지 않는다. 사용자 선택값이나 잔량으로 실제 설정을 대신하지 않는다.
5. **실제 변경은 모델 적합성과 안전성이 확인된 후속 단계로 둔다.** 현재 물리 어댑터의 쓰기 차단을 유지한다. 커널/펌웨어 제어 추가는 AGENTS.md의 별도 승인·검증 조건을 따른다.

지금은 같은 배터리 진단이나 삼성 파일의 추가 제출을 요청할 필요가 없습니다. 다음 개발은 파일 식별에서 출발하며, 실제 제어를 이미 구현했다고 표현하지 않습니다.
