# 고정 보호 저장 byte 단발 조회 — 구현 승인 검토안

**현재 상태: 조건부 구현 제안 검토 가능 / 실제 firmware 호출 구현·실행 미승인.** 이번 문서는 고정 요청·실행 코드가 아니라 다음에 구현할 정확한 범위입니다. 공개 `PrepareSdkAsync`의 `ReadSpecificationUnavailable`과 실제 보호 조회·충전 제어 `Unsupported`는 그대로입니다. [현재 명세](FIXED_READ_TRIAL_SPECIFICATION.md)와 [취소 수명 수정](SDK_CALL_CANCELED_LIFETIME_FIX.md)을 적용합니다.

## 앞선 허용 기준의 정정

제공자 기계코드 미복구와 공통 owner 미확보를 각각 추가 blocker로 쌓으면, 이미 인정한 정상 실행 stream의 순서 근거를 사용하지 못하는 기준이 됩니다. **명시적 정상 플랫폼 전제 아래 제한된 시험 제안까지 검토하는 기준으로 정정합니다.** 새로운 P05 제공자 함수를 발견했거나 현재 노트북의 순서를 직접 관측했다는 뜻은 아닙니다.

새로 확보한 공식 UDK2014 [PiSmmCore.c](https://github.com/tianocore/edk2/blob/3ccd6d8b75b7fab66a35da9e77312eaca167c0f0/MdeModulePkg/Core/PiSmmCore/PiSmmCore.c)는 같은 bootstrap Context에 실제 entry를 공급하고, 그 normal entry에서 typed 통신 처리 → 결과 게시 → NULL-root 처리를 순서대로 호출하는 대표 구현을 보여줍니다. 이 코드를 P05 binary와 동일시하거나 API 성공 문구만으로 CPU 전체 배제를 추론하지 않습니다.

| 명시적으로 적용할 전제 | 기존 사실과의 구분 |
| --- | --- |
| 정상 proxy·private wrapper/backend 초기화가 적용됨 | 저장 source의 조건부 설치 관계를 재사용. UEFI 부팅·모듈 성공 반환만으로 현재 성공을 인증하지 않음 |
| 표준 통신은 등록된 정상 Foundation entry에서 해당 typed handler를 inline 처리하고 관련 처리 뒤 반환함 | 적용할 정상 플랫폼 계약. 위 대표 구현은 구체 예시이며 새 P05 source edge가 아님 |
| 그 entry는 조회와 같은 초기화 완료·비재진입 P05 normal stream에 속함 | 기존 single-root·child/legacy 순서 근거를 재사용하고 조건을 명시. 관련 hook의 독립 AP/direct 우회가 있다는 구체 근거는 없음 |
| 대상의 조건부 ISA/bank·host indexed↔XDATA 대응과 기존 SDK/whole-exchange 계약이 적용됨 | 기존 고정 대상·입력 분리·ISR·mapper·수명 근거 유지. 현재 이미지 전체 hash를 확인했다는 뜻은 아님 |

관련 hook의 실제 AP offload·다른 실행 domain/direct-host 진입·handler 반환 뒤 deferred indexed 작업, 또는 정상 초기화·비재진입 조건의 불적용을 보여주는 구체 근거가 생기면 재평가합니다. AP API가 존재하거나 provider 본문이 없다는 사실만으로 그런 actor를 새로 가정하지 않습니다. 이미 같은 stream이 보호하는 분기에는 별도 공통 lock을 추가 요구하지 않습니다.

이 전제들은 새 runtime 승인 bool로 바꾸거나 사용자가 확인할 수 없는 live pointer 관측을 요구하는 항목이 아닙니다. 조건부 제안의 적용 범위와 반증 조건입니다. 현재 사용자 보고의 Complete·UEFI는 Windows 부팅 방식만 확인하며 위 전제를 입증하지 않습니다.

## 제안하는 한 번의 시험

| 항목 | 고정 범위 |
| --- | --- |
| 대상 profile | 보존 관측의 940X3G/930X3G 모델 문자열과 BIOS `P05ACJ.128.140819.dg`. 실행 전 해당 profile·대상 metadata를 비교하고 불일치/불명은 호출0 |
| 동작 | source로 대조한 generic read branch로 **고정 보호 모드 저장 byte 하나**만 조회. 임의 주소·명령·길이 인수 없음 |
| method·sample 한도 | `CallSabiFunction` method 최대1회, 실제 고정 byte sample은 gate·전달에 따라0~1회 |
| 추가 동작 | gate handshake·삼성 DLL/OEM 초기화·재시도·대체 명령·B fallback 각각0회 |
| 변경 금지 | 보호 설정·임계값·충전기·flash·보안 설정 쓰기0, 드라이버/서비스 변경0, 앱의 직접 port I/O·물리 메모리 접근0 |
| 대기 | 기존 상한대로 owner 획득 최대2초, 응답 표시 deadline10초. 실제 관련 종료·정리는 별도 join |
| 실행 형태 | 별도 목적의 명시적 단발 시험 도구. 시작·주기적 배터리 갱신·기존 파일 정보 버튼에서 자동 호출하지 않음 |

보호 설정을 바꾸지 않는 읽기 시험이지만, 기존 통신 규약의 입력 buffer와 EC mailbox 게시·응답 교환은 있습니다. 이 통신 동작을 모든 하드웨어 쓰기가 전혀 없는 동작이라고 설명하지 않습니다. 실제 대상 저장 byte에 쓰는 경로는 선택하지 않습니다.

새 시험 목적의 영속 1회 예약을 승인 후 별도로 구현합니다. 준비 실패·권한 거부·gate 거부·timeout도 재시도하지 않으며 같은 목적을 새 process에서 다시 실행하지 않습니다. 과거 `WmiQuery65-v1.attempt`는 확인·초기화·삭제·재사용·우회하지 않습니다. 이번에 새 예약 파일을 만들거나 그 코드를 추가한 것도 아닙니다.

표시 deadline은 firmware 강제 중단이 아닙니다. `CallCanceled`·terminal 소실·종료 불명에서는 실패/판정불가를 표시하고 입력·출력·lease를 유지합니다. 후속 실제 종료가 없으면 close가 pending으로 남을 수 있습니다. SDK Cancel·합성 final·자동 재시작을 넣지 않고, 현재 메타데이터 worker의 10초 후 강제 종료 경로를 이 시험에 재사용하지 않습니다.

## 응답의 거부와 해석

고정 profile의 command/address·전체 교환 보호를 먼저 적용하고 기존 구조/ACK·실패 prefix·입력 echo·보존 성분·반환 내용·후보 범위를 함께 검증합니다. FF·gate 거부·오류·귀속 불명은 판정불가이며 다른 명령이나 handshake로 이어가지 않습니다. gate의 source 초기값이 닫힘이라서 값을 못 얻을 수 있으며, gate-open 관측을 새 필수조건으로 추가하지 않습니다.

8개 보존 셀의 비교 내용은 승인 후 단발 RNG 선택으로 구현하고 전체 zero가 나오면 호출 전에 중단합니다. firmware 재시도는 없습니다. [기존 nonzero 단발 충돌 모델](FIXED_READ_ACCEPTANCE_SPECIFICATION.md)의 가정과 한계를 유지하며, old-content 우연 일치 확률을 수용 결과의 신뢰도로 표시하지 않습니다. 현재 실제 비교 값·요청·주소 조합·frame·generator는 없습니다.

통과해도 보고할 것은 **저장 모드 후보0/1**입니다. 현재80/75임계값·실제80% 제한·충전기 적용을 입증하지 않습니다. `desiredMode`, 검증된 `actualMode`, Windows 잔량을 합치지 않고 실제 제어는 Unsupported로 남깁니다. 경로·사용자명·고유 ID·raw frame/nonce·예외 원문은 보고하지 않습니다.

## 승인 범위와 이후 검증

승인 대상으로 제시하는 것은 **위 고정 단발 조회용 코드 구현·빌드·오프라인 검증·시험 도구 제공**입니다. 실제 호출은 제공된 도구에서 사용자가 이 시험을 명시적으로 시작할 때만 최대1회입니다. 설정 변경·충전 제어 구현은 승인 범위에 포함하지 않습니다.

구현 후에는 독립 기대 byte/역할 대조, 모델/metadata 거부·영속1회 제한·입력 무결성·응답 거부·취소/Unknown 수명 회귀와 전체 빌드를 통과한 파일만 제공합니다. 삼성 원본 DLL·firmware·과거 실험 EXE는 포함하지 않습니다. 기존 TXT/DLL/EXE 재제출이나 현재 부팅 방식 재확인은 필요하지 않습니다.

프로젝트 [AGENTS.md](AGENTS.md)는 **“커널/펌웨어 제어 코드 추가 작업은 사용자에게 별도의 명시적 승인을 받은 뒤 안전성과 모델 적합성이 입증된 범위에서만 진행한다.”**고 요구합니다. 따라서 이번에는 SDK 취소 수명 결함 수정과 이 구체안까지 완료했고, 새 firmware 호출 구현은 별도 승인 전까지 보류합니다. 현재 데이터나 과거 소모된 실험 승인을 새 시험 승인으로 사용하지 않습니다.
