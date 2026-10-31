# 삼성 DLL 추출 없는 개발 경로 조사

2026-11-01 한국 시간 기준입니다. 사용자의 Samsung Settings에서 DLL을 추출할 수 없다는 조건을 적용합니다. 삼성 실행 파일·DLL의 추가 수집·분석·로드·호출은 수행하지 않았습니다.

## 이번에 실제 확인한 공식 자료

삼성/NBRchive 원문은 실행 환경의 허용 목록이 적용되지 않아 아직 읽지 못했습니다. 현재 허용된 GitHub에서 MicrosoftDocs 공식 저장소의 원본 문서 다섯 개를 직접 읽었습니다. 아래는 그 문서 범위에서의 결론이며 이 노트북의 동작 검증을 대신하지 않습니다.

| 문서와 항목 | 문서에서 확인한 의미 | 이번 개발의 판단 |
| --- | --- | --- |
| GetSystemPowerStatus | AC/DC 전원, 충전 여부, 잔량 등 상태 조회 | 기존 배터리 표시 유지. 충전 상한 쓰기 기능으로 사용하지 않음 |
| IOCTL_BATTERY_SET_INFORMATION | 배터리 장치에 설정 요청을 보내는 Windows 인터페이스 | Windows에 설정 요청 경로가 전혀 없다고 단정하지 않음. 이번에는 호출하지 않음 |
| BatteryCharge | 지금 충전하라는 요청이며 Buffer 값은 무시됨 | 80% 상한을 지정하는 매개변수로 볼 수 없음 |
| BatteryDischarge | 지금 방전하라는 요청이며 Buffer 값은 무시됨 | AC 전원 유지 상태의 안전한 충전 상한 설정으로 취급하지 않음 |
| BatteryCriticalBias | 유지보수 목적의 잔량 보고 보정 | 충전 상한 대신 사용하지 않음. 잔량 0%나 62%를 보정할 이유도 없음 |
| BATTERY_SET_CHARGE_SUPPORTED / BATTERY_SET_DISCHARGE_SUPPORTED | 해당 장치가 위 요청 유형을 지원하는지 나타내는 플래그 | 드라이버 지원 확인이 필요함. 플래그가 있더라도 80% 상한 지원 증거가 아님 |

검토한 표준 인터페이스에는 지속되는 80%/100% 충전 상한 설정 항목이 문서화되어 있지 않았습니다. 이는 모든 Windows/OEM 인터페이스의 불가능을 입증하는 결론이 아닙니다.

## DLL 없이 남아 있는 경로

사용자 노트북의 기존 읽기 전용 진단에서는 Windows 내장 System.Management를 통해 ROOT\WMI의 WmiAcpiVersion, WmiAcpiMethod, DataBuffer 정의를 이미 조회했습니다. 따라서 이 WMI 정의를 읽는 데 추출한 삼성 DLL을 앱에 포함할 필요는 없습니다.

독립 C# 어댑터가 문서화된 OEM WMI 규약을 구현하는 구조 자체는 가능하지만, 지금은 CallSabiFunction 입력 바이트의 의미, 충전 설정 명령, 실제 상태 read-back, 모델·BIOS·OS 적합성을 입증할 공개 규약을 확보하지 못했습니다. 메서드 이름과 입력 Object/Bytes 배열 형식만으로 명령을 만들어 호출하지 않습니다. 기존 WMI 공급자가 필요한 구조와 추출 DLL이 필요한 구조도 구분합니다.

현재 목표는 해당 모델의 공식 충전 명령/조회 규약 또는 공식적으로 지원되는 독립 인터페이스를 확보하는 것입니다. DLL 추출을 다시 선행 조건으로 요구하지 않습니다. 근거를 확보하지 못한 동안 실제 충전 제어는 Unsupported로 유지합니다.

## 코드에 반영한 조건

- 배포 WPF 프로젝트에서 SamsungAnalysisBundleService와 SamsungSettingsLocator 소스를 컴파일 제외했습니다.
- 삼성 파일 수집 확인 창 구현과 수집 UI를 제거했습니다. 이전 구현은 소스 이력으로 보관하며 배포 EXE의 해당 타입 부재를 정적으로 검사합니다.
- 배터리 표시·로컬 설정·Mock·읽기 전용 WMI 정의 조회·공식 문의문 복사는 유지합니다.
- 실제 쓰기용 IOCTL, OEM WMI 메서드 호출, 드라이버 설치나 펌웨어 쓰기는 추가하지 않았습니다.

## 출처

GitHub의 MicrosoftDocs 공식 원본을 조회했습니다. 장치 제어 코드는 실행하지 않았습니다.

1. [GetSystemPowerStatus](https://github.com/MicrosoftDocs/sdk-api/blob/docs/sdk-api-src/content/winbase/nf-winbase-getsystempowerstatus.md)
2. [Battery Information](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Power/battery-information.md)
3. [IOCTL_BATTERY_SET_INFORMATION](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Power/ioctl-battery-set-information.md)
4. [BATTERY_SET_INFORMATION](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Power/battery-set-information-str.md)
5. [BATTERY_INFORMATION](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Power/battery-information-str.md)

## 네트워크 적용 상태

사용자는 네트워크 변경 적용을 승인했습니다. 현재 도구와 설치된 Codex CLI의 공개 명령을 확인했으나 환경 게시 기능은 제공되지 않습니다. CLI의 cloud apply도 Git 변경 적용 명령이며 환경 게시 명령이 아닙니다. 저장된 다섯 도메인 초안은 게시·적용되지 않은 상태입니다. 권한 승인과 실제 도구의 실행 가능성을 구분하며, 적용했다고 보고하지 않습니다.
