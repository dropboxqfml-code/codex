# ATIV Battery Guard

현재는 [실제 WMI 규약 결과 반영과 CIMTYPE 판독 보완](WMI_PARAMETER_RESULT_AND_CIMTYPE_REVIEW.md) 단계입니다. 사용자 출력에서 공개 GUID 후보 일치·CallSabiFunction 존재·Windows 메서드 번호1·Bytes UInt8[]를 확인했으며 입출력 클래스는 Unknown입니다. 이전 도구의 불완전한 EmbeddedInstance 단독 판정을 표준 CIMTYPE와 함께 읽도록 수정했습니다. 실제 노트북 CIMTYPE 값은 아직 미관측입니다.

[입출력 형식 판독 보완판 다운로드](../downloads/README.md): 기존과 같은 ATIVBatteryGuard.WmiContractCheck.exe를 일반적으로 실행하며 상단에 판독기2가 표시됩니다. 고정 메타데이터만 읽고 qualifier 누락·불일치·충돌·형식 오류를 구분합니다. 기존 자료·관리자 비교는 다시 필요하지 않습니다. 전체274개 테스트와 Python6개 통과, 전체 빌드 경고·오류0개입니다. 수정 도구의 Windows 실기는 미검증이며 실제 배터리 보호 설정 조회·충전 제어는 계속 미구현입니다. 아래는 이전 단계 이력입니다.

현재 개발은 [WMI 비동기 프레임 처리와 클래스 규약 확인](WMI_EXCHANGE_AND_BINDING_CHECK.md)입니다. 취소·시간 초과 후 실제 작업 종료까지 중복을 차단하는 코드를 가짜 채널로 검증했고, 공개 WMI 전송과 Windows 클래스의 연결을 확인하는 별도 일반 권한 도구를 추가했습니다. 실제 OEM 전송 구현은 연결하지 않았습니다.

[새 확인 도구 다운로드](../downloads/README.md): ZIP을 새 폴더에 모두 풀고 ATIVBatteryGuard.WmiContractCheck.exe를 일반적으로 더블클릭합니다. 새 GUID 후보 일치 여부·메서드 번호·입출력 정의만 확인합니다. 이전 TXT·DLL·일반/관리자 비교는 다시 필요하지 않습니다. 관리자 실행은 요청하지 않습니다.

전체 테스트 **262개 통과**, Core·WPF·두 별도 도구 빌드 **경고·오류 0개**, Python 배포 검증 **6개 통과**입니다. 새 도구의 Windows 실기는 미검증이며 실제 충전 제어는 계속 미지원입니다. 아래 단계별 수치와 승인 대기는 당시 이력입니다.

[최신 개발: 구조적 WMI 응답 디코더](WMI_REPLY_DECODER_AND_PUBLIC_EVIDENCE.md)를 구현했습니다. API 미완료·응답 형식·길이·ACK 오류를 구분하고 실패 시 이전 데이터를 제거합니다. 기존 bool API와 지원 범위를 유지하며 배터리 상태 해석·실제 OEM 호출은 추가하지 않았습니다.

추가 공개 소스 두 곳에서 21바이트 전송 구조를 교차 확인했습니다. 현재 모델의 배터리 명령 계약은 여전히 미검증입니다. 전체 테스트244개 통과, 솔루션 빌드 경고·오류0개이며 실제 충전 제어는 계속 미지원입니다.

[권한 비교 결과 수신](WMI_PERMISSION_COMPARISON_RESULT.md): 일반 토큰에서 버전 클래스 Active=True/version16을 읽었고, 메서드 클래스는 열거에서 거부됐습니다. 상승 토큰에서는 두 클래스의 속성을 읽었습니다. 실제 배터리 명령이나 보호 상태를 확인한 결과는 아니며 충전 제어는 계속 미지원입니다. 비교 단계는 완료됐고 같은 진단을 다시 요청하지 않습니다.

[최신: WMI 권한 거부 지속과 별도 비교 도구](WMI_PERMISSION_COMPARISON_REVIEW.md): PacketPrivacy 적용 후에도 두 클래스 AccessDenied가 유지된 실제 결과를 확인했습니다. 자동 권한 상승 없이 현재 토큰과 실패 단계를 읽는 별도 asInvoker 도구를 준비했습니다. 관리자 비교는 아직 승인·실행하지 않았으며 메인 앱과 충전 제어는 그대로 일반 권한·미지원입니다.

