# 최초 보호 설정0→1 단발 시험 — 구현 승인 검토안

**승인·구현 후속:** 사용자가 이 구체안에 **“그래 진행해.”**로 명시 승인했습니다. [구현·새 ZIP·실행 안내](PROTECTION_0TO1_IMPLEMENTATION.md)에 승인 범위의 단발 도구와854회귀/두 Release 빌드0경고·0오류를 기록했습니다. 실제 노트북 호출은 사용자의 수동START에 한정되며, 아래는 승인 전 검토안입니다.

2026-11-09 한국 시간 · 기준 `2923cd6`

**이번 승인 대상은 별도 단발 시험 도구의 구현·빌드·오프라인 검증·다운로드 제공입니다.** 제공된 도구의 실제 호출은 사용자가 같은 계정에서 수동 관리자 실행 후 범위를 읽고 `START`를 직접 입력할 때만 한 번 시도합니다. 클라우드에서는 실제 노트북·SDK/OEM 호출을 하지 않습니다. 이 문서 작성만으로 쓰기 예산이나 실행 승인이 생기지 않습니다.

## 사용자가 승인할 변경과 영향

목적은 **그때의 사전 모드 후보가0일 경우에만 고정 의미의 설정1을 최대1회 요청하고, 이후 저장 모드·상한·하한을 독립 조회하는 것**입니다. 기존 Access1의 과거 후보0은 재사용하지 않습니다.

**이 시험은 보호 모드와 기존 임계값을 바꿀 수 있습니다.** 선택된 setter의 정상0→1 경로는 모드1·상한80·하한75를 기록합니다. 따라서 기존 임계값이 덮어써질 수 있으며, 단순한 상태 조회나 잠깐 켠 뒤 자동 원복하는 시험이 아닙니다. 이번 도구에는 끄기·역방향1→0·이전 임계값 복원 기능을 넣지 않습니다. 재부팅·절전으로 원복된다고 보장하지 않습니다. 알려진1→0 본문도 이전 임계값을 되돌리는 동작이 아니므로 자동 rollback을 추가하지 않습니다.

사후 후보가1/80/75로 일치해도 **저장 후보 비교 결과**입니다. setter가 실행됐다는 독립 ACK, 충전기 레지스터 적용, 전기적 충전 제한 성공으로 표시하지 않습니다. 일반 앱의 실제 제어는 Unsupported로 유지합니다.

## 고정 범위와 호출 한도

| 항목 | 구현할 한도 |
| --- | --- |
| 장치 범위 | Windows10 x64·.NET Framework4.8·기존 `940X3G/930X3G` / `P05ACJ.128.140819.dg` profile만. 불명·불일치면 firmware method0 |
| 시도 | 새 목적의 영속 준비1회. claim 뒤 준비 실패·중단·권한 거부·timeout도 소모 |
| CallSabiFunction의 SDK InvokeMethod 진입 | 전체 최대7회 = 고정 byte 읽기 최대6회 + 의미상 설정1 최대1회. metadata/속성 연산 횟수와 구분 |
| 수용 읽기 후보 | 최대6개. setter의 입력 echo는 읽기 sample이 아님 |
| 설정 입력 | 고정1만.0·다른값·임의 주소·임의 명령·직접 임계값 쓰기 없음 |
| 대기 | 전체 owner 획득 최대2초.7단계 Run 시작 기준 전체 표시 deadline10초. 실제 종료 join은 별도이며 timeout으로 끝내지 않음 |
| 제외 | handshake·삼성 DLL 초기화·재시도·resample·다른 분기/B·자동 repair·반대 쓰기·rollback·추가 조회 모두0 |

순서는 변경할 수 없습니다. 각 단계의 정상 응답과 관련 실제 종료가 모두 확인된 뒤에만 다음으로 진행합니다.

