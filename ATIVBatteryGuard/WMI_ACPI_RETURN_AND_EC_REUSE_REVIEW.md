# WMI·ACPI 반환 계약과 EC 입력 재사용 — 2026-11-07

**정상 method의 입출력 흐름을 공식 계약으로 보강하고, EC 오류를 무조건적인 전체 종료 요구와 분리했습니다.** 보호 값을 얻을 유용성이 제한된 기본 안 A와, 추가 gate 호출·상태 변경을 명시한 비실행 대안 B도 비교했습니다. 실제 backend·실기 호출은 추가하지 않았으며 보호 설정 조회·충전 제어는 여전히 미구현·Unsupported입니다.

[이전 경로 검토](SELECTED_WMI_ROUTE_AND_COMPLETION_REVIEW.md)의 후속입니다. [현재 시험안](FIXED_MODE_READ_PROPOSAL.md)과 [연결 판정](FIXED_MODE_READ_DECISION.md)에 반영하고, 출처·해시·한계는 [정제 기록](reports/wmi-acpi-return-ec-reuse-audit.json)에 남겼습니다.

## 공식 계약이 설명하는 범위

| 근거 | 확인한 계약 | 확대하지 않는 범위 |
| --- | --- | --- |
| Microsoft WMI ACPI sample README | Wmiacpi.sys가 ASL의 data·method·event를 WMI에 노출하는 mapper 역할 | 현재 로드된 구현·선택 메서드 실행 관측 아님 |
| IRP_MN_EXECUTE_METHOD 계약 | GUID·method ID로 선택하고 입력 자료를 사용해 출력 자료를 반환하는 WMI method 요청 | 성공 출력이 보호 설정이라는 의미나 모든 오류의 미게시 보장 아님 |
| Microsoft ACPI method 평가 계약 | 입력/출력 argument buffer와 동기 평가·비동기 하위 요청 완료의 관계 | 일반 ACPI 평가를 실제 WMI-ACPI 내부 구현 trace로 대체하지 않음 |

저장된 모델의 WMI metadata·선언·AML 본문은 기존 매핑 근거입니다. 이번 공식 자료와 합쳐 정상 method 출력이 평가 결과를 반환하는 구조를 보강하지만, 세부 WMxx/Arg2/_WDG 매핑의 공식 규격 원문까지 확보한 것은 아닙니다. 공식 sample README가 지목한 첨부 문서·ASL·MOF의 정확 경로는404였으며 원문 부재나 다른 위치의 부재를 증명하지 않습니다. 추측 URL을 늘리거나 Linux 설명을 Windows 계약으로 승격하지 않았습니다.

정상 mapper가 보존된 object/method와 AML 본문을 선택하고 입력 buffer를 해당 인수에, 반환 buffer를 API 출력에 연결한다는 모델 대응을 명시 가정으로 둡니다. **정상 평가·반환 경계는 이 가정 아래 조건부 연결됨으로 동결**합니다. 세부 규격 원문 미확보 하나를 독립 blocker나 전체 kernel 구현·현재 장치 trace·모든 대안 경로 해명의 요구로 남기지 않습니다. 정상 반환과 실제 샘플의 신선함은 서로 다른 판단입니다. 새 규격 원문·provider 코드·관련 trace나 구체 반례가 있을 때만 이 항목을 다시 열고 같은404·GUID·metadata 검색은 반복하지 않습니다.

## 내부 분기와 외부 관측

| source 분기 또는 관측 | 확정할 수 있는 범위 | 남기는 판단 |
| --- | --- | --- |
| SDK 호출 전 로컬 검증/중단으로 확실히 종료 | 이 invocation은 OEM method를 호출하지 않음 | 외부 actor 전체의 정지는 뜻하지 않음 |
| source상 gate 거부 또는 첫 EC 준비 실패 | 해당 분기에서 새 EC command 게시 없음 | 외부 FF만으로 이 분기를 식별할 수 없음 |
| SDK 비동기 호출의 즉시 반환 | 호출 개시 단계가 반환함 | 최종 완료·EC 실행·새 샘플은 미확정 |
| 취소가 아닌 정상 최종 API 완료: 성공 HRESULT와 적용 가능한 provider/AML 반환 계약 | 선택 host 프레임의 관련 접근 종료를 설명할 근거 | EC 게시 여부·다음 mailbox 재사용·결과 유효성은 별도 |
| 정상 API 완료 뒤 출력 구조/값 검증 실패 | 결과는 판정불가 | 잘못된 값이라는 이유만으로 host 요청이 계속 실행 중이라고 하지 않음 |
| SDK dispatch 예외 또는 완료 근거 유실 | 부분 개시를 배제하지 못함 | faulted Task만으로 미게시·종료를 판정하지 않음 |
| UI timeout 또는 클라이언트 취소 | 사용자의 대기·클라이언트 측 중단 | provider 정지·rollback·버퍼 재사용 허용이 아님 |

명시적인 오류 완료도 출처와 계약이 마지막 관련 접근 종료를 보장한다면 완료 근거로 사용할 수 있습니다. 임의의 비성공 상태나 불명 dispatch를 그런 오류 완료로 간주하지 않습니다.

