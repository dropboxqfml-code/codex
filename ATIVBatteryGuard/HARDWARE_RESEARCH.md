# 하드웨어 조사

## 최신 — 베타2 화면·결과 정보 정리, 제어 경로 보존 / 2026-11-10 한국 시간

[수동 베타2](MANUAL_CONTROL_BETA2.md)는 사용 빈도에 따른 화면 순서, 버전, GUI 결과 수신 시각과 오류 안내를 개선했습니다. 기존 Core·WmiInterop·helper·GUI 실행 서비스·로컬 프로토콜·실제 정리·owner·quarantine·예약 소스는 동일하며 추가 Core 파일은 문자열 상수입니다. 고정3/7/3·설정≤1과 지원 범위도 유지합니다. 시간은 GUI에서만 기록하며 firmware 읽기의 정확한 시각이나 쓰기 권한으로 사용하지 않습니다. 기존 충전 효과·GUI 해제 근거는 유효하고 같은 시험/자료를 다시 요구하지 않습니다. 1093회귀·두 Release 각0경고/0오류·소스196/ZIP9항목 검산을 [검증 기록](reports/manual-control-beta2-validation.json)에 남깁니다. 새 베타2 Windows 화면/DPI 실기와 클라우드 실제 SDK/OEM/노트북 예약 접근은 없습니다. 아래는 이전 기록입니다.

## 최신 — 수동 GUI의 해제 경로 실기 확인 / 2026-11-10 한국 시간

[새 베타 결과](MANUAL_CONTROL_BETA_RESULT.md)는 보호 해제의 사전1 → 사후0, SDK3·설정1·읽기2, 관련 정리 Complete입니다. 상한·하한 미조회는 정상이며, 검토한 소스의 Result·ACK·Released 완료 조건과 일치합니다. 기존 80% 억제·해제 후85% 충전 재개 근거를 유지하고 같은 충전 기록이나 원본 자료를 다시 요구하지 않습니다. 이번 한 건으로 별도 조회·켜기 보고서, 재부팅 지속성·75% 하한·100% 완충을 새로 확인한 것으로 확대하지 않습니다. 다음은 수동 베타의 화면·결과 버전 정보·오류 안내 정리입니다. 이번에는 소스·테스트·ZIP을 보존했고 추가 하드웨어 동작이나 실기 재요청은 없습니다. [정제 기록](reports/manual-control-beta-disable-result-review.json)을 참조합니다. 아래는 이전 기록입니다.

## 최신 — 확인된 모델의 수동 GUI 제어 경로 연결 / 2026-11-10 한국 시간

이전 노트북 전후 시험에서 확인한 80% 억제와 1→0 해제 후 85% 충전 재개를 기반으로 [수동 GUI 베타](MANUAL_CONTROL_BETA.md)를 구현했습니다. 일반 GUI의 `asInvoker`, 명시적 동작별 관리자 helper, 고정 상태조회 3회·켜기 7회·해제 3회와 설정 최대 1회를 연결했습니다. 실제 join → `Result` → ACK → 자기 원장 해제 → `Released` 순서를 따르며 새 `ManualProtection-v1`만 사용합니다. 이전 단발 예산·목적·원본 소스는 복원하지 않습니다. metadata·모델 범위는 기존 Windows 10 x64·940X3G/930X3G·P05ACJ를 유지합니다.

1081개 회귀, 두 Release 빌드의 경고·오류 0개, 소스 195개·ZIP 9항목·Release IL 독립 검증을 [정제 기록](reports/manual-control-beta-validation.json)에 남겼습니다. 새 GUI/helper 조합의 실제 노트북 실행은 아직 미검증이며, 클라우드의 실제 OEM·SDK·노트북 marker 접근과 원본 decode·검색도 없습니다. 지원 조건이 불명확할 때는 쓰기를 허용하지 않고, 초기 상태·절전 복귀·실패 뒤에는 명시적 상태 확인부터 수행합니다. 자동 polling OEM 호출·재시도·원복·부팅 적용·드라이버/서비스/보안 변경은 없습니다. SID는 같은 계정의 pipe ACL에만 내부 사용하고 개인정보·nonce·raw frame을 보고하지 않습니다. 아래는 이전 기록입니다.


## 최신 — 80% 억제와 해제 뒤 충전 재개를 전후 실기로 확인 / 2026-11-09 한국 시간

[전후기능검증](PROTECTION_CONTROL_FUNCTIONAL_RESULT_AND_GUI_PLAN.md):해제전AC연결중62→80%상승뒤80%/NotCharging20개샘플(첫끝241초),새1→0도구는pre1/post0·read2/receipt·SDK3/set1·Complete,해제후35개Connected/Charging·80→85%입니다. 오류·30초초과gap0으로기대된제어흐름과일치하며 **이모델·이번조건에서충전상한억제/해제재개를기능적으로확인한실기근거**입니다. 단일표시나저장후보만의관측으로축소하지않습니다.

전류/충전기레지스터독립측정·하한75재개·100%완충·재부팅/절전지속·다른모델은미검증이며과거파일을현재모드로인증하지않습니다. 일반GUI미구현과하드웨어경로부재를구분하고수동제어통합을다음목표로정했습니다. 원본decode/새firmware호출/marker접근/프로그램변경0이며모든단발예산은소모됐습니다. 추가실기·자료재제출불필요, [정제집계](reports/protection-off-before-after-result-review.json)에결과를보존합니다. 아래는이전기록입니다.

## 최신 — 별도 승인된1→0 해제 도구 구현 / 2026-11-09 한국 시간

[구현·사용 절차](PROTECTION_1TO0_IMPLEMENTATION.md)에따라새목적 `Protection1To0-v1`의사전1/read→semantic0/set최대1→사후0/read최대3SDK를구현했습니다. 저장source의mode0+소프트웨어상태reset 의미만사용하며임계값100설정/기존값복원/충전재개성공으로확대하지않습니다. 기존ON상태의AC관찰을먼저보관하고정상후보전환·실제정리Complete일때같은AC의후속관찰을안내합니다. 기존0→1실기1/80/75는과거보고이며새사전값을대체하지않습니다. 새1→0도구의실제Windows/노트북결과는아직없습니다.

새86개포함973회귀·portable/전체net48참조Release각0경고/오류와Release테스트도우미부재·소스/ZIP독립대조를 [정제검증](reports/protection-1to0-implementation-validation.json)에남겼습니다. 실제원본새decode/검색·OEM/노트북예약접근은0이고이전모든시험소스·ZIP을보존했습니다. 새프로그램은사용자START뒤새purpose1회만다루며예전marker접근·초기화·retry·ON/원복·직접threshold·driver/service/보안변경0입니다. 일반GUI실제제어와상시상태조회는계속Unsupported입니다. 아래는이전기록입니다.

## 최신 — AC 미연결 관찰 수신·보호 해제 최소안 / 2026-11-09 한국 시간

[첫 관찰](CHARGE_EFFECT_OBSERVATION_RESULT.md)의16개 샘플은 모두 AC 미연결·방전이며 잔량75→74%, 오류·긴gap0입니다. 사용자가 충전기를 연결하지 않았다고 확인했습니다. Windows 기록·로컬 저장은 동작했지만 충전 억제/재개는 관측 기회가 없어 성공·실패를 판정하지 않습니다. 직전1/80/75는 과거 저장 후보이고 이번 파일은 현재모드·지속성 조회가 아닙니다.

저장된 동일 EC 분석에서 보호 모드의 소비자는 EC 내부 polling 정책이므로 반복setter가 필수라는 근거는 없습니다. 먼저 기존 앱으로 AC 연결 상태를 관찰합니다. [다음1→0 구현 승인안](PROTECTION_1TO0_IMPLEMENTATION_PROPOSAL.md)은 새목적의pre1/set0/post0 최대3method이며, mode0+소프트웨어상태reset을 임계값100설정·이전값복원·충전재개 성공으로 바꾸지 않습니다. 새 실제코드·실기예산·EXE/ZIP·원본decode/검색/실행0이고 일반GUI제어Unsupported를 유지합니다. [정제 검토](reports/charge-effect-and-off-proposal-review.json)에 자료·소스 보존과 새구체안을 기록했습니다. 아래는 이전 기록입니다.

## 최신 — 최초 보호 설정의 저장값 전환 보고 / 2026-11-09 한국 시간

[사용자 결과](STORED_TRANSITION_RESULT_AND_OBSERVATION.md)에서 사전 `0 / 0 / 0` → 사후 **`1 / 80 / 75`** 후보 일치, 여섯 읽기 후보 수용, 설정 `ReceiptOnly`, 실제 종료 뒤 SDK7/set1 및 관련 정리 `Complete`가 보고됐습니다. 보호 설정의 저장 경로에 접근한 유의미한 결과입니다. 이번 수신 TXT의 도구 판정을 보존하며 원시 프레임의 독립 재검증·텍스트 인증·현재 보호 상태·충전기 내부 설정·전기적 제한·재부팅 지속성을 관측했다고 주장하지 않습니다. 기존 고정 `설정 효과: Unknown` 문구는 독립 사후 후보 일치를 무효화하는 실패 코드가 아닙니다.

최초 설정과 과거 단발 시험은 모두 종료·소모됐습니다. 새 일반 GUI는 과거 결과 검토와 기존 `GetSystemPowerStatus` 스냅샷의 수동 관찰만 추가하고, 새 OEM 조회·펌웨어 쓰기·초기화·marker 접근·Mock 관측·실제 제어 활성화는 없습니다. Windows의 80% 유지나 NotCharging을 전기적 제한 성공으로 판정하지 않습니다. 실제 보호 조회·제어는 계속 `Unsupported`이며 다음은 재설정 없는 일상 사용 상태 관찰입니다. 검증 수치와 패키지 해시는 [새 정제 기록](reports/stored-transition-observation-validation.json)을 참조합니다. 아래는 이전 기록입니다.

## 최신 — 명시 승인된 최초0→1 설정 시험 도구 / 2026-11-09 한국 시간

사용자가구체안에명시승인한뒤 [고정단발도구](PROTECTION_0TO1_IMPLEMENTATION.md)를구현했습니다. 저장proof의3개읽기대상과semanticsetter1을고정하고새purpose예약·같은전체owner·lazySDKleaf·세종료join·strict응답·정제계측을연결했습니다. Mode0일때만설정최대1/전체최대7이며80/75를덮어쓸수있고OFF/복원은없습니다. 기존A/Access1/Query65소모상태와일반앱Unsupported는유지합니다.

새50개포함854회귀·두Release빌드0경고/0오류,Release테스트helper부재와ZIP7항목/CRC/6체크섬/빌드·137source지문을독립검증했습니다. 새Windows SDK·노트북·firmware설정호출은클라우드에서0이며새실기성공은아직없습니다. 저장source대조를재사용했고원본새decode/검색/실행0입니다. 다음은새도구의승인된1회결과만평가하며설정receipt·저장후보·충전기·전기적제한을구분합니다. 아래는이전기록입니다.

## 최신 — 최초0→1 설정 시험의 조건부 구현 제안 / 2026-11-09 한국 시간

[구체안](PROTECTION_0TO1_IMPLEMENTATION_PROPOSAL.md)은 저장setter근거·성공한과거모드읽기·804대역회귀를 적용해 새준비1회/최대7method(read6/set1)를 한정합니다. 실제쓰기/현재threshold/충전효과를 새로 관측한 것은 아닙니다. 정상플랫폼전제를 유지하며 새selector/전체writer/livehash조건을 추가하지 않습니다. 설정1은80/75를 덮어쓸 수 있고 역방향·복원·재부팅원복보장은 없습니다.

SDK검토는 기존하위transport/input/callback/cleanup을 재사용하고 per-frameowner·A의settingwrites0경로를 새setter로확대하지 않는 구현지도를확정했습니다. 별도명시승인전 실제code/SDK호출·새artifact0,이번C#빌드/회귀미실행입니다. 804/두Release0/0은 이전2923cd6 기록이며src/tests/ZIP을 보존합니다. 아래는 이전 기록입니다.

## 최신 — 단계별 응답 대응과 종료 인계의 대역 연결 / 2026-11-09 한국 시간

[내부 바인딩 원형](BOUND_STAGE_HANDOFF_PROTOTYPE.md)으로 응답 판정과 전체 owner를 연결했습니다. 로컬 참조·자원 일회용·비교8tuple중복 검사와 세 종료task의 독립 join을 검증했고, 새 receipt evidence는 setter실행·저장변화·실제충전성공으로 승격하지 않습니다. 새18개 포함804통과·두 Release빌드0경고·0오류입니다. 이는 대역 연결 검증으로서 새 firmware source·노트북 관측이 아닙니다.

실제 고정주소/요청·SDKleaf·App은 추가하지 않았습니다. SDK수명설계는 기존invoke stack/terminal/capture·handler/output/subscription·input정리의 합성이며 미시작단계자원을 선등록하지 않는 조건을 명시합니다. 로컬 binding이나 종료task약속은 hardware/freshness인증이 아닙니다. 실제쓰기0·Unsupported·기존소모예약보존,새실기/자료재제출불필요를 유지합니다. 아래는 이전 기록입니다.

## 최신 — 조회 후보와 setter 응답의 의미 분리 / 2026-11-09 한국 시간

[순수 응답 판정기](PROTECTION_REPLY_CONTRACTS.md)를 구현했습니다. 임계값 전체byte 영역은 입력 첫 성분과 겹치므로 같은 값은 합법적인 read와 미갱신echo를 구별하지 못하며 후보 없이 보류합니다. 선택 setter는 전체10개 메시지byte를 보존하므로 정상echo도 `ReceiptOnly`입니다. 이는 저장된 proof의 재적용이며 새 firmware decode·source 발견·실기 관측이 아닙니다. 공통 실패의0표본, 형식·보존·domain 검사와 귀속 한계를 회귀로 보존했습니다.

새27개 포함786C# 통과·portable/전체net48참조 Release 각각0경고·0오류입니다. 실제 설정 명령·SDK·App 연결·예약 접근0·Unsupported를 유지합니다. 독립적인 setter 성공코드 부재를 영구 조회 금지 조건으로 삼지 않고, 향후 엄격한receipt+실제close 뒤 독립readback의 전이를 구체 시험 계약에서 분리해 검토합니다. 새 노트북 실행·자료 재제출은 불필요합니다. 아래는 이전 기록입니다.

## 최신 — 전환 순서·전체 owner의 대역 구현 / 2026-11-08

[고정 명세와 내부 원형](SEVEN_STAGE_COORDINATOR_PROTOTYPE.md)을 구현했습니다. 기존 source의0→1 기대값과 실제 관측 필드를 분리하고 사전0·사후1/80/75를 판정합니다. 단일 owner의 전 단계 유지·actual close 인계·stop/deadline·별도 peer 경합은 가짜 역할과 수명으로 검증했습니다. 새32개 포함759회귀와 두 Release 빌드0경고·0오류입니다.

새 source decode나 실기 관측은 없습니다. Access1의 과거 후보0을 새 사전값으로 사용하지 않으며 응답 귀속·fixed threshold getter·setter ACK의 실제 codec·SDK 연결은 남아 있습니다. gate 소유권 자체가 불명인 영구 보유 경로는 소스 검토 범위입니다. 실제 쓰기 코드·예약·App 연결0·Unsupported를 유지하며 새 노트북 실행·자료 재제출은 불필요합니다. 아래는 이전 기록입니다.

## 최신 — 고정 읽기의 후보0 관측 / 2026-11-08

[Access1결과](ACCESS1_STORED_ZERO_RESULT_AND_NEXT.md)는Elevated·준비/SDKReady·ReplyReceived·StoredModeCandidate0·정리Complete입니다. 실제노트북의선택된읽기를도구가판정한사용자보고로보존하며rawbyte독립재검증/현재보호OFF/임계값/충전제어성공으로확대하지않습니다. 실제binary/장치/계정/시각해시를새로요구하지않습니다. 모든과거예약소모유지·재실행0입니다.

새일반GUI는기존TXT의오프라인기록검토만추가해actualMode/controller/desiredMode와분리했습니다. parser12/VM6 포함727회귀·두Release빌드0/0과실제제출텍스트의순수parser실행을검증했습니다. 새SDK/OEM/Global/노트북예약접근0입니다.

[전환설계](PROTECTION_TRANSITION_REVIEW.md)는knownsemanticsetter/0→1초기화80·75/동일값조기return/비활성reset/normal96·97/ACKvsreadback/지속성미확정을정리합니다. 향후0→1기준7method(3read+1set+3read)는사전0만진행하며fixedthresholdgetter와setter응답명세·전체ownercoordinator가남았습니다. source재검색/모든writer부재조건을추가하지않고현재write승인/코드/시험0·Unsupported를유지합니다. 아래는이전기록입니다.


## 최신 — 승인된 추가 예산 Access1 연결 / 2026-11-08

[Access1 도구](FIXED_READ_ACCESS1_IMPLEMENTATION.md)는 사용자 별도명시승인에 따라 기존A소모를유지한 추가준비1회/method최대1만 구현했습니다. 같은계정수동관리자·TOKEN_QUERY/Elevated사전차단·직접START·새전용영속예약선소모 순서입니다. 예전예약읽기/복구0,실패뒤자동추가시험0입니다.

기존고정요청/metadata/SDK/owner/CallCanceled·actualclose·정상플랫폼전제·candidate검증은바꾸지않았습니다. 신규storage9 포함709C#통과·portable/전체net48참조0/0, 선택IL/source50·ZIP48정적검산을수행했습니다. 이정적수는앱회귀/하드웨어분석률과합산하지않습니다. 새firmwareedge/실기응답은0이고cloud원본/SDK/OEM/Global/노트북예약접근0입니다. 실제후보0/1은현재임계값/충전제어성공의증거가아니며Unsupported유지입니다. 아래는이전기록입니다.


## 최신 — 일반 실행의 A 준비 열거 거부 / 2026-11-08

[새 결과](FIXED_READ_A_ACCESS_DENIED_RESULT.md)는 Claimed·AccessDenied·MethodEnumeration·호출없음입니다. 사용자가 일반 실행임을 확인했지만 TokenElevation 직접 관측은 없습니다. 모델/BIOS/상세metadata단계 통과와 실제target선택·RNG/SDK/owner/method미진입을 구분합니다. FF/gate/driver부재/충전기능부재 판정은 불가합니다.