| 순서 | 동작·진행 조건 | 중단 조건 |
| --- | --- | --- |
| 1 | 사전 모드 고정 읽기, 수용 후보0만 진행 |1·불명·실패이면 즉시 종료. 뒤 두 사전 임계값과 setter도0회 |
| 2–3 | 사전 상한·하한 고정 읽기 | byte 비교 기준으로 보존. 범위·형식·귀속 실패나 입력echo와 구별 불가이면 setter0회 |
| 4 | 의미상 설정1 최대1회 | 실패·불명·중단이면 후속0회. 정상 `ReceiptOnly`와 실제 close가 모두 있어야 진행 |
| 5–7 | 사후 모드·상한·하한 고정 읽기 | 모드1·상한80·하한75를 각각 비교. 첫 불일치/모호함에서 중단, 추가 쓰기·조회0회 |

사전 임계값은0..255의 비교 기준이며, 이미80/75일 필요가 없습니다. 상·하한 역전이나 특이한 byte도 그것만으로 firmware 오류라고 부르지 않습니다. 다만 읽기 표본이 입력 첫 성분과 겹치면 합법적인 저장 byte와 미갱신echo를 구별하지 못하므로 후보 없이 중단합니다. 이를 피하려고 주소·입력·명령을 바꾸지 않습니다.

여러 읽기는 원자적 snapshot이 아니며 사전0과 setter 사이는 compare-and-set이 아닙니다. 사이에 모드가 바뀌면 setter가 같은 값으로 조기 반환할 수도 있습니다. 사후 불일치에서 자동 토글·재설정으로 고치지 않습니다.

## 토큰·사용자 시작·영속 예약

실행 순서는 현재 토큰 읽기 → 범위·영향 안내와 직접START → 새 목적 영속 claim/flush → profile/metadata/RNG 준비 → 전체 owner → 단계별 lazy SDK 준비·호출·정리입니다. NotElevated/Unknown이면 START·예약·WMI 전에 종료합니다. 같은 계정의 수동 관리자 실행만 안내하며 자동UAC/runas·계정/SID 수집·권한 조정·보안 설정 변경은 없습니다.

새 purpose와 marker는 `Protection0To1-v1` / `Protection0To1-v1.attempt`로 고정할 안입니다. 승인 후 기존 예약 방어 규칙을 재사용해 같은 사용자 고정 LocalAppData 위치에서 CreateNew·WriteThrough·Flush(true)한 뒤만 진행합니다. 기존/빈/중단 marker와 저장소 불명은 거부하며, 파일·폴더·버전·계정 변경으로 반복하도록 안내하지 않습니다. per-user 제한을 machine-wide 보안 경계라고 부르지 않습니다.

기존 A·Access1·Query65 marker의 존재 확인·읽기·삭제·초기화·복구·재사용은0입니다. 새 도구는 옛 예약을 가져오거나 기존 단발 EXE를 다시 실행하지 않습니다.

## 고정 요청과 비교 내용

새 purpose 전용 sealed plan이 일곱 역할과 고정 대상·선택 분기·명령·의미 입력을 묶습니다. 실제 SDK 진입 전 MethodID/command/전체 frozen frame/observer/target/input의 대응을 검사합니다. 외부에서 주소·명령·payload·단계 수·재시도·입력값을 받는 실행 API를 만들지 않습니다. 기존 `WsabiWmiSingleReadPlan`의 설정쓰기0 선언이나 `PrepareFixedReadAAsync`를 설정 허가로 재해석하지 않습니다. 일반 `PrepareSdkAsync` 차단도 유지합니다.

비교 내용은 RNG로 **56byte를 한 번만 채워7×8개로 나누는 안**으로 고정합니다. 각 tuple의 전체zero 또는7개 사이의 중복이 있으면 첫 method 전에 중단하고 다시 뽑지 않습니다. 이 생성은 request의 고정 의미를 바꾸지 않습니다. 입력 비교·보존 내용이 응답 신선도나 실제 대상 실행을 인증하지 않는 한계는 유지하며, 기존 단발 충돌 모델을7단계 성공 신뢰도로 확대하지 않습니다.

모드·상한·하한의 source 대응과 의미상 setter 선택·입력 위치는 저장 분석을 재사용합니다. 새 selector 탐색·원본 재수집·전체 firmware 재분석을 반복하지 않습니다. 실제 실행용 byte 생성·새 SDK 연결 코드는 승인 후에만 작성합니다.

## SDK 연결의 구체 변경 지도

