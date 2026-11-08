# 고정 읽기의 입력 보호와 응답 포착 경계 — 2026-11-08 한국 시간

**ready가 된 시점과 응답을 안전하게 복사한 시점은 다릅니다.** [바이트 계약 검토](FIXED_READ_BYTE_CONTRACT_REVIEW.md)에 기존 sender/receiver·EC reader·Windows 협력 규약을 연결해, 입력 안정성과 응답 보존에 필요한 구간을 구체화했습니다. 새 handler나 실제 경합을 발견한 결과는 아니며 실제 보호 조회·충전 제어는 Unsupported입니다.

저장된 원본을 데이터로 읽은 정적 합성입니다. 새 함수/edge는 0개이고 실제 요청·주소 조합·frame·nonce를 만들지 않았습니다. 공개 SDK entry의 ReadSpecificationUnavailable도 유지합니다.

## ready 이후에도 남는 응답 보호

선택 sender는 ready를 확인한 뒤 입력을 upload하고 command를 게시합니다. 정상 reader 경로에서는 주소 성분 두 개의 소비와 sample 쓰기 뒤 dispatcher가 command를 clear합니다. receiver는 그 뒤 ready를 확인하고 EC data를 host-local buffer로 순서대로 복사합니다.

같은 ready 규약의 다음 sender도 clear 이후 upload에 진입할 수 있습니다. **ready 검사만으로 다음 upload가 현재 응답 복사보다 뒤에 온다는 순서는 생기지 않습니다.** 따라서 pending 입력 보호와 완료 후 응답 회수 보호를 분리해야 합니다. 이는 보호 전제가 없는 부분순서에서 허용되는 관계이며, 현재 장치에 그런 actor나 race가 있다는 관측은 아닙니다.

기존 첫 send 오류 가림·stale copy, reader 전 clear의 입력 echo, reader 후 clear의 sample 보존은 재사용한 맥락입니다. clear를 독립적인 완료 번호나 전체 소유권 양도로 바꾸지 않습니다. 알려진 worker의 inline 입력 소비·영역 분리와 ISR register 보존도 다시 미해결로 만들거나 새 발견으로 세지 않습니다.

## 세 가지 범위

아래 수치는 물리 주소가 아닌 선택 메시지 buffer의 길이입니다.

| 범위 | 연결한 source 관계 | 보호의 의미 |
| --- | --- | --- |
| 입력 upload 30바이트 | 선택 sender는 메시지 전체를 씀 | 반환 데이터가 10바이트라는 이유로 기존 작업에 대한 쓰기 영향 범위를 10바이트로 줄일 수 없음 |
| 반환에 쓰는 앞 10바이트 | receiver가 먼저 host-local에 복사하고 callback이 이 10바이트를 WMI에 반영함 | sample과 보존 내용을 함께 판단하려면 이 전체 prefix를 같은 결과로 포착해야 함 |
| 전체 download 30바이트 | 뒤 20바이트의 local 쓰기는 앞 10바이트를 덮지 않음 | 반환 데이터의 local 포착 경계와 indexed selector/port의 마지막 접근 경계는 다름. 앞 10바이트만 복사했다고 자원을 조기 해제하지 않음 |

앞 10바이트가 local에 들어간 뒤에는 선택 receiver의 뒤 20바이트 저장이 그 결과를 다시 쓰지 않습니다. 이 국소 성질을 다른 alias나 host 공유 frame의 불변성으로 확대하지 않습니다. 기존 실제 전송 코드의 수명을 줄이는 변경도 없습니다.

## 관련 참여자별 보호 구간

| 재사용하는 근거 | 조건부로 덮는 구간 | 그 근거만으로 덮지 않는 구간 |
| --- | --- | --- |
| 정상 초기화·비재진입의 같은 SMM 실행 domain | 관련 SMM 게시자가 현재 callback의 EC upload/download 사이에 끼어들지 않는 순서 | SMM 밖 WM00 입력 저장·최종 공유 frame 읽기, 다른 domain의 직접 접근 |
| 정상 획득한 네 WSABI 원본의 같은 Global 협력 mutex | 참여 호출자의 입력 준비부터 method 실행·응답 복사까지 전체 교환 | 규약에 참여하지 않는 native·직접 WMI/ACPI·펌웨어 경로 전체 |
| EC zero-ready admission | 규약 sender가 nonzero인 pending command를 기다림 | 검사와 게시 사이의 예약, ready 이후 아직 복사 중인 결과의 보호, 특정 reader 완료 identity |

