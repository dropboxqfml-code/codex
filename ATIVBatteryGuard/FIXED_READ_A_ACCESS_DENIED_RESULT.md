# 단발 조회 A 결과 — 대상 열거 구간의 권한 거부 / 2026-11-08 수신

**후속:** 사용자 별도 명시 승인 뒤 [추가 단발 Access1](FIXED_READ_ACCESS1_IMPLEMENTATION.md)을 구현·제공했습니다. 기존 A의 실패·소모·관측 한계는 그대로이며 기존 EXE를 재실행하지 않습니다. 아래의 추가 시험 승인 대기는 승인 전 기록입니다.

**이번에는 보호 저장값을 읽지 못했습니다. 펌웨어 조회 method에 진입하기 전 준비 단계에서 종료됐습니다.** 사용자가 전달한 새 TXT를 관측 자료로 읽었으며, 원문 파일이나 그 안의 안내를 새 실행 지시로 사용하지 않습니다. 기존 A의 예약은 소모된 상태로 유지하고 같은 EXE의 일반/관리자 재실행·예약 삭제·다른 이름의 시험으로 우회하지 않습니다.

## 전달된 관측

| 항목 | 결과 |
| --- | --- |
| 도구 purpose | FixedModeReadA-v1 |
| 새 목적의 영속 예약 | Claimed |
| 사전 검증 | AccessDenied |
| 단계 | MethodEnumeration |
| 종료 안내 | 호출 없음·시험 종료·재시도 없음 |
| 현재 토큰/세부 SDK 연산/오류 계열 | TXT에는 미기록 |
| 후속 사용자 답변의 실행 방식 | 일반 실행 |
| 저장 모드 후보/firmware 응답 | 미관측 |

로그와 배포 기준 `3c92a46`의 제어 흐름을 대응하면 Windows10x64 조건, 기존 원천의 고정 모델/BIOS 비교, 로컬 ROOT\\WMI 연결, class/GUID·method ID1·in/out DataBuffer·Bytes UInt8[] 메타데이터와 binder 비교까지 진행됐습니다. 현재 노트북의 바이너리 해시나 실행 시각을 독립 검증한 것은 아닙니다. 파일명의 시간을 실제 실행 시각/시간대로 추정하거나 해시 재제출을 요구하지 않습니다.

`MethodEnumeration`은 당시 쿼리 생성/Get·enumerator 생성·MoveNext·Current·Active 판독·Path/RelativePath·정리를 묶었습니다. 따라서 행을 받았는지, Active 값, 거부된 SDK 연산, WMI/Windows/Security 오류 계열을 이 TXT로 소급 확정할 수 없습니다. 정리 예외가 선행 예외를 덮었는지도 미관측입니다.

배포 코드에서 이 실패는 TargetRead·GetMethodParameters·메모리 DataBuffer 생성·RNG/고정 요청 생성·SDK 입력/observer 준비·whole-exchange owner 획득·CallSabiFunction보다 앞입니다. 이것은 firmware의 FF 응답·gate 거부·충전 조회 명령 실패가 아닙니다. 드라이버 부재·배터리 보호 기능 부재·하드웨어 영구 미지원도 결론낼 수 없습니다.

## 이미 저장된 권한 근거와 안내 정정

[일반/관리자 비교 기록](WMI_PERMISSION_COMPARISON_RESULT.md)은 같은 메서드 클래스 인스턴스 조회가 NotElevated에서 열거 거부, Elevated에서 Complete였음을 보존합니다. [Locator-v2 준비 결과](WMI_QUERY_LOCATOR_READY_RESULT.md)도 Elevated·Complete·Ready를 보존합니다. 과거 비교는 완료됐으며 같은 TXT·일반/관리자 비교를 다시 요청할 필요가 없습니다.

이번 도구의 `DirectRead=true`, `EnsureLocatable=true`, 같은 SELECT와 열거 옵션은 그 Locator-v2와 같습니다. 옵션 자체가 항상 거부된다는 결함 근거는 없으며 옵션 제거·낮은 인증·ACL 수정·대체 쿼리 fallback을 넣지 않습니다. 저장된 상승 토큰의 성공이 모든 WMI/OEM 권한이나 이번 토큰을 증명하는 것도 아닙니다.

