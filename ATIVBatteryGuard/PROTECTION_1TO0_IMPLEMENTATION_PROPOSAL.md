# Protection1To0-v1 — 보호 해제 최소 시험의 구체 구현 승인안

**구현 승인·제공 / 2026-11-09 한국 시간:** 사용자가 이 구체안의 구현·검증·공유와1회 시험 범위를 명시 승인했습니다. [구현과 사용자 작업 순서](PROTECTION_1TO0_IMPLEMENTATION.md), [새 ZIP](../downloads/ATIVBatteryGuard-PROTECTION-1TO0.zip)을 참조합니다. 해제 전 AC 관찰을 먼저 보관하며, 기존 시험을 재실행하지 않습니다. 아래는 승인 전 검토안의 기록입니다.

2026-11-09 한국 시간. 기준 `37a18d5`. **설계·오프라인 검토안이며 새 실행 코드·예약·쓰기 권한·실행 파일은 아직 없습니다.**

## 목적과 이미 확보한 근거

승인된0→1 시험은 사전0/0/0 → 사후1/80/75, SDK7/set1·정리Complete를 보고했습니다. 첫 Windows 관찰은 사용자가 충전기를 연결하지 않은16개의 방전 샘플이므로 충전 제한 효과는 아직 평가하지 못했습니다. [결과와 AC 관찰 절차](CHARGE_EFFECT_OBSERVATION_RESULT.md)를 먼저 적용합니다.

다음 제어 검증의 최소 목표는 **이번 실행에서 읽은 모드1일 때만 의미상 설정0을 한 번 요청하고, 실제 종료 뒤 독립 모드 읽기의 후보0을 비교**하는 것입니다. 원래0→1 코드·목적·예약을 바꾸거나 재활용하지 않습니다. 보호 ON 상태의 AC 관찰 전에 새 OFF를 실행하지 않습니다.

저장된 동일 EC setter 본문의 조건부 해석에서1→0은 모드0 저장과 별도 소프트웨어 상태 reset입니다. **80/75를100으로 바꾸거나 이전 임계값으로 복원하는 기능이 아닙니다.** 같은 값 요청은 조기 반환하며, 0→1은80/75를 초기화하므로 자동 OFF→ON 토글도 넣지 않습니다. 모드0의 후속 일반 충전 정책에는 별도 조건이 있으며, 저장모드0을100%충전 보장으로 표시하지 않습니다.

기존 P05 capsule·파생 EC의 조건부8051/bank 해석과 정상 Windows 플랫폼·동일 비재진입 stream 적용 전제를 재사용합니다. metadata·profile 검사는 현재 firmware 전체 이미지의 해시 인증이 아닙니다. 이전0→1 결과나 UEFI 관측을 모든 제공자·장치에서 동작한다는 보증으로 확대하지 않습니다. 새로운 selector·이미지 탐색을 반복하거나 동일 원본 자료 재제출을 요구하지 않습니다.

## 제안하는 승인 범위와 영향

구현·빌드·오프라인 검증·새 다운로드 ZIP 제공 및 사용자가 새 도구에서 직접START한 뒤의 **새 준비1회, SDK최대3회(읽기2 + 설정0최대1), 읽기 후보최대2개**에 한정합니다. 자동 시작·상시 제어·예약 재사용은 없습니다. 이번 문서를 승인하기 전에는 실제 firmware 호출용 코드를 추가하지 않습니다.

보호 해제는 충전 상한 억제를 해제하는 방향의 설정 변경입니다. 정상 충전이 재개될 수 있지만 실제 재개·완충·이전 설정 복원은 보장하지 않습니다. 이번 도구에는 ON 복원·임계값 복원·자동rollback·재부팅 원복 기능이 없습니다. 해제 시험 뒤 실패·timeout·사후 불일치가 발생해도 자동으로 다시 켜거나 재시도하지 않습니다. 사용자에게 이 영향을 먼저 설명하고 START를 받습니다.

| 단계 | 고정 동작 | 진행·종료 조건 |
| --- | --- | --- |
| `PreMode` | 이번 실행의 고정 모드byte 조회 | 수용 후보1만 다음 단계.0이면 이미 해제된 후보로 쓰기0회 종료. 다른 값·형식 실패·오류·불명·입력echo와 구별 불가는 쓰기0회 종료 |
| `SemanticSet0` | 동일한 분석 근거의 의미상 setter, 입력0만 | 최대1회. strict `ReceiptOnly`와 실제 호출·출력·입력 정리 완료가 모두 있어야 다음 단계 |
| `PostMode` | 고정 모드byte 독립 조회 | 수용 후보0이면 저장 모드 전환 후보 일치.1·불명·오류·echo는 불일치 또는 불명으로 종료 |

