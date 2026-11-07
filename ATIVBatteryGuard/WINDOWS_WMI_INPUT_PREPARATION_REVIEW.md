# 저장된 읽기 근거 대조와 SDK 입력 준비 — 2026-11-08 한국 시간

**고정 저장 byte reader의 조건부 읽기 의미를 정리하고, 공급된 SDK 입력 객체에 요청을 넣는 준비 코드를 분리했습니다.** 실제 보호 조회 명령·요청 template·SDK 메서드 호출은 추가하지 않았습니다. 보호 설정 조회·충전 제어는 Unsupported이며 현재 노트북의 보호 상태를 새로 관측한 결과가 아닙니다.

## 저장 근거가 지지하는 읽기 범위

| 비교 항목 | 저장된 근거와 이번 판정 |
| --- | --- |
| 읽는 대상 | [EC 보호 후보](EC_CHARGE_PROTECTION_CANDIDATE.md)와 [독립 reader](EC_READBACK_AND_WINDOWS_BRIDGE.md)는 조건부 8051·공통/bank 모델에서 software mode 저장 byte와 80/75 정책을 연결합니다. 선택 reader는 대상에 쓰지 않고 결과 한 byte를 메시지에 넣습니다. setter echo와 다르지만 전용 보호 getter·충전기 적용·영속성은 아닙니다. |
| Windows 경로 | 같은 기록에서 WMI→AML→등록된 generic callback과 입력·반환 위치를 연결했습니다. [선택 경로](SELECTED_WMI_ROUTE_AND_COMPLETION_REVIEW.md)의 gate는 초기닫힘/현재미관측입니다. A의 handshake 0회는 유지하며 별도 상태 변경 호출인 B를 숨겨 추가하지 않습니다. |
| 입력 보존 | [입력·정리 분석](EC_QUERY_INPUT_AND_CLEANUP_REVIEW.md)과 [공유 규약](SHARED_CHANNEL_COORDINATION_UPDATE.md)은 주소 성분의 별도 소비, 식별된 선택 worker의 원본/local 입력의 inline 소비·영역 분리와 알려진 ISR 보존을 설명합니다. 전체 IRQ·별칭·하드웨어 보존을 완결한 것은 아니며 사후 tail 일치가 사전 command/주소 안정성을 증명하지는 않습니다. |
| 오류·신선함 | [오류 경계](EC_FRESHNESS_AND_ERROR_PATHS.md)에는 새 게시 실패를 뒤 wait가 가려 과거 데이터를 반환할 수 있는 조건이 있습니다. ACK·API 완료·FF·유효한 frame만으로 reader 실행이나 최신 결과를 확정하지 않습니다. |
| 재사용·완료 | [EC 재사용 검토](WMI_ACPI_RETURN_AND_EC_REUSE_REVIEW.md)는 미게시·정상 ready·게시 후 wait 오류를 구분합니다. 관련 참여자의 전체 교환/admission 규약과 실제 adapter의 terminal·결과 귀속이 남으며, 모든 EC 활동의 종료나 모든 writer 부재를 요구하지 않습니다. |

이는 기존 소스 연결의 대조입니다. 새 펌웨어 처리자나 현재 장치의 실행 근거를 찾았다고 세지 않습니다. 과거 소비한 단발 후보와 현재 generic 저장 byte reader를 같은 명령으로 취급하지 않고 옛 정책·payload 생성기를 재사용하지 않습니다.

## SDK 호출에 아직 빠져 있던 입력 경계

기존 request의 `Arguments`는 순수 dictionary입니다. 저장된 Microsoft 참조 소스에서 선택 async overload는 실제 `ManagementBaseObject` 입력을 native 비동기 호출에 넘깁니다. dictionary만으로 SDK 입력 객체를 대신할 수 없습니다. 기존 실험 backend가 하던 `Bytes`와 `inData` 할당을 새 실행 경로에 그대로 복사하기 전에 별도 준비 단계로 검증했습니다.

`WsabiWmiWindowsInputPreparation.Populate`는 기존 plan으로 요청의 MethodId·frame·command 관계를 확인하고 canonical 사본을 만듭니다. null/동일 wrapper를 거부한 뒤 다음 조건을 검사합니다.

- 공급 buffer의 class는 DataBuffer이며, input의 단일 inData는 scalar Object입니다.
- buffer의 단일 Bytes는 UInt8 array입니다. 모든 shape 확인이 끝나기 전에는 Value를 할당하지 않습니다.
- frame 사본을 Bytes에 넣은 다음 같은 buffer 참조를 inData에 넣습니다. 이전 Value는 읽지 않습니다.