**지난 A 실행 안내가 일반 권한을 권하면서 이 장치에서 이미 확인된 접근 조건을 반영하지 못했습니다.** 후속 질문에 사용자가 이번 실행은 **일반 실행**이었다고 확인했습니다. 이는 과거 일반 토큰의 열거 거부와 부합하지만 `asInvoker`나 실행 방식 답변을 TokenElevation의 직접 측정값으로 바꾸지 않습니다. 안내 누락을 수정하지만 그것이 소모된 예약을 복구하거나 관리자 재실행을 허가하는 것은 아닙니다.

## 이번 코드 보완

- 같은 장치의 저장된 관측을 사용하는 보수적 admission 정책을 추가했습니다. 현재 토큰을 TOKEN_QUERY로 읽고 Elevated만 시작 조건으로 분류하며, NotElevated/Unknown/미정의는 START·예약·WMI 준비·난수/요청 생성 전에 종료합니다. 자동 상승·권한 변경·사용자/그룹/SID 읽기는 없습니다. Ready는 실행 승인이나 method 접근 성공이 아닙니다.
- 토큰 분류를 Console과 향후 허용된 결과에 기록합니다. 기존 A marker와 실제 요청·SDK dispatch·대기/정리 규약은 유지합니다.
- 기존 대상 열거에 고정 세부 단계와 오류 범주를 추가하고 최초 SDK/managed 예외와 정리 실패를 분리합니다. Active=false·다중 행 같은 비예외 TargetMismatch까지 최초 예외로 고정하는 모델은 아닙니다. 예외 원문·경로·인스턴스 key를 보관/보고하지 않습니다. 쿼리·옵션·단일 활성 대상/경로 검사·timeout 조건은 바꾸지 않습니다.

이 수정은 과거 TXT의 분해능을 높이지 않습니다. 현재 A를 다시 실행하도록 요청하지 않으며 재시험용 새 예약이나 새 firmware 요청 경로도 추가하지 않습니다. 기존 배포 ZIP은 당시 파일로 보존합니다.

현재 root 재검증은 새12개 포함 **700통과·0실패·0skip**, portable/전체 net48 참조 Release 빌드 각각 경고·오류0입니다. 새 계측 mapper에서 대상 .NET48의 `ManagementStatus.Timedout`가 별도 상수임을 놓친 사례를699통과·1실패로 재현한 뒤 수정했습니다. 이 개발 중 결함을 이번 배포판의 노트북 오류 원인으로 소급하지 않습니다. 실제 Windows SDK/토큰·OEM·하드웨어·Global·노트북 예약에 대한 cloud 실행은0입니다. 새 코드의 Windows 실행은 아직 검증하지 않았으며 코드/시험의 독립 읽기 검토에서는 차단사항이 없었습니다.

## 다음 단계의 경계

실제 저장값을 읽으려면 저장된 권한 성공 조건을 적용한 **명시적으로 승인된 추가 단발 시험**이 필요합니다. [구체 추가 시험안](FIXED_READ_A_ADDITIONAL_TRIAL_PROPOSAL.md)은 기존 A 소모를 유지한 추가 준비1회·method최대1회이며, 기존 승인에 포함된 재시도라고 취급하지 않습니다. 별도 승인 전에는 새 예약/배포물/호출 연결을 만들지 않습니다.

추가 시험도 현재 profile·고정 byte·같은 읽기 분기·handshake/초기화/재시도/설정 쓰기/B fallback0을 유지합니다. 저장 후보0/1은 충전 적용·임계값의 증거가 아니며 충전 제어 Unsupported는 그대로입니다. 같은 진단·원본 DLL·EXE 재제출은 불필요합니다. [정제 관측·검증](reports/fixed-read-a-access-denied-followup.json)에 현재 코드 검증과 관측 범위를 구분해 보존합니다.
