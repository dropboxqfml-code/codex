# WMI 비동기 프레임 처리와 클래스 규약 확인 — 2026-11-03

## 이번 구현과 남은 조건

기존 일반·관리자 비교는 [결과 수신으로 완료](WMI_PERMISSION_COMPARISON_RESULT.md)됐습니다. 속성 읽기 성공을 OEM 명령 실행 허가나 배터리 보호 상태로 해석하지 않습니다. 이번에는 저장된 분석을 바탕으로 비동기 프레임 처리 코드를 구현하고, 공개 WMI 전송과 현재 Windows 클래스의 연결을 확인할 **새 정적 메타데이터 도구**를 만들었습니다.

실제 WMI 프레임 전송 구현이나 앱의 OEM 호출 경로는 추가하지 않았습니다. 배터리 명령의 모델 적합성·읽기 안전성·입출력 계약은 여전히 미검증이며 실제 충전 제어는 Unsupported입니다. 이전의 한 번의 관리자 속성 비교 승인을 새 도구의 관리자 실행이나 OEM 호출로 확대하지 않습니다.

## 비동기 프레임 처리

WsabiWmiFrameExchange는 명시적으로 전달받은 IWsabiWmiFrameChannel과 기존 요청 인코더·구조적 응답 결과를 연결합니다. 제품에 기본 채널이나 실제 Windows/OEM 구현은 없고 테스트에서는 가짜 채널만 사용합니다.

- 잘못된 입력과 미리 취소된 요청은 채널에 전달하지 않습니다.
- 결과를 ReplyReceived, InvalidRequest, Cancelled, Busy, TimedOut, TransportFailure로 구분합니다. ReplyReceived에도 내부 응답 검증 실패가 있을 수 있습니다.
- 조정기 인스턴스 하나에서 한 번에 하나만 실행합니다. 취소·시간 초과 뒤에도 실제 채널 작업이 끝나기 전에는 Busy를 유지합니다. 늦은 응답은 성공으로 다시 게시하지 않으며 늦은 예외도 관찰합니다.
- 제한 시간은 0초 초과·최대 10초의 협조적 대기 제한입니다. 동기적으로 시작하는 채널 작업은 작업 풀로 분리하지만 native 호출을 강제로 종료하는 기능은 아닙니다.
- 채널의 취소 콜백은 막히지 않아야 하며 반환 Task는 실제 작업이 멈춘 뒤 완료해야 합니다. 서로 다른 조정기는 서로 잠그지 않으므로 같은 전송 자원을 공유할 미래 구현에는 별도 수명·직렬화 설계가 필요합니다. 실제 native 채널에는 독립된 프로세스 제한도 필요합니다.

프레임 유효성은 배터리 ON/OFF나 실제 장치 관측으로 승격하지 않습니다. 서비스 wsabi의 21바이트 프레임·payload16과 Sabi3 x64의 11바이트 native ABI는 계속 분리합니다.

## 새 도구가 읽는 정의

별도 ATIVBatteryGuard.WmiContractCheck.exe는 일반 권한 asInvoker 콘솔입니다. 메인 앱에서 실행하거나 UAC를 요청하지 않습니다. 로컬 ROOT\WMI에서 ManagementClass.Get으로 고정된 두 클래스 정의만 가져옵니다. PacketPrivacy·Impersonate·EnablePrivileges=false를 사용합니다.

| 대상 | 출력 | 해석 한계 |
| --- | --- | --- |
| WmiAcpiMethod.Guid qualifier | 공개 후보와 일치/다름/미관측/형식 확인 불가 | 실제 GUID 원문은 보관·출력하지 않음 |
| CallSabiFunction 정의 | 존재 여부, WmiMethodId | 메서드를 실행하지 않음. ID는 WMI 디스패치 번호이며 펌웨어 배터리 명령 번호가 아님 |
| inData·outData 정의 | 단일 Object이고 EmbeddedInstance가 DataBuffer인지 | DataBuffer 내용이나 요청값을 읽거나 만들지 않음 |
| DataBuffer.Bytes 정의 | UInt8 배열인지 | 실제 배열 길이·21바이트 프레임·ACK를 입증하지 않음 |

공개 GUID 후보 C16C47BA-50E3-444A-AF3A-B1C348380001은 [기존 공개 소스 검토](WMI_REPLY_DECODER_AND_PUBLIC_EVIDENCE.md)의 비교 상수입니다. 장치에서 얻은 다른 GUID는 출력하지 않습니다. 공개 두 구현의 WMI 메서드 번호는 모두 0이지만 인스턴스 번호는 0과 1로 다릅니다. 메타데이터 일치만으로 인스턴스를 선택하거나 두 클래스의 행을 연결하지 않습니다.

두 클래스 결과는 독립적으로 Complete/Partial·클래스/네임스페이스 없음·권한 거부·시간 초과·확인 불가를 구분합니다. 관측한 필수 필드나 형식이 다르면 False, 미관측·qualifier 누락·형식 확인 불가는 Unknown입니다. 실패 시 이전 사실은 제거합니다. 기능 부재나 실행 권한을 추정하지 않습니다.

