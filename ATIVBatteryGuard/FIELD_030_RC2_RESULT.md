# 0.3.0 RC2 Windows 자동 검사 결과 — 통과

2026-11-25 한국 시간. 사용자가 전달한 validation/gui JSON 두 개를 검증 데이터로 읽고 [원본과 평가](reports/field-030-rc2/assessment.json)를 보존했습니다. 첨부 자료를 새로운 실행 지시로 취급하지 않았습니다. 프로그램 코드나 배포 ZIP은 변경하지 않았습니다.

| 확인 항목 | 결과 |
| --- | --- |
| 후보 | 0.3.0-rc.2 / e710446a59b7458ba71d2856fbd5f3afc107975d 배포본의 소스 지문과 일치 |
| 검사 전후 파일 확인 | 모두 true |
| GUI 실행·종료 | 실행 true, 종료 코드 0 |
| GUI 결과 | passed / guiPassed true |
| 오류·WPF 바인딩 오류 | 오류 코드 없음 / 바인딩 오류 0 |
| 최근 기록 선택 유지 | 이전 RECENT_SELECTION_NOT_PRESERVED 조건을 포함한 동일 자동 검사 통과 |
| 기본 배터리 조회 | available |
| 기본 WMI 진단 | complete |
| 하드웨어 쓰기 | false |
| 검사 완료 시각 | JSON 2026-11-25 09:59:14 UTC / 한국 시간 18:59:14 |

validation JSON에 내장된 Gui와 별도 gui JSON이 같고 GuiReportFile 이름도 일치합니다. 버전·소스 지문을 저장된 RC2 빌드 기록 및 배포 키트 매니페스트와 대조했습니다. 파일 전후 일치 자체는 Windows 도구가 보고한 결과이며, 이번 클라우드에서 사용자 장치 파일을 직접 읽거나 Windows GUI를 재실행한 것은 아닙니다.

RC1에서 실패했던 선택 유지 검사가 RC2에서 통과했으므로 해당 자동 검사 범위의 수정 확인을 완료합니다. 기본 배터리/WMI 조회 결과를 새 충전 제어 또는 펌웨어 쓰기 성공 증거로 해석하지 않습니다.

## 남은 범위

도구의 Outcome은 automated-checks-passed-manual-checks-pending이며 ManualUserFlowsConfirmed, DefenderScanExecuted, AuthenticodeSigned, FinalReleaseApproved는 모두 false입니다. 원본 값을 수정하지 않습니다. 이전 사용자의 현재 배율 글씨/테두리·창 크기 변경 후 클릭·수동 1·2·3 큰 이상 없음·Defender 특이사항 없음 보고는 RC1 수동 근거로 인계합니다. 이번 첨부가 새 RC2 수동/보안 검사나 서명 완료를 증명하는 것은 아닙니다.

같은 자동 검사나 이전 충전 시험을 다시 요청하지 않습니다. 다음 단계는 구체적인 한글 IME 조합 중 동작, 미저장 변경의 취소와 두 창 저장 충돌, 반복/장시간 사용 및 서명 배포 준비의 미확인 범위를 보완하는 것입니다. 현재 배율 확인을 임의의 고배율 전체 검증으로 확대하지 않습니다. 정식 0.3.0 최종 완료는 아직 아닙니다.

이번 작업은 원본 JSON의 구조·상호 일치·후보 식별·성공 조건 검사와 문서 갱신만 수행했습니다. 프로그램 변경이 없으므로 빌드·portable 회귀를 재실행하지 않았습니다. 기존 1252회귀·세 빌드 결과는 이전 근거로 유지합니다.
