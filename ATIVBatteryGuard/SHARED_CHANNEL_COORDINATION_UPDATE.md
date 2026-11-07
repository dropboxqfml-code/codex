# 공유 채널 재진입 방지 보강 — 2026-11-07 한국 시간

후속 [협력 교환 소유권 구현](COOPERATIVE_EXCHANGE_OWNERSHIP_UPDATE.md)에서 opt-in gate/owner, stop CAS와 불명확 소유권 격리를 추가하고 [고정 조회 시험은 보류](FIXED_MODE_READ_DECISION.md)로 판정했습니다. 아래는 당시441개 검사·수정 기록입니다.

**같은 채널을 새 교환 객체로 감싸 진행 중인 작업을 우회하던 소프트웨어 결함을 수정했습니다.** 같은 snapshot transport를 사용하는 별도 BoundFrameChannel 래퍼도 진행 상태를 공유합니다. 오프라인 C# 테스트441개 통과, 전체 솔루션 빌드 경고·오류0입니다. 실제 보호 모드 조회·충전 제어는 아직 미구현·Unsupported입니다.

[이전 입력·정리 분석](EC_QUERY_INPUT_AND_CLEANUP_REVIEW.md)의 후속입니다. 이번에는 준비용 전송 조정 코드와 회귀 테스트를 수정하고, 관련 EC 작업의 입력 소비 시점도 저장 원본으로 한 단계 더 연결했습니다. 새 하드웨어 요청·배터리 명령·실제 backend는 추가하지 않았습니다.

## 수정한 소프트웨어 동작

기존 `WsabiWmiFrameExchange`의 active 상태는 교환 인스턴스마다 따로 있었습니다. timeout이나 취소 뒤 원래 객체는 실제 작업이 끝날 때까지 Busy를 유지해도, **같은 channel을 전달한 새 교환 객체**는 그 상태를 모르고 다시 진입할 수 있었습니다. 같은 transport를 새 BoundFrameChannel로 감싸는 경우도 같았습니다.

이제 `ConditionalWeakTable`에 resource reference별 slot을 공유합니다. 일반 채널은 자신의 객체 reference, sealed BoundFrameChannel은 내부 readonly transport reference를 사용합니다. binder의 metadata나 요청 내용이 같다는 이유로 서로 다른 transport를 묶지는 않습니다. weak key를 사용해 끝난 자원을 static 목록에 영구 보관하지 않습니다.

진입은 공유 slot의 원자적 확인으로 결정하며, 기존 작업과 그 취소 callback이 **모두 끝난 뒤** slot을 해제합니다. UI에 timeout/cancelled를 반환한 것만으로 다른 교환 객체의 재진입을 허용하지 않습니다. 마지막 channel fault의 관측·token 정리·독립 자원의 동시 진행은 기존 의미를 유지합니다. 공급된 channel task가 실제 작업 종료를 정확히 나타낸다는 기존 계약이 전제이며, native provider의 강제 종료를 증명하는 기능은 아닙니다.

보호 범위는 **FrameExchange를 거치는 동일 resource reference의 프로세스 내부 요청**입니다. 직접 channel 호출, 별도 reference 뒤에 숨은 같은 물리 endpoint, 다른 프로세스·OEM·ACPI·펌웨어 호출자까지 보호하지 않습니다. 외부 Global mutex나 native API를 추가한 것도 아닙니다. 앱에 이 준비용 전송 경로를 새로 등록하지 않았고, 기존 OneShot backend·Program·예약·승인 gate·요청 encoder도 변경하지 않았습니다. 사용 완료된 단발 시험의 재실행은 필요하지 않습니다.

## 입력을 계속 소비하는 EC 작업의 범위

이전에는 선택 buffered 작업의 시작·완료 버퍼가 query mailbox와 다름을 확인했습니다. 이번에는 그 사이의 **실제 입력 소비 시점**을 연결했습니다. 선택 worker는 원본 buffer에서 local staging으로 복사하고 byte/bit 계산을 동기 실행한 다음, 마지막 요청 함수가 반환합니다. 확인한 원본·local 입력 범위는 조회 upload 영역과 분리되며, 고정 reader의 결과 쓰기도 이 worker 입력 영역을 건드리지 않습니다.

