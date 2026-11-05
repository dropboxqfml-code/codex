# P05ACJ 외부 SABI 등록 추적·원본 검사 보강 — 2026-11-05

추가 업로드는 필요하지 않습니다. 사용자가 직전 [P05ACJ 응답 근거 반영판](FIRMWARE_REPLY_EVIDENCE_UPDATE.md)의 실행을 보고했습니다. 이는 실행 확인이며 과거 FF의 전체 데이터·실패 원인이나 실제 충전 제어를 확인한 결과는 아닙니다. 이번 개발은 확보한 이미지의 외부 등록 경로 분석과 개발용 원본 검사 보강입니다. 앱 실행 파일과 기존 배포 ZIP은 변경하지 않았습니다.

## 분석 범위와 출처

이전 보고서의 실제 P05ACJ.cap SHA-256 `052660c18e967f7f73b2881379066bde4b90b29192ce4292c8d29bef1ce92ab0`에서 추출한 동일 FV의 파일을 사용했습니다. 기존 GUID 일치 목록34개 전체의 실행 section을 Capstone5.0.6/pefile2024.8.26으로 정적 디스어셈블하고, 실제 참조가 있는 외부 모듈은 descriptor 준비 → 해당 인터페이스 획득 → 공개 등록 메서드 호출을 따라갔습니다. 제조사 EXE/DLL/UEFI/AML은 실행·로드하지 않았고, 하드웨어·포트·메모리·EC·UEFI 변수·예약 표식을 읽거나 쓰지 않았습니다. 원본과 디스어셈블리는 비공개 캐시에만 보존합니다.

**34개는 실제 소비자/등록자 수가 아니라 GUID 바이트 포함 후보 수입니다.** 직접 RIP 상대 코드 참조가 복구된 파일은6개입니다. 그중 제공자 SecSabiDispatch와 중계 SecLagacySabi를 제외한 외부 등록자는4개이고, 아래 main/sub 등록 경로10개를 복구했습니다. 나머지28개에서 해당 GUID 직접 참조를 복구하지 못했지만 계산된 참조·공유 테이블·동적 변경·다른 볼륨을 닫은 것은 아닙니다. 미관측을 미사용/기능부재로 해석하지 않습니다. 이전 private 목록의 protocol-consumers라는 파일명도 실제 소비 입증으로 취급하지 않습니다.

## 실제 복구한 외부 등록 경로

아래 숫자는 모두16진수이며 main은0x5843입니다. callback RVA는 위 이미지 모듈 안의 정적 위치로, 장치 주소나 실행 지시가 아닙니다. 초기화 선행 조건과 오류 분기가 있어 실제 부팅에서의 등록 성공은 관측하지 않았습니다.

| 모듈 | sub → callback RVA | 확인한 문맥 |
| --- | --- | --- |
| SecWirelessDev | 12→620, 13→668, 69→6C4, 6A→75C | 해당 GUID LocateProtocol 후4개 descriptor 등록 루프. 배터리 계약은 입증하지 않음 |
| SecSwSmiDispatch | 78→66C | KBDBacklitLvl 변수 문맥 |
| SecSwSmiDispatch | 67→B58, 68→B98 | Setup·SecUsbCtrlStarted 초기화 문맥. 비슷한80/81 입력을 배터리 명령으로 대체할 수 없음 |
| SecAlwaysOn | 6D→2A0, 6E→33C | 모듈 상태와 SecSleepType·설정 처리. 배터리80/100% 의미는 입증하지 않음 |
| SecSetupWin | 7C→498 | 협상과 공유 통신구조 발견용. 별도 설정 경로에 인증·UEFI 변수 읽기/쓰기 포함 |

재검사 가능한 모듈 식별은 다음과 같습니다. 이 해시는 사용자 식별자나 현재 장치의 펌웨어 증명이 아닙니다.

