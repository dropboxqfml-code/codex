# 고정 조회 시험 전 오프라인 리허설과 기록 계획

**이번 단계는 호출·중단·정리 규약을 가짜 source로 재현하는 개발용 시험입니다. 노트북의 보호 설정을 읽거나 변경하지 않습니다.** 공개 SDK entry는 계속 `ReadSpecificationUnavailable`로 차단하며, 보호 조회·충전 제어는 `Unsupported`입니다. 지금 노트북에서 새 프로그램을 실행하거나 자료를 업로드할 필요는 없습니다.

새 리허설은 `tests/OfflineReadTrialRehearsal.cs`와 PortableTests의 테스트 전용 진입점에 둡니다. 기존 Core/Windows 구현을 가짜 SDK 타입·gate·호출 대역과 연결하며 생산 코드나 앱의 실행 경로를 열지 않습니다. 기존 테스트의 합성 frame만 재사용하고 삼성 실기 요청·주소 조합·nonce 생성기는 만들지 않습니다. 펌웨어 검색은 동결하며 삼성 DLL·OEM 호출·Windows WMI provider·Global mutex·과거 소모 예약에 접근하지 않습니다.

## 실기 전에 남아 있는 조건

[고정 시험안](FIXED_MODE_READ_PROPOSAL.md), [응답 거부 명세](FIXED_READ_ACCEPTANCE_SPECIFICATION.md), [입력·회수 경계](FIXED_READ_INPUT_AND_CAPTURE_REVIEW.md)를 유지합니다. 실제 공급자의 method에서 nonNULL GUID를 선택하는 typed dispatch로 이어지는 연결과 관련 실행 영역은 아직 완성되지 않았습니다. 리허설의 성공이 이 연결, 실제 고정 요청의 읽기 의미, 모델 적합성이나 입력·응답 귀속을 증명하지 않습니다.

향후 실기를 검토할 때에는 고정 대상·선택 경로의 근거, 관련 참여자의 입력 준비부터 마지막 소비·응답 회수까지의 보호, 적용 가능한 실제 완료·안전한 거부 규약을 함께 제시해야 합니다. 실기관측이 없다는 이유만으로 모든 writer/IRQ의 부재나 전체 live hash를 새 절대조건으로 추가하지 않습니다. [AGENTS.md](AGENTS.md)의 별도 명시 승인 조건도 유지하며, 이번 테스트 옵션이나 결과 파일은 실행 승인 수단이 아닙니다.

기본 안 A의 한도는 다음과 같습니다. 아래 수치는 미래의 **실제 시험안**에 대한 상한이며 리허설의 fake 호출 횟수와 구분합니다.

| 항목 | 상한 |
| --- | --- |
| WMI/OEM method | 고정 읽기 요청 최대 1회 |
| 고정 대상 sample | 전달·gate 조건에 따라 0~1회 |
| gate handshake·DLL/OEM 초기화 | 0회 |
| 재시도·다른 명령·B fallback | 0회 |
| 배터리 설정·충전기·펌웨어 쓰기 | 0회 |

## 여섯 시나리오의 예상 관찰과 중단선

각 시나리오는 관측 checkpoint와 최종 정리를 구분합니다. 아래는 기대 조건이며 실제 통과 여부는 생성된 기록과 테스트 결과로 확인합니다.

