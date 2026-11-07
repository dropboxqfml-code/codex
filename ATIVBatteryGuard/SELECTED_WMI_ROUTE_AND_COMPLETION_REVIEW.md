# 선택 WMI 경로와 gate·완료 계약 — 2026-11-07

**조회 진입 경로와 별도 Runtime 변수 경로를 분리해, 조회에 잘못 합쳐질 수 있던 조건을 정정했습니다.** 선택 WMI 조회의 펌웨어 callback까지는 저장 소스에 연결 근거가 있습니다. 표준 typed 통신 제공자의 미연결을 조회 진입 자체의 필수조건으로 두지 않습니다. 실제 보호 설정 조회·충전 제어 성공을 확인한 것은 아니며 제어는 Unsupported입니다.

[이전 완료 경계 검토](PROVIDER_COMPLETION_AND_READ_TRIAL_REVIEW.md), [시험안](FIXED_MODE_READ_PROPOSAL.md), [판정](FIXED_MODE_READ_DECISION.md)의 후속입니다. 새 실기 호출 대신 보존한 소스의 경로 대응과 Microsoft 공식 WMI API 계약을 검토했습니다.

## 두 경로의 역할

| 구분 | 저장 소스에서 연결한 경로 | 이번 판단 |
| --- | --- | --- |
| 선택 WMI 조회 | WMI method → AML method → software trigger → 해당 PCH legacy SW 등록 → SABI dispatcher → generic callback | 조회 진입의 경로 근거로 유지. 현재 장치의 등록·전달 성공 관측과는 구분 |
| Runtime 변수 서비스 | host SetVariable proxy → 선택 통신 interface 또는 별도 legacy fallback → 변수 서비스 handler → 관련 EC 후크 | 표준 typed interface의 미연결은 이 분기의 문제. 관련 EC 게시자의 실행 순서·입력 보존에 영향을 주는 범위만 조회와 함께 평가 |

첫 경로는 이전에 확보한 WMI 매핑·AML·등록·callback 근거를 대조한 것입니다. Windows provider의 method→AML 평가→반환 객체 생성 계약을 이번에 새로 확보했다는 뜻은 아닙니다. 새로운 통신 제공자를 발견하거나 과거 모든 미연결을 해소했다고 세지 않습니다. 두 번째 경로의 존재를 충전 보호 설정용 Windows API의 증거로 삼지도 않습니다.

## gate를 여는 호출과 조회의 구분

저장된 Samsung Settings의 keyboard/jog 기능 caller에는 조건을 만족할 때 조회 함수가 local handshake를 먼저 호출하고, API·응답 서명을 확인한 뒤 generic query로 진행하는 순서가 있습니다. 초기화 함수의 성공 반환만으로 이 handshake가 실행됐다고 할 수 없습니다. 이는 **해당 caller의 gate 사용 순서**이며 배터리 명령이나 현재 노트북의 실행 상태 증거는 아닙니다.

handshake는 gate의 image-data 값을 열고 고정 응답을 돌려주는 별도 호출입니다. query 뒤에 이를 실행해도 직전 query 당시 gate 상태·실제 EC 실행·응답의 신선함을 소급 인증하지 못합니다. 따라서 확인용이라는 이유로 사후 handshake를 추가하지 않습니다.

[현재 시험안](FIXED_MODE_READ_PROPOSAL.md)의 상한은 계속 **WMI 읽기 시도 최대1회·고정 대상 byte 샘플0~1회·handshake/초기화0회**입니다. gate가 닫혀 있어 값을 얻지 못할 수 있다는 유용성 제한을 유지합니다. gate를 여는 호출까지 포함한 다른 안은 호출 수와 상태 영향을 명시해 별도로 검토해야 합니다.

## 정상 완료와 클라이언트 취소

Microsoft의 ExecMethodAsync·SetStatus·CancelAsyncCall 문서3개를 텍스트로 읽고 해시와 선택 관계6개를 검산했습니다. 원문은 private cache에, 출처·해시·한계는 [정제 기록](reports/selected-wmi-route-completion-audit.json)에 남겼습니다.

