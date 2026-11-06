# 940X3G 계열 원본 확보와 프로그램 설명 반영 — 2026-11-06 한국 시간

**후속:** [현재 SUS 후속 처리·전체 FV·제조사 매뉴얼 대조](CONTROL_CONTRACT_CLOSURE_REVIEW.md)에서 실제 파일 설정 helper와 장치 read-back의 차이를 더 확인했습니다. 후속 분석에서는 실행 파일을 바꾸지 않았습니다. 아래 빌드·테스트 수치는 이 설명 반영판을 검증한 당시 기록입니다.

**현재 계열의 배포 목록에서 Settings2.2.0.18 원본을 확보했고, 이전 사용자 제공 x64 Sabi3와 같은 파일을 확인했습니다.** 이 연결과 검증한 비교 OEM 근거를 앱의 오프라인 설명에 반영했습니다. 현재 장치의 보호 설정·Windows10 충전 제어 지원을 확인한 결과는 아니며 실제 제어는 Unsupported를 유지합니다.

## 현재 계열 카탈로그를 확보한 근거

문서화된 공개 모델 조회에서 얻은 코드만 사용했습니다. 실제 장치 시리얼·DMI·UUID·개체 경로는 수집하거나 전송하지 않았고 공개 코드도 보고서에 넣지 않습니다. 개발 서버 조회는 앱의 네트워크 기능이나 노트북 OEM 호출을 추가한 작업이 아닙니다.

비교 모델의 GetSupportedOSList가 실제 OS 토큰A1/W7/WB를 반환했습니다(HTTP200/서비스0,520바이트/SHA `4898a84fc0bbe9bdec2f4c6fcdf8316864c60210d5d5158f15dddb5c5128900a`). WB 카탈로그의 WB 전용 항목에는 Win8.1 드라이버/설명서 표시명이 있어 이 응답 계열의 Windows8.1 문맥을 확인했습니다. 전체 API enum의 의미를 추정하거나 OS/client 버전을 무차별 대입하지 않았습니다.

같은 문서화된 legacy JSON3.0/client3.0.108.0 조건과 실제 반환 토큰WB를 사용한 현재 계열 카탈로그는 **HTTP200/ResultSUCC, 목록 XML2개**를 반환했습니다. 이전 W8 요청의404와 다른 결과이며, 이전 실패를 장치 미지원으로 사용할 수 없음을 확인했습니다.

| 현재 계열 BOM | 바이트 | SHA-256 | Header |
| --- | ---: | --- | --- |
| 0 | 440,536 | `60cd213f900c93b7e9947fdbc998c0dda7ce8628c0180bb63a355f1d5ed0bd6f` | Model940X3G / WBPR64 |
| 1 | 454,048 | `e6ce8071684aaee64c648b82c827e4d25a8846760eb421395897ca1cead2adae` | Model940X3G / DONCR |

두 목록은 **Settings [2.2 ver] 2.2.0.18 → BASW-84270A4N.ZIP**을 가리킵니다. 같은 다운로드 위치를 독립 바이너리 두 개로 세지 않습니다. TestYes·FileVer·카탈로그 성공은 실제 실행·장치 지원·제조사 서명 신뢰의 검증이 아닙니다. Header 모델은 배포 목록의 모델이며 사용자의 정확한 판매 SKU를 식별한 결과가 아닙니다.

## 실제 받은 원본과 파일 연결

정상 ORCA → org.downloadcenter → downloadcenter 리다이렉트를 따라 다음 원본을 HTTP200으로 받았습니다. 프록시·TLS 검증을 유지했고 추가 호스트나 환경 초안을 저장하지 않았습니다.

