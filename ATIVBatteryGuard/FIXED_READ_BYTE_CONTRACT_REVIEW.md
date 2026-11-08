# 고정 읽기 후보의 요청·응답 바이트 계약 — 2026-11-08 한국 시간

**선택한 generic callback과 EC byte reader 사이의 바이트 대응을 합성해, 현재 입력 주소와 반환 sample을 함께 다룰 후보 분기를 하나로 좁혔습니다.** 공통 실패와 명령 전용 분기에서도 sample 자리가 0이 될 수 있어, sample 하나만 읽어 저장 모드 후보로 해석할 수 없다는 관계도 확인했습니다. 실제 읽기 요청 명세를 완성하거나 공개 entry를 연 것은 아니며 충전 제어는 Unsupported입니다.

[실기 진입 조건](READ_TRIAL_ENTRY_CONDITIONS_UPDATE.md)의 후속입니다. 보존된 원본을 데이터로 읽고 기존에 개별 확인한 본문들을 합성했습니다. 새 firmware 함수/edge 발견은 0개이며 기존 byte reader·echo-domain 분석을 새 발견으로 세지 않습니다. 실제 노트북·SDK/OEM 호출이나 요청/주소 조합·frame·nonce 생성은 없습니다.

## 요청에서 reader로 이어지는 선택 범위

Windows method ID, SABI 분배 selector, generic callback 분기, EC command는 각각 다른 층입니다. callback의 전송 방식만 정했다고 EC의 읽기 handler를 선택한 것이 되지는 않습니다. 기존 conditional ISA/bank 모델과 host indexed window↔EC mailbox 대응 가정 아래 다음 관계를 확인했습니다.

| 선택 callback의 분기 | 현재 주소 입력과 반환의 관계 |
| --- | --- |
| 입력 upload + 응답 수신 | 현재 입력 data를 메시지에 복사하고 반환 data도 WMI에 복사합니다. 이 세 분기 중 현재 두 주소 성분과 반환 sample을 함께 제공할 후보입니다. 남은 무결성/실행 전제를 충족한 것은 아닙니다. |
| zero-message 실행 + 수신 | 현재 주소 data를 복사하지 않습니다. 새 게시·선택 reader·주소 공간 대응 전제 아래 두 주소 성분은 zero-message의 값이므로 고정 mode 저장소를 현재 입력으로 선택하지 못합니다. 첫 send 생략/stale 가능성은 별도입니다. |
| command-only | WMI 응답 data 복사를 건너뜁니다. sample 자리는 입구 clear의 0으로 남으며, EC 내부에서 무엇이 실행되었는지와 별개로 현재 입력의 독립 read-back 경로가 아닙니다. |

이 선택 callback 범위의 제외 결과이며 다른 모든 firmware/driver 경로의 부재를 주장하지 않습니다. 어느 분기도 이름만으로 read-only라고 판정하지 않습니다.

주소 helper는 첫 성분을 high, 둘째를 low로 사용합니다. 바깥 header의 UInt16LE 규칙을 payload 주소 성분에 확대하면 다른 대상을 고를 수 있습니다. header를 만드는 기존 C# encoder는 payload byte 순서를 그대로 복사합니다. 실제 대상 주소나 실행용 byte 조합은 작성하지 않았습니다.

## 응답으로 돌아오는 필드

아래 번호는 물리 주소가 아닌 **0부터 시작하는 응답 buffer의 상대 위치**입니다. 현재 보수적으로 지원하는 전체 21byte/payload 16byte 범위와 선택 source의 정상 data-return 분기에 한정합니다.

| 역할 | WMI payload 위치 | 합성한 source 관계 |
| --- | --- | --- |
| generic 제어 두 셀 | 0..1 | 입구에서 지우며 정상 data-return copy가 복원하지 않음 |
| 첫 주소 성분 → sample | 2 | reader가 첫 메시지 셀을 결과 한 byte로 대체. 전체 frame의 상대 위치 7 |
| 둘째 주소 성분 | 3 | 선택 reader 본문에서는 보존됨 |
| 그 밖의 메시지 보존 내용 | 4..11 | 반환되는 메시지 안의 8개 셀. 전송 보존 가능 위치이며 신선함/nonce 안전성 인증은 아님 |
| 보이는 WMI 뒤 4개 셀 | 12..15 | 입구 clear 뒤 반환 copy 범위 밖이라 복원되지 않음 |

따라서 EC 메시지 꼬리의 보존을 WMI payload 16byte 전체의 보존으로 확대할 수 없습니다. WMI 뒤 4byte에 별도 내용 표식을 두면 이 선택 경로에서 소실됩니다. 새 표식·nonce·검증 parser는 만들지 않았습니다.

## 실패의 0과 실제 sample의 0