저장된 일반토큰거부/상승완료·LocatorReady를 재사용해 안내 누락을 정정했습니다. query/options를 추측 변경하거나 같은 권한 비교를 다시 요구하지 않습니다. read-only 토큰 사전 admission·세부 단계/고정오류·최초 예외와 정리오류 분리를 구현해 현재700회귀와 portable/전체net48참조빌드0/0을 검증했습니다. 신규실기·hardware/Global/예약접근0이며 고정요청·SDK호출·예약규약은 바꾸지 않았습니다.

기존A는 종료·소모 유지이며 관리자 재실행·marker우회를 하지 않습니다. [추가준비1회안](FIXED_READ_A_ADDITIONAL_TRIAL_PROPOSAL.md)은 별도승인 전 미구현입니다. 충전제어Unsupported·B/쓰기/재시도금지는 유지합니다. 아래는 이전 기록입니다.


## 최신 — 승인된 fixed read A 구현 / 2026-11-08

**구현:** [별도 단발 도구](FIXED_READ_A_IMPLEMENTATION.md)는 사용자가 승인한 고정 저장 byte 조회만 연결합니다. 새 목적 영속1회 예약→exact profile/metadata→sealed request→고정SDK entry→관련 actualclose 순서이며 method최대1/sample0~1/handshake·초기화·재시도·설정 쓰기·B fallback0입니다. 정상 플랫폼 전제는 구체안대로 유지하고 실제P05 provider/typed edge를 새로 발견했다고 주장하지 않습니다.

**검증/한계:** 새39개 포함688C# 통과·portable/전체net48참조 Release0경고·0오류, 독립template/proof27대조와 읽기 검토를 수행했습니다. 실제Windows SDK·OEM·하드웨어·Global·노트북예약 접근은0입니다. 후보0/1은 현재임계값·충전 적용의 증거가 아니며 실제 제어 Unsupported입니다. 새ZIP은 삼성원본/firmware/과거실험EXE 없이 별도도구만 제공합니다. 새 결과TXT만 필요하고 기존자료 재제출은 불필요합니다. 아래는 이전 기록입니다.


## 최신 — SDK 취소 수명 보강·조건부 단발 구현 제안 / 2026-11-08

**확인한 결함:** .NET48 문서는 내부 `CallCanceled`도 실제 중단을 보장하지 않는다고 명시합니다. Windows adapter가 이를 terminal로 전달하던 [조기 정리 결함을 수정](SDK_CALL_CANCELED_LIFETIME_FIX.md)했습니다. 새3개 포함649C# 통과, portable/전체 net48 참조 Release0경고·0오류입니다. 실제 노트북에서 이 결함을 관측했거나 SDK를 실행한 결과는 아닙니다.

**전제와 판정:** 새 공식 대표 PiSmmCore source는 참조 IPL의 공유 Context→실제 normal entry→inline typed 처리→NULL-root→반환을 연결합니다. P05의 실제 제공자/typed edge 발견은0입니다. [구현 검토안](READ_TRIAL_A_IMPLEMENTATION_PROPOSAL.md)은 정상 등록·inline 관련 처리·같은 초기화 완료/비재진입 P05 stream을 **명시적 적용 전제**로 사용합니다. 같은 stream 근거에 제공자 본문 복구와 별도 공통 lock을 추가로 요구하던 기준을 정정한 것이며 UEFI나 API 성공이 위 전제를 증명하는 것은 아닙니다. 관련 독립 AP/direct/domain 우회·deferred 처리·정상 조건 불적용의 구체 반례가 있으면 재평가합니다.

**경계:** 새 firmware 호출 코드·실제 요청은 별도 명시 승인 전까지 추가하지 않습니다. method최대1/sample0~1, handshake·초기화·재시도·설정 쓰기·B fallback0의 고정 저장 byte 조회안입니다. 후보0/1은 실제80/75임계값·충전 제한 증거가 아닙니다. public 차단·보호 조회/제어 Unsupported·old consumed 예약 금지와 기존 ZIP을 유지합니다. 추가 실기/자료 제출은 불필요합니다. 아래는 이전 기록입니다.


## 최신 — 실행 당시 UEFI 부팅 사용자 관측 / 2026-11-08 수신

**관측:** 사용자 보고의 새 부팅 항목이 Complete·UEFI였습니다. [관측 기록](WINDOWS_BOOT_UEFI_RESULT.md)은 실행 당시 범위이며 시각·권한·파일 해시는 미관측입니다. legacy BIOS를 이유로 특정 Windows EFI 변수 OS 경로를 제외할 수 없으므로 해당 경로를 분석 범위에 유지합니다.

**한계:** UEFI는 proxy cache nonnull·실제 표준 제공자 선택·EFI 변수 접근 성공·indexed 보호 순서·Secure Boot·배터리 보호 상태가 아닙니다. 정상 NULL-cache legacy fallback과도 모순되지 않습니다. 전체 Windows GUI/SDK/펌웨어 검증으로 확대하지 않고 공개 차단·Unsupported를 유지합니다. 추가 자료·반복 실행은 필요 없으며 동결 조사는 재개하지 않습니다. 코드·배포물 변경과 이번 빌드/회귀는 없습니다. 아래는 이전 기록입니다.

## 최신 — Windows 부팅 방식과 표준 EFI 변수 경로의 적용 범위 / 2026-11-08

**새 관측 기능:** [구현·공식 계약](WINDOWS_BOOT_FIRMWARE_UPDATE.md)은 GetFirmwareType으로 현재 Windows의 BIOS/UEFI/Unknown과 조회 상태를 기존 삼성 보고서에 추가합니다. 공식 enum 문서는 실제 부팅 방식을 설명하며 legacy에서는 표준 EFI 변수 API가 지원되지 않습니다. BIOS는 그 특정 OS 소비경로를 제외할 수 있을 뿐 다른 firmware/SMM/driver 부재가 아닙니다. UEFI·Unknown·오류는 actual proxy/cache·indexed 보호 순서를 입증하지 않습니다. 현재 노트북의 결과는 아직 없습니다.

**새 source 범위:** 기존 231PE의 선언 debug/COFF/export metadata와 저장된 P04 changed FV 출력313개를 후보 선택에 사용했으나 새 공급자·typed/보호 edge0입니다. 동일 P05 GUID/operand·entry/state 검사는 재개하지 않았습니다. 이 메타데이터 조사 성공을 통신 경로 복구로 세지 않습니다.

**검증·경계:** 새18개 포함646C# 통과, portable/전체 net48 Release 경고·오류0이며 새 ZIP의6항목/CRC/5체크섬/build-byte/source fingerprint/asInvoker/x64/net48을 독립 확인했습니다. Windows API/GUI 실기는 미확인입니다. EFI 변수 접근·OEM·삼성DLL 초기화·실험실행·예약·보안/드라이버/펌웨어 변경은 없으며 실제 보호 조회/충전 제어 Unsupported를 유지합니다. 아래는 이전 기록입니다.

## 최신 — 통신 진입과 공통 owner 대조 / 2026-11-08

**결과:** [보호 순서 조사](INDEXED_ORDERING_CONTRACT_REVIEW.md)에서도 새 supplier/typed 경로·공통 owner를 확보하지 못했습니다. 실기 전 핵심 첫 단계는 미완료입니다. 기존 정상 root·legacy fallback·proxy 조건과 입력 분리·ISR·SDK의 긍정 근거를 유지하며 미관측을 실제 race나 영구 미지원으로 바꾸지 않습니다.

**확인한 구분:** 대표 구현의 PE bootstrap, 실제 SMI entry 등록, runtime message/Trigger는 다른 경계입니다. assertion 뒤 flag를 성공 인증으로 쓰거나 P05 deferred function을 reference message pointer에 대응시키지 않습니다. variable-family busy·flash nesting/local busy·hook state도 공통 자원 소유권과 구분합니다. 이 선택 범위에 SABI가 같은 owner로 참여한다는 새 source 연결은 없습니다.

**범위:** 기존 자료의 대조·한정 검산·독립 읽기 검토만 수행했습니다. 같은 검색·legacy decode는 재개하지 않았고 이 대조도 동결합니다. C#/SDK/tests·EXE/ZIP이 같아 빌드/C#회귀는 미실행이며628/전체 net48 Release0/0은ae8f8e7 이전 기록입니다. 실제 호출·원본 실행·예약 접근·환경 변경0, 공개 차단·Unsupported 유지이며 새 실기·파일 제출은 필요 없습니다. 아래는 이전 기록입니다.

## 최신 — 고정 대상 의미·EC 공유 구간·SDK 수명 적용 / 2026-11-08

**대상:** [적용 검토](FIXED_READ_APPLICABILITY_REVIEW.md)는 초기화/설정 writer/충전 정책 consumer의 같은 mode cell과 generic XDATA reader를 조건부 모델 아래 대응시켰습니다. unchanged1은80/75를 다시 쓰지 않으므로 후보1만으로 현재 임계값이나 실제 충전 제한을 입증하지 않습니다. 옛32/32 exploratory와 후속48/16모형, 동일 byte의 재검산과 다른 role anchor를 분리하며 새 이미지 불일치나 분석 재시작으로 해석하지 않습니다.

**자원·SDK:** 정상 proxy의 PIC mask/ordinary RAM staging/status를 private Runtime hook의 EC indexed 접근과 구분했습니다. copy/strlen의 직접 I/O 부재를 모든 효과 부재로 확대하지 않고 통신 제공자를 숨은 독립 actor로 중복 세지 않습니다. 관련 hook의 동일 보호 순서 귀속은 아직 미완료입니다. 현재 코드의 입력/terminal/capture/정리 계약과 cached.NET48 참조 XML을 대조했고 v8대표 구현·실제Windows관측과 구분했습니다. Completed.Status와 method ReturnValue도 별개입니다.

**한계:** source·역할 crosswalk/정적 검산과 독립 읽기 검토만 수행했습니다. 새 provider/실제 typed edge/실기 race0, public 차단·Unsupported 유지입니다. C#/SDK/tests·EXE/ZIP은 변경하지 않아 빌드/C#회귀 미실행이며628/전체 net48 Release0/0은ae8f8e7이전기록입니다. 실제 SDK/OEM/hardware/Global/과거예약·원본실행·환경변경0, 새노트북실행·재제출불필요입니다. 아래는 이전 기록입니다.

## 최신 — PI 통신 계약과 단발 조회 명세 적용 / 2026-11-08

**새 출처:** [계약 대조](PI_COMMUNICATION_CONTRACT_REVIEW.md)는 공식 edk2의 고정 UDK2014 branch/현대 tag 자료8개를 읽었습니다. PI 원문 HTML은 HTTP403으로 미확보입니다. 헤더의 successfully posted를 handler 완료로 확대하지 않고, 대표 구현의 Trigger/직접 SmiManage 호출 순서와 P05 구현 근거를 구분합니다. UDK2014 이름이나 현대 MM alias로 P05의 PI버전을 단정하지 않습니다.

**판단:** [통합 조회 명세](FIXED_READ_TRIAL_SPECIFICATION.md)로 검토 가능한 조건부 제안은 정리했습니다. 표준 제공자 본문 복구만을 유일한 필수조건으로 두지 않으며 관련 indexed 게시자의 동일 보호 순서 적용 근거가 남습니다. 정상 legacy와 proxy 교체의 긍정 근거·known worker 입력 비훼손은 유지합니다. SMM이라는 분류와 동기 반환만으로 바깥 WMI 교환이나 indexed 상호 배제가 생기지는 않습니다. 초기화 완료·비재진입의 같은 실행 stream에 대해 확보한 순서 근거는 유지합니다. gate 초기 닫힘은 A의 유용성 한계이고 새 실측 조건이 아닙니다.

**검증·한계:** 각각70개 순서의 제한된 기호 모형2개와 간섭 가능 순서2개, 보호 전제 추가 시 각각2개 순서를 검산했습니다. 실제 PI/P05 실행 모델·race 관측·앱 테스트가 아니고 새 provider/실제 typed edge0입니다. source/proof pin과 독립 읽기 검토는 정제 기록에 남깁니다. C#/SDK/tests·배포물은 같아 build/C#회귀 미실행,628/전체 net48 Release0/0은 ae8f8e7 이전 기록입니다. 실제 SDK/OEM/hardware/Global·과거 예약 접근·원본 실행·환경 변경0, public 차단·Unsupported 유지이며 새 노트북 실행·재제출은 필요 없습니다. 아래는 이전 기록입니다.

## 최신 — 실기 전 오프라인 시나리오·정제 기록 구현 / 2026-11-08

**소프트웨어 준비:** [리허설 계획](READ_TRIAL_REHEARSAL_PLAN.md)과 test-only CLI로 공개 차단·사전 취소·fake gate timeout·early terminal/call-exit 대기·terminal 유실·유효 frame 귀속 불명의 6사례를 실행했습니다. 실제 관측 enum/카운터만 기록하고 bounded timeout과 합성 정리 후 상태를 분리합니다. 예상 밖 fake Invoke와 input cleanup 실패의 회귀도 보강했습니다.

**검증:** 새11개 포함628개 통과·실패/skip0, 리허설6개 통과(전체와 중복), portable 테스트/전체 net48 참조 Release 빌드 경고/오류0입니다. 초기 Linux WPF task의 MSB4062는 개발 빌드 프로세스에서 ReadyToRun을 끄고 해결했으며 노트북·제품 정책 변경은 없습니다. 실제 SDK/provider/OEM/hardware/Global/소모 예약 접근은0입니다.

**남은 범위:** 원래 공급자/실행 영역 미연결과 실제 고정 읽기 명세는 해결되지 않았습니다. 펌웨어 재검색은 하지 않았고 생산 코드·앱/배포물·실제 제어 상태는 그대로입니다. 테스트 대역의 IsValidFrame/Ready나 fake cleanup을 실기 완료로 승격하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 표준 통신 제공자 후보·역방향 source 조사 / 2026-11-08

**조사 결과:** [후속 검토](COMMUNICATION_PROVIDER_CANDIDATE_REVIEW.md)에서도 실제 제공자→typed dispatch를 확보하지 못했습니다. 실제 게시 Base2 method0의 동적 공급원이 완전한 InSmm 출력 leaf임을 연결해 후보에서 제외했습니다. 역방향 native slot operand 검색의 호출 후보6개는 USBRT 계산 record이고 SMST receiver로 연결되지 않아 typed 호출로 수용하지 않습니다. 전역적인 제공자 부재나 실제 위험 actor 발견이 아닙니다.

**자료·수신 조건:** 기존 section/index231 hash multiset·7FV/390표준압축 coverage는 재사용했습니다. index 밖274개 겹침 영역에서 이번 bounded 후보를 찾지 못했으며, 기존 nested EFI application의 별도 decoder 범위도 확인했습니다. 완전 Nvram wrapper/server는 retained buffer에서 입력을 구성하므로 사용하지 않는 incoming buffer와의 alias를 추가 요구할 이유가 없습니다. 실제 handler 선택·영역·retained slot 유효성은 별도입니다.

**범위와 검증:** 후보군과 탐색 범위를 동결하며 새 게시 객체/함수 공급원/nonnull 선택 caller/새 실행 자료 근거가 있을 때만 재개합니다. 담당·root의 정적 검산 및 독립 읽기 검토를 통과했지만 provideredge/새제공자/실기race0이며 검사 수는 앱 테스트·분석률이 아닙니다. 코드·배포물 변경 없이 공개 ReadSpecificationUnavailable·조회/제어 Unsupported를 유지합니다. 아래는 이전 기록입니다.

## 최신 — Runtime의 부팅 후 중계와 선택된 알림 처리 경계 / 2026-11-08

**새 연결:** [후속 검토](RUNTIME_POSTBOOT_TRANSPORT_REVIEW.md)는 BDS의 기존 marker 다음 선택 continuation이 실제 RestoreTPL4를 거쳐 이미지 Load/Start로 가는 연결을 확보했습니다. 정상 pending/live Event·버퍼·선택 진행 조건에서 TPL8 교체 알림이 해당 restore 반환 전에 처리됩니다. 모든 Windows 부팅 경로나 현재 장치의 실제 전달을 입증한 결과는 아닙니다.

**교체·선택 조건:** 버퍼 할당/공유 게시 실패에도 초기화가 성공 0을 반환할 수 있고 교체 알림 등록 상태는 뒤 조회로 덮입니다. proxy store는 CRC 계산보다 앞서며 CRC 실패의 local rollback은 없습니다. 정상 교체가 끝난 분기에 초기 direct-host 경로를 동시에 경쟁자로 넣지 않습니다. 실제 공급 객체는 초기/알림 조회→같은 캐시→This/method0→VA 변환으로 연결되며 NULL만 legacy 선택, nonnull 호출 오류 뒤 fallback은 없습니다.

**남은 범위·검증:** nonnull 제공자 method0에서 typed dispatch로의 실제 source 연결은 미확정입니다. 알려진 legacy 정상 root/협력 mutex 근거는 유지하며 변수 guard 미공유를 정상 proxy 분기의 새 blocker로 두지 않습니다. 담당별 원본/decode·root mask/분기 검산과 독립 읽기 검토를 수행했습니다. 새 부팅 순서 binding1, 새 함수/게시자/race0이며 검사 수는 중복·앱 테스트 아님입니다. 코드/EXE/ZIP이 같아 빌드/C# 테스트는 미실행,617/0/0은62f2d2e의 이전 기록입니다. 아래는 이전 기록입니다.

## 최신 — 응답 거부 명세와 관련 참여자 적용 / 2026-11-08

**구체화:** [비실행 명세](FIXED_READ_ACCEPTANCE_SPECIFICATION.md)는 8개 보존 셀의 전체 zero 원소 하나를 제외한 비교 영역을 제안합니다. 단일 고정 old tuple과 균등·독립인 선택의 우연 일치 한계는1/(2^64−1)이며 실제 생성·측정은 없습니다. 이 한계는 수용된 결과의 오류 확률이나 신뢰도가 아닙니다. no-copy zero·echo·공통 실패·형식/내용 불일치의 거부 규칙을 구체화하고, 다른 producer·혼합 copy·충돌이 관측 검사를 통과할 수 있는 반례도 보존했습니다.

