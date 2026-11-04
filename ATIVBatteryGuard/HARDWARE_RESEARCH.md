# 하드웨어 조사

## 보조 본문 미지원의 관측과 표준 구문 확장

**확인된 사실:** v3에서 후보 본문의 알려진 호출 표현식 1개·보조 정의 1개를 관측했으나 보조 본문은 해석 불가였습니다. root의 직접 Arg2 인수 0·UnresolvedName 반환은 입력 미전달·잘못된 응답 판정이 아닙니다. 기존 출력에는 정확한 중단 원인이 없습니다.

**구현과 미검증:** [v4](ACPI_HELPER_SYNTAX_UPDATE.md)는 고정 ACPICA 문법에 맞춘 확장 구문의 정적 소비와 고정 실패 원인, 해석 완료한 보조 본문 범위만의 반환 구문을 추가합니다. 어떤 동기화/대기/Fatal도 실행하지 않으며 현재 노트북에서 특정 확장 opcode가 사용됐다고 단정하지 않습니다. 새 실기 결과와 FF의 실제 의미는 미확정이고 실제 제어는 Unsupported입니다. 아래는 이전 조사입니다.

## 현재 DSDT 정의 관측과 보조 연결 구문

**확인된 사실:** v2 사용자 요약에서 DSDT 직접 본문 읽기·알려진 설명자/대응 메서드 각 1개·인수 3개·본문 Parsed를 관측했습니다. 전체 namespace는 Partial이고 직접 ID1/길이21 비교·상수 FF 반환은 지원 범위에서 미관측입니다. 기존 판독기는 호출된 보조 정의 본문을 따라 읽지 않았으므로 보조 본문에도 해당 처리가 없다고 해석할 수 없습니다.

**새 정적 구현과 미검증:** [v3](ACPI_METHOD_FLOW_UPDATE.md)는 반환 형태·명명 호출·직접 Arg2 인수와 같은 테이블의 보조 정의를 제한적으로 요약합니다. 구문 존재만 다루며 메서드 실행·값/별칭/조건 계산·WMI 원본 입력과 보조 인수 매핑은 하지 않습니다. 실제 FF 발생 위치나 배터리 의미는 아직 미확정이고 새 분석의 실기도 미관측입니다. 수집 범위를 넓히거나 OEM 실험을 반복하지 않으며 실제 제어는 Unsupported입니다. 아래는 이전 조사입니다.

## DSDT 미열거와 직접 읽기 근거

