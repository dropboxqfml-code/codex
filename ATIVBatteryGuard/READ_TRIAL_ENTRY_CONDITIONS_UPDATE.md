# 실기 읽기 시험의 시작·중단 조건 적용 — 2026-11-08 한국 시간

**후속:** [요청·응답 바이트 계약](FIXED_READ_BYTE_CONTRACT_REVIEW.md)에서 선택 generic 분기와 reader의 필드를 합성했습니다. 현재 주소/반환을 함께 제공할 분기·payload 주소 순서·지워지는 WMI tail·실패 sample zero를 좁혔지만 실제 요청은 만들지 않았고 공개 차단은 유지합니다. 아래는 entry 차단 구현 시점의 기록입니다.

**공개 SDK 시험 진입점은 검토된 실제 고정 읽기 명세가 없으면 ReadSpecificationUnavailable로 끝나도록 변경했습니다.** [SDK 연결](WINDOWS_WMI_SDK_DISPATCH_BINDING_UPDATE.md)의 후속입니다. 형식이 맞는 임의 frame을 실제 읽기로 허용하는 경로는 열지 않았습니다. 실제 보호 설정 조회·충전 제어는 Unsupported이며 하드웨어의 영구 미지원 판정이 아닙니다.

## 실제 적용한 시작 조건

공개 `PrepareSdkAsync`는 기존 구조 인자·plan 대상/요청·실제 target 참조 identity·bundle 단발 claim·준비 전 취소의 순서를 유지합니다. 이 검사를 통과해도 현재 실기에 사용할 고정 요청 명세가 없으므로 `ReadSpecificationUnavailable`를 반환합니다. 실제 요청 byte·주소·nonce·generator를 새로 만들거나 옛 소비된 후보를 현재 reader의 명세로 사용하지 않았습니다.

이 결과는 SDK target metadata 조회·입력 claim/할당·observer 등록·gate 획득·session·typed Invoke 전에 반환됩니다. Invocation=null, IsReady=false, InputOwnershipTransferred=false이고 InputStatus/InputCleanupStatus/RegistrationStatus/SdkStatus는 모두 null입니다. 입력·대상 Dispose도 하지 않으며 원래 소유자 계약을 유지합니다. 선행 identity/bundle 오류는 기존 SdkStatus 값을 가질 수 있지만 이는 SDK 조회 결과가 아닙니다.

같은 plan/bundle은 유효 시도에서 소모되므로 재진입·새 wrapper·내부 기계 경로로 같은 객체를 재무장하지 않습니다. 인자/plan 단계 거부와 pre-cancel의 기존 우선순위도 유지합니다. 이 소모는 메모리 객체의 software attempt이며 실제 OEM 호출 횟수나 소비된 실기 승인·persistent 예약의 소모/복원이 아닙니다.

새 승인 bool·빈 registry·None supplier·가상의 Ready 분기·runtime override는 추가하지 않았습니다. 실제 고정 요청을 검토한 뒤 코드를 변경해야 이 진입점이 열릴 수 있습니다. 그 명세도 실기 실행 승인을 대신하지 않으며 옛 소비된 승인을 재사용하지 않습니다. 명세 부재를 runtime 표식 하나로 메우지 않습니다.

## 저장 근거와 아직 필요한 실제 명세

| 시작 조건의 묶음 | 유지한 긍정 근거 | 실제 명세에 남는 연결 |
| --- | --- | --- |
| 경로·고정 대상·읽기 의미 | [별도 저장 byte reader](EC_READBACK_AND_WINDOWS_BRIDGE.md)는 조건부 EC 해석에서 대상을 읽고 응답만 갱신합니다. 모드 저장값과 실제 충전 적용은 별개입니다. | 실제 고정 요청과 선택 reader/대상의 대응 및 모델·BIOS 범위를 정해야 합니다. opaque frame 구조·참조 identity·SDK Ready만으로 대체하지 않습니다. |
| 공유 입력·재사용 보호 | [선택 worker의 inline 입력 소비·영역 분리](SHARED_CHANNEL_COORDINATION_UPDATE.md), [주소 성분 소비와 알려진 ISR 보존](EC_QUERY_INPUT_AND_CLEANUP_REVIEW.md), [미게시/ready/게시 후 오류 구분](WMI_ACPI_RETURN_AND_EC_REUSE_REVIEW.md)은 유지합니다. | 관련 참여자의 command/address 안정성·입력 준비~응답 회수 보호·마지막 결과 쓰기/clear와 다음 게시의 재사용 규약을 적용해야 합니다. |
| 관련 완료·결과 분류 | [송신 오류 가림과 stale 복사](EC_FRESHNESS_AND_ERROR_PATHS.md), 기존 call-exit/terminal/capture·lease/입력 정리 대기 구현은 유지합니다. | 적용 가능한 관련 종료 계약과 귀속·신선함이 불명인 결과를 수용하지 않는 규칙을 고정해야 합니다. terminal이 반드시 도착한다거나 모든 응답이 반드시 신선하다는 보장은 요구하지 않습니다. |

