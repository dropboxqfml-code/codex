# 완료 경계와 조건부 고정 읽기 시험안 — 2026-11-07 한국 시간

**고정 보호 저장 바이트의 비실행 시험안을 구체화했습니다. 실제 호출 연결은 계속 보류합니다.** 이전 판정에서 실행 준비 조건이 시험안 작성 시점까지 확대될 수 있던 표현을 정정했습니다. 미확인 IRQ 전체나 모든 외부 활동의 정지는 제안의 절대 전제가 아닙니다. 실제 보호 설정 조회·충전 제어는 여전히 미구현·Unsupported입니다.

[이전 협력 소유권 구현](COOPERATIVE_EXCHANGE_OWNERSHIP_UPDATE.md)의 후속입니다. 이번에는 잠금 코드를 더 늘리지 않고 기존 provider 완료의 의미와 고정 읽기에 필요한 조건을 독립 재검토했습니다. [구체 시험안](FIXED_MODE_READ_PROPOSAL.md)과 [실제 호출 연결 판정](FIXED_MODE_READ_DECISION.md)을 구분합니다.

## 기존 완료 Task의 범위

기존 backend의 정상 경로는 SDK dispatch call이 반환하고 Completed 처리에서 선택 객체의 detached snapshot 읽기·Dispose 시도가 끝나야 Task를 게시합니다. 반면 별도 ObjectReady에서 진행 중인 다른 객체 정리 전체의 drain barrier는 없습니다. SDK dispatch의 동기 예외도 async backend에서는 faulted Task가 되므로 겉의 직접 throw/null 검사만으로 보완되지 않습니다.

우리 collector와 snapshot 두 파일만 연결한 private .NET8 하네스로 이를 재현했습니다. 선택 A의 읽기를 멈춘 사이 late B의 Dispose를 event로 막고, A 완료와 capture.Dispose가 반환해도 B 정리는 남아 있음을 확인했습니다. 이후 두 작업을 모두 종료하고 객체를 각각 한 번 정리했습니다. **13개 검산 통과·하네스 빌드 경고/오류0**이며 실제 WMI SDK·provider·펌웨어는 실행하지 않았습니다.

이 결과는 관리 객체 정리의 경계입니다. B의 private Dispose가 남았다는 사실만으로 펌웨어가 계속 실행되거나 공유 WMI 입력이 다시 바뀐다고 결론 내리지 않습니다. 실제로 확인할 완료는 해당 교환의 **공유 입력 준비·trigger·응답 회수와 관련 후속 접근**의 종료입니다. 독립 SDK housekeeping나 무관한 EC 백그라운드 활동 전체의 정지를 요구하지 않습니다.

## 참조 코드의 비교 근거

Microsoft dotnet/runtime v8.0.0의 observer·sink·event args·base object 소스4개를 읽고 해시·선택 텍스트 관계6개를 검산했습니다. NewObject getter는 저장된 객체를 반환하고 COMPLETE 분기는 Completed를 알린 뒤 sink를 제거합니다. delegate 구현의 실제 호출 순서와 stub/객체 cleanup을 구분했으며 comment를 thread/완료 보장의 대용으로 쓰지 않았습니다.

이 참조는 **현재 노트북 Windows10의 .NET Framework4.8 구현과 일치함을 입증하지 않습니다.** 선택 new Dispose 본문만으로 generic IDisposable의 실제 dispatch target이나 COM 부수 효과도 확정하지 않습니다. callback 전체 quiescence·실제 provider/AML/EC 종료의 증거도 아닙니다. 원문은 private cache에만 보존하고 [정제 기록](reports/provider-completion-read-trial-audit.json)에 출처·해시·한계를 남겼습니다.

## 읽기 횟수와 gate 조건

기존 generic callback의 software gate는 저장 원본에서 닫힌 값으로 시작합니다. local handshake는 그 값을 열 수 있고 선택 소스에서 EC helper를 부르지 않지만, **별도 WMI/OEM method 호출과 firmware image-data 상태변경**입니다. EC 읽기1회와 WMI 호출1회를 같은 계수로 세지 않습니다.