[BASW-84270A4N.ZIP](https://downloadcenter.samsung.com/content/SW/201411/20141103085646234/BASW-84270A4N.ZIP)

| 관측 대상 | 바이트 | SHA-256 |
| --- | ---: | --- |
| 원본 ZIP | 73,237,618 | `a709e49804b02f3441ef063a849c11c4c16a632a3cdf2eb6c5667bfe30d5a216` |
| SettingsSetup.msi | 74,493,440 | `7fe6e31947dee80543eaaa631881d7a6507a3b67bab6d417806258bdc1a02f44` |
| Settings.exe | 2,179,904 | `98bc2c0f084a08c6a26a6d464841194d5bb818014f0e0f4cb208df8bd0de06ad` |
| ModuleBatteryMgr.dll | 46,400 | `562d6adb8706f0d508f378a23aae9d14d37ceb4244f27f5286f91570e445e46d` |
| ModuleSABI.dll | 27,968 | `7c57ac5a6ce5727766f425c0aa7368ee75be20fdf790b84113b7e9abf2069f12` |
| x64 Sabi3.dll | 28,976 | `09a9714f0e11734872d60f2966edf8590ca721f0c05b2ca852a0bf20d6c006ae` |

ZIP7항목/파일6개, CRC·중복/대소문자 충돌·심볼릭 링크·위험 경로 검사를 통과했습니다. 실제 비압축 합계75,357,277은 이번 목록의 원본 크기와 일치합니다. MSI File table260개를 매핑하고 CAB 데이터를 고정 비공개 위치에 추출했습니다. MSI ProductVersion2.2.0과 Settings.exe 파일 버전2.2.0.18을 구분합니다.

x64 Sabi3의 해시는 기존 사용자 제공 파일과 정확히 같습니다. 같은 원본에 있는 x86 Sabi3는 별도 해시입니다. 이 일치는 한 구성 파일의 출처 연결이며 전체 설치 버전·실제 로드 경로·현재 장치 식별·충전 지원의 증거가 아닙니다. 기존 SUS1.0.6.1과 WSABI4변형도 이전 비교 원본과 바이트가 같지만, 구형 CmdServer/SUS1.0.5.7 배치가 그대로 있는 것으로 취급하지 않습니다.

## 새 원본의 한정 정적 분석

원본 EXE/DLL/MSI/BAT·함수·AML은 실행/로드하지 않았습니다. 독립 구조 검토와 trusted 데이터 파서·pefile/capstone 분석만 수행했습니다. 다음은 실제 바이트와 연결한 범위입니다.

| 모듈/근거 | 확인한 역할과 한계 |
| --- | --- |
| ModuleBatteryMgr Init5BF0, Install5C00, Uninstall5DE0, Check5DF0, IsHighPerformance5EB0 | Windows 전원계획 가져오기/활성화/복원·설치 등록·언어·WOL 관리. Init은 상수1이며 CheckInstalled와 활성 계획 GUID 비교는 충전 보호 read-back이 아님 |
| ModuleBatteryToast | 확인한4 export는 타이머 ID DWORD 저장·반환·검사·초기화. 이 본문을 충전 제어로 볼 근거 없음 |
| ModuleSABI Init10C0, Core1A80/1B10/1BD0 | Init은 상수1이고 실제 준비는 lazy Core에서 수행. 보고 OS 버전에 따라 전송 DLL을 선택하고 AL/GetBiosMode 조건 검사. 현재 Win10의 실제 선택은 미관측 |
| ModuleSABI export36개·관측 Core 호출47개 | USB·밝기·키보드·팬 등의 문맥. 이 파일의 직접65/66 호출은 미관측. USB67/68을 노트북 충전 제한으로 대체하지 않음 |
| SettingsCmd Init66D0→3550 | 호스트 설정 파일의 plugin 목록에서 Initialize/GetCommandCount/GetCommand를 연결. 서버13개/이벤트16개, 합집합16개 DLL |
| CommandMNPowerManagement count3FA0/factory3FC0 | 선언26명령의 생성자/RTTI를 복구. USB·Office·EcoMode 등의 명령이며 이 범위에서 구형 BatteryLifeExtend/SupportBLEMenu는 미관측 |
| SettingsCmd GetCommand6460/PushCommand64E0 | 명령 부재·null 입력의0 fallback. 성공한 하드웨어 조회로 해석하지 않음 |
| SettingsEventHandler | BatteryLife 문자열은 수명 알림 토큰과 CmdExecuteBatteryToast 문맥. 충전 상한 caller의 잔존 근거가 아님 |

전체 설정은289명령을 선언하고, 고유 factory 대상287개 중281개 RTTI를 복구했습니다. 나머지와 동적 등록·설치 후 설정·실제 DLL 검색 결과는 미해결입니다. 모듈 이름이나 한정 미관측을 패키지 전체·펌웨어의 충전 기능 부재로 확대하지 않습니다.

P05ACJ flag도 새로 한정 추적했습니다. generic setter07FC는 caller의5바이트를 마스크 없이 복사해 bit3 변경 가능성을 막지 않습니다. 같은 offset의 다른 프로토콜/NVS 객체 쓰기는 SABI flag writer에서 제외했습니다. 기존 마스크가 보존하는 것은 입력 snapshot의 bit3이며 모든 런타임 변경까지 닫은 것은 아닙니다. 새 배터리 처리자나 확정된 bit3 변경 caller는 확보하지 못했고 초기7F를 현재 값으로 사용하지 않습니다.

## 프로그램에서 바뀐 부분

- 오프라인 검토의 기본 화면에 현재 계열 원본과 기존 x64 DLL의 연결, 현재 보호 설정의 미확정 상태를 표시합니다. 과거 텍스트를 다시 입력하지 않아도 기본 설명을 볼 수 있습니다.
- 구조 검증된 과거FF 기록에는 비교 OEM의 분류·선행 버퍼 재사용·입력 동등성 미확정 설명을 추가했습니다. 잘못되거나 모순된 입력에 새 하드웨어 의미를 부여하지 않습니다.
- 배포 metadata와 읽기 안내에 두 원본의 출처를 기록하되 현재 모델 적용성·Win10 제어 지원·설정 적용 확인은false로 유지합니다.

이는 검증한 근거를 설명에 반영하는 변경입니다. parser·상태 enum·opaque 디코더·요청 인코더·단발 정책·하드웨어 권한·제어 어댑터는 바꾸지 않았습니다. 프로그램의 네트워크 통신이나 새 장치 조회·OEM 호출·예약 접근은 추가하지 않았습니다. 실제 충전 제어는 Unsupported입니다.

## 검증과 배포

최종 코드로 **C#435개·Python85개 통과**, 실패/건너뜀0개입니다. 솔루션과 portable test 빌드는 **경고·오류0개**입니다. 문자열 표시 변경에 같은 구현을 반복하는 새 테스트는 만들지 않고 기존 parser/권한/모의 동작·배포 경계 회귀 검증을 수행했습니다. 독립 코드 검토에서도 차단 결함은 발견되지 않았습니다.

검증 기록은 `reports/oem-caller-evidence-final-*` 접두사의 build/portable-build/tests/python-tests 파일에 있습니다. 새 GUI의 Windows 실기는 미검증이며 미서명 개발판입니다. 원본·추출 데이터·디스어셈블리는 저장소 밖 비공개 캐시에만 두고 배포에 포함하지 않습니다.

[프로그램 ZIP](../downloads/ATIVBatteryGuard-OEM-CALLER-EVIDENCE.zip) 하나만 새 폴더에 전부 풀고 ATIVBatteryGuard.exe를 일반 권한으로 실행할 수 있습니다. [소스 ZIP](../downloads/ATIVBatteryGuard-OEM-CALLER-EVIDENCE-SOURCE.zip)은 개발용이며 함께 풀지 않습니다. [체크섬](../downloads/ATIVBatteryGuard-OEM-CALLER-EVIDENCE-SHA256SUMS.txt)도 제공합니다. 이전 ZIP은 보존합니다.

현재 계열의 실제 배포 원본까지 확보했지만 펌웨어65/66 처리·현재 지원 flag·신뢰할 설정 read-back은 여전히 미확정입니다. 다음 제어 구현은 이 연결을 입증하는 정적 근거가 확보된 범위에 한합니다. 추가 노트북 시험·관리자 비교·파일 재제출·원본 실행·OEM 반복·예약 초기화·드라이버/서비스/보안 변경은 필요하지 않습니다.