현재의 첫 차단은 실제 고정 요청 명세 부재입니다. 뒤의 조건이 이미 충족됐다고 표시하지 않습니다. 새 source edge·현재 firmware 이미지/실행 관측을 확보한 분석도 아닙니다. live EC 전체 hash·모든 writer/IRQ 부재·독립 SDK 정리 전체 종료·동결 mapper 재검토를 새 필수조건으로 추가하지 않았습니다.

기본 A의 gate는 초기 닫힘/현재 미관측입니다. gate-open 실측을 새 절대 시작 조건으로 삼지 않으며 값이 안 나올 수 있다는 유용성 제한을 유지합니다. handshake·초기화·재시도·설정 쓰기·B fallback은 0입니다. B의 gate 상태 변경이나 옛 실기 승인 범위를 이번 변경으로 허용하지 않습니다.

## 중단 조건과 현재 구현의 범위

| 단계/관측 | 적용할 중단·분류 |
| --- | --- |
| 현재 공개 entry의 ReadSpecificationUnavailable | 이 entry는 SDK 미진입으로 종료하며 추가 호출·fallback·객체 Dispose 없음. driver 부재/보호 기능 부재 판정 아님 |
| 기존 기계 경로의 gate 접근 거부·시간 초과·abandoned·불명 소유권 또는 admission 전 stop | 해당 실제 상태의 기존 owner 규약으로 하위 진입을 막고 필요한 소유권 정리를 기다림 |
| SDK 진입 뒤 throw·UI timeout·caller stop·terminal 유실 | 적용 가능한 terminal/capture·call-exit의 관련 종료가 불명이면 Unknown/보유를 유지하고, 알려진 경우 기존 완료 규약대로 정리를 기다림. throw·UI timeout·stop 자체나 취소 알림/faulted Task를 provider 종료로 바꾸지 않음. 추가 요청·조기 해제 없음 |
| 정상 API 완료 뒤 구조/허용 값/귀속/신선함이 불명 | 판정불가로 끝내고 추가 호출 없음. ACK·FF·echo·보존 tail·잔량만으로 저장 모드/충전 적용 성공을 만들지 않음 |

기존 FrameExchange의 TransportFailure는 여러 원인을 합칩니다. 그 값 하나만 보고 gate 거부·SDK 미진입을 새로 추론하는 classifier는 추가하지 않았습니다. 구조상 유효한 frame도 여전히 IsHardwareObservation/CanRead/Write/Invoke=false입니다. 현재 공개 entry는 앞 단계에서 끝나므로 실기 frame 분류나 적용 성공을 관측한 결과가 없습니다.

## 내부 연결 검증과 API 변경

이전 공개 entry의 기계적 SDK 연결은 `internal PrepareSdkBindingAsync`로 옮겨 기존 SDK stand-in 회귀를 이어갑니다. 실제 보호 읽기 허가를 나타내는 경로는 아닙니다. 공개 entry에서 이 내부 경로로 fallback하는 코드는 없습니다. 기존 generic supplied-delegate API는 유지하므로 시스템 전체의 SDK 사용을 금지하는 보안 경계로 표시하지 않습니다. 앱은 새 SDK 경로를 사용하지 않아 기본 Unsupported 동작·배포 ZIP은 그대로입니다.

기존 성공 hook의 assertion이 fake terminal 전에 실패하면 Unknown 대기 때문에 시험이 끝나지 않을 수 있다는 읽기 검토 지적도 반영했습니다. hook은 인수를 기록하고 합성 terminal을 공급하며 assertion은 Run 정리 뒤에 수행하도록 고쳤습니다. 이는 테스트 harness 보강이며 실제 제품 실패 재현이나 실기 terminal 보장이 아닙니다.

새 공개 entry 회귀 8개 포함 **전체 617개 통과·실패 0·skip 0**입니다. valid opaque payload·SDK getter poison·구조 인자/plan/identity/취소 우선순위·same plan/bundle 재사용·public→internal의 같은 인스턴스 재무장 거부·입력 미인계·동시 시도를 검증했습니다. 기존 binding 12개/수명 7개는 internal seam으로 적응했으며 이 19개가 공개 entry의 허용을 검증했다는 뜻은 아닙니다.

Windows production 소스 8개와 Core를 SDK stand-in과 실행했고 기존 synthetic 요청만 사용했습니다. 실제 System.Management runtime/provider/노트북 호출은 실행하지 않았습니다. 전체 솔루션은 실제 net48 참조 Release 빌드 **경고 0·오류 0**입니다. 새 외부 자료나 의존성은 받지 않았으며 정적 근거 재사용을 테스트 수에 합산하지 않았습니다. [정제 기록](reports/read-trial-entry-conditions-audit.json)에 검증 소스 해시와 실행 범위를 보관합니다.

이번에는 실제 WMI/OEM·하드웨어/Global 객체·삼성 원본·사용 완료된 예약·드라이버/서비스/보안/펌웨어·클라우드 환경에 접근하거나 변경하지 않았습니다. 새 실행 파일·노트북 재시험·동일 자료 제출은 필요하지 않습니다.

다음 작업은 위 세 묶음을 실제 고정 읽기 명세에 대응시키는 근거를 좁히는 일입니다. 이미 구현한 SDK 연결이나 같은 metadata/FF를 다시 세는 작업은 실행 허가 근거가 아닙니다. 검토된 명세가 생기기 전에는 공개 entry의 차단을 유지합니다.
