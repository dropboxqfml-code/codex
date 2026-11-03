# WMI 형식 일치 관측과 메모리용 메서드 바인더 — 2026-11-03

## 이번 실제 결과

사용자가 전달한 판독기2의 출력에서 WmiAcpiMethod와 DataBuffer가 모두 Complete이고 전체 비교가 MetadataShapeMatched임을 확인했습니다. 원본 TXT는 저장소·배포물에 넣지 않습니다.

| 항목 | 실제 관측 |
| --- | --- |
| 클래스 GUID | 공개 후보와 일치; 원문은 출력하지 않음 |
| CallSabiFunction | 정의 존재 |
| Windows WmiMethodId | 1 (0x00000001) |
| inData / outData | 모두 단일 Object, CIMTYPE가 DataBuffer 지정 |
| EmbeddedInstance | 두 매개변수 모두 미관측 또는 qualifier 없음 |
| DataBuffer.Bytes | UInt8[] |

이 결과로 이전 Unknown이던 입력/출력의 구체 클래스를 CIMTYPE로 확인했습니다. 이전 Partial 관측을 당시의 독립 결과로 보존하며 최초 도구가 그 qualifier를 읽었다고 바꾸지 않습니다. 원문 CIMTYPE를 보고하는 대신 고정 후보 일치 상태를 출력한 결과입니다. 토큰 상태·인스턴스 연계·메서드 실행 권한·실제 응답 길이·배터리 명령은 관측하지 않았습니다.

**클래스 형식 확인 단계는 완료됐으므로 같은 규약 도구·파일 목록·일반/관리자 비교를 다시 요청하지 않습니다.** 실제 배터리 보호 상태 읽기와 충전 제어는 여전히 미구현·Unsupported입니다. Windows 메서드 번호1을 다른 OS 번호나 펌웨어 명령 번호로 바꾸지 않습니다.

## 구현한 메모리용 바인더

기존 요청 인코더와 응답 디코더는 Bytes 배열을 처리합니다. 새 WsabiWmiMethodBinder는 그 배열과 고정 WMI 메서드의 중첩 필드 구조를 연결하는 순수 코드입니다. WMI 연결·native 객체 생성·CreateInstance·InvokeMethod·전송 채널 구현은 없습니다. 앱이나 진단 도구에 실행 경로를 등록하지 않았습니다.

| 계층 | 새 동작 |
| --- | --- |
| 바인딩 생성 | 두 클래스 Complete, GUID/메서드/번호 관측, 상세 입력·출력의 ScalarObject와 DataBuffer 근거, Bytes UInt8[]를 모두 확인해야 생성 |
| 요청 포장 | 기존 인코더의 21바이트를 inData → Bytes의 읽기 전용 중첩 snapshot으로 포장. DataBuffer는 계획의 고정 클래스 이름 |
| 응답 추출 | 분리된 메모리 snapshot에서 outData → Bytes만 조회한 뒤 기존 디코더에 전달 |
| 실패 처리 | API 실패·출력 없음/형식 오류·outData 없음/형식 오류·Bytes 없음·조회 예외와 내부 프레임 검증 실패를 구분 |

이전 호환 생성자로 bool만 true인 보고서는 상세 qualifier 근거가 없어 바인딩을 생성하지 못합니다. Partial·누락·충돌·잘못된 형식·조회 실패도 생성하지 못합니다. 생성 성공은 메모리 변환 준비 상태이며 OEM 실행 권한이나 모델 호환성 승인이 아닙니다.

WsabiWmiMethodRequest는 관측 WindowsMethodId와 호출자가 포장용으로 전달한 FirmwareCommand를 별도 보관합니다. 명령을 자동 선택하거나 배터리 명령 목록을 만들지 않습니다. 요청 원본·Frame getter·Arguments getter·중첩 Bytes는 서로 독립 복사본입니다. 바깥/안쪽 map은 읽기 전용이며 새 접근마다 새 snapshot을 반환합니다.

응답 API 값은 기존 분석의 COM HRESULT를 따르며 S_OK=0만 필드 조회로 진행합니다. S_FALSE나 오류는 출력 getter를 읽기 전에 실패합니다. 검증하지 않은 ReturnValue 필드를 새 성공 기준으로 가정하지 않습니다. 고정 outData와 Bytes 외의 멤버·오류 원문·원시 응답 객체는 읽거나 보관하지 않습니다.