| 모듈 | 바이트 | SHA-256 |
| --- | ---: | --- |
| SecWirelessDev | 11,296 | 300bad958d191cf73719048ca61ad19053c4c7dffc1dcc834a35be4ab8861d7b |
| SecSwSmiDispatch | 11,744 | fc8d0f6968b18843243dd906104fba88770ccb73c8adf4a8e559bcdd08d11c9a |
| SecAlwaysOn | 6,496 | f550a74df96680ed7a2d0b041c5fbbec62afd899e89d1adfb858671b09419d1b |
| SecSetupWin | 23,552 | 85746029af1b2beccf415104e866f570f4e627bd568858b7278664c2351df3f8 |

대표 근거는 Wireless의 LocateProtocol3B8/등록3DA 루프, SwSmi의78등록A94와67/68등록1018, AlwaysOn의Locate582/등록59F 루프, SetupWin의descriptor311E–313E/Locate3153/등록317A입니다. 숫자 상수나 GUID 존재만으로 이 표를 만들지 않았습니다. SecSwSmiDispatch의C28/D08 콜백은 다른 이벤트 인터페이스의 별도 selector이며 SABI68의 callback으로 혼동하지 않습니다.

## 7C를 배터리 대체 조회로 사용하지 않는 이유

SecSetupWin의 실제 callback은RVA498입니다. callback은 데이터20바이트를 복사/초기화하고 협상 상태와 입력을 확인해 공유 통신구조를 발견하게 합니다. 이는 배터리 잔량·보호 boolean 응답이 아닙니다. 별도 핸들러3408 → 분배4FC → 설정 처리ED4를 더 따라가면 인증 분기와 EFI RuntimeServices의 GetVariable/SetVariable로 연결됩니다. **이 설정 경로를 읽기 전용 대체 조회로 사용할 수 없습니다.**

설정 캡션 USB Charge In Sleep Mode도 확인했지만 USB 수면 중 충전과 노트북 배터리 상한은 다른 대상입니다. 기존 HII Battery Life Cycle Extension/80%·100% 도움말과 이 처리자 또는65/66 등록 사이의 연결은 복구하지 못했습니다. 도움말 문자열·비슷한80/81 입력·EC 관련 모듈명만으로 새 제어 경로를 연결하지 않습니다.

AlwaysOn의 입력 검증 실패가 EFI 오류를 반환하는 예도 확인했습니다. 이 경우 공통 디스패처의 FF 경로로 합류할 수 있어 **FF는 미등록뿐 아니라 등록된 callback의 입력 오류에서도 나올 수 있습니다.** 과거 첫FF만으로 이 조건을 선택하거나 전체 실패 패턴을 복원할 수는 없습니다.

## 오프라인 서명 검증에서 추가로 확인한 범위

동일 원본 패키지를 trusted OpenSSL3.5.7과 pefile로 데이터로만 검사했습니다. PE checksum·certificate directory 항목·인증서 영역을 제외하고 헤더·5개 raw section·LPCK overlay를 포함해 계산한 Authenticode SHA-1은 `36d873d74ee730faadac50223abc2e2b468b3f14`이며 서명된 content의 digest와 일치했습니다. 신뢰 체인 검사를 생략한 OpenSSL PKCS#7 서명 수학검증도 성공했고, 서명1비트 변조는 거부되며 이미지1비트 변조는 digest 불일치가 됐습니다. 단순 PKCS#7 구조 관측보다 진전된 근거입니다.

내장 signer 인증서의 subject는 Samsung Electronics CO., LTD.를 표방합니다. 하지만 임베디드 인증서를 신뢰 루트로 승격하지 않은 시스템 CA 체인 검증은 issuer 부재로 실패했습니다. 타임스탬프 서명/체인·폐기 조회·Windows Authenticode 정책은 검증하지 않았습니다. 인증서의 과거 만료일만으로 정상 타임스탬프 서명의 유효성을 부정하지 않으며, subject 문자열이나 수학검증만으로 제조사 신뢰를 보증하지도 않습니다. **전체 authenticodeVerified는 false로 유지**합니다. 인증서 설치·네트워크 요청·원본 실행은 없었고 이 결과는 플래시/명령 실행 승인이 아닙니다.

