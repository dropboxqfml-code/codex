# 통신 제공자 후보와 역방향 호출 조사 — 2026-11-08

**이번 조사에서도 실제 표준 제공자 함수→typed SMM dispatch 연결은 확보하지 못했습니다.** [부팅 후 중계 검토](RUNTIME_POSTBOOT_TRANSPORT_REVIEW.md)의 후속으로, 같은 GUID 검색 대신 실제 게시 객체의 함수 공급원, 수신 측의 역방향 호출 후보, PE index 밖의 자료를 대조했습니다. 새 제공자나 실기 성공을 보고하는 문서가 아닙니다.

## 실제 게시 객체에서 제외한 후보

SmmBase가 실제로 게시하는 Base2 객체의 method0은 정적 표에 고정된 함수가 아니라, 초기화 중 복사하는 28바이트 본문에서 공급됩니다. 원본의 할당→복사→두 method slot 저장→실제 GUID/interface 게시 인수를 연결했습니다.

그 전체 본문은 출력 포인터를 검사하고 한 byte를 쓴 뒤 반환하는 **InSmm**입니다. 전달·dispatch·SMI trigger 호출이 없으며, 같은 함수가 legacy InSmm slot도 공급합니다. 따라서 이 특정 동적 method0을 표준 Communicate 후보에서 제외합니다. 인수 개수나 method0이라는 위치만으로 판정한 것이 아닙니다. 원본의 코드 복사를 분석했을 뿐, 검사기가 실행 가능한 메모리에 그 코드를 로드·복사·실행·에뮬레이션하지 않았습니다.

## typed dispatcher에서 거슬러 찾은 호출 후보

기존 231개 pinned PE의 executable raw section에서 native manage slot과 같은 displacement의 호출·jump operand를 역검색했습니다. 이는 예전 GUID literal/split 검색과 다른 탐색입니다.

- 호출·jump 후보 6개는 모두 USBRT의 계산된 indexed record 접근이었습니다. base도 별도 조회 객체의 field에서 공급됩니다. native SMST getter에서 온 receiver라는 연결은 없습니다.
- 따라서 같은 slot offset이라는 이유로 이 6개를 SmiManage 호출로 인정하지 않습니다. 실제 target 값과 USB 코드 전체를 해명하거나 해당 호출의 SMM 도달이 불가능하다고 증명한 것은 아닙니다.
- SmmDispatcher 자기 함수로 향하는 직접 호출은 기존 NULL-type 순회였습니다. 이를 nonnull GUID 선택으로 승격하지 않습니다.

탐색은 executable section의 선형 skip-data decode와 직접 operand 모양에 제한됩니다. 계산된 다른 slot·별칭·저장 후 register 호출·미인식 코드 경계·외부 공급자는 닫지 못했습니다. 후보가 없거나 receiver가 미연결이라는 결과는 전역적인 제공자 부재의 증명이 아닙니다.

## 자료 범위와 기존 nested EFI application

기존 section tree와 231개 PE index의 payload hash multiset이 일치함을 교차 확인했습니다. 7FV·표준 압축 section 390개에 대한 이전 coverage를 재사용했으며 이번에 다시 압축 해제한 것은 아닙니다.

추가로 index 밖의 비PE 추출 출력 252개, RAW/PAD body 21개, CAP carve gap 1개를 검사했습니다. **274개 기록은 겹치는 영역**이며 독립 이미지 274개가 아닙니다. 이 범위의 연속 GUID·bounded PE/TE 후보 선택에서는 새 제공자 단서나 누락 실행 section을 찾지 못했습니다. 변환·암호화·계산된 등록 등은 배제하지 않습니다.

이미 알려진 SecLoJack 내부 후보 중 하나는 AMD64 **EFI application**입니다. 이름이나 다른 nested Windows 이미지 때문에 Windows-only로 제외하지 않았습니다. 이 payload는 과거 outer 파일 전체의 literal 검색에는 이미 포함됐지만 231개 독립 이미지의 machine/section decode 단위는 아니었습니다. 별도 범위를 검사한 결과, 선택된 protocol lookup은 다른 구체 protocol을 요청하며 이번 대상 객체로 연결되지 않습니다. 해당 app의 모든 계산된 게시 경로가 없다고 주장하지 않습니다. 원본 payload는 private cache에만 둡니다.

