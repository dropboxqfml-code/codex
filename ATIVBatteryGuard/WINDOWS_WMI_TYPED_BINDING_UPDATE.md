# Windows WMI 타입 검사와 이벤트 연결 — 2026-11-08 한국 시간

**후속:** [등록 준비 분리](WINDOWS_WMI_PREPARATION_UPDATE.md)에서 준비 실패를 세션 전으로 분리하고 성공 handle만 Run/Close를 제공하도록 변경했습니다. 새15개 포함541회귀·실제 net48 참조 빌드 경고/오류0이며 실제 OEM 호출은 없습니다. 아래는 당시 SDK 타입 연결 기록입니다.

**실제 System.Management 타입을 사용하는 reader와 이벤트 연결 라이브러리를 구현했습니다.** 새 `ATIVBatteryGuard.WmiInterop`는 Core의 기존 callback source/세션을 소비하며 앱에는 등록하지 않았습니다. 준비된 observer와 명시적 dispatch delegate만 받습니다. InvokeMethod·Connect·Get·대상 선택·명령/프레임 생성은 없으며 실제 보호 설정 조회·충전 제어는 Unsupported입니다. [이전 callback source](CALLBACK_SOURCE_CAPTURE_UPDATE.md)의 후속입니다.

## 타입과 소유권

`WsabiWmiWindowsOutputReader`는 공급된 결과의 scalar Object `outData`, embedded `DataBuffer`, UInt8 array `Bytes` 선언과 **정확한 runtime byte[] 타입**을 검사합니다. `as byte[]`만으로는 CLR의 일부 signed primitive 배열 호환을 거부하지 못해 GetType 일치 검사로 보강했습니다. null·다차원·nonzero lower-bound·다른 요소 타입·4096 초과는 고정 실패이며 coercion·padding·truncate는 없습니다. 4096은 보유/복사 상한이고 SDK getter의 선행 할당을 제한하거나 decoder의 허용 길이를 뜻하지 않습니다.

root는 reader가 빌려 쓰며 source가 소유합니다. distinct embedded wrapper는 reader가 byte[]를 **먼저 복사한 뒤** concrete Dispose를 시도합니다. embedded가 root와 같은 참조면 root를 중간에 정리하지 않고 거부합니다. getter/Dispose 실패는 원문 예외·InnerException을 보존하지 않는 고정 실패입니다.

저장된 SDK 참조의 ManagementBaseObject는 Component의 Dispose를 숨깁니다. 일반 IDisposable 호출이 그 concrete method에 도달한다고 가정하지 않고 `OwnedWmiResult`가 명시적으로 호출합니다. 같은 raw root 참조는 같은 canonical wrapper로 묶어 generic source의 reader 보호·중복 Dispose 억제를 유지합니다. 이것은 callback root의 managed reference 범위이며 embedded/native COM alias 전체나 native 자원 소멸의 인증이 아닙니다. 새 코드는 Framework4.8 참조로 컴파일했지만 저장된 v8 원문이 현재 Windows 구현과 같다고 입증한 것은 아닙니다.

## 이벤트 연결과 종료 대기

`WsabiWmiWindowsCallbackSource`는 전용 ManagementOperationObserver 하나를 한 binding에만 허용하며, 두 handler 등록이 끝난 뒤에만 supplied dispatch를 시작합니다. observer의 다른 ObjectReady 소비자·직접 호출·Cancel·재사용은 허용 계약 밖입니다. CWT의 일회 소유는 알려진 observer alias를 막는 소프트웨어 경계이며 실제 SDK method 횟수·물리 endpoint 독점·실행 권한을 인증하지 않습니다.

ObjectReady handler는 NewObject getter **전에** 입장을 등록합니다. Completed 입장과 ObjectReady 입장은 같은 lock에서 completion phase를 결정합니다. Completed가 진행 중인 raw handoff를 앞지르거나 그 뒤 closing 전 새 handoff가 입장하면 결과를 보수적으로 실패 처리합니다. 같은 raw root가 다시 와도 선택 reader를 중간에 Dispose하지 않으며 정상 결과로 승격하지 않습니다. Completed.Status만 terminal로 전달하며 Context/StatusObject는 읽거나 보존·보고하지 않습니다. 이 별도 status 객체의 소유·정리는 binding 범위 밖입니다.

generic source가 선택 복사·정리를 끝내면 observer proxy가 capture를 잠시 보관합니다. 새 primary 입장을 닫고, 이미 입장한 관련 handler의 접근과 unsubscribe **시도**가 끝난 다음 실제 transport observer에 capture를 한 번 전달합니다. 해제 실패면 고정 capture 실패이고 실제 handler 제거 성공으로 보고하지 않습니다. flags의 게시/해제 claim은 lock 안에서, SDK event 조작·getter·reader·Dispose·외부 통지는 lock 밖에서 수행합니다.

