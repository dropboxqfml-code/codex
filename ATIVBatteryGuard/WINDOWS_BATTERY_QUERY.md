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

## 실행과 종료 처리

동기식 장치 호출이 메인 창을 붙잡지 않도록 이미 실행 중인 자체 EXE를 보조 조회 모드로 실행합니다. 삼성 프로그램이나 외부 셸은 실행하지 않습니다. 이 기능은 사용자가 상세 진단 생성을 선택했을 때만 실행하며 주기적 배터리 표시나 앱 시작에는 추가하지 않았습니다.

부모는 보조 프로세스에 10초 제한을 두고, 초과하면 종료를 요청한 뒤 최대 1초만 추가 대기합니다. 종료가 지연되면 단일 슬롯을 유지해 반복 요청으로 보조 프로세스가 계속 늘어나지 않도록 합니다. 앱 종료 시에도 저장해 둔 자체 보조 프로세스만 종료 요청합니다. 잘못 동작하는 드라이버가 OS 수준의 종료를 지연시킬 가능성까지 프로그램이 제거할 수 있는 것은 아닙니다.

보조 모드는 `%LOCALAPPDATA%\ATIVBatteryGuard`의 `battery-capabilities-worker-<GUID>.json` 새 파일만 생성합니다. 기존 파일은 덮어쓰지 않습니다. 결과는 최대 16 KiB이며 상태 코드·목록 순번·지원 비트만 담습니다. 경로·태그·시리얼번호·고유 ID·예외 원문은 내보내지 않습니다. 정상 종료 후 부모가 결과를 확인하고 임시 파일을 정리합니다.

결과 프로토콜은 필수 필드, 버전, 최대 장치 수, 인덱스, 단일 JSON 객체, 깊이 제한과 객체 수를 검사합니다. 문자열 안의 괄호나 이스케이프 따옴표를 고려하면서 두 번째 JSON 문서나 후행 쓰레기 데이터는 거부합니다. 실패 응답의 이전 비트 값은 보존하지 않습니다.

## 검증과 한계

공유 소스의 회귀 테스트 130개 통과·실패 0개·건너뜀 0개를 확인했습니다. 네이티브 ABI·조회 상수·프로세스 수명·경로 비노출은 별도 코드 검토를 수행했습니다. 실제 Windows 장치 조회와 보조 프로세스 실행 결과는 아직 미검증입니다. Linux에서의 빌드·자동 테스트를 실제 충전 제한 성공으로 주장하지 않습니다.

## 실제로 확인한 Microsoft 공개 원본

- [배터리 장치 열거](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Power/enumerating-battery-devices.md)
- [QUERY_TAG](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Power/ioctl-battery-query-tag.md)
- [QUERY_INFORMATION](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Power/ioctl-battery-query-information.md)
- [BATTERY_INFORMATION 지원 비트](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Power/battery-information-str.md)
- [Windows SDK poclass.h](https://github.com/microsoft/win32metadata/blob/main/generation/WinSDK/RecompiledIdlHeaders/shared/poclass.h)
- [Windows SDK devioctl.h](https://github.com/microsoft/win32metadata/blob/main/generation/WinSDK/RecompiledIdlHeaders/shared/devioctl.h)

현행 SDK에는 충전원·충전기 상태 등에 관한 추가 항목도 있습니다. 이번 구현은 두 조회 IOCTL과 기본 BatteryInformation만 허용하며 다른 항목을 임의로 사용하지 않습니다.
