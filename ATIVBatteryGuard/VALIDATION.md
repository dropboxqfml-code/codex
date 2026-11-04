# Settings 앱 분석판 검증 기록

## 무호출 사전 검증 점검 도구 — 2026-11-04

- 전체 **329 passed, 0 failed, 0 skipped (329 registered)**: reports/wmi-preflight-only-tests.json 및 .log. 새 네 그룹은 허용된 오류 분류, 모든 유효 enum 조합의 준비 조건, 잘못된 값 처리, 개인정보와 불변성을 검사합니다. 실제 Windows/OEM을 사용하지 않습니다.
- Core·WPF·기존 세 별도 도구·새 WmiPreflightCheck 등 전체6개 프로젝트 x64 net48 Release 빌드 **경고0개·오류0개**: reports/wmi-preflight-only-build.log. 테스트 프로젝트도 별도 빌드 경고·오류0개입니다.
- 새 네이티브 진단은 원래 준비 경로의 고정 모델/BIOS·metadata/id1·DirectRead/단일Active/입력CIMTYPE/메모리버퍼 조건을 유지합니다. 원래 실험 프로젝트와 정책/예약 파일은 변경하지 않았습니다.
- 기존 Python 배포 검증도 이번 환경에서 **6개 통과**했습니다: reports/wmi-preflight-only-python-tests.log.
- 독립 읽기 전용 검토에서 정상 빈 stderr를 실패로 처리하는 문제를 발견해 수정했고 Complete 문구를 관측 단계의 판정 완료로 좁혔습니다. 새 경로에는 OEM 실행·예약 접근·펌웨어/서비스/ACL 변경이 없습니다.
- 패키저는 고정 EXE/config/Core만 포함하고 실제 PE x64/asInvoker·호출/예약 참조 부재·전체 소스 대응·SHA-256·ZIP CRC를 검사합니다. 삼성 원본 DLL과 기존 실험 EXE 및 원문 사용자 TXT는 실행 ZIP에서 제외합니다.
- 별도 패키지 점검 **14항목 통과**: 정상 빌드·소스 수락, 호출/예약 타입·메서드 5종을 참조에 삽입했을 때 거부, 잘못된 PE, 삼성 DLL 혼입·오래된 소스·미완료 테스트 보고서 거부를 확인했습니다. 실제 RT_MANIFEST 리소스 XML도 asInvoker/uiAccess=false로 확인했습니다. reports/wmi-preflight-only-package-audit.json에 기록합니다.
- 새 Windows 도구의 실기 실행은 아직 미검증입니다. 새 도구로 준비 실패 위치만 확인하며 기존 실험 재실행·표식 삭제·추가 OEM 호출을 요청하지 않습니다. 실제 충전 제어는 Unsupported입니다.

## 실기 사전 검증 중단 수신·보고만 보완 — 2026-11-04 한국 시간

- 사용자 출력은 Elevated·PreflightFailed·Unavailable·OEM요청없음·응답/후보미관측입니다. 이번실행에서는예약과채널에진입하지않았으며 기존표식유무나실패세부위치를단정하지않습니다. [관측과수정](WMI_ONE_SHOT_PREFLIGHT_RESULT.md)을기록했습니다.
- 현재전체 **325 passed, 0 failed, 0 skipped (325 registered)**, reports/wmi-preflight-trace-tests.json 및 .log. 전체5개프로젝트빌드 **경고0개·오류0개**, reports/wmi-preflight-trace-build.log에기록합니다.
- 새3개그룹은실패단계의고정enum전달·실패준비정보제거·무호출/무예약·Unknown기존출력·잘못된enum·원문미보관·기존1회gate를검사합니다. 원래7인수공개생성자도유지합니다.
- 호출메서드·콜백·출력추출·쿼리옵션·시간제한helper는20b046b와바이트동일하게유지했고 고정정책/예약/가드도변경하지않았습니다. 독립읽기전용검토에서차단문제를찾지못했습니다.
- 변경은보고와기록뿐이며 새실험EXE·추가Windows/OEM실행·재시도·표식삭제는없습니다. 원본TXT는저장소에넣지않고 새로운자료를요청하지않습니다. 배포스크립트는변경하지않아Python suite는반복하지않았습니다. 실제충전제어는계속Unsupported입니다.

## 승인된 단1회 조회 후보 도구 — 2026-11-03 한국 시간

- 사용자가 검토서의 미검증0x65 후보 한정1회 실험을 명시적으로 승인했습니다. [승인·정확한 범위](WMI_ONE_SHOT_QUERY_APPROVAL.md)에 원문과 구현 제한을 기록했으며 같은 범위를 다시 승인받지 않습니다.
- 현재 전체 suite **322 passed, 0 failed, 0 skipped (322 registered)**. reports/wmi-one-shot-tests.json 및 .log는 이번 최종 실행입니다.
- 새25개 그룹: Core 실험 gate/고정 요청/한번·재진입/예약 실패/후보 비해석12개, 원자적 영속 예약/재실행/경로6개, SDK와 분리한 콜백 collector의 완료0·단1개·중복/늦은 도착·cancel/읽기오류·정리/reentrancy7개. 실제 Windows 제공자는 사용하지 않습니다.
- Core·WPF·WmiAccessCheck·WmiContractCheck·WmiOneShotQuery 전체5개 프로젝트 x64 net48 빌드 **경고0개·오류0개**. reports/wmi-one-shot-build.log와 test-build.log에 기록합니다.
- 기존 Python 배포 검증 **6개 통과**. 새 실행 ZIP은 고정 파일·x64/asInvoker·SDK 호출 지점1개·부모/작업자 독립10초·일치 소스·SHA-256·CRC를 별도 확인합니다.
- 독립 읽기 전용 코드 검토에서 차단 문제를 발견하지 않았습니다. 명시적 model/BIOS·token·schema·정확히1Active·입력준비·영속claim 뒤에만 고정 후보를 요청합니다. metadata 일치를 실제 후보 안전성으로 해석하지 않습니다.
- 새로운 환경의 기본 체크아웃은 다른 작업 상태여서 수정하지 않았습니다. 체크섬 검증된 이전 소스 캐시에서 별도 폴더로 시작했고, 원격 검토 기준8f98ba8을 별도 게시 준비 폴더로 확보해 기존 이력을 보존했습니다. 공식 SDK/net48 참조 캐시로 offline restore했으며 단일 MSBuild node·서버 비사용·DOTNET_ReadyToRun=0을 사용했습니다.
- 클라우드에서 새 EXE·Windows 토큰/WMI 제공자·OEM 명령·펌웨어 응답을 **실행하지 않았습니다**. Windows 실기는 사용자 승인1회 시험으로 남아 있으며 실제 충전 제어는 계속 Unsupported입니다. 환경 설정 게시는 하지 않았습니다.

