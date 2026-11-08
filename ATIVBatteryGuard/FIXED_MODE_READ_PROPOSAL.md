# 고정 보호 저장 byte의 조건부 시험안 — 비실행 문서

**오프라인 시험 준비:** [시나리오·정제 기록](READ_TRIAL_REHEARSAL_PLAN.md)은 public 사전차단부터 내부 대역의 pending/cleanup까지 재현합니다. 생성된 기록은 가짜 SDK의 관측이며 실제 요청 명세·제공자 연결·입력 보호의 하드웨어 근거나 실행 승인이 아닙니다. A/B 호출 수·상태 영향·실행 보류를 유지합니다.

**제공자 후보 후속:** [구조·역방향 조사](COMMUNICATION_PROVIDER_CANDIDATE_REVIEW.md)에서도 실제 표준 제공자 연결은 미확정입니다. Base2 동적 InSmm을 통신 후보에서 제외하며, Nvram 수신자가 쓰지 않는 incoming buffer와 retained buffer의 동일성을 새 조건으로 두지 않습니다. 기존 정상 legacy 경로는 유지하고 nonnull 분기의 긍정적 순서 근거 한계를 실제 위험 관측으로 바꾸지 않습니다. A/B 실행 보류와 호출 수는 유지합니다.

**Runtime 부팅 경로 후속:** [선택된 알림 처리 지점](RUNTIME_POSTBOOT_TRANSPORT_REVIEW.md)은 정상 교체 조건과 초기화 예외를 구분합니다. 성공 반환 0만으로 교체를 인증하지 않으며, 정상 proxy 설치 시 초기 direct-host 경로를 같은 분기의 경쟁자로 중복 취급하지 않습니다. NULL 캐시의 legacy 순서 근거는 유지하고 nonnull 제공자 method0의 실제 dispatch 연결은 미완료입니다. A/B 호출 수·권한·실행 보류는 그대로입니다.

**응답 명세 후속:** [거부 규칙과 참여자 적용](FIXED_READ_ACCEPTANCE_SPECIFICATION.md)은 관측 가능한 거부 규칙, 8개 보존 셀의 nonzero·균등·독립 단발 충돌 모델을 비실행 후보로 구체화했습니다. 이는 수용 결과의 신뢰도를 뜻하지 않으며 실제 값/생성기/요청은 없습니다. 알려진 host Runtime 게시자의 선택 조회와의 보호·순서 연결이 남아 A/B 실행 보류를 유지합니다.

**입력·회수 후속:** [보호 구간 검토](FIXED_READ_INPUT_AND_CAPTURE_REVIEW.md)에서 ready admission과 완료 후 결과 회수를 구분했습니다. 입력 upload 30바이트·반환 prefix 10바이트·전체 indexed I/O의 수명을 따로 유지하며, 같은 SMM 순서만으로 바깥 WMI frame 회수를 보호하지 않습니다. A/B의 호출 수·권한·실행 보류는 유지합니다.

**바이트 계약 후속:** [선택 callback/reader 합성](FIXED_READ_BYTE_CONTRACT_REVIEW.md)은 주소 upload/반환 분기·payload 순서·반환 창과 지워지는 WMI tail을 좁혔습니다. 실패/command-only sample zero를 stored mode로 수용하지 않으며 기존 prefix 표시를 유지합니다. 실제 요청·nonce·frame을 생성하거나 A/B 실행을 허용한 결과는 아닙니다.

**현재 entry 적용:** [시작·중단 조건 구현](READ_TRIAL_ENTRY_CONDITIONS_UPDATE.md)에서 공개 SDK 시험 entry는 실제 고정 읽기 명세 부재로 사전 차단됩니다. 내부 기계 연결의 synthetic 회귀는 이 A/B의 실행 허가나 실제 요청 명세가 아닙니다. 아래 A/B의 횟수·gate 영향·조건부 의미는 유지합니다.

