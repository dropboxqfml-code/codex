# 별도 WMI 권한 비교 도구 — 검토 준비판

[별도 도구 ZIP](ATIVBatteryGuard-WMI-PERMISSION-REVIEW.zip) · [같은 버전 소스](ATIVBatteryGuard-WMI-PERMISSION-SOURCE.zip) · [범위·승인 조건](../ATIVBatteryGuard/WMI_PERMISSION_COMPARISON_REVIEW.md)

PacketPrivacy 적용 뒤에도 두 WMI 조회가 AccessDenied로 끝난 결과를 확인했습니다. 같은 TXT를 반복 요청하지 않고, 현재 토큰 상승 여부와 Connect/Query/Enumerate/ReadProperties 실패 단계를 확인할 별도 고정 조회 도구를 준비했습니다.

asInvoker 프로그램이며 자동 UAC·runas·메인 앱의 도구 실행이 없습니다. 메인 프로그램과 다른 로컬 폴더에 모두 압축 해제해 파일이 섞이지 않게 합니다. 관리자 비교 실행은 아직 승인받거나 수행하지 않았으므로 그 실행은 보류합니다. 같은 계정에서 한 번의 관리자 읽기 비교에 대한 별도 동의가 필요합니다.

두 고정 로컬 Active/version 속성만 읽으며 표준 출력뿐이고 임의 경로·쿼리·명령을 받지 않습니다. 사용자 이름·SID·장치 식별자·경로·원문 오류를 기록하지 않습니다. 서비스·드라이버·ACL·삼성 DLL·OEM·펌웨어 쓰기는 없으며 실제 충전 제어는 계속 미지원입니다.

현재 전체 테스트237개, 별도 배포 검증6개 통과, 메인 앱·Core·새 도구 빌드 경고·오류0개입니다. 미서명 개발 도구이며 Windows 실기·실제 토큰 API·관리자 비교는 미검증입니다. 삼성 원본 파일·사용자 TXT는 포함하지 않았습니다.

실행 ZIP SHA-256: e843210c5f79e0c8a130451e8586befcfd924e4afaa7ff1e7614d889bcaa72e8

이전 다운로드 파일은 아래에 그대로 보존합니다.

## 이전 WMI 암호화 연결·전송 경로 해석판

[실행 ZIP 다운로드](ATIVBatteryGuard-WMI-ACCESS-REVIEW.zip) · [같은 버전 소스 ZIP](ATIVBatteryGuard-WMI-ACCESS-SOURCE.zip) · [관측·수정 근거와 한계](../ATIVBatteryGuard/WMI_ACCESS_RESULT_AND_TRANSPORT_REVIEW.md)

기존 TXT에서 삼성 이름 후보 7개 Stopped/Manual, SABI NotFound, WMI 두 클래스 AccessDenied를 확인했습니다. 새 연결은 일반 사용자 권한으로 PacketPrivacy 암호화 인증을 명시합니다. 이 설정으로 노트북의 권한 거부가 해소되는지는 아직 미검증입니다. 관리자 권한·ACL 수정·드라이버 시작은 추가하지 않았습니다.

화면에 TXT 저장과 별개인 전송 경로 요약을 표시합니다. 순수 wsabi 요청 바이트 인코더도 준비했지만 실제 호출에는 연결하지 않았으며 충전 제어는 계속 미지원입니다. ZIP 전체를 새 폴더에 풀고 ATIVBatteryGuard.exe를 일반 권한으로 실행합니다. 같은 삼성 파일 정보 만들기에서 요약과 WMI 결과를 볼 수 있으며 이전 TXT·삼성 바이너리를 다시 제출할 필요는 없습니다.

테스트 228개·별도 배포 검증 6개 통과, WPF/XAML 빌드 경고·오류 0개. 미서명 개발판이며 새 Windows 연결·화면의 실기 동작은 아직 미검증입니다. 삼성 원본 DLL·EXE·사용자 원본 TXT는 포함하지 않습니다.

실행 ZIP SHA-256: e2cb5023c667549ac00e3fb9397d669c2cde938d0ad792a50345df75d8d6f8cc

이전 파일과 이력은 보존합니다.

## 이전 삼성 WMI 인스턴스·버전·활성 속성 확인판

[실행 ZIP 다운로드](ATIVBatteryGuard-WMI-INSTANCE-CHECK.zip) · [같은 버전 소스 ZIP](ATIVBatteryGuard-WMI-INSTANCE-SOURCE.zip) · [구현·확인 항목](../ATIVBatteryGuard/SAMSUNG_WMI_INSTANCE_INSPECTION.md)

ZIP 전체를 새 폴더에 풀고 ATIVBatteryGuard.exe를 일반 권한으로 실행합니다. 기존 삼성 파일 정보 만들기의 새 삼성 WMI 인스턴스 섹션에서 클래스별 조회 상태와 Active/version을 확인할 수 있습니다. Active=True는 배터리 보호 ON이 아니며 실제 충전 제어는 계속 미지원입니다.

이전 드라이버 확인판의 실제 노트북 실행과 TXT 생성은 확인됐습니다. 이번 WMI 조회의 실기 결과는 아직 미검증입니다. 앱 테스트 217개, 별도 배포 검증 6개 통과, WPF/XAML 빌드 경고·오류 0개입니다. 미서명 개발판이며 삼성 원본 DLL·EXE와 사용자 자료는 포함하지 않습니다. 기존 진단·TXT·삼성 바이너리의 재제출은 요구하지 않습니다.