## 수신 인수에 대한 불필요한 조건 제거

완전한 Nvram typed wrapper와 그 짧은 server body를 대조했습니다. wrapper는 callback으로 전달된 context/data/size 인수를 소비하지 않습니다. server는 자신의 **retained SMM buffer**를 다시 읽고, 하위 변수 호출의 모든 인수를 그 버퍼에서 구성하며 결과 status도 거기에 씁니다.

따라서 provider의 incoming data 인수가 retained buffer와 같은 포인터여야만 이 server 입력을 설명할 수 있다는 추가 조건은 필요하지 않습니다. native dispatcher가 인수를 전달한다는 사실만으로 header 파싱·retained buffer 공급을 입증할 수도 없습니다.

이 구분은 handler 선택을 닫지는 않습니다. 실제 nonnull GUID 선택·그 호출의 실행 영역, retained slot의 유효성·client/server의 공유 자료 관계·의도한 private 변수 wrapper 게시 성공은 기존의 별도 전제입니다. 이번 refinement를 새로운 제공자 연결이나 live 안전성 증명으로 세지 않습니다.

## 현재 판정과 재조사 범위

| 범위 | 판정 |
| --- | --- |
| Base2의 실제 동적 method0 | InSmm 본문으로 후보 제외 |
| 역검색의 호출 후보 6개 | native SMST receiver 연결 없음. typed 호출로 수용하지 않음 |
| index 밖 추가 자료·기존 nested EFI app | 이번 방식에서 새 공급자 근거 없음. 부재의 증명 아님 |
| 수신 buffer 인수와 retained buffer의 alias | 해당 server가 쓰지 않는 인수이므로 추가 요구에서 제거 |
| 실제 표준 객체.method0→nonnull GUID dispatch | 미연결 유지 |

정상 proxy + NULL cache의 기존 legacy fallback 순서는 유지합니다. nonnull 분기의 미연결을 direct-host 게시자나 실제 race로 바꾸지 않으며, 모든 경로에 표준 제공자 복구를 추가 조건으로 요구하지 않습니다. 정상 API 제공자가 메시지를 전달한다는 설계 가정도 P05의 특정 root/CPU 순서·host 전후 처리와 indexed 자원 사이의 비간섭을 복구한 소스 근거와 구분합니다.

이번 후보군·operand 검색·자료 범위를 동결합니다. 같은 검색을 반복해 새 진전으로 세지 않고, **구체적인 새 게시 객체·실제 함수 공급원·nonnull 선택 caller 또는 새 실행 자료**가 나올 때 해당 범위만 다시 엽니다. 현재 자료로 이 미연결을 해결했다고 표시하거나 시험용 backend를 활성화하지 않습니다.

## 검증과 변경 범위

게시 후보 검산은 source 27행·완전한 inert template 28바이트, 역방향 후보 검산은 원본 pin 3개·선택 단언 16개·bounded decode 122행을 통과했습니다. inventory 교차 검산과 root의 별도 handler/server·nested source 검산도 통과했습니다. [정제 기록](reports/communication-provider-candidate-audit.json)에 범위·해시·실행 여부를 남깁니다. 검사 수는 겹치며 앱 테스트·새 firmware 함수 수·분석률로 합산하지 않습니다.

실제 제공자→typed dispatch의 새 연결·새 제공자·실기 race 발견은 0입니다. C#/SDK/프로젝트·앱·기존 EXE/ZIP은 변경하지 않아 빌드/C# 테스트는 재실행하지 않았습니다. 617개·빌드 경고/오류 0은 62f2d2e의 이전 기록입니다.

공개 ReadSpecificationUnavailable·보호 조회/제어 Unsupported, A의 호출 상한·handshake/초기화/재시도/쓰기/B fallback 0, 과거 소모 예약 접근·재사용 금지를 유지합니다. 원본 실행·실행 코드 로드·에뮬레이션, SDK/OEM/하드웨어/Global 객체 접근, 드라이버/서비스/보안/펌웨어·클라우드 환경 변경, 실제 요청·주소 조합·frame·nonce/생성기 추가는 없습니다. 추가 노트북 실행·같은 파일 재제출도 요구하지 않습니다.
