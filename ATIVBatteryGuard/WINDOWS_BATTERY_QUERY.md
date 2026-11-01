# Windows 표준 배터리 요청 지원 조회

삼성 DLL을 추출하거나 호출하지 않고, Microsoft가 공개한 배터리 장치 조회만 사용합니다. 기존 `진단 파일 만들기`의 상세 TXT에 새 섹션을 추가했습니다. 실제 충전 제어는 계속 미지원입니다.

## 조회 범위

- SetupDi로 현재 배터리 인터페이스를 최대 8개 열거합니다.
- 장치 핸들은 GENERIC_READ와 OPEN_EXISTING으로만 엽니다. 쓰기 접근 권한을 요청하지 않습니다.
- IOCTL_BATTERY_QUERY_TAG는 대기 시간 0으로 호출합니다. 태그는 다음 조회에 일시적으로만 사용하고 저장·보고하지 않습니다.
- IOCTL_BATTERY_QUERY_INFORMATION은 BatteryInformation 정보 수준(0)만 사용합니다. 12바이트 입력과 36바이트 응답을 검사합니다.
- 응답에서는 Capabilities 정수만 보관하고 BatteryCharge/BatteryDischarge 요청 지원 비트를 해석합니다.
- SET_INFORMATION, 임의 IOCTL, OEM 메서드, 시리얼번호·고유 ID 정보 수준은 호출하지 않습니다.

지원 비트가 있더라도 80%/100% 충전 상한과 설정 유지 기능이 있다는 증거는 아닙니다. 표시가 없더라도 OEM 기능 전체의 부재로 확정하지 않습니다. 접근 거부·조회 실패·빈 장치·시간 초과는 각각 표시하고 false 지원 값으로 대체하지 않습니다. 배터리 잔량이나 실제 제어 어댑터 상태는 이 보고서로 바꾸지 않습니다.

## 결과 해석 표시

상세 진단을 실행하면 메인 화면과 TXT에 해석을 함께 표시합니다. 전체 조회가 완료되고 범위 제한이 없을 때 일반 시스템 배터리의 비트를 비교합니다. 시스템 배터리 표시가 없거나 단기 배터리(예: UPS)인 항목은 노트북의 지원 판정에 사용하지 않습니다. 대상이 없거나 일부 결과가 누락되면 판단 불가로 남깁니다.

여러 대상 중 하나라도 요청 지원 비트가 있으면 지원 표시가 있음을 알리지만 실제 제어를 켜지 않습니다. 모든 대상의 두 비트가 없으면 현재 표준 경로를 제어에 사용하지 않는다고 설명합니다. OEM 충전 상한 지원과는 별개입니다. 결과는 이번 앱 실행에서만 보관하고, 재조회 시 이전 결과를 지웁니다. 조회 후 파일 저장만 실패한 경우에는 관측한 화면 결과를 유지하고 저장 오류를 별도로 표시합니다.

## 실행과 종료 처리

동기식 장치 호출이 메인 창을 붙잡지 않도록 이미 실행 중인 자체 EXE를 보조 조회 모드로 실행합니다. 삼성 프로그램이나 외부 셸은 실행하지 않습니다. 이 기능은 사용자가 상세 진단 생성을 선택했을 때만 실행하며 주기적 배터리 표시나 앱 시작에는 추가하지 않았습니다.

부모는 보조 프로세스에 10초 제한을 두고, 초과하면 종료를 요청한 뒤 최대 1초만 추가 대기합니다. 종료가 지연되면 단일 슬롯을 유지해 반복 요청으로 보조 프로세스가 계속 늘어나지 않도록 합니다. 앱 종료 시에도 저장해 둔 자체 보조 프로세스만 종료 요청합니다. 잘못 동작하는 드라이버가 OS 수준의 종료를 지연시킬 가능성까지 프로그램이 제거할 수 있는 것은 아닙니다.

