# 승인된 최초 보호 설정0→1 단발 도구 — 2026-11-09 한국 시간

사용자가 [구체 구현안](PROTECTION_0TO1_IMPLEMENTATION_PROPOSAL.md)에 **“그래 진행해.”**로 명시 승인했습니다. 승인 범위의 고정 요청·새 영속1회 예약·실제 SDK 연결·빌드·오프라인 검증·패키징을 완료했습니다. 클라우드에서 실제 Windows SDK/OEM·노트북 설정 호출은 하지 않았습니다. 새 도구의 Windows/노트북 실행은 아직 미검증입니다.

## 다운로드와 실행

1. [ATIVBatteryGuard-PROTECTION-0TO1.zip](../downloads/ATIVBatteryGuard-PROTECTION-0TO1.zip) **하나를 새 로컬 폴더에 모두 풉니다.** 다른 ZIP·기존 프로그램·삼성 DLL과 합치지 않습니다.
2. 같은 계정에서 **`ATIVBatteryGuard.ProtectionTransitionTrial.exe`만 오른쪽 클릭 → 관리자 권한으로 실행**합니다. 목적 `Protection0To1-v1`과 현재 토큰 `Elevated`를 확인합니다. 다른 계정 암호나 보안 우회가 필요하면 중단합니다. 자동UAC/runas·driver/service 설치·보안 설정 변경은 없습니다.
3. **모드1·상한80·하한75가 기록되어 기존 임계값이 덮어써질 수 있습니다. 끄기·역방향·이전 임계값 복원·자동rollback은 없고 재부팅·절전 원복도 보장하지 않습니다.** 이 영향을 이해하고 이번1회 시험을 진행할 때만 `START`를 직접 입력합니다. 실행만 하거나 다른 입력이면 firmware method를 호출하지 않습니다.
4. 같은 폴더에 생성되는 **새 `protection-0to1-result-*.txt`만** 전달합니다. 옛 TXT·삼성 DLL·EXE 재제출은 필요 없습니다.

**START 뒤에는 실패·중단·timeout도1회를 소모합니다. 재실행하거나 예약을 삭제·변경하지 않습니다.** Pending/실제 정리 대기 중에는 창·프로세스를 강제로 닫거나 다시 실행하지 않고 기다립니다. `관련 정리: Complete` 또는 호출 전 종료 안내 뒤에만 Enter로 닫습니다. 표시10초는 firmware 강제 중단 시간이 아닙니다. Ctrl+C도 중단 의사만 전달합니다.

대상은 Windows10 x64·.NET Framework4.8·기존 `940X3G/930X3G` / `P05ACJ.128.140819.dg` profile입니다. 미서명 개발 빌드입니다. 새 ZIP은 자체 EXE/Core/WmiInterop/config+안내/BUILDINFO/SHA의7항목이며 삼성 원본 DLL·firmware·PDB·옛 실험 EXE를 포함하지 않습니다. 일반 앱을 상시 관리자 실행하도록 바꾸지 않았습니다.

## 실행 범위

| 순서 | 요청·진행 조건 |
| --- | --- |
| 1 | 사전 모드 고정 읽기. 수용 후보0만 진행.1·실패·불명은 바로 종료 |
| 2–3 | 사전 상한·하한 고정 읽기. 비교 기준 byte로 보존하며 echo와 구별 불가·형식 실패는 설정0회로 중단 |
| 4 | 의미상 설정1 최대1회. 정상 `ReceiptOnly`와 관련 실제 close가 모두 있어야 진행 |
| 5–7 | 사후 모드·상한·하한을 독립 조회해1/80/75 비교. 첫 불일치·오류에서 중단 |

CallSabiFunction의 **SDK InvokeMethod 진입 최대7회 = 읽기최대6 + 설정1최대1**입니다. 새 준비1회·수용 byte 후보최대6이며 setterecho는 읽기 sample이 아닙니다. 초기화·handshake·재시도·resample·B/다른 주소·명령·직접 임계값 쓰기·추가 조회·역방향·복원은0입니다. 사전 임계값이 이미80/75여야 한다는 조건은 없지만, 합법 byte라도 입력 첫 성분과 같아 echo와 구별되지 않으면 보류합니다.

이전 Access1의 후보0을 현재 사전값으로 사용하지 않습니다. 여러 읽기는 원자적 snapshot이나 compare-and-set이 아닙니다. 같은 값으로 바뀌어 setter가 조기 반환하거나 사후 값이 예상과 달라도 자동 토글·repair하지 않습니다.

## 구현과 종료 계약

새 sealed attempt는 profile·metadata·단일 Active 대상·MethodID1을 검사하고56byte RNG1fill을7×8로 나눕니다. 전체zero·중복tuple은 호출 전 중단하며 다시 뽑지 않습니다.7개 요청의 역할·명령·전체21byte를 고정하고 실제 SDK 진입 전 다시 대조합니다. 외부 임의 명령·주소·payload를 받는 실행 entry는 없습니다.

