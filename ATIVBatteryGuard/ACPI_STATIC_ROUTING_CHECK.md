# ACPI 정적 WMI 연결 점검 — Acpi-routing-v1

**실기 결과 수신:** 목록 Complete·DSDT 0·SSDT 4·첫 SSDT Partial·설명자/메서드 0이 보고됐습니다. [결과와 수집 한계](ACPI_ROUTING_LAPTOP_RESULT.md)를 현재 기록으로 따릅니다. DSDT 본문은 읽지 않았고 WMI 정의/FF 의미를 확보하지 못했습니다. 아래는 배포 당시의 범위와 절차이며 같은 도구 재실행이나 기존 자료 재제출은 필요하지 않습니다.

## 이번 접근의 목적

기존 코드를 다시 대조했으나 byte order·입출력 필드·stale buffer·응답 offset에서 FF를 만들어 내는 오류는 찾지 못했습니다. Windows 메서드 번호1은 프레임에 들어가지 않으며 CallSabiFunction 이름으로 호출합니다. 공개 모델명/README 검색으로 찾은 정확 모델 관련 설정 저장소에서도 현재 펌웨어의 WMI 배터리 명령 계약을 확보하지 못했습니다. GitHub 검색 제한 응답 뒤에는 추가 검색을 반복하지 않았습니다.