**구체 미완료:** 알려진 host Runtime SetVariable의 NV persistence→flash 후크→동일 indexed 게시자는 boot-only나 WSABI 협력 호출자로 자동 포함할 수 없습니다. 정상 SMM/WSABI의 기존 보호 근거는 유지하며, 이 Runtime 경로의 선택 조회와의 순서·보호가 구체 미완료입니다. Native·이름 없는 가능성은 연결 없이 실제 경쟁자로 추가하지 않습니다. 새 source edge·actor·race 발견0입니다.

**검증·범위:** 담당별 source/reference 검산, root 14사례/256추상조합·정확 분수 검산, 독립 검토를 수행했습니다. 수치는 중복되며 앱 test/coverage가 아닙니다. C#/SDK/배포물 변경이 없어 빌드/C# 회귀는 재실행하지 않았습니다. 공개 ReadSpecificationUnavailable·조회/제어 Unsupported·실제호출0을 유지합니다. 아래는 이전 기록입니다.

## 최신 — 입력 보호·응답 회수 구간의 합성 / 2026-11-08 한국 시간

**확인 범위:** [후속 검토](FIXED_READ_INPUT_AND_CAPTURE_REVIEW.md)는 command clear 뒤 ready가 열려도 현재 EC 응답 복사가 끝난 것은 아님을 source 순서에 연결했습니다. 현재 입력은 30바이트 upload되며 반환에 쓰는 앞 10바이트가 먼저 local로 포착됩니다. 뒤 20바이트 local 저장은 그 prefix를 덮지 않지만 indexed I/O는 전체 download까지 계속됩니다. 새 함수/edge·실제 race 발견은 0입니다.

**조건부 보호와 한계:** 정상 같은 SMM domain의 비중첩은 EC copyout을 덮고, 정상 획득한 전체 교환 협력 mutex는 참여 호출자의 바깥 WMI frame 회수까지 덮습니다. 전자는 SMM 밖 입력 저장·반환 읽기를 자동 보호하지 않으며 후자는 비참여 경로를 자동 포함하지 않습니다. 실제 참여자 가입·입력 안정성·새 게시/reader 실행 인증은 여전히 미완료입니다. 기존 worker inline 소비·영역 분리/ISR 보존·stale/echo 분석은 재사용 맥락입니다.

**검증·범위:** 담당별 정적 검산과 root 부분순서/footprint 검산·독립 읽기 검토를 수행했습니다. 검사 수는 중복되며 앱 테스트나 분석률이 아닙니다. 코드/테스트/배포물 변경이 없어 빌드/C# 테스트는 재실행하지 않았고 617개·빌드 0/0은 62f2d2e 기록입니다. 공개 ReadSpecificationUnavailable·조회/제어 Unsupported와 실제 호출 0은 유지합니다. 아래는 이전 기록입니다.

## 최신 — Windows/EC 바이트 계약의 합성 / 2026-11-08 한국 시간

**새 합성 범위:** [byte 계약](FIXED_READ_BYTE_CONTRACT_REVIEW.md)은 기존 개별 본문을 합쳐 현재 주소+반환을 함께 제공하는 upload/receive 분기만 남기고, payload high→low 주소 순서와 sample 치환/실제 보존 8개 셀·WMI tail4 소거를 확인했습니다. 새 firmware 함수/edge는 0이며 새 request/frame은 만들지 않았습니다.

**응답 귀속의 제한:** common failure marker와 sample 투영이 달라 실패에도 sample 자리는 zero입니다. command-only 성공도 반환 data를 복사하지 않아 sample 자리가 zero입니다. 미래 scalar-only 해석의 오인 조건이며 현재 제품은 이미 실패 prefix를 표시하고 mode decoder가 없으므로 제품 false-OFF나 실기 오류 발견이 아닙니다. 비실패 prefix·보존값 일치도 새 게시/reader 실행/신선함의 증거가 아닙니다.

**검증·남은 조건:** 세 정적 검산은 각각 관계/재사용 8/39·10/29·15/20을 통과했으며 서로 겹치고 앱 테스트 수가 아닙니다. indexed-window↔EC mailbox 대응 가정, 조건부 ISA/bank·현재 이미지, command/address 안정성과 관련 참여자·응답 귀속은 남습니다. 코드·테스트·SDK·ZIP은 바꾸지 않아 빌드/C# 회귀는 재실행하지 않았습니다. 617개·빌드 경고/오류 0은 이전 62f2d2e 기록입니다. 공개 SDK entry 차단·실제 조회/제어 Unsupported는 유지합니다. 아래는 이전 기록입니다.

## 최신 — 실기 읽기 명세 부재의 공개 entry 차단 / 2026-11-08 한국 시간

**구현:** [시작·중단 조건](READ_TRIAL_ENTRY_CONDITIONS_UPDATE.md)은 기존 인자/plan/identity/단발 claim/pre-cancel 뒤 public SDK entry를 ReadSpecificationUnavailable로 끝냅니다. SDK metadata/input claim/등록/호출/Dispose는 시작하지 않습니다. 기존 typed 기계 경로는 internal로 유지하며 승인 bool·빈 registry·미구현 Ready 분기는 추가하지 않았습니다.

**근거:** 조건부 target-write 없는 reader, 알려진 inline 입력 소비·영역 분리·ISR 보존과 관련 정상 반환은 유지합니다. 실제 고정 요청↔reader/대상, 관련 참여자 입력/재사용, 적용 가능한 완료·귀속/불명 결과 거부의 세 묶음은 아직 실기 명세로 닫지 못했습니다. gate-open 실측·모든 writer/IRQ·현재 EC 전체 hash를 새 필수조건으로 추가하지 않았습니다. 새 펌웨어 source edge나 실기 관측도 아닙니다.

**검증:** 새 8개 포함 617개 통과·실제 net48 참조 전체 Release 빌드 경고/오류 0입니다. 기존 SDK 19개 회귀는 internal seam에서 대역으로 검증하며 공개 entry의 실행 허가가 아닙니다. 실제 보호 조회·충전 제어는 Unsupported·새 실기/동일 자료 제출 불필요입니다. 아래는 이전 기록입니다.

## 최신 — 같은 SDK 대상·observer·입력으로 typed 호출 연결 / 2026-11-08 한국 시간

**구현:** [SDK binding](WINDOWS_WMI_SDK_DISPATCH_BINDING_UPDATE.md)은 계획의 opaque identity와 supplied ManagementObject를 참조 비교한 뒤 exact type·연결된 local scope·instance/class를 worker에서 검사합니다. readonly target/observer/parameters와 private options로 typed InvokeMethod 한 곳에 최대 한 번 진입하도록 연결했습니다. target은 borrowed이며 input pair의 정리/출력 alias 보호는 target 참조도 포함합니다.

**검증:** 새 19개 포함 609개 통과·실제 net48 참조 전체 Release 빌드 경고/오류 0입니다. production Windows 소스 8개를 SDK stand-in과 실행했으며 실제 System.Management runtime/provider·노트북을 호출한 것은 아닙니다. 캐시의 Microsoft v8 참조 1개와 선택 관계 5개는 재사용 대조이며 새 펌웨어 근거가 아닙니다.

**한계:** SDK overload 진입의 고정 참조와 횟수만 검증했습니다. 외부 Scope/Path/input mutation·native alias·SDK 내부 작업·현재 hardware 지원/신선함·실제 요청 의미를 인증하지 않습니다. 새 target/input 탐색·생성이나 보호 조회 template·앱/배포 ZIP 변경은 없으며 조회·충전 제어는 Unsupported입니다. 아래는 이전 기록입니다.

## 최신 — 입력 객체 소유권과 관련 종료 대기 연결 / 2026-11-08 한국 시간

**구현:** [owned 입력 경로](WINDOWS_WMI_OWNED_INPUT_LIFETIME_UPDATE.md)는 입력 두 wrapper의 공통 원자 claim에서 소유권을 인계받고, 기존 close/관련 정리가 끝난 뒤 두 concrete Dispose를 시도합니다. 준비 중 SDK 입력 작업·Unknown·보고 예외·막힌 lease 동안 입력을 유지하며, 입력이 root/embedded 출력으로 돌아오는 managed alias도 먼저 해제하지 않습니다.

**검증:** 새 18개 포함 590개 통과·실제 net48 참조 전체 Release 빌드 경고/오류 0입니다. SDK stand-in과 기존 synthetic 요청으로 검증했으며 실제 provider나 노트북을 호출한 결과가 아닙니다.

**한계:** 입력 보유는 supplied delegate가 실제로 같은 입력/target을 사용함을 인증하지 않습니다. 다른 COM alias·SDK 내부 copy·실제 호출 수·고정 요청의 읽기 의미·현재 gate/완료 귀속은 별도입니다. 새 펌웨어 근거나 실제 조회 명령/SDK dispatch·앱 연결·배포 ZIP 변경은 없으며 보호 설정 조회·제어는 Unsupported입니다. 아래는 이전 기록입니다.

## 최신 — 저장 reader 근거와 SDK 입력 준비 대조 / 2026-11-08 한국 시간

**확인된 범위:** [입력 준비 검토](WINDOWS_WMI_INPUT_PREPARATION_REVIEW.md)는 저장된 generic byte reader와 기존 WMI/SDK 경로를 대조했습니다. 선택 reader는 조건부 EC 해석에서 저장 mode byte를 읽고 대상에는 쓰지 않습니다. 별도 대상·gate·관련 참여자·신선한 응답 조건까지 충족됐다는 뜻은 아니며 새 펌웨어 연결을 찾은 작업도 아닙니다.

**구현·검증:** 공급된 SDK 입력 객체의 class/CIM shape를 확인한 뒤 고정 요청 사본을 Bytes→inData로 할당합니다. 두 wrapper를 SDK 접근 전에 함께 claim해 오류·부분 변경 뒤 재사용을 막고 caller 소유는 유지합니다. 신규 10개 포함 572개 통과·실제 net48 참조 전체 Release 빌드 경고/오류 0입니다. 테스트는 SDK stand-in이며 실제 provider는 실행하지 않았습니다.

**미확정:** 임의 supplied 객체의 method 출처·lazy 초기화·native 복사·다른 COM alias는 인증하지 않습니다. 실제 요청 template·SDK dispatch·앱 연결·배포 ZIP 변경은 없으며 보호 설정 조회·충전 제어는 Unsupported입니다. 아래는 이전 기록입니다.

## 최신 — A 선언 scope와 고정 요청 이행 경로 / 2026-11-08 한국 시간

**구현:** [단발 plan/binding](SINGLE_READ_PLAN_BINDING_UPDATE.md)은 정확한 관측Name/전체BIOS·선언한platform·local method target·상세metadata/MethodId1·완료열거/단일Active를 검사합니다. opaque token을 참조 비교하고 기존 요청을 복사·재구성해 prepared Run에 고정합니다. 공급 사실/참조 일치이며 실제 SDK target/read semantic/권한의 인증이 아닙니다.

**검증:** plan9/binding6/lifetime6의 신규21개 포함562개 통과·실제 net48 참조 전체 Release 빌드 경고/오류0입니다. 동시 같은plan 준비·alias재시도·SDK등록전 거부·고정 byte 전달과 기존 Unknown/lease/close를 SDK stand-in으로 검증했습니다. 실제 SDK method 수·현재gate·데이터신선함을 관측한 작업이나 새 펌웨어 근거는 아닙니다.

**범위:** A의선언budget을softwarehandoff1·자체추가경로0으로대응했으며opaqueframe의write0/read의미는입증하지않았습니다. B·oldOneShotcandidate/예약·실제SDKdispatch·앱등록·배포ZIP은그대로이고보호조회/제어Unsupported·새실기/재제출불필요입니다. 아래는 이전 기록입니다.

## 최신 — WMI 등록 준비를 세션 전으로 분리 / 2026-11-08 한국 시간

**구현:** [Preparation factory/handle](WINDOWS_WMI_PREPARATION_UPDATE.md)은 등록과 필요한 실패 정리를 Core 밖에서 끝내고 성공 handle만 단발 Run/Close를 제공합니다. raw source는 internal이며 미사용 close가 먼저면 session을 만들지 않습니다. += 시도 기록·등록 종료·early callback 정리를 join하고 준비 오류를 다음 조회의 terminal/출력으로 replay하지 않습니다.

**검증:** 새factory9/수명6 포함541개 통과·실제 net48 참조 전체 Release 빌드 경고/오류0입니다. 실제 실행은 동일 소스의 SDK stand-in이며 prepare failure의 gate/dispatch0·null handle·Run/Close 경합·Unknown 유지와 구독 정리를 검증했습니다. session0은 API/생성 위치의 코드 근거와 구분하며 합성 terminal을 실제 SDK 완료로 세지 않습니다.

**남은 경계:** Run 예약 후 실제 Invoke 전 외부 이벤트 위반은 기존 Core Unknown에 남을 수 있습니다. Ready/단발 delegate는 실제 SDK 횟수·지원·권한이나 COM/provider 종료를 인증하지 않습니다. 실제 호출·old Backend/예약·A/B 범위·배포 ZIP은 그대로이며 보호 조회/제어 Unsupported·새 실기/재제출 불필요입니다. 아래는 이전 기록입니다.

## 최신 — Windows SDK 타입 reader/event binding / 2026-11-08 한국 시간

**구현한 코드:** [Windows library](WINDOWS_WMI_TYPED_BINDING_UPDATE.md)는 scalar outData/DataBuffer와 UInt8 선언·exact runtime byte[]를 검사하고, 복사 후 concrete embedded/root Dispose를 분리합니다. dedicated observer의 raw handler 입장·completion phase와 capture proxy가 관련 handoff/구독 해제 시도를 실제 capture 전에 join합니다. 실제 InvokeMethod/Connect/Get·대상/명령/프레임은 없습니다.

**검증:** source stand-in 회귀21개 포함526개 통과·실제 net48 참조 전체 Release 빌드 경고/오류0입니다. signed 배열 호환과 completion 검사 뒤 새 handoff 누락을525개 중523통과2실패로 재현한 뒤 수정했습니다. 실제SDK runtime/COM/provider/Win10 이벤트 관측이 아니며 이전 private 수를 합산하지 않습니다.

**아직 미확정:** actual SDK terminal/queued callback·COM threading·native alias 전체 정리·cutoff 뒤 local 독립성은 새로 입증하지 않았습니다. 등록 실패도 현재 source 진입 뒤면 Unknown/pending이므로 미래 도구의 준비 단계를 분리해야 합니다. old Backend/예약·A/B 범위·배포 ZIP은 그대로이고 실제 보호 조회·충전 제어 Unsupported·새 실기/재제출 불필요입니다. 아래는 이전 기록입니다.

## 최신 — typed callback source 구현 / 2026-11-07

**구현:** [CallbackInvocationSource](CALLBACK_SOURCE_CAPTURE_UPDATE.md)는 명시적 dispatch/reader의 T 객체를 terminal window에서 선택하고, bounded clone·관련 Dispose 뒤 byte[]/고정 실패만 기존 transport에 전달합니다. T의 형식/terminal 출처는 공급자 계약이며 실제 SDK 타입 검사·event adapter는 아직 없습니다. claim 뒤 late 정리가 독립 local이라는 전제와 source Invoke1회가 실제 SDK 횟수를 인증하지 않는 한계를 유지합니다.

**검증:** 기본9+수명6의 새15개 포함505개 통과·전체 net48 Release 빌드 경고/오류0입니다. source stack이 끝난 뒤 독립 callback에서 막힌 reader/selected·duplicate·late Dispose를 만들어 host/lease 유지·terminal 재진입·중복 정리 억제를 검증했습니다. 합성 terminal finally 정리는 실제 SDK 완료 보장이 아니며 이전 private 검산 수를 합산하지 않습니다.

**실제 연결:** SDK reader/event adapter·실제 WMI/OEM/하드웨어·기존 Backend/예약·A/B 범위·배포 ZIP은 그대로입니다. SDK sink 소실·COM threading·모든 provider 활동 종료를 해결한 것으로 확대하지 않습니다. 실제 보호 조회·충전 제어 Unsupported·새 실기/재제출 불필요입니다. 아래는 이전 기록입니다.

## 최신 — host 결과 표시와 종료 대기 / 2026-11-07

**구현:** [RunAndCloseAsync](INVOCATION_HOST_LIFETIME_UPDATE.md)는 bounded 결과 뒤 admission을 닫고 표시 callback을 실행하며 finally에서 source/자기·공유 owner의 정리를 기다립니다. 시간 초과·취소·표시 예외가 Main의 조기 반환을 허용하지 않습니다. 새 tracker·실제 SDK source·앱 hook은 추가하지 않았습니다.

**검증:** 새6개 포함490개 통과·전체 net48 Release 빌드 경고/오류0입니다. 별도 fake-only 콘솔 child2개의 Main 생존·반복 stop·정리 뒤 exit를48검산으로 확인했으며 앱 수에 합산하지 않습니다. 합성 terminal 정리이며 실제 OS Ctrl+C·WMI/provider 종료 관측은 아닙니다.

**source 선택과 한계:** 저장된 SDK의 sync typed-output 경로는 비음수 즉시 상태를 보존하지 않으므로 기존 async Completed.Status 계약을 유지하는 방향입니다. 이것은 다음 구현의 선택이며 새 runtime 사실이 아닙니다. 다음은 선택 객체의 소유/형식 확인/분리/정리 source이며 SDK throw·terminal 소실을 source가 임의 완료로 바꾸지 않습니다. 기존 Backend/예약·A/B 횟수/상태 영향·권한은 유지하고 실제 보호 조회·충전 제어는 Unsupported입니다. 새 노트북 실행/재제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 공통 managed 호출 세션 / 2026-11-07