## 다음 OEM 후보 단계 검토서 — 2026-11-03

추가 공개자료의 고정소스·callsite를 정적으로 대조하고 [한정 후보 실험의 범위·바이트·중단조건·위험](WMI_ONE_SHOT_QUERY_REVIEW.md)을 문서로 만들었습니다. 실제실행코드·테스트·빌드의 변경은 없으며 같은suite를 다시 실행하지 않았습니다. 아래297개 통과·경고오류0은 이전코드의 검증기록입니다.

OEM 구현·새 EXE·실제 실험은 아직 **미승인·미구현·미실행**입니다. FF를OFF로접거나 모델별검증조건을충족했다고기록하지않습니다. 검토서의 후보 프레임은21바이트이며 경로간전이가설을포함합니다. 원본Samsung/사용자자료·외부원문소스는추가하지않고환경설정게시는하지않습니다.

## 메모리 채널·전체 경로 통합 — 2026-11-03

- 현재 전체 suite **297 passed, 0 failed, 0 skipped (297 registered)**. reports/wmi-pipeline-tests.json 및 .log에 기록합니다.
- Core·WPF·두 별도 도구 전체 x64 net48 빌드 **경고0개·오류0개**, reports/wmi-pipeline-build.log에 기록합니다.
- 신규11개 그룹은 고정 바인더/명시 transport, 요청 프레임 형식/길이/magic/예약0의 무호출, encoder→coordinator→channel→가짜 snapshot→binder→decoder 전체 연결, 배열 독립성·번호 분리, 중첩 오류/byte 오류, 결합 결과의 재포장 거부, API 실패의 무조회, transport 예외/null과 Output=null 구분, token 전파·취소·시간 초과 뒤 실제 완료 전 Busy·늦은 fault 관찰·회복을 검사합니다.
- 기존 byte decoder 테스트에 MethodReplyStatus=null 호환 검사를 추가했습니다. 기존 bool validator와 바이트 수락 경계·기존 enum 번호는 유지하고 새 InvalidEnvelope는 끝에 추가했습니다. 기존 coordinator는 수정하지 않았습니다.
- 신규 transport는 가짜 메모리 자료만 사용하며 실제 WMI/native/OEM 구현·객체 생성·앱 등록이 없습니다. 실제 메서드 응답·배터리 보호 설정·충전 제어는 **미실행·미구현**입니다.
- 배포 스크립트 변경이 없어 Python suite는 반복 실행하지 않았습니다. 이전6개 통과는 이전 기록이며 소스 ZIP의 허용 파일·현재 내용 일치·체크섬·CRC는 별도 확인합니다.

[통합 계층·추가 공개 포크 조사·현재 한계](WMI_BOUND_CHANNEL_AND_PIPELINE.md)를 기록했습니다. 같은 노트북 진단을 요청하지 않고 원본 삼성 바이너리·사용자 보고서·외부 코드는 포함하지 않습니다. 환경 설정 게시는 하지 않았습니다. 아래는 이전 기록입니다.

## 형식 일치 관측·메모리용 메서드 바인더 — 2026-11-03

- 판독기2의 사용자 출력에서 두 클래스Complete, GUID후보일치, MethodId1, in/out의 단일Object+CIMTYPE DataBuffer, Bytes UInt8[]를 확인했습니다. 수정 판독기2의 이 클래스 조회 경로는 실기 확인됐습니다. EmbeddedInstance는 미관측/없음이며 토큰·OEM 실행·실제 응답·배터리 상태는 관측하지 않았습니다.
- 현재 전체 suite **286 passed, 0 failed, 0 skipped (286 registered)**. reports/wmi-method-binder-tests.json 및 .log에 기록합니다.
- Core·WPF·두 별도 도구 전체 x64 net48 빌드 **경고0개·오류0개**, reports/wmi-method-binder-build.log에 기록합니다.
- 신규12개 그룹은 실제 완전 일치 관측 합성과 상세 메타데이터 필수·기존 Partial/호환bool 거부, 고정 입출력 포장/추출, Windows번호/firmware명령 분리, 깊은 복사와 읽기 전용 map, API 실패의 무조회, 중첩 필드/예외 분류, 불필요한 멤버 무조회·기존 디코더 오류 보존·payload 비해석을 검사합니다.
- 독립 Core 코드 검토에서 추가 결함을 발견하지 않았습니다. 새 바인더는 메모리용 snapshot API이고 WMI/native 호출·CreateInstance·전송 채널·앱 등록이 없습니다. 테스트는 합성 자료만 사용했습니다.
- 배포 스크립트 변경이 없어 Python suite는 다시 실행하지 않았습니다. 이전6개 통과는 이전 기록입니다. 새 소스 ZIP의 파일 허용 목록·현재 파일 일치·SHA-256·CRC는 별도 확인합니다.
- 현재 모델의 실제 보호 상태 읽기·OEM 명령·충전 제어는 **미실행·미구현**입니다. 반복 노트북 규약 진단은 요청하지 않습니다.