새로 확인한 `pimterry/qtile-config`는 NP940X3G용 배터리 표시 설정이고, `nagromc/machine-configuration`의 [정확 모델 Windows 브랜치](https://github.com/nagromc/machine-configuration/tree/bb14726e74ee6bf56b760f0a37443220245ff3f7)는 시간/터치패드 설정 자료였습니다. 해당 브랜치 파일 목록과 README에서 배터리 명령·펌웨어 정의를 확보하지 못했습니다. 설정 스크립트나 레지스트리 파일은 실행하지 않았습니다.

남은 새 분석 대상은 **현재 노트북의 WMxx 메서드가 method ID와21바이트 입력을 어떻게 분기하는지**입니다. 이를 확인할 모델별 ACPI 자료가 공개 저장소에 없었으므로 Windows가 제공하는 현재 테이블의 제한된 정적 요약을 읽는 별도 도구를 구현했습니다. 기존 배터리 진단·DLL·과거 실행 결과의 재제출은 필요하지 않습니다.

이 도구는 아직 FF의 의미를 해결한 결과가 아닙니다. 전송 바이트를 바꾸거나 새 OEM 요청을 해보는 대신, 실제 모델의 연결 정의에서 확인 가능한 범위를 좁힙니다.

## 수집 범위

새 `ATIVBatteryGuard.AcpiRoutingCheck.exe`는 일반 권한으로 실행하는 별도 x64 net48 콘솔입니다. 메인 앱에서 자동 실행하지 않습니다.

- Windows의 EnumSystemFirmwareTables/GetSystemFirmwareTable 두 API만 사용합니다. 공급자는 ACPI로 고정하고 DSDT와 첫 SSDT만 읽습니다. SMBIOS/RSMB/FIRM/MSDM 등 다른 테이블은 요청하지 않습니다.
- 원본 테이블은 메모리에서만 다루고 파일로 내보내지 않습니다. 해석 후 원본과 검사 복사본을 지웁니다. 프로세스 메모리의 완전한 삭제를 보장하는 기능으로 해석하지 않습니다.
- AML·ACPI 메서드를 평가/실행하지 않고 포트·장치·SMI·삼성 DLL·WMI/OEM 메서드를 호출하지 않습니다. 기존 1회 예약 파일도 읽거나 쓰지 않습니다.
- 오류는 AccessDenied/NotSupported/NotFound/Unavailable/Incomplete 등 고정 종류만 출력합니다. 부모와 작업자에 각각10초 제한이 있습니다. 권한 오류가 나도 자동 상승하거나 보안 설정을 바꾸지 않습니다.

공식 API 근거: [EnumSystemFirmwareTables](https://github.com/MicrosoftDocs/sdk-api/blob/656e9656bfaef34dd29cd7ee9e1146aec17e924c/sdk-api-src/content/sysinfoapi/nf-sysinfoapi-enumsystemfirmwaretables.md), [GetSystemFirmwareTable](https://github.com/MicrosoftDocs/sdk-api/blob/656e9656bfaef34dd29cd7ee9e1146aec17e924c/sdk-api-src/content/sysinfoapi/nf-sysinfoapi-getsystemfirmwaretable.md). 표 ID는 little endian이며 같은 서명 테이블의 첫 것만 반환한다는 제한을 반영했습니다.

## 출력하는 정적 사실

알려진 공개 SABI GUID에 대응하는 `_WDG`의 정적 Buffer 설명자와 같은 namespace의 WMxx 정의 후보만 찾습니다. GUID 원문·이름·namespace 경로·주소·OEM 정보·장치 식별자는 내보내지 않습니다.

| 항목 | 해석 |
| --- | --- |
| 테이블 정의 구문 Complete/Partial | 지원하는 구문 범위의 탐색 상태. 전체 펌웨어나 기능 유무의 판정이 아닙니다. |
| 설명자/대응 메서드 관측 수 | 정적으로 읽은 범위의 수. 다른 테이블이나 건너뛴 정의까지 합친 유일성 보장이 아닙니다. |
| 단일 관측 후보 인수 수 | 정의의 인수 수만 표시합니다. 다른 후보·미관측에는 미확정입니다. |
| 메서드 본문 Parsed/UnsupportedSyntax 등 | 구문 해석 가능 여부를 인수 불일치·모호함·미관측과 구분합니다. |
| ID1·입력 길이21 동등 비교 | 직접적인 구문 관측만 표시합니다. 보조 메서드·변수 값·조건 실행을 추론하지 않습니다. |
| 상수FF/FF프레임 Return | 스칼라255 또는 정확한21바이트/ACKAA/첫payloadFF인 상수 Buffer의 직접 반환 구문입니다. 실제 분기 실행이나 FF의 배터리 의미는 아닙니다. |

해석하지 못하는 구문은 byte 단위로 재검색해 추측하지 않고 현재 컨테이너를 닫습니다. Buffer/Package/String/Field의 데이터 안에 우연히 있는 opcode를 정의로 인식하지 않습니다. 부분 관측은 전체 부재로 바꾸지 않고, 메서드 본문 해석이 실패하면 중간 구문 표식을 폐기합니다.

한계는 명확합니다. 전체 AML 언어, 동적 `_WDG`, alias/조건부 정의, 모든 SSDT와 테이블 간 결합, 호출된 보조 메서드의 동작을 완전히 해석하지 않습니다. 특히 SABI/SMI 내부 명령 처리가 다른 곳에 있으면 이 요약만으로 배터리 계약은 밝혀지지 않을 수 있습니다. 어떤 결과도 제어를 활성화하지 않습니다.

## 실행과 필요한 새 자료

1. [ACPI-ROUTING-CHECK ZIP](../downloads/README.md) 전체를 새 로컬 폴더에 압축 해제합니다.
2. `ATIVBatteryGuard.AcpiRoutingCheck.exe`를 **일반 권한**으로 실행합니다. 관리자 실행이나 기존 실험 EXE 실행은 필요하지 않습니다.
3. `(Acpi-routing-v1)` 표시가 있는 출력 요약만 복사해 전달하고 Enter로 닫습니다.

앞서 일반 앱·배터리 표시 확인에는 추가 파일이 필요하지 않았습니다. 이번에 필요한 것은 기존 TXT/DLL의 재제출이 아니라, 그 자료에 없던 **현재 펌웨어의 WMI 연결 정의 요약**입니다. 원본 ACPI나 삼성 파일을 제출하지 않습니다. 새 OEM 시험도 아닙니다.

기존 1회 실험은 완료됐습니다. 재실행·예약 표식 삭제/초기화·추가 후보·0x66 쓰기를 하지 않습니다. 실제 충전 제어는 계속 Unsupported입니다.

## 검증 범위

합성 AML로 namespace 연결, 패키지 경계/체크섬, opaque 데이터의 오인식 방지, 중복/인수 불일치/부분 해석, 구문/개인정보·메모리 한계를 검사했습니다. 테이블당4MiB, namespace/표현식 깊이32, 처리 노드10만, 메서드4096개, 알려진 설명자32개를 상한으로 둡니다.

공개된 다른 삼성530U3 자료는 파서 형식 검증에만 사용했습니다. 해당 DSDT/첫 SSDT를 별도로 추출해 정적으로 읽었고 DSDT의 알려진 설명자1개·대응 메서드1개·인수3개를 관측했습니다. 전체 namespace 해석은 Partial이었습니다. 이는 현재940/930 모델의 근거가 아니며 다른 모델의 동작을 대입하지 않습니다. 원본 공개 ACPI도 배포물에 포함하지 않습니다.

새 Windows API 실행과 실제 노트북의 결과는 아직 미검증입니다. 클라우드에서 펌웨어/AML/OEM을 실행하지 않았습니다. 정확한 자동 검증 수치는 [VALIDATION](VALIDATION.md)에 기록합니다.

이번 전체353개와 Python 배포 검증22개가 통과했고 전체7개 프로젝트 및 테스트 프로젝트 빌드는 경고·오류0개입니다. 독립적인 소스 검토도 완료했습니다.
