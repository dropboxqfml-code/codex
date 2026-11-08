# WMI 내부 취소 통지와 실제 종료를 구분 — 2026-11-08

**`CallCanceled`를 메서드 종료로 받아 자원을 일찍 정리할 수 있던 결함을 수정했습니다.** 공개 firmware 시험 entry는 계속 차단돼 있고, 이 결함을 실제 노트북에서 관측한 것은 아닙니다. 기존 부팅 방식 보고 프로그램의 교체나 추가 실행도 필요하지 않습니다.

## 발견 근거와 수정

현재 대상인 .NET Framework 4.8의 cached System.Management.xml은 `ManagementStatus.CallCanceled`에 대해 내부 또는 사용자 취소일 수 있고 **“the operation may not have been truly canceled”**라고 명시합니다. 해당 참조 DLL의 enum metadata도 코드로 실행하지 않고 읽어 같은 상수를 확인했습니다.

Windows callback adapter는 모든 `Completed.Status`를 Core의 적용 가능한 method terminal로 전달했습니다. 외부 `Cancel` 호출을 금지하는 계약만으로는 문서에 명시된 **내부 취소**를 배제할 수 없습니다. SDK 호출 stack이 돌아온 뒤 이 통지만 오면 Core의 terminal/capture barrier가 충족돼 입력·출력과 lease를 정리할 수 있었습니다.

수정은 Windows adapter의 해당 상태에 한정됩니다.

- `CallCanceled`는 실패를 기록하되 Core terminal로 전달하지 않습니다. capture를 미리 완료하거나 선택 출력을 Dispose하지 않습니다.
- 반복 취소·UI timeout·호출 반환만으로 입력·observer·lease를 해제하지 않습니다.
- 적용 가능한 실제 final이 나중에 오면 관련 정리를 진행하지만, 앞선 취소 실패를 성공으로 바꾸지 않습니다.
- 일반 `AccessDenied` 등 적용 가능한 오류 final의 기존 종료 규약은 유지합니다. 모든 오류를 무기한 대기로 바꾸지 않았습니다.

실제 sink에서 후속 final이 오지 않으면 관련 close는 계속 pending일 수 있습니다. 합성 완료·SDK Cancel·재시도·프로세스 강제 종료로 이를 복구했다고 취급하지 않습니다. 후속 final을 공급하는 테스트 코드는 대역 정리 수단이며 실제 SDK 중단 증거가 아닙니다.

수정 전에도 canceled status가 유효한 보호 값이나 충전 성공으로 표시됐다고 주장하지 않습니다. 재현한 것은 **응답 수신으로 분류돼 소유권이 조기 종료되는 문제**입니다.

## 현재 검증

새 회귀3개를 추가한 수정 전 대역 suite는 **647통과·2실패 / 649등록**이었습니다. 취소 후 UI deadline을 기다릴 사례가 `ReplyReceived`로 먼저 끝났고, 취소 뒤 후속 success final 사례도 실패했습니다. 일반 오류 final 사례는 수정 전부터 통과했습니다.

수정 후 root의 전체 재실행은 **649통과·0실패·0skip**, portable 및 전체 net48 참조 Release 빌드는 각각 경고·오류0입니다. 기존646개도 재실행했습니다. 실제 Windows/System.Management runtime·OEM/하드웨어 호출은 없습니다.

기존 부팅 방식 ZIP과 새 전체 빌드의 모든 byte가 같다고 주장하지 않습니다. 기존 ZIP은 `f474e6f` 배포물로 그대로 보존하며 이번에는 새 UI 배포 파일을 만들지 않았습니다. 수정 대상은 아직 실제 앱에 연결하지 않은 WmiInterop library와 대역 테스트이고, App/Core 및 과거 소모 예약·공개 entry source는 바꾸지 않았습니다.

[정제 검증 기록](reports/sdk-cancellation-readiness-validation.json)에 대상 API 문서·참조 metadata·source·수정 전후 로그의 pin을 보관합니다. [단발 조회 구현 제안](READ_TRIAL_A_IMPLEMENTATION_PROPOSAL.md)은 이 보강을 전제로 하지만, 실제 호출 구현은 별도 승인 전까지 추가하지 않습니다.