이번 전체 테스트 237개 통과, WPF·Core·별도 비교 도구 빌드 경고·오류 0개입니다. 새 도구의 Windows 실기 실행은 미검증입니다. 아래는 이전 작업 이력입니다.

[최신 WMI 권한 결과와 다음 구현](WMI_ACCESS_RESULT_AND_TRANSPORT_REVIEW.md): 실제 TXT에서 SABI 이름 미관측, Samsung 이름 후보 7개 Stopped/Manual, 두 WMI 클래스 AccessDenied를 확인했습니다. 일반 사용자 권한을 유지한 암호화 WMI 연결을 명시하고 저장 성공과 조회 결과를 구분하는 화면 요약을 추가했습니다. 실제 거부 원인·해결 여부는 아직 미검증입니다.

기존 서비스 wsabi 규약의 순수 요청 인코더도 준비했으나 실제 호출 경로에는 연결하지 않았습니다. 이번 테스트 228개 및 배포 검증 6개 통과, WPF/XAML 빌드 경고·오류 0개입니다. 실제 설정 읽기·충전 제어는 계속 미검증·미지원이며 아래 설명은 이전 단계 이력입니다.

[다음 단계: 삼성 WMI 인스턴스·버전·활성 속성 확인](SAMSUNG_WMI_INSTANCE_INSPECTION.md)을 구현했습니다. 기존 삼성 파일 보고서에 로컬 WmiAcpiVersion의 Active/version과 WmiAcpiMethod의 Active를 클래스별로 표시합니다. 인스턴스 이름·장치 식별자는 읽지 않으며 OEM 메서드는 실행하지 않습니다. Active를 배터리 보호 상태로 해석하지 않고 실제 충전 제어는 계속 미지원입니다.

이전 드라이버 확인판의 노트북 실행·TXT 생성은 사용자가 확인했습니다. TXT 내부의 조회 결과는 아직 전달받지 않았습니다. 이번 공유 소스 테스트는 **217개 통과**, 별도 배포 검증 **6개 통과**, WPF/XAML 빌드는 **경고·오류 0개**입니다. 새 WMI 값 조회의 실제 Windows 동작은 아직 미검증이며 아래 기록은 이전 단계 이력입니다.

[현재 개발: 삼성/SABI 커널 드라이버 상태 조회](SAMSUNG_KERNEL_DRIVER_INSPECTION.md)를 구현했습니다. 기존 **삼성 파일 정보 만들기** 결과에 이름 후보의 등록·실행 상태·시작 방식과 SABI 연결 이름 비교를 함께 표시합니다. 정상 조회의 후보 미관측과 오류·시간 초과를 구분하고 원래 서비스 이름·경로·사용자 이름·식별자는 보고하지 않습니다. 드라이버·서비스 변경, 삼성 DLL 초기화, OEM 명령은 실행하지 않으며 실제 충전 제어는 계속 미지원입니다.

현재 환경에서 공유 소스 테스트 **204개 통과·실패/건너뜀 0개**, x64 net48 WPF/XAML 빌드 **경고·오류 0개**를 확인했습니다. 새 Windows WMI 조회의 실제 노트북 동작은 아직 미검증입니다. 아래 이전 단계의 검증 수치와 관측 기록은 이력입니다.

[제공받은 x64 Sabi3 정적 분석](SABI3_NATIVE_ABI_REVIEW.md)에서 실제 11바이트 호출자 버퍼와 초기화·드라이버 경로를 확인했습니다. 코드를 수정하고 장치를 열지 않는 SABI 연결 이름 조회를 추가했습니다. 실제 OEM 함수는 아직 호출하지 않습니다.

후속 사용자 TXT에서 SABI 연결 이름 NotFound를 확인했습니다. [최신 관측과 별도 WMI 전송 구조](SABI_LINK_RESULT_AND_WMI_REVIEW.md)에 근거와 한계를 기록하고 Sabi3 선행 조건 설명·순수 WMI 응답 검증을 보완했습니다. 이번 소스 변경을 확인하기 위해 같은 TXT를 다시 만들 필요는 없습니다.