과거1/80/75나 새 Windows 충전 상태를 `PreMode` 대신 사용하지 않습니다. 임계값 조회와 직접쓰기0회이며, 임계값 보존을 검증했다는 주장도 하지 않습니다. 원시 frame·명령·주소·비교 내용·계정·전체 경로는 TXT에 출력하지 않습니다.

## 입장 조건과 새 예약

1. 새 전용EXE만 같은 Windows 계정에서 수동 관리자 실행합니다. 자동UAC/runas·다른 계정 우회·보안 설정 변경은 없습니다. 현재 토큰`Elevated`와 새 목적`Protection1To0-v1`을 표시하고 START를 받습니다. NotElevated/Unknown에서는 START·예약·WMI 전에 종료합니다.
2. START 뒤 새 고정 목적의 로컬 영속1회 예약을 `CreateNew/WriteThrough/Flush(true)`로 선소모합니다. 준비실패·취소·권한·시간초과도 이1회를 소모합니다. 폴더·계정·버전 변경으로 반복하지 않습니다.
3. 기존 `WindowsProtectionPreflight.Prepare()`의 Windows10x64·기존940X3G/930X3G·P05ACJ profile·정확한WMI metadata·MethodID·단일Active 대상 검사를 재사용합니다. 성공한 동일 대상만 전체 세 단계에 사용합니다. 불일치·불명에서는 SDK0회입니다.
4. A/Access1/Query65/Protection0To1 예약은 조회·삭제·초기화·변경·재사용하지 않습니다. 기존 Windows mutex identity와 공통 자원 quarantine은 그대로 존중합니다.

사전 검증용metadata 조회와 `CallSabiFunction`의 SDK 진입 수는 별도 계측합니다. 사전 검증1회가 임의 firmware 조회를 허용하지 않습니다.

## 구체 구현 경계

| 기존 구현 | 재사용 또는 새 작업 |
| --- | --- |
| `WsabiWmiProtectionTransitionAttempt` | 원래7단계·input1 고정을 보존. 새 sealed disable attempt에3역할·3개 frozen request·동일 target identity를 고정하며 임의 입력·역할·주소 API를 공개하지 않음 |
| `WsabiWmiProtectionSetterReplyReview` | input1 전용을 보존. 새 input0 receipt 판정기에 envelope/frame·실패prefix·control/tail·둘째성분·8byte 보존을 적용. output0 echo는 저장모드나 독립성공ACK가 아님 |
| `WsabiWmiProtectionTransitionReview` / `WsabiWmiSevenStageCoordinator` | 0→1·7역할 계약을 보존. 새 내부3단계 판정/owner는 pre1·receipt+actual-close·post0 순서만 허용. 가짜 생략 단계나7개 per-frame owner 반복으로 대체하지 않음 |
| `WsabiWmiInvocationSnapshotTransport` / `WsabiWmiBoundFrameChannel` | gate 없는 교환·detached 응답·고정frame binding 규약 재사용. 전체 절차에 단일owner를 유지 |
| `WsabiWmiWindowsCallbackSource` / `WsabiWmiWindowsOwnedInputPair` | 실제SDK 등록·observer/input claim과 수명 규약 재사용. 기존SDK leaf factory는 old attempt 고정이므로 새 typed factory 필요 |
| `WsabiWmiWindowsInputPreparation.PopulateProtectionOwned` | 새 typed disable entry를 추가하고 private frozen population만 공유하는 안. 임의frame 공개·소스중복link·전체internals 공개는 추가하지 않음 |
| `WsabiWmiProtection0To1FileReservation` | 기존파일 규약은 보존. 새purpose 전용예약을 별도로 작성 |
| `IChargeLimitController` / `MainViewModel` | 실제 제어를 연결하지 않음. 동기 getter가 WPF binding에서 반복될 수 있으므로 여기에 OEM 호출을 넣지 않음. 결과는 별도 시험 TXT로 보존 |

새 비교 내용은24byte 1fill을3×8byte로 나누고 전체zero·어느tuple의zero·중복이면 즉시중단하며 resample0으로 제한하는 안입니다. 비교 내용은 귀속 검토를 돕지만 nonce 인증·현재성의 독립 증거라고 부르지 않습니다. reader의 입력echo 모호함은 새비교생성이나fallback으로 해결하지 않고 중단합니다.