보조 모드는 `%LOCALAPPDATA%\ATIVBatteryGuard`의 `battery-capabilities-worker-<GUID>.json` 새 파일만 생성합니다. 기존 파일은 덮어쓰지 않습니다. 결과는 최대 16 KiB이며 상태 코드·목록 순번·지원 비트만 담습니다. 경로·태그·시리얼번호·고유 ID·예외 원문은 내보내지 않습니다. 정상 종료 후 부모가 결과를 확인하고 임시 파일을 정리합니다.

결과 프로토콜은 필수 필드, 버전, 최대 장치 수, 인덱스, 단일 JSON 객체, 깊이 제한과 객체 수를 검사합니다. 문자열 안의 괄호나 이스케이프 따옴표를 고려하면서 두 번째 JSON 문서나 후행 쓰레기 데이터는 거부합니다. 실패 응답의 이전 비트 값은 보존하지 않습니다.

## 검증과 한계

조회 기능을 처음 배포할 때 공유 소스의 회귀 테스트 130개 통과·실패 0개·건너뜀 0개를 확인했습니다. 네이티브 ABI·조회 상수·프로세스 수명·경로 비노출은 별도 코드 검토를 수행했습니다. 이후 사용자가 전달한 아래 진단으로 실제 Windows 노트북에서 한 번의 정상 조회 결과를 확인했습니다. 시간 초과·종료 지연 등 모든 실행 경로가 실제 장치에서 검증된 것은 아닙니다. Linux에서의 빌드·자동 테스트나 정상 조회를 실제 충전 제한 성공으로 주장하지 않습니다.

## 사용자 노트북에서 확인한 결과 — 2026-11-01

사용자가 전달한 `diagnostics-20261101T015228` 보고서의 관측입니다. 원본 진단 파일은 저장소나 배포 ZIP에 포함하지 않습니다.

| 항목 | 관측 결과 |
| --- | --- |
| 모델 / BIOS | 940X3G/930X3G / P05ACJ.128.140819.dg |
| OS | Windows 10 Home 10.0.19045, x64 |
| 표준 배터리 조회 | 전체 조회 완료, 인터페이스 1개 조회 완료 |
| Capabilities | `0x80000000` — `BATTERY_SYSTEM_BATTERY`만 표시 |
| 표준 충전 / 방전 요청 | `BATTERY_SET_CHARGE_SUPPORTED`와 `BATTERY_SET_DISCHARGE_SUPPORTED` 모두 표시 없음 |

현재 드라이버는 표준 충전·방전 요청의 지원을 표시하지 않습니다. 이 경로를 제어용으로 채택하거나 SET 요청을 시험하지 않습니다. 이 결과는 삼성 OEM 충전 상한 기능의 부재나 Windows 8에서 지원됐다는 과거 보고의 진위를 판정하지 않습니다.

같은 보고서의 GetSystemPowerStatus 잔량은 53%, WMI 잔량은 52%였습니다. 순차 조회에서 1%p 차이가 났으며 값을 보정하거나 서로 덮어쓰지 않습니다. 삼성 WMI 클래스와 메서드 정의도 조회됐지만 OEM 메서드는 호출하지 않았습니다. 실제 80%/100% 충전 상한의 명령과 상태 조회 규약은 여전히 미검증입니다.

## 실제로 확인한 Microsoft 공개 원본

- [배터리 장치 열거](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Power/enumerating-battery-devices.md)
- [QUERY_TAG](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Power/ioctl-battery-query-tag.md)
- [QUERY_INFORMATION](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Power/ioctl-battery-query-information.md)
- [BATTERY_INFORMATION 지원 비트](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Power/battery-information-str.md)
- [Windows SDK poclass.h](https://github.com/microsoft/win32metadata/blob/main/generation/WinSDK/RecompiledIdlHeaders/shared/poclass.h)
- [Windows SDK devioctl.h](https://github.com/microsoft/win32metadata/blob/main/generation/WinSDK/RecompiledIdlHeaders/shared/devioctl.h)

현행 SDK에는 충전원·충전기 상태 등에 관한 추가 항목도 있습니다. 이번 구현은 두 조회 IOCTL과 기본 BatteryInformation만 허용하며 다른 항목을 임의로 사용하지 않습니다.