이번 소스 검증은 191개 테스트 통과·WPF 빌드 경고/오류 0개입니다. 실행용 ZIP은 이전 SABI-LINK-CHECK판을 유지하며 이번 변경으로 새 ZIP을 만들지 않았습니다. 실제 WMI 메서드와 충전 제어는 아직 실행하지 않습니다.

[최신 초기화·드라이버 규약 검토](SABI3_INITIALIZATION_REVIEW.md): 함수 참조의 실제 Windows 결과를 확인하고, 응답을 해석하는 순수 코드를 추가했습니다. 다음 단계에는 x64 Sabi3.dll의 구현 자체를 정적으로 확인해야 하며 현재 DLL 초기화·OEM 조회·실제 제어는 실행하지 않습니다.

현재는 사용자가 실제 DLL 식별 결과를 제공해 Sabi3 연동 준비를 진행하고 있습니다. [이번 결과와 구현 범위](SABI3_COMPATIBILITY_REVIEW.md)를 참고하세요. 실행용 개발 미리보기와 명시적인 배포 검증 모드를 구분하며, 이전 보안 관련 문서는 이력으로 보관합니다.

현재 개발판은 **삼성 파일 정보 만들기**로 두 DLL과 두 EXE의 버전·구조·오프라인 서명·정적 참조·함수 이름을 로컬 TXT에 저장합니다. [범위·사용법·검증 한계](SAMSUNG_FILE_INSPECTION.md)를 참고하세요. 삼성 코드를 실행하지 않으며 실제 충전 제어는 계속 미지원입니다.

현재 함수 참조 분석·Sabi3 준비 판정 변경의 공유 소스 테스트는 173개 통과·실패 0개·건너뜀 0개이며 실제 WPF 빌드는 경고·오류 0개입니다. 이전 파일 식별은 사용자 TXT로 확인됐고 이번 확장 기능의 Windows 실기 실행은 아직 미검증입니다.

[최신 공개 제어 규약 조사](PUBLIC_CONTROL_PROTOCOL_REVIEW.md): 구형 Windows SABI3 명령 후보와 Galaxy Book ACPI 규약을 찾았으나 현재 ATIV의 DLL 없는 Windows 제어 경로는 미검증입니다. 실제 충전 제어는 계속 미지원입니다.

[설치 폴더에서 확인할 DLL 후보](SAMSUNG_DLL_CANDIDATES.md): 사용자 제공 `Setting` 경로를 참고용으로 기록하고 `Sabi3.dll`·`wsabi.dll`의 근거와 추가 검색 패턴을 구분했습니다. 실제 폴더 목록을 클라우드에서 열람한 결과는 아닙니다.

[사용량 초기화 후 다음 개발 메모](NEXT_DEVELOPMENT.md): 사용자가 찾은 두 DLL과 `BatteryToast.exe`·`PowerAudit.exe`의 확인 수준 및 다음 작업 순서를 정리했습니다.

## 현재 배터리 진단 결과 해석판

삼성 DLL 추출 없이 표준 Windows 배터리 드라이버의 요청 지원 여부를 읽는 진단을 추가했습니다. **진단 파일 만들기**로 생성되는 TXT의 ‘Windows 표준 배터리 드라이버의 요청 지원 여부’ 섹션에서 볼 수 있습니다. BatteryCharge/BatteryDischarge 지원 비트는 80% 충전 상한 지원의 증거가 아니며, 결과가 있어도 실제 제어는 미지원으로 유지합니다.

GENERIC_READ, QUERY_TAG(대기 0), QUERY_INFORMATION(정보 수준 0)만 사용합니다. 자체 보조 프로세스의 10초 제한과 최대 8개 인터페이스·16 KiB 결과 한도를 적용합니다. 장치 경로·태그·시리얼번호·고유 ID를 보고하지 않습니다. SET 요청이나 OEM 메서드는 실행하지 않습니다. 앱 시작이나 주기적 표시에서는 보조 조회를 실행하지 않습니다.

