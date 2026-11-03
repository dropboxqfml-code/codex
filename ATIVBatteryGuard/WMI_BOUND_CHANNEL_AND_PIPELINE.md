# WMI 메모리 채널 연결과 통합 검증 — 2026-11-03

## 이번 개발 범위

[노트북에서 확인한 클래스 형식](WMI_MATCHED_BINDING_AND_OFFLINE_ENVELOPE.md)을 바탕으로 개별 구현된 요청 인코더·비동기 조정기·메서드 바인더·응답 디코더를 하나의 경로로 연결했습니다. 새 WsabiWmiBoundFrameChannel은 명시적으로 주입한 메모리 snapshot transport만 사용합니다. 기본 transport, Windows/native 구현, WMI 객체 생성·메서드 실행, 인스턴스 자동 선택이나 앱 등록은 없습니다.

합성 검증 경로는 다음과 같습니다.

요청 인코더 → 기존 FrameExchange → BoundFrameChannel → inData/Bytes 포장 → 가짜 snapshot transport → outData/Bytes 추출 → 응답 디코더 → 불변 결과

이는 소프트웨어 구성 요소를 함께 검증한 결과입니다. 실제 Windows/OEM 전송·배터리 보호 상태 읽기·충전 제한은 여전히 미구현·Unsupported입니다. 클래스 규약 확인은 이미 완료됐으므로 사용자에게 같은 노트북 진단이나 원본 자료를 다시 요청하지 않습니다.

## 요청 경계와 명시적 주입

WsabiWmiMethodBinder.TryWrapFrame은 정확한 CLR byte[]·21바이트만 받아 먼저 독립 복사한 뒤 magic0x5843의 little-endian 바이트와 예약 바이트0을 확인합니다. 명령 UInt16LE와 payload16은 기존 TryPrepareRequest로 전달합니다. 잘못된 형식·길이·magic·예약 값은 snapshot transport에 전달하지 않습니다.

입출력 바인더는 기존 상세 메타데이터 검증을 통과해야 생성됩니다. WindowsMethodId와 프레임 내부 명령은 계속 별도로 유지합니다. 관측WindowsMethodId1을 Linux0이나 배터리 명령으로 치환하지 않으며 명령 목록·기본 배터리 요청을 추가하지 않습니다.

IWsabiWmiMethodSnapshotTransport.ExchangeAsync는 포장된 요청과 취소 token을 받고 WsabiWmiMethodSnapshot을 반환하는 경계입니다. snapshot은 HRESULT와 분리된 메모리 출력만 임시 보관합니다. 출력 조회는 이미 메모리에 있는 제한된 lookup이어야 하며 live 제공자 getter를 전달하지 않습니다. 테스트에만 가짜 transport가 있고 제품용 실제 구현은 없습니다.

snapshot의 원문 출력은 보고서나 최종 응답에 보관하지 않습니다. 채널에는 last-result·원문 오류·출력 기록 필드가 없고 고정 outData/Bytes만 판독합니다. 네트워크·파일 저장·삼성 DLL·드라이버/서비스/ACL·펌웨어 변경을 추가하지 않았습니다.

## 단계별 응답 상태 보존

기존 WsabiWmiReplyResult에 nullable MethodReplyStatus를 추가하고 enum 끝에 InvalidEnvelope를 추가했습니다. 기존 값의 번호와 byte decoder/bool validator의 수락 조건은 유지합니다. 결과 결합은 내부 FromMethodReply에서만 수행하며 이미 결합한 응답을 byte decoder의 새 결과인 것처럼 재포장하지 못하게 합니다.

| 메서드 판정 | 최종 frame 상태와 상세 |
| --- | --- |
| FrameChecked | 원래 byte decoder의 상태·payload와 상세 FrameChecked |
| ApiNotSuccessful | 기존 ApiNotSuccessful와 같은 상세 상태 |
| 출력/중첩 객체/필드 없음·형식 오류·필드 조회 예외 | InvalidEnvelope와 구체적인 MethodReplyStatus, 빈 payload |
| 기존 byte decoder 직접 사용 | 원래 상태·payload, MethodReplyStatus=null |

S_OK=0만 출력 판독으로 진행하며 API 실패는 어떤 출력 lookup보다 우선합니다. 검증하지 않은 ReturnValue를 새 성공 기준으로 삼지 않습니다. 내부 프레임의 형식·차원·길이·ACK 오류는 그대로 보존하고 payload를 배터리 OFF/ON/미지원으로 해석하지 않습니다.

transport가 Task나 snapshot 자체를 반환하지 않거나 예외를 내면 기존 조정기가 TransportFailure로 처리합니다. 반환된 snapshot의 Output=null은 별도 MissingOutput으로 보존합니다. ReplyReceived는 결과가 반환됐다는 뜻이며 실제 유효성은 IsValidFrame으로 구분합니다. 모든 경우 실제 하드웨어 가능 플래그는 false입니다.