**구현한 소프트웨어:** [새 세션](MANAGED_INVOCATION_SESSION_UPDATE.md)은 명시적으로 공급한 source의 call exit·적용 가능한 terminal·선택 capture 종료를 기다리는 snapshot transport와 host입니다. 같은 source 참조의 단발 상태·identity를 공유하고 capture는 byte[] 복사와 앱 소유 고정 map으로 제한했습니다. terminal status가 권위 있는 값이며 source 신호는 실제 종료를 스스로 인증하는 기능이 아닙니다.

**검증:** 새15개 포함484개 통과·전체 net48 Release 빌드 경고/오류0입니다. source는 끝났어도 다른 owner의 lease.Dispose가 막힌 동안 peer close가 일찍 끝나는 문제를 추가 회귀로 재현했고482통과1실패→483통과로 수정했습니다. admission과 canonical cleanup barrier를 함께 게시하고 새 admission을 막은 뒤 해당 정리를 기다립니다. source·자기/공유 cleanup을 모두 기다리므로 Busy/quarantine을 종료 신호로 쓰지 않습니다.

**남은 실제 연결:** 실제 System.Management source·GUI close/프로세스 수명 hook은 없습니다. observer가 받는 terminal과 capture 사실의 적용 조건·신호 소실은 source 구현에서 검토해야 합니다. 삼성 원본·SDK·OEM·하드웨어를 실행한 검증이 아니며 기존 marker/backend/encoder·A/B 범위·배포 ZIP은 그대로입니다. 실제 제어 Unsupported·새 실기/재제출 불필요입니다. 아래는 이전 기록입니다.

## 최신 — SDK 오류와 관련 작업 종료의 분리 / 2026-11-07

**확인한 소스 범위:** [SDK 수명 검토](SDK_INVOCATION_LIFETIME_REVIEW.md)는 새 Microsoft dotnet/runtime v8.0.0 ManagementObject 참조1파일과 기존 observer/Backend를 대조했습니다. 정상 Backend는 SDK 정상 반환과 선택 completion을 기다립니다. 참조의 음수 immediate 상태는 sink/stub을 정리하고 throw하므로 같은 observer의 late terminal을 보장할 수 없습니다. 새 관계1개·선택 text17·재사용13·pins6이며 실제.NET48 일치·노트북의 호출 순서·Reset의 실제 throw를 입증하지 않습니다.

**private 증명:** 실제 SDK가 없는 single-use prototype로 call exit·적용 가능한 terminal·선택 capture settled를 분리했습니다.8개 case·48개 검산과 시험 빌드 경고/오류0입니다. Unknown 진단으로 종료 Task를 끝내지 않고 UI timeout/caller stop 뒤에도 lease/slot과 peer 차단이 유지됨을 확인했습니다. 이후 합성 terminal/capture로 모든 fake 작업을 정리했으며 이것은 실제 SDK 종료 보장이 아닙니다.

**한계:** terminal이 사라지면 수명은 pending으로 남고 helper는 신호를 만들지 못합니다. process 종료·lease 해제를 provider stop으로 바꾸지 않습니다. 앱/Core/public API·EXE/ZIP은 변경하지 않았고 전체 앱 검증은 반복하지 않았습니다.469개/빌드0은fc14fea 기록입니다. 실제 backend·하드웨어 호출·A/B 권한 변경 없이 Unsupported를 유지하며 새 실기·재제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — Bound 직접 실패의 격리 전파와 참여 범위 / 2026-11-07

**확인된 사실:** [후속 수정](BOUND_TRANSPORT_FAILURE_QUARANTINE_UPDATE.md)은 Bound async 경계가 snapshot transport의 직접 throw/null을 faulted/cancelled Task로 바꿔 cooperative owner의 기존 격리 정책을 소실시키던 문제를 고쳤습니다. 호출 자체만 내부 고정 표식으로 보존하고 owner가 canonical resource와 gate를 격리합니다. 새6개 포함469개 통과·전체 net48 Release 빌드 경고/오류0입니다. 반환된 task fault/cancel·null snapshot과 미진입의 재사용 대조도 유지합니다.

**정적 참여 범위:** 알려진 WSABI4개는 정상 Call의 입력 준비~응답 복사를 같은 협력 객체로 보호합니다. 선택 BSTR 할당 실패에서는 기본 throw handler와 해당 함수의 unwind closure에 mutex 해제 guard가 없는 관계1개를 추가 대조했습니다. 선택 실패는 method 전이며 상위 처리·모든 예외·현재 참여/abandon을 관측한 것은 아닙니다. native 경로의 같은 WMI host frame 사용은 미확정이고 Runtime의 확인된 공유는 downstream EC wire입니다.

**한계:** 격리/lease 해제는 공급자 작업 중단 증거가 아니며 기존 실제 SDK 내부 예외가 이미 async fault로 변환된 경우는 식별하지 못합니다. 실제 adapter 계약·관련 참여 규약·A/B 유용성은 별도입니다. 실제 backend/앱 등록/예약/encoder/배포 ZIP·시험 권한은 유지하고 제어는 Unsupported입니다. 새 실행/동일 자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 정상 반환의 조건부 연결과 EC outcome / 2026-11-07

**확인된 사실:** [후속 결과](WMI_ACPI_RETURN_AND_EC_REUSE_REVIEW.md)는 Microsoft의 Wmiacpi mapper 역할, WMI method 입출력, ACPI 평가/완료 계약을 기존 모델 선언과 대조했습니다. 같은 규약의 sender는 첫 준비 실패 시 upload/post를 생략하고 다음 호출도 zero-ready 전에는 게시하지 않습니다. 선택 reader의 입력 소비·결과 저장은 정상 dispatcher clear보다 앞섭니다. 새 EC source edge 발견은0개이며 기존 근거를 outcome별로 분류했습니다.

**명시 가정:** 정상 mapper가 저장 모델의 object/method·AML 인수·반환 buffer를 대응시킨다는 조건 아래 정상 평가/반환은 연결됨으로 동결합니다. 세부 WMxx/Arg2 규격 원문 미확보를 독립 blocker로 두지 않으며 새 반례나 관련 원문이 있을 때 재검토합니다. raw zero와 FF는 신선함·미게시를 각각 단독 인증하지 않습니다.

**미검증:** 실제 관련 외부 참여자의 admission 규약, 불명 dispatch의 관련 완료/소유권, 실제 adapter의 결과 분류와 선택 안의 유용성은 남습니다. [별도 비실행 대안 B](FIXED_MODE_READ_PROPOSAL.md)는 공유 gate 변경1회+조건부 읽기1회이며 초기화 없는 기본 A의 실패 뒤 추가하는 fallback이 아닙니다. B의 상태 지속·복원은 관측하지 않았고 승인/실행을 요청하지 않습니다.

문서·정제 기록만 변경했습니다. 앱/Core/테스트/EXE/ZIP 미변경·전체 빌드/단위 테스트 미반복이며463개·빌드 경고/오류0은1790a4b 과거 기록입니다. 실제 제어 Unsupported·추가 실행/자료 제출 불필요입니다. 아래는 이전 기록입니다.

## 최신 — 선택 조회 경로·gate 호출자·두 공유 버퍼 / 2026-11-07

[선택 WMI 경로 검토](SELECTED_WMI_ROUTE_AND_COMPLETION_REVIEW.md)에서 보존한 AML trigger와 PCH legacy SW 등록을 교차 대조했습니다. 조회는 이 경로를 거치며 별도 Runtime 변수 서비스의 typed 통신 미연결을 조회 진입 자체의 필수조건에서 제외합니다. 관련 EC 후크 게시자의 순서 문제까지 해소한 것은 아닙니다.

저장된 keyboard/jog caller는 조건부 조회에서 handshake와 응답 검증을 먼저 수행합니다. 이는 배터리 getter나 현재 gate 관측이 아니며 사후 handshake로 이전 응답의 신선함을 인증할 수도 없습니다. 선택 callback의 host snapshot/response copy와 EC command/data mailbox 재사용을 분리했습니다. 공식 WMI 문서3개도 정상 최종 성공과 클라이언트 취소를 구분합니다. 취소 통지는 provider 정지 근거가 아니지만 기존 단발 backend가 이 SDK 취소를 실행했다는 주장도 하지 않습니다.

실제 backend·새 시험·초기화 없이 Unsupported를 유지합니다. 문서·정제 기록만 변경했고 전체 앱 테스트/빌드는 반복하지 않았습니다. C#463개·빌드 경고/오류0은1790a4b 기록이며 이번 정적 검산과 합산하지 않습니다. 새 실행·동일 자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 관련 완료와 비실행 시험안의 비례적 조건 / 2026-11-07 한국 시간

[후속 재검토](PROVIDER_COMPLETION_AND_READ_TRIAL_REVIEW.md)는 비실행 제안의 조건을 실제 코드/실행 준비와 구분합니다. known worker 입력 소비·버퍼 분리·ISR 보존은 이미 위험을 좁혔으며 미확인 status/IRQ 전체를 독립 필수조건으로 되돌리지 않습니다. 실제 연결의 세 조건은 선택 경로/고정 대상/gate, 관련 전체 교환 소유권, 관련 완료/입력 비훼손/결과 귀속입니다. 실제 간섭 actor를 새로 확보한 것은 아닙니다.

우리 collector2파일의 private 하네스13검사는 선택 A completion/capture.Dispose 뒤 다른 B.Dispose가 남을 수 있음을 재현했습니다. managed drain 미보증이며 firmware/shared frame 진행의 증거가 아닙니다. dotnet/runtime v8.0.0 참조4파일의6관계도 현재 Windows10.NET48 일치나 provider/EC 정지를 입증하지 않습니다. 기존 gate 증거는 초기닫힘/현재미관측이며 여는 handshake를 읽기1회에 포함시키지 않습니다. 비실행안은 최대1WMI시도/EC읽기0~1·초기화0입니다. 실제 연결은 보류·Unsupported, app/Core/기존테스트/EXE/ZIP 미변경·전체검증 미반복이며463/빌드0은1790a4b 기록입니다. 새 실기·동일 자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 협력 owner와 고정 조회 판정 / 2026-11-07 한국 시간

[협력 교환 구현](COOPERATIVE_EXCHANGE_OWNERSHIP_UPDATE.md)에서 finite gate·전용 owner의 획득/해제·하위 task/취소 callback 종료·attempt별 stop CAS·abandon/해제 실패의 resource/gate identity 격리를 추가했습니다. lazy 고정 Global mutex adapter도 opt-in이며 실제 Global은 열지 않고 fake/unnamed Mutex로만 검사했습니다. 실제 Windows 상호 운용·모든 외부 참여자·provider 완료를 증명한 것은 아닙니다. 테스트463개·전체 빌드 경고/오류0입니다.

source 한정 조사에서는 요청 field와 고정 status 소비의 관계를 대조했지만 실제 외부 status/IRQ 생산자 새 연결은0개입니다. 인접 OR/helper의 ordinary byte 의미와 물리 MMIO/외부 처리 의미를 구분하며 기존 polling을 새 producer로 세지 않습니다. 요청 control→외부/controller/IRQ→준비·오류 status 간극은 그대로 동결했습니다. [고정1바이트1회 조회는 보류](FIXED_MODE_READ_DECISION.md)하며 live 전체hash나 모든writer 부재를 대신 요구하지 않습니다. 실제 hardware backend·배터리 명령·OneShot/예약·앱등록·드라이버/서비스/보안/펌웨어 변경 없이 Unsupported입니다. 새 노트북 실행·동일 자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 같은 전송 자원의 조정과 inline 입력 소비 / 2026-11-07 한국 시간

[후속 결과](SHARED_CHANNEL_COORDINATION_UPDATE.md)에서 FrameExchange의 active 상태를 동일 resource reference별로 공유하도록 수정했습니다. 같은 channel·같은 snapshot transport의 별도 래퍼는 실제 작업과 취소 callback이 모두 끝나기 전 재진입하지 못합니다. 별도 자원은 독립적입니다. 프로세스 내부의 FrameExchange 범위이며 외부 OEM mutex·직접 channel 호출·모든 WMI 참여자 보호가 아닙니다. 소모된 OneShot backend/Program/예약/승인·요청 encoder는 변경하지 않았습니다.

선택 EC worker의 원본 입력과 local byte/bit 소비는 terminal 요청 반환 전에 동기 실행되고 식별된 입력 영역은 query upload와 분리됩니다. 후속으로 입증된 것은 기존 polled finalizer이며 새 IRQ/status 생산자를 확보한 것은 아닙니다. helper 이후 pointer 상태를 반영해 잘못된 status-writer 후보를 제외했습니다. 관련 hardware/미확인 IRQ/alias/scratch까지 전체 비훼손은 미확정입니다. C#441개 통과·전체 솔루션 빌드 경고/오류0, source 선택 검산·독립 검토 통과입니다. 실제 제어 Unsupported·새 실기/OEM/예약 접근·자료 제출 없이 개발 소스만 제공합니다. 아래는 이전 기록입니다.

## 최신 — 작업 상태 생산자·읽기 소비 시점·Field Lock / 2026-11-07 한국 시간

[후속 검토](EC_QUERY_INPUT_AND_CLEANUP_REVIEW.md)에서 descriptor 하위 작업의 시작 성공이 active·완료 대기 상태를 생산하고 후처리 gate로 연결됨을 확인했습니다. 선택 staging/복사와 query mailbox 영역은 구분하지만 관련 하위 작업이 계속 소비할 입력을 조회 upload가 훼손하지 않는지는 미완료입니다. 이 특정 정리를 초기화/flash/종료 전용으로 이름 붙이거나 현재 Windows 겹침으로 관측하지 않습니다.

reader는 주소 성분을 따로 소비한 뒤 첫 성분만 결과로 바꾸며 known stable-command ISR이 필요한 register를 보존합니다. 사후 tail 일치는 반환 보존 관계일 뿐 소비 시점의 안정성·실행 identity를 단독 인증하지 않습니다. 두 raw DSDT의 Field Lock 선언과 NotSerialized method·trigger mutex도 전체 교환 소유권과 구분했습니다. 필요한 것은 특정 mutex의 강제가 아닌 관련 입력 준비~응답 회수의 무결성입니다. 기존 작업 비훼손·조회 취소의 안전한 실패를 최소 계약으로 반영했으며 실제 backend·새 시험 없이 Unsupported입니다. 문서·정제 기록만 변경, 앱·EXE·기존ZIP·하드웨어 미변경, 이번 빌드·단위 테스트 미실행·추가 실행/자료 제출 불필요입니다. 아래는 이전 기록입니다.

## 최신 — 부팅 순서와 legacy 정상 실행 영역 / 2026-11-07 한국 시간

[새 검토](EC_READ_HANDOFF_AND_BOOT_ORDER.md)에서 Nvram 복합 모듈의 DXE 의존성과 dispatch→BDS 호출 순서를 대조해, 발견·의존성·시작·등록 성공 조건의 알림 선행을 구체화했습니다. 별도 SMM 의존성과 혼합하거나 dispatch 반환을 전체 성공으로 바꾸지 않습니다. legacy SW fallback은 정확한 PCH 제공자·default root·수신 인수·선택 private Runtime 표까지 동기 연결했습니다. SmmBase legacy Communicate의 별도 deferred 입력 전달도 복원했지만 표준 typed 통신 제공자 증거로 합치지 않습니다.

Runtime 후크와 generic 조회 helper는 같은 주소 선택·명령 슬롯·zero-ready·오류 게시 생략 규약입니다. 같은 정상 SMM 순서라면 관련 CPU 접근 중첩을 좁힐 수 있지만 준비 0을 이전 효과 완료·EC 양쪽 작업 보존으로 승격하지 않습니다. 표준 통신 분기, EC 늦은 clear·인계, WMI 전체 교환·응답 귀속은 남습니다. live 포인터나 EC 전체 해시 미관측 하나를 제안 검토의 절대 조건으로 반복하지 않습니다. [조회 검토안](FIXED_MODE_READ_PROPOSAL.md)만 갱신, 앱·EXE·기존 ZIP 미변경·이번 빌드/단위 테스트 미실행, 실제 제어 Unsupported입니다. 원본·하드웨어 실행·변경이나 추가 실기·자료 제출은 없습니다. 아래는 이전 기록입니다.

## 최신 — 후속 Runtime 교체·EC 효과·고정 조회 조건 / 2026-11-07 한국 시간

[새 분석](RUNTIME_PROXY_AND_FIXED_READ_REVIEW.md)에서 정확한 PEI HOB 생산자→Runtime 구성, 후반 host adapter 선택, BDS 알림 생산자→NvramSmi의 실제 host 함수 교체를 연결했습니다. VA 전환은 현재 함수를 변환합니다. 주소 보정 adapter는 host에서도 쓰이므로 SMM 전용 해석을 정정합니다. 선택한 EC 후크 두 개는 같은 플래그 한 비트만 바꾸며 mailbox 입력·응답을 직접 쓰지 않습니다. 명령 게시 뒤 완료 대기가 없으므로 다른 정상 작업 보존·관련 indexed 접근 조건은 여전히 남습니다. 플랫폼의 조건부 SMI_LOCK 위치 writer는 현재 잠금·마스크 효과를 입증하지 않습니다.

[비실행 고정 조회 검토안](FIXED_MODE_READ_PROPOSAL.md)은 임시 CandidateProfile과 저장 모드 한 바이트 1회 범위를 정의합니다. 전체 live EC 해시는 제안 검토의 절대 전제가 아니지만, 현재 이미지 일치·최종 host 경로·통신의 정상 SMM domain·안전한 교환이 확정된 것은 아닙니다. 실제 backend·새 시험·새 승인·코드 변경 없이 Unsupported입니다. 문서·정적 기록만 변경, 이번 빌드·단위 테스트 미실행, 추가 자료 제출은 불필요합니다. 분석 중 잘못 전달한 PE 실행 시도 1건은 OS에서 차단됐고 원본 실행·권한 변경·재시도는 없습니다. 아래는 이전 기록입니다.

## 최신 — OS 변수 저장 경로와 EC 버전 메타데이터 / 2026-11-07 한국 시간