최신 진단에서 Windows 조회 성공과 `0x80000000`을 확인했습니다. 시스템 배터리 표시만 있고 표준 충전·방전 요청 지원 비트는 없습니다. 삼성 OEM 충전 상한의 가능성은 별도 미검증입니다.

현재 해석판은 이 차이를 메인 화면과 진단 TXT에서 설명합니다. 조회가 불완전하면 판단 불가로 남기고 재조회 시 이전 결과를 지웁니다. 같은 진단 파일을 다시 전달할 필요는 없습니다. 회귀 테스트 **138개 통과·실패 0개·건너뜀 0개**입니다. 새 해석 화면의 Windows 실행은 아직 미검증입니다. [구조·출처·검증 한계](WINDOWS_BATTERY_QUERY.md)에 상세히 기록했습니다. 아래 버전별 설명은 이전 단계의 이력입니다.


## 삼성 파일 추출 제외판의 현재 조건

사용자의 Samsung Settings에서 DLL을 추출할 수 없다는 조건으로 진행합니다. WPF 배포 프로젝트에서 삼성 파일 수집기와 위치 탐색기를 컴파일 제외했고 수집 확인 창과 UI도 제거했습니다. 장치 조회·로컬 설정·시뮬레이션·공식 문의문 복사는 유지합니다. 추출한 삼성 DLL은 필요하지 않습니다. 자체 Core DLL과 Windows 내장 프레임워크는 앱 구성 요소입니다.

Microsoft 공식 문서에서 일반 배터리 설정 요청 경로는 확인했지만, 검토한 인터페이스에는 지속되는 80% 충전 상한 항목이 없습니다. OEM WMI 입력 규약은 아직 확보하지 못했으며 실제 제어는 미지원입니다. [DLL 추출 없는 개발 경로와 실제 확인한 출처](DLL_INDEPENDENT_RESEARCH.md)를 참고하세요.

아래 수집 관련 설명은 이전 단계의 기록이며 현재 배포 기능이 아닙니다.


Samsung ATIV Book 9 Plus 계열을 위한 Windows 10 x64 배터리 상태·로컬 설정·읽기 전용 진단 앱입니다. C# / WPF / MVVM / .NET Framework 4.8을 사용합니다.

**현재 실제 80%/100% 충전 제한은 지원하지 않습니다.** 사용자 선택값, 실제 하드웨어 상태, Windows가 보고한 배터리 잔량은 별도로 표시합니다. Mock 모드는 메모리 안에서만 동작하는 시뮬레이션입니다.

이 디렉터리는 기존 자체 배포본의 C# 코드를 복원하고 프로젝트·화면·테스트·문서를 재구성한 작업본입니다. 원본 주석·테스트·문서 전체를 복구한 것은 아닙니다. 출처와 제한은 [RECOVERY.md](RECOVERY.md)에 기록합니다.

## Windows 10 빌드

개발용 PC에 다음 구성이 필요합니다.

- Visual Studio 2022의 **.NET 데스크톱 개발** 워크로드
- **.NET Framework 4.8 개발자 팩/대상 팩**
- .NET 8 SDK (SDK 형식 프로젝트와 portable 테스트용)

Visual Studio에서 `ATIVBatteryGuard.sln`을 열고 Release 구성을 빌드합니다. 개발자 터미널에서는 이 디렉터리를 기준으로 실행합니다.

```powershell
dotnet build ATIVBatteryGuard.sln -c Release
```

빌드된 `ATIVBatteryGuard.exe`와 같은 폴더의 앱 DLL·구성 파일을 함께 유지해 실행합니다. 일반 사용자 권한으로 실행하며, 관리자 권한 실행이나 드라이버 설치는 요구하지 않습니다.

Windows에서 빌드·회귀 테스트·제한 시간 90초의 GUI self-test를 함께 실행하려면 다음 명령을 사용합니다. 이 스크립트는 현재 Linux 환경에서 실행하지 않았습니다.

```powershell
powershell -File scripts/Test-Windows.ps1
```

## 현재 공식 지원 검토판