**host 후속:** [RunAndCloseAsync 구현](INVOCATION_HOST_LIFETIME_UPDATE.md)은 bounded 결과 표시 뒤에도 관련 close를 기다립니다. 실제 WMI source·Main 연결·아래 A/B의 선택·호출 수·승인 범위를 변경하지 않았습니다. B의 연속 소유권을 두 단발 세션으로 대신하지 않습니다.

**시험안 검토 가능 / 실제 코드 연결·실행 보류.** [WMI·ACPI 반환과 EC 재사용 검토](WMI_ACPI_RETURN_AND_EC_REUSE_REVIEW.md)와 [현재 판정](FIXED_MODE_READ_DECISION.md)을 반영한 구체 안입니다. 실행용 주소·command·표식 값·프레임·generator·backend는 포함하지 않으며 사용자가 지금 수행할 작업은 없습니다.

[후속 software 수정](BOUND_TRANSPORT_FAILURE_QUARANTINE_UPDATE.md)은 Bound 뒤에서 사라지던 직접 throw/null의 owner 격리 정책을 복구합니다. 실제 SDK 내부 async fault의 완료를 새로 판정한 것은 아니며 아래 A/B의 호출 수·상태 영향·승인 상태는 그대로입니다.

[SDK 수명 private 증명](SDK_INVOCATION_LIFETIME_REVIEW.md)은 확실한 미진입 또는 call exit+관련 terminal+선택 capture settled를 종료 조건으로 검산했습니다. 실제 SDK의 terminal 소실을 해결한 것은 아니며, A/B 실행 준비·하드웨어 종료 증명으로 승격하지 않습니다.

[공통 호출 세션](MANAGED_INVOCATION_SESSION_UPDATE.md)은 이제 같은 계약을 실제 transport/host 코드로 구현하고 fake 회귀로 검증합니다. 실제 SDK source·GUI close hook을 연결한 것은 아니며 아래 호출 상한·gate 영향·승인 범위는 그대로입니다.

## 현재 기본 안 A의 목표와 횟수

목표는 임시 CandidateProfile에 고정된 보호 모드 저장 byte를 한 번 읽어 **저장 후보값**으로 분류하는 것입니다. 충전기 적용·잔량·Windows 충전 상태와 구분합니다. 실제 제어 활성화·설정 변경·임계값 쓰기는 범위에 없습니다.

| 항목 | 이 안의 상한 |
| --- | --- |
| WMI/OEM method 호출 | 읽기 요청 최대1회 |
| 고정 대상 byte 샘플 읽기 | gate·전달 조건에 따라0~1회 |
| gate handshake·DLL/OEM 초기화 | 0회 |
| 자동 재시도·다른 명령 fallback | 0회 |
| firmware 설정·배터리/충전기 쓰기 | 0회 |

0~1회는 고정 대상 byte의 샘플 횟수이며, mailbox 접근·ready polling이나 무관한 EC 활동 전체의 횟수가 아닙니다.

현재 generic callback의 software gate는 미관측입니다. 저장 원본의 초기 값은 닫힘이며 이를 여는 handshake는 별도 호출·image-data 변경입니다. 이 안에 숨겨 포함하지 않습니다. 닫힌 gate 때문에 값이 안 나올 수 있다는 **시험 유용성의 제한**을 명시합니다. handshake를 추가한 시험은 다른 호출 수·상태 영향·승인 범위가 필요합니다.

## 유용성 비교 — 추가 호출은 별도 비실행 대안

현재 기본 안은 아래 A이며, B는 호출 수와 상태 영향을 드러내기 위한 **별도 검토 대안**입니다. 두 안 모두 실제 backend 연결·실행 승인을 요청하는 단계가 아닙니다. B를 A의 실패 후 fallback으로 수행하지 않습니다.