gate/준비 실패와 게시 후 wait 오류는 같은 외부 실패 형태로 나타날 수 있고, 첫 send 오류가 다음 wait에 가려질 수도 있습니다. FF·ACK·겉의 정상 반환만으로 **명령을 실행하지 않았음**을 판정하지 않습니다. FF를 본 뒤 handshake나 다른 명령을 추가하는 fallback도 없습니다.

기존 backend의 로컬 dispatch 예약은 SDK 호출 전에 설정되고 그 뒤에도 중단 검사가 있습니다. 예약값은 실제 SDK 호출 증거가 아닙니다. 기존 backend는 서로 다른 실패를 같은 fault로 정리하므로 이를 그대로 새 owner에 연결하지 않습니다. 새 callback drain counter를 추가해도 이 provenance를 복구할 수는 없습니다. 사용 완료된 과거 단발 예약의 상태나 재사용 정책은 변경하지 않았습니다.

## EC mailbox의 세 결과와 다음 재사용

1. **첫 준비 실패로 미게시:** upload와 command post를 건너뜁니다. 새로 게시한 작업의 drain은 필요하지 않습니다. 뒤의 wait가 성공해도 기존 데이터를 복사할 수 있으므로 새 조회 성공으로 분류하지 않습니다.
2. **게시 후 정상 ready:** 선택 reader의 입력 소비·결과 저장은 dispatcher clear보다 앞섭니다. 이 정상 흐름의 clear는 다음 재사용 근거가 됩니다. reader 전 clear로 조회가 폐기될 수도 있으므로 raw zero는 새 샘플의 고유 완료ID가 아닙니다.
3. **게시 후 wait 오류:** 오류 반환 자체로 EC 종료를 확정하지 않습니다. 다만 같은 규약의 다음 sender도 zero-ready 이전에는 upload/post하지 않고 준비 오류면 미게시로 끝납니다. 따라서 관련 참여자가 이 규약을 지킨다면 다음 재사용을 지연·실패시켜 pending 입력을 보존할 수 있습니다.

최소 조건은 계속 사용할 입력뿐 아니라 해당 요청의 마지막 관련 결과 쓰기·command clear가 다음 요청과 충돌하지 않는 handoff입니다. 모든 EC effect 종료를 기다리는 것만이 유일한 해법은 아닙니다. 알려진 inline 입력 소비·버퍼 분리·reader 후 clear·late clear의 샘플 비변경 근거는 유지합니다. 새 source edge나 IRQ actor를 발견한 것은 아닙니다.

확인한 fixed reader는 저장 보호 mode·임계값에 쓰지 않고 mailbox 결과를 씁니다. 이는 선택 source 모델의 고정 대상·입력 안정성 전제에 한정합니다. 실제 관련 외부 참여자의 admission 규약 준수는 별도 조건이며, 사전 대상 무결성은 사후 응답 거부로 대체하지 않습니다. 모든 status/IRQ 생산자 발견이나 모든 SDK cleanup 종료를 추가 요구하지 않습니다.

## 유용성 비교와 다음 연결 조건

[시험안의 A/B 비교](FIXED_MODE_READ_PROPOSAL.md)를 구체화했습니다. A는 기존대로 최대1회 읽기·handshake0이며 source 초기 gate 닫힘이면 값을 얻지 못합니다. B는 사전에 별도로 선택하는 대안으로 handshake1회와 조건부 읽기1회, 최대2회 WMI 호출입니다. handshake 실패·불명이면 읽기0회이고 고정 대상 샘플은 두 안 모두0~1회입니다.

B의 handshake는 EC helper를 호출하지 않아도 공유 image-data gate에 열린 값을 기록하는 상태 변경입니다. 후속 generic 기능 허용에도 영향을 주고 이전 상태 복원을 제공하지 않습니다. 실패·불명으로 읽기를 중단해도 이미 일어났을 수 있는 gate 변경이 rollback되는 것은 아닙니다. 두 호출과 그 사이의 관련 소유권·마지막 접근을 검토해야 하며, gate 응답은 뒤의 EC 읽기 실행·신선함을 인증하지 않습니다. 현재 기본 안·실행 권한은 바뀌지 않았고 승인 질문도 하지 않습니다.

다음 연결 판단은 모델 선언·표준 mapper 계약의 적용 가정, 관련 참여자의 재사용 규약, 실제 adapter의 미게시/관련 완료/불명 dispatch 구분과 선택 안의 유용성에 집중합니다. 이미 확인한 source 순서·같은 문서·동결된 status 검색을 반복해 새 근거로 세지 않습니다.

## 검증과 변경 범위

공식 문서는 텍스트로만 읽고 출처·해시를 보존했습니다. EC 결과 검산은 기존 source body의 재대조이며 새 code edge 수는0입니다. 자체 C#도 텍스트로 검토했고 실행하지 않았습니다. 앱/Core·테스트·EXE·배포 ZIP은 변경하지 않아 전체 빌드·단위 테스트를 반복하지 않았습니다. C#463개·빌드 경고/오류0은 이전1790a4b 기록이며 이번 검산에 합산하지 않습니다.

실제 WMI/OEM·하드웨어·사용 완료된 예약 접근, 원본 실행·로딩·에뮬레이션, driver/service/security/firmware 변경은 없습니다. 주소·request/frame·표식·generator·backend는 만들지 않았습니다. 새 노트북 실행이나 동일 자료 제출은 필요하지 않습니다.