제품 시작 구성에서 OEM 파일 수집기를 해제했고 해당 버튼은 비활성화됩니다. 추가 삼성 파일 업로드는 요청하지 않습니다. 대신 장치 정보를 포함한 공식 문의문을 미리 보고 복사할 수 있습니다. 문의는 자동 전송하지 않습니다. 이 변경은 공식 사용권이나 충전 지원 여부를 확인했다는 뜻이 아닙니다.

실행용 파일은 `ATIVBatteryGuard-SUPPORT-REVIEW.zip`입니다. 새 suite는 114개 통과·실패 0개·건너뜀 0개이며 WPF 빌드는 경고·오류 0개입니다. 실제 새 Windows 문의 복사 동작은 미검증입니다. 아래 수집 관련 설명은 이전 단계의 구현 이력입니다.

## 동작 범위

- Windows 내장 배터리 API로 잔량·AC 연결·충전 상태 조회
- 사용자 희망 설정을 `%LOCALAPPDATA%\ATIVBatteryGuard\settings.json`에 저장
- 기본 실제 제어 어댑터의 모든 쓰기 요청 거부
- Mock 모드의 80%/100% 선택 시뮬레이션
- 모델·BIOS·Windows 정보와 읽기 전용 진단의 로컬 저장
- 삼성 WMI 클래스 `WmiAcpiVersion`, `WmiAcpiMethod`, `DataBuffer`의 **정의만** 확인하는 진단
- 사용자 확인 후 설치된 Samsung Settings 앱의 EXE·DLL을 제한적으로 복사하는 정적 분석 ZIP

진단은 삼성 DLL을 로드하거나 WMI 제어 메서드를 호출하지 않습니다. 클래스가 발견되어도 충전 제한 지원으로 판단하지 않습니다. 유효한 Windows 배터리 측정값을 그대로 표시하며, 0%도 유효한 값입니다.

Settings 분석은 HKLM의 정확한 Samsung Settings 등록 정보와 허용된 전용 설치 폴더에 한정합니다. **Settings 분석 파일 만들기**를 누른 뒤 포함 내용을 확인해야 추가 분석용 경로 탐색·복사를 시작합니다. 설치·아이콘 경로가 모두 없는 등록 앱에만 전용 후보 폴더 최대 6곳을 확인합니다. 제공된 경로가 거부된 경우에는 대체 조회를 하지 않습니다. 파일을 확보하지 못하면 원인을 기록한 보고서만 ZIP으로 생성합니다. 실행용 배포 파일 이름은 `ATIVBatteryGuard-SETTINGS-ANALYSIS.zip`입니다.

## 검증

2026-10-31(한국 시간) 이전 WMI 정의 진단판은 .NET Framework 4.8 x64 WPF/XAML 빌드와 portable 테스트 **78개 통과, 실패 0개, 건너뜀 0개**를 확인했습니다. 사용자의 후속 화면과 진단 파일에서 Windows 앱 실행, 배터리 62%·AC 연결 안 됨·방전 중 표시, 세 WMI 클래스의 실제 정의 조회도 확인했습니다. 이전의 0%는 당시의 정상 관측이며 현재 값으로 고정하지 않습니다.

새 Settings 앱 분석 기능의 .NET Framework 4.8 x64 WPF 빌드는 **경고 0개·오류 0개**로 성공했습니다. 새 경계 검사 30개를 포함한 portable 회귀 테스트는 **108개 통과·실패 0개·건너뜀 0개**입니다. 이번에 실제로 다시 실행한 결과이며 과거 테스트 수치를 재사용하지 않았습니다.

```powershell
dotnet run --project tests/ATIVBatteryGuard.PortableTests.csproj -c Release -- --report reports/portable-tests.json
```

WMI 정의 진단판의 노트북 실행은 확인됐지만 새 Settings 파일 수집의 Windows 동작은 아직 검증하지 않았습니다. 검증 범위와 Windows 수동 확인 절차는 [TEST_PLAN.md](TEST_PLAN.md)를 참고하세요.

사용법은 [USER_GUIDE.md](USER_GUIDE.md), 계층 구조는 [ARCHITECTURE.md](ARCHITECTURE.md), 하드웨어 근거는 [HARDWARE_RESEARCH.md](HARDWARE_RESEARCH.md), 개인정보와 권한은 [SECURITY.md](SECURITY.md)에 설명합니다.