[실제 관측·구현·추가 공개 ACPI 조사 범위](WMI_MATCHED_BINDING_AND_OFFLINE_ENVELOPE.md)를 기록했습니다. 원본 사용자 TXT·삼성 바이너리·외부 코드/문서는 배포하지 않으며 환경 설정을 게시하지 않습니다. 아래는 이전 이력입니다.

## 실제 규약 관측·CIMTYPE 판독 보완 — 2026-11-03

- 사용자 콘솔 출력에서 GUID 후보 일치·메서드 존재·WmiMethodId1·DataBuffer UInt8[] 및 입출력 Unknown을 확인했습니다. 이전 도구의 메타데이터 조회 실기 관측이며 수정 도구의 실행이나 OEM 호출 결과는 아닙니다. 토큰 상태는 미관측입니다.
- 현재 전체 suite **274 passed, 0 failed, 0 skipped (274 registered)**. reports/wmi-parameter-tests.json 및 .log에 기록합니다.
- Core·WPF·두 별도 도구 전체 x64 net48 빌드 **경고0개·오류0개**, reports/wmi-parameter-build.log에 기록합니다.
- 신규12개 그룹은 CIMTYPE/EmbeddedInstance 독립 정규화, 누락·다른 정의·충돌·잘못된 형식, 길이/식별자/shape 조건, 불변·원문 미보관, 실제 부분 관측 보존, 번호 비치환과 실패 시 상세 정보 제거를 검사합니다. 기존262개 테스트도 포함합니다.
- 기존 Python 배포 검증 **6개 통과**. 고정 파일·asInvoker·SHA-256·ZIP CRC·소스 대응은 패키징 때 별도 검증합니다.
- 새 판독기2의 Windows 제공자 실행·CIMTYPE 실제값·배터리 설정 읽기·OEM 호출·충전 제어는 **미검증/미실행**입니다. 표준 표현 지원을 노트북의 실제 qualifier 값으로 기록하지 않습니다.

[공식 원문과 구현 범위](WMI_PARAMETER_RESULT_AND_CIMTYPE_REVIEW.md)를 기록했습니다. 원본 사용자 TXT·삼성 파일·외부 문서 원문을 복사하지 않고 환경 설정 게시는 하지 않습니다. 아래는 이전 검증 이력입니다.

## 비동기 교환·정적 클래스 규약 도구 — 2026-11-03 한국 시간

- 현재 전체 suite **262 passed, 0 failed, 0 skipped (262 registered)**. reports/wmi-exchange-contract-tests.json 및 .log는 이번 실행입니다.
- Core·WPF·WmiAccessCheck·WmiContractCheck의 x64 net48 빌드 **경고0개·오류0개**, reports/wmi-exchange-contract-build.log에 기록합니다.
- 신규 비동기12개 그룹은 인코더/가짜 채널/디코더 연계, 잘못된 입력·사전 취소의 무호출, 예외·null 응답, Busy, 취소·시간 초과 후 지연 완료/예외, 취소 콜백과 동기 시작, 독립된 조정기를 검사합니다.
- 신규 메타데이터6개 그룹은 고정 후보 비교, 형식·대소문자 정규화, 클래스별 실패/누락/불일치, 불변 상태와 정보 보호, 모든 호출/하드웨어 기능 차단을 검사합니다. 실제 WMI 제공자 실행 테스트는 아닙니다.
- Python 기존 배포 검증 **6개 통과**. 새 도구의 패키징은 허용 파일·내장 asInvoker manifest·일치 소스·SHA-256·ZIP CRC를 별도 확인합니다.
- 독립 코드 검토에서 추가 결함을 발견하지 않았습니다. 새 도구의 Windows 실행·제공자 메타데이터·OEM 메서드·실제 충전 제어는 **미실행**입니다.

공식 net48 참조로 새 프로젝트를 복원했으며 기존 .NET SDK8.0.427·WindowsDesktop SDK·DOTNET_ReadyToRun=0을 사용했습니다. [구현·공개 자료·실기 확인 범위](WMI_EXCHANGE_AND_BINDING_CHECK.md)를 기록했습니다. 원본 삼성 파일·사용자 보고서는 포함하지 않고 환경 설정을 게시하지 않았습니다. 아래는 이전 이력입니다.

## 구조적 WMI 응답 디코더 — 2026-11-03 한국 시간

- 현재 전체 suite **244 passed, 0 failed, 0 skipped (244 registered)**. reports/wmi-reply-decoder-tests.json 및 .log는 이번 실행입니다.
- Core·WPF·별도 비교 도구 x64 net48 빌드 **경고0개·오류0개**, reports/wmi-reply-decoder-build.log에 기록합니다.
- 추가6개 그룹은 API 우선순위·S_FALSE, 요소 형식/차원/시작 인덱스, 길이0..64 및 큰 버퍼, 전체ACK256값, 입력/결과/호출자 복사본 독립성, payload 비해석과 bool API 호환을 검사합니다.
- 기존 bool validator가 새 typed decoder에 위임해도 수락 조건 S_OK·정확한byte[]·1차원·0기반·21바이트·ACK0xAA는 유지됩니다. 실패 데이터는 보관하지 않고 제어·하드웨어 관측으로 승격하지 않습니다.
- 추가 공개 Linux WMI 원문 두 개를 고정 커밋에서 정적으로 대조했습니다. 외부 코드·unlock·OEM·드라이버 호출은 실행하지 않았고 제품에 코드를 복사하지 않았습니다.
- 새 실제 Windows 호출·응답·충전 제어는 **미실행**입니다. 현재 모델 배터리 조회 명령·실제 응답 계약을 확보했다는 결과가 아닙니다. 실제 실행 경로와 패키징 코드는 바꾸지 않아 Python 배포 suite를 불필요하게 반복 실행하지 않았습니다.