| 시나리오 | checkpoint에서 확인할 관찰 | 중단·최종 정리 조건 |
| --- | --- | --- |
| 공개 SDK entry 차단 | 정상 local 검증 뒤 `ReadSpecificationUnavailable`; Invocation 없음, 하위 준비 상태 없음, 입력 소유 이전 없음. fake gate/Invoke/terminal/capture 호출 0회. | SDK 준비·등록·호출로 진행하지 않음. 별도 실행 또는 숨은 승인 flag를 추가하지 않음. |
| 사전 취소 | 선행 local 검증·claim 후 취소 분기: `PreparationNotReady`와 `RegistrationStatus=Cancelled`; Invocation 없음, 입력 소유 이전 없음, fake Invoke 0회. | 이미 소비한 plan/binding을 새 wrapper로 재시도하지 않음. 이 분기를 호출 후 취소와 구분함. |
| 내부 대역의 gate 시간 초과 | 준비 완료 뒤 fake gate가 실제 `TimedOut`을 반환하고 fake Invoke 0회. 외부 frame 결과는 `TransportFailure`로 접힐 수 있음. | gate의 실제 반환·호출 횟수와 함께 판단함. `TransportFailure` 하나에서 미게시를 추론하지 않음. 사용하지 않은 구독·소유 입력의 정리를 마침. |
| 이른 terminal 뒤 호출 반환 대기 중 UI timeout | fake Invoke·terminal·capture가 관측돼도 호출 stack이 아직 반환하지 않으면 `TimedOut` 표시 뒤 run/close는 pending. lease는 유지되고 입력 Dispose는 0회. | terminal/capture만으로 lease나 입력을 해제하지 않음. 이미 capture가 끝났다면 subscriber는 0일 수 있으므로 구독 보유를 이 case의 필수 조건으로 삼지 않음. 호출 반환을 허용한 뒤 관련 정리를 join하며 표시한 timeout을 성공으로 교체하지 않음. |
| terminal 없이 SDK 대역 throw | fake Invoke는 진입했으나 terminal/capture 완료가 없음. UI timeout 뒤에도 run/close가 pending이고 lease·관련 구독·선택 결과·입력 수명을 유지함. | throw·취소·timeout을 terminal로 바꾸지 않음. 실제 종료 근거가 없는 동안 추가 호출·조기 해제를 허용하지 않음. 리허설을 끝내는 별도 합성 정리는 아래 규칙대로 표시함. |
| 정상 API 완료와 유효 fake frame, 귀속 불명 | 가짜 terminal/capture/호출 반환이 끝나 구조상 유효한 응답을 얻을 수 있음. 준비 상태·frame 결과·정리 결과를 각각 기록함. | fake frame의 형식 통과를 실제 reader 실행·신선함·저장 모드·충전 적용으로 승격하지 않음. 귀속은 불명으로 남기고 실제 제어는 계속 `Unsupported`. |

사전 차단·취소의 의미는 해당 entry와 source 분기에 근거합니다. nullable 상태나 최종 상태 이름만으로 SDK 무접근·미게시를 역추론하지 않습니다. gate 거부 또한 준비 과정의 속성 조회·등록까지 없었다는 의미는 아닙니다.

## 표시 종료와 자원 수명 종료

UI 결과를 표시한 시점과 host를 닫아도 되는 시점을 나눕니다. `RunAndCloseAsync`는 표시 결과를 한 번 전달한 뒤에도 관련 close를 기다리며, 보고 callback의 예외도 이 기다림을 우회하지 않습니다.

Core의 관련 호출 종료에는 호출 stack 반환, 해당 method에 적용되는 terminal, 선택 capture 접근 종료가 필요합니다. 확실한 사전 미진입은 그 local 분기의 근거로 따로 끝낼 수 있습니다. FrameExchange는 늦은 채널 결과와 취소 callback worker를 함께 정리하고, cooperative owner는 필요한 완료 뒤 같은 owner thread에서 lease를 해제합니다. Windows 계층은 관련 handler 접근·구독 해제 시도와 capture 정리를 마친 뒤 입력 해제를 진행합니다. 소유 입력은 parameters 다음 buffer 순으로 각각 Dispose를 시도하며 첫 실패도 둘째 정리를 생략하지 않습니다. borrowed target을 정리 대상으로 바꾸지 않습니다.

terminal이 사라진 경우 close는 계속 pending일 수 있습니다. 반복 stop, 두 번째 timeout, process 종료나 잠금 해제를 provider 종료의 증거로 사용하지 않습니다. Core의 `IsBusy`나 `IsCompletionUnknown=false` 하나도 종료 증거가 아닙니다. 준비 결과의 `InputCleanupStatus`는 그때의 immutable snapshot이므로, 이후 close의 실제 반환 상태와 혼동하지 않습니다. 구독 해제는 이미 queue에 들어간 모든 독립 SDK 작업의 종료를 뜻하지 않습니다.

## 합성 정리를 실제 완료와 구분

리허설의 `finally`는 남아 있는 fake gate·호출 반환 대기를 풀고 필요한 가짜 terminal을 명시적으로 공급한 뒤 관련 task를 join합니다. 이는 테스트 프로세스가 작업을 남기지 않기 위한 **합성 정리**입니다. terminal이 없던 checkpoint를 정상 완료로 고쳐 쓰거나, 실제 SDK가 terminal을 보장한다는 근거로 사용하지 않습니다.