## 이번 코드 변경: 관측 원본과 다음 분석의 일치 강제

개발용 `scripts/inspect_command_research_artifact.py`의 p05acj 사양을 실제 관측 패키지5,822,368바이트/SHA-256 `374c768a09211ce8da6e0812bde870e3b90957bf8b38e2289cac4dc52857e7fd`로 고정했습니다. 크기나 해시가 다르면 PE 해석 전에 거부하고, 일치한 뒤 PE 구조가 정상일 때만 `ObservedSourcePayloadMatched`를 반환합니다. 기존 CLI는 임의 기대 해시/길이 인수를 허용하지 않습니다.

이는 **이전에 관측한 바이트와의 일치**입니다. HTTP로 받은 원본의 제조사 진위·서명·현재 모델 동일성·배터리 계약을 검증하는 신뢰 기준이 아닙니다. authenticodeVerified/currentModelCompatibilityVerified/batteryCommandContractVerified 및 하드웨어 권한은 모두false로 유지합니다. 다운로드·추출·외부 프로그램·라이브러리 로드·OEM 실행 기능은 추가하지 않았습니다.

합성 PE의 구조 경계 테스트는 원본 신원 검사와 분리합니다. legacy BLE는 기존처럼 크기/해시가 없으면 ZIP이 정상이어도 검증되지 않도록 유지했습니다. 독립 코드 검토에서 이 순수 API 경계의 퇴행을 찾아 수정하고 회귀 테스트로 고정했습니다.

## 검증과 배포

Python 전체 **46개 통과**(reports/p05acj-registration-python-tests.log). 신규4개는 P05ACJ 크기/해시의 PE 해석 전 거부, 관측 일치 후에도 진위/권한false, 일치 바이트의 잘린 PE 거부, pin 없는 legacy ZIP의 검증 거부를 검사합니다. 고정 CLI와 기대 해시 덮어쓰기 거부도 확인했습니다. 실제 보유 P05ACJ 파일은 `ObservedSourcePayloadMatched`·PE5sections이고 진위/모델/계약/권한은false였습니다(reports/p05acj-observed-source-review.json).

C#/XAML·실행 파일은 바꾸지 않아 빌드와 C# 테스트는 이번에 반복하지 않았습니다. 직전434개 통과/빌드 경고·오류0개는 이전 버전의 검증 기록입니다. 기존 프로그램 ZIP을 그대로 사용하며 새 OEM 시험·관리자 비교·자료 재제출은 필요하지 않습니다. 새 개발 소스는 [별도 소스 ZIP](../downloads/ATIVBatteryGuard-P05ACJ-REGISTRATION-SOURCE.zip)으로 제공하며 실행에 필요하지 않습니다. 삼성 원본·펌웨어·사용자 원문·실행 파일은 포함하지 않습니다.

## 남은 병목과 다음 범위

확인한 외부 등록 경로10개와 이전 내부 초기화21개 루틴의 제한된 추적에서는 **현재 모델의65/66 배터리 callback 연결을 복구하지 못했습니다.** 정적 미관측이 전체 미등록·장치 미지원 증명은 아니지만, 구형65/66 입력을 반복하거나 비슷한67/68·6D/6E·7C로 바꿔 시험할 근거도 없습니다. 현재 FF의 발생 경로와 실제 충전 제한 가능성은 미확정입니다.

다음은 이 등록 지도를 기준으로 기존 Windows 호출자 분석 기록과 현재 모델에 적용되는 OEM 호출자의 선택/응답 계약을 대조하는 것입니다. 새 근거는 모델·전송·등록·입출력·의미를 따로 입증해야 합니다. 등록을 완전히 닫지 못했거나 명령 의미가 불명확하면 실행 경로를 추가하지 않습니다. 제어는 Unsupported이며 완료된 실험/예약을 유지합니다.