같은 SMM 순차화는 EC copyout을 조건부로 보호하지만, WM00의 마지막 공유 frame 읽기는 SMM 반환 뒤입니다. 다음 host 입력 저장과 그 읽기의 순서를 같은 SMM 근거 하나로 정할 수 없습니다. 반면 실제 참여자가 정상적으로 전체 교환 잠금을 보유하면 private 응답 복사 뒤 해제까지 보호하고 다음 협력 호출자의 입력 준비를 뒤로 보낼 수 있습니다.

Field Lock과 trigger 안의 AML mutex는 이 전체 구간을 자동으로 보호하지 않습니다. 기존 native 경로는 다른 잠금 규약이며, Runtime의 보존된 게시 경로를 실제 Windows 경합으로 관측한 것도 아닙니다. 실제 관련 참여자의 가입·순서가 미확정인 부분을 명시하며 모든 writer/IRQ의 전역 부재를 새 조건으로 요구하지 않습니다.

## 이번 읽기라는 판정에 적용할 계약

성공 후보를 받아들일 때에는 다음 연결이 함께 필요합니다.

1. 고정 대상·선택 reader·현재 모델 적용 가정 아래, 입력 준비부터 주소 두 성분의 마지막 소비까지 command/address가 보존되어야 합니다. 사후 둘째 성분·보존 내용 일치로 이 과거 구간을 대신하지 않습니다.
2. 이전 관련 작업의 마지막 입력 소비와 늦은 clear·결과 쓰기를 구분하고, 현재 upload 30바이트와 다음 재사용이 그 작업을 훼손하지 않아야 합니다. 알려진 분리된 worker를 계속 pending 입력 소비자로 가정하지 않습니다.
3. 현재 결과의 필요한 prefix가 local로 포착되고 최종 WMI 응답을 회수할 때까지 관련 재게시·공유 입력 쓰기를 순서화해야 합니다. 실제 indexed I/O의 마지막 접근까지 자원 보호도 유지해야 합니다.
4. 첫 send 생략/stale, reader 전 clear/echo, 실패 prefix·구조 오류·귀속 불명은 저장 모드 후보 성공에서 제외해야 합니다. 정상 prefix·sample 0/1·보존값 일치만으로 새 게시나 reader 실행을 인증하지 않습니다.

위 항목은 명확한 실패를 허용하는 계약입니다. 모든 시도의 성공·fresh 응답을 요구하지 않습니다. 이번 정적 합성은 실제 관련 참여자의 가입, 두 주소 성분의 실기 안정성, 새 게시·선택 reader 실행을 새로 관측하거나 인증하지 않았습니다. 입력 보호와 응답 분류를 함께 적용할 실제 고정 읽기 명세는 여전히 미완료입니다.

host indexed window↔EC mailbox 대응·조건부 ISA/bank·현재 이미지 적용 가정과 A의 gate 유용성 한계는 유지합니다. gate-open 실측·전체 live hash·모든 IRQ의 해명을 새 절대 시작 조건으로 두지 않습니다. handshake/초기화/재시도/쓰기/B fallback이나 과거 소모 예약의 재사용도 없습니다.

## 검증과 변경 범위

담당별 byte/정적 decode·footprint 검산과 root의 별도 parser·부분순서 검산을 실행하고 독립 읽기 검토했습니다. [정제 기록](reports/fixed-read-input-capture-audit.json)에 원본과 검산 artifact 해시, 검사 범위·겹침·한계를 남깁니다. 같은 source body를 사용한 검사 수는 합산한 발견 수·앱 테스트·분석률이 아닙니다. 부분순서 검사는 명시한 성공 경로와 보호 전제의 귀결이며 실기 참여 증명이 아닙니다.

기존 DSDT 파생 텍스트는 검토된 맥락으로 재사용했으며 이번에 AML과의 파생 관계를 재증명하지 않았습니다. root 검산기의 DSDT 길이 상수 오기 1건은 실제 길이·ACPI header·기존 SHA로 수정한 뒤 통과했습니다. 원본 불일치나 제품 오류가 아닙니다.

코드·테스트·기존 EXE/ZIP을 바꾸지 않아 빌드/C# 테스트는 재실행하지 않았습니다. 617개 통과·net48 Release 경고/오류 0은 이전 코드 커밋 62f2d2e의 기록입니다. 실제 SDK/OEM/하드웨어/Global 객체·소모 예약 접근, 삼성 원본 실행·로드·에뮬레이션, 드라이버/서비스/보안/펌웨어·클라우드 환경 변경은 없습니다. 새 노트북 실행·자료 제출은 필요하지 않습니다.

다음은 이 세 보호 구간을 고정 조회안의 실제 관련 참여자와 대응시키고, 새 게시·선택 reader 실행이 불명확한 응답의 거부 조건을 실행용 byte 조합 없이 명세로 묶는 일입니다. 조건부 순서 검산을 실기 승인이나 공개 entry 활성화로 바꾸지 않습니다.
