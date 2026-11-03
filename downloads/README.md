# WMI 메모리 채널·통합 경로 개발 소스

[최신 개발 소스 ZIP](ATIVBatteryGuard-WMI-PIPELINE-SOURCE.zip) · [구현·검증·남은 조건](../ATIVBatteryGuard/WMI_BOUND_CHANNEL_AND_PIPELINE.md) · [기존 실기 확인 프로그램](ATIVBatteryGuard-WMI-PARAMETER-CHECK.zip)

요청 인코더·비동기 조정기·메서드 바인더·응답 검증기를 명시적으로 주입한 메모리 snapshot 경계로 연결했습니다. 잘못된 요청의 무호출, 중첩 필드 오류/byte 오류 구분, 취소·시간 초과 뒤 실제 작업 종료 전 Busy와 늦은 응답 처리를 통합 검증했습니다. 기존 byte decoder와 bool validator의 동작을 유지합니다.

전체297개 테스트 통과·실패/건너뜀0개, 4개 프로젝트 빌드 경고·오류0개입니다. 가짜 transport만 사용했으며 실제 WMI/native/OEM 구현·인스턴스 자동 선택·앱 등록은 없습니다. 이번에는 개발 소스를 제공하고 노트북에서 새로 실행·제출할 항목은 없습니다. 기존 실행판은 그대로 보존합니다.

현재 모델의 배터리 명령 의미·읽기 안전성·실제 응답 계약은 여전히 미확정이고 실제 보호 상태 조회·충전 제어는 미구현·Unsupported입니다. 공개 포크·이슈 후속 조사에서도 새 근거는 확보하지 못했습니다. 소스 ZIP에는 자체 소스·문서만 있으며 원본 삼성 바이너리·사용자 TXT·외부 코드·빌드 출력은 없습니다.

소스 ZIP SHA-256: 366d08d2f96634630c5af72c0cdbe0179993533e4e2a273980fd7c4a1bd8c0fa

아래는 이전 프로그램과 개발 이력입니다.

## 이전 WMI 형식 확인 완료·메모리용 바인더 개발 소스

[최신 개발 소스 ZIP](ATIVBatteryGuard-WMI-BINDING-SOURCE.zip) · [실제 결과·구현·남은 조건](../ATIVBatteryGuard/WMI_MATCHED_BINDING_AND_OFFLINE_ENVELOPE.md) · [노트북에서 확인한 판독기2 프로그램](ATIVBatteryGuard-WMI-PARAMETER-CHECK.zip)

판독기2의 실제 결과로 GUID 후보·메서드·입출력 DataBuffer·Bytes UInt8[]의 형식 일치를 확인했습니다. 기존 Unknown은 해소됐고 같은 규약 진단·파일 목록·관리자 비교는 다시 필요하지 않습니다. WindowsMethodId1은 관측값 그대로 유지합니다.

최신 내부 코드는 상세 메타데이터를 바탕으로 inData/Bytes 요청 포장과 outData/Bytes 응답 추출을 기존 프레임 인코더·검증기에 연결합니다. 분리된 메모리 snapshot만 처리하며 WMI/native 객체 생성·OEM 호출·실제 전송 채널은 없습니다. 이번에는 소스 ZIP을 제공하고 새 노트북 실행을 요청하지 않습니다. 기존 프로그램 ZIP은 실기 확인에 사용한 판독기2로 보존하며 이번 코드가 들어간 새 실행판으로 표시하지 않습니다.

전체286개 테스트 통과·실패/건너뜀0개, Core·WPF·두 별도 도구 빌드 경고·오류0개입니다. 현재 모델의 실제 배터리 명령 의미·읽기 안전성·응답 계약은 여전히 미확정이고 실제 충전 제어는 Unsupported입니다. 소스 ZIP에는 자체 소스·문서만 있으며 삼성 바이너리·사용자 원문 TXT·외부 코드·실행 파일은 없습니다.

