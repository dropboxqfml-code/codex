# 고정 보호 저장값 단발 조회 명세 — 비실행 검토본

**적용 검토 후속:** [대상·자원·SDK crosswalk](FIXED_READ_APPLICABILITY_REVIEW.md)에서 저장값의 조건부 의미와 SDK 대상 API 문서를 대조했습니다. mode 후보1만으로 현재80/75임계값·실제80%제한을 입증하지 않습니다. 정상 proxy의 알려진 EC 공유 footprint는 private Runtime hook에 한정하며, 해당 구간의 동일 보호 순서 근거는 여전히 미완료입니다. 실제 요청·공개 entry·실기 실행은 보류합니다.

**검토 상태: 조건부 제안 작성 완료 / 실제 요청·시험 빌드 연결 보류.** [PI 계약 대조](PI_COMMUNICATION_CONTRACT_REVIEW.md), [A/B 제안](FIXED_MODE_READ_PROPOSAL.md), [응답 거부 명세](FIXED_READ_ACCEPTANCE_SPECIFICATION.md), [오프라인 리허설](READ_TRIAL_REHEARSAL_PLAN.md)을 하나의 흐름으로 묶었습니다. 실행용 command/address·frame·nonce·generator·승인 flag가 없는 문서입니다. 공개 `PrepareSdkAsync`의 `ReadSpecificationUnavailable`과 보호 조회·충전 제어 `Unsupported`를 유지합니다.

## 목표와 대상

읽으려는 것은 고정된 RAM 보호 모드 저장 byte의 **후보값**입니다. 사용자 희망 설정, Windows 배터리 잔량, 충전기에 실제 적용된 상태와 분리합니다.

기존 설정 writer는 값이 달라져서 새 값이1일 때에만80/75임계값을 씁니다. 따라서 단일 저장 후보1을 얻어도 현재 임계값이나 `80% 제한 적용됨`을 확인한 결과로 표시하지 않습니다. A에 추가 조회를 넣지 않습니다.

대상은 보존된 940X3G/930X3G 계열 관측과 BIOS `P05ACJ.128.140819.dg`에 대응하는 CandidateProfile입니다. 모델명 문자열만으로 source 일치나 지원을 인증하지 않습니다. 저장 원본의 선택 read branch, 주소 배치, 조건부 ISA/bank 해석과 host indexed window ↔ EC mailbox 대응을 명시한 모델 전제를 유지합니다. 임의 주소·명령·길이 입력, 다른 모델·BIOS 자동 대체는 없습니다.

보존된 WMI 대상 사실·class/instance/method·입출력 선언을 기존 single-read plan의 exact 비교와 묶습니다. 구체 instance 식별자·전체 경로·계정·장치 고유 ID는 결과에 보고하지 않습니다. 실제 고정 template를 검토하기 전에는 형식만 맞는 임의 payload를 통과시키지 않습니다.

## 호출 예산과 유용성

| 항목 | 기본 안 A |
| --- | --- |
| WMI/OEM method | 고정 읽기 요청 최대 1회 |
| 고정 대상 byte 샘플 | gate·전달 조건에 따라 0~1회 |
| gate handshake, 삼성 DLL/OEM 초기화 | 각각 0회 |
| 재시도, 다른 명령·대상, B fallback | 각각 0회 |
| 보호 설정·충전기 쓰기, 사후 reset | 각각 0회 |

0~1은 고정 byte 샘플 횟수이며 mailbox 접근·ready polling·무관한 EC 활동 전체를 한 번으로 제한한다는 뜻이 아닙니다. source 초기 gate는 닫힘이며 현재 상태는 미관측입니다. gate가 닫혔으면 값을 얻지 못할 수 있습니다. 사전 handshake나 gate-open 실측을 이 안에 추가하지 않습니다. 상태를 바꾸는 별도 B는 실행 보류이며 A 실패 후 대체 실행이 아닙니다.

사용 완료된 과거 단발 예약은 읽거나 초기화·삭제·재사용·우회하지 않습니다. 이 문서에서 새 예약이나 다른 시험 실행 권한을 만들지 않습니다.

## 게시 전에 적용할 보호

| 구간 | 필요한 계약과 보존된 근거 |
| --- | --- |
| 로컬 SDK 입력·target·observer | 기존 exact binding/소유권 계약. 공급 객체의 외부 변경·Dispose·독립 dispatch를 준비부터 관련 close까지 배제합니다. 포장 객체의 형식 검사는 실제 읽기 의미의 대체물이 아닙니다. |
| WM00 입력 저장 전 → 최종 공유 field 읽기·관련 detached 결과 포착 | 확인된 WSABI의 전체 교환 cooperative owner를 적용합니다. 같은 잠금 이름·우리 앱의 단발 slot만으로 비참여자를 포함하지 않습니다. |
| 공유 command/address 준비 → 두 주소 성분의 마지막 소비 | 선택 read template의 branch와 두 성분이 보존되어야 합니다. 사후 보존 내용 일치만으로 과거 입력 무결성을 추론하지 않습니다. |
| EC upload 30byte → 게시·주소 소비·sample → 전체 download 30byte 및 마지막 indexed 접근 | 관련 CPU 게시자를 같은 보호 순서에 귀속시킵니다. 정상 legacy root의 기존 양의 근거를 재사용하고, nonnull 표준 통신에는 적용 가능한 플랫폼 순서 계약을 별도로 명시합니다. PI의 메시지 전달·반환만으로 이 순서를 만들지 않습니다. |
| 기존 작업과 다음 재사용 | 정상 ready admission과 이미 확인한 inline 소비·buffer 분리·ISR 보존을 유지합니다. reader 전/후 clear·오래된 결과는 조회의 안전한 거부로 처리하며 모든 EC 효과 완료를 요구하지 않습니다. |

