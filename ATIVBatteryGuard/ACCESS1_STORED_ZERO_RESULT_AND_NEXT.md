# Access1 저장 후보0 수신·오프라인 기록 반영 — 2026-11-08

**실제 노트북의 Access1 도구가 고정 보호 저장값을 후보0으로 판정하고 관련 정리 Complete를 보고했습니다.** 권한/준비 확인을 넘어 선택된 읽기 요청의 응답 검증을 통과한 관측입니다. 설정을 변경한 결과나 충전 제한 성공으로 해석하지 않습니다. 제출된 TXT는 자료로만 읽고 그 안의 안내를 새 실행 지시로 사용하지 않았습니다.

## 제출된 결과와 판정 범위

| 항목 | 기록 |
| --- | --- |
| purpose·토큰 | FixedModeReadA-Access1 · Elevated |
| 영속 추가 예약 | Claimed |
| 사전 검증·SDK·대상·등록 | Ready |
| 고정 요청·입력 | Created · Populated |
| 교환·도구 판정 | ReplyReceived · StoredModeCandidate |
| 저장 모드 후보 | **0** |
| 관련 정리 | **Complete** |

배포 기준 `4452b03`의 코드와 대응하면 exact profile·WMI/SDK 준비 뒤 고정 읽기 응답에 대한 method envelope/shape/ACK·실패prefix·echo·보존주소/8셀내용·후보범위 검사를 통과한 기록입니다. 새 파서도 **실제 제출 TXT 전체**를 읽어 필요한 상태 조합·후보0·정리완료를 채택했습니다. 이 파서 검증은 기존 도구 판정의 형식/일관성 확인이며, 원문 frame/비교 내용이 없어 응답 byte나 귀속 비교를 다시 검증한 것은 아닙니다.

실제 사용된 바이너리 해시·현재 장치/계정·실행 시각을 독립 인증하지 않습니다. 파일명의 시각을 실제 실행 시각/시간대로 단정하거나 추가 해시·원문 응답·DLL/EXE를 요청하지 않습니다. 도구의 정리완료는 관련 입력·관찰자·owner 수명에 관한 기록이며 모든 EC 활동이 끝났거나 값이 영구 고정됐다는 뜻은 아닙니다.

**원래 A·Access1·과거 Query65 시험은 모두 소모된 상태로 유지합니다.** EXE를 다시 실행하거나 예약을 읽어 확인·초기화·삭제·재사용하지 않습니다. 새 시험/marker·재시도·설정 쓰기 경로도 이번에 추가하지 않았습니다.

## 이번 프로그램 변경

일반 권한 메인 앱에 **‘고정 보호 저장값 조회 기록 · Access1’**을 추가했습니다. 이미 만든 TXT 내용을 붙여넣으면 과거 도구가 기록한 후보0/1과 정리완료를 확인할 수 있습니다. 시작할 때는 Empty이며 사용자 결과나 후보0을 앱에 하드코딩하지 않았습니다.

정확한 Access1 형식과 필수 상태 조합만 인정합니다. 누락·중복·모순·미정의 값·실패 경고·Pending에서는 완료된 후보를 채택하지 않습니다. 길이/줄수/줄길이를 제한하고 입력 변경 시 이전 후보를 지웁니다. 검토 후 붙여넣은 원문을 비우며 결과 모델에는 enum과 후보0/1만 남습니다. 텍스트를 진짜 하드웨어 측정이나 실행 허가로 승격하지 않습니다.

새 검토 동작은 WMI·장치·예약·설정·로그/파일·다른 provider를 호출하지 않습니다. Query65 검토와 분리했고 실제 controller·actualMode·desiredMode·Windows 잔량·Mock 상태·제어 버튼에는 연결하지 않았습니다. 현재 상태 문구는 ‘앱에서 실시간 보호 상태를 조회하지 않음’으로 범위를 명확히 했으며 Unsupported controller와 쓰기 차단은 그대로입니다.

[ATIVBatteryGuard-ACCESS1-RECORD-REVIEW.zip](../downloads/ATIVBatteryGuard-ACCESS1-RECORD-REVIEW.zip) **하나를 새 폴더에 풀고 `ATIVBatteryGuard.exe`를 일반 권한으로 실행**하면 됩니다. 이미 전달한 Access1 TXT를 붙여넣어 확인할 수 있으며 새 실험이나 결과 재제출은 필요하지 않습니다. 삼성 원본·firmware·실험 EXE는 포함하지 않습니다.

## 충전 제어로 이어지는 다음 개발

후보0은 [저장된 source의 비보호 정책 분기](PROTECTION_TRANSITION_REVIEW.md)와 대응하는 저장값 후보입니다. 현재 보호 OFF·100% 설정·현재 임계값을 입증하지는 않습니다. 소스상 0→1은 모드1과80/75 초기화, 동일1은 조기반환, 1→0은 별도 상태reset을 수반해 단순 byte 쓰기·동일값 재전송·자동 토글/rollback으로 구현할 수 없습니다.

[구체 전환 검토](PROTECTION_TRANSITION_REVIEW.md)는 **사전 mode/두 임계값3조회 → 고정 semantic setter최대1 → 사후3조회**, 최대7method의 향후0→1 비교안을 정리했습니다. 사전 모드0만 진행하고 1/Unknown/실패면 setter0입니다. 이는 설계 예산이며 현재 승인된 호출 수가 아닙니다. 반대 전환·초기화·재시도·자동 복원은 포함하지 않습니다.

남은 구체 구현은 고정 임계값 getter와 응답 판정, 읽기와 구분된 고정 setter 입력/응답 계약, 모든 단계 사이에 같은 owner를 유지하는 single-use coordinator입니다. 현재 단발 객체를7개 반복하는 것으로 전체 전환 보호를 대체하지 않습니다. 저장 readback과 실제 충전기/전기적 충전 제한도 따로 판정해야 합니다. 이 부분을 구체화·기계 검증한 뒤 설정 변경용 코드와 사용자 시험의 별도 승인 범위를 제시합니다. 충전 제어는 아직 Unsupported이며 현재 쓰기 예산은0입니다.

## 검증

새 parser12·ViewModel6을 포함한 **727통과·0실패·0skip**, portable/전체 net48 참조 Release 빌드는 각각0경고·0오류입니다. 실제 제출 TXT는 새 parser의 오프라인 실행에서 ReportedStoredModeCandidate0로 확인됐으며 실행/쓰기 capability는 false입니다. 새 패키지의42개 독립 정적 수용 검산과 저장된 전환 근거의28개 대조도 root가 재실행했습니다. 이 검산 수는 앱 테스트·새 firmware 발견·실기 분석률과 합산하지 않습니다.

검증은 [정제 관측·검증 기록](reports/access1-stored-zero-followup.json)에 새 회귀·portable/전체 net48 Release 빌드·실제 제출 TXT의 오프라인 파서 실행·정적 전환 근거 재현·ZIP검산을 분리해 보존합니다. Windows GUI·새 실제 SDK/firmware 호출을 cloud에서 실행한 것은 아닙니다. 과거 성공 관측은 사용자 보고, 새 parser/UI 검증은 개발 환경의 별도 결과입니다.