소스 ZIP SHA-256: 22739035c1aaee8e3a53fa4ffd05fb136f2d878580fadf70f8783bb288192f78

아래는 이전 프로그램과 관측 이력입니다.

## 이전 WMI 입출력 형식 판독 보완판 — 판독기 2

[새 프로그램 ZIP 다운로드](ATIVBatteryGuard-WMI-PARAMETER-CHECK.zip) · [같은 버전 소스 ZIP](ATIVBatteryGuard-WMI-PARAMETER-SOURCE.zip) · [실제 결과·공식 근거·수정 범위](../ATIVBatteryGuard/WMI_PARAMETER_RESULT_AND_CIMTYPE_REVIEW.md)

사용자 결과에서 공개 GUID 후보 일치·메서드 존재·Windows 메서드 번호1·Bytes UInt8[]를 확인했습니다. 입출력 Unknown은 미확정으로 보존합니다. 기존 도구에서 누락한 표준 CIMTYPE 표기를 읽도록 고쳤으며 실제 노트북 CIMTYPE와 이번 실행의 권한 수준은 아직 미관측입니다. 번호1을 Linux0이나 배터리 명령으로 치환하지 않습니다.

ZIP 전체를 메인 앱과 다른 새 로컬 폴더에 풀고 **ATIVBatteryGuard.WmiContractCheck.exe**를 일반적으로 실행합니다. 상단의 **메타데이터 판독기: 2 (CIMTYPE 포함)**과 inData/outData의 **CIMTYPE·판정**이 새 확인 대상입니다. 고정 정의의 qualifier 누락·다른 정의·잘못된 형식·충돌을 독립 표시하며 원문 클래스명은 내보내지 않습니다. 이전 TXT·삼성 DLL·권한 비교는 다시 필요하지 않습니다. 관리자 실행은 요청하지 않습니다.

전체274개 테스트와 Python6개 통과, 4개 프로젝트 빌드 경고·오류0개입니다. 이전 도구의 클래스 조회는 이번 사용자 출력으로 실기 확인됐지만 수정 판독기2의 Windows 실행은 미검증입니다. 실제 OEM 호출·배터리 보호 설정 조회·충전 제어는 미구현이며 Unsupported를 유지합니다. 삼성 원본 바이너리·사용자 원문 출력은 포함하지 않습니다.

SHA-256:

- 실행 ZIP: 49e410aa46ee55423ad44d4f9213ea7a4e1c34d64fcddae448b65997af9a608a
- 소스 ZIP: b4f555baae75802ec3914c48e835acd7bc4069513183f3e1ce6e71b9b56c4723

아래 이전 프로그램과 관측 이력은 그대로 보존합니다.

## 이전 WMI 정적 클래스 규약 확인 도구

[새 도구 ZIP 다운로드](ATIVBatteryGuard-WMI-CONTRACT-CHECK.zip) · [같은 버전 소스 ZIP](ATIVBatteryGuard-WMI-CONTRACT-SOURCE.zip) · [구현·확인 항목·한계](../ATIVBatteryGuard/WMI_EXCHANGE_AND_BINDING_CHECK.md)

ZIP 전체를 메인 앱과 다른 새 로컬 폴더에 풀고 **ATIVBatteryGuard.WmiContractCheck.exe**를 일반적으로 더블클릭합니다. 새 WmiAcpiMethod/DataBuffer 클래스 정의의 조회 상태·공개 GUID 후보 일치·WmiMethodId·입출력/Bytes 형식만 확인하고 출력 내용을 복사한 뒤 Enter로 닫습니다. 기존 배터리 진단·삼성 파일 TXT·삼성 DLL·일반/관리자 비교를 다시 제출할 필요는 없습니다.