**새로 연결한 근거:** [후속 분석](RUNTIME_VARIABLE_AND_EC_IDENTITY_REVIEW.md)에서 host RuntimeServices의 SetVariable 게시→조건부 NV backend→새 변수 추가·선택 rebuild fallback→실제 flash receiver→기존 EC 후크를 연결했습니다. host/SMM 표와 RAM/flash/별도 SMM adapter는 구분했습니다. SBDXE와 SMIFlash의 외부 소비자도 실제 lookup·receiver·게시 표로 연결했습니다. guard의 SMI 제어 의도는 공개 Lynxpoint 헤더와 저장 삼성 base로 교차 확인했습니다.

**미확정:** 현재 Windows 호출·선택 구성·probe·실제 경합과 공통 EC 소유권은 미관측입니다. 저장 TXT17개에 명시적 EC 버전 필드는 없고, SMBiosBoard의 ECRev1/2 수신값→정확한 SMBIOS Type0 EC 필드 연결은 변수 생산자·갱신주기·live EC 조회를 입증하지 않습니다. 현재 이미지 동일성이나 호출 권한으로 승격하지 않습니다. 문서·정적 기록만 변경, 앱·EXE·기존 ZIP·예약 그대로이며 이번 빌드·단위 테스트는 미실행입니다. 제어 Unsupported, 추가 실기·동일 자료 제출·하드웨어 변경 없음. 아래는 이전 기록입니다.

## 최신 — 명령 게시자 문맥과 조건부 소유권 / 2026-11-07 한국 시간

**연결한 근거:** [명령 소유권 검토](EC_COMMAND_OWNERSHIP_REVIEW.md)에서 대체 EC poll을 같은 main scheduler로 연결하고, 포인터 writer의 capability와 실제 선택 전 개입을 구분했습니다. 펌웨어의 boot 초기화·알림과 SMM callback·forwarder를 분류했으며, 과거 서비스 WSABI도 기존 세 변형과 같은 Global 협력 잠금을 쓰는 것을 확인했습니다. 초기화 완료·관련 전역 상태 안정·정상 CPU context를 전제로 정상 SMM 세대의 하나의 root 실행을 설명하고, 새 GPI/SW 제공자를 실제 같은 root/child 호출로 연결했습니다.

**미완료:** 조건부 root 연결과 실제 장치 조건을 구분합니다. Runtime의 게시된 flash interface→전후 hook→EC 게시와 virtual-address 전환 보존을 연결했지만 현재 probe 선택·실제 OS 소비자·경합은 미확정입니다. busy 확인은 소유권 예약이 아니고, WMI 협력 잠금은 다른 native/직접 호출자까지 포함하지 않습니다. 현재 모델·입력·소유권 조건이 미확정인 상태에서 실제 호출 backend를 추가하지 않습니다. 최소 조회 설계는 검토 문서이며 실제 보호 상태 조회·충전 제어 성공이 아닙니다. 앱·기존 ZIP·예약 그대로, 이번 빌드·단위 테스트 미실행, 추가 실기·자료 재제출·하드웨어 변경 없음. 아래는 이전 기록입니다.

## 최신 — EC 생산자 진입과 실제 AP 작업 분류 / 2026-11-07 한국 시간

**새로 연결한 근거:** [후속 검토](EC_QUERY_INTERFERENCE_REVIEW.md)에서 첫 바이트 결과 작성자를 별도 high-command handler로, 다른 clear를 같은 main thread의 조건부 후처리로 연결했습니다. 선택 명령이 유지될 때의 알려진 ISR 분기와 중복 pending guard도 좁혔습니다. 실제 AP 소비자 네 모듈·여섯 호출·열 고정 작업은 CPU 복원·열 관리 등으로 분류했고, 일반 callback을 포함한 13함수의 직접 호출 사슬에는 AP pump가 없습니다. 입력 복사 완료 뒤에는 local 명령·메시지를 사용합니다.

**남은 조건:** 위 결과를 전역 작성자 부재나 실제 경합·조회 성공으로 확대하지 않습니다. 명령 판정/handler 선택 사이 공유 명령의 안정성, 입력 복사의 원자성·외부 규약·현재 이미지·IRQ binding은 미해결입니다. 응답 사후 거부는 앞선 부작용을 되돌리지 못하며 앱 timeout도 SMM 내부 중단 계약이 아닙니다. 문서·정적 기록만 변경했고 빌드/단위 테스트는 반복하지 않았습니다. 앱·기존 ZIP·단발 예약 그대로, 실제 제어 Unsupported이며 추가 실기·재제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 범용 읽기의 성립 조건과 SMM 동기화 / 2026-11-07 한국 시간

**확인한 근거:** [후속 검토](BOUNDED_READ_ROUTE_FEASIBILITY.md)에서 기존 정적 보호 모드 저장값 읽기 경로를 다시 평가했습니다. 요청별 내용 비교는 기존 mailbox와 다르고 다른 작성자가 기록하지 않는다는 전제에서 업로드 생략 stale 응답을 거부할 수 있습니다. 전용 OEM getter만 유일한 해법이라는 기준은 교정합니다. 저장된 SMM에는 CPU 도착·장벽·동기 handler 순회가 있으며 참여 보조 CPU의 작업 실행 경로도 있습니다.

**미검증:** 내용 표식은 EC 완료 번호가 아니며 다른 결과 생산자의 개입 배제는 미완료입니다. 모든 CPU 도착 대기에는 한도 소진 후 진행 분기가 있어 전체 작성자 배제로 확대하지 않습니다. 실제 race·현재 장치 적용·안전한 호출 계약·보호 상태 조회·충전 제어 성공은 입증하지 못했습니다. 문서·정적 기록만 변경했고 빌드·단위 테스트는 반복하지 않았습니다. 앱·기존 ZIP·예약은 그대로이며 Unsupported입니다. 추가 실행·동일 자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 새 Amor3 제조사 패키지와 구성 분류 / 2026-11-07 한국 시간

**확인된 사실:** [새 원본 확보](AMOR3_OEM_SOURCE_ACQUISITION.md)에서 Model940X3G의 WB 두 목록이 가리키는 SamsungSystemConfiguration 1.0.0.7 원본 3,771,257바이트를 정상 제조사 경로로 받았습니다. 10파일/비압축 7,585,067과 CRC·경로 검사가 일치합니다. WSABI는 과거 서비스 DLL SHA564b 기록과 같으며 Monitor loader·선택한 팬 query/setter, 서비스→Monitor·idle worker IPC를 정적으로 연결했습니다. 기존 W7 ChargingOnlyMode는 USB 태블릿, V21 추가 OSD는 알림 소비자로 분리했습니다. 개발 오프라인 검사 pin과 신규 3개 테스트를 추가해 전체 Python 88개 통과했습니다.

**미검증:** 배포 목록·관측 해시·언어 리소스의 BLE 설명은 현재 Win10 설치·모델별 지원·보호 조회 계약 증거가 아닙니다. 현재 원본의 모델 메타데이터·MSI OS 조건에서도 보호 허용 목록을 확보하지 못했습니다. 원본 실행·설치·하드웨어 호출 없이 실제 제어 Unsupported, C#/WPF·실행 파일·기존 ZIP·단발 예약은 그대로입니다. 추가 실기·동일 자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 외부·간접 계약 경계와 보류 조건 / 2026-11-07 한국 시간

**원본과 대조한 내용:** [후속 검토](EXTERNAL_INDIRECT_CONTRACT_BOUNDARIES.md)에서 34개 PE의 공통 192바이트 GUID 구간과 선택 참조를 분류했습니다. 파일 수는 등록자 수가 아니며 새 typed 등록자는 확인하지 못했습니다. 게시 과정의 선택 간접 호출은 기존 초기화로 연결했습니다. 별도 EC 페이지 반환 후보는 이전 값을 보관한 뒤 새 값을 쓰는 교환 경로여서 제외했습니다. 선택한 표 기반 초기화 계열도 직접 쓰기 대상이 다른 페이지임을 확인했습니다.

**미검증:** 요청·반환 포인터의 공급자, 다른 그룹의 새 보호 처리자, 동적 별칭·외부 소비자와 현재 장치 적용은 미해결입니다. 확인 범위의 계약 부족을 하드웨어 영구 미지원으로 해석하지 않습니다. 현재 자료로 실제 조회·제어 코드를 추가하지 않으며 새 모델별 등록·호출자·응답 근거가 다음 착수 조건입니다. 앱·기존 ZIP·예약은 그대로이고 실제 제어 Unsupported, 추가 실기·동일 자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — OEM 전력 소비자와 ACPI 대체 조회 연결 / 2026-11-07 한국 시간

**원본과 대조한 내용:** [후속 결과](FIXED_QUERY_CONSUMER_REVIEW.md)에서 현재 OEM의 명명된 전력 조회→고정 callback→배터리 전류·전압 캐시와 RTTI/vtable/import로 확인한 숫자 소비자를 연결했습니다. 저장된 ACPI의 ECON==0 byte/word 대체 조회도 공유 제공자와 등록 callback까지 연결했지만 상위 callback이 하위 오류를 무시합니다. word는 두 번의 byte 읽기이며 실패 시 0/재사용 byte가 섞일 수 있습니다. 다른 수신 word 캐시의 선택 대상은 기존 충전기 경로와 다르고 부품 의미는 미확정입니다.

**미검증:** 새 보호 상태 getter·현재 fallback 선택·실제 오류·최신 응답·현 장치 지원은 미확정입니다. 보호 기능 부재를 판정하지 않으며 목적이 식별된 전력 조회를 다시 보호 후보로 세지 않습니다. 문서·정적 기록만 갱신했고 실제 제어는 Unsupported입니다. 앱·기존 ZIP·기존 예약은 그대로이며 추가 실기·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 버스 응답 생산자와 정책 활동 스냅샷 / 2026-11-07 한국 시간

**원본과 대조한 내용:** [후속 결과](CHARGER_READBACK_AND_PROJECTION.md)에서 버스 상태 성공 시 수신 word를 복사하고 반환하는 별도 EC 후보를 분배표·bank stub과 연결했습니다. 정책 동작 비트→갱신 표시→활동 스냅샷→EC 페이지 읽기 경로도 확인했습니다. 보호 모드 저장값·소프트웨어 활동 기록·버스 수신값을 구분했습니다.

**미검증:** 활동 스냅샷은 보호 모드·임계값의 직접 미러나 충전기 쓰기 성공 증거가 아닙니다. 범용 버스 읽기의 고정 보호 조회·오류 보존 Windows 연결·현재 모델 안전성·응답 신선도는 미확정입니다. 제조사 조회의 scratch 값도 실제 옵션 read-back으로 쓰지 않습니다. 문서·정적 기록만 갱신했고 실제 제어는 Unsupported입니다. 앱·기존 ZIP·기존 예약은 그대로이며 추가 실기·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 오류 보존 조회와 상태 생산자 경계 / 2026-11-07 한국 시간

**원본과 대조한 내용:** [후속 결과](EC_FRESHNESS_AND_ERROR_PATHS.md)에서 두 대기 오류를 보존하는 helper와 등록 callback 네 개를 연결했습니다. 이는 다른 상태 페이지의 고정 조회이며 한 비트는 생산 코드·ACPI ACEX에 맞는 AC 전원 상태입니다. 일반 중계는 새 게시 실패 뒤 이전 작업이 끝나면 기존 응답을 정상으로 복사할 수 있는 조건부 분기가 있습니다. EC 바이트 읽기는 결과 한 바이트만 갱신하며 선택 본문에 요청 순번이 없습니다. 현재 WSABI 세 변형의 같은 Global mutex는 협력 호출자 사이 일반 교환을 감쌉니다.

**미검증:** 위 사건의 실제 발생·현재 이미지·보호 모드 상태 페이지 반영·독립적이고 신선한 read-back은 미확정입니다. 오류 보존 경로와 모드 저장소를 동일시하지 않으며 협력 잠금을 시스템 전체 배제·펌웨어 오류 복구로 해석하지 않습니다. 문서·정적 기록만 갱신했고 앱·기존 ZIP·기존 예약은 그대로이며 실제 제어는 Unsupported입니다. 추가 실기·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 보호 모드 저장값 조회 후보와 WMI 연결 / 2026-11-07 한국 시간

**원본과 대조한 내용:** [후속 결과](EC_READBACK_AND_WINDOWS_BRIDGE.md)에서 WMI→공유 버퍼→등록 callback의 소스 사슬을 연결했습니다. 261바이트 공유 영역이 20바이트 입력 복사를 포함하며 선택한 입력·응답 10바이트는 기존 WMI 범위 안에 있습니다. 현재 삼성 ModuleSABI의 LED·키보드 호출자도 같은 형식을 사용합니다. 조건부 EC 해석에서는 setter echo와 별도로 저장 바이트를 읽는 범용 경로와 특정 초기화 분기의 모드·임계값 지우기를 확인했습니다.

**미검증:** 범용 읽기는 전용 보호 조회 API나 실제 충전기 read-back이 아닙니다. 현재 이미지·등록·권한·신선한 응답·전체 교환 직렬화·재부팅 지속성은 미확정입니다. 원본·하드웨어 호출 없이 문서와 정적 기록만 갱신하며 실제 제어는 Unsupported입니다. 앱·기존 ZIP·단발 예약은 그대로이고 추가 실기·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 조건부 EC 충전 보호 흐름의 직접 근거 / 2026-11-07 한국 시간

**원본과 대조한 내용:** [새 결과](EC_CHARGE_PROTECTION_CANDIDATE.md)는 고정 P05 CAP/EC 영역의 명령어 가정을 명시한 정적 해석입니다. 모드80/75 설정, 같은SBS0D 잔량의생산·소비,상한이상억제/하한이하조건부재개,충전기옵션·전류·전압요청을연결했습니다. 공개레지스터정의와word바이트순서도대조했습니다. 버전·USBwake 역할과bank전환stub이해석모델을지지합니다.

**미검증:** 제조사에의한chip/ISA/bank확정·현재실기이미지·Windows전달계약·실제설정재조회·전기적충전중단/재개·지속성은미확정입니다. 원본은버스쓰기status를검사하지않으므로소프트웨어last-action flags는적용성공이아닙니다. generic중계·ACK·echo로허가/상태를승격하지않고Unsupported를유지합니다. 앱·테스트·기존ZIP미변경,이번빌드·단위테스트미실행,실기/OEM/예약/드라이버·서비스/보안·펌웨어변경없음. 아래는이전기록입니다.

## 최신 — EC 업데이트 영역의 용도 연결과 제어 구현의 한계 / 2026-11-07 한국 시간

**확인된 사실:** [새 결과](EC_UPDATE_REGION_RESULT.md)에서실제AFU EC옵션의type3소비와SMIFlash/1의16B header/1280개9B record생산을연결했습니다. type3의31개4KiB페이지는별도ROM-layout의124KiB영역과일치하고96KiB대상을포함합니다. AMITSE의같은영역복사·현재6+3버전비교·조건부갱신도확인했습니다. 이소스인터페이스의EC업데이트분류근거이며실제충전제어성공은아닙니다.

**미검증:** 현재설치이미지·실행선택·컨트롤러종류·ISA/bank/codebase·충전보호처리자·응답·신뢰할재조회는미확정입니다. 버퍼변환/쓰기포함갱신코드를조회로사용하지않습니다. 현재자료와안전조건에서실제제어구현은막혀있고Unsupported를유지합니다. 제품·테스트·기존ZIP미변경,이번빌드·단위테스트미실행이며추가실기·자료제출·OEM/예약·하드웨어변경을요청하지않습니다. 아래는이전기록입니다.

## 최신 — 보유 native 드라이버와 DLL의 연결 / 2026-11-07 한국 시간

**확인된 사실:** [native 드라이버 검토](NATIVE_SABI_DRIVER_REVIEW.md)에서 기존 보유 x64 Sabi.sys 본문을 새로 분석했습니다. DLL과 같은 IOCTL의 입력26/응답16 전달을 확인했지만 완료 NTSTATUS는 ACK·배터리 상태와 별개입니다. 호출자가 포트·selector·공유 주소를 공급하며 현재 P05의 실제 결합은 확인하지 못했습니다. 기존 명령 후보6개도 inline object로 정정했지만 배터리 계약은 없습니다.

**미검증:** 현 설치 드라이버·Win10 선택·모델별 보호 처리자·응답 의미·신뢰할 재조회는 미확정입니다. 설치 선언·원본 존재·일반 전송을 실제 충전 지원으로 승격하지 않습니다. 제품 코드·기존 ZIP은 유지하며 빌드·단위 테스트는 이번에 반복하지 않았습니다. 추가 실기·재제출·OEM/예약 접근·드라이버/서비스/보안 변경 없이 Unsupported입니다. 아래는 이전 기록입니다.

## 최신 — 소프트웨어 취소 처리와 raw 영역의 한정 비교 / 2026-11-07 한국 시간

**확인된 사실:** [전송 취소 보강](WMI_CANCELLATION_BOUNDARY_UPDATE.md)은 순수 조정 코드의 callback 차단 결함 수정입니다. 실제 장치 경로·단발 정책·예약·제어 권한은 변경하지 않습니다. C#437/Python85 통과와 전체 빌드 경고·오류0은 이번 새 검증 결과입니다. 별도로 P04/P05 미분류 raw 영역 262,144바이트의 차이 10바이트를 확인했으며 버전·날짜와 헤더 차이입니다.

**미검증:** 그 영역의 명시적 포맷·MICOM/EC/CPU 정체성·배터리 명령과의 연결은 미확정입니다. 소프트웨어 timeout 수정이나 바이트 관계를 실제 보호 설정 접근으로 보고하지 않습니다. 현재 모델의 handler·응답·신뢰할 read-back이 없어 Unsupported를 유지하며 추가 실행·자료 재제출·하드웨어 변경을 요청하지 않습니다. 아래는 이전 기록입니다.

## 최신 — 역사적 P04 원본과 현재 분석 대상의 차이 / 2026-11-06

**확인된 사실:** [P04/P05 비교](P04_P05_FIRMWARE_COMPARISON.md)에서 실제 제조사 940X3G W7 목록의 P04 패키지를 새로 확보했습니다. BIN과 wrapper의 CAP는 동일 payload입니다. 선택된 SABI core의 실행 코드·데이터와 초기화 표는 같지만 전체 이미지는 unwind 등에서 다릅니다. 변경된 Wireless/SetupWin의 P04 등록 경로를 별도로 복원했으며 새 65/66 처리자는 찾지 못했습니다. P04 HII도 보호 문구와 표준 설정 항목 사이의 연결을 제공하지 못했습니다.