normal proxy/private wrapper 게시가 성립한 분기에 초기 direct-host 경로를 중복 경쟁자로 남기지 않습니다. 정상 전달·반환과 해당 플랫폼의 초기화 완료·비재진입·동일 실행 영역 가정은 source가 입증한 부분과 구별해 기록합니다. 실제 provider 본문 복구만을 유일한 해법으로 강제하지 않고 동일 보호 순서의 적용 근거를 평가합니다.

관련성이 연결되지 않은 모든 writer/IRQ의 부재, EC 전체 live hash, 새 포인터 수집을 필수조건으로 늘리지 않습니다. 실제 연결된 새 source나 반례가 생긴 구간만 다시 조사합니다.

## 시작·중단·결과 분류

1. **준비:** 검토된 고정 profile/template, 대상 metadata, 정상 토큰 조건, 관련 보호·완료 계약이 있는 경우에만 준비를 검토합니다. 현재 공개 entry는 template 명세 부재로 이 전에 차단됩니다.
2. **획득:** 기존 유한 대기 한도를 적용합니다. 권한 거부·시간 초과·abandoned·불명확 owner·사전 취소면 요청 없이 종료합니다. 권한 상승·다른 잠금 이름·계정 fallback은 없습니다.
3. **게시:** 준비를 한 번 소모하고 입력을 동결합니다. stop이 admission보다 먼저 이기면 미게시 종료합니다. Run에 새 command/payload를 받거나 실패 후 다시 준비하지 않습니다. 이 plan 참조의 제한을 프로세스 전체의 영구 보안 경계로 부르지 않습니다.
4. **회수:** 관련 실제 완료와 보호 계약 안에서 detached 결과를 분류합니다. API/method·shape/ACK 오류, 기존 실패 prefix, 입력 echo, 보존 성분/내용 불일치, 허용 후보값 밖, gate 거부·FF·귀속 불명은 모두 **판정불가**이며 추가 호출은 없습니다.
5. **후보 표시:** 고정 대상·입력 보호·정상 반환 형식과 관측 거부 규칙을 함께 만족하는 경우만 저장 모드 후보로 표시할 수 있습니다. 실제 충전 적용은 **Unknown**, 제어는 **Unsupported**로 남깁니다.

8개 보존 셀의 독립·균등 nonzero 단발 비교는 [응답 명세](FIXED_READ_ACCEPTANCE_SPECIFICATION.md)의 조건부 old-content 충돌 모델을 따릅니다. 이는 수용 결과가 틀릴 확률이나 성공 신뢰도가 아닙니다. 다른 생산자·replay·혼합 회수·입력 불안정을 이 확률로 덮지 않습니다. 값이나 generator는 만들지 않았습니다.

## 표시 시간과 실제 종료·정리

UI deadline은 기다림의 표시 한도이며 provider 중단이나 안전한 해제를 뜻하지 않습니다. SDK 즉시 반환·throw·사용자 취소만으로 terminal을 생성하지 않습니다. 확실한 사전 미진입은 해당 local 분기로 따로 끝낼 수 있습니다.

실제 진입한 호출은 call stack 반환, 해당 method에 적용되는 terminal, 선택 capture 접근 종료를 함께 기다립니다. FrameExchange의 late 결과·취소 callback worker, Windows handler 접근·구독 해제 시도·출력 정리, owned 입력 해제, owner thread의 lease 해제를 기존 수명 계약으로 join합니다. 입력은 parameters와 buffer를 각각 정리하며 borrowed target을 소유 대상으로 바꾸지 않습니다.

종료 불명이면 판정불가 표시 뒤에도 관련 Run/Close는 pending일 수 있습니다. 새 호출·자동 재시작·SDK Cancel·잠금 조기 해제를 넣지 않습니다. 오프라인 리허설의 합성 terminal/cleanup은 가짜 source의 정리 수단이며 실기 코드로 옮기지 않습니다. 독립 SDK 내부 정리나 모든 EC 활동 종료까지 무조건 기다리라는 조건은 아닙니다.

## 남은 적용 검토와 사용자 작업

이 명세로 **실행 여부를 검토할 구체 제안**은 갖췄습니다. [적용 검토](FIXED_READ_APPLICABILITY_REVIEW.md)는 source의 대상 역할·주소 공간·조건부 모델과 실제 대상 SDK API 문서를 대응시켰습니다. 실제 요청 template를 생성한 결과는 아닙니다. 남은 구체 순서 근거는 관련 private Runtime hook의 indexed 접근을 조회와 같은 보호 순서에 귀속시키는 계약입니다. 실제 연결 전에는 이 근거와 고정 template·SDK 수명 적용 결과를 함께 제시해야 하며 현재 결과를 준비 완료로 표시하지 않습니다.

커널/펌웨어 제어 코드의 추가와 실기 호출은 이번에 수행하지 않았습니다. [AGENTS.md](AGENTS.md)의 별도 명시 승인·안전성/모델 적합성 조건을 유지합니다. 지금 승인을 요구하거나 사용자에게 새 프로그램 실행·같은 진단·DLL·TXT 재제출을 요구하는 단계는 아닙니다. 제품 코드·노트북용 EXE/ZIP 변경도 없습니다.