[구현·공개 근거·검증 한계](WMI_REPLY_DECODER_AND_PUBLIC_EVIDENCE.md)를 기록했습니다. 기존 공식 .NET SDK8.0.427·net48 참조·WindowsDesktop SDK·DOTNET_ReadyToRun=0을 사용했습니다.


## 실제 일반·관리자 비교 결과 반영 — 2026-11-03 한국 시간

사용자 제공 두 콘솔 출력에서 일반 토큰의 버전 클래스 Complete(Active=True, version16), 메서드 클래스 Enumerate/0x80041003 거부와 상승 토큰의 두 클래스 Complete(활성 행1개씩, version16)를 확인했습니다. 기존237개 도구의 이 고정 속성 읽기와 토큰 표시 경로가 실제 Windows에서 실행된 결과입니다. OEM 메서드·실제 충전 제어를 시험한 결과가 아닙니다.

- 현재 전체 suite **238 passed, 0 failed, 0 skipped (238 registered)**. reports/wmi-observed-comparison-tests.json 및 .log에 이번 결과를 보관합니다.
- Core·WPF·비교 도구 x64 net48 빌드 **경고0개·오류0개**, reports/wmi-observed-comparison-build.log에 기록합니다.
- 실제 두 결과를 개인정보 없는 합성 회귀 사례1개로 추가해 선택적 열거 거부, 관리자 속성 성공, 버전16 원값, 독립 상태 및 OEM/제어 차단을 검사했습니다.
- 단일 보고서의 관리자 실행 관련 표현을 단일 관측에 한정하도록 수정했습니다. 현재 소스의 이 표현 변경은 Windows에서 재실행하지 않았으며, 새 장치 호출·OEM 코드·진단 배포 ZIP은 추가하지 않았습니다.
- 기존237개 테스트·빌드 기록과 이번238개 실행을 구분합니다. 이번에는 배포 코드가 바뀌지 않아 기존 Python 배포 suite를 다시 실행하지 않았습니다.

[구체적인 관측 행렬과 명령 계약의 남은 조건](WMI_PERMISSION_COMPARISON_RESULT.md)을 기록했습니다. 원본 두 출력은 저장소·배포물에 넣지 않았습니다. 승인된 한 번의 비교는 결과 수신으로 완료됐으며 상시 관리자·자동 상승·OEM 호출로 확대하지 않습니다.


## 권한 거부 지속·별도 비교 도구 준비 — 2026-11-03 한국 시간

사용자 TXT samsung-files-20261102T154749에서 PacketPrivacy 적용 빌드의 두 클래스 AccessDenied 지속을 확인했습니다. SABI NotFound와 이름 후보 7개 Stopped/Manual도 유지됐습니다. 관리자 비교 실행은 아직 승인·수행하지 않았습니다.

- 전체 portable suite: **237 passed, 0 failed, 0 skipped (237 registered)**. 이번 reports/wmi-permission-tests.json 및 .log 결과입니다.
- Core·WPF·별도 asInvoker WmiAccessCheck를 포함한 x64 net48 솔루션 빌드: **경고 0개·오류 0개**, reports/wmi-permission-build.log에 보관합니다.
- 기존 Python 배포 검증: **6개 통과**, 앱 suite 수와 별도입니다.
- 새 9개 테스트 그룹: 토큰 상승 상태·조회 단계·고정 오류 분류·독립 관측·실패/잘못된 enum/클래스·불변 복사·정보 보호·출력 길이 경계·짧은 읽기와 오류 채널을 검증합니다.
- 최초 새 helper 빌드는 참조 복원 미완료로 실패했습니다. 공식 참조와 취약점 메타데이터를 다시 복원한 뒤 최종 전체 빌드를 통과했습니다. 검증을 끄거나 다른 대상 프레임워크로 바꾸지 않았습니다.
- 별도 도구는 asInvoker이며 메인 앱의 실행/UAC 연결이 없습니다. 자체 자식 조회만 감시하고 임의 파일 경로·서버·쿼리·명령은 입력받지 않습니다. 출력은 콘솔뿐입니다.
- 새 도구의 Windows 실행·실제 토큰 API·실패 단계·관리자 비교는 **미실행**입니다. 소스 검토 중 TokenIsElevated의 zero/nonzero 의미를 수정했고, 부모의 10초 제한은 인수 없는 일반 실행 경로에 적용된다고 명시했습니다.

기존 .NET SDK 8.0.427·공식 net48 참조·WindowsDesktop SDK·DOTNET_ReadyToRun=0을 사용했습니다. [완성된 검토 도구·허용 범위·승인 조건](WMI_PERMISSION_COMPARISON_REVIEW.md)에 상세히 기록했습니다. 원본 TXT·삼성 원본 파일은 복사하지 않았으며 환경 게시는 하지 않았습니다.


## WMI 권한 해석·암호화 연결·요청 프레임 — 2026-11-03 한국 시간

이번 사용자 TXT에서 삼성 이름 후보 7개 모두 Stopped/Manual, SABI 이름 NotFound, WmiAcpiVersion/WmiAcpiMethod AccessDenied를 확인했습니다. 앱 실행과 TXT 생성은 확인됐지만 Active/version·실제 충전 제어는 확인되지 않았습니다.