Core의 고정 목적 façade가 내부7단계 owner/binding과 gate 없는 snapshot transport/channel을 연결합니다. WmiInterop의 내부 factory가 해당 Start 안에서만 실제 SDK 입력·관찰자를 만들고 기존 input-pair/observer 일회용 registry를 재사용합니다. 처음부터7개의 SDK 자원을 만들어 미시작 단계 정리를 놓치지 않습니다. 기존 A의 설정쓰기0 plan/entry·일반 entry 차단은 유지합니다. Core에 `System.Management`·전체 internals 공개·소스 중복 링크를 추가하지 않았습니다.

한 owner가 획득부터 마지막 실제 정리까지 gate를 유지하고 같은 owner thread에서 해제합니다. 호출 stack·해당 terminal/capture/등록 종료 → 출력/handler/subscription 정리 → 두 입력 정리의 순서를 지킵니다. 출력 정리가 Complete가 아니면 입력을 조기 해제하지 않습니다. Failed/Unknown/fault/cancel은 owner와 참조를 보유한 Pending이며 SDKCancel·합성final·watchdog·강제 종료·자동 재시작이 없습니다.

SDK 진입 전 guard가 source 입장 뒤 거부하면 SDK 진입0이어도 Pending일 수 있습니다. 카운터0을 실제 source 종료 증거로 사용하지 않습니다. 표시 결과 뒤에도 실제 join을 기다리고, 관련 정리 뒤에만 borrowed target을 정리합니다.

## 새 예약과 정제 결과

현재 토큰 확인 → 안내·직접START → 새 고정 `Protection0To1-v1.attempt`의 CreateNew/WriteThrough/Flush(true) → profile/metadata/RNG 준비 → 전체 owner·lazy SDK 순서입니다. NotElevated/Unknown은 START·예약·WMI 전에 종료합니다. 같은 사용자 고정 LocalAppData 위치를 사용하며 저장소 불명·reparse/UNC·기존/빈/중단 예약은 거부합니다. per-user 제한을 machine-wide 보안 경계라고 하지 않습니다.

기존 A·Access1·Query65 예약의 존재 확인·읽기·삭제·복구·초기화·재사용은0입니다. 새 도구를 다른 폴더·계정·버전으로 다시 실행하도록 안내하지 않습니다.

TXT는 역할 입장·SDK 진입/설정 진입·수용 후보·전이 모델 수용 수를 분리합니다. 단계별 binding/read/setter 판정과 gate/전이 상태를 기록하고, 표시 시점 진단·카운터와 실제 종료 뒤 최종 진단·카운터도 구분합니다. raw frame·비교 내용·전체 경로·계정명·SID·고유 식별자·예외 원문은 출력하지 않으며 실행 중 네트워크 통신은0입니다.

**1/80/75 일치는 저장 후보 비교이며 실제 충전기 적용·전기적 충전 제한의 성공이 아닙니다.** SDK 진입도 EC 처리 성공 수가 아닙니다. setter 입장/진입 뒤 실패·중단·timeout이면 변경 여부Unknown으로 남기고 ‘미변경’이나 취소 성공으로 단정하지 않습니다. 일반 앱의 실제 보호 조회·충전 제어는 Unsupported입니다.

## 검증·배포 기록

새50개(고정attempt11·예약9·façade13·SDK대역10·host7)를 포함해 **854통과·0실패·0skip**입니다. 기존804개도 재실행했습니다. portable와 전체 net48 참조 Release 빌드는 각각0경고·0오류이며 실제 assembly 경계로 새 EXE/Core/WmiInterop을 함께 빌드했습니다. SDK/host 회귀는 합성 응답·명시적 대역 수명·임시 폴더를 사용하며 실제 Windows SDK나 노트북의 실행 검증이 아닙니다.

Release IL에는 `ConfirmDetachedForTests`·`PrepareForTests`·가짜 System.Management 타입이 없음을 확인했습니다. 시험용 helper는 `PORTABLE_TESTS` 조건으로만 포함됩니다. 기존 gate의 영구 불명 분기는 소스 검토 범위이며, 대역 teardown의 명시적 종료 확인을 실제 SDK 복구로 배포하지 않습니다.

ZIP은 **179,605byte**, SHA256 `41dfca027365d1e3927754e6e24b7b754beee9fa51416feedb628828d97ef8d3`입니다. product source fingerprint는 `7b59fa5617934dca2a94ba93b086c50eb22668b9840ea258b898fc60d890fc31`이며 linked token/preflight helper를 포함한137개 source closure를 고정합니다. CRC·6개 내부 checksum·빌드 byte·x64/net48/asInvoker·미서명과 원본 제외를 확인합니다. [정제 검증](reports/protection-0to1-implementation-validation.json)에 source/build/suite/package pin과 한계를 보존합니다.

정상 proxy/private backend 초기화, 정상 entry의 관련 typed inline 처리·반환, 같은 초기화 완료·비재진입 P05 stream과 기존 조건부 ISA/bank·indexed↔XDATA·SDK/whole-exchange 적용 전제를 유지합니다. 이를 새로 실측했다고 주장하지 않고 새 firmware/selector 검색·live 전체hash·모든 writer 부재·반복 자료 제출을 조건으로 추가하지 않습니다. 새 실제 관측은 이 도구의 승인된1회 결과로만 평가합니다.