| 위치 | 재사용 / 새 구현 |
| --- | --- |
| Core | 내부 coordinator/binding/두 raw 판정기는 유지. 새 fixed-purpose plan과 작은 public façade 및 typed leaf/cleanup 계약을 추가해 내부 engine을 감쌈. 일반 명령 실행 API·공개 coordinator/binding·모든 internals 공개·Core source 중복 링크는 하지 않음 |
| Core 전송 | `WsabiWmiInvocationSnapshotTransport` + `WsabiWmiBoundFrameChannel`의 gate 없는 경로를 재사용. per-frame owner·별도 표시 timer를 만드는 기존 `InvocationSession`/PreparedInvocation 전체를7번 감싸지 않음 |
| WmiInterop | 새 purpose 전용 entry와 내부 lazy leaf factory. 실제 SDK target·observer·입력 bundle을 묶고 frozen request를 확인한 뒤 기존 async `CallSabiFunction` dispatch 형태를 최대1회 사용 |
| 입력 준비 | target/profile·metadata 사실, atomic input-pair claim·PopulateOwned의 공통 내부 부분을 분리 재사용. 기존 A의 공개 wrapper·settingwrites0 범위와 동작을 보존 |
| callback/출력 | 전용 observer의 일회용 claim, detached copy, selected/related 출력 disposal·handler join·unsubscribe 상태를 재사용. CallCanceled는 실제 종료 아님 |
| 별도 도구 | `ATIVBatteryGuard.ProtectionTransitionTrial.exe` 신규 프로젝트. 일반 App·자동실행·서비스·driver·controller 지원은 바꾸지 않음 |
| 저장·배포 | 새 전용 marker·정제 TXT·정확한 allowlist 패키저. 기존 EXE/ZIP은 당시 byte로 보존 |

façade는 Core 내부형을 다른 assembly에 복제하거나 전체 `InternalsVisibleTo`로 열지 않기 위한 제한된 계약입니다. 실제 WmiInterop entry는 sealed purpose와 검증된 target만 받고 내부에서 SDK factory를 구성합니다. 호출자가 제공하는 임의 dispatcher/frame을 실제 실행 entry에 넘기지 않습니다. Core에는 `System.Management` 의존성을 추가하지 않습니다.

Core의 단계별 논리 identity는 Start 전 준비 handle입니다. 실제 SDK 입력·observer는 허용된 해당 Start 안에서만 만들고, 기존 input-pair/observer registry로 실제 SDK 객체의 재사용도 거부합니다. 따라서 중단 뒤 미시작6개의 SDK 자원이 정리에서 누락되는 경로를 만들지 않습니다.

한 owner가 첫 단계부터 마지막 정리까지 gate를 유지합니다. SDK source는 기존 transport worker에서 dispatch될 수 있으며, gate 획득·단계 Start 입장·lease 해제는 같은 owner thread입니다. SDK 호출 자체까지 owner thread로 옮기는 불필요한 재작성을 요구하지 않습니다.

종료는 호출 stack·해당 terminal/capture·token등록 종료, 출력/handler/subscription 정리, 두 입력 정리의 합성입니다. 모두 정상이어야 ActualClose이고 Failed/Unknown/fault/cancel은 성공으로 변환하지 않습니다. target은 전체 procedure 동안 외부 mutation·Dispose·독립 dispatch 없이 보유하고, 전체 join 뒤에만 정리합니다. 준비 도중 중단도 부분 생성 자원과 관련 작업을 먼저 join합니다.

## 중단·오류·결과 의미

setter 역할 입장, 실제 SDK InvokeMethod 진입, EC 처리와 설정 효과는 서로 다릅니다. setter 입장/진입 뒤 timeout·중단·reply 거부가 생기면 **변경 여부Unknown**이지 ‘변경 안 됨’이 아닙니다. 이미 입장한 호출이 취소됐다고 주장하지 않으며, 후속0회·추가쓰기0회로 끝납니다. SDKCancel·합성final·watchdog·강제 종료·자동 재시작은 없습니다. 실제 종료가 불명이면 관련 수명과 lease를 보유하고 Pending을 유지합니다.