asInvoker 도구이며 관리자 실행을 요청하지 않습니다. 권한 거부·시간 초과가 나오면 그대로 사용합니다. 실제 GUID·인스턴스·토큰·사용자 이름·SID·경로는 출력하지 않습니다. OEM 메서드 실행·삼성 DLL 로드·서비스/드라이버/ACL·펌웨어 변경과 네트워크 통신은 없습니다. 정의 일치는 배터리 명령의 안전성·실제 응답 계약·충전 제어 지원의 증거가 아닙니다.

개발 소스에는 비동기 프레임 처리도 포함했지만 가짜 채널만 검증했고 실제 OEM 채널이나 앱 호출 경로는 없습니다. 전체262개 테스트와 Python6개 통과, Core·WPF·두 별도 도구 빌드 경고·오류0개입니다. 새 도구의 Windows 실기는 미검증인 미서명 개발판이며 실제 충전 제어는 계속 미지원입니다. 삼성 원본 바이너리·사용자 원문 보고서는 포함하지 않습니다.

SHA-256:

- 실행 ZIP: 5fb0dee6779294c21b4c64c5b8000a4672a65c64394795b51099379189c67f3a
- 소스 ZIP: 3b3cea3677f8181e1625894a2d20a413b77f949534ab4010f72af076c0bb1c13

아래는 이전 실행판과 관측 이력입니다. 새 파일은 별도 이름으로 제공하고 이전 ZIP은 보존합니다.

## 이전 WMI 응답 디코더 개발 소스

[최신 개발 소스 ZIP](ATIVBatteryGuard-WMI-REPLY-SOURCE.zip) · [구현과 추가 공개 근거](../ATIVBatteryGuard/WMI_REPLY_DECODER_AND_PUBLIC_EVIDENCE.md)

이번 변경은 API 미완료·응답 형식·배열 경계·길이·ACK를 구분하는 순수 응답 처리 코드입니다. 기존 bool 인터페이스를 유지하며 실제 OEM 호출이나 배터리 제어를 추가하지 않았습니다. 현재 모델의 배터리 조회 명령·실제 응답 계약은 여전히 미검증입니다.

전체 테스트244개 통과, Core·WPF·비교 도구 빌드 경고·오류0개입니다. 추가 공개 두 소스는 프레임 구조만 교차 확인했으며 드라이버 코드를 제품에 복사·실행하지 않았습니다. 소스 ZIP에는 실행 파일·원본 삼성 바이너리·사용자 원문 보고서가 없습니다. 같은 진단을 다시 실행할 필요는 없습니다.

소스 ZIP SHA-256: 3d09947e26109f84637fbe97822f28512812a0e42e9ede5d8b5b409dcd2f615d

기존 실행판과 관측 이력은 아래에 보존합니다.

## 이전 별도 WMI 권한 비교 도구 — 검토 준비판

**비교 결과 수신 완료:** 일반 토큰은 버전 속성(Active=True/version16)을 읽고 메서드 클래스 열거에서 0x80041003으로 거부됐습니다. 상승 토큰은 두 클래스의 속성을 읽었습니다. [결과와 해석 범위](../ATIVBatteryGuard/WMI_PERMISSION_COMPARISON_RESULT.md)에 기록했으며 같은 비교를 다시 요청하지 않습니다. 실제 충전 제어는 계속 미지원입니다. 기존 ZIP은 그 관측에 사용한 파일로 보존합니다.


**2026-11-03 승인 반영:** 사용자가 같은 Windows 계정에서 고정된 두 WMI 속성의 일반 권한/한 번의 관리자 권한 읽기 비교를 승인했습니다. [실행 순서](../ATIVBatteryGuard/WMI_PERMISSION_COMPARISON_RUN.md)를 따릅니다. 기존 ZIP을 그대로 사용하며 ZIP 내부의 승인 대기 표시는 패키징 시점의 기록입니다. 실제 결과는 아직 받지 않았습니다. 아래 보류 설명은 승인 전 이력입니다.

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
