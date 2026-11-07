# SDK 대상·관찰자·입력의 단일 시도 연결 — 2026-11-08 한국 시간

**공급된 SDK target·observer·parameters/buffer를 private binding에 고정하고 typed 비동기 호출 한 곳으로 연결했습니다.** [입력 소유권·정리](WINDOWS_WMI_OWNED_INPUT_LIFETIME_UPDATE.md)의 후속입니다. 새 연결은 SDK stand-in으로만 실행 검증하며 실제 노트북 호출이나 보호 조회 명령/template·앱 활성화를 추가한 작업이 아닙니다. 보호 설정 조회·충전 제어는 Unsupported입니다.

## 같은 시도에 고정한 객체

`WsabiWmiWindowsSdkBinding`은 nonnull 대상 사실·ManagementObject target·dedicated observer·parameters/buffer를 받아 불변 참조로 보유합니다. 세 SDK object wrapper는 서로 달라야 합니다. 공개 객체 getter·사용자가 주입하는 dispatch·실행 시 target/observer/input 교체 인자는 없습니다.

`PrepareSdkAsync`는 기존 두 Prepare API와 같은 plan 예산을 사용합니다. 기존 model/BIOS·metadata·고정 요청 검증 뒤 새 순수 `MatchesTargetIdentity(object)`로 plan의 opaque identity가 바로 이 target wrapper인지 ReferenceEquals로 확인합니다. 별도 instance key나 사용자/serial·전체 경로를 비교하거나 출력하지 않습니다. 참조 일치는 현재 하드웨어 동일성·데이터 신선함의 인증이 아닙니다.

bundle도 첫 준비 시도에 소모합니다. 같은 plan 또는 같은 bundle은 실패·취소·미사용 close 뒤 재무장하지 않습니다. 인자·plan 검증에 먼저 거부되면 bundle은 소모하지 않으며 이미 취소된 유효 시도는 plan/bundle을 소모하되 SDK getter·입력 인계는 시작하지 않습니다. 새 plan·새 bundle·별도 프로세스 전체를 막는 persistent 승인 경계는 아닙니다. 사용 완료된 옛 단발 예약은 접근하거나 재사용하지 않았습니다.

## 입력 인계 전 target 검사

추적되는 worker에서 다음 SDK metadata를 검사합니다. 검사 중 취소는 worker 완료를 대신하지 않습니다.

| 검사 | 허용 범위 |
| --- | --- |
| 런타임 타입 | 정확히 ManagementObject. Path의 virtual override와 실제 SDK 내부 routing이 달라질 수 있어 ManagementClass/다른 subclass는 거부 |
| Scope | 연결된 supplied Scope, server는 명시적 local dot, namespace는 고정 `root\WMI`. 문자열은 길이 128 이내·OrdinalIgnoreCase 비교이며 trim/서버 이름 fallback은 없음 |
| Path | instance이며 고정 WmiAcpiMethod class. RelativePath·전체 경로 문자열·instance key는 별도로 읽거나 보고하지 않음 |

대상 타입/연결/범위/instance 불일치와 getter 오류는 SdkStatus로 구분하며 입력 claim·event 등록·SDK method 진입 전에 거부합니다. NotConnected는 공급된 scope의 상태이며 driver 부재나 보호 기능 미지원을 뜻하지 않습니다. SdkStatus=Ready는 준비 시점 검사 결과이며 hardware 지원이나 실행 승인이 아닙니다. 검사 뒤 input/등록 실패가 나도 그 결과와 SdkStatus를 별도로 보존합니다.

scope/path는 한 번 검사한 snapshot입니다. binding의 참조 고정이 외부 alias의 Scope/Path·input 변경을 막지는 않습니다. caller는 준비 시작부터 관련 outer close까지 외부 mutation·Dispose·독립 dispatch를 배제해야 합니다. 새 query로 Active/metadata를 반복 확인하지 않았고 공급된 materialized 입력/기존 detached 사실 계약을 유지합니다.

## 고정된 SDK 진입과 완료

기존 fixed-request guard의 MethodId·command·전체 byte 검사 뒤 private dispatch가 같은 observer/target/parameters만 사용합니다. typed `InvokeMethod(observer, 고정 CallSabiFunction, parameters, 새 private InvokeMethodOptions)` 진입은 bundle당 최대 한 번입니다. 사용자에게 받은 method/options·동기 overload·retry·handshake·다른 DLL/driver fallback은 없습니다. buffer는 기존 Populator가 같은 parameters의 inData에 할당한 객체입니다.

