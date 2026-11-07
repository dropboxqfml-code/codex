# 입력 객체 소유권과 실행·정리 수명 연결 — 2026-11-08 한국 시간

**공급된 입력 객체를 준비 단계에서 인계받고 기존 관련 종료 대기 뒤에 정리하는 경로를 구현했습니다.** [입력 준비](WINDOWS_WMI_INPUT_PREPARATION_REVIEW.md)의 후속입니다. SDK target 탐색·실제 메서드 호출·보호 조회 명령/template은 추가하지 않았습니다. 보호 설정 조회·충전 제어는 Unsupported입니다.

## 준비와 소유권 이전

새 `PrepareWithInputsAsync`는 기존 단발 plan·대상 binding·고정 요청에 이미 materialize된 parameters/buffer를 함께 받습니다. 기존 `PrepareAsync`와 같은 plan 예산을 공유합니다. 구조 인자 오류는 기존 예외로 거부하고, plan/target/request 거부나 준비 전 취소는 SDK 입력 접근·객체 인계 없이 끝냅니다. 준비 전 취소도 같은 plan을 재무장하지 않습니다.

입력 준비는 추적되는 worker에서 기존 Populator를 사용합니다. borrowed Populate와 owned 경로가 같은 원자적 pair claim을 공유하므로, 이미 사용한 객체의 상태값을 인계 허가로 재사용하지 않습니다. 두 managed wrapper를 함께 claim한 순간에만 이 경로가 소유권을 얻습니다. 준비 Task가 끝나기 전에는 caller가 두 객체를 쓰거나 Dispose하지 않아야 합니다.

| 준비 결과의 소유권 표기 | 의미 |
| --- | --- |
| InputOwnershipTransferred=false | 이 경로는 인계받지 않았습니다. 원래 소유자의 계약이 유지됩니다. 다른 시도가 보유한 객체를 이 factory가 해제하지 않습니다. |
| true + 준비 실패 | 입력 작업·필요한 등록 정리가 끝난 뒤 두 객체의 Dispose 시도까지 기다려 결과를 반환합니다. InputStatus와 InputCleanupStatus를 별도로 보존합니다. |
| true + Ready | 성공 handle이 두 객체를 보유합니다. 준비 결과의 InputCleanupStatus는 null인 시점 정보이며 최종 정리 결과는 RequestCloseAsync로 받습니다. |

null/같은 wrapper·기존 사용 객체의 거부는 인계하지 않습니다. claim 뒤 shape/getter/부분 setter 실패는 인계된 객체를 정리합니다. 한쪽이 이미 사용됐다면 새 다른 쪽은 불필요하게 소모하지 않습니다. 인계 후 준비 취소가 와도 실행 중인 getter/setter worker를 취소하거나 객체를 먼저 해제하지 않습니다. 입력 작업이 끝난 뒤 기존 준비 취소/실패 분류와 정리를 적용합니다.

## 실행 뒤 정리 순서

고정 handle의 Run은 여전히 publish callback/token만 받습니다. 먼저 기존 단발 Run을 소비하며 두 번째 Run의 동기 거부가 첫 Run을 닫지 않도록 유지했습니다. 기존 경로의 관련 종료 대기는 수정하지 않았습니다.

정리 순서는 **기존 RequestCloseAsync → 관련 source/capture·호출 스택·lease/등록 정리 대기 → parameters의 concrete Dispose → buffer의 concrete Dispose → 바깥 close 완료**입니다. 미사용 close도 등록 정리가 끝난 뒤 같은 입력 정리로 합류합니다. Run·외부 close·반복 close는 하나의 입력 정리 Task를 공유합니다.

UI timeout·caller 취소·보고 예외는 관련 종료 근거가 아닙니다. Unknown의 기존 close가 pending이면 입력 객체도 계속 보유하고 Run/바깥 close를 완료하지 않습니다. caller token이나 새 timeout으로 이 대기를 끊지 않습니다. 실제 terminal이 끝내 오지 않으면 이 보유가 계속될 수 있습니다. process 종료나 OS 자원 회수를 provider 종료 증거로 사용하지 않습니다.