unsubscribe는 이미 캡처·큐된 delegate를 철회하거나 SDK 전체를 drain하는 기능이 아닙니다. cutoff 뒤 도착한 객체 callback은 새 선택/reader 없이 canonical wrapper의 독립 로컬 정리만 수행해야 한다는 공급자 계약을 유지합니다. 전체 COM cleanup·provider 종료·실제 Windows callback 타이밍을 새로 입증한 것은 아닙니다.

dispatch의 정상 반환·throw·사용자 stop만으로 handler를 해제하거나 terminal을 만들지 않습니다. terminal이 없으면 선택 객체/구독과 transport/owner/host close가 Unknown/pending으로 남을 수 있습니다. SDK가 제거한 sink를 복구했다고 하지 않습니다. terminal 뒤 dispatch throw는 관련 정리와 결과 실패를 함께 보존합니다.

**등록 준비 실패도 현재 source.Invoke 안에서 발생하면 transport에서는 terminal 없는 Unknown/pending입니다.** 직접 source 시험의 supplied dispatch0회가 세션의 유한 종료를 뜻하지 않습니다. 미래 도구가 이 준비 실패를 유한하게 분류하려면 준비·등록을 세션 시작 전 단계로 분리해야 합니다. 새 NoDispatch/가짜 terminal/재시도 protocol은 추가하지 않았습니다.

## 검증

reader9개와 binding12개, **새 회귀21개 포함 전체526개 통과·실패0·skip0**입니다. 처음524개 중 배열 검사1개가 실패했고, raw admission 경합 회귀를 더한525개에서는523통과·2실패를 기록했습니다. exact runtime 타입과 completion phase를 수정하고 terminal 뒤 dispatch throw 사례를 추가한 뒤526개가 통과했습니다. 경합 회귀는 source.Invoke를 먼저 끝낸 다음 독립 event Task에서 terminal forwarding과 raw getter를 막아, 기존 call-stack join만 확인하는 시험을 피했습니다.

portable 시험은 **동일 production 3개 소스 파일을 테스트 전용 System.Management stand-in과 컴파일**합니다. strict metadata/getter 순서, concrete Dispose 선택·복사 전후 소유권, raw handoff/reader/unsubscribe 대기, queued 동일 객체, 준비 실패·terminal 소실·동시 입장을 검증합니다. stand-in은 Component/new-Dispose라는 필요한 언어 경계만 모델링하며 실제 SDK 구현 전체를 복제하지 않습니다. 실제 System.Management runtime을 로드하거나 객체 생성·provider/COM 동작을 실행한 시험은 아닙니다. portable dependency는 우리 시험 어셈블리뿐입니다.

별도로 **실제 Framework4.8 참조를 사용하는 전체 솔루션 Release 빌드가 경고0·오류0**으로 통과했고 새 Windows 라이브러리도 포함합니다. 기존 캐시의 reference 패키지1.0.3·SDK8.0.427과 ReadyToRun0 IL 설정을 사용해 package source0의 오프라인 복원을 완료했습니다. 초기 일반 restore는 빈 로그/코드1, 미복원 새 프로젝트 빌드는 reference 오류1이었으며 복원 뒤 최종 빌드는 정상입니다. 새 runtime/개발도구 설치·SDK 패치·XAML 단계 생략은 없습니다. 앱·기존 진단 EXE는 컴파일했지만 실행하지 않았습니다.

[정제 기록](reports/windows-wmi-typed-binding-audit.json)에 현재 source/test/project hash와 실행 기록·한계를 분리했습니다. 이전 private 검산이나 SDK 원문 관찰 수는 앱526개에 합산하지 않습니다.

## 다음 작업과 제공 범위

다음은 전용 observer의 준비·등록 실패를 세션 시작 전으로 분리하고, 검토할 단발 조회안의 대상·횟수·준비 조건과 이 연결 계층의 접점을 확정하는 작업입니다. 실제 SDK 이벤트 전달·getter/Dispose·COM threading과 cutoff 뒤 정리의 독립성은 실기 연결 전에 검토해야 합니다. fake 통과와 참조 빌드를 실기 승인으로 바꾸지 않습니다. [A/B 시험안](FIXED_MODE_READ_PROPOSAL.md)의 호출 상한·gate 상태 영향·승인 상태는 유지합니다.

변경은 Windows library4파일·solution1·tests5파일과 문서/정제 기록입니다. Core·앱 기본 backend/UI·old SDK Backend/Program·encoder·사용 완료된 예약·배포 ZIP은 그대로입니다. 실제 WMI/OEM/하드웨어/Global 객체·삼성 원본에 접근하거나 드라이버/서비스/보안/펌웨어·클라우드 환경을 변경하지 않았습니다. 새 노트북 실행이나 동일 자료 제출은 필요하지 않습니다.