현재 비실행 안은 초기화·handshake 없이 **최대1회 WMI 읽기 시도, 고정 대상 byte 샘플은0~1회**입니다. 이는 mailbox 접근·ready polling이나 무관한 EC 활동 전체의 횟수가 아닙니다. 현재 gate는 미관측이며 과거 단발 실기의 FF 원인을 이 gate로 확정하는 것도 아닙니다. 닫혀 있으면 보호 값을 얻지 못할 수 있으며 FF/오류를 기능 부재·보호 해제로 해석하지 않습니다. 유의미한 데이터가 나올 준비를 마친 실기 시험이라고 표시하지도 않습니다. gate 열기를 추가하려면 호출 수·상태 영향·승인 범위를 별도로 검토해야 합니다.

fresh-content 비교는 특정 이전 내용·송신 생략을 구분하는 조건으로 검토할 수 있습니다. EC가 발급한 완료ID가 아니며 보존 tail 일치만으로 주소 소비 시점의 무결성·handler 실행을 인증하지 않습니다. echo 거부도 입력과 허용 결과 영역의 구분이 별도로 성립할 때만 유효합니다. 실제 표식 값·주소·프레임·generator는 만들지 않았습니다.

## 남길 조건과 제외할 과도한 조건

실제 연결 판단에 필요한 근거는 세 묶음으로 한정합니다.

1. **선택 경로와 고정 대상:** 모델/BIOS·조건부 해석·등록된 Windows 경로·저장 byte·gate 범위를 묶습니다. 선택하지 않는 모든 대안 통신 경로까지 닫을 필요는 없습니다.
2. **관련 전체 교환의 소유권:** 공유 입력 준비부터 trigger·응답 회수까지 실제 관여하는 호출자가 같은 규약을 지키거나 동등하게 순차화돼야 합니다. mutex 이름·Field Lock·앱 slot만으로 대체하지 않습니다.
3. **관련 완료와 결과 분류:** 완료 뒤에도 같은 입력/응답을 사용하는 host 작업이 남는지, 오래된 응답·echo·모호한 값 거부와 기존 작업 입력 비훼손을 확인합니다. old backend를 그대로 새 owner에 연결하지 않습니다.

이미 확인한 worker 입력의 inline 소비·버퍼 분리, known ISR register 보존, 완료 후 clear의 샘플 비변경은 위험을 좁혔습니다. 관련 없는 status/IRQ 생산자 전체 미확인을 다시 독립 필수조건으로 세지 않습니다. 조회의 명령·주소·계속 사용할 입력·결과에 영향을 준다는 구체 연결이 생긴 범위만 추적합니다. 실제 간섭 actor를 새로 찾았다는 주장도 아닙니다.

## 현재 결과와 제공 범위

**조건부 비실행 시험안 검토 가능, 실제 backend 추가·호출은 보류**입니다. gate 통과의 유용성과 위 세 묶음의 실제 연결 근거가 남습니다. 현재는 실행 승인을 요청하는 단계가 아니며 초기화나 사용 완료된 실기 예약 재사용으로 우회하지 않습니다.

문서·정제 기록만 변경했습니다. 앱/Core·기존 테스트·EXE·배포 ZIP은 그대로이고 전체 테스트/빌드는 반복하지 않았습니다. C#463개·전체 빌드 경고/오류0은 이전1790a4b, Python88개는 이전e7b067a 기록입니다. 이번 새 실행은 우리 collector의 private fake 하네스이며 참조 source 검산과 혼합해 앱 테스트 수로 세지 않습니다.

삼성/펌웨어 원본 실행·로딩·에뮬레이션, 실제 WMI/OEM·기존 실기 예약·hardware/firmware 변수 접근, 드라이버·서비스·보안 변경은 없습니다. 개발 참고 원문4개는 정상 proxy/TLS로 읽었으며 앱 네트워크는 추가하지 않았습니다. 이전 차단된 실행 시도도 재현하지 않았습니다. 새 노트북 실행이나 동일 자료 제출은 필요하지 않습니다.
