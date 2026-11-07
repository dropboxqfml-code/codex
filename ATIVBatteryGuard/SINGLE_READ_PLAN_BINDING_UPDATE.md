# 단발 조회안의 대상·고정 요청·준비 경로 결합 — 2026-11-08 한국 시간

**A안의 선언한 대상 조건과 한 번의 software handoff를 prepared 경로에 연결했습니다.** 순수 `WsabiWmiSingleReadPlan`과 Windows의 고정 요청 handle을 추가했습니다. 실제 보호 byte 조회 template/명령은 만들지 않았으며 기존 synthetic 요청을 주입해 이행 경로를 검증했습니다. [이전 등록 준비](WINDOWS_WMI_PREPARATION_UPDATE.md)의 후속이며 실제 보호 설정 조회·충전 제어는 Unsupported입니다.

## 대상 plan

plan은 공급된 detached 사실을 비교합니다. 제품명은 저장 관측의 단일 WMI Name `940X3G/930X3G`, BIOS는 전체 `P05ACJ.128.140819.dg`에만 맞춥니다. 기존 비교와 같이 raw 길이128 이내에서 Trim/OrdinalIgnoreCase를 사용하며 UI의 prefix 지원 판정이나 두 모델의 OR 조건으로 확대하지 않습니다. Windows10 x64도 공급된 선언이며 새 OS probe로 입증한 사실은 아닙니다.

local namespace·method class/name, 완료 열거·정확히 한 instance·Active=true·nonnull opaque target identity를 요구합니다. 상세 metadata는 기존 Binder의 대체 qualifier 허용을 그대로 재사용하고 Windows MethodId1을 따로 확인합니다. CIMTYPE 매치/EmbeddedInstance 미관측을 거부하지 않으며 기존 EmbeddedInstance 대안도 유지합니다. 별도 instance path·사용자·serial/UUID 필드는 추가하지 않았으며 opaque identity의 내용을 읽거나 보고하지 않고 reference로만 비교합니다.

B의 handshake+read 및 알 수 없는 variant는 이 plan에서 거부합니다. A의 선언 상한은 handoff1·handshake0·retry0·setting-write0입니다. `MatchesCandidateScope`는 공급 사실의 일치이며 hardware 관측/지원/권한이 아닙니다. 실제 frame이 읽기인지 쓰기인지는 opaque template로 입증하지 못합니다.

## 준비 전에 고정한 실행 입력

Windows binding은 대상 사실·준비된 observer·supplied dispatch 참조를 불변 묶음으로 보유합니다. plan의 대상과 다른 token/범위를 거부하고, MethodId·형식·command/frame 관계가 맞는 기존 요청만 복사·canonical 재구성합니다. 기존 generic encoder를 사용하는 형식 검사이며 새 실제 요청 생성기나 firmware recipe를 추가한 것은 아닙니다. 불일치면 lower preparation/추가 SDK subscription을 시작하지 않습니다. 제공된 observer 자체를 외부에서 생성하거나 이미 사용했는지까지 이 검사로 인증하지 않습니다.

plan 참조의 첫 유효 인자 준비 시도에서 단발 예산을 소모합니다. 그 뒤 target/request 거부·취소·등록 실패·Unknown·미사용 닫기가 생겨도 같은 plan을 새 binding/observer/wrapper로 감싸 재무장하지 않습니다. 형식상 null dependency/잘못된 timeout은 이 claim 전에 인자 오류로 거부합니다. 새 plan·다른 프로세스·직접 lower API까지 영구1회를 보장하는 보안 경계나 persistent 예약은 아닙니다. 사용 완료된 옛 예약을 읽거나 재사용·초기화하지 않습니다.

성공한 고정 handle의 Run은 **publish callback과 실행 token만** 받습니다. command/payload/target/variant를 실행 시 다시 고르지 않습니다. private 복사본으로 기존 prepared Run을 소비하고, 실제 supplied-dispatch handoff 직전에 observer reference·MethodId·command·frame 전체 byte를 확인해 최대 한 번만 넘깁니다. 입력 불일치나 같은 guard의 재진입은 고정 실패이며 자동 재시도/다른 명령 fallback은 없습니다.

