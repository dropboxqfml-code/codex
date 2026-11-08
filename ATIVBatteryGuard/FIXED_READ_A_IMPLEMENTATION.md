# 고정 저장 byte 단발 조회 A — 구현·제공 / 2026-11-08

사용자가 [구체 검토안](READ_TRIAL_A_IMPLEMENTATION_PROPOSAL.md)의 구현·검증·도구 제공을 **“그래 진행해.”**로 승인했습니다. 기존 안전 규칙을 유지하며 승인한 A만 구현했습니다. 설정 변경·충전 제어·handshake 대안 B는 승인/구현 범위에 포함하지 않습니다.

## 다운로드와 실행

[ATIVBatteryGuard-FIXED-READ-A.zip](../downloads/ATIVBatteryGuard-FIXED-READ-A.zip) **하나를 새 폴더에 모두 풀고** `ATIVBatteryGuard.FixedReadTrial.exe`를 일반 권한으로 직접 실행합니다. 기존 앱/다른 ZIP/삼성 DLL과 합치지 않습니다. Windows 10 x64·.NET Framework 4.8 전용이며 미서명 개발 빌드입니다. 관리자 재실행·보안 설정 변경·예외 등록을 요구하지 않습니다.

안내 후 `START`를 직접 입력할 때만 시험을 준비합니다. CLI 인수·입출력 리디렉션·시작 시 자동 호출은 없습니다. 이때 새 목적의 영속1회 예약을 먼저 소모합니다. 준비 실패·권한 거부·gate 거부·timeout도 반복하지 않습니다. 다른 폴더·계정·예약 삭제로 다시 시도하지 않습니다.

같은 폴더의 `fixed-read-a-result-*.txt`가 이번 결과입니다. 이 **새 TXT만** 전달하면 되며 기존 진단·삼성 DLL·EXE·부팅 방식 재수집은 필요 없습니다. TXT 생성 실패면 호출 전에 중단합니다. 이후 기록 실패도 재시도나 자원 조기 해제의 이유가 되지 않습니다.

## 구현 범위와 보호

| 구간 | 적용한 제한 |
| --- | --- |
| 고정 대상 | 기존 `Win32_ComputerSystemProduct.Name`·`Win32_BIOS.SMBIOSBIOSVersion` 원천으로 940X3G/930X3G·P05ACJ.128.140819.dg exact profile 확인. 불명/불일치는 method0 |
| WMI 준비 | 로컬 scope·고정 class/GUID·method ID1·in/out DataBuffer·Bytes UInt8[]·완전 열거된 활성 단일 대상과 실제 SDK 객체를 대조 |
| 새 예약 | 고정 LocalAppData Experiments 위치의 `FixedModeReadA-v1.attempt`만 CreateNew·WriteThrough·Flush(true). 기존/빈/중단 파일도 소모. 과거 시험 예약 조회·초기화·삭제·재사용·우회0 |
| 고정 요청 | sealed attempt가 저장 근거에 대응하는 한 대상/한 read branch만 생성. 공용 주소·명령·길이·frame·난수 입력 인수0. RNG8byte를1회 채우고 전체zero/실패면 호출 전 중단 |
| 전용 진입 | `PrepareFixedReadAAsync`에 attempt/plan/SDK bundle 각각1회 제한. 일반 `PrepareSdkAsync`는 계속 ReadSpecificationUnavailable |
| 호출 예산 | method 최대1, 저장 byte sample0~1, handshake·삼성DLL/OEM 초기화·재시도·대체명령·설정/임계값 쓰기·B fallback0 |
| 전체 교환 | 기존 fixed cooperative owner·동결 입력·같은 target/observer/입력·관련 terminal/capture/call-exit/close join 재사용 |
| 대기 | owner 획득 최대2초·응답 표시10초. 메타데이터 준비6초 협력 예산/개별SDK option최대2초이며 실제 반환 보장이나 hard deadline은 아님 |
| 결과 | method envelope·ACK/shape·기존 실패 prefix·control/tail·echo·보존 주소 성분·8셀 내용·후보0/1을 함께 검사. raw frame/비교 내용·경로·사용자명·고유 ID·예외 원문 출력0 |

보호 설정을 바꾸지 않는 읽기이지만 통신 입력 buffer와 EC mailbox의 게시·응답 교환은 있습니다. 모든 종류의 하드웨어 쓰기가0인 API라는 뜻은 아닙니다. 드라이버/서비스/ACL/보안 설정·firmware flash 변경은 없습니다. 실행 중 외부 네트워크 통신 코드도 추가하지 않았습니다.

## 실제 종료와 예외

