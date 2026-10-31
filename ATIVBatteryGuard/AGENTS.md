# ATIV Battery Guard — Codex Project Instructions

## 프로젝트 정의
- 목적: Samsung ATIV Book 9 Plus에서 구형 Samsung Settings의 Battery Life Extender와 유사한 Windows 충전 제한 앱 개발.
- 대상 OS: **Windows 10 x64**. 실제 모델과 BIOS 버전은 실행 시 WMI로 감지하고, NP940X3G 계열을 연구 우선순위로 둔다.
- 개발 언어/GUI: **C# / WPF / .NET Framework 4.8 / MVVM**. Visual Studio 2022에서 빌드 가능한 형태로 작성한다.
- 프로젝트 UI 기본 언어: 한국어. 코드 식별자와 기술 문서는 필요한 경우 영어 허용.
- 1단계 목표: 배터리 상태 조회, UI, 로컬 설정 영속성, read-only 진단, Mock 시뮬레이션, 테스트.

## 절대 준수해야 할 하드웨어 안전 규칙
1. 확인되지 않은 삼성 EC/BIOS/SABI/ACPI/UEFI 펌웨어 인터페이스에 쓰기 작업을 하지 않는다.
2. Linux `samsung-laptop.c`에서 기능이 보인다는 사실만으로 이 장치의 Windows 호환성이나 안전성이 입증되지는 않는다. 해당 코드를 포팅하여 실제 장치에 실행하지 않는다.
3. 검증되지 않은 커널 드라이버, 임의 포트 I/O, 물리 메모리 접근, 레지스트리 펌웨어 설정 변경, BIOS 플래시를 구현하지 않는다.
4. Secure Boot 해제, Windows Defender 예외, 드라이버 서명 우회, 테스트 서명 모드 전환을 요구하지 않는다.
5. 하드웨어 지원 여부가 Unknown/Unsupported면 실제 제어 버튼을 비활성화하고 쓰기 경로는 실패하도록 한다.
6. `desiredMode`(사용자 희망 설정), `actualMode`(장치 read-back), `batteryChargePercent`(Windows 측정값)는 서로 다른 데이터다. 절대 혼동하지 않는다.
7. 배터리 잔량 80%나 '충전 중 아님' 상태는 충전 제한 성공 증거가 아니다. 초기 구현은 실제 충전 제한을 제공하지 않는다.

## 보안 및 개인정보
- 실행 중 네트워크 통신 **0건**. 로그인, 클라우드, telemetry, 업데이트 체크, 외부 웹뷰, CDN, 원격 오류전송 금지.
- 기본 구성은 Microsoft/Windows 내장 API 우선. 불필요한 NuGet 종속성이나 설치 프로그램 포함 금지.
- 로그와 진단 데이터는 로컬에만 저장한다. 시리얼번호, 사용자 이름, 고유 식별자를 기본 로그에 남기지 않는다.
- UI는 일반 권한으로 실행한다. 관리자 권한은 필요성이 검증되고 사용자 승인된 장래의 별도 구성 요소에만 사용한다.
- 설치/실행만으로 서비스, 자동 실행, 작업 스케줄러, 드라이버, 시스템 정책을 등록하거나 변경하지 않는다.

## 설계 원칙
- WPF MVVM: View에서 하드웨어 직접 접근하지 말고 ViewModel → Service → Hardware Adapter로 분리한다.
- 하드웨어 인터페이스는 `IChargeLimitController`를 통해 추상화한다.
- 기본 Adapter = `UnsupportedChargeLimitController`. 이 Adapter의 모든 쓰기 요청은 실패해야 한다.
- `MockChargeLimitController`는 개발/시연에만 사용한다. Mock 표기를 항상 보여주고 실제 적용 성공으로 표시하지 않는다.
- Win32 `GetSystemPowerStatus`는 배터리 상태 조회에만 사용하며 충전 상한 제어 API로 취급하지 않는다.
- WMI 조회는 읽기 전용으로 제한하고 예외/권한 거부 시 안전하게 처리한다.
- 로컬 사용자 설정 경로는 `%LOCALAPPDATA%\ATIVBatteryGuard\settings.json`.
- 설정 저장은 원자적 파일 교체, 스키마 버전, 유효성 검증, 손상 파일 복구를 고려한다.
- 설정 로드 시 사용자 희망 모드를 복원하되 실제 펌웨어 설정 확인 전에 '적용됨'으로 표시하지 않는다.
- 후속 단계에서 검증된 제어 경로가 발견되면 부팅 시 실제 상태 read-back 및 필요 시 복원하는 Windows Service를 설계할 수 있지만, 1단계에서 서비스 자동 등록 및 실 하드웨어 쓰기는 금지한다.

## UI/UX
- Samsung Settings를 참고하되 로고·이미지·코드의 무단 복제는 피한다.
- 80% 보호 모드와 100% 일반 모드를 직관적으로 표시한다.
- '사용자 선택값', '실제 하드웨어 상태', '배터리 잔량/AC 상태'를 별도로 표시한다.
- 지원 여부와 오류 메시지를 숨기지 않는다.
- 배터리 데이터가 제공되지 않는 경우 Unknown으로 표시한다.
- Mock 모드는 눈에 띄게 '시뮬레이션 — 실제 충전 제어 없음'으로 표시한다.

## 코딩, 검증, 보고
- 먼저 실제 파일을 생성·수정하고 기능을 구현한다. 계획만 제안하고 종료하지 않는다.
- 자동화 테스트를 작성한다: 설정 round-trip/손상 복구, Mock 모드, Unsupported 쓰기 거부, 상태 변환.
- 빌드/테스트가 불가능한 환경에서는 실행했다고 주장하지 않는다. 실제 실행 결과와 미실행 항목을 구분하여 보고한다.
- Windows 10 빌드/실행 방법 및 필요한 VS 구성 요소를 README.md에 적는다.
- HARDWARE_RESEARCH.md에서는 '확인된 사실 / 가정 / 아직 검증되지 않은 항목'을 구분한다.
- 커널/펌웨어 제어 코드 추가 작업은 사용자에게 별도의 명시적 승인을 받은 뒤 안전성과 모델 적합성이 입증된 범위에서만 진행한다.
- Codex 작업 완료 요약에는 수정 파일, 테스트 실행 여부, 제한사항, 다음 검증 과제를 포함한다.