- 현재 전체 suite **228 passed, 0 failed, 0 skipped (228 registered)**. reports/transport-review-tests.json 및 같은 이름의 .log는 이번 실행 결과입니다.
- x64 net48 WPF/XAML 빌드 **경고 0개·오류 0개**, reports/transport-review-build.log에 보관합니다.
- Python 배포 검증 **6개 통과**. 앱 suite 수와 별도입니다.
- 신규 11개 그룹은 wsabi 요청의 정확한 21바이트·little-endian·명령 범위·배열 형식/길이·복사/실패 초기화와 독립 관측 요약·인과 추론/제어 차단·저장 성공/실패/재조회/공급자 오류를 검사합니다. 기존 종료 후 늦은 완료 시험도 새 요약 값의 비변경을 확인하도록 확장했습니다.
- 기존 서비스 wsabi의 정적 계약만 순수 바이트 인코더로 구현했으며 WMI/OEM/장치로 전송하는 연결은 없습니다. 실제 하드웨어 어댑터와 쓰기 차단은 유지했습니다.
- 새 연결은 PacketPrivacy·Impersonate·EnablePrivileges=false입니다. 공식 문서의 암호화 네임스페이스 요구를 근거로 설정했으며 관리자 권한·ACL 변경이 아닙니다. 노트북에서 이번 설정으로 AccessDenied가 해소됐는지는 **미검증**입니다.
- 새 화면·암호화 WMI의 Windows 실기 동작은 **미실행**입니다. 이전 TXT는 이전 빌드의 권한 거부 관측이며 새 빌드 검증으로 재사용하지 않았습니다.

기존 공식 .NET SDK 8.0.427과 net48 참조·WindowsDesktop SDK, DOTNET_ReadyToRun=0을 사용했습니다. [이번 분석과 수정 파일의 역할](WMI_ACCESS_RESULT_AND_TRANSPORT_REVIEW.md)에 근거·제한을 기록했습니다. 원본 TXT·삼성 바이너리를 소스나 배포물에 복사하지 않았고, 환경 초안 재적용·게시는 하지 않았습니다.


## WMI 인스턴스·버전·활성 속성 — 2026-11-02 한국 시간

이전 커널 드라이버 확인판의 실제 노트북 실행과 TXT 생성은 사용자 확인을 받았습니다. TXT 내용은 전달받지 않아 드라이버 조회 상태·SABI 결과는 추가 확인하지 않았습니다. 이번 변경은 다음 준비 단계의 로컬 WMI 속성 읽기이며 실제 충전 상태 조회·제어는 아닙니다.

- 전체 공유 Core·ViewModel suite: **217 passed, 0 failed, 0 skipped (217 registered)**. 이번 실행 결과는 reports/wmi-instance-tests.json 및 reports/wmi-instance-tests.log입니다. 이전 204개 기록을 현재 결과로 재사용하지 않았습니다.
- x64 net48 WPF/XAML 빌드: **경고 0개·오류 0개**, reports/wmi-instance-build.log에 보관합니다.
- 기존 Python 배포 검증: **6개 통과**. 앱 suite 수와 별도입니다.
- 추가 13개 그룹: 고정 속성 범위, 엄격한 Boolean/UInt32 해석, 클래스별 독립 상태, 정상 0개와 오류 구분, 부분·실패·한도, 다중 인스턴스, IPC v5 필수 필드/오래된 버전/모순/primitive 형식, 개인정보 제거, 화면·저장과 Unsupported 유지.
- 최초 새 suite는 **215 passed, 1 failed**였습니다. JSON 문자열이 Boolean/숫자로 자동 변환되는 경로를 발견해 IPC의 원래 JSON 형식을 엄격히 확인한 뒤 최종 217개 전체 통과를 확인했습니다. 필수 속성 미확인은 Partial로 남기고 Complete와 구분합니다.
- 현재 환경에서 새 WMI 제공자 조회와 Windows GUI는 **미실행**입니다. 실제 OEM 메서드·삼성 DLL·드라이버 변경·충전 제어도 실행하지 않았습니다.

기존에 준비한 .NET SDK 8.0.427, 공식 net48 참조 어셈블리, WindowsDesktop SDK와 DOTNET_ReadyToRun=0으로 빌드했습니다. 재현 환경 변수와 빌드 명령은 아래 이전 절을 참고하고, 테스트 보고서 경로는 위의 새 이름을 사용합니다. 환경 초안 재적용이나 게시는 하지 않았습니다. [구현·한계·노트북 확인 범위](SAMSUNG_WMI_INSTANCE_INSPECTION.md)를 참고하세요.


## 삼성/SABI 커널 드라이버 상태 조회 — 2026-11-02 한국 시간

현재 대화의 새 실행 환경에서 지정 브랜치의 `4492bbaa6f9cb87a9fb7c24969c6f1efcf6b6bd9`를 확인하고 개발했습니다. 기존 작업 브랜치를 보존했으며 이전 고장 환경의 게시 완료를 기다리거나 새로 게시하지 않았습니다.

- 전체 공유 Core·ViewModel 테스트: **204개 통과, 실패 0개, 건너뜀 0개**. `reports/portable-tests.json`과 `reports/portable-tests.log`는 이번 실행의 결과입니다. 이전 191개 기록을 현재 검증으로 재사용하지 않았습니다.
- .NET Framework 4.8 x64 WPF/XAML 빌드: **경고 0개, 오류 0개**. `reports/wpf-build.log`에 현재 빌드 결과를 보관합니다.
- 기존 Python 배포 검증 테스트: **6개 통과**. 앱 테스트 수에는 합산하지 않았습니다. 개발 미리보기의 프로토콜 4·읽기 전용 드라이버 조회·Windows 미검증 표기도 갱신했습니다.
- 새 13개 그룹은 후보 분류·상태/시작 방식의 모든 값·부분/오류 시 부재 판정 금지·결과 복사와 제한·SABI 결과 비교·IPC 필수 필드/잘못된 enum/개수/실패+관측 모순·개인정보 제거·기존 UI/저장과 시간 초과 후 이전 결과 제거를 검사합니다.
- Windows WMI 제공자 열거, Windows GUI·노트북 실기 실행은 **미실행**입니다. 삼성 DLL 초기화·OEM 메서드·드라이버 변경·실제 충전 제한도 실행하지 않았습니다.