파일 페이지에서 Download raw file로 내려받을 수 있습니다. 실행 ZIP SHA-256: 9c26bc1db4ac7ef77e7c3aaa8c759aa0c64f7008ae5b2a95062f33345ddfbfd5

이전 파일은 아래 이력과 함께 보존합니다.

## 이전 삼성/SABI 커널 드라이버 상태 확인판

[실행용 ZIP 다운로드](ATIVBatteryGuard-DRIVER-STATUS-CHECK.zip) · [같은 버전 소스 ZIP](ATIVBatteryGuard-DRIVER-STATUS-SOURCE.zip) · [구현·실기 확인 항목](../ATIVBatteryGuard/SAMSUNG_KERNEL_DRIVER_INSPECTION.md)

이 파일들은 채팅의 클라우드 로컬 경로 대신 GitHub 저장소에서 다운로드할 수 있습니다. ZIP 파일 페이지에서는 **Download raw file**을 선택합니다. 비공개 저장소라면 접근 가능한 GitHub 계정으로 로그인해야 합니다.

Windows 10 x64 / .NET Framework 4.8용 미서명 개발 미리보기입니다. 새 폴더에 ZIP 전체를 압축 해제하고 `ATIVBatteryGuard.exe`를 일반 권한으로 실행합니다. **삼성 파일 정보 만들기**에서 이름 후보의 등록·실행 상태·시작 방식과 SABI 연결 이름 비교를 확인합니다. 같은 진단·파일 목록·삼성 DLL의 재제출은 필요하지 않습니다.

정상 완료의 후보 미관측과 오류·권한 거부·시간 초과·일부 조회를 구분합니다. 후보 미관측을 드라이버 미설치로 단정하지 않으며 Running 관측도 실제 충전 제어를 활성화하지 않습니다. 실제 충전 제한은 계속 미지원입니다. 드라이버·서비스 변경·삼성 DLL 초기화·OEM 명령은 하지 않습니다.

검증 기록: 앱 테스트 204개 통과, 별도 배포 검증 테스트 6개 통과, WPF/XAML 빌드 경고·오류 0개. 새 Windows WMI 조회의 실기 동작은 아직 미검증입니다. 삼성 원본 DLL과 사용자 진단은 포함하지 않습니다.

SHA-256:

- 실행 ZIP: `cf7174470d50510085bb33b676fb193f6871c9bb0b9beb79011f0198a5a1c6b9`
- 소스 ZIP: `f02f79b4df6f560e31bac162cd0f3e375501e3cbb2b804d55907d236c678680b`

아래는 이전 배포 이력입니다. 새 확인판은 위의 고유 파일명을 사용하며 이전 ZIP은 보존합니다.

## 이전 Sabi3 x64 규약 수정·SABI 연결 확인판

[실행용 ZIP](ATIVBatteryGuard-SABI-LINK-CHECK.zip) · [같은 버전의 자체 소스](ATIVBatteryGuard-SOURCE.zip) · [정적 분석 기록](../ATIVBatteryGuard/SABI3_NATIVE_ABI_REVIEW.md)

제공받은 Sabi3.dll이 x64 파일임을 확인했습니다. 정적 분석에서 공개 예제의 4바이트와 다른 실제 11바이트 버퍼 접근을 확인해 관련 코드를 수정했습니다. 원본 DLL은 실행하거나 배포에 포함하지 않았습니다. x86 DLL은 이번 단계에 필요하지 않습니다.

새 실행판은 Windows의 SABI 연결 이름만 조회합니다. 삼성 DLL을 로드하거나 장치를 열거나 드라이버 명령을 보내지 않습니다. 연결 이름의 존재만으로 배터리 제어 지원을 판정하지 않으며, 실제 충전 제한은 계속 미지원입니다.

1. 이전 프로그램을 닫고 실행용 ZIP을 새 폴더에 모두 압축 해제합니다.
2. ATIVBatteryGuard.exe를 실행해 **삼성 파일 정보 만들기**를 누릅니다.
3. **정보 파일 위치 열기**에서 새 samsung-files-*.txt를 찾아 채팅에 첨부합니다. 이번에 확인할 항목은 **SABI 장치 연결 이름**입니다.

전체 소스 테스트 184개 통과, 실패·건너뜀 0개입니다. x64 net48 WPF/XAML 빌드와 실행 파일 정적 검사는 통과했으며 빌드 경고·오류는 0개입니다. 이번 SABI 이름 조회 기능은 실제 Windows에서 아직 시험하지 않았습니다.

SHA-256:

- 실행 ZIP: `e75e3b9cc386d804ff12c23da670dd6bbab7c41e8f7536d6506553b4908edf43`
- 소스 ZIP: `7458d5189c5ff6bb93a467dae8bd18d49aa6e425b4e39ee73a87dc50c78ec39d`

이전 배포본은 이력으로 보관합니다. 현재 실행판과 일치하는 소스는 위 ATIVBatteryGuard-SOURCE.zip입니다. 원본 삼성 파일·사용자 진단·외부 분석 자료는 저장소와 배포 ZIP에 포함하지 않습니다.