| 항목 | A: 현재 기본 안 | B: 별도 검토 대안 |
| --- | --- | --- |
| 사전에 정할 순서 | 고정 읽기 시도만 | local gate handshake1회 → 그 응답 검증 후 조건부 고정 읽기1회 |
| WMI/OEM method 호출 상한 | 1회 | 2회. handshake 실패·불명이면 읽기0회 |
| 고정 대상 byte 샘플 | 0~1회 | 0~1회 |
| generic gate 상태 변경 | 추가하지 않음 | handshake가 공유 image-data gate를 열 수 있음 |
| DLL·boot 초기화/재시도/사후 reset | 모두0회 | 모두0회 |
| 유용성 제한 | source 초기닫힘 상태라면 값을 얻지 못함 | gate 조건을 줄일 수 있지만 실제 EC 실행·응답 신선함은 별도 |

B의 handshake는 선택 소스에서 EC helper를 호출하지 않지만 **상태 변경이 있는 별도 OEM 호출**입니다. 같은 generic 인터페이스의 후속 동작 허용에도 영향을 주므로 쓰기가 전혀 없는 조회라고 표시하지 않습니다. 선택 소스에는 이전 gate 값을 복원하는 분기가 없으며 현재 loaded firmware에서의 상태 지속·복원을 관측하지 않았습니다. 설정·충전기 쓰기나 사후 reset을 추가해 되돌리려 하지 않습니다.

B를 실제 안으로 채택하려면 두 호출의 입력 준비·회수와 그 사이를 포함하는 관련 소유권/참여자 규약, 마지막 공유 접근과 오류 처리를 함께 검토해야 합니다. API·서명 검증에 실패하거나 완료가 불명확하면 후속 읽기는 없습니다. 이 중단은 이미 일어났을 수 있는 gate 변경의 rollback을 뜻하지 않습니다. handshake 성공은 고정 읽기의 실행·신선함을 인증하는 token이 아닙니다. 주소·frame·표식·generator·호출 코드는 어느 안에도 만들지 않았습니다.

## 프로파일과 선택 경로

보존된940X3G/930X3G 계열 관측, BIOS P05ACJ.128.140819.dg, 제조사 원본의 EC 배치·주소 관계와 독립 해석 anchor를 묶습니다. 조건부 ISA/bank 해석·현재 이미지 미관측은 가정으로 명시하고 다른 모델/BIOS로 확대하지 않습니다. live EC 전체 hash나 host 함수 포인터 관측은 제안 작성의 절대 전제가 아닙니다.

선택 WMI 조회의 AML→PCH legacy SW 등록→SABI generic callback은 저장 소스로 연결했습니다. 별도 Runtime 변수 proxy의 표준 typed 통신 미연결을 이 조회 진입 자체의 필수조건으로 두지 않습니다. 관련 EC 후크 게시자의 실행 순서·고정 대상·정상 전달과 재사용 계약은 별도 평가합니다. source byte와 현재 장치의 지원 확정을 구분하며 선택하지 않는 모든 대안 경로의 완전 해명을 요구하지 않습니다.

공식 mapper·WMI method 입출력·ACPI 평가 계약과 모델 선언 대응 가정 아래 정상 평가/반환은 조건부 연결됨으로 동결합니다. 세부 매핑 규격 원문 미확보를 별도 중단 조건으로 두지 않으며 새 불일치·반례·관련 원문이 생길 때만 다시 검토합니다. 불명 dispatch와 응답 신선함은 이 정상 계약으로 대신하지 않습니다.

## 기본 안 A의 한 번의 흐름과 중단선