입력 Dispose는 caller/상태 lock 밖의 worker에서 구체 메서드로 시도합니다. 첫 Dispose가 오류를 내도 두 번째를 시도하고 원문 예외 대신 Failed를 보존합니다. 각 managed wrapper의 시도는 한 번이며 자동 재시도·rollback은 없습니다. 성공 상태는 두 시도가 오류 없이 돌아왔다는 범위이지 native 참조 전체 소멸의 인증이 아닙니다. Dispose가 지연되면 Run/close도 함께 기다립니다.

## 입력이 출력으로 돌아온 경우

같은 입력 객체가 ObjectReady의 root로 오거나 다른 root의 outData 안에 들어오면, 출력 reader/정리가 입력을 먼저 Dispose할 수 있습니다. 새 owned 경로는 두 managed 입력 참조를 source·result wrapper·reader에 전달해 이를 차단합니다.

root alias는 입력의 Properties/Value를 읽거나 Dispose하지 않습니다. 실행 중이면 고정 capture 실패, 준비 중이면 기존 early-callback 실패로 처리하며, 게시 cutoff 뒤에는 다시 capture를 열지 않고 건너뜁니다. embedded alias도 Value로 얻은 참조를 확인한 뒤 추가 metadata/Dispose를 건너뛰고 실패로 남깁니다. provider terminal을 만들어내지는 않으며 입력 owner가 기존 종료 대기 뒤에만 정리합니다. 해제 후에도 약한 identity를 유지해 queued callback의 같은 managed 객체를 다시 Dispose하지 않습니다. 다른 COM wrapper/native alias 전체를 인증하는 경계는 아닙니다.

## 검증과 범위

새 준비 회귀 10개·수명 회귀 8개, **신규 18개 포함 전체 590개 통과·실패 0·skip 0**입니다. 사전 거부의 미인계, 기존 owner 보호, input 작업 중 취소, 부분 실패의 두 Dispose, 등록 실패/취소, 미사용 닫기, 조기 terminal/늦은 dispatch 반환, Unknown·lease·보고 예외, 막힌 Dispose와 root/embedded/late alias를 검증했습니다. 모든 가짜 gate와 관련 Task는 finally에서 합류합니다.

Windows 연결 계층의 production 소스 7개를 portable 시험에 링크해 SDK stand-in과 실행했습니다. 기존 synthetic frame만 사용했으며 실제 System.Management runtime/provider·삼성 원본·노트북 호출은 실행하지 않았습니다. 이전 private 검산을 회귀 수에 합산하지 않았습니다. 전체 솔루션은 실제 net48 참조 Release 빌드 **경고 0·오류 0**입니다.

[정제 기록](reports/windows-wmi-owned-input-lifetime-audit.json)에 검증한 소스 해시와 범위를 보관합니다. 독립 읽기 검토는 테스트 재실행이나 실제 SDK 관측과 구분합니다.

소유권 이전은 supplied materialized 객체와 dedicated observer/dispatch 계약에 한정됩니다. 외부 mutation·임의 delegate 내부 행동·실제 SDK target/메서드 수·입력의 method 출처·native embedding copy·고정 요청의 읽기 의미를 인증하지 않습니다. SDK property 접근의 lazy 초기화·COM 가능성은 [이전 검토](WINDOWS_WMI_INPUT_PREPARATION_REVIEW.md)대로입니다. lower generic API와 borrowed Populate는 유지하며 시스템 전체 권한 경계로 표시하지 않습니다.

Core/앱 UI·default backend·기존 실험 backend/Program·encoder·소모 예약·배포 ZIP은 변경하지 않았습니다. 실제 WMI/OEM·하드웨어/Global 객체·삼성 원본·드라이버/서비스/보안/펌웨어·클라우드 환경에는 접근하거나 변경하지 않았습니다. 새 실행 파일·노트북 재시험·동일 자료 제출은 필요하지 않습니다.

다음은 인계된 입력과 구체 target/observer를 같은 시도에 묶는 SDK dispatch 경계를 저장 계약과 대조하는 작업입니다. 실제 요청의 의미·gate 유용성·관련 참여/완료·결과 귀속·실기 승인은 별도로 유지합니다. A/B 호출 수·B의 gate 상태 영향이나 사용 완료된 옛 단발 정책은 변경하지 않습니다.