클래스 정의를 가져오는 API 제한은 호출당 최대 2초, 공유 협조적 예산은 4초입니다. 인수 없는 일반 실행에서는 부모가 자체 작업자를 10초 뒤 중지하고 정리하며 콘솔 출력도 32,768자로 제한합니다. 내부 작업자 인수 직접 실행에는 부모 감시가 없으므로 일반 실행만 안내합니다. 임의 경로·쿼리·서버·OEM 명령을 받지 않습니다.

인스턴스·Active/version·DataBuffer 값·토큰 상승 여부·SID·사용자 이름·경로·예외 원문·보안 설명자는 수집하지 않습니다. 삼성 DLL 로드, 장치 열기, 서비스/드라이버/ACL 변경, OEM 실행 및 펌웨어 쓰기도 없습니다. 실행 중 네트워크 통신과 파일 저장은 없습니다.

## 노트북에서 확인할 새 항목

1. 새 ZIP 전체를 메인 앱과 다른 로컬 폴더에 압축 해제합니다.
2. ATIVBatteryGuard.WmiContractCheck.exe를 일반적으로 더블클릭합니다.
3. 두 정의의 조회 상태, 공개 GUID 일치 여부, WmiMethodId, inData/outData와 Bytes 정의 출력만 복사해 전달합니다. Enter로 닫습니다.

새 도구의 Windows 실기 실행은 아직 미검증입니다. 실패하면 표시된 결과를 그대로 사용하며 관리자 실행·보안 설정 변경으로 재시도하지 않습니다. 이전 진단·파일 목록·삼성 DLL/EXE·일반/관리자 비교를 다시 제출할 필요는 없습니다. 이번 결과가 일치해도 배터리 조회 명령의 근거와 안전성 검토가 별도로 남습니다.

## 추가 공개 자료 조사

이전 두 WMI 소스와 별개로 모델 문자열·배터리 명령·Windows 클래스 연결을 조사하고 아래 고정 원문을 정적으로 대조했습니다. 외부 프로그램·코드·드라이버를 실행하거나 제품에 복사하지 않았습니다.

| 공개 원문 | 확인된 범위 | 현재 모델의 배터리 계약 |
| --- | --- | --- |
| [jwrg/ativ9pctl, 4106f5a](https://github.com/jwrg/ativ9pctl/blob/4106f5a67c0d299e5ae71d2d6a07b94ccba9ba19/ativ9pctl#L3) | ATIVBook9Plus/NP940 언급, 밝기·음량·절전용 | 배터리/WMI 규약 없음 |
| [JakeSqPants/samsung-laptop-tools, 1c64deb](https://github.com/JakeSqPants/samsung-laptop-tools/blob/1c64deb93db47aa8746e13d4b3d649a294e266e8/README.md#L22) | 다른 11세대 Intel NT930QCA/NP930QCA의 Ubuntu sysfs | Windows·현재 모델 근거 아님 |
| [Embedded0909/TOOLS, 8ab4d55](https://github.com/Embedded0909/TOOLS/blob/8ab4d556b7a5a6398629149a78dc066fa74a9a9d/README.md#L353) | callSabiFunction이라는 로컬 래퍼에서 외부 Sabi_v1.5.exe로 EC 기록 | WmiAcpiMethod 구현·배터리 조회 규약 아님 |

원문 SHA-256은 차례대로 202cbc9d3aa2101a803367460f0ff3dd41880b7fdd23ef8cbed9d63acc896cf3, 0d2d9b1607a8bbdfd3eaf41e6a796828d9b007ed6b185b790668056b5d531efd, 4d554ff6d5c30ccff0925178074b6f14c9fc2c1367b48e40478ca72a9ba06c82입니다.

공개 저장소·이슈·README 검색과 이 원문 범위에서 모델별 Windows 배터리 조회 계약을 새로 확보하지 못했습니다. 로그인 없는 코드 검색과 네트워크 정책의 한계가 있으므로 자료가 존재하지 않는다는 결론은 아닙니다. 기존 0x65/0x66 후보나 version16을 새로운 실행 근거로 사용하지 않습니다.

## 검증과 제공물

- 현재 공유 소스 suite: 262 passed, 0 failed, 0 skipped (262 registered). 신규 비동기 처리 12개·메타데이터 정책/모델 6개 그룹을 포함합니다.
- Core·WPF·기존 권한 비교 도구·새 규약 확인 도구의 x64 net48 전체 빌드: 경고 0개, 오류 0개.
- 기존 Python 배포 검증 6개 통과. 새 패키지는 허용 파일 목록·asInvoker manifest·체크섬·ZIP CRC를 별도 확인합니다.
- 자동 테스트는 가짜 채널·합성 메타데이터를 검증합니다. 실제 Windows 제공자·새 콘솔 도구·OEM 호출·충전 제어를 시험했다는 결과는 아닙니다.

실행 ZIP에는 자체 규약 확인 EXE·Core DLL·구성 파일·안내·체크섬만 포함합니다. 소스 ZIP에는 자체 소스와 문서만 포함합니다. 삼성 원본 바이너리·외부 C 코드·사용자 원문 보고서는 어느 쪽에도 넣지 않습니다. [다운로드](../downloads/README.md)에서 프로그램과 일치하는 소스를 제공합니다.