1. **준비:** 모델/BIOS·기존 metadata·정상 토큰 조건과 고정 요청 형식이 검토된 프로파일 범위인지 확인합니다. 시리얼·계정·전체 경로는 보고하지 않습니다. 임의 주소·명령·길이 입력은 없습니다.
2. **획득:** 관련 전체 교환을 보호하는 규약에서 유한 대기합니다. 접근 거부·시간 초과·abandoned·불명확 소유권은 요청 없이 종료합니다. OS 권한·이름·계정 fallback은 없습니다.
3. **게시 전 확정:** 공유 입력·명령·고정 대상 무결성과 기존 작업 입력 비훼손 조건이 충족되고 stop이 admission보다 먼저 이기지 않은 경우에만 최대1회 시도합니다. 앱 slot이나 사후 내용 비교만으로 전제를 대체하지 않습니다.
4. **회수·분류:** 해당 요청의 공유 준비·trigger·응답 소비가 끝났다는 계약 안에서 detached 결과만 분류합니다. 아래 모호한 경우는 성공으로 받지 않습니다.
5. **정리:** UI timeout과 실제 관련 작업 종료를 구분합니다. 완료 불명이면 새 요청을 허용하지 않고 process 종료나 잠금 해제를 provider 정지로 해석하지 않습니다. 사용 완료된 과거 단발 예약을 읽거나 초기화·삭제·재사용·우회하지 않습니다.

host WMI 프레임의 snapshot/copy 수명과 EC command/data mailbox의 후속 재사용을 구분합니다. 확인한 callback closure에는 반환 뒤 host 프레임을 다시 쓰는 예약이 없습니다. 독립 SDK cleanup·모든 EC 활동의 정지를 요구하지 않고 각 관련 입력·명령·응답의 마지막 접근을 평가합니다. 정상 최종 성공은 API 완료 근거이며, 취소로 생성된 완료 알림은 provider 정지 근거가 아닙니다. 기존 backend에는 이 SDK 취소 호출이 없고 이번에도 연결하지 않습니다.

## 결과 분류

| 관측 조건 | 보고할 분류 |
| --- | --- |
| 획득/준비 실패 | 미시도 + 권한/시간 초과/오류 구분 |
| API·method·구조 오류 | 판정불가. 확인된 오류 종류만 보고 |
| gate 거부로 식별된 응답·FF·기타 모호한 응답 | 판정불가. FF의 보편적 의미나 원인을 추정하지 않고 보호 해제·미지원·드라이버 부재로 바꾸지 않음 |
| 입력 echo·fresh-content 불일치·귀속 불명 | 판정불가. 추가 호출 없음 |
| 허용 해석 밖의 값 | 판정불가. 의미를 추측하지 않음 |
| 고정 대상·실행 전 무결성과 신선한 응답 전제 아래 허용된 값 | 저장 모드 후보값. 실제 충전 적용은 Unknown, 제어는 Unsupported 유지 |

fresh host content는 특정 이전 내용/송신 생략을 구분하는 전제이며 EC 고유 완료ID가 아닙니다. 보존 tail 일치만으로 첫 주소 성분의 소비 당시 값·전체 입력 안정성·reader 실행을 인증하지 않습니다. echo 거부도 입력과 허용 결과 영역이 분리된다는 근거가 있어야 합니다. 실제 nonce나 프레임 값은 생성하지 않았습니다.

## 실제 연결 전 남은 세 조건

- 선택 경로·고정 대상·gate 범위와 모델 적합성의 검토 근거.
- 공유 입력 준비~응답 회수에 실제 참여하는 관련 호출자들의 보호/순차화 규약.
- 관련 host/provider 완료·기존 작업 입력 비훼손·안전한 결과 분류의 계약.

미확인 IRQ/status가 이 자원에 영향을 준다는 구체 연결이 생길 때만 그 범위를 조사합니다. 이미 확인한 inline 소비·버퍼 분리·ISR 보존을 전체 미확인 hardware 문제로 되돌리지 않습니다. 모든 writer의 부재나 Global ACL 사전 수집도 필수화하지 않습니다.

이 문서는 조건부 설계 검토 결과이며 **실행 승인 요청이 아닙니다**. 프로젝트 [AGENTS.md](AGENTS.md)의 “커널/펌웨어 제어 코드 추가 작업은 사용자에게 별도의 명시적 승인을 받은 뒤 안전성과 모델 적합성이 입증된 범위에서만 진행한다.”는 조건을 유지합니다. 실제 backend·실기 호출은 추가하지 않았고 새 노트북 실행이나 동일 자료 제출은 필요하지 않습니다.
