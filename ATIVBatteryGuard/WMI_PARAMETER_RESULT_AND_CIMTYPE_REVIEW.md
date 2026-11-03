# WMI 입출력 결과와 CIMTYPE 판독 보완 — 2026-11-03

## 수신한 실제 결과

사용자가 전달한 규약 확인 도구의 콘솔 출력에서 다음 사실을 확인했습니다. 원본 TXT·파일 이름에 들어갈 수 있는 식별 정보는 저장소와 패키지에 넣지 않습니다.

| 항목 | 관측 | 해석 |
| --- | --- | --- |
| WmiAcpiMethod | Partial | 클래스 전체 조회 실패가 아니라 입출력의 구체 클래스가 미확정 |
| 공개 GUID 후보 | 일치 | 공개 전송과 같은 GUID 후보, 배터리 명령 계약은 미확정 |
| CallSabiFunction | 정의 존재 | 메서드 실행을 시험한 결과 아님 |
| WmiMethodId | 1 (0x00000001) | Windows 정의의 디스패치 번호 원값 |
| inData / outData | 모두 Unknown | 기존 도구의 EmbeddedInstance 판독으로는 DataBuffer 여부 미확정 |
| DataBuffer | Complete, Bytes=UInt8[] | 클래스 정의의 형식 관측, 실제 버퍼 길이·내용·ACK는 미관측 |

도구의 해당 코드 경로에서는 입력/출력의 존재·단일 Object·비배열 조건을 통과한 뒤 Unknown을 반환합니다. EmbeddedInstance가 없었는지, 값이 null·비문자열·과도한 길이였는지는 기존 출력으로 구분할 수 없습니다. CIMTYPE 값은 이전 도구가 읽지 않았으므로 아직 미관측입니다. 이 도구는 토큰을 읽지 않아 이번 실행의 권한 수준도 출력만으로 확정하지 않습니다.

공개 Linux 두 소스는 메서드 번호 0을 사용하지만 Windows WmiMethodId와의 매핑 근거는 없습니다. 특정 서비스 wsabi는 Windows 메서드를 이름으로 호출합니다. 따라서 1을 0으로 바꾸거나 1을 빼지 않으며, 번호 차이를 비호환·기능 부재로 단정하지도 않습니다. 인스턴스 번호와 프레임 내부 펌웨어 명령도 서로 다른 값입니다.

## 공식 형식과 이전 판독기의 한계