이제 supplied delegate가 임의 target/input을 고르던 여지를 새 SDK 경로 안에서는 제거했습니다. 이것은 해당 SDK overload의 공급 참조 연결과 진입 상한입니다. SDK 내부 작업 수·암묵적 COM/연결·native input 변환·실제 firmware 읽기 의미를 인증하지 않습니다. 저장된 Microsoft v8 참조와 net48 API 컴파일은 현재 노트북 runtime 관측과 구분합니다.

SDK 직접 throw는 고정 예외로만 넘기며 정상 즉시 반환·throw·caller stop을 terminal로 바꾸지 않습니다. 이미 SDK 쪽에 진입한 실패는 기존 Unknown/관련 종료 대기를 유지합니다. 실제 terminal이 사라지면 Run/close와 입력 보유가 계속될 수 있습니다. 테스트 정리의 가짜 terminal이 실기 완료 보장은 아닙니다.

## borrowed target과 owned 입력

parameters/buffer는 기존 원자 claim에서만 인계받아 inner close 뒤 두 concrete Dispose를 시도합니다. target은 borrowed이며 binding이 강하게 보유하고 이 경로에서 Dispose하지 않습니다. caller는 해당 target을 보유하는 실제 선행/승리 시도의 관련 준비·outer close가 끝난 뒤 원래 소유 계약에 따라 target을 정리합니다. 재진입 거부는 그 시도의 수명을 단축하거나 target 정리를 허용하는 결과가 아닙니다.

protected membership에 borrowed target의 약한 identity를 추가해 root/embedded/queued 출력 alias가 target을 잘못 Dispose하거나 추가 metadata를 읽지 않도록 했습니다. 입력 pair의 강한 필드는 정리 뒤 해제되지만 불변 binding을 caller가 보유하면 wrapper 참조는 여전히 남을 수 있습니다. 모든 참조 소멸·다른 COM alias까지 보장한 것은 아닙니다. Run/Unknown·lease/등록 정리·입력 Dispose의 기존 합류 순서는 유지합니다.

## 검증과 다음 작업

새 binding 회귀 12개·수명 회귀 7개, **신규 19개 포함 전체 609개 통과·실패 0·skip 0**입니다. 순수 identity·constructor/alias·exact type·연결/local scope·instance·getter 오류·사전 취소·공유 예산·원래 입력 참조의 typed SDK 진입 1회·기존 owner 보호·검사 worker 취소·조기 terminal/늦은 반환·Unknown·lease/보고 예외·borrowed target의 root/embedded/late alias와 정리 실패를 검증했습니다. 모든 fake gate/관련 Task는 finally에서 합류합니다.

Windows production 소스 8개와 Core를 portable 시험에서 SDK stand-in과 실행했습니다. 기존 synthetic frame만 사용했고 실제 System.Management runtime/provider·노트북 SDK 객체는 실행하지 않았습니다. 전체 솔루션은 실제 net48 참조 Release 빌드 **경고 0·오류 0**입니다.

기존 Microsoft v8 ManagementObject 참조 파일의 길이·SHA와 선택 member 관계 5개를 대조했습니다. 새 다운로드나 현재 .NET48 구현 동일성 주장은 없으며 이 정적 5개를 앱 회귀 609개에 합산하지 않습니다. [정제 기록](reports/windows-wmi-sdk-dispatch-binding-audit.json)에 관측 범위와 검증 소스 해시를 남깁니다.

새 target/input 탐색·생성·명시 Connect/Get/Put/Cancel은 없습니다. private InvokeMethodOptions 생성과 typed InvokeMethod 호출 지점은 이번에 추가했습니다. Core의 순수 identity 비교 외에 앱 UI/default backend·기존 실험 backend/Program·encoder·소모 예약·배포 ZIP은 변경하지 않았습니다. 실제 WMI/OEM·하드웨어/Global 객체·삼성 원본·드라이버/서비스/보안/펌웨어·클라우드 환경은 실행·접근·변경하지 않았으며 새 노트북 실행·자료 제출은 필요하지 않습니다.

다음은 실제 시험의 시작·중단 조건과 고정 요청의 읽기 의미를 이 SDK 경로에 적용할 수 있는지 정리하는 작업입니다. 실제 요청 template·gate 유용성·관련 참여/완료·결과 귀속·실기 승인은 별도로 유지합니다. A/B의 호출 상한·B의 상태 변경과 옛 소비된 시험 권한은 바꾸지 않습니다.
