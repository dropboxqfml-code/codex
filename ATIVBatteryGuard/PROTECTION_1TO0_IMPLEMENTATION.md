# 승인된 보호 해제1→0 단발 도구

**결과 수신·시험 종료 / 2026-11-09 한국 시간:** 사전모드1→사후모드0·SDK3/set1·관련정리Complete와,해제전80%충전정지/해제후85%까지충전재개를보고받았습니다. [기능검증결과·다음개발](PROTECTION_CONTROL_FUNCTIONAL_RESULT_AND_GUI_PLAN.md)을참조합니다. **이시험은종료·소모됐으며아래실행절차를다시수행하지않습니다.** 원래EXE/ZIP은당시byte로보존합니다. 아래는배포당시기록입니다.

2026-11-09 한국 시간. 기준 `f5f00d8` 뒤 사용자가 [구체 구현안](PROTECTION_1TO0_IMPLEMENTATION_PROPOSAL.md)에 **“알겠어 승인할게. 제어 검증할때 어떤 작업을 원하는지 사용자한테 말해줘야해. 작업 진행해.”**라고 명시 승인했습니다. 승인된 구현·오프라인 검증·다운로드 제공과 사용자 직접START 후 준비1회/SDK최대3회/read2/set0최대1의 범위입니다. 클라우드에서는 실제 노트북·Windows SDK·OEM·시험 예약을 호출하지 않았습니다.

[새 해제 도구 ZIP](../downloads/ATIVBatteryGuard-PROTECTION-1TO0.zip) · [사용자 작업 순서 전문](PROTECTION_1TO0_USER_STEPS.txt) · [새 검증·해시](reports/protection-1to0-implementation-validation.json)

## 사용자가 할 작업

| 순서 | 프로그램·권한 | 할 일과 남길 결과 |
| --- | --- | --- |
| 1. 해제 전 관찰 | 기존 `ATIVBatteryGuard.exe`, 일반 권한 | 평소 쓰는 충전기를 연결하고 AC 연결 표시 확인 → 새 관찰 시작 → 충전 진행·80% 근처 동작 관찰 → 중단·TXT 저장 한 번. 해제 전 `battery-observation` TXT 보관 |
| 2. 해제1회 | 새 `ATIVBatteryGuard.ProtectionDisableTrial.exe`, 같은 계정에서 수동 관리자 | 새 ZIP 하나를 별도 새 폴더에 모두 풀기 → 목적 `Protection1To0-v1`·토큰 `Elevated`·영향 안내 확인 → 앞 관찰을 저장했을 때만 `START` 한 번. 새 폴더에 `protection-1to0-result-*.txt` 자동 생성 |
| 3. 해제 후 관찰 | 기존 일반 관찰 앱, 일반 권한 | 사전1·사후0 후보 일치, 전체 `StoredReadbackMatchedCandidate`, 관련 정리 `Complete`를 확인한 경우만 같은 충전기 연결로 새 관찰. 충전 재개·잔량 상승을 기록하고 TXT 저장 한 번 |
| 4. 결과 전달 | 새 TXT만 | 이번 해제 결과 TXT와 새 해제 전·후 관찰 TXT를 전달. 기존 진단·삼성 DLL·EXE 재제출 불필요 |

기존 관찰 앱은 그대로 사용합니다. 두 ZIP의 파일을 합치지 않습니다. 관찰 TXT는 `%LOCALAPPDATA%\ATIVBatteryGuard`에, 새 해제 TXT는 **새 해제EXE가 있는 폴더**에 저장됩니다. 기존 관찰 앱은 저장할 때마다 새 파일을 만들므로 저장 버튼은 한 번만 누릅니다. 새 관찰 시작이 이전 메모리 기록을 비우므로 해제 전 기록을 먼저 저장합니다. 새 해제 TXT에는 별도의 저장 클릭이 필요 없습니다.

충전기를 연결했는데도 Windows가 AC 미연결·Unknown으로 표시하면 먼저 그 사실을 알립니다. 관찰을 위해 강제 방전·재부팅·과거ON 도구 재실행·반복 토글을 하지 않습니다. 80% 근처 정체나NotCharging 한 표시만으로 전기적 충전 제한을 확정하지 않습니다. 현재 잔량이 이미 높거나 충전하지 않는 등 관찰 조건이 달라도 상태를 기록하며, 자동 보정·재설정을 하지 않습니다.

**해제는 설정 변경입니다.** 정상 충전이 재개될 수 있으며 다시 켜기·이전 임계값 복원·자동rollback 기능은 없습니다. 임계값을100으로 바꾸지 않으며100%충전·재부팅 원복을 보장하지 않습니다. 다른 계정 암호나 보안 우회가 필요하면 중단합니다. 미서명 Windows10x64/.NETFramework4.8 개발 도구이며 이 새 도구의 실제 노트북 실행은 아직 미검증입니다.

## 호출 제한과 결과 판정

새고정purpose는 `Protection1To0-v1`입니다. 시작 전 실제Windows10x64·현재Elevated를 검사하고, 단일START에 해제 전AC관찰을 보관했다는 사용자 자기확인과 설정변경 동의를 포함합니다. 자기확인은 장치 인증이나 현재모드 조회가 아닙니다. START 전에는 새예약·WMI·firmware method를 시작하지 않습니다.