공통 provider 실패 분기는 payload 0에 실패 marker를 쓰고 나머지를 지웁니다. 선택 reader의 sample 투영은 payload 2이므로 **실패 응답의 sample 자리도 0**입니다. source는 그 실패에도 ACK를 쓰고 source zero를 반환합니다. 이를 Windows HRESULT/ReturnValue와 직접 같은 값으로 식별한 것은 아닙니다.

정상 mapper 계약 아래 이 자료가 지원 응답 크기로 노출될 때, 미래 consumer가 길이·ACK와 sample 0/1만 수용하면 실패의 zero를 좁은 저장 모드 후보 zero로 오인할 수 있습니다. 현재 `WsabiWmiReplyResult`는 이미 `DispatchFailurePrefix.MatchesAnalyzedP05AcjPrefix`를 표시합니다. 현재 제품에는 저장 mode decoder가 없고 실제 entry도 차단돼 있으므로 **제품 오류나 실기 false-OFF를 발견한 결과는 아닙니다.**

향후 sample 해석 전에는 기존 실패 prefix 표시를 무시하지 않고 판정불가로 끝내야 합니다. 반대로 prefix가 다르거나 정상 제어 두 셀이 zero여도 새 읽기의 증거는 아닙니다. command-only 성공도 sample 자리가 0이고, 첫 send 오류 가림·다른 생산자·입력 변경이 남습니다. 좁은 0/1 후보 밖의 값을 자동으로 OFF로 바꾸지도 않습니다. prefix는 선택 원본과의 패턴 비교이며 특정 실패 원인·미게시·driver 부재를 식별하지 않습니다.

## 남는 입력 보호·귀속 조건

사후에 둘째 주소 성분이나 8개 보존 셀이 맞아도, 따로 소비된 주소 두 성분이 읽는 동안 안정적이었다는 뜻은 아닙니다. 새 게시 여부·의도한 reader 실행·반환값의 생산자 귀속도 이 비교로 인증하지 않습니다. 이 제한과 알려진 worker 입력의 inline 소비·영역 분리, ISR 보존은 기존 근거 그대로입니다.

host indexed window와 EC mailbox가 대응한다는 가정, 조건부 ISA/bank와 현재 이미지 적합성, 관련 참여자의 command/address·입력 준비~응답 회수 보호, 마지막 결과 쓰기/clear와 다음 재사용 계약을 계속 명시해야 합니다. 모든 writer/IRQ 부재·현재 EC 전체 hash·gate-open 실측을 새 절대조건으로 요구하지 않습니다. A의 handshake/초기화/재시도/쓰기/B fallback 0과 gate 미관측의 유용성 한계는 유지합니다.

## 검증과 변경 범위

| 정적 검산 | 합성 관계 | 재사용 원본/문맥 검사 |
| --- | ---: | ---: |
| 요청·분기·주소/응답 위치 | 8 | 39 |
| 실패 marker와 sample 투영 | 10 | 29 |
| root의 별도 parser/정적 decode·관계 검산 | 15 | 20 |

검사들은 서로 겹치므로 합산한 고유 발견 수가 아닙니다. 앱 단위 테스트·새 함수 수·firmware 분석률로도 세지 않습니다. PE/CAP와 그 내부 EC slice의 길이·SHA를 검산했고, stdlib PE section 파싱과 기존 trusted pefile/Capstone을 사용한 별도 검산 모두 통과했습니다. 원본은 실행·로드·에뮬레이션하지 않았습니다. 최초 affine verifier의 명령 displacement byte index 오류 1건을 수정한 기록은 제품/원본 오류와 구분했습니다.

[정제 기록](reports/fixed-read-byte-contract-audit.json)에 source/검산 artifact 해시와 범위를 남겼습니다. raw 주소·기계어·실행 조합은 private cache에만 보관합니다. 앱·테스트·SDK/Core 코드·기존 ZIP은 바꾸지 않아 빌드/C# 회귀를 재실행하지 않았습니다. **617개 통과·net48 Release 경고/오류 0은 이전 62f2d2e의 검증 기록**입니다.

공개 SDK entry의 ReadSpecificationUnavailable, 실제 보호 조회·제어 Unsupported는 유지합니다. 실제 WMI/OEM/하드웨어/Global 객체·삼성 원본 실행·소모 예약·드라이버/서비스/보안/펌웨어·클라우드 환경 변경은 없고 새 실행 파일·노트북 시험·자료 제출은 필요하지 않습니다.

다음은 위의 좁혀진 field/분기 계약에 실제 관련 참여자의 입력 안정성과 새 게시·응답 귀속을 연결하는 일입니다. 문서의 조건부 바이트 대응을 실기 명세 완성이나 실행 승인으로 바꾸지 않습니다.
