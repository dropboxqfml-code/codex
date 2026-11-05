# Windows 호출자·P05ACJ 등록 대조와 native 응답 해석 수정 — 2026-11-05

보존한 Windows 호출자 기록을 [P05ACJ 등록 지도](P05ACJ_EXTERNAL_REGISTRATION_REVIEW.md)와 대조했습니다. 새로 확인한 관계는 **구형 OEM 앱의 호환성 조건과 P05ACJ의 별도0B 플래그 경로**입니다. 현재 모델의65/66 배터리 처리자·실제FF 원인은 여전히 미확정입니다. 대조 과정에서 기존 native11바이트 순수 디코더의 근거 없는0/1/FF 의미 부여를 찾아 수정했습니다. 삭제된 자료를 복원한 작업이 아니며 기존 이미지와 보존 기록을 사용했습니다.

## 호출자별 근거 대조

| 출처 | 실제 확인한 선택·응답 처리 | P05ACJ와 연결한 범위 / 한계 |
| --- | --- | --- |
| 구형 BatteryLifeExtender.exe1.0.0.11 | 65/80+10zero 조회,66/81·80 설정. 조회 API 결과를 무시하고1이면80% UI, 나머지는100% UI | 다른 NP-RV520 Win7/XP 패키지. UI fallback을 현재 보호 상태로 사용할 수 없음 |
| 공개 samsung-hotkeys | GetBLEEnabled가 API 오류를 throw하지만 FF는false, 그 외는==1. 모델명은 표시하며 배터리 getter 전에 모델 지원 allowlist는 없음 | 제3자 소스. USB67/68·무선69/6A·키보드78은 P05ACJ의 별도 문맥과 일부 일치하지만 배터리65/66 등록까지 입증하지 않음 |
| 사용자 제공 Sabi3 x64 | 전달받은 명령을 main5843/sub16·native11바이트 ABI로 중계 | 일반 전송 라이브러리. 배터리 명령 선택·모델 가드·보호 의미를 결정하는 호출자가 아님 |
| 기존 서비스 wsabi x86 | 호출자 명령을 WMI frame21/data16에 포장, AA+4/data+5 응답 접근 | 일반 중계. 현재 Settings의 다른 wsabi 해시에 동일 동작을 대입하지 않음 |
| SamsungConfigurationMonitor 보존 분석 | 같은 폴더의 wsabi 참조, 팬·정숙 문맥 | 배터리 명령값·응답 분기·모델 선택의 hash/RVA 기록은 없음. 0x80은 배터리80% 수치가 아님 |
| BatteryToast/PowerAudit | 버전·PE·WinRT/POWRPROF 참조 메타데이터 | 배터리 제어 caller·selector·지원 가드의 근거 없음 |

구형 OEM EXE는 SHA-256 `428e052fea9e67f7a948db472166ab970fd583a758ab26a68f3cc3310e4925ba`이며 [기존 원본 기록](FIRMWARE_REPLY_EVIDENCE_UPDATE.md)과 같습니다. Sabi3 x64는 `09a9714f0e11734872d60f2966edf8590ca721f0c05b2ca852a0bf20d6c006ae`, 서비스 wsabi x86은 `564b640d62db2a4e4b56c6331e0e526bad2ac1fcf438a41a9e5241551f457b6e`의 보존 분석에 한정합니다. 이번에 현재 Settings 원본을 새로 확보하거나 기계어를 재검증한 것으로 보고하지 않습니다. 보존 기록에 없는 내용을 다른 파일로 채우지 않습니다.