실제 frame의 읽기 의미·대상 적합성·입력 객체의 method 출처·embedded qualifier 연결은 이 객체 shape 검사가 인증하지 않습니다. 기존 상세 metadata의 qualifier 대안은 변경하지 않았고 새로운 qualifier 강제 조건도 추가하지 않았습니다.

## 일부 변경 뒤 실패와 소유권

두 wrapper는 SDK 접근 전에 같은 lock 아래 reference identity로 함께 claim합니다. 그 뒤 shape 거부·getter 오류·일부 할당 후 setter 오류가 나도 같은 wrapper를 어느 역할로든 다시 준비하지 않습니다. 한쪽이 이미 사용됐다면 새 다른 쪽을 불필요하게 소모하지 않습니다. SDK getter/setter는 lock 밖에서 실행하며 재진입·동시 시도는 같은 객체에 다시 접근하지 못합니다.

두 번째 할당이 실패하면 첫 변경이 남을 수 있습니다. 이전 값을 읽거나 rollback·자동 재시도하지 않고 고정 오류 상태만 반환합니다. 이 준비는 동기 SDK 접근이므로 getter/setter가 지연되면 함께 기다립니다. 호출자 timeout을 준비 종료나 객체 폐기 가능의 근거로 사용하지 않습니다. 두 객체는 caller가 소유하므로 성공·실패 모두 여기서 Dispose하지 않습니다. 향후 실제 host는 실패 객체를 폐기하고, 성공 객체는 관련 호출의 종료·Unknown 수명 동안 보유해야 합니다. 아직 그 host 연결은 추가하지 않았습니다.

같은 managed wrapper는 plan을 새로 만들어도 재사용할 수 없습니다. 새 wrapper·다른 프로세스·다른 COM alias는 제한 범위 밖입니다. 외부 동시 변경·대상 선택·실제 SDK 호출 수나 embedded setter의 native 복사 방식도 인증하지 않습니다. 옛 persistent 예약에는 접근하지 않았습니다.

공급 계약은 이미 materialize된 입력 객체입니다. 저장된 참조의 Properties/indexer 접근은 Initialize(true)를 부를 수 있으므로 임의 lazy 객체에 대한 순수 메모리 작업·무조회 보장으로 표현하지 않습니다. 이 helper에는 SDK 객체 생성·탐색·Connect/Get/Put/InvokeMethod/Cancel의 명시적 호출이 없습니다. 실제 SDK 객체로 실행한 시험도 아닙니다.

## 검증과 다음 작업

새 입력 준비 회귀 10개를 포함해 **전체 572개 통과·실패 0·skip 0**입니다. 사전 SDK 접근 차단, 잘못된 shape의 무할당, 정확한 byte[] 사본과 두 setter 순서, getter/부분 setter 실패, wrapper 역할 공유·동시 claim과 borrowed Dispose 0을 검증했습니다. 기존 synthetic 요청과 SDK stand-in만 사용했으며 실제 System.Management runtime/provider는 실행하지 않았습니다. Windows 연결 계층의 production 소스 6개를 같은 portable 시험에 링크했습니다.

기존 SDK 참조 텍스트 2개의 길이·해시와 선택 member 내부 관계 7개를 대조했습니다. 새 다운로드·새 펌웨어 연결은 없으며 이 7개를 앱 회귀 수에 합산하지 않습니다. 참조는 dotnet/runtime v8.0.0이고 현재 Windows 10/.NET Framework 4.8 구현 동일성을 뜻하지 않습니다. PropertyData의 실제 변환·native 복사 수명은 이번 근거로 확정하지 않았습니다.

전체 솔루션은 실제 net48 참조 Release 빌드 **경고 0·오류 0**입니다. [정제 기록](reports/windows-wmi-input-preparation-audit.json)에 관측 범위와 검증한 소스 해시를 남깁니다.

이번 결과는 SDK 입력 배치의 준비이며 실제 backend·Main/UI·사용 완료된 실험 정책·encoder·배포 ZIP을 바꾸지 않습니다. 삼성 원본 실행·하드웨어 호출·드라이버/서비스/보안/펌웨어·클라우드 환경 변경은 없습니다. 추가 노트북 실행이나 같은 자료 제출은 필요하지 않습니다.

다음은 준비된 입력 객체의 소유권을 기존 Run/Close 수명에 연결하고, 구체 target/observer/입력이 같은 시도에 묶이는 SDK dispatch 경계를 검토하는 일입니다. 실제 고정 요청의 의미·gate 유용성·관련 참여자·완료/귀속 조건과 실기 승인은 별도로 유지합니다. 소모된 옛 호출을 재연결하거나 A 실패 후 다른 호출을 추가하지 않습니다.
