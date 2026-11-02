# WMI 응답 디코더와 추가 공개 전송 근거

2026-11-03 한국 시간 기준입니다. 프로그램 후속 개발로 기존 순수 요청 인코더에 대응하는 구조적 응답 디코더를 구현했습니다. 실제 WMI 메서드·삼성 DLL·장치 호출은 연결하지 않았습니다.

## 새로 확인한 공개 근거

공개 GitHub 검색과 고정 커밋의 원문을 읽어 기존 서비스 wsabi의 정적 분석과 대조했습니다. 외부 코드는 실행하거나 제품에 복사하지 않았습니다.

| 공개 소스 | 정적으로 확인한 내용 | 적용 한계 |
| --- | --- | --- |
| [gh2o/samsung-wmi:30](https://github.com/gh2o/samsung-wmi/blob/95150ada3a29be02d132093af573701f1f55c843/samsung-wmi.c#L30) | packed u16 magic + u16 opcode + u8 상태 + data16, magic0x5843 | 팬·키보드 등의 구현이며 별도 unlock 호출도 있음 |
| [djpohly/samsung-wmi:61](https://github.com/djpohly/samsung-wmi/blob/a0a73dd8e810f6feae4e2aff4514f8a83f9b3995/samsung-wmi.c#L61) | 같은 총21바이트 구조, 상태0xAA와 payload16 복사 | 현재 모델의 Windows 호출·배터리 보호를 검증한 자료가 아님 |

두 소스는 WMI GUID C16C47BA-50E3-444A-AF3A-B1C348380001을 사용합니다. 이 공개 GUID와 사용자가 관측한 Windows 클래스의 동일성은 아직 대조하지 않았으므로 현재 앱의 연결 대상으로 추가하지 않았습니다.

검토한 소스에서는 0x65/0x66, WmiAcpiMethod/CallSabiFunction 이름, 940X3G/930X3G, version16의 의미를 확인하지 못했습니다. djpohly의 [battery parking 지원 확인](https://github.com/djpohly/samsung-wmi/blob/a0a73dd8e810f6feae4e2aff4514f8a83f9b3995/samsung-wmi.c#L178)은 0x7A의 하위 기능이며 배터리 수명 연장 조회0x65나 충전 상한으로 바꿔 해석하지 않습니다.

공개 코드의 길이 검사는 그대로 따르지 않습니다. gh2o의 [73행](https://github.com/gh2o/samsung-wmi/blob/95150ada3a29be02d132093af573701f1f55c843/samsung-wmi.c#L73)은 구조체가 아닌 포인터의 크기로 최소 길이를 비교합니다. djpohly의 [123행](https://github.com/djpohly/samsung-wmi/blob/a0a73dd8e810f6feae4e2aff4514f8a83f9b3995/samsung-wmi.c#L123)은 큰 길이만 거부하고 작은 응답을 읽기 전에 최소 길이를 확인하지 않습니다. 새 디코더는 배열 형식과 정확한 지원 길이를 먼저 검증한 뒤 ACK와 payload를 읽습니다.

원문 파일의 SHA-256:

- gh2o 고정 커밋95150ada3a29be02d132093af573701f1f55c843: a230c1056930541f7fc54cadbc60b4e2fbdb9aec6608781b6ae00c1b8a0d9cf2
- djpohly 고정 커밋a0a73dd8e810f6feae4e2aff4514f8a83f9b3995: 3281018d70fb8158dee1622e12f0ca6b0d1b3b4317d5e42731e3606218b6d88b

GitHub API 검색은 현재 정책에서 Forbidden이었고, 비로그인 공개 코드 검색은 로그인 요구 화면이었습니다. 허용된 공개 저장소 검색과 원문 읽기로 진행했으며 검색 결과 미표시를 전체 코드 부재로 해석하지 않았습니다. API 우회·새 인증값 요청·네트워크 설정 변경은 하지 않았습니다.

## 구현한 구조적 응답 처리

WsabiWmiReplyDecoder.Decode는 API 반환값과 전달된 object를 받아 다음 결과를 반환합니다. 입력은 실행 결과일 필요가 없으며 이 함수 자체는 장치에 접근하지 않습니다.

| 상태 | 의미 |
| --- | --- |
| ValidFrame | 지원하는 형식의 프레임 구조만 확인 |
| ApiNotSuccessful | S_OK가 아님. S_FALSE도 성공 데이터로 사용하지 않음 |
| MissingResponse | 응답 객체 없음 |
| InvalidType | 정확한 CLR byte[]가 아니거나 요소 형식 불일치 |
| InvalidShape | 차원·배열 시작 인덱스가 지원 범위와 다름 |
| UnsupportedLength | 지원하는 정확한21바이트와 다름 |
| InvalidAcknowledgement | 길이를 검증한 응답의 +4가 0xAA가 아님 |

기존 WsabiWmiReplyValidator.TryExtractPayload는 새 디코더를 사용하되 기존 bool API와 수락 범위를 그대로 유지합니다. API 오류를 응답 필드보다 먼저 처리하며 실패하면 이전 데이터 없이 빈 payload만 반환합니다. 응답·원문 오류·임의 형식 이름은 결과 객체에 보관하지 않습니다.

성공한 구조에서만 +5부터16바이트를 새 배열에 복사합니다. 결과 객체도 입력을 복사하고 Payload getter마다 독립 복사본을 반환하므로 호출자의 이후 변경이 기존 결과를 바꾸지 않습니다. 검증되지 않은 응답 헤더의 의미나 요청 echo 조건은 추가하지 않았습니다.

정확한21바이트는 현재 보수적 지원 범위이며 실제 Windows 제공자의 응답이 항상 그 길이라는 관측 결론이 아닙니다. 기존 서비스 wsabi의 특정 해시564b640d62db2a4e4b56c6331e0e526bad2ac1fcf438a41a9e5241551f457b6e를 대상으로 하며 모든 Settings DLL에 일반화하지 않습니다.

## 배터리 의미와 실제 호출의 경계

이 디코더는 payload의 0,1,0xFF를 그대로 바이트로 보존합니다. 이를 배터리 보호 OFF/ON/미지원으로 해석하지 않습니다. ValidFrame은 API·배열·ACK의 구조적 판정일 뿐 하드웨어 관측, 명령 지원, 실제 설정 읽기나 제어 허가가 아닙니다.

WMI의 payload16·프레임21은 Sabi3 x64의 payload11·드라이버 응답16과 구분합니다. 기존 Sabi3 응답 해석을 WMI payload에 재사용하지 않았습니다. 새 배터리 명령 목록·기본 요청·실행 도구·자동 권한 상승·OEM 메서드 연결은 추가하지 않았으며 Unsupported 컨트롤러를 유지합니다.

이번 추가 공개 근거는 전송 프레임을 독립적으로 뒷받침하는 진전입니다. 현재 모델의 배터리 조회 명령 의미·읽기 안전성·Windows 클래스와의 연결·제공자의 실제 응답 계약을 확정하는 근거는 아직 확보하지 못했습니다. 관리자 속성 읽기 성공을 그 근거로 대신하지 않습니다.

## 검증과 전달

전체 테스트244개 통과·실패/건너뜀0개, Core·WPF·별도 권한 비교 도구 빌드 경고·오류0개입니다. 추가6개 그룹은 API 우선순위·S_FALSE, 배열 형식/차원/경계, 짧거나 큰 길이, 전체256개 ACK, 독립 버퍼, payload 의미 비해석과 기존 bool 호환성을 검사합니다.

실제 명령 전송·OEM 응답·충전 제어는 실행하지 않았습니다. 이번 산출물은 검토 가능한 소스이며 사용자에게 같은 노트북 진단이나 원본 DLL을 다시 요청하지 않습니다. 외부 C 소스·삼성 바이너리·사용자 원문 TXT는 배포 소스에 포함하지 않습니다.