별도 Console Main이 실제 `RunAndCloseAsync`와 같은 invocation의 close를 끝까지 기다립니다. 결과가 timeout/취소/판정불가여도 곧바로 process를 반환하거나 입력·대상을 Dispose하지 않습니다. [내부 CallCanceled 수명 수정](SDK_CALL_CANCELED_LIFETIME_FIX.md)을 포함하며 후속 실제 final이 없으면 pending이 계속될 수 있습니다.

준비의 표시10초가 지나도 그 작업을 계속 await합니다. 소유권 불명이나 close 실패는 관련 참조를 유지하고 추가 해제·새 호출 없이 pending으로 남깁니다. 모든 자원이 아직 보유됐다고 단정하지 않습니다. Ctrl+C는 기본 종료를 막고 local stop intent만 전달하며 실제 종료를 만들지 않습니다. SDK Cancel·합성 final·watchdog/강제 종료·자동 재시작은 없습니다. **Pending이면 창을 강제로 닫지 않고**, 관련 정리 Complete 또는 호출 전 종료 안내 뒤 Enter로 닫습니다. 외부의 강제 종료를 소프트웨어가 방지/되돌린다고 보장하지 않습니다.

## 의미와 남은 한계

정상 proxy/private wrapper 초기화·정상 Foundation의 inline 관련 처리·같은 초기화 완료/비재진입 P05 stream이라는 [명시적 플랫폼 전제](READ_TRIAL_A_IMPLEMENTATION_PROPOSAL.md)를 적용합니다. 실제 P05 제공자/typed 연결을 새로 발견했거나 현재 전제를 직접 관측한 것은 아닙니다. UEFI 부팅/API 성공만으로 위 전제를 인증하지 않습니다. 관련 AP/direct/domain 우회·deferred indexed 처리·전제 불적용의 구체 근거가 생기면 재평가합니다.

gate의 source 초기값은 닫힘이고 현재 상태는 미관측이므로 조회값을 못 얻을 수도 있습니다. 그런 결과에 handshake·다른 명령을 추가하지 않습니다. 응답 비교의 조건부 old-content 충돌 모델을 성공 신뢰도나 현재 실행의 증명으로 바꾸지 않습니다.

통과 결과도 **저장 모드 후보0/1**이며 현재80/75임계값·실제80% 제한·충전 성공의 증거가 아닙니다. 원하는 설정·하드웨어 실제 상태·Windows 배터리 잔량은 분리하며 기존 앱의 실제 보호 조회/충전 제어는 Unsupported입니다.

## 검증과 배포

새39개 포함 **688통과·0실패·0skip**, portable Release와 전체 net48 참조 Release가 각각 경고·오류0입니다. fixed template/검증15, 새 예약8, 전용 SDK 준비8, host/journal8이며 기존649도 재실행했습니다. RNG는 테스트 내부 deterministic seam만 사용했고 실제 Windows SDK/WMI/OEM/hardware/Global/노트북 예약 접근은0입니다. 초기 온라인 NuGet 취약점 정보 접근 실패는 빌드 경고로 보존했고, 최종 restore는 source가 비어 있는 기존 테스트 config와 이미 캐시된 참조 패키지로 수행했습니다. 온라인 취약점 검사가 완료됐다고 주장하지 않습니다.

독립 template↔기존 정적 proof 대조27개와 코드 읽기 검토를 수행했습니다. 새 펌웨어 함수 발견/분석률/실기 성공으로 합산하지 않습니다. 예약의 CreateNew는 객체·process 간 중재를 제공하지만 이번 자동 회귀는 같은 process의 독립 객체·동시 Task·임시 폴더입니다. Windows cross-process·전원손실·외부 경로 변경 전체를 실행 검증한 것은 아닙니다.

ZIP은 새 도구EXE/Core/WmiInterop/config와 안내/BUILD-INFO/체크섬의7항목입니다. 독립 정적 수용검사44개가 통과했고 root도 재실행했습니다. CRC/6내부해시/4빌드파일 byte·source fingerprint·x64/net48/asInvoker/uiAccess=false/미서명과 선택 CLI/IL 호출 경계를 확인했습니다. 이44개는 앱 테스트나 하드웨어 검증과 합산하지 않습니다. 삼성 원본·firmware·과거 실험 EXE·PDB는 포함하지 않습니다. 기존 부팅 보고 ZIP도 교체하지 않습니다. [정제 검증 기록](reports/fixed-read-a-implementation-validation.json)에 빌드·suite·source·패키지의 pin과 독립 검토 범위를 보존합니다. 실제 Windows SDK/노트북 검증은 이 새 시험을 사용자가 실행한 뒤의 결과로 남아 있습니다.