## 취소·시간 초과와 수명

채널은 transport에 같은 취소 token을 전달하고 실제 Task 완료를 기다립니다. 완료 직후와 출력 판독 직후에도 취소를 확인합니다. 미리 취소된 요청은 transport에 전달하지 않으며 취소 후 늦게 반환된 snapshot을 새 성공으로 게시하지 않습니다.

기존 FrameExchange의 시간 초과·취소·Busy 처리를 재사용하고 별도 조정기를 복제하지 않았습니다. 협조하지 않는 작업이 계속되면 실제 완료까지 해당 FrameExchange의 Busy가 유지됩니다. 늦은 예외도 관찰합니다. 이 제한은 협조적 대기와 취소이며 native 강제 종료 기능이 아닙니다. transport Task는 실제 작업이 멈춘 뒤 완료해야 하고 취소 콜백은 막히지 않아야 합니다.

직렬화는 FrameExchange 인스턴스별입니다. 채널 자체에는 전역 잠금이나 Busy가 없으므로 여러 조정기에 같은 transport를 공유한다고 자원 전체가 직렬화되지는 않습니다. 장래 실제 전송 구현에는 장치별 수명·직렬화·독립 프로세스 제한과 모델별 호출 근거가 별도로 필요합니다. 주입 인터페이스나 metadata 일치 자체를 실행 승인으로 취급하지 않습니다.

## 추가 공개 명령 근거 조사

기존 두 공개 WMI 프로젝트의 현재 루트·기간 필터 없는 포크 목록·공개 이슈를 제한된 범위에서 확인했습니다. 새로 확인한 [jesperol/samsung-wmi 원문](https://github.com/jesperol/samsung-wmi/blob/95150ada3a29be02d132093af573701f1f55c843/samsung-wmi.c)은 기존 gh2o와 커밋·바이트가 동일했습니다. SHA-256은 a230c1056930541f7fc54cadbc60b4e2fbdb9aec6608781b6ae00c1b8a0d9cf2이며 새 배터리 구현의 근거가 아닙니다.

djpohly의 현재 루트도 기존 a0a73dd8e810f6feae4e2aff4514f8a83f9b3995입니다. 새로 읽은 [고정 Kconfig](https://github.com/djpohly/samsung-wmi/blob/a0a73dd8e810f6feae4e2aff4514f8a83f9b3995/Kconfig#L9)는 battery parking을 명시하며 충전 상한/BLE와 구분합니다. SHA-256은 b352c53874e4bd9f2ba5371f4db3498aa67d873f1611d36ad06ac406a92b8eed입니다. 확인한 이슈 화면에는 결과가 없었지만 이를 다른 곳의 자료 부재로 확대하지 않습니다.

이 후속 조사에서도 현재940X3G/930X3G·BIOSP05ACJ의 Windows 배터리 명령·읽기 안전성·실제 응답 계약은 추가 확보하지 못했습니다. 비로그인 검색·공개 페이지 범위의 한계를 유지하며 외부 코드·드라이버·AML·삼성 프로그램은 실행하지 않았습니다.

## 전달과 다음 조건

전체 suite는 **297 passed, 0 failed, 0 skipped (297 registered)**이며 reports/wmi-pipeline-tests.json 및 .log에 기록했습니다. 새11개 그룹은 명시적 주입, 잘못된 프레임·사전 취소의 무호출, 전체 합성 경로, 요청·응답 복사 독립성, 번호 분리, 중첩/프레임 오류 보존, 재포장 거부, API 우선·기존 byte 호환, transport 예외/null/cancel, token 전파, 늦은 완료/예외와 Busy 회복을 검증합니다. 기존 byte decoder 테스트에도 상세 상태=null 호환 검사를 추가했습니다.

Core·WPF·두 별도 도구의 x64 net48 전체 빌드는 **경고0개·오류0개**이며 reports/wmi-pipeline-build.log에 기록했습니다. 합성 transport만 사용했고 실제 Windows/OEM 호출은 실행하지 않았습니다. 배포 스크립트 변경이 없어 Python suite는 다시 실행하지 않았으며 이전6개 통과는 이전 기록입니다. 새 소스 ZIP의 파일 허용 목록·현재 소스 일치·SHA-256·CRC는 별도 확인합니다.

이번에는 내부 통합 코드와 합성 테스트의 소스 ZIP을 제공합니다. 새 노트북 실행이나 이전 TXT·DLL·권한 비교 재제출은 필요하지 않습니다. 기존 실행판·소스 ZIP과 관측 이력은 보존합니다. 원본 삼성 바이너리·사용자 보고서·외부 소스는 포함하지 않습니다.

다음 개발 우선순위는 현재 모델의 배터리 명령 의미·안전성·실제 응답 계약의 근거 확보입니다. 통합된 메모리 경로의 테스트 수를 실제 충전 제어 성공이나 준비 완료 비율로 해석하지 않습니다.