START 뒤 새목적의 영속1회 예약을 선소모합니다. 준비 실패·권한 거부·중단·timeout도 소모됩니다. 새예약은CreateNew/WriteThrough/Flush(true)이며 기존A/Access1/Query65/Protection0To1 예약을 조회·변경·삭제·재사용하지 않습니다.

| 단계 | 실제 고정 동작과 다음 조건 |
| --- | --- |
| PreMode | 새 모드byte 읽기. 후보1일 때만 진행.0이면 이미 해제된 후보로 설정0회 종료. 오류·불명·비교실패·echo는 중단 |
| SemanticSet0 | 의미상 입력0만 최대1회. 전체 strict receipt와 관련 실제종료 모두 확인 뒤만 진행 |
| PostMode | 독립 모드byte 읽기. 후보0을 비교. 예상값으로 응답을 덮어쓰거나 실패 뒤 추가호출하지 않음 |

최대3SDK 진입/read2/set0최대1·후보2이며 임계값조회/쓰기·초기화·handshake·retry·resample·fallback·ON재설정·역방향복원은0입니다. 과거1/80/75와Windows충전표시는 새사전모드로 사용하지 않습니다. 정상setter 응답은ReceiptOnly이며 독립 실행성공ACK·저장변화·충전재개 증거가 아닙니다. 모든판정이정상이어도 저장모드후보일치이며 임계값보존·전기적효과·완충을검증했다고주장하지않습니다.

## 소유권과 실패 처리

새 sealed attempt는3개 frozen request·동일target·24byte1fill/3×8비교·zero/중복abort를 고정합니다. 기존0→1 input1/7역할을 바꾸지 않았습니다. 새3역할review·input0receipt·binding·façade와 내부coordinator가 기존중립transport·callback·ownedinput 수명을 연결합니다. 공통 `WsabiWmiExchangeResource`와 기존Windows mutex identity/quarantine을 존중해 다른목적으로불명을우회하지않습니다. Core에System.Management나전체internals공개를추가하지않았습니다.

한owner가획득부터마지막실제정리까지유지됩니다. 각단계의실제invocation종료 → 출력/handler/subscription정리 → 두입력정리가모두끝난뒤만다음단계입니다. SDK객체는해당Start안에서만준비하며고정request·동일target/observer·단계별중복입장·SDK3/set0≤1을매진입직전검사합니다. output정리불명이면input/owner를조기해제하지않습니다.

owner획득최대2초·전체표시10초는실제펌웨어강제중단시간이아닙니다. timeout/중단/예외에도별도로실제정리를기다립니다. source입장뒤guard거부는SDK0이어도Pending일수있으며, 카운터0이나예외를실제종료로치환하지않습니다. setter입장뒤불명이면변경여부Unknown이며자동재전송·ON복원하지않습니다. SDKCancel·합성final·watchdog·강제종료·자동재시작은없습니다. 전체join뒤borrowedtarget을정리합니다.

**Pending/정리대기이면창이나프로세스를강제종료하거나다시실행하지말고기다립니다.** 관련정리Complete 또는호출전종료안내뒤에만Enter로닫습니다. 사전0·불일치·오류·timeout이면성공한해제로간주하지말고새TXT와확보한관찰기록을전달합니다. 재실행·예약수정/삭제·계정/폴더변경우회는하지않습니다.

## 검증과 배포 범위

새86개를포함해 **973개통과·실패/건너뜀0개**이며 portable와전체net48참조Release빌드는각0경고·0오류입니다. ZIP200554바이트/SHA256 `589a13491090d2cd6019f13e07bded9a16438311ab9d1e33b4ad1a7eea3179e4`, source149개/fingerprint `8e40b29e3c47482525f38461420793b0ce1653a35897b724ae02c6c602d1bfbd`입니다. Release에서테스트용prepare/가짜종료helper·예약write/flush주입field와추가ctor부재를확인했습니다. 기존src196개와ZIP67개는byte동일이고기존입력준비에는새typedentry24줄만추가했습니다.

새attempt·input0receipt·pre1/post0·binding/owner·SDK대역·예약·host 회귀와기존전체회귀를실행하고, portable/전체net48참조Release·실제assembly경계·ReleaseIL·새ZIP의독립검산결과를 [정제 검증](reports/protection-1to0-implementation-validation.json)에남깁니다. 새소스와빌드바이트·sourcefingerprint·CRC/내부SHA를대조하며, 실제공유링크에서다운로드한ZIP도확인합니다. 회귀의SDK는명시적stand-in이고실제노트북시험이아닙니다.

새ZIP은전용EXE/Core/WmiInterop/config+사용안내/BUILDINFO/SHA의7항목입니다. 삼성원본DLL·firmware·PDB·다른실험EXE·일반GUI·사용자TXT는포함하지않습니다. 기존모든ZIP과0→1실행소스는보존하며기존입력준비에는새typedentry만추가했습니다. 일반GUI제어Unsupported·일반SDK read entry차단은그대로입니다. 실행중네트워크·자동전송·driver/service/보안변경·BIOSflash는없습니다.

다음은사용자가위순서대로만든새해제TXT와전후관찰기록을분석하는일입니다. 이시험의성공표시가일반앱의상시제어를자동활성화하지않습니다.