공식 릴리스 메타데이터의 SHA-512로 검증한 .NET SDK 8.0.427 Linux 배포본과 같은 버전 WindowsDesktop SDK 도구를 `/workspace/.dotnet`에 준비했습니다. NuGet에서 공식 net48 참조 어셈블리 1.0.3을 복원했습니다. 최초 WPF 빌드는 Windows용 ReadyToRun 도구의 형식 오류로 실패했고, 관리 IL을 사용하도록 `DOTNET_ReadyToRun=0`을 적용한 뒤 실제 XAML 빌드를 성공시켰습니다. 체크섬·TLS 검증이나 앱의 대상 플랫폼을 바꾸지 않았습니다.

이 환경의 재현 명령입니다.

```sh
cd /workspace/codex/ATIVBatteryGuard
export DOTNET_ROOT=/workspace/.dotnet
export DOTNET_CLI_HOME=/workspace/.cache/dotnet
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
export NUGET_PACKAGES=/workspace/.cache/nuget
export PATH="$DOTNET_ROOT:$PATH"
dotnet restore ATIVBatteryGuard.sln --disable-parallel
dotnet restore tests/ATIVBatteryGuard.PortableTests.csproj
DOTNET_ReadyToRun=0 dotnet build ATIVBatteryGuard.sln -c Release --no-restore -p:UseSharedCompilation=false -m:1
dotnet run --project tests/ATIVBatteryGuard.PortableTests.csproj -c Release --no-restore -p:UseSharedCompilation=false -- --report reports/portable-tests.json
```

네트워크 복원은 지원되는 명령 실행 권한과 기존 HTTPS 프록시를 사용했습니다. SDK·캐시 경로는 이 환경에 준비한 로컬 도구이며, 설정 초안을 다시 적용하거나 게시한 기록이 아닙니다. [구현과 노트북 확인 항목](SAMSUNG_KERNEL_DRIVER_INSPECTION.md)에 범위와 한계를 기록했습니다.

## SABI 이름 결과 수신·WMI 응답 검증

후속 `samsung-files-20261101T132149`에서 SABI 이름 조회의 실제 Windows NotFound 경로를 확인했습니다. 동일 x64 DLL 해시와 기존 파일 항목들의 해시·버전 일치도 확인했습니다. 이름 부재를 드라이버 미설치나 펌웨어 기능 부재로 판정하지 않습니다.

이번 소스 변경의 전체 공유 소스 테스트는 **191개 통과·실패 0개·건너뜀 0개**, 실제 x64 net48 WPF/XAML 빌드는 경고·오류 0개입니다. 추가 7개 그룹은 정확한 x64 해시에서의 SABI 선행 조건 설명, 존재/미조회/오류 구분, 다른 해시·구조 배제, WMI 16바이트 복사의 독립성, S_FALSE·잘못된 배열/길이 거부, ACK 전수 검사, Sabi3와 WMI 규약 혼용 거부를 검사합니다.

기존 서비스 폴더 wsabi를 실행 없이 추가 정적 검토해 WMI 입력 21바이트·payload 16바이트를 확인했습니다. 응답 길이 21바이트 제한은 새 검증 코드의 보수적인 지원 정책이며 제공자의 실제 출력 길이를 시험한 결과가 아닙니다. DLL 로드·WMI 메서드 실행·장치 명령·충전 제어는 하지 않았습니다. 새 설명의 Windows 화면과 실제 WMI 응답은 아직 미검증입니다. 이번에는 새 실행 ZIP이나 사용자 재실행을 요구하지 않습니다. [관측·정적 근거·구현 한계](SABI_LINK_RESULT_AND_WMI_REVIEW.md)를 참고하세요.

## 제공받은 x64 DLL 규약 반영

실제 파일의 해시·x64·크기를 확인하고 초기화/통신 경로를 정적으로 교차 검토했습니다. 공개 4바이트 가정을 11바이트로 수정하고, 정확한 응답 길이·ACK·실패 시 이전 값 제거와 수동 SABI 이름 조회 상태의 IPC 버전 3 검증을 추가했습니다. 전체 공유 소스 테스트 **184개 통과·실패 0개·건너뜀 0개**, 실제 x64 net48 WPF/XAML 빌드는 경고·오류 0개입니다.

추가 5개 그룹은 새 버퍼의 길이/초기값/독립성, 16바이트 응답 전체 추출, 길이·ACK·실패 응답 거부, 이름 조회 상태별 왕복·쓰기 차단, 알 수 없는 상태/필수 필드/이전 버전 거부를 검사합니다. DLL 실행·장치 열기·드라이버 IOCTL·펌웨어 호출은 하지 않았습니다. 새 QueryDosDevice 조회의 실제 Windows 실행은 아직 미검증입니다. [정적 근거와 한계](SABI3_NATIVE_ABI_REVIEW.md)를 참고하세요.

## Sabi3 참조 응답 해석 코드

전체 공유 소스 테스트 **179개 통과·실패 0개·건너뜀 0개**와 실제 x64 net48 WPF/XAML 빌드 경고·오류 0개를 확인했습니다. 새 6개 그룹은 미지원과 OFF 구분, 모든 기타 바이트 값, API 오류 우선, 길이 오류, 퍼센트/실제 관측 승격 금지, 버퍼 비변경을 검사합니다. 공개 래퍼의 계약을 대상으로 한 순수 함수 검증이며 실제 DLL 응답이나 장치 호출을 시험한 결과는 아닙니다.

현재 단계는 추가 메타데이터 수집이 아니라 DLL 구현의 정적 검토 준비입니다. [근거·누락 자료·정확한 다음 대상](SABI3_INITIALIZATION_REVIEW.md)에 기록했습니다.

## Sabi3 후보 판정 및 import 함수 분석

새 변경에서 실제 공유 소스 suite를 실행해 **173개 통과·실패 0개·건너뜀 0개**를 확인했습니다. 실제 .NET Framework 4.8 x64 WPF/XAML 빌드는 경고·오류 0개입니다. 기존 158개에 실제 x86/x64 PE 함수 참조·ordinal·IAT·주소/종료/작업량 한도 10개 그룹과 후보 판정·함수 IPC·최대 결과 5개 그룹을 추가했습니다. 실제 Windows 파일 정보 조회는 이전 배포본의 사용자 TXT로 확인했으며 이번 확장 기능의 Windows 실행은 아직 미검증입니다. DLL 초기화·장치 메서드·실제 충전 제어는 실행하지 않았습니다.

