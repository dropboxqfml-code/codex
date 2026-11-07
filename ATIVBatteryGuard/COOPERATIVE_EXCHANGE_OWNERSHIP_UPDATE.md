# 협력 교환의 소유권 경계 구현 — 2026-11-07 한국 시간

후속 [완료 경계·조건부 시험안 검토](PROVIDER_COMPLETION_AND_READ_TRIAL_REVIEW.md)에서 비실행 제안과 실제 호출 준비를 구분하고 관련 완료·gate 호출 수를 구체화했습니다. 미확인 status/IRQ 전체를 제안의 필수조건으로 다시 세지 않습니다. 아래는 당시 코드463개·source 검사 기록입니다.

**유한 잠금 대기·같은 스레드의 획득/해제·실제 하위 작업 종료까지 소유하는 준비용 조정 코드를 구현했습니다.** C#463개 테스트 통과, 전체 솔루션 Release 빌드 경고0·오류0입니다. 새 1회 보호 조회 시험은 [보류 판정](FIXED_MODE_READ_DECISION.md)이며 실제 보호 설정 조회·충전 제어는 아직 미구현·Unsupported입니다.

[공유 자원 재진입 수정](SHARED_CHANNEL_COORDINATION_UPDATE.md)의 후속입니다. 새 코드는 명시적으로 공급한 채널과 잠금만 조정하며 앱에 등록하지 않았습니다. 실제 OneShot backend·Program·사용 완료 예약·승인 gate·요청 encoder는 그대로입니다.

## 구현과 보호 범위

`WsabiWmiCooperativeFrameChannel`은 전용 owner thread에서 잠금을 획득하고 하위 channel task를 기다린 뒤 같은 thread에서 해제합니다. 획득 대기는 최대2초이며 하위 작업·SMM 처리의 강제 종료 상한을 뜻하지 않습니다. 정상 결과도 해제가 성공한 후에만 게시합니다.

Gate attempt는 결과와 실제 소유 lease를 함께 보고합니다. 정상 획득만 하위 호출을 허용합니다. 대기 시간 초과·접근 거부·사용 불가·취소는 하위 호출 없이 종료합니다. abandoned 결과는 소유권을 받았어도 실행하지 않고 같은 owner가 정리합니다. abandoned·획득 상태 불명·해제 실패는 해당 resource와 gate identity를 프로세스 안에서 계속 격리합니다. 새 wrapper나 새 고정 adapter로 이 격리를 우회하지 못하며 reset API는 없습니다.

`WsabiWmiWindowsMutexGate`는 저장된 OEM의 고정 Global mutex 이름만 지원합니다. 생성자는 아무 OS 객체도 열지 않고, 명시적 Acquire에서만 정상 권한으로 열거나 만듭니다. 다른 이름·계정·권한 fallback이나 ACL 변경은 없습니다. 기본 경로는 Windows에서만 사용할 수 있고, 모든 고정 adapter는 같은 gate identity를 공유합니다. 실제 이름을 받는 public 생성자는 없습니다.

이는 같은 잠금 규약에 참여하는 호출자의 조정입니다. 모든 OEM·직접 ACPI·펌웨어 작업의 배제를 제공하지 않습니다. 공유 준비·staging과 detached 응답 정리는 공급된 channel의 호출/task 안에 포함돼야 합니다. Gate를 쓰더라도 전체 WMI 입력 준비·snapshot·응답 회수에 관련 참여자가 실제로 같은 규약을 지킨다는 근거가 추가로 필요합니다.

## 취소·늦은 획득·불명확한 종료

각 시도에 별도 stop 신호를 만들고, caller 취소나 UI deadline에서 하위 취소 callback을 실행하기 전에 그 신호부터 보냅니다. 획득 직후의 CAS가 dispatch 시작점입니다. **stop이 먼저 이기면 하위 호출0회**, dispatch가 먼저 이기면 이미 시작한 작업의 취소·완료 정리로 다룹니다. 모든 실제 취소 시점 뒤에 하위 메서드 진입이 절대 없다는 더 강한 주장은 하지 않습니다.

하위 channel에는 private CTS를 전달하고 owner가 취소 callback을 직접 실행합니다. callback이 막히거나 하위 task가 아직 진행 중이면 lease와 공유 Busy 상태를 유지합니다. UI의 timeout/cancel 결과 반환은 이 소유권 해제보다 앞설 수 있습니다. 기존 FrameExchange는 하위 task와 취소 정리가 끝나기 전 같은 알려진 자원의 peer 요청을 허용하지 않습니다.