같은 요청의 Frame/Arguments getter 복사본이나 최초 입력 배열을 바꿔도 전달 값은 유지됩니다. bundle이 고정하는 것은 참조이며 delegate closure의 행동 불변·실제 SDK 대상·delegate 내부 SDK method 수·현재 데이터 신선함까지 인증하지 않습니다. 저수준 generic preparation/command API는 유지하므로 이 제한은 새 정책을 경유하는 host 흐름의 범위입니다.

## 종료와 결과

registration 결과는 이전 preparation 상태 그대로 구분하고 실패면 고정 handle을 반환하지 않습니다. Run/Close 순서·보고 예외·소유 thread 해제·실제 진입 뒤 Unknown의 구독/lease/host 대기는 기존 prepared 경로를 재사용합니다. token 취소나 software 예산 소모를 provider terminal로 바꾸지 않습니다. 합성 late terminal은 테스트 정리일 뿐 실제 SDK 완료 보장이 아닙니다.

structurally valid frame은 저장 모드나 충전 제한 성공이 아닙니다. gate 미관측·FF·echo·불명 귀속에 대한 [기존 A/B 결과 분류](FIXED_MODE_READ_PROPOSAL.md)는 유지합니다. 이번에는 고정 보호 byte의 read semantic·실제 SDK dispatch 구현·실행 승인을 연결하지 않았습니다.

## 검증

plan9개·binding6개·lifetime6개, **신규21개 포함 전체562개 통과·실패0·skip0**입니다. 먼저 plan/binding15개 포함556개가 통과했고 수명6개 통합 후562개를 확인했습니다. 최초 컴파일에서 테스트의 short-circuit out 변수 definite-assignment 오류1개를 수정했으며 제품 기능 실패를 재현한 것으로 세지 않습니다. 전체 솔루션은 실제 net48 참조 Release 빌드 **경고0·오류0**입니다.

scope/metadata/MethodId/identity 거부, 복사·동결, lower 등록 전 mismatch 거부, handoff 전체 byte 비교, 같은 plan 두 준비의 동시 경쟁, 취소/등록 실패 뒤 alias 재시도 차단, close-first, Unknown·gate/lease·보고 예외를 검증했습니다. 기존 synthetic 요청만 사용했고 old OneShotPolicy의 candidate/payload 생성기를 재사용하지 않았습니다. 테스트 SDK 객체는 stand-in이며 실제 System.Management runtime/provider/노트북 호출을 실행하지 않았습니다. Windows 연결 계층의 production 소스 5개를 같은 portable 시험에 링크했고 이전 private 검산 수는 합산하지 않았습니다.

[정제 기록](reports/single-read-plan-binding-audit.json)에 source/test hash와 관측 범위를 남겼습니다. source/객체 제공 계약의 일치와 실제 하드웨어 사실을 구분합니다.

## 다음 작업과 제공 범위

다음은 A안의 실제 고정 대상/요청 의미와 구체 SDK dispatch가 위 선언한 예산을 이행하는지 저장 근거와 대조해, 실행 가능한 시험안으로 승격할 조건을 정리하는 일입니다. 현재 gate의 유용성·관련 소유권·완료/귀속·실행 승인은 여전히 별도입니다. B를 채택하거나 A 실패 후 handshake를 숨겨 추가하지 않습니다. 지금은 새 실행 승인이나 노트북 시험을 요청하지 않습니다.

Core 새plan1·Windows adapter1·tests5파일(새3/등록/프로젝트)과 문서/정제 기록을 변경했습니다. 앱 기본 backend/UI·기존SDKBackend/Program·encoder·사용 완료된 예약·배포 ZIP은 그대로입니다. 실제 WMI/OEM/hardware/Global 객체·삼성 원본·드라이버/서비스/보안/펌웨어·클라우드 환경을 건드리지 않았으며 새 자료 제출은 필요하지 않습니다.