사용자 요청에 따라 개발 미리보기 패키징을 재개하고 이전 배포 증거 검사는 명시적인 `--require-windows-release` 모드에 유지합니다. 배포 검증 Python 테스트는 별도로 실행하며 앱 suite 수에 합산하지 않습니다.

## Windows 보안 배포 검증 변경

사용자 Defender 차단 보고 후 실행용 배포를 보류하고 검증 게이트를 추가했습니다. Python 회귀 테스트 6개를 실제 실행해 모두 통과했습니다. 미서명/다른 게시자, 미완료 검사·보호 비활성·탐지, 검사 후 바이너리 변경, 오래된/미래 시각·다른 소스 증거와 증거 없는 CLI 배포 거부를 확인했습니다. 검토용 소스 ZIP만 생성했습니다.

앱 코드는 변경하지 않아 기존 158개 앱 시험·WPF 빌드를 재실행하지 않았습니다. 현재 환경에는 Windows Defender·PowerShell·게시자 서명 인증서가 없어 새 Windows 검증 스크립트는 실행하지 못했습니다. 악성코드 검사 통과나 오탐 해소를 확인한 결과가 아닙니다. [보안 대응 기록](WINDOWS_SECURITY_RELEASE.md)을 참고하세요.

## 현재 삼성 파일 정보 확인판

전체 공유 소스 회귀 테스트를 이번 변경에서 다시 실행해 **158개 통과·실패 0개·건너뜀 0개**를 확인했습니다. 실제 .NET Framework 4.8 x64 WPF/XAML 빌드도 경고·오류 0개입니다. 새 20개 그룹은 실제 합성 PE의 import/export 읽기와 잘못된 RVA/이름, 메타데이터 보호, 필수 필드·응답 길이·문자열·깊이 한도, 최대 유효 응답, ViewModel의 실패·중복 요청·저장 실패·종료 후 완료를 검사합니다.

첫 실행에서는 알 수 없는 JSON 필드의 129자 문자열을 길이 제한으로 거부하지 못하는 테스트가 실패했습니다. 프레이밍 검사에서 모든 JSON 문자열의 디코딩 길이를 확인하도록 보완하고 다시 전체 158개 통과를 확인했습니다. Unicode escape의 문자 수 처리와 경계값도 검사했습니다.

네이티브 코드의 독립 정적 검토, 별도 컴파일 및 x64 WINTRUST_FILE_INFO 32바이트·WINTRUST_DATA 88바이트·FILE_ATTRIBUTE_TAG_INFO 8바이트 확인을 수행했습니다. Windows의 실제 파일 핸들·오프라인 서명 API·새 조회 화면·보조 프로세스 실행은 아직 미검증입니다. [구조와 한계](SAMSUNG_FILE_INSPECTION.md)를 참고하세요.

## 이전 배터리 진단 결과 해석판

삼성 DLL 추출 없이 표준 Windows 배터리 드라이버의 요청 지원 여부를 읽는 진단을 추가했습니다. **진단 파일 만들기**로 생성되는 TXT의 ‘Windows 표준 배터리 드라이버의 요청 지원 여부’ 섹션에서 볼 수 있습니다. BatteryCharge/BatteryDischarge 지원 비트는 80% 충전 상한 지원의 증거가 아니며, 결과가 있어도 실제 제어는 미지원으로 유지합니다.

GENERIC_READ, QUERY_TAG(대기 0), QUERY_INFORMATION(정보 수준 0)만 사용합니다. 자체 보조 프로세스의 10초 제한과 최대 8개 인터페이스·16 KiB 결과 한도를 적용합니다. 장치 경로·태그·시리얼번호·고유 ID를 보고하지 않습니다. SET 요청이나 OEM 메서드는 실행하지 않습니다. 앱 시작이나 주기적 표시에서는 보조 조회를 실행하지 않습니다.

최신 진단에서 Windows 조회 성공과 `0x80000000`을 확인했습니다. 시스템 배터리 표시만 있고 표준 충전·방전 요청 지원 비트는 없습니다. 삼성 OEM 충전 상한의 가능성은 별도 미검증입니다.

현재 해석판은 이 차이를 메인 화면과 진단 TXT에서 설명합니다. 조회가 불완전하면 판단 불가로 남기고 재조회 시 이전 결과를 지웁니다. 같은 진단 파일을 다시 전달할 필요는 없습니다. 회귀 테스트 **138개 통과·실패 0개·건너뜀 0개**입니다. 새 해석 화면의 Windows 실행은 아직 미검증입니다. [구조·출처·검증 한계](WINDOWS_BATTERY_QUERY.md)에 상세히 기록했습니다. 아래 버전별 설명은 이전 단계의 이력입니다.

새 8개 테스트 그룹은 실제 관측 플래그, 한쪽·양쪽 요청 지원 비트, UPS·비시스템 배터리 제외, 부분·범위 제한·실패 결과, 화면 갱신, 파일 저장 실패, 종료 후 늦은 완료를 검사합니다. 전체 138개는 이번 변경에서 다시 실행했습니다. 실제 WPF/XAML x64 net48 빌드는 경고·오류 0개이며, Windows GUI 자동 시험과 새 화면의 노트북 실행은 수행하지 않았습니다.

사용자가 후속으로 전달한 `diagnostics-20261101T021357`에서 새 결과 해석 문장의 정상 기록과 읽기 전용 조회 완료를 확인했습니다. Win32/WMI 잔량은 52%로 일치했고 AC 연결·충전 중이었습니다. 메인 화면의 렌더링, 시간 초과 경로, 실제 충전 제어를 검증한 결과는 아닙니다. 그다음 공개 규약 조사 단계에서는 앱 코드를 바꾸지 않았고 빌드·테스트를 재실행하지 않았습니다.