성공·fault·cancel task가 실제 작업 종료를 뜻해야 하며, sync throw/null task에는 미추적 작업이 없어야 합니다. 이 계약을 인터페이스에 명시했고 sync throw/null도 새 요청을 격리합니다. 격리만으로 잘못된 provider가 이미 시작한 작업을 종료시킬 수는 없습니다. 프로세스·owner thread 강제 종료도 외부 provider 작업의 정지·원상 복구를 보장하지 않습니다. 이 한계가 남는 경로는 실제 시험에 연결하지 않습니다.

보호 scope는 FrameExchange의 같은 알려진 resource reference와 공급된 gate 규약입니다. 새 owner wrapper도 기존 channel/BoundFrameChannel의 canonical identity를 이어받습니다. 직접 channel 호출에는 FrameExchange admission이 없으며, 별도 reference 뒤의 같은 물리 endpoint나 임의 비참여 wrapper 전체까지 같은 자원이라고 보장하지 않습니다.

## 실제 검증 범위

기존441개에 새22개를 더해 **463개 모두 통과**했습니다. 정상 해제의 thread affinity·해제 후 결과 게시, 유한 대기·접근 거부, 늦은 획득과 stop CAS, blocked 취소 callback·late fault, abandon·해제 실패·peer 격리, 기존 resource identity 보존을 검사했습니다. [테스트 결과](reports/cooperative-owner-tests.json)를 보존했습니다.

테스트는 fake gate/channel과 실제 **unnamed Mutex**만 사용했습니다. fixed Global adapter는 lazy identity와 비Windows 거부만 검사했으며, Windows에서도 그 실제 이름을 획득하지 않도록 테스트를 작성했습니다. 따라서 현재 Windows Global namespace의 ACL·OEM 프로그램 참여·실제 상호 운용을 검증한 것은 아닙니다. synthetic 프레임은 기존 fixture이며 하드웨어 요청이 아닙니다.

SDK8.0.427·보존된 .NET Framework4.8 참조와 이전에 확인한 IL 빌드 설정으로 전체 솔루션을 빌드했습니다. 경고0·오류0이며 SDK 패치·XAML 단계 생략·새 패키지 설치는 없었습니다. Windows에서 새 EXE를 실행한 시험은 아닙니다. Python 개발 도구는 변경하지 않았고 Python88개는 이전 `e7b067a` 기록입니다.

## 한정한 펌웨어 조사와 시험 판정

이번 한정 조사에서는 **새 실제 status/IRQ 생산자 연결을 확보하지 못했습니다.** 요청 인수가 기록되는 고정 field와 상태 소비자의 관계를 검산했지만, 인접 helper를 준비·오류 상태의 실제 생산자로 부를 근거는 없었습니다. ordinary byte readback 가정과 실제 MMIO/외부 처리 의미를 구분하며 물리 효과를 추정하지 않습니다.

남은 연결은 요청 control 게시→외부/controller/IRQ 처리→후속 준비·오류 상태 생산입니다. 소비자·기존 polling·앞선 pointer 정정을 새 IRQ 발견으로 다시 세지 않았고, 이 후보 범위는 동결했습니다. [정제 기록](reports/cooperative-owner-audit.json)은 source의 새 check와 기존 문맥, **생산자 연결0개**를 분리합니다.

새 software 경계의 검증은 진전이지만, 실제 Global 협력·provider 완료 계약과 관련 하드웨어/표준 통신 실행 영역이 닫히지 않았습니다. 따라서 [고정1바이트1회 시험](FIXED_MODE_READ_DECISION.md)은 **보류**합니다. 같은 source 후보·잠금·내용 비교를 반복하는 것으로 이 판정을 바꾸지 않으며, 그 미완료 조건을 줄이는 새 근거가 필요합니다. 전체 live EC hash나 모든 writer의 전역 부재를 대신 필수화하지 않습니다.

## 제공 범위

제공물은 조정 코드·오프라인 테스트·source 분석·시험 판정입니다. 현재 앱 흐름과 기존 배포 ZIP은 그대로이고, 새 실기 실행·동일 자료 제출은 필요하지 않습니다. 실제 하드웨어 backend·배터리 명령·실행용 firmware 주소/프레임·새 예약은 추가하지 않았습니다.

삼성/펌웨어 원본의 실행·로딩·에뮬레이션, 하드웨어/OEM·기존 실기 예약 접근, 드라이버·서비스·보안·펌웨어 변경은 없습니다. 실제 OEM Global 객체도 열지 않았습니다. 이전 차단 실행 시도는 보존하며 재현하지 않았습니다.