공개 소스는 [고정 SamsungBIOSInterface.cs](https://github.com/akastormseeker/samsung-hotkeys/blob/0d3947eea0003dd8e9372c36925c0fd0a8fd28d3/SamsungHotkeys/Controls/SamsungBIOSInterface.cs#L88)(SHAfa3e2ee228d3f4012bfa259c06437ee0de2f7187fcc64518a8dac6b60ad54c68)와 [SettingsWindow.xaml.cs](https://github.com/akastormseeker/samsung-hotkeys/blob/0d3947eea0003dd8e9372c36925c0fd0a8fd28d3/SamsungHotkeys/SettingsWindow.xaml.cs#L34)(SHA6ee9ad2e59454c562acf466dc8024406832d748d12413149619737e34c81eb5c)를 보존 원문으로 확인했습니다. 모델명 표시와 제조사 검사만으로 모델별 배터리 지원이 보장되지 않습니다. 이 소스의4바이트 버퍼도 실제 x64 DLL의11바이트 접근과 달라 그대로 실행하지 않습니다. 6D/6E FastStart 표기는 enum/comment뿐이고 해당 getter/setter callsite가 없으므로 완전한 동작 계약으로 취급하지 않습니다.

## 구형 OEM의 DLL 선택과 시작 가드

실제 OEM 앱의 RVA10D2–1110/28DC–290F는 **보고된 major>=6 AND minor==1**일 때 SABI3.dll, 아니면 SABI2.dll을 선택합니다. 일반적인 Windows7 이상 판정이 아닙니다. 조건식에 보고 버전6.1을 넣으면SABI3,6.0/6.2/6.3/10.0이면SABI2입니다. 실제 Windows 버전 가상화·호환성 설정·API 반환값은 관측하지 않았으므로 Windows10에서 어느 DLL을 선택한다고 확정하지 않습니다.

두 DLL은 같은65/66를 main5843으로 전달합니다. 이 선택이 명령을67/68·6D/6E·7C로 바꾸는 근거는 없습니다. helper1470은 Windows 설치 ImageState, helper4FB0은 conf.ini의 n100ModeSetFirst 검사여서 모델 가드가 아닙니다. OEM EXE 매니페스트도 requireAdministrator이며 supportedOS 선언은 없습니다. 현재 앱은 asInvoker를 유지합니다.

별도 helper13D0은0B와11바이트 zero 입력을 보내고 API 결과를 무시한 채 `(~(payload[0] >> 3)) & 1`을 반환합니다. 값0이면 caller12E2–12F9가 모델 미지원 문구/종료로 흐르고1이면 UI 진행을 허용합니다. 그러나 **65 조회(12D9→144E)와 조건부66 쓰기(123B–1280)가 이 검사보다 앞**입니다. 이 OEM 앱을 안전한 진단 실행용으로 사용할 수 없습니다. 이번에는 실행하지 않았습니다.

## P05ACJ에서 새로 연결한0B 경로

SecSabiDispatch.efi(SHA2795669f18e3fb787d908ba00e2e9da7ab7d398ee599f27aa2f068129b46f310)의 initializer3B84는0B descriptor에 callback3908을 넣고3C3D에서 공개 등록 메서드를 호출합니다. callback3908은 저장한 같은 인터페이스의 getter7DC(method+10)를 호출해 flag5바이트 중 첫 바이트를 응답 데이터에 복사합니다. 이 범위는 장치 상태 조회가 아닌 모듈 flag 복사 경로입니다.

| 조건부 소스 대조 | 결과 | 입증하지 않는 것 |
| --- | --- | --- |
| provider의 미변경 초기 첫 flag7F | bit3=1 → 구형 caller 식의 결과0 → 호환 거부 UI 분기 | 현재 노트북의0B 응답·호환성·배터리 기능 부재 |
| 확인한 getter/mask/setter 경로 | bit1/4/5를 지우는 경로는 bit3을 보존 | 다른 동적 setter·다른 볼륨·다른 현재 이미지까지 폐쇄 |
| API 오류 후 구형0B 입력zero가 남는 경우 | 식의 결과1 → UI 허용 가능 | 실제 성공한 지원 조회 |

setter7FC(method+18)로 공유 flag를 바꿀 수 있으며 모든 런타임 변경은 닫지 못했습니다. 초기7F와 구형 앱의 호환성 거부는 **조건부 정적 연결**입니다. bit3을 제조사 전체의 배터리 지원 bit로 명명하거나 실기값으로 확정하지 않습니다. 사용자가 과거에 받은 FF는 **65의 첫 응답 바이트**이므로 별도0B flag와 혼합하지 않습니다. 이를 확인하기 위한 새0B 호출도 수행하거나 요청하지 않습니다.

## 바로잡은 기존11바이트 디코더

기존 Sabi3ReplyDecoder는 API0·길이11이면0→ProtectionDisabled,1→ProtectionEnabled,FF→Unsupported를 반환했습니다. 당시 소스상의 해석을 현재 모델 계약처럼 표현한 것으로, 이번 대조의 근거와 맞지 않습니다. 실제 앱·어댑터에서 이 순수 디코더를 참조하는 경로는 없었고 실제 제어 활성화나 노트북 상태 변경은 없었습니다.

- API 오류 우선 처리와 정확히11바이트만 받는 경계는 유지합니다. 실패에는 표식을 부여하지 않습니다.
- 정상 바이트는 `UninterpretedPayload`와 `Zero/One/FF/Other` 표식만 반환합니다. 이것은 실제 응답 출처나 보호 의미를 인증한 상태가 아닙니다.
- ProtectionEnabled/ChargeLimitPercent는 항상null, 하드웨어 관측/쓰기 권한은false입니다. native11과 WMI data16/frame21은 별도입니다.
- 기존 enum 이름·숫자와 public 생성자 시그니처는 유지하지만, 외부에서 보호/지원 enum이나 검사된 payload 상태를 생성자에 넘겨도 Unknown/NotInspected로 정규화합니다. **기존0/1/FF 결과의 동작은 의도적으로 변경**했습니다.
- 패키지 보호 검사는 native 모델/디코더의 순수성·의미 미확정·권한false도 검사하고, 새 표식 enum이 없는 이전 Core DLL 혼합을 거부합니다. metadata revision은 Offline-result-review-v3입니다.

## 검증과 사용

C# **435개 통과**, 실패·건너뜀0개. 기존 decoder 테스트를 모든256 첫 바이트·API 오류/잘못된 길이·입력 격리 경계에 맞춰 수정했고 public enum 생성으로 의미/검사 상태를 위조할 수 없다는 회귀1개를 추가했습니다. Python **48개 통과**이며 v2 Core 혼합 거부·native 의미/하드웨어 주장 재도입 거부2개를 추가했습니다. 7개 프로젝트와 portable tests 빌드 경고·오류0개입니다. 독립 읽기 전용 코드 검토에서도 차단 결함은 발견하지 못했습니다.

실제 빌드 PE의 AMD64/내장 매니페스트 asInvoker·uiAccess=false, 금지 참조 부재, 최신 build 표식과 source guard를 확인했습니다. 새 GUI의 Windows 실기는 미검증인 미서명 개발판입니다. 관련 결과는 reports/caller-contract-tests.json·.log, caller-contract-python-tests.log, caller-contract-build.log, caller-contract-portable-build.log, caller-contract-build-audit.json에 남겼습니다.

[프로그램 ZIP](../downloads/ATIVBatteryGuard-CALLER-CONTRACT-REVIEW.zip) **하나만** 새 폴더에 전부 풀어 ATIVBatteryGuard.exe를 일반 권한으로 실행할 수 있습니다. 소스 ZIP은 실행에 필요하지 않습니다. 사용자에게 새 시험이나 파일 업로드를 요청하는 변경이 아니며, 배터리 표시·기존 오프라인 검토 흐름은 유지합니다. 삼성 원본 DLL/EXE·펌웨어·실험 실행 파일은 포함하지 않습니다. 프로그램/소스/체크섬과 다운로드 링크의 무결성을 확인합니다.

## 현재 판단과 남은 작업

이 대조로 구형 caller의 선택/호환성 가드와 오류 fallback의 한계를 구체화했고, 코드에 남아 있던 의미 추정을 제거했습니다. 현재 모델의 Windows OEM 배터리 호출자 →65/66 등록/처리자 → 보호 상태·상한 응답 계약의 연결은 아직 없습니다. 실제 제어는 Unsupported입니다.

현재 보존 기록에서 더 읽으면 완전한 배터리 계약이 나온다는 근거는 없습니다. 다음 근거는 현재 모델·BIOS에 적용되는 OEM 배터리 모듈/모델 선택 조건 또는 대응 처리 계약이어야 합니다. 일반 중계·메뉴 부재·같은 숫자·다른 모델/기능·초기 flag를 대신 사용하지 않습니다. 추가 자료 재제출·반복 진단·OEM 재호출·예약 초기화·드라이버/보안/펌웨어 변경 없이 이 경계를 유지합니다.