따라서 이 식별된 software 경로가 반환 후에도 query mailbox에서 원본 입력을 계속 읽는다는 우려는 좁힐 수 있습니다. 반환 이후 확인된 경로는 기존 readiness-gated polling 후처리이며 새 IRQ callback을 발견한 것은 아닙니다. helper가 바꾼 pointer를 반영하면 status 생산자로 볼 수 없던 후보도 분리했습니다.

실제 IRQ 진입·외부 status 생산, hardware continuation·계산된 별칭·공유 임시 영역의 수명은 닫지 못했습니다. 선택 경로의 입력 분리를 전체 작업의 무조건 비훼손으로 승격하지 않습니다. [조회 검토안](FIXED_MODE_READ_PROPOSAL.md)은 기존 정상 작업 비훼손·조회의 안전한 실패·사전 대상 무결성·응답 귀속을 계속 구분합니다.

## 검증과 빌드

회귀 테스트4개를 추가했습니다.

- 같은 채널의 새 교환 객체가 timeout 뒤 미완료 작업을 우회하지 못함.
- 원래 channel이 끝나도 취소 callback이 진행 중이면 peer도 Busy를 유지함.
- 같은 snapshot transport의 별도 BoundFrameChannel 래퍼도 Busy를 공유함.
- 같은 metadata를 쓰는 다른 transport는 독립적으로 진행함.

수정 전에는 새 검사 중3개가 실패했고, 수정 후 **441개 모두 통과**했습니다. 기존 취소 검사2개도 off-thread 취소가 실제 관측될 때까지 기다리도록 정밀화했습니다. UI timeout 반환과 취소 callback 실행 사이의 비동기 순서를 혼동한 검사 가정을 바로잡았으며, 제품의 취소 처리를 동기화하지 않았습니다. fake channel·snapshot만 사용했고 실제 OEM 호출·기존 실기 예약은 접근하지 않았습니다. [테스트 결과](reports/shared-channel-coordination-tests.json)를 보존했습니다.

현재 환경의 SDK8.0.427과 보존된 .NET Framework4.8 참조로 **전체 솔루션 Release 빌드 경고0·오류0**을 확인했습니다. 첫 시도는 WindowsDesktop markup task의 이미지 형식 오류로 실패했고, 개발 도구에 `DOTNET_ReadyToRun=0`·`COMPlus_ReadyToRun=0`을 적용해 일반 IL 경로로 빌드했습니다. 쓰기 가능한 `DOTNET_CLI_HOME`을 사용했으며 새 패키지 설치·SDK 파일 패치·XAML 단계 생략은 하지 않았습니다. Windows에서 새 EXE를 실행한 검증은 아닙니다.

EC 선택 입력 lifecycle 검산14개와 기존 문맥8개, pointer 불변식1개를 지지하는 검사2개와 기존 문맥15개도 독립 재검산·검토를 통과했습니다. source 수치를 앱 테스트나 전체 분석률에 합산하지 않습니다. Python 개발 도구는 변경하지 않았고 Python88개는 이전 `e7b067a`의 검증 기록입니다. [정제 검사 기록](reports/shared-channel-coordination-audit.json)은 실제 실행한 검사와 과거 문맥을 구분합니다.

## 남은 작업과 제공 범위

프로세스 내부의 알려진 같은 자원에 대한 중복 진입은 보강했습니다. 전체 WMI 교환에서 다른 참여자를 포함하는 보호, 표준 통신의 미연결 실행 영역, 관련 hardware/IRQ 입력 수명·응답 귀속 조건은 여전히 남습니다. 이 수정만으로 실제 보호 조회나 쓰기를 활성화하지 않습니다.

다음 구현 판단은 이 남은 관련 조건에 근거합니다. 확인한 resource slot·inline 입력 소비·기존 내용 비교를 반복 세분화해 실제 조회 성공으로 보고하지 않습니다. 전체 EC 해시나 모든 플랫폼 writer의 부재를 절대 전제로 추가하지도 않습니다.

이번 제공물은 개발 소스·회귀 테스트·분석 기록입니다. 현재 앱의 사용자 흐름은 같고 배포 ZIP은 갱신하지 않았으며 새 노트북 실행·동일 자료 제출은 필요하지 않습니다. 삼성 원본·사용자 식별정보·실행용 firmware 주소/명령/프레임을 배포하지 않습니다. 원본 코드의 실행·로딩·에뮬레이션, 하드웨어/OEM·기존 단발 예약 접근, 드라이버·서비스·보안·펌웨어 변경은 없었습니다. 이전 차단 실행 시도도 재현하지 않았습니다.
