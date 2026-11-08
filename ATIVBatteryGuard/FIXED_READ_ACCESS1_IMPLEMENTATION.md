# 승인된 추가 단발 조회 Access1 — 구현·제공 / 2026-11-08

**결과 수신·이 시험 종료:** [후보0·관련정리Complete](ACCESS1_STORED_ZERO_RESULT_AND_NEXT.md)를사용자가전달했습니다. Access1예산은소모됐고아래실행절차를다시수행하지않습니다. 기록은일반권한메인앱에서오프라인으로검토할수있습니다. 현재임계값/충전적용은미관측이며아래는배포당시이력입니다.


사용자가 [추가 시험안](FIXED_READ_A_ADDITIONAL_TRIAL_PROPOSAL.md)에 **“알겠어 진행해.”**로 명시 승인했습니다. 승인 범위인 **추가 준비1회·고정 WMI method최대1회·저장 byte sample0~1회**만 연결했습니다. 기존 A/Query65 소모분은 유지하며 복구하지 않습니다. 설정 변경·충전 제어·handshake·재시도·대체 명령·B는 범위 밖입니다.

## 실행 방법

1. [ATIVBatteryGuard-FIXED-READ-A-ACCESS1.zip](../downloads/ATIVBatteryGuard-FIXED-READ-A-ACCESS1.zip) **하나를 새 로컬 폴더에 모두 풉니다.** 기존 ZIP·프로그램·삼성 DLL과 합치지 않습니다.
2. 같은 Windows 계정에서 **새 폴더의 `ATIVBatteryGuard.FixedReadTrial.exe`만 오른쪽 클릭 → 관리자 권한으로 실행**합니다. 자동 UAC/runas는 없으며 manifest는 asInvoker입니다. 다른 계정의 암호가 필요하거나 보안 기능이 차단하면 중단하고 우회하지 않습니다.
3. 화면의 **Access1 / FixedModeReadA-Access1 / 현재 토큰 Elevated**를 확인하고 안내를 읽은 뒤 `START`를 직접 입력합니다. 실행만으로 WMI 준비나 firmware method가 시작되지는 않습니다. 현재 토큰이 NotElevated/Unknown이면 START·예약·WMI 전에 종료합니다.
4. 같은 폴더의 **`fixed-read-a-access1-result-*.txt`만** 전달합니다. 과거 TXT·삼성 DLL·EXE·같은 권한 비교 자료는 필요 없습니다.

**START 뒤에는 결과와 관계없이 재실행하지 않습니다.** 준비 실패·권한 거부·gate 거부·timeout도 추가1회를 소모합니다. 예약을 삭제하거나 다른 계정/폴더/버전으로 반복하지 않습니다. `Pending` 또는 관련 종료 대기 중이면 창/프로세스를 강제로 닫지 않고 기다립니다. `관련 정리: Complete` 또는 호출 전 종료 안내 뒤 Enter로 닫습니다.

대상은 Windows10x64·.NET Framework4.8·기존 940X3G/930X3G · P05ACJ.128.140819.dg profile입니다. 미서명 개발 빌드이며 보안 설정 변경·백신 예외·서명 우회·드라이버/서비스 설치는 요구하지 않습니다. 일반 앱을 상시 관리자 실행하도록 바꾼 것이 아닙니다.

## 구현한 연결과 유지한 제한

| 구간 | 적용 |
| --- | --- |
| 사전 조건 | 기존 TOKEN_QUERY 판독+Elevated-only admission을 START/예약/WMI보다 앞에 유지. 계정 이름·그룹·SID/토큰 권한 조정0 |
| 승인된 추가 예약 | 고정 LocalAppData Experiments 위치의 `FixedModeReadA-Access1.attempt`만 CreateNew·WriteThrough·Flush(true). 상대/UNC/reparse/불명 저장소는 거부. 기존/빈/중단 파일은 소모 |
| 실패 처리 | Claim 성공 뒤 TXT/metadata/RNG/SDK 준비가 실패해도 marker 복구·다른 marker 생성·반복0. 실행 폴더를 바꿔도 같은 사용자 내 고정 위치 사용 |
| 기존 예약 경계 | Program은 새 전용 클래스만 연결. 기존 A/Query65 존재 확인·읽기·초기화·삭제·재사용0. 공유 Core에 옛 클래스가 남아 있는 것과 실제 호출을 구분 |
| 고정 읽기 | 기존 요청·read branch·target profile·한번의8byte RNG/zero중단·exact metadata/활성단일대상·fixedSDK bundle·엄격 응답 거부를 변경하지 않음 |
| 호출·대기 | method최대1/sample0~1, owner획득최대2초/표시10초. 실제 call-exit·해당terminal·capture·입력/owner close는 별도join |
| 취소/불명 | CallCanceled를 실제종료로 취급하지 않음. Ctrl+C는localstop만 전달. SDKCancel·합성final·watchdog/강제종료·자동재시작0 |
| 결과 | Access1 purpose/TXT prefix로 옛 A와 구분. 토큰·고정substep/error·cleanupfailure·판정/후보0/1만 기록. rawframe/비교값·경로·개인식별자·예외원문0 |