Microsoft의 [CIMType qualifier 문서](https://github.com/MicrosoftDocs/win32/blob/ca8274decead49403d70ceeed4af8d4ca74eaf11/desktop-src/WmiSdk/cimtype-qualifier.md#L40)는 embedded object의 구체 클래스 표기로 **object:EmbedClass**를 설명하며 CIMType qualifier가 자동 추가된다고 명시합니다. [EmbeddedInstance 문서](https://github.com/MicrosoftDocs/win32/blob/ca8274decead49403d70ceeed4af8d4ca74eaf11/desktop-src/WmiSdk/standard-qualifiers.md#L205)는 문자열 타입 요소에 담긴 embedded instance를 설명합니다. [적용 범위](https://github.com/MicrosoftDocs/win32/blob/ca8274decead49403d70ceeed4af8d4ca74eaf11/desktop-src/WmiSdk/standard-wmi-qualifiers.md#L66)에는 properties·methods·parameters와 문자열 형식을 명시합니다.

첫 도구에서 단일 Object의 구체 클래스를 EmbeddedInstance만으로 확인한 것은 불완전했습니다. 표준 CIMTYPE 표기를 지원하도록 고쳤습니다. 다만 노트북에서 실제로 object:DataBuffer가 제공되는지는 아직 확인하지 않았으며, 이를 기존 Unknown의 확정 원인으로 기록하지 않습니다.

검토 원문은 MicrosoftDocs/win32 고정 커밋 ca8274decead49403d70ceeed4af8d4ca74eaf11입니다. 각 SHA-256은 순서대로 ac0729c19f10a413416822d41fb1bae63cf143c35298fe7e0495f84c09631f65, 963820feefcdad47f3f78dd623f9661e67ac0434c736ae8164047746f9b83091, 40e45292a81379d1d3341cf97bfe90f983523bc634800cbd13727d63db1860a7입니다. 문서만 정적으로 읽었으며 외부 코드나 삼성 프로그램을 실행하지 않았습니다.

## 구현한 변경

- WsabiWmiParameterMetadata와 정책은 매개변수 형식·EmbeddedInstance·CIMTYPE를 독립된 불변 enum으로 보관합니다. 원문 문자열·다른 클래스 이름·오류 원문은 보관하지 않습니다.
- 단일 Object에서 EmbeddedInstance=DataBuffer 또는 CIMTYPE=object:DataBuffer를 정확한 대소문자 무시 비교로 확인합니다. 공백 제거·경로 해석·문자열 강제 변환은 하지 않습니다. 각 입력은 최대 96자입니다.
- 한쪽이 누락되고 다른 쪽이 정확히 일치하면 그 근거로 형식을 확인합니다. CIMTYPE가 object만 지정하면 클래스는 미지정입니다. 명시된 다른 형식은 불일치로 남깁니다. 두 qualifier가 충돌하거나 하나라도 잘못된 형식이면 Unknown으로 남기며 일치하는 값으로 덮지 않습니다.
- 조회 실패·메서드 부재에서는 상세 사실을 제거합니다. 독립된 DataBuffer 결과는 유지합니다. 일부 조회를 전체 형식 일치로 바꾸지 않습니다.
- 보고서에 각 매개변수의 형식·두 qualifier 결과·판정과 전체 비교 상태를 표시합니다. 전체 상태는 정보 부족, GUID/메서드 확인 후 나머지 미확정, 메타데이터 형식 일치, 관측한 정의의 불일치를 구분합니다. 모든 상태의 OEM 실행·하드웨어 읽기/쓰기 가능 플래그는 false입니다.
- 상단에 **메타데이터 판독기: 2 (CIMTYPE 포함)**을 표시해 이전 도구와 구분합니다. WmiMethodId는 관측 원값을 보존합니다.

WMI 조회 대상은 이전과 같은 로컬 두 클래스와 고정 필드이며 추가 읽기는 inData/outData의 고정 CIMTYPE qualifier입니다. 인스턴스·Active/version·실제 DataBuffer 값·토큰·보안 설명자·경로는 읽지 않습니다. asInvoker·PacketPrivacy·EnablePrivileges=false, 부모 작업자 10초 제한·32,768자 상한을 유지합니다. 자동 권한 상승·OEM 메서드·삼성 DLL·서비스/드라이버/ACL·펌웨어 변경은 없습니다.

## 검증과 현재 개발 단계

현재 전체 suite는 **274 passed, 0 failed, 0 skipped (274 registered)**입니다. 신규12개 그룹은 표준 CIMTYPE·기존 표현·충돌·잘못된 형식·길이/식별자 경계·형식 선행 조건·정보 보호·잘못된 enum·실제 관측 합성 사례·OS 번호 비치환·불완전 상태·실패 시 상세 정보 제거를 검사합니다. reports/wmi-parameter-tests.json 및 .log에 기록했습니다.

Core·WPF·기존 권한 비교 도구·새 판독기 전체 x64 net48 빌드는 **경고0개·오류0개**이며 reports/wmi-parameter-build.log에 기록했습니다. 기존 Python 배포 검증 **6개**도 통과했습니다. 자동 테스트는 합성 정의를 사용하며 실제 Windows 제공자를 시험하지 않습니다.

이전 판독기는 이번 사용자 결과로 클래스 정의 조회의 실기 실행을 확인했습니다. 수정 판독기2의 Windows 실행은 아직 미검증입니다. 실제 배터리 보호 상태 읽기와 충전 제한은 여전히 미구현·Unsupported입니다. WMI 클래스 연결의 근거가 늘었지만 현재 모델 배터리 명령의 의미·읽기 안전성·실제 응답 계약은 별도로 남습니다. 실제 OEM 전송 채널은 연결하지 않았습니다.

## 제공물과 다음 확인

[다운로드](../downloads/README.md)의 새 WMI-PARAMETER-CHECK ZIP 전체를 새 로컬 폴더에 풀고 ATIVBatteryGuard.WmiContractCheck.exe를 일반적으로 실행합니다. 상단 판독기2 표시와 inData/outData의 **CIMTYPE·판정**이 이번 새 확인 대상입니다. 이전 TXT·삼성 파일 목록·원본 DLL·권한 비교를 다시 제출할 필요는 없습니다. 권한 거부·시간 초과가 나면 그대로 사용하며 관리자 실행이나 보안 설정 변경은 요청하지 않습니다.

실행 ZIP에는 자체 EXE·Core DLL·설정·안내·체크섬만, 대응 소스 ZIP에는 자체 소스·문서만 넣습니다. 원본 삼성 바이너리·사용자 원문 출력·외부 문서 원문은 포함하지 않습니다. 새 프로그램 링크는 GitHub의 고정 커밋으로 제공하고 실제 다운로드와 체크섬을 확인합니다.