## 삼성 파일 추출 제외판의 현재 조건

사용자의 Samsung Settings에서 DLL을 추출할 수 없다는 조건으로 진행합니다. WPF 배포 프로젝트에서 삼성 파일 수집기와 위치 탐색기를 컴파일 제외했고 수집 확인 창과 UI도 제거했습니다. 장치 조회·로컬 설정·시뮬레이션·공식 문의문 복사는 유지합니다. 추출한 삼성 DLL은 필요하지 않습니다. 자체 Core DLL과 Windows 내장 프레임워크는 앱 구성 요소입니다.

Microsoft 공식 문서에서 일반 배터리 설정 요청 경로는 확인했지만, 검토한 인터페이스에는 지속되는 80% 충전 상한 항목이 없습니다. OEM WMI 입력 규약은 아직 확보하지 못했으며 실제 제어는 미지원입니다. [DLL 추출 없는 개발 경로와 실제 확인한 출처](DLL_INDEPENDENT_RESEARCH.md)를 참고하세요.

아래 수집 관련 설명은 이전 단계의 기록이며 현재 배포 기능이 아닙니다.


## 공식 지원 검토판의 현재 상태

새 제품 시작 구성은 OEM 파일 수집기와 확인 콜백을 전달하지 않습니다. 수집 명령은 비활성화되고 직접 비동기 호출도 작업 없이 반환합니다. 기존 수집 코드는 소스 이력과 회귀 검증을 위해 보관하며 현재 제품 경로에서 사용하지 않습니다.

문의문 복사는 장치 정보 조회 완료 후에만 사용할 수 있고, 조회 갱신 중의 오래된 값과 종료 후 복사를 차단합니다. 공개 장치 정보 필드만 사용하며 상세 오류와 경로를 문의문에서 제외합니다. 클립보드에 복사할 뿐 실제 문의 제출·네트워크 통신은 수행하지 않습니다.

이 변경을 포함한 전체 portable suite는 **114개 통과·실패 0개·건너뜀 0개**, 실제 WPF 빌드는 경고·오류 0개입니다. Windows에서 새 문의 복사 동작은 아직 미검증입니다. 아래 표와 수집 절차는 이전 단계의 기록입니다.


2026-10-31 한국 시간 기준입니다. 이전 WMI 진단판의 확인 결과와 이번 Settings 수집 변경을 구분합니다.

## 이전 WMI 정의 진단판

| 항목 | 실제 확인 결과 |
| --- | --- |
| .NET Framework 4.8 x64 WPF 빌드 | 성공, 경고 0개·오류 0개 |
| 공유 Core·ViewModel 및 WMI 정책 회귀 테스트 | 78개 통과·실패 0개·건너뜀 0개 |
| 실행 파일 정적 검사 | x64 GUI, .NET 4.8 참조, 관리 진입점 확인 |
| 실제 XAML 컴파일 산출물 | `app.baml`, `views/mainwindow.baml` 포함 확인 |
| 일반 권한 manifest | `asInvoker` 포함 확인 |
| Windows 노트북 앱 실행 | 사용자 화면으로 창·배터리 표시 확인 |
| 실제 WMI 클래스 정의 | 사용자 TXT에서 정확한 클래스 3개·메서드 서명 확인, 조회 오류 없음 |

사용자 최신 관측은 배터리 62%, AC 연결 안 됨, 방전 중이며 Win32와 WMI 잔량이 일치했습니다. 이전 0%는 과거 관측이며 현재 고정값이 아닙니다. 클래스 정의 조회는 메서드를 실행하거나 충전 제한을 적용한 시험이 아닙니다.

## 새 Settings 앱 파일 수집

| 항목 | 현재 상태 |
| --- | --- |
| 새 변경의 WPF 빌드 | 성공, 경고 0개·오류 0개 |
| 새 변경의 portable 회귀 테스트 | 108개 통과·실패 0개·건너뜀 0개 |
| 새 수집 기능의 Windows 동작 | 미검증, 새 ZIP 결과 필요 |
| Windows GUI 자동 self-test | 미실행 |
| 실제 충전 제한 | 구현하지 않음, 항상 미지원 |

새 suite는 기존 78개와 Settings 경계 검사 30개를 이번 변경에서 다시 실행했습니다. pure 정책과 공유 Core·ViewModel의 회귀 검증이며, Windows Registry 열거·파일 수집을 실행한 결과가 아닙니다.

재실행할 주요 명령입니다. `dotnet`은 .NET 8 SDK를 사용합니다.

```sh
dotnet restore ATIVBatteryGuard.sln
dotnet build ATIVBatteryGuard.sln -c Release --no-restore -p:UseSharedCompilation=false -m:1
dotnet run --project tests/ATIVBatteryGuard.PortableTests.csproj -c Release --no-restore -p:UseSharedCompilation=false -- --report reports/portable-tests.json
python scripts/package_preview.py --test-report reports/portable-tests.json
```

Windows용 `scripts/Test-Windows.ps1`은 제공하지만 이 환경에서는 실행하지 않았습니다. 빌드 성공·클래스 발견·파일 수집 성공을 실제 충전 제어 성공으로 해석하지 않습니다. 과거 149개 또는 이전 WMI 판의 78개 시험 기록을 새 변경의 시험 수치로 재사용하지 않았습니다.

## 위치 누락 수정판

사용자 ZIP에서 앱 등록만 있고 설치·아이콘 위치가 없는 원인을 확인했습니다. 수정 후 전체 portable suite는 108개이며 등록 불일치/제공 경로의 대체 조회 금지와 고정 후보 범위를 검사합니다. 새 native 대체 조회는 Windows 결과가 필요합니다.