- 비동기 API의 즉시 반환, Indicate로 받는 출력·method ReturnValue, SetStatus의 최종 상태는 서로 다릅니다.
- COMPLETE flag와 성공 HRESULT를 함께 구분해야 합니다. 정상 최종 성공은 API 작업 완료의 유용한 근거이며 관리 객체 전체 정리가 끝났다는 뜻으로 확대하지 않습니다.
- method의 CancelAsyncCall은 클라이언트 측을 취소하며 provider에 취소를 통지하지 않습니다. WMI가 취소 상태의 SetStatus를 생성할 수도 있으므로 취소 알림을 provider 정지로 해석하지 않습니다.

이는 공개 API 계약이며 현재 Windows10/.NET48 내부 구현이나 실제 AML/EC 종료를 직접 관측한 자료가 아닙니다. 기존 단발 backend는 observer.Cancel을 호출하지 않고 기존 experiment는 취소 없는 토큰을 사용합니다. 과거 실기에서 이 취소 동작이 발생했다고 추정하지 않습니다.

## 공유 교환 완료의 좁은 경계

선택 AML은 입력 준비 → trigger helper → 공유 응답 반환 순서입니다. 선택 dispatcher와 generic callback의 send/wait/download/copy는 확인한 호출 스택 안에 있고, 선택 SMI thunk는 callback 반환 뒤 복귀합니다. 이 소스 순서를 독립 SDK cleanup 전체나 모든 EC 활동의 정지 요구로 바꾸지 않습니다.

host WMI 공유 프레임과 EC command/data mailbox도 구분합니다. 선택 callback은 host 입력을 local snapshot으로 읽고 EC에 업로드한 뒤, local download를 host 응답으로 복사합니다. 확인한 closure에는 EC로 host 프레임 포인터를 넘기거나 callback 반환 뒤 그 프레임에 다시 쓰도록 예약하는 경로가 없습니다. EC의 후속 진행 가능성만으로 host 프레임 소비도 계속된다고 하지 않습니다.

반면 그 thunk만으로 현재 trigger의 전달·응답 시점을 관측했다고 할 수 없습니다. 필요한 것은 선택 source·아키텍처의 정상 전달과 미게시·지연·생략 분기에서, 완료 통지·소유권 해제·재사용 전에 **관련 입력의 마지막 소비와 응답 쓰기/회수가 끝났거나 애초 게시되지 않았다는 계약**입니다. host 프레임에서는 callback 마지막 접근과 AML 응답 회수를, EC mailbox에서는 첫 준비 실패의 미게시/stale와 게시 후 다음 입력 재사용을 각각 평가합니다. 무효 응답을 거부했다는 사실만으로 남은 공유 접근이 종료되지는 않습니다. Task 취소·process 종료·잠금 해제를 provider 정지로 해석하거나 현재 장치 trace·모든 IRQ 해명을 새 절대조건으로 추가하지 않습니다.

실제 연결 전에는 선택 경로/대상/gate·관련 교환 참여 규약·관련 완료/입력 비훼손/응답 귀속의 세 묶음을 유지합니다. 이번에는 조회 진입과 별도 변수 경로를 분리하고, 정상 반환·취소·source 순서가 각각 뒷받침하는 범위를 명확히 했습니다. 실기 backend·프레임·표식 값·초기화·새 시험은 추가하지 않았습니다.

## 검증과 제공 범위

문서와 정제 기록만 변경했습니다. 앱/Core·테스트·EXE·배포 ZIP은 그대로이며 전체 빌드·단위 테스트는 반복하지 않았습니다. C#463개·전체 빌드 경고/오류0은 이전1790a4b 기록입니다. 이번 소스 검산·공식 문서 텍스트 검산은 앱 테스트 수나 펌웨어 분석률에 합산하지 않습니다.

원본 코드 실행·로딩·에뮬레이션, 실제 WMI/OEM·하드웨어·사용 완료된 실기 예약 접근, 드라이버·서비스·보안·펌웨어 변경은 없습니다. 새 노트북 실행이나 동일 자료 제출은 필요하지 않습니다.