출력 snapshot의 계약은 IReadOnlyDictionary<string, object>와 고정 canonical 키입니다. 이름 조회는 전달된 map의 comparer 규칙을 따르며 다른 키 열거·경로 해석·값 강제 변환을 하지 않습니다. 이는 이미 메모리로 분리된 자료를 위한 API이며 live 제공자 getter는 전달하지 않아야 합니다. 미래 Windows 전송 계층의 프로세스 제한·객체 수명·권한 설계는 별도로 필요합니다.

FrameChecked는 내부 프레임을 검사했다는 뜻입니다. 실제 유효성은 FrameReply.IsValidFrame으로 구분합니다. byte[] 형식·차원·길이·ACK 검증은 기존 디코더에 위임하고 실패 payload는 제거합니다. 정확히21바이트만 지원하는 기존 보수적 범위를 유지하며 실제 Windows 응답이 그 길이라는 관측으로 바꾸지 않습니다. payload의 0/1/FF를 배터리 OFF/ON/미지원으로 해석하지 않습니다.

바인더·요청·응답의 모든 호출 및 하드웨어 capability는 false입니다. 프로그램 실행 중 네트워크, 삼성 DLL, 드라이버/서비스/ACL 변경, 펌웨어 접근은 추가하지 않았습니다.

## 모델별 명령 근거 조사

저장된 서비스 wsabi 분석은 임의 명령의 WMI 중계를 설명하며 배터리 명령을 고정하지 않습니다. 저장된 SamsungConfigurationMonitor 분석은 팬·정숙 모드 문맥이고 0x80을 80%로 해석할 근거가 아닙니다. 다른 Sabi3 전송의 0x65/0x66이나 공개 WMI의 battery parking을 현재 충전 상한 명령으로 일반화하지 않습니다. 원본 바이너리를 이번에 재실행·재분석한 것은 아닙니다.

추가로 공개 [linuxhw/ACPI의 고정 README](https://github.com/linuxhw/ACPI/blob/d6d30c6ef6f45506567f25a302c64f009d8f5f4e/README.md#L776)와 [삼성 노트북 디렉터리](https://github.com/linuxhw/ACPI/tree/d6d30c6ef6f45506567f25a302c64f009d8f5f4e/Notebook/Samsung%20Electronics)를 정적으로 확인했습니다. 해당815개 보고서 인덱스와 확인한 디렉터리에는 940X3G/930X3G·P05ACJ 대상 자료를 찾지 못해 _WDG/WMxx와 배터리 명령을 연결하는 새 근거는 확보하지 못했습니다. 이 범위를 다른 곳의 자료 부재나 하드웨어 기능 부재로 확대하지 않습니다.

검토 커밋은 d6d30c6ef6f45506567f25a302c64f009d8f5f4e, README SHA-256은 0013600eeb413ea7ea36684ec2120f4bab28c483602a1d23330908048eecb5f9입니다. 거대 저장소 전체·다른 모델의 테이블을 내려받거나 AML/OEM 코드를 실행하지 않았습니다.

다음 실제 배터리 읽기의 남은 조건은 현재 모델·BIOS에 맞는 명령 의미, 읽기의 부작용과 안전성, 실제 응답 계약입니다. 새 클래스 일치 결과나 일반/관리자 속성 읽기는 그 근거를 대신하지 않습니다.

## 제공 범위

이번 전체 테스트는 **286 passed, 0 failed, 0 skipped (286 registered)**입니다. 신규12개 그룹은 실제 완전 일치 관측 보존과 오프라인 바인더의 상세 근거·이전 Partial/호환 보고서 거부·고정 구조·번호 분리·복사 독립·API 우선·중첩 실패·고정 조회·기존 프레임 오류·payload 비해석을 검사합니다. reports/wmi-method-binder-tests.json 및 .log에 기록했습니다.

Core·WPF·두 별도 도구의 전체 x64 net48 빌드는 **경고0개·오류0개**이며 reports/wmi-method-binder-build.log에 기록했습니다. 메모리용 합성 테스트이며 실제 OEM 호출·응답을 시험한 결과는 아닙니다. 독립 Core 검토에서 추가 결함을 발견하지 않았습니다. 기존 Python 배포 검증6개는 이전 결과이고 이번에 배포 스크립트를 수정하지 않아 다시 실행하지 않았습니다. 새 소스 ZIP의 허용 파일·현재 소스 일치·체크섬·CRC는 별도 확인합니다.

이번 변경은 내부 메모리 변환 코드와 합성 테스트이며 사용자가 노트북에서 새로 실행할 항목은 없습니다. [다운로드](../downloads/README.md)에 검증한 소스 ZIP을 제공합니다. 기존 실기 확인 도구와 모든 이전 배포물은 보존합니다. 삼성 원본 바이너리·사용자 원문 보고서·외부 문서/코드는 포함하지 않습니다.