SDK객체는 해당 단계Start 안에서만 준비합니다. 각 단계는 자기 input-pair/source/observer/capture만 사용하며, 실제SDK 진입 직전 고정frame·동일대상·동일관찰자·목적·단계·SDK3/set0≤1을 재검사합니다. 처음부터3개 관찰자를 등록해 미시작 단계의 정리를 남기지 않습니다.

## 중단·timeout·실제 종료

전체 owner 획득 최대2초, 표시deadline10초와 관련 실제 종료 대기는 분리합니다. 한 owner가 마지막 실제 정리까지 유지되며 동일owner thread에서 해제합니다. 각 단계의 invocation 종료 → 출력/handler/subscription 정리 → 입력두객체 정리를 join한 뒤에만 다음 단계로 갑니다. output이Complete가 아니면 입력을 조기 해제하지 않습니다.

정상 receipt여도 실제 close 전에는 PostMode를 실행하지 않습니다. setter입장/SDK진입 뒤 오류·중단·timeout·불명은 **변경 여부Unknown**이며 변경 안 됨이나 복원 성공으로 바꾸지 않습니다. source입장뒤 guard거부로 SDK0인 경우도 실제 종료 증거를 대신하지 못합니다. 불명 수명은 Pending으로 참조·owner·target을 보유하며 새실행/추가해제하지 않습니다. SDKCancel·합성final·watchdog·강제종료·자동재시작은 없습니다. target은 전체join 뒤 정리합니다.

## 제외한 작업

초기화·handshake·재시도·resample·fallbackB·다른 명령·임계값 읽기/쓰기·ON 재설정·자동역방향/복원·추가현재값조회는0입니다. driver/service/portI/O/물리메모리·EFI변수·BIOSflash·보안설정 변경, 삼성원본DLL 로드·배포도0입니다. 배터리 잔량이나NotCharging을 근거로 자동 설정하지 않습니다.

## 승인 후 완료할 검증과 배포

- 고정3요청·pre1/post0·중복/재진입 차단·두reader anti-echo·input0 receipt·SDK3/set0≤1·zero/중복비교·재생성0을 회귀검증합니다.
- receipt뒤에도 실제종료 전 다음단계0, stop/timeout 뒤 후속진입0, 부분준비·미시작/중복자원·정리실패 수명보유를 SDK대역으로 검증합니다. 공통자원 quarantine과 기존mutex를 다른 목적이라고 우회하지 않는지 확인합니다.
- 새예약 경쟁·CreateNew/flush실패·소모 유지·Elevated/START 입장·TXT 정제·옛예약접근0을 검증합니다. 기존887개도 재실행합니다.
- 실제 Core/WmiInterop/새전용EXE의 net48 참조 Release 빌드와 Release IL에서 portable-only 도우미 부재를 확인합니다. 새허용목록ZIP의 CRC·SHA·프로그램byte·소스fingerprint를 독립 대조하고 실제 다운로드 링크를 검증합니다. 삼성원본·firmware·PDB·다른실험EXE·사용자TXT는 제외합니다.

이번에는 문서와 정제검토만 변경했으므로 기존887회귀·두빌드0/0을 새구현의 검증으로 주장하지 않습니다. 실제Windows·OEM·SDK·새예약 접근은0이며 새실기예산은 아직0입니다. 검토된 구현 뒤에도 일반GUI 상시제어는 별도 단계이고, 이 단발도구의 일치 결과가 이를 자동 활성화하지 않습니다.

## 승인 근거와 다음 결정

[AGENTS.md](AGENTS.md):52는 **“커널/펌웨어 제어 코드 추가 작업은 사용자에게 별도의 명시적 승인을 받은 뒤 안전성과 모델 적합성이 입증된 범위에서만 진행한다.”**고 규정합니다. 기존 명시승인은0→1 단발의 제한범위에 적용됐고 이미 소모됐습니다. 일반적인 개발재개 요청을 새1→0 쓰기의 승인으로 확대하지 않습니다.

이번 검토로 구현·중단·영향·검증·배포 범위를 구체화했습니다. **새1→0 단발 도구의 구현·오프라인 검증·다운로드 제공과, AC 관찰을 먼저 마친 사용자가 직접START할 때의 위3회 제한범위를 별도로 승인받는 것이 다음 결정**입니다. 현재 AC 관찰에는 이 승인이 필요하지 않으며 기존 앱을 그대로 사용합니다.
