# 하드웨어 조사

## 확인된 사실

사용자 화면·진단과 로컬 정적 분석에서 확인한 범위입니다. 원본 사용자 진단 파일과 삼성 바이너리는 저장소·배포물에 포함하지 않습니다.

- 모델: `940X3G/930X3G`, BIOS: `P05ACJ.128.140819.dg`.
- Windows 10 Home `10.0.19045`, OS와 앱 프로세스는 x64.
- 이전에 Windows와 앱이 모두 표시한 0%는 사용자가 당시의 실제 상태임을 확인했습니다. 수치 보정 대상이 아닙니다.
- 2026-10-31 후속 화면과 진단에서는 **62%, AC 연결 안 됨, 방전 중**이었습니다. `GetSystemPowerStatus`와 `Win32_Battery` 잔량이 62%로 일치했습니다. 현재 값은 계속 Windows 측정에 따라 갱신합니다.
- Samsung Settings 2.2.0이 설치되어 있지만 충전 제한 메뉴가 없다고 사용자가 확인했습니다.
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

실제 Samsung Settings 앱의 EXE·DLL에는 메뉴 노출 조건, 모델 지원 조건 또는 배터리 관련 정적 참조가 있을 수 있습니다. 기존 팬·정숙 모드 서비스 모듈에서 이 정보가 확인되지 않아 실제 설정 앱을 다음 분석 대상으로 삼습니다. 앱 파일을 확보하거나 충전 관련 문자열을 발견하는 것만으로 명령의 안전성을 확정하지 않습니다.

## 아직 검증되지 않은 항목

- `CallSabiFunction` 입력 바이트의 의미와 모델·BIOS별 지원·안전 범위
- 실제 충전 상한 80%/100% 명령과 현재 설정을 읽는 방법
- Samsung Settings 앱의 충전 메뉴 노출·모델 지원 조건
- Windows에서 쓸 수 있는 공식·검증된 OEM 제어 인터페이스
- 앱 종료·재부팅·전원 차단 뒤 펌웨어 설정 유지 여부
- 삼성 DLL의 공식 ABI와 전자서명 신뢰

클래스나 메서드가 발견되어도 실제 제어 지원으로 표시하지 않습니다. 하드웨어 상태는 계속 미지원으로 유지합니다.

## 다음 검증

사용자 확인 후 설치된 Samsung Settings 앱의 제한된 EXE·DLL 복사본을 수집해 정적 분석합니다. HKLM 등록 정보에서 검증된 전용 설치 위치만 사용하고, 파일·깊이·용량 한도를 적용합니다. 설정·로그·개인 문서는 수집하지 않습니다. 위치나 파일 검증에 실패하면 보고서만 생성합니다.

OEM 메서드 호출, 인스턴스 값 수집, OEM DLL 로드·실행, 드라이버 설치는 이 단계에 포함하지 않습니다. 실제 커널·펌웨어 제어 코드는 별도의 명시적 사용자 승인과 모델 적합성·안전성 근거가 확보된 뒤에만 추가할 수 있습니다.

## 설치 위치 정보 누락 결과와 수정

후속 사용자 Settings 분석 ZIP은 모듈 0개인 보고서 전용 자료였습니다. 32비트 Samsung Settings 등록은 발견됐지만 InstallLocation/DisplayIcon 문자열이 모두 비어 ICON_PATH_NOT_PROVIDED로 종료했습니다. 이는 앱 미설치나 배터리 제어 미지원의 증거가 아닙니다.

이 경우에만 시스템 Program Files/PFx86/ProgramData의 Samsung\Settings 또는 Samsung\Samsung Settings 전용 후보 최대 6곳을 확인하도록 수정했습니다. 등록 불일치나 제공 경로 거부에는 적용하지 않습니다. 링크 차단·회사 정보/PE 검사·복사 한도·동의 확인은 유지합니다. 수정 후 실제 Windows 파일 확보는 아직 검증하지 않았습니다.