TXT에는 profile 판정·단계 상태, 역할 입장 수, 실제 SDK 진입 수/설정 진입 수, 수용 읽기 후보 수와 사전/사후 숫자 후보, receipt 판정과 정리 상태를 따로 기록합니다. SDK 진입도 EC 처리 성공 수라고 부르지 않습니다. raw frame·비교값·전체 경로·계정명·SID·고유 식별자·예외 원문은 기록하지 않습니다. 새 결과 파일만 후속 분석 대상으로 삼고 옛 TXT/DLL/EXE 재제출을 요구하지 않습니다.

## 적용 전제와 승인 후 출하 기준

[이전 단발 구현 검토안](READ_TRIAL_A_IMPLEMENTATION_PROPOSAL.md)의 정정된 정상 플랫폼 전제를 재사용합니다. 정상 proxy/private backend 초기화, 정상 Foundation entry의 관련 typed inline 처리·반환, 같은 초기화 완료·비재진입 P05 stream, 조건부 ISA/bank·indexed↔XDATA 및 SDK/whole-exchange 계약입니다. Access1 후보0은 고정 읽기 경로에 대한 사용자 관측이며 이 전제 전체·setter·임계값·충전 효과를 새로 입증하지 않습니다. 구체 반례가 생기면 해당 범위를 재평가하되 provider 본문·모든 writer 부재·live 전체hash·반복 자료 제출을 새 절대조건으로 추가하지 않습니다.

승인 후 구현에서는 다음을 통과한 도구만 제공합니다.

1. 저장 proof를 근거로 생산 encoder를 재사용하지 않는 별도 기대 byte/역할 대조로7개 frozen 요청을 확인하고, 입력 변조·잘못된 역할/target/observer·generic entry를 거부합니다. 같은 proof의 검산을 새 독립 firmware 증거로 세지 않습니다.
2. 기존804개와 새 RNG/영속claim·SDK stand-in·lazy 부분준비/미시작 정리·전체 owner·별도 facade 조합 회귀를 실행합니다. 실제assembly 경계도 net48 참조 빌드로 검증하며, 테스트의 같은assembly source-link만으로 충분하다고 하지 않습니다.
3. 실제 SDK dispatch 계측과 역할 입장 수를 구분하고 최대7/설정1/sample6·사전0 조건·첫 실패 중단·정리 불명 보유를 검증합니다.
4. 일반 앱·A/Access1/Query65 경계와 기존 ZIP 보존을 확인합니다. 새 ZIP은 도구EXE/Core/WmiInterop/config+안내/BUILDINFO/SHA의 allowlist로 만들고 CRC·내부SHA·build bytes·source pin·x64/net48/asInvoker를 확인합니다. 삼성 원본 DLL·firmware·PDB·옛 실험 EXE는 포함하지 않습니다.

현재804통과와 두 Release 빌드0경고·0오류는 `2923cd6`의 **이전 검증**입니다. 이번 문서는 실제 설정용 코드·도구를 추가하지 않았으므로 이를 새 구현의 통과 수치로 주장하지 않습니다. 구현 뒤 새 검증 수치와 다운로드 링크를 제공하며, 보안 기능이 차단하면 우회하지 않습니다.

## 승인이 필요한 이유

프로젝트 [AGENTS.md](AGENTS.md)는 **“커널/펌웨어 제어 코드 추가 작업은 사용자에게 별도의 명시적 승인을 받은 뒤 안전성과 모델 적합성이 입증된 범위에서만 진행한다.”**고 명시합니다. 이번 안은 최초로 실제 보호 설정을 바꿀 수 있는 코드·도구를 만드는 범위라 이 규정이 적용됩니다. 과거의 읽기1회 승인과 이번 일반적인 개발 재개 요청을 새 설정 쓰기 승인으로 확대하지 않습니다.

이 문서의 범위로 구현·오프라인 검증·단발 시험 도구 제공을 승인받은 뒤 진행합니다. 실제 실행은 사용자의 수동START에 한정되며 그 전에는 새 method/쓰기0입니다. 자동 상시 충전 제어, 복원 서비스, 역방향 시험과 추가 시도는 포함하지 않습니다.