**미검증:** 현재 장치의 설치 이미지·동적 등록·화면 표시·보호 설정 응답 및 신뢰할 read-back은 미확정입니다. 과거 공식 출처·문구·코드 일치를 현재 Windows 10 지원이나 영구 미지원으로 확대하지 않습니다. 이번에는 프로그램·테스트·EXE·ZIP을 변경하지 않았고 빌드·단위 테스트를 반복하지 않았습니다. 추가 실기 시험·재제출·OEM 호출·BIOS 변경 없이 Unsupported입니다. 아래는 이전 기록입니다.

## 최신 — 남은 직접 조회 후보의 효과와 한계 / 2026-11-06

**확인된 사실:** [새 검토](REMAINING_QUERY_PATHS_REVIEW.md)에서직접callee8개의버퍼효과와구성테이블producer,기존5모듈의unregister후보,레거시외부selector80/81/82를대조했습니다. 공개SSDT4개의54MethodOp쌍도캡슐과같지만CPU패키지/리소스데이터차이는남습니다. 공개ECMD caller도확인했으며외부객체에쓰기후호출하는경로라읽기전용보호조회로채택할근거가없습니다.

**미검증:** 새로운65/66처리자·보호상태read-back은없습니다. 삭제API능력은실제65삭제/FF원인증거가아니며,다른runtime producer·보존된별칭·opaque callback효과·현이미지정체성은미해결입니다. 이결과는현재자료로새실행경로를추가할근거가없다는판단이며하드웨어영구미지원증명은아닙니다. code/EXE/ZIP유지,이번빌드·단위테스트미실행,추가시험·재제출없이Unsupported입니다. 아래는이전기록입니다.

## 최신 — 조회 테이블의 범위와 실패 응답 / 2026-11-06

**확인된 사실:** [새 분석·보강](FIRMWARE_QUERY_BOUNDARY_UPDATE.md)에서 main-group256슬롯과 raw sub WORD lookup·공개삭제·공통실패 정상0의 관계를 대조했습니다. 이 근거로 현재 순수 encoder의 준비 범위를0..255로 좁혔고, raw frame 우회/가짜 의존성 미호출 회귀를 추가했습니다. 일반 UInt16 ABI나 명령 안전성을 새로 확정한 것은 아닙니다. 캡슐의16 ACPI 템플릿에서 공개 DSDT와9개 원시 메서드 패킷이 같은 것도 확인했습니다.

**미검증:** 현재 설치 이미지·도달 가능성·Windows HRESULT 매핑·모든 별칭/동적 경로는 미확정입니다. 캡슐 템플릿과 현재 장치 namespace도 동일시하지 않습니다. 새65/66 callback이나 보호 설정 read-back은 없어 실제 제어는 Unsupported입니다. 추가 OEM/장치 시험 없이 개발 소스만 제공하며 기존 실행 프로그램은 유지합니다. 아래는 이전 기록입니다.

## 최신 — 실제 배터리 접근을 위한 간접 경로 감사 / 2026-11-06

**같은 계열 원본 추가:** 공식 A1/W7의2.2.0.21/2.0.0.78을 받아 같은940X3G 계열의 과거 배터리 caller를 직접 확인했습니다. W7의SUS1.0.5.7은 같은 표시 버전이라도 비교 원본과 SHA/코드가 달라 새RVA로검토했습니다. 0B/bit3·AL gate→65·소프트웨어상태분류와 setter정상1·Cmd메뉴캐시는 현재 보호 상태의 검증이 아닙니다. A1의전송DLL은 기존과같고 변경된BatteryMgr/Power명령도 한정 대조했지만 새보호경로는 확보하지못했습니다. 배포출처와실기Win10/P05지원은별도입니다.

**확인된 사실:** [후속 감사](BATTERY_PROTECTION_ACCESS_FOLLOWUP.md)에서 provider의 SABI 등록 호출21곳/descriptor 후보56개를 복원하고 별도 d32 byte-selector 테이블을 분리했습니다. 기존 소비자4개의 lookup출력11개·다른6모듈8개 offset 후보와 HII의 동적 GUID consumer도 대조했습니다. flags 위치는 interface+30..34=parent+40..44이며 parent+30 dispatch slot과 다릅니다.

**미검증:** 위 후보에65/66은 없지만 동적·외부·opaque 경계가 남습니다. 새 bit3 writer·배터리 설정 필드·현재 보호 상태 read-back은 확보하지 못했습니다. 정적 목록·다른 receiver·import 이름 미관측을 현재 장치의 기능 부재로 확정하지 않습니다. 앱/EXE/ZIP 유지, 이번 빌드·단위 테스트 미실행, 새 실기/자료 요청 없이 Unsupported입니다. 아래는 이전 기록입니다.

## 최신 — 후속 INI 처리와 실제 설정 재조회의 구분 / 2026-11-06

**확인된 사실:** [새 대조 결과](CONTROL_CONTRACT_CLOSURE_REVIEW.md)에서 현재 SUS 1.0.6.1의 x86/x64 후속 helper를 파일 스트림 타입·열기 모드까지 추적했습니다. 팝업용 `conf.ini` 처리이며 setter 반환1·wrapper 0x63은 검증된 장치 read-back에 조건부가 아닙니다. 저장 P05ACJ의7 FV·466 FFS·390 표준 압축 섹션을 검사해 기존 볼륨 밖232파일/46개 PE를 추가 확인했습니다. USB bit4/67/68의 양측 관계와 Model940X3G 배포 매뉴얼의 전원/보정 문맥도 대조했습니다.

**미검증:** 새 배터리65/66 처리자·현재 bit3 writer·신뢰할 보호 설정 응답은 확보하지 못했습니다. 표준 섹션의 전수 구조 검사는 계산/간접 등록·raw 구간·설치된 런타임 동일성을 닫지 않습니다. 매뉴얼 미관측과 USB 대응은 배터리 기능 부재/지원의 증명이 아닙니다. 앱/EXE/ZIP 유지, 이번 빌드·단위 테스트 미실행, 추가 시험·업로드 없이 Unsupported입니다. 아래는 이전 기록입니다.

## 최신 — 현재 계열 배포 원본과 실제 제어의 구분 / 2026-11-06

**확인된 사실:** [새 원본 검토](CURRENT_MODEL_OEM_EVIDENCE_UPDATE.md)에서Model940X3G/WB목록의Settings2.2.0.18을실제로받고x64Sabi3가기존분석SHA와같음을확인했습니다. 새ModuleBatteryMgr/Toast는전원계획·알림관련범위이며ModuleSABI의직접호출과등록명령범위를따로분석했습니다. 확인된근거를프로그램오프라인설명에반영하고최종435/85테스트·경고오류0빌드로검증했습니다.

**미검증:** 한DLL의일치는실제설치전체/실행선택/Win10충전지원이아닙니다. 범위한정미관측도전체기능부재가아니며현재flag·65/66처리·설정read-back은미확정입니다. 기존P05genericsetter는다른bit3값을받을수있어초기7F불변을입증하지못했습니다. Unsupported와모든안전경계를유지하고추가시험·재제출을요청하지않습니다. 아래는이전기록입니다.

## 최신 — OEM 메뉴 생성과 실제 상태의 분리 / 2026-11-06

**확인된 사실:** [재개한 정적 대조](OEM_UI_SUPPORT_CONTRACT_REVIEW.md)에서 SUS조회분류→Cmd메뉴지원캐시→UI의SUB_PM_BLE/PM_BLE→child/헤더생성을연결했습니다. 로컬UI속성과상태표시경로도별도입니다. 0B뒤tail을호출자가덮지않는것은확인했지만비영/과거와다른payload를확정하지않습니다. setter정상반환1은read-back비교에조건부가아니고후속helper전체는미완료입니다.

**미검증:** 비교원본은현재ATIV의OEM실행/지원/상한증거가아닙니다. PROGRAM_PRIVILIGE 생성자·실제Win10DLL선택·현재0B응답·65/66처리자와신뢰가능한read-back은미확정입니다. 초기7F/메뉴부재/화면변경으로대체하지않습니다. 코드/EXE/기존ZIP유지,이번빌드·테스트미실행,추가시험·업로드없이Unsupported입니다. 아래는이전기록입니다.

## 최신 — 비교 Settings ZIP명과 실제 바이트의 구분 / 2026-11-06

**확인된 사실:** [실제 BOM 분석](SETTINGS_BOM_PACKAGE_UPDATE.md)에서930X5J의 두 목록을 받아 Easy Settings for Win7 2.0.0.89 → BASW-83876A21.ZIP을 확인했습니다. 항목40/45·원본 위치25/30·동일 비교 항목1/1입니다. FileVer/VerifyAttribute는 버전 검사이며 원본 해시가 아닙니다. 실제 ZIP 링크는 삼성 다운로드센터로302 이동하며 현재 CONNECT403으로 바이트는 미확보입니다.

**미검증:** 내부Win8 Settings·배터리 caller·940X3G/930X3G/P05ACJ 적용성·명령/응답 계약은 아직 미확정입니다. Header TestYes는 실기 시험 결과가 아니고 두 동일 항목은 독립 바이너리 검증이 아닙니다. 새 오프라인 BOM 구조 검사가 이 한계를 바꾸지 않습니다. 추가 시험·업로드 없이 실제 제어Unsupported를 유지합니다. 아래는 이전 기록입니다.

## 최신 — 공개 모델 조회와 배터리 지원의 분리 / 2026-11-06

**확인된 사실:** [새 카탈로그 조사](SAMSUNG_UPDATE_CATALOG_REVIEW.md)에서 공개 모델명 조회로 얻은 ModelCode만 사용했습니다. 현재 계열의 모델 목록은116개이며 비교 NP930X5J-S02US의 W7 카탈로그는 SUCC/HDM.ITEM2입니다. HTTP200이어도 현재 계열의 OS/W8 요청은 서비스404입니다. 오프라인 검사기로 HTTP·서비스 결과·빈 목록·null을 구분하며 서버 원문은 배포하지 않습니다.

**미검증:** 두 항목은 비교 모델의 BOM XML 위치로 Settings2.0.0.89 바이트·적용 모델·명령 계약은 아직 미확보입니다. 실제 장치 시리얼이나 하드웨어 상태는 읽지 않았습니다. 공개 목록/오류코드로 현재 ATIV의 배터리 지원·보호 상태·과거FF·충전 가능성을 판정하지 않습니다. 실제 제어Unsupported, 추가 노트북 시험·업로드 불필요. 아래는 이전 기록입니다.

## 최신 — 원문 UI 분기와 비교 패키지의 적용 한계 / 2026-11-06

**확인된 사실:** [새 원문 분석](SETTINGS_VERSION_SOURCE_REVIEW.md)에서커뮤니티의 NP940X3G/Settings2.1.0.20 배포기록을 읽었습니다. #39는구형NP700Z3A의 UI탭/업데이트분기, #62/#63의2.0.0.89 시험은구형Series7의Win8.x용Settings에관한것이며패키지위치는다른NP930X5J-S02US Win7목록입니다. 원문2페이지의길이/해시와인용/추측의범위를검토했습니다.

**미검증:** NP940X3K·NP930X5J는현재모델과다르고, Win7외부패키지와Win8내부모듈도별도입니다. 현재ATIV/P05ACJ/Windows10의지원·0x65/66·FF·충전상한은입증하지못했습니다. 탭부재를펌웨어부재로, 구버전시험을현재모델호환으로해석하지않습니다. 원본비교파일은미확보이며원문삼성인입호스트를추가한초안의게시가필요합니다. 실제제어Unsupported, 추가노트북시험/업로드불필요입니다. 아래는이전기록입니다.

## 최신 — HII 참조의 검증 범위와 시험 경로 제외 / 2026-11-06

**확인된 사실:** [새 분석](P05ACJ_HII_REFERENCE_UPDATE.md)에서 기존 Setup HII 리소스를11종 표준 statement 헤더까지 검사했습니다. USB 충전 CheckBox와 보정 Ref는 각1회 참조되고 배터리 수명 연장 prompt/help는 지원 범위에서0회입니다. 별도 OFBD의 배터리 신뢰성 시험 flag 분기를 포트 IN/OUT helper까지 정적으로 연결했습니다. 실행·하드웨어 접근은 하지 않았습니다.

**미검증:** vendor GUID34개 내부·동적/다른리소스·메뉴표시·하드웨어 기능 부재는 미확정이며 문자열/참조 결과를 배터리 명령 계약으로 취급하지 않습니다. 시험/보정/USB 충전은 상한의 대체 경로가 아닙니다. 현재 모델 caller/처리자/응답 연결 근거는 여전히 없고 제어는 Unsupported입니다. 원본 재제출·반복/OEM 시험은 불필요합니다. 아래는 이전 기록입니다.

## 최신 — caller 선택/응답 대조와 코드 해석 정정

**확인된 사실:** [새 대조](WINDOWS_CALLER_CONTRACT_UPDATE.md)는 구형OEM의 OS 조건·설치/INI gate·0B 호환성 분기와 P05ACJ0B callback3908/초기flag의 조건부 관계를 연결했습니다. flag getter는 공유상태 복사이며 현재 장치 응답을 읽은 것이 아닙니다. 0B gate보다65조회/조건부66쓰기가 먼저이며 구형EXE는 관리자 매니페스트여서 진단용 실행 근거가 없습니다. 제3자 소스의 USB/무선/키보드 일부 명령은 등록 문맥과 맞지만 배터리 계약까지 확장하지 않습니다.

**정정/미검증:** 기존 native11 디코더의0/1/FF를 보호/지원으로 부른 해석을 제거하고 opaque 표식만 분리했습니다. 보호/상한은null·권한false, 실제앱/어댑터 참조는 없었습니다. 현재 모델 caller·65/66 처리자·FF원인·실제 상한은 미확정입니다. 초기0B flag를 실제65응답에 적용하거나 현재 flag/지원부재로 확정하지 않습니다. 추가 시험/업로드 없이 실제 제어Unsupported를 유지합니다. 아래는 이전 단계 기록입니다.

## 최신 — 외부 등록 지도와 위험한 대체 경로 제외

**확인된 사실:** [외부 등록 추적](P05ACJ_EXTERNAL_REGISTRATION_REVIEW.md)에서 GUID 포함34파일 중 직접 참조6개(provider/bridge/등록자4개), 실제 외부 등록 경로10개를 복구했습니다. 해당 범위는 Wireless12/13/69/6A·SwSmi78/67/68·AlwaysOn6D/6E·SetupWin7C입니다. 67/68은 USB 초기화 문맥, 6D/6E는 SecSleepType/설정 문맥이며7C는 협상/구조 발견과 별도 UEFI 변수 읽기/쓰기 경로로 연결됩니다. 유사80/81 입력이나 USB 충전 캡션은 배터리 상한 계약이 아닙니다.

**미검증:** 28파일의 직접 참조 미관측을 미사용·기능 부재로 보지 않으며 동적/다른 볼륨 등록은 미폐쇄입니다. 65/66 등록·HII 배터리 토큰 연결·현재FF 원인·실제 보호 상태는 미확정입니다. 관측 원본 pin은 동일 바이트 대조입니다. 서명 수학검증/이미지 digest 일치는 통과했지만 신뢰 체인·타임스탬프·폐기·Windows 정책은 미완료여서 전체 진위 검증을 주장하지 않습니다. 기존 실험/프로그램을 보존하며 추가 OEM 시험·자료 재제출 없이 Windows 호출자 기록과 등록 지도를 대조합니다. 실제 제어는 Unsupported입니다. 아래는 이전 단계 기록입니다.

## 최신 — P05ACJ 공통 실패 응답과 구형 실제 호출자

**확인된 사실:** [새 정적 분석](FIRMWARE_REPLY_EVIDENCE_UPDATE.md)에 두 실제 원본의 길이/해시와 내부 모듈을 기록했습니다. SecSabiDispatch는 콜백 부재/null/EFI 오류를 공통 FF+19zero 응답으로 만들며 ACK AA도 설정합니다. 현재 순수 코드에서는 데이터16바이트 접두부만 비교합니다. 구형 BLE는65입력80+10zero와66설정바이트를 쓰지만 API오류를 무시하고1 이외를100% UI로 처리합니다.

**미검증:** 과거 실기에는 첫FF만 있어 전체패턴과 원인이 미확정이며 같은모듈/현재 장치 실행도 입증하지 않았습니다. 패턴일치는 비배타적이고 다른패턴도 성공/보호상태 판정이 아닙니다. HII80/100문자열은 표준question연결을 관측하지 못해 실제사용가능성을 뜻하지 않습니다. 다음은 확보이미지의등록/게이트/처리자를 정적으로 추적합니다. 실제제어는Unsupported, 추가OEM시험·원본재제출은 없습니다. 아래는 이전 단계 기록입니다.

## 명령 원본 후보의 고정 출처와 미확보 경계

**확인된 사실:** [새 원본 위치](COMMAND_SOURCE_ARTIFACTS_AND_ACCESS.md)는 ACJ→P05ACJ 정확한 업데이트 파일명과 NP-RV520용 구형BLE1.0.0.11 LFS 객체를 명시합니다. 실제 BLE 다운로드는133바이트 포인터이고 EXE/ZIP 원본은 확보하지 못했습니다. 정상 요청은 현재 네트워크 정책으로 차단됐으며 필요한2개 호스트를 초안에만 추가했습니다.

**미검증과 다음 조건:** 현재 장치용 펌웨어·OEM 서명/진위·배터리 명령·FF 의미는 미확정입니다. 다른모델BLE를 그대로사용하거나 목록해시를 펌웨어해시로 취급하지 않습니다. 접근조건 적용후 인입검증·실행없는 정적분석부터 진행합니다. 앱·실험·제어정책은 유지하며 실제제어는Unsupported입니다. 아래는 이전 조사입니다.

## 같은 모델 계열·P05ACJ의 공개 정적 자료