이전 A는 [일반 실행의 MethodEnumeration/AccessDenied](FIXED_READ_A_ACCESS_DENIED_RESULT.md)로 firmware호출 전에 끝났습니다. 저장된 상승 토큰의 준비 성공 조건을 이번 별도 승인에 적용하지만 Elevated가 현재 WMI 권한·gate열림·reader실행·보호 상태를 보장하지는 않습니다. 같은 계정은 실행 안내상의 조건이며 이를 검증하려고 식별자를 수집하지 않습니다. per-user 예약을 machine-wide 보안 경계로 주장하지 않습니다.

## 결과 의미와 안전 한계

정상 proxy/private backend 초기화·inline 관련 처리·같은 초기화 완료/비재진입 P05 stream과 기존 조건부 모델/주소 대응 전제를 유지합니다. 현재 P05제공자/typed 연결이나 실행 상태를 새로 발견/관측한 것은 아닙니다. 통신 input buffer와 EC mailbox 게시·응답 교환은 있지만 보호 저장값·임계값을 쓰는 경로는 선택하지 않습니다.

gate가 닫혀 있으면 값을 얻지 못할 수 있습니다. FF·실패prefix·echo·보존 내용 불일치·귀속 불명·후보 범위 밖은 판정불가이며 추가 명령으로 이어가지 않습니다. 후보0/1이 나와도 현재80/75임계값·실제80%제한·충전 성공의 증거가 아닙니다. desiredMode·실제상태·Windows 잔량은 분리하며 충전 제어는 Unsupported입니다.

이전의 실제 수명/whole-exchange 보호를 그대로 재사용합니다. timeout은 firmware 강제 중단이 아니며 후속 실제final이 없거나 준비/정리 소유권이 불명이면 관련 대기가 계속될 수 있습니다. 소프트웨어가 외부 강제 종료를 방지/되돌린다고 보장하지 않습니다.

## 검증·배포 기록

새 예약9개 포함 **709통과·0실패·0skip**, portable/전체 net48 참조 Release 빌드 각각0경고·0오류입니다. 기존700개도 재실행했습니다. 현재 검증 결과와 source/build/ZIP pin은 [정제 검증 기록](reports/fixed-read-access1-validation.json)에 보존합니다. 추가 예약의 회귀는 임시 폴더·독립 객체·동시 Task·claim 뒤 합성 준비 예외의 storage 단위 검증이며 Windows실기/end-to-end·cross-process·전원손실 전체를 검증한 것은 아닙니다. 실제 Windows SDK/OEM·Global·노트북의 과거/새 예약에는 cloud에서 접근하지 않습니다.

독립 IL/source50관계와 ZIP48정적수용검산을 수행했고 root도 재실행했습니다. 전자는 Access1 constructor/claim 단일site·old예약call0·token→START→claim→기존SDK 순서 및 기존25source동일성, 후자는7항목/CRC/6내부SHA/4빌드byte/x64/net48/manifest/미서명/purpose·prefix·linkedprobe포함sourcefingerprint를 확인합니다. 서로겹치는정적관계이므로 앱회귀·새firmware발견·실기검증으로합산하지않습니다.

ZIP은 새도구EXE/Core/WmiInterop/config+안내/BUILD-INFO/체크섬의7항목입니다. 삼성원본DLL/firmware·옛실험EXE·PDB는 없습니다. 기존 A ZIP은 당시 byte로 보존합니다. 새패키저는 Access1 purpose/prefix와 linked token-probe를 포함한 source fingerprint를 검증하고, 역사 A 패키저는 Access1 bytes를 A-v1으로 오표기하는 것을 거부합니다. 실제 새도구의 Windows/노트북 실행은 사용자가 이 한 번을 실행한 뒤 확인할 항목입니다.