기록의 `syntheticCleanupUsed`와 `finalCleanupStatus`를 구분합니다. 정리 상태가 완료됐더라도 합성 terminal로 끝낸 case의 원래 관찰은 여전히 terminal 유실·pending입니다. 이른 terminal case의 fake 호출 반환 대기를 푸는 행위도 합성 정리로 표시합니다. 해제 실패는 run이 fault하더라도 마지막 checkpoint에 남기고 실패 판정을 유지합니다.

## JSON에 남길 최소 범위

기록은 고정된 시나리오/checkpoint 이름과 다음 안전한 상태·횟수에 한정합니다.

- 준비 결과 enum과 nullable 하위 상태, 입력 소유 이전 상태.
- frame 결과 상태와 fake gate의 실제 반환 상태·호출 횟수.
- fake Invoke 호출·terminal emission·ObjectReady emission·결과 표시 횟수.
- input/target Dispose 횟수, subscriber 수, fake lease 보유 상태.
- run/close task 완료 여부, 최종 정리 상태와 합성 정리 여부.

관련 객체·동작이 없었던 경우와 아직 pending인 경우를 구분합니다. 한 checkpoint의 여러 관찰을 전체 실행에 대한 원자적 증명으로 확대하지 않습니다. 횟수는 대역에서 실제 관측한 값이며 하드웨어/OEM 호출 횟수로 표시하지 않습니다.

`fakeTerminalEmissions`와 `fakeObjectEmissions`는 대역이 이벤트를 보낸 횟수이며, 그 자체로 source가 소비·포착을 완료했다는 뜻은 아닙니다. `fakeInvokeHookExited`도 대역 hook의 반환/throw 관찰일 뿐 SDK 전체 종료 증거가 아닙니다. `preparationInputCleanupStatus`는 준비 당시 snapshot이고 실제 나중의 close 반환은 `finalCleanupStatus`로 따로 기록합니다. 실패한 시나리오는 성공으로 추측하지 않고 `Failed`/`Indeterminate`로 남깁니다.

원시 payload/frame·명령·주소·nonce·삼성 원본·전체 경로·계정·시리얼·고유 장치 식별자·원문 예외는 저장하지 않습니다. `fresh`, `readerRan`, `approved` 같은 관측 불가능한 boolean을 넣어 성공 조건을 만드는 방식도 사용하지 않습니다. 유효 fake frame을 얻은 case에도 실제 배터리 상태나 성공한 보호 모드를 기록하지 않습니다.

## 개발 환경의 테스트 전용 명령

프로젝트 폴더에서 PortableTests 기록 모드를 실행합니다. 출력 경로에는 기존 결과와 다른 새 JSON 파일을 지정합니다.

```sh
dotnet run --project tests/ATIVBatteryGuard.PortableTests.csproj -c Release -- --offline-rehearsal reports/read-trial-rehearsal-new.json
```

이 명령은 개발용 테스트 진입점입니다. 배포 앱·기존 진단 EXE·노트북용 시험 도구를 실행하는 명령이 아닙니다. 리허설 기록과 전체 회귀/빌드 로그도 구분하며, 이전 통과 기록을 이번 실행 결과로 재사용하지 않습니다. 새 실행 파일이나 ZIP 배포 없이 이 단계의 개발 검증을 진행합니다.

## 이번 실행의 검증 기록 — 2026-11-08

[실측 리허설 JSON](reports/read-trial-offline-rehearsal.json)은 6개 시나리오 통과·실패 0을 기록합니다. [정제 검증 기록](reports/read-trial-rehearsal-validation.json)의 전체 회귀는 새 11개를 포함한 628개 통과·실패/skip 0이며, 리허설 6개는 이 전체 검사와 겹칩니다. 테스트 프로젝트와 전체 net48 참조 Release 빌드는 각각 경고·오류 0입니다. 실제 System.Management runtime·OEM·하드웨어 호출은 0이고, 실제 Windows GUI 실행은 검증하지 않았습니다.

초기 SDK first-run의 쓰기 위치는 workspace cache로 옮겼습니다. Linux에서 Windows ReadyToRun 빌드 작업을 로드하지 못한 MSB4062는 개발 빌드 프로세스에만 `COMPlus_ReadyToRun=0`을 적용해 해결했습니다. 노트북·제품·보안 정책을 변경한 것은 아닙니다. 공개 entry 차단과 실제 조회·제어 Unsupported는 그대로입니다.