**확인된 사실:** [새 공개 출처](P05ACJ_BATTERY_COMMAND_EVIDENCE.md)는 같은 수집 실행의 metadata에940X3G/930X3G·NP940X3G-K03FR·P05ACJ.128.140819.dg를 명시합니다. 별도 Linux 장치의 DSDT1/SSDT4개를 정적으로 검증했습니다. WMI 중계의 선행 literal은Zero이고 WQ본문은 상수0x10을 반환합니다. 표준 배터리 정보/상태·알림 임계값은 별도 helper 경로입니다. _BTP를 충전 상한으로 재사용하지 않습니다.

**미검증과 다음 조건:** 공개 자료가 현재 사용자 장치와 같은 바이트/런타임을 뜻하지 않습니다. 미해소 외부 참조·동적 로드가 있고0x65/FF/실제 보호 상태는 미확정입니다. 현재 모델의 명령 계약을 입증할 OEM 배터리 호출자 또는 관련 펌웨어 처리 근거가 필요합니다. 포트/EC/SMM 경로를 실행하거나 다른SAM0428 명령을 대입하지 않습니다. 앱·배포 ZIP·Unsupported 정책은 유지합니다. 아래는 이전 조사입니다.

## v7 실기에서 관측한 Literal 대상과 직접 구문 배치

**확인된 사실:** Literal Store1회는 Integer 원천이며 SystemMemory·21바이트 Field입니다. 입력/반환과 같은 Field·Region, 보조 Store와 다른 Field·Region 선언을 참조합니다. SingleDirectList의 소스 배치는 Literal Store → Arg2 Store → 보조 호출 → Return입니다. 정수 값·실제 실행·형 변환·덮어쓰기·물리 영역 분리·FF 원인을 확인한 결과는 아닙니다.

**미검증과 다음 계획:** 중계 구조가 구체화돼도 모델별 Windows 배터리 명령/응답 계약은 남아 있습니다. [후속 계획](ACPI_V7_RESULT_AND_NEXT_PLAN.md)은 기존 wsabi/Sabi3의 전송 규약을 구분하고, 배터리 호출자가 명령·입력·응답 의미를 정하는 적합한 정적 출처를 추적하는 것입니다. 추가 wrapper 세분화·진단 반복·추가 OEM 호출은 우선하지 않습니다. FF 의미와 실제 제어는 미확정·Unsupported입니다. 아래는 이전 조사입니다.

## Literal Store 대상과 직접 구문 배치 v7 — 2026-11-05 한국 시간

**확인된 사실:** v6 실기에서 후보 입력 저장/반환 Field는 SystemMemory·고정21바이트 선언 폭 일치였고, 보조 Store Field는 SystemIo의 다른 Region 선언을 참조했습니다. 후보 Store2회 중1회가 Literal 원천이지만 그 대상·직접 구문 종류·위치는 당시 출력에 없었습니다. Literal을 FF 초기화나 명령 selector로 단정하지 않습니다.

**새 구현:** [v7](ACPI_STORE_ROLE_UPDATE.md)는 Literal Store의 구문 종류와 대상 Field의 공간·폭 범주, 입력/반환/보조 Store의 Field·Region 관측 정의 관계를 분류합니다. 같은 후보 직접 구문 목록에 있는 Store·보조 호출·Return의 앞뒤 관계만 제한적으로 보고합니다. 분기·반복·중첩·복수 후보는 보수적으로 남기고 실제 값·실행 순서·초기화·I/O 트리거·물리 영역 동일성을 계산하지 않습니다.

**아직 검증되지 않은 항목:** v7의 실제 노트북 출력, FF 생성 위치와 현재 모델의 Windows 배터리 명령 계약입니다. 기존 수집/API/상한을 유지하고 새 구문 기록 한계는 새 보고서에만 적용합니다. 원문 값·주소·이름·폭·구문 위치는 내보내지 않으며 실제 영역 접근·OEM/AML/DLL 실행·예약 접근을 추가하지 않습니다. 실제 제어는 Unsupported입니다. 아래는 이전 조사 당시의 기록입니다.

## v6 실기에서 구분한 프레임 Field와 보조 Store 선언

**확인된 사실:** 후보 Arg2 저장/직접 반환 Field는 SystemMemory·Matches21ByteFrame이며 같은 관측 Field 정의 참조 관계를 유지했습니다. 보조 Store Field는 SystemIo이고 두 역할의 Region 비교는 DifferentObservedDefinitions입니다. 후보 Field Store2회 중1회는 직접 Arg2, 나머지1회는 Literal 원천입니다. 서로 다른 Region 선언은 실제 물리 주소의 분리나 SMI 실행을 뜻하지 않습니다.

**미검증과 다음 계획:** 추가 literal Store의 대상·직접 literal 종류·구문 위치는 현재 요약에 없습니다. FF 초기화나 명령 selector로 단정하지 않습니다. [후속 계획](ACPI_V6_RESULT_AND_NEXT_PLAN.md)은 그 역할을 관측 선언과 제한된 구문 관계로 확인하며 실제 값/분기 평가·영역 접근·OEM 실행은 하지 않습니다. 모델별 명령 계약과 실제 FF 의미는 미확정이고 제어는 Unsupported입니다. 아래는 이전 조사입니다.

## Field 선언 폭·입력 역할·Region 관계 v6 — 2026-11-05 한국 시간

**확인된 사실:** v5 실기에서 후보 Field 참조3/3회·보조 Mutex/Field 참조3/3회, 후보 Store(Arg2)/Return의 동일 관측 Field 정의와 보조 SystemIo Field Store 구문을 확인했습니다. 후보 Field 공간·폭과 보조와의 Region 선언 관계는 당시 요약에 없었습니다. 이를 실제 값 전달·I/O·SMI 실행으로 해석하지 않습니다.

**새 구현:** [v6](ACPI_FIELD_CHANNEL_UPDATE.md)는 후보 입력 저장/직접 반환 Field의 공간·고정21바이트 대비 폭 범주, 후보 Store의 즉시 원천 종류, 보조 Store와 같은 관측 Region 정의인지 비교합니다. 고유 선언 후보로 분류하며 복수·혼합·미분류를 하나의 일치로 확정하지 않습니다. 원시 폭·주소·오프셋·길이·이름은 보고하지 않고 물리 영역이나 실제 Field 값을 접근하지 않습니다.

**아직 검증되지 않은 항목:** v6의 실제 노트북 출력과 모델별 Windows 배터리 명령/FF 계약입니다. 선언 폭 일치와 Region 선언 동일성은 정확한 배치·실행·동일 물리 메모리·프로토콜·충전 지원을 증명하지 않습니다. 별도 OEM/AML/DLL 실행·새 명령·예약 초기화 없이 진행하며 실제 제어는 Unsupported입니다. 아래는 이전 조사 당시의 기록입니다.

## 이전 개발 기록

## v5 실기에서 관측한 Field 전달 구문

**확인된 사실:** v5 출력에서 후보와 보조의 이름 참조 각 3/3회가 분류됐습니다. 후보 저장/반환 대상은 같은 관측 Field 정의를 참조하며 보조 Store 대상 Field의 선언 공간은 SystemIo입니다. 고유 객체 개수나 실제 I/O·SMI·데이터 변경을 관측한 결과는 아닙니다.

**미검증과 다음 계획:** 후보 Field의 주소 공간·폭과 두 본문의 Region 선언 관계는 현재 요약에 없습니다. [다음 계획](ACPI_V5_RESULT_AND_NEXT_PLAN.md)은 이를 고정된 정적 분류로 확인하고 직접 Store의 입력 역할을 구분하는 것입니다. 같은 Region 선언도 같은 물리 영역/런타임 객체·실행 효과를 보장하지 않습니다. FF의 의미와 모델별 배터리 명령 계약은 별도 근거가 필요하며 실제 제어는 Unsupported입니다. 아래는 이전 조사입니다.

## 관측 이름 정의와 정적 참조 관계

**확인된 사실:** v4는 후보와 보조 본문을 해석했으나 이름 참조 종류와 Store/Return 대상 관계는 보고하지 않았습니다. 미확정 참조 6회는 고유 객체 수나 실제 데이터 전달 실패를 뜻하지 않습니다. 공유 버퍼 방식은 아직 가설입니다.

**새 구현과 미검증:** [v5](ACPI_OBJECT_REFERENCE_UPDATE.md)는 같은 테이블에서 관측한 선언 종류와 동일 정의 참조 구문을 분류합니다. Region은 정적 주소 공간 종류만 표시하며 실제 영역을 읽거나 쓰지 않습니다. 선언 종류·구문 관계를 실제 runtime 객체·입출력 동일성·값/별칭/분기·펌웨어 효과로 확대하지 않습니다. FF 의미·충전 제어와 새 v5 실기 결과는 미확정입니다. 아래는 이전 조사입니다.

## 보조 본문 미지원의 관측과 표준 구문 확장

**확인된 사실:** v3에서 후보 본문의 알려진 호출 표현식 1개·보조 정의 1개를 관측했으나 보조 본문은 해석 불가였습니다. root의 직접 Arg2 인수 0·UnresolvedName 반환은 입력 미전달·잘못된 응답 판정이 아닙니다. 기존 출력에는 정확한 중단 원인이 없습니다.

**구현과 미검증:** [v4](ACPI_HELPER_SYNTAX_UPDATE.md)는 고정 ACPICA 문법에 맞춘 확장 구문의 정적 소비와 고정 실패 원인, 해석 완료한 보조 본문 범위만의 반환 구문을 추가합니다. 어떤 동기화/대기/Fatal도 실행하지 않으며 현재 노트북에서 특정 확장 opcode가 사용됐다고 단정하지 않습니다. 새 실기 결과와 FF의 실제 의미는 미확정이고 실제 제어는 Unsupported입니다. 아래는 이전 조사입니다.

## 현재 DSDT 정의 관측과 보조 연결 구문

**확인된 사실:** v2 사용자 요약에서 DSDT 직접 본문 읽기·알려진 설명자/대응 메서드 각 1개·인수 3개·본문 Parsed를 관측했습니다. 전체 namespace는 Partial이고 직접 ID1/길이21 비교·상수 FF 반환은 지원 범위에서 미관측입니다. 기존 판독기는 호출된 보조 정의 본문을 따라 읽지 않았으므로 보조 본문에도 해당 처리가 없다고 해석할 수 없습니다.

**새 정적 구현과 미검증:** [v3](ACPI_METHOD_FLOW_UPDATE.md)는 반환 형태·명명 호출·직접 Arg2 인수와 같은 테이블의 보조 정의를 제한적으로 요약합니다. 구문 존재만 다루며 메서드 실행·값/별칭/조건 계산·WMI 원본 입력과 보조 인수 매핑은 하지 않습니다. 실제 FF 발생 위치나 배터리 의미는 아직 미확정이고 새 분석의 실기도 미관측입니다. 수집 범위를 넓히거나 OEM 실험을 반복하지 않으며 실제 제어는 Unsupported입니다. 아래는 이전 조사입니다.

## DSDT 미열거와 직접 읽기 근거