**확인된 사실:** v1은 실기에서 DSDT 목록 0 때문에 본문 조회를 건너뛰었습니다. ACPICA의 [고정 Windows 수집 구현](https://github.com/acpica/acpica/blob/e85aa3bebaae81ed1e6d163511ac7e1eafe732cf/source/os_specific/service_layers/oswintbl.c#L231)도 DSDT/XSDT 미열거를 설명하고 DSDT를 고정 ID로 직접 읽습니다. 이 근거로 [v2 수정](ACPI_DSDT_DIRECT_READ_UPDATE.md)을 구현했습니다. 실제 실행 코드는 복사하지 않고 기존 Windows 두 읽기 API와 제한된 순수 파서를 사용합니다.

**가정·미검증:** 현재 모델에서 직접 DSDT 읽기와 WMI 정의 해석이 성공할지는 아직 모릅니다. 읽혀도 부분 구문 또는 SMM 내부 처리 때문에 FF 의미를 밝히지 못할 수 있습니다. 여러 SSDT를 읽는 별도 레지스트리 캐시 방식은 공개 구현에 있지만 전체 활성 테이블 계약으로 확인되지 않았고 이번에는 도입하지 않습니다. OEM/AML 호출이나 원본 내보내기는 없으며 제어는 Unsupported입니다. 아래는 이전 조사 기록입니다.

## 모델 계약 후속 정적 조사

[입력·버전·공개 ACPI 트리 대조](WMI_MODEL_CONTRACT_FOLLOWUP.md)를 추가했습니다. 조회0x80은Linux에도근거가있으며 version16→SABI3 변환근거는없습니다. 현재공개tree에서940/930X모델을찾지못했고다른모델AML/명령을대입하지않았습니다. 현재Windows명령/FF의미를확정할근거는여전히부족하므로실제제어를활성화하지않습니다. 일반앱의일반권한시작/배터리표시는사용자가확인했습니다.

## 실제 후보 응답 수신 — 프레임 검증과 의미 분리

[이번 결과와 정적 대조](WMI_ONE_SHOT_QUERY_RESULT.md): 사용자 노트북에서 승인된0x65 요청의 ResponseReceived/FrameChecked/ValidFrame/FF를 확인했습니다. 비동기 완료0·단일 출력·정확히21바이트/ACKAA를 통과했고 payload첫바이트만FF였습니다. 명령 지원·보호상태·상한·부작용 부재나 전체payload/명령echo는 확인하지 않았습니다.

고정hotkeys와Linux v6.12 소스를 대조했으나 각각Sabi3 DLL/직접SABI 경로의FF를 현재모델WindowsWMI 의미로 전이할 근거는 확보하지 못했습니다. FF를OFF나하드웨어미지원으로 확정하지 않고decoder수락조건도변경하지 않습니다. 승인된1회는사용됐으며추가요청/표식초기화/0x66은없습니다. 이번개발은일반앱의과거결과오프라인검토이며실제제어는Unsupported입니다. 아래는이전기록입니다.

## 승인된 조회 후보 한정 실험 도구

[승인과 구현 범위](WMI_ONE_SHOT_QUERY_APPROVAL.md): 사용자가 미검증0x65 후보의 한정1회 실험을 승인했습니다. 별도도구에서 고정모델/BIOS·token·schema·단일Active대상·영속예약을 확인해야요청하며 삼성DLL·쓰기명령·driver/service/ACL·포트IO·자동상승은 구현하지않습니다. 비동기완료상태0과정확히1개출력후에만고정Bytes를읽고후보표식만분류합니다.

새 도구는 아직 Windows에서 실행하지않았습니다. 후보의모델별의미·입력padding·실제응답계약·예상하지못한펌웨어부작용은여전히미검증입니다. 어떤표식도실제보호설정/지원/80%성공으로승격하지않으며 현재제어는Unsupported입니다.

## 추가 공개자료 대조와 다음 실제 단계의 경계

[이번 근거·후보 실험 검토서](WMI_ONE_SHOT_QUERY_REVIEW.md): voria의Linux도구와hotkeys추가callsite/이슈를 정적으로읽었지만현재940/930·P05ACJ의WindowsWMI배터리계약은확정하지못했습니다. hotkeys는FF와OFF를같은false로접으므로그대로재사용하지않고 미사용0x0B주석도 새조회근거로사용하지않습니다.

미검증0x65후보·입력·권한·한정횟수·중단조건·위험을검토가능하게정리했습니다. 실제OEM코드와실험은아직미승인·미구현·미실행이고 현재제어는Unsupported입니다. ACPI선언만보는추가진단은배터리명령계약을해결하지못해즉시추가하지않았습니다. 이번에는외부코드·AML·삼성프로그램을실행하지않았습니다.

## 메모리 전송 경계 연결과 공개 포크 후속 조사

[이번 통합 경로와 공개 근거](WMI_BOUND_CHANNEL_AND_PIPELINE.md): 요청 인코더·비동기 조정기·메서드 바인더·응답 디코더를 가짜 snapshot transport로 연결했습니다. 실제 WMI/OEM 구현은 추가하지 않았으며 클래스 일치나 내부 프레임 유효성을 하드웨어 지원으로 승격하지 않습니다.

새로 읽은 jesperol 포크는 기존 gh2o 고정 원문과 바이트가 같고, djpohly Kconfig는 battery parking만 설명합니다. 확인한 공개 포크·이슈 범위에서 현재 모델의 배터리 명령 의미·안전성·실제 응답 계약을 새로 확보하지 못했습니다. 다른 곳의 자료 부재나 하드웨어 기능 부재를 뜻하지 않습니다. 실제 충전 제어는 계속 Unsupported입니다.

## 실제 WMI 형식 일치 확인 완료

[판독기2 결과와 오프라인 바인더](WMI_MATCHED_BINDING_AND_OFFLINE_ENVELOPE.md): GUID 후보·메서드 존재·입출력 CIMTYPE의 DataBuffer·Bytes UInt8[]를 모두 확인했습니다. 두 클래스Complete·WindowsMethodId1이며 기존 입출력Unknown을 해소했습니다. 클래스 규약 진단은 완료됐고 같은 자료를 다시 요청하지 않습니다.

상세 메타데이터에서만 메모리용 중첩 입출력 바인더를 생성하도록 구현했으며 실제 OEM 전송은 없습니다. 공개linuxhw/ACPI의 고정 커밋 인덱스·삼성 디렉터리에서는 현재 모델/BIOS 자료를 찾지 못했습니다. 조사 범위 밖의 자료 부재나 기능 부재를 뜻하지 않습니다. 현재 모델 배터리 명령의 의미·안전성·실제 응답 계약은 여전히 미확정이고 실제 제어는 Unsupported입니다.

## 실제 WMI 클래스 관측과 미확정 입출력

[사용자 결과와 표준 CIMTYPE 근거](WMI_PARAMETER_RESULT_AND_CIMTYPE_REVIEW.md): 공개 GUID 후보 일치·CallSabiFunction 존재·Windows WmiMethodId1·DataBuffer.Bytes UInt8[]를 확인했습니다. 입력/출력은 Unknown이며 이전 도구는 CIMTYPE를 읽지 않았습니다. Microsoft 공식 정의의 object:EmbedClass 표기를 지원하도록 판독기를 수정했지만 현재 노트북에서 그 값이 제공되는지는 미관측입니다.

Windows 번호1을 공개 Linux0으로 매핑하거나 번호 차이로 비호환을 단정하지 않습니다. 이번 출력의 권한 수준도 미관측입니다. 클래스 정의의 연결 근거가 늘었지만 실제 명령 실행 권한·인스턴스 연계·배터리 명령 의미·안전성·실제 응답 계약은 확인되지 않았습니다. 실제 충전 제어는 계속 Unsupported이며 반복 파일/관리자 진단을 요구하지 않습니다.

## Windows 클래스와 공개 전송의 연결 확인 준비

[새 정적 메타데이터 도구와 추가 자료3건](WMI_EXCHANGE_AND_BINDING_CHECK.md)을 기록했습니다. 일반 권한으로 고정 WmiAcpiMethod/DataBuffer 정의만 읽고 공개 GUID 후보 일치·WmiMethodId·입출력 형식을 확인합니다. 새 노트북 출력은 아직 없습니다. WmiMethodId는 배터리 명령 번호가 아니며 정의 일치는 메서드 실행 권한·실제 응답 길이·현재 모델의 배터리 안전성을 입증하지 않습니다.

모델을 명시한 ativ9pctl은 밝기·음량·절전만 다루고, samsung-laptop-tools는 다른 11세대 모델의 Linux sysfs이며, TOOLS의 callSabiFunction은 외부 EXE 래퍼였습니다. 이 조사 범위에서는 현재 모델의 Windows 배터리 조회 계약을 확보하지 못했습니다. 자료의 부재나 기능 부재를 증명한 결과는 아닙니다. 실제 OEM 실행과 충전 제어는 여전히 미구현·미지원입니다.

## 추가 공개 WMI 프레임 근거

[두 공개 구현의 고정 커밋](WMI_REPLY_DECODER_AND_PUBLIC_EVIDENCE.md)에서 기존 서비스 wsabi와 같은 크기의21바이트 WMI 프레임과 payload16을 확인했습니다. 포인터 크기 또는 상한만 검사하는 원본의 길이 검사는 그대로 따르지 않았습니다. 공개 GUID와 현재 Windows 클래스의 동일성, 현재 모델의 배터리 명령, version16의 의미는 여전히 미검증입니다. 새 코드는 입력 바이트만 해석하며 실제 호출은 없습니다.

## 확인된 실제 비교: 일반 토큰의 부분 접근과 상승 토큰의 두 속성 조회

[권한 비교 결과](WMI_PERMISSION_COMPARISON_RESULT.md): 일반 실행은 버전 클래스의 Active=True/version16을 읽었지만 메서드 클래스 열거에서 0x80041003으로 거부됐습니다. 상승 실행은 두 클래스에서 활성 행1개씩과 version16을 읽었습니다. 이는 고정 속성 읽기의 접근 차이이며 메서드 실행·배터리 명령·실제 충전 제어 지원 근거가 아닙니다. 버전16 의미·행 연계·현재 모델의 조회 명령 계약은 아직 미확정입니다.

## PacketPrivacy로 해소되지 않은 WMI 거부

후속 TXT에서 암호화 인증 안내가 있는 빌드에서도 두 클래스 AccessDenied가 유지됨을 확인했습니다. 이로써 암호화 명시만으로 현재 문제가 해결되지 않았음을 확인했지만 현재 토큰 상승 여부·거부 단계·ACL/제공자 원인은 여전히 미확인입니다. [별도 제한된 비교 도구](WMI_PERMISSION_COMPARISON_REVIEW.md)를 준비했으며 관리자 비교는 아직 승인·실행하지 않았습니다. 실제 충전 제어는 계속 미지원입니다.

## 새 실제 관측: WMI 인스턴스 접근 거부

사용자 TXT에서 커널 드라이버 이름 후보 7개 모두 중지·수동 시작, SABI 이름 NotFound, WmiAcpiVersion/WmiAcpiMethod 모두 AccessDenied를 확인했습니다. 후보의 실제 용도나 WMI 거부 원인은 미확정입니다. Active·version은 관측되지 않았습니다. [분석·공식 근거·구현](WMI_ACCESS_RESULT_AND_TRANSPORT_REVIEW.md)에 일반 권한 암호화 인증 설정과 순수 프레임 준비를 기록했습니다. 접근 거부가 암호화 요구 때문이라는 것은 가설이며 실제 확인한 사실과 구분합니다. 관리자 실행·드라이버 시작·충전 지원 결론으로 바꾸지 않습니다.

## WMI 인스턴스 속성 확인 단계

사용자는 커널 드라이버 확인판의 실제 노트북 실행과 TXT 생성을 확인했습니다. TXT 내부의 드라이버 결과는 아직 전달받지 않았으므로 별도 미검증입니다. 기존 스키마에서 확인한 WmiAcpiVersion.Active/version과 WmiAcpiMethod.Active를 읽는 [새 기능](SAMSUNG_WMI_INSTANCE_INSPECTION.md)을 구현했습니다. 속성 읽기는 제공자를 사용하며 클래스 메타데이터 검사와 구분합니다. 새 조회의 노트북 결과·버전 의미·명령 호환성은 아직 미검증입니다. Active나 인스턴스 발견은 실제 보호 상태 또는 제어 지원 근거가 아닙니다.

## 최신 관측: SABI 연결 이름과 WMI 전송 구조

`samsung-files-20261101T132149`에서 현재 SABI 연결 이름을 찾지 못한 결과를 받았습니다. x64 DLL의 해시는 기존 정적 분석 대상과 같습니다. 드라이버 미설치나 펌웨어 기능 부재로 확정하지 않습니다. 기존 서비스 폴더 wsabi의 추가 정적 분석에서는 별도의 WMI 전송 구조(payload 16바이트·입력 21바이트)를 확인했습니다. 이는 Sabi3 x64의 11바이트 규약과 다르며, 현재 Settings 폴더의 다른 wsabi 해시에 일반화하지 않습니다. [최신 근거·코드 반영·다음 조건](SABI_LINK_RESULT_AND_WMI_REVIEW.md)을 우선 읽으세요. 아래 자료 수집 보류·선행 자료 요청은 당시 단계의 이력이며 사용자가 이후 직접 제공한 DLL의 현재 분석 범위를 대체하지 않습니다.

## 확인된 사실

최신 파일 식별 TXT에서 **Sabi3 3.2.0.0의 x64·x86과 공개 예제 함수 이름 5개**를 실제 확인했습니다. Settings 하위 폴더에서 네 대상 파일이 모두 관측됐으며 wsabi는 여러 다른 해시가 있습니다. [파일별 관측과 적용 한계](SABI3_COMPATIBILITY_REVIEW.md)에 기록했습니다. 메타데이터 확인을 현재 DLL 초기화·OEM 조회 성공으로 보지 않습니다.

사용자 화면·진단과 로컬 정적 분석에서 확인한 범위입니다. 원본 사용자 진단 파일과 삼성 바이너리는 저장소·배포물에 포함하지 않습니다.

- 모델: `940X3G/930X3G`, BIOS: `P05ACJ.128.140819.dg`.
- Windows 10 Home `10.0.19045`, OS와 앱 프로세스는 x64.
- 이전에 Windows와 앱이 모두 표시한 0%는 사용자가 당시의 실제 상태임을 확인했습니다. 수치 보정 대상이 아닙니다.
- 2026-10-31 후속 화면과 진단에서는 **62%, AC 연결 안 됨, 방전 중**이었습니다. `GetSystemPowerStatus`와 `Win32_Battery` 잔량이 62%로 일치했습니다. 현재 값은 계속 Windows 측정에 따라 갱신합니다.
- 2026-11-01 진단에서는 GetSystemPowerStatus 53%, WMI 52%, AC 연결 안 됨이었습니다. 순차 조회의 1%p 차이이며 값을 보정하지 않습니다.
- 같은 진단의 표준 배터리 조회는 인터페이스 1개에서 완료됐고 Capabilities는 `0x80000000`이었습니다. 시스템 배터리 표시만 있고 표준 충전·방전 요청 지원 비트는 없습니다. 현재 드라이버의 이 표준 경로를 제어에 사용하지 않습니다. OEM 기능 전체의 부재로 확정하지는 않습니다.
- 후속 `diagnostics-20261101T021357`에서는 52%, AC 연결, 충전 중이며 Win32와 WMI 잔량이 일치했습니다. 새 결과 해석 문장이 TXT에 정상 기록됐고 표준 지원 비트는 같았습니다. 이 TXT로 새 메인 화면의 렌더링까지 검증했다고 주장하지 않습니다.
- 공개 구형 Windows 래퍼와 Linux SABI3에서 배터리 수명 연장의 조회·변경 명령 후보를 찾았습니다. Windows 래퍼는 삼성 DLL에 의존하며 현재 WMI 바이트 계약이나 해당 모델의 실제 제어를 검증하지 않습니다. [공개 규약 비교](PUBLIC_CONTROL_PROTOCOL_REVIEW.md)에 출처와 한계를 기록했습니다.
- Samsung Settings 2.2.0이 설치되어 있지만 충전 제한 메뉴가 없다고 사용자가 확인했습니다.
- 사용자는 `Sabi3.dll`이 설치 폴더에 있다고 추가 보고했고 참고 경로 `C:\Program Files (x86)\Samsung\Setting`을 전달했습니다. 클라우드에서 이 폴더나 실제 DLL을 확인한 결과는 아닙니다. 이번에는 [DLL 후보 목록](SAMSUNG_DLL_CANDIDATES.md)으로 기록했으며 앱의 탐색·실행 경로로 사용하지 않습니다.
- 사용자는 BIOS 설정에도 배터리 충전 제한·수명 연장 메뉴가 없음을 추가 확인했습니다. 두 설정 화면의 부재는 관측 사실이며, 미공개 펌웨어 기능의 유무나 제어 안전성을 입증하지 않습니다. 메뉴 재점검은 요청하지 않습니다.
- `SamsungSystemConfiguration` 서비스가 실행 중인 것으로 보고됐습니다. 서비스 실행은 충전 제한 지원 증거가 아닙니다.
- 업로드된 `SamsungConfigurationMonitor.exe`는 같은 폴더의 `wsabi.dll`을 정적으로 참조합니다. 확인된 호출 문맥은 팬·정숙 모드입니다. 이 문맥의 `0x80`을 배터리 80% 명령으로 해석하지 않습니다.
- `wsabi.dll` 수집에 성공했습니다. 파일은 22,920바이트이며 SHA-256은 `564b640d62db2a4e4b56c6331e0e526bad2ac1fcf438a41a9e5241551f457b6e`입니다.
- 해당 DLL은 x86 네이티브 WMI/COM SABI 중계 DLL입니다. export는 `InitBIOSInterface`, `UninitBIOSInterface`, `CallBIOSInterface`, `GetBiosVersion`, `GetBiosMode`입니다.
- 정적 코드에서 `ROOT\WMI`, `WmiAcpiVersion`, `WmiAcpiMethod`, `DataBuffer`, `Bytes`, `inData`, `outData`, `CallSabiFunction` 참조를 확인했습니다.
- 후속 실제 노트북 진단에서 아래 클래스·메서드 정의를 모두 찾았고, 보고서에 기록된 조회 오류는 없었습니다. 속성 이름·형식과 메서드 정의만 읽었습니다. 해당 인스턴스 값은 읽지 않았고 OEM 메서드는 실행하지 않았습니다.

| 정의 | 실제 확인한 스키마 |
| --- | --- |
| `WmiAcpiVersion` | `Active: Boolean`, `InstanceName: String`, `version: UInt32` |
| `WmiAcpiMethod` | `Active: Boolean`, `InstanceName: String`; `CallSabiFunction(inData: Object) → outData: Object` |
| `DataBuffer` | `Bytes: UInt8[]` |

`CallBIOSInterface`에는 실제 WMI 메서드 실행 경로가 있으므로 읽기 전용 진단 함수로 취급할 수 없습니다. `GetBiosMode`가 조회하는 것은 SMBIOS 정보이며 배터리 보호 모드로 볼 근거가 없습니다. 이 분석에서는 OEM 파일을 실행·로드하거나 DLL 함수를 호출하지 않았습니다. 삼성 DLL의 전자서명 신뢰 검증도 수행하지 않았습니다.

## 가정

기존 Samsung/SABI 이름 필터만 사용한 목록은 위 클래스를 찾지 못했지만, 정확한 클래스 이름을 사용한 후속 정의 조회에서는 발견했습니다. 이로써 중계 인터페이스의 존재를 확인했으며 충전 제어 지원을 확인한 것은 아닙니다.

Samsung Settings 앱의 EXE·DLL에서 메뉴·모델 지원 조건을 확인하려던 접근은 이전 단계의 가설입니다. 현재는 사용자 조건에 따라 해당 앱에서 DLL을 추출할 수 없다고 가정하고 진행합니다. 추가 삼성 파일 수집이나 분석을 선행 조건으로 요구하지 않습니다. 공개 자료에서 해당 모델의 Windows OEM 명령과 실제 설정 조회 규약을 확인하는 경로로 전환했습니다. [공개 자료 검토 결과](DLL_INDEPENDENT_RESEARCH.md)를 참고하세요.

## 아직 검증되지 않은 항목

- `CallSabiFunction` 입력 바이트의 의미와 모델·BIOS별 지원·안전 범위
- 공개 명령 후보를 현재 모델의 Windows WMI로 전달하는 방법, 실제 80%/100% 상한의 의미와 현재 설정을 읽는 방법
- Samsung Settings 앱의 충전 메뉴 노출·모델 지원 조건
- Windows에서 쓸 수 있는 공식·검증된 OEM 제어 인터페이스
- 앱 종료·재부팅·전원 차단 뒤 펌웨어 설정 유지 여부
- 삼성 DLL의 공식 ABI와 전자서명 신뢰

클래스나 메서드가 발견되어도 실제 제어 지원으로 표시하지 않습니다. 하드웨어 상태는 계속 미지원으로 유지합니다.

## 다음 검증

현재는 삼성 프로그램 파일의 추가 수집·분석을 보류합니다. 먼저 해당 버전의 사용권 계약과 정확한 모델·BIOS·Windows 조합의 공식 지원 근거를 확인합니다. 공식 사이트 조회 준비 상태와 미전송 문의 초안은 [OFFICIAL_SUPPORT_REVIEW.md](OFFICIAL_SUPPORT_REVIEW.md)에 기록했습니다. 아직 공식 문서나 계약 조항을 열람하지 못했으므로 허용·금지나 충전 기능 지원 여부를 확정하지 않습니다.

실제 커널·펌웨어 제어 코드는 별도의 명시적 사용자 승인과 모델 적합성·안전성 근거가 확보된 뒤에만 추가할 수 있습니다.

## 설치 위치 정보 누락 결과와 수정

후속 사용자 Settings 분석 ZIP은 모듈 0개인 보고서 전용 자료였습니다. 32비트 Samsung Settings 등록은 발견됐지만 InstallLocation/DisplayIcon 문자열이 모두 비어 ICON_PATH_NOT_PROVIDED로 종료했습니다. 이는 앱 미설치나 배터리 제어 미지원의 증거가 아닙니다.

이 경우에만 시스템 Program Files/PFx86/ProgramData의 Samsung\Settings 또는 Samsung\Samsung Settings 전용 후보 최대 6곳을 확인하도록 수정했습니다. 등록 불일치나 제공 경로 거부에는 적용하지 않습니다. 링크 차단·회사 정보/PE 검사·복사 한도·동의 확인은 유지합니다. 수정 후 실제 Windows 파일 확보는 아직 검증하지 않았습니다.

## 2026-11-01 사용자 결과 확인

위치 누락 수정판의 후속 보고서에서 `RegisteredKnownDirectory`, `SettingsProgramFilesX86`, `Settings.exe` 앵커 발견을 확인했습니다. 대체 위치 확인은 동작했지만 회사 표시 정보가 수집 조건을 통과하지 않아 `COMPANY_NOT_SAMSUNG`으로 제외됐으며 복사 모듈 수는 0개입니다. 회사 정보가 누락된 것인지 다른 값인지는 이 보고서로 구분할 수 없습니다. 실제 파일 바이트는 아직 확보하지 못했습니다.

같이 재첨부된 이전 서비스 ZIP의 5개 모듈 SHA-256은 기존 분석 대상과 모두 일치했습니다. `wsabi.dll`도 같은 파일이며 배터리 명령에 관한 추가 근거는 없습니다. 원본 사용자 ZIP이나 OEM 파일은 저장소에 포함하지 않습니다.

앞서 요청했던 Settings.exe 직접 전달은 사용권 확인 전까지 철회했습니다. 추가 OEM 파일을 요청하거나 분석하지 않습니다. 위 수집 결과는 과거 조사 기록이며, 현재 진행 방향은 공식 지원·사용권 확인입니다. 실제 충전 제어는 계속 미지원입니다.

## Windows 버전별 지원 차이에 관한 사용자 제공 단서

사용자는 Windows 8에서는 충전 제한을 지원했으나 Windows 10 및 Samsung Settings 2.2 이후 메뉴가 사라졌다는 보고를 제시했습니다. 현재 사용 환경은 Windows 10과 Settings 2.2.xx입니다. 해당 보고의 원문 URL·정확한 모델·BIOS·이전 소프트웨어 버전은 아직 확보하지 못해 과거 지원 사실을 독립 검증한 것은 아닙니다.

같은 모델의 과거 공식 지원이 확인된다면 Windows 10용 OEM 프로그램의 기능 변경, 모델 판별, 드라이버/API 호환성 또는 지원 정책 차이를 우선 조사합니다. 보고만으로 정확한 원인이나 현재 펌웨어의 제어 가능성을 확정하지 않습니다. 메뉴 부재를 하드웨어 불가능으로 단정하지 않으며, UI 제거만을 확정 원인으로 취급하지도 않습니다.

다음 문서 비교는 Windows 8 당시 같은 모델의 공식 충전 제한 설명·프로그램 버전·요구 드라이버와 Windows 10/Settings 2.2의 공식 지원 범위입니다. 사용자에게 요청할 자료는 보고의 공개 URL 또는 문서 제목이며 삼성 실행 파일·DLL의 추가 수집은 계속 보류합니다. 실제 충전 제어는 미지원 상태를 유지합니다.