**확인된 사실:** v1은 실기에서 DSDT 목록 0 때문에 본문 조회를 건너뛰었습니다. ACPICA의 [고정 Windows 수집 구현](https://github.com/acpica/acpica/blob/e85aa3bebaae81ed1e6d163511ac7e1eafe732cf/source/os_specific/service_layers/oswintbl.c#L231)도 DSDT/XSDT 미열거를 설명하고 DSDT를 고정 ID로 직접 읽습니다. 이 근거로 [v2 수정](ACPI_DSDT_DIRECT_READ_UPDATE.md)을 구현했습니다. 실제 실행 코드는 복사하지 않고 기존 Windows 두 읽기 API와 제한된 순수 파서를 사용합니다.

**가정·미검증:** 현재 모델에서 직접 DSDT 읽기와 WMI 정의 해석이 성공할지는 아직 모릅니다. 읽혀도 부분 구문 또는 SMM 내부 처리 때문에 FF 의미를 밝히지 못할 수 있습니다. 여러 SSDT를 읽는 별도 레지스트리 캐시 방식은 공개 구현에 있지만 전체 활성 테이블 계약으로 확인되지 않았고 이번에는 도입하지 않습니다. OEM/AML 호출이나 원본 내보내기는 없으며 제어는 Unsupported입니다. 아래는 이전 조사 기록입니다.

## 모델 계약 후속 정적 조사

[입력·버전·공개 ACPI 트리 대조](WMI_MODEL_CONTRACT_FOLLOWUP.md)를 추가했습니다. 조회0x80은Linux에도근거가있으며 version16→SABI3 변환근거는없습니다. 현재공개tree에서940/930X모델을찾지못했고다른모델AML/명령을대입하지않았습니다. 현재Windows명령/FF의미를확정할근거는여전히부족하므로실제제어를활성화하지않습니다. 일반앱의일반권한시작/배터리표시는사용자가확인했습니다.

## 실제 후보 응답 수신 — 프레임 검증과 의미 분리

[이번 결과와 정적 대조](WMI_ONE_SHOT_QUERY_RESULT.md): 사용자 노트북에서 승인된0x65 요청의 ResponseReceived/FrameChecked/ValidFrame/FF를 확인했습니다. 비동기 완료0·단일 출력·정확히21바이트/ACKAA를 통과했고 payload첫바이트만FF였습니다. 명령 지원·보호상태·상한·부작용 부재나 전체payload/명령echo는 확인하지 않았습니다.

고정hotkeys와Linux v6.12 소스를 대조했으나 각각Sabi3 DLL/직접SABI 경로의FF를 현재모델WindowsWMI 의미로 전이할 근거는 확보하지 못했습니다. FF를OFF나하드웨어미지원으로 확정하지 않고decoder수락조건도변경하지 않습니다. 승인된1회는사용됐으며추가요청/표식초기화/0x66은없습니다. 이번개발은일반앱의과거결과오프라인검토이며실제제어는Unsupported입니다. 아래는이전기록입니다.

## 승인된 조회 후보 한정 실험 도구

[승인과 구현 범위](WMI_ONE_SHOT_QUERY_APPROVAL.md): 사용자가 미검증0x65 후보의 한정1회 실험을 승인했습니다. 별도도구에서 고정모델/BIOS·token·schema·단일Active대상·영속예약을 확인해야요청하며 삼성DLL·쓰기명령·driver/service/ACL·포트IO·자동상승은 구현하지않습니다. 비동기완료상태0과정확히1개출력후에만고정Bytes를읽고후보표식만분류합니다.

새 도구는 아직 Windows에서 실행하지않았습니다. 후보의모델별의미·입력padding·실제응답계약·예상하지못한펌웨어부작용은여전히미검증입니다. 어떤표식도실제보호설정/지원/80%성공으로승격하지않으며 현재제어는Unsupported입니다.

## 추가 공개자료 대조와 다음 실제 단계의 경계

[이번 근거·후보 실험 검토서](WMI_ONE_SHOT_QUERY_REVIEW.md): voria의Linux도구와hotkeys추가callsite/이슈를 정적으로읽었지만현재940/930·P05ACJ의WindowsWMI배터리계약은확정하지못했습니다. hotkeys는FF와OFF를같은false로접으므로그대로재사용하지않고 미사용0x0B주석도 새조회근거로사용하지않습니다.

미검증0x65후보·입력·권한·한정횟수·중단조건·위험을검토가능하게정리했습니다. 실제OEM코드와실험은아직미승인·미구현·미실행이고 현재제어는Unsupported입니다. ACPI선언만보는추가진단은배터리명령계약을해결하지못해즉시추가하지않았습니다. 이번에는외부코드·AML·삼성프로그램을실행하지않았습니다.

## 메모리 전송 경계 연결과 공개 포크 후속 조사

[이번 통합 경로와 공개 근거](WMI_BOUND_CHANNEL_AND_PIPELINE.md): 요청 인코더·비동기 조정기·메서드 바인더·응답 디코더를 가짜 snapshot transport로 연결했습니다. 실제 WMI/OEM 구현은 추가하지 않았으며 클래스 일치나 내부 프레임 유효성을 하드웨어 지원으로 승격하지 않습니다.

새로 읽은 jesperol 포크는 기존 gh2o 고정 원문과 바이트가 같고, djpohly Kconfig는 battery parking만 설명합니다. 확인한 공개 포크·이슈 범위에서 현재 모델의 배터리 명령 의미·안전성·실제 응답 계약을 새로 확보하지 못했습니다. 다른 곳의 자료 부재나 하드웨어 기능 부재를 뜻하지 않습니다. 실제 충전 제어는 계속 Unsupported입니다.

## 실제 WMI 형식 일치 확인 완료

[판독기2 결과와 오프라인 바인더](WMI_MATCHED_BINDING_AND_OFFLINE_ENVELOPE.md): GUID 후보·메서드 존재·입출력 CIMTYPE의 DataBuffer·Bytes UInt8[]를 모두 확인했습니다. 두 클래스Complete·WindowsMethodId1이며 기존 입출력Unknown을 해소했습니다. 클래스 규약 진단은 완료됐고 같은 자료를 다시 요청하지 않습니다.

상세 메타데이터에서만 메모리용 중첩 입출력 바인더를 생성하도록 구현했으며 실제 OEM 전송은 없습니다. 공개linuxhw/ACPI의 고정 커밋 인덱스·삼성 디렉터리에서는 현재 모델/BIOS 자료를 찾지 못했습니다. 조사 범위 밖의 자료 부재나 기능 부재를 뜻하지 않습니다. 현재 모델 배터리 명령의 의미·안전성·실제 응답 계약은 여전히 미확정이고 실제 제어는 Unsupported입니다.

## 실제 WMI 클래스 관측과 미확정 입출력

[사용자 결과와 표준 CIMTYPE 근거](WMI_PARAMETER_RESULT_AND_CIMTYPE_REVIEW.md): 공개 GUID 후보 일치·CallSabiFunction 존재·Windows WmiMethodId1·DataBuffer.Bytes UInt8[]를 확인했습니다. 입력/출력은 Unknown이며 이전 도구는 CIMTYPE를 읽지 않았습니다. Microsoft 공식 정의의 object:EmbedClass 표기를 지원하도록 판독기를 수정했지만 현재 노트북에서 그 값이 제공되는지는 미관측입니다.

Windows 번호1을 공개 Linux0으로 매핑하거나 번호 차이로 비호환을 단정하지 않습니다. 이번 출력의 권한 수준도 미관측입니다. 클래스 정의의 연결 근거가 늘었지만 실제 명령 실행 권한·인스턴스 연계·배터리 명령 의미·안전성·실제 응답 계약은 확인되지 않았습니다. 실제 충전 제어는 계속 Unsupported이며 반복 파일/관리자 진단을 요구하지 않습니다.

## Windows 클래스와 공개 전송의 연결 확인 준비

[새 정적 메타데이터 도구와 추가 자료3건](WMI_EXCHANGE_AND_BINDING_CHECK.md)을 기록했습니다. 일반 권한으로 고정 WmiAcpiMethod/DataBuffer 정의만 읽고 공개 GUID 후보 일치·WmiMethodId·입출력 형식을 확인합니다. 새 노트북 출력은 아직 없습니다. WmiMethodId는 배터리 명령 번호가 아니며 정의 일치는 메서드 실행 권한·실제 응답 길이·현재 모델의 배터리 안전성을 입증하지 않습니다.

모델을 명시한 ativ9pctl은 밝기·음량·절전만 다루고, samsung-laptop-tools는 다른 11세대 모델의 Linux sysfs이며, TOOLS의 callSabiFunction은 외부 EXE 래퍼였습니다. 이 조사 범위에서는 현재 모델의 Windows 배터리 조회 계약을 확보하지 못했습니다. 자료의 부재나 기능 부재를 증명한 결과는 아닙니다. 실제 OEM 실행과 충전 제어는 여전히 미구현·미지원입니다.

## 추가 공개 WMI 프레임 근거

[두 공개 구현의 고정 커밋](WMI_REPLY_DECODER_AND_PUBLIC_EVIDENCE.md)에서 기존 서비스 wsabi와 같은 크기의21바이트 WMI 프레임과 payload16을 확인했습니다. 포인터 크기 또는 상한만 검사하는 원본의 길이 검사는 그대로 따르지 않았습니다. 공개 GUID와 현재 Windows 클래스의 동일성, 현재 모델의 배터리 명령, version16의 의미는 여전히 미검증입니다. 새 코드는 입력 바이트만 해석하며 실제 호출은 없습니다.

## 확인된 실제 비교: 일반 토큰의 부분 접근과 상승 토큰의 두 속성 조회

[권한 비교 결과](WMI_PERMISSION_COMPARISON_RESULT.md): 일반 실행은 버전 클래스의 Active=True/version16을 읽었지만 메서드 클래스 열거에서 0x80041003으로 거부됐습니다. 상승 실행은 두 클래스에서 활성 행1개씩과 version16을 읽었습니다. 이는 고정 속성 읽기의 접근 차이이며 메서드 실행·배터리 명령·실제 충전 제어 지원 근거가 아닙니다. 버전16 의미·행 연계·현재 모델의 조회 명령 계약은 아직 미확정입니다.

## PacketPrivacy로 해소되지 않은 WMI 거부

후속 TXT에서 암호화 인증 안내가 있는 빌드에서도 두 클래스 AccessDenied가 유지됨을 확인했습니다. 이로써 암호화 명시만으로 현재 문제가 해결되지 않았음을 확인했지만 현재 토큰 상승 여부·거부 단계·ACL/제공자 원인은 여전히 미확인입니다. [별도 제한된 비교 도구](WMI_PERMISSION_COMPARISON_REVIEW.md)를 준비했으며 관리자 비교는 아직 승인·실행하지 않았습니다. 실제 충전 제어는 계속 미지원입니다.

## 새 실제 관측: WMI 인스턴스 접근 거부

사용자 TXT에서 커널 드라이버 이름 후보 7개 모두 중지·수동 시작, SABI 이름 NotFound, WmiAcpiVersion/WmiAcpiMethod 모두 AccessDenied를 확인했습니다. 후보의 실제 용도나 WMI 거부 원인은 미확정입니다. Active·version은 관측되지 않았습니다. [분석·공식 근거·구현](WMI_ACCESS_RESULT_AND_TRANSPORT_REVIEW.md)에 일반 권한 암호화 인증 설정과 순수 프레임 준비를 기록했습니다. 접근 거부가 암호화 요구 때문이라는 것은 가설이며 실제 확인한 사실과 구분합니다. 관리자 실행·드라이버 시작·충전 지원 결론으로 바꾸지 않습니다.

## WMI 인스턴스 속성 확인 단계

사용자는 커널 드라이버 확인판의 실제 노트북 실행과 TXT 생성을 확인했습니다. TXT 내부의 드라이버 결과는 아직 전달받지 않았으므로 별도 미검증입니다. 기존 스키마에서 확인한 WmiAcpiVersion.Active/version과 WmiAcpiMethod.Active를 읽는 [새 기능](SAMSUNG_WMI_INSTANCE_INSPECTION.md)을 구현했습니다. 속성 읽기는 제공자를 사용하며 클래스 메타데이터 검사와 구분합니다. 새 조회의 노트북 결과·버전 의미·명령 호환성은 아직 미검증입니다. Active나 인스턴스 발견은 실제 보호 상태 또는 제어 지원 근거가 아닙니다.

## 최신 관측: SABI 연결 이름과 WMI 전송 구조

`samsung-files-20261101T132149`에서 현재 SABI 연결 이름을 찾지 못한 결과를 받았습니다. x64 DLL의 해시는 기존 정적 분석 대상과 같습니다. 드라이버 미설치나 펌웨어 기능 부재로 확정하지 않습니다. 기존 서비스 폴더 wsabi의 추가 정적 분석에서는 별도의 WMI 전송 구조(payload 16바이트·입력 21바이트)를 확인했습니다. 이는 Sabi3 x64의 11바이트 규약과 다르며, 현재 Settings 폴더의 다른 wsabi 해시에 일반화하지 않습니다. [최신 근거·코드 반영·다음 조건](SABI_LINK_RESULT_AND_WMI_REVIEW.md)을 우선 읽으세요. 아래 자료 수집 보류·선행 자료 요청은 당시 단계의 이력이며 사용자가 이후 직접 제공한 DLL의 현재 분석 범위를 대체하지 않습니다.

## 확인된 사실

최신 파일 식별 TXT에서 **Sabi3 3.2.0.0의 x64·x86과 공개 예제 함수 이름 5개**를 실제 확인했습니다. Settings 하위 폴더에서 네 대상 파일이 모두 관측됐으며 wsabi는 여러 다른 해시가 있습니다. [파일별 관측과 적용 한계](SABI3_COMPATIBILITY_REVIEW.md)에 기록했습니다. 메타데이터 확인을 현재 DLL 초기화·OEM 조회 성공으로 보지 않습니다.

사용자 화면·진단과 로컬 정적 분석에서 확인한 범위입니다. 원본 사용자 진단 파일과 삼성 바이너리는 저장소·배포물에 포함하지 않습니다.

- 모델: `940X3G/930X3G`, BIOS: `P05ACJ.128.140819.dg`.
- Windows 10 Home `10.0.19045`, OS와 앱 프로세스는 x64.
- 이전에 Windows와 앱이 모두 표시한 0%는 사용자가 당시의 실제 상태임을 확인했습니다. 수치 보정 대상이 아닙니다.
- 2026-10-31 후속 화면과 진단에서는 **62%, AC 연결 안 됨, 방전 중**이었습니다. `GetSystemPowerStatus`와 `Win32_Battery` 잔량이 62%로 일치했습니다. 현재 값은 계속 Windows 측정에 따라 갱신합니다.
- 2026-11-01 진단에서는 GetSystemPowerStatus 53%, WMI 52%, AC 연결 안 됨이었습니다. 순차 조회의 1%p 차이이며 값을 보정하지 않습니다.
- 같은 진단의 표준 배터리 조회는 인터페이스 1개에서 완료됐고 Capabilities는 `0x80000000`이었습니다. 시스템 배터리 표시만 있고 표준 충전·방전 요청 지원 비트는 없습니다. 현재 드라이버의 이 표준 경로를 제어에 사용하지 않습니다. OEM 기능 전체의 부재로 확정하지는 않습니다.
- 후속 `diagnostics-20261101T021357`에서는 52%, AC 연결, 충전 중이며 Win32와 WMI 잔량이 일치했습니다. 새 결과 해석 문장이 TXT에 정상 기록됐고 표준 지원 비트는 같았습니다. 이 TXT로 새 메인 화면의 렌더링까지 검증했다고 주장하지 않습니다.
- 공개 구형 Windows 래퍼와 Linux SABI3에서 배터리 수명 연장의 조회·변경 명령 후보를 찾았습니다. Windows 래퍼는 삼성 DLL에 의존하며 현재 WMI 바이트 계약이나 해당 모델의 실제 제어를 검증하지 않습니다. [공개 규약 비교](PUBLIC_CONTROL_PROTOCOL_REVIEW.md)에 출처와 한계를 기록했습니다.
- Samsung Settings 2.2.0이 설치되어 있지만 충전 제한 메뉴가 없다고 사용자가 확인했습니다.
- 사용자는 `Sabi3.dll`이 설치 폴더에 있다고 추가 보고했고 참고 경로 `C:\Program Files (x86)\Samsung\Setting`을 전달했습니다. 클라우드에서 이 폴더나 실제 DLL을 확인한 결과는 아닙니다. 이번에는 [DLL 후보 목록](SAMSUNG_DLL_CANDIDATES.md)으로 기록했으며 앱의 탐색·실행 경로로 사용하지 않습니다.
- 사용자는 BIOS 설정에도 배터리 충전 제한·수명 연장 메뉴가 없음을 추가 확인했습니다. 두 설정 화면의 부재는 관측 사실이며, 미공개 펌웨어 기능의 유무나 제어 안전성을 입증하지 않습니다. 메뉴 재점검은 요청하지 않습니다.
- `SamsungSystemConfiguration` 서비스가 실행 중인 것으로 보고됐습니다. 서비스 실행은 충전 제한 지원 증거가 아닙니다.
- 업로드된 `SamsungConfigurationMonitor.exe`는 같은 폴더의 `wsabi.dll`을 정적으로 참조합니다. 확인된 호출 문맥은 팬·정숙 모드입니다. 이 문맥의 `0x80`을 배터리 80% 명령으로 해석하지 않습니다.
- `wsabi.dll` 수집에 성공했습니다. 파일은 22,920바이트이며 SHA-256은 `564b640d62db2a4e4b56c6331e0e526bad2ac1fcf438a41a9e5241551f457b6e`입니다.
- 해당 DLL은 x86 네이티브 WMI/COM SABI 중계 DLL입니다. export는 `InitBIOSInterface`, `UninitBIOSInterface`, `CallBIOSInterface`, `GetBiosVersion`, `GetBiosMode`입니다.
- 정적 코드에서 `ROOT\WMI`, `WmiAcpiVersion`, `WmiAcpiMethod`, `DataBuffer`, `Bytes`, `inData`, `outData`, `CallSabiFunction` 참조를 확인했습니다.
- 후속 실제 노트북 진단에서 아래 클래스·메서드 정의를 모두 찾았고, 보고서에 기록된 조회 오류는 없었습니다. 속성 이름·형식과 메서드 정의만 읽었습니다. 해당 인스턴스 값은 읽지 않았고 OEM 메서드는 실행하지 않았습니다.

| 정의 | 실제 확인한 스키마 |
| --- | --- |
| `WmiAcpiVersion` | `Active: Boolean`, `InstanceName: String`, `version: UInt32` |
| `WmiAcpiMethod` | `Active: Boolean`, `InstanceName: String`; `CallSabiFunction(inData: Object) → outData: Object` |
| `DataBuffer` | `Bytes: UInt8[]` |

`CallBIOSInterface`에는 실제 WMI 메서드 실행 경로가 있으므로 읽기 전용 진단 함수로 취급할 수 없습니다. `GetBiosMode`가 조회하는 것은 SMBIOS 정보이며 배터리 보호 모드로 볼 근거가 없습니다. 이 분석에서는 OEM 파일을 실행·로드하거나 DLL 함수를 호출하지 않았습니다. 삼성 DLL의 전자서명 신뢰 검증도 수행하지 않았습니다.

## 가정

기존 Samsung/SABI 이름 필터만 사용한 목록은 위 클래스를 찾지 못했지만, 정확한 클래스 이름을 사용한 후속 정의 조회에서는 발견했습니다. 이로써 중계 인터페이스의 존재를 확인했으며 충전 제어 지원을 확인한 것은 아닙니다.

Samsung Settings 앱의 EXE·DLL에서 메뉴·모델 지원 조건을 확인하려던 접근은 이전 단계의 가설입니다. 현재는 사용자 조건에 따라 해당 앱에서 DLL을 추출할 수 없다고 가정하고 진행합니다. 추가 삼성 파일 수집이나 분석을 선행 조건으로 요구하지 않습니다. 공개 자료에서 해당 모델의 Windows OEM 명령과 실제 설정 조회 규약을 확인하는 경로로 전환했습니다. [공개 자료 검토 결과](DLL_INDEPENDENT_RESEARCH.md)를 참고하세요.

## 아직 검증되지 않은 항목

- `CallSabiFunction` 입력 바이트의 의미와 모델·BIOS별 지원·안전 범위
- 공개 명령 후보를 현재 모델의 Windows WMI로 전달하는 방법, 실제 80%/100% 상한의 의미와 현재 설정을 읽는 방법
- Samsung Settings 앱의 충전 메뉴 노출·모델 지원 조건
- Windows에서 쓸 수 있는 공식·검증된 OEM 제어 인터페이스
- 앱 종료·재부팅·전원 차단 뒤 펌웨어 설정 유지 여부
- 삼성 DLL의 공식 ABI와 전자서명 신뢰

클래스나 메서드가 발견되어도 실제 제어 지원으로 표시하지 않습니다. 하드웨어 상태는 계속 미지원으로 유지합니다.

## 다음 검증

현재는 삼성 프로그램 파일의 추가 수집·분석을 보류합니다. 먼저 해당 버전의 사용권 계약과 정확한 모델·BIOS·Windows 조합의 공식 지원 근거를 확인합니다. 공식 사이트 조회 준비 상태와 미전송 문의 초안은 [OFFICIAL_SUPPORT_REVIEW.md](OFFICIAL_SUPPORT_REVIEW.md)에 기록했습니다. 아직 공식 문서나 계약 조항을 열람하지 못했으므로 허용·금지나 충전 기능 지원 여부를 확정하지 않습니다.

실제 커널·펌웨어 제어 코드는 별도의 명시적 사용자 승인과 모델 적합성·안전성 근거가 확보된 뒤에만 추가할 수 있습니다.

## 설치 위치 정보 누락 결과와 수정

후속 사용자 Settings 분석 ZIP은 모듈 0개인 보고서 전용 자료였습니다. 32비트 Samsung Settings 등록은 발견됐지만 InstallLocation/DisplayIcon 문자열이 모두 비어 ICON_PATH_NOT_PROVIDED로 종료했습니다. 이는 앱 미설치나 배터리 제어 미지원의 증거가 아닙니다.

이 경우에만 시스템 Program Files/PFx86/ProgramData의 Samsung\Settings 또는 Samsung\Samsung Settings 전용 후보 최대 6곳을 확인하도록 수정했습니다. 등록 불일치나 제공 경로 거부에는 적용하지 않습니다. 링크 차단·회사 정보/PE 검사·복사 한도·동의 확인은 유지합니다. 수정 후 실제 Windows 파일 확보는 아직 검증하지 않았습니다.

## 2026-11-01 사용자 결과 확인

위치 누락 수정판의 후속 보고서에서 `RegisteredKnownDirectory`, `SettingsProgramFilesX86`, `Settings.exe` 앵커 발견을 확인했습니다. 대체 위치 확인은 동작했지만 회사 표시 정보가 수집 조건을 통과하지 않아 `COMPANY_NOT_SAMSUNG`으로 제외됐으며 복사 모듈 수는 0개입니다. 회사 정보가 누락된 것인지 다른 값인지는 이 보고서로 구분할 수 없습니다. 실제 파일 바이트는 아직 확보하지 못했습니다.

같이 재첨부된 이전 서비스 ZIP의 5개 모듈 SHA-256은 기존 분석 대상과 모두 일치했습니다. `wsabi.dll`도 같은 파일이며 배터리 명령에 관한 추가 근거는 없습니다. 원본 사용자 ZIP이나 OEM 파일은 저장소에 포함하지 않습니다.

앞서 요청했던 Settings.exe 직접 전달은 사용권 확인 전까지 철회했습니다. 추가 OEM 파일을 요청하거나 분석하지 않습니다. 위 수집 결과는 과거 조사 기록이며, 현재 진행 방향은 공식 지원·사용권 확인입니다. 실제 충전 제어는 계속 미지원입니다.

## Windows 버전별 지원 차이에 관한 사용자 제공 단서

사용자는 Windows 8에서는 충전 제한을 지원했으나 Windows 10 및 Samsung Settings 2.2 이후 메뉴가 사라졌다는 보고를 제시했습니다. 현재 사용 환경은 Windows 10과 Settings 2.2.xx입니다. 해당 보고의 원문 URL·정확한 모델·BIOS·이전 소프트웨어 버전은 아직 확보하지 못해 과거 지원 사실을 독립 검증한 것은 아닙니다.

같은 모델의 과거 공식 지원이 확인된다면 Windows 10용 OEM 프로그램의 기능 변경, 모델 판별, 드라이버/API 호환성 또는 지원 정책 차이를 우선 조사합니다. 보고만으로 정확한 원인이나 현재 펌웨어의 제어 가능성을 확정하지 않습니다. 메뉴 부재를 하드웨어 불가능으로 단정하지 않으며, UI 제거만을 확정 원인으로 취급하지도 않습니다.

다음 문서 비교는 Windows 8 당시 같은 모델의 공식 충전 제한 설명·프로그램 버전·요구 드라이버와 Windows 10/Settings 2.2의 공식 지원 범위입니다. 사용자에게 요청할 자료는 보고의 공개 URL 또는 문서 제목이며 삼성 실행 파일·DLL의 추가 수집은 계속 보류합니다. 실제 충전 제어는 미지원 상태를 유지합니다.
