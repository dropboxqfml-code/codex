# 고정 조회의 대상·자원 보호·SDK 적용 검토 — 2026-11-08

**저장된 모드 byte를 읽으려는 근거와 적용 범위를 좁혔습니다. 실제 보호값 조회·충전 제어는 여전히 Unsupported이며 실기 연결은 보류합니다.** [통합 명세](FIXED_READ_TRIAL_SPECIFICATION.md)의 대상 적합성, 관련 자원의 보호 순서, SDK 수명을 각각 기존 원본·참조 문서·생산 코드에 대응시켰습니다. 실제 요청·주소 조합·frame·generator·backend 활성화는 없습니다.

## 보호 저장값의 의미와 근거 계보

조건부 EC 해석에서 초기화, 설정 writer, 상·하한을 사용하는 충전 정책 consumer가 같은 보호 모드 저장 cell을 참조합니다. generic reader는 이 저장값의 XDATA 영역을 읽는 후보이며, CODE 영역의 버전·상수 anchor를 RAM 값처럼 읽는 안이 아닙니다. 두 주소 성분의 소비 순서와 sample 반환 자리는 기존 byte 계약을 재사용합니다. source/model을 합성한 결과이지 현재 노트북에서 해당 reader를 실행한 관측은 아닙니다.

설정 writer는 이전 모드와 **달라진 새 값이 1인 경우**에 80/75 임계값을 기록합니다. 이미 1이면 임계값을 다시 쓰지 않는 분기가 있습니다. 따라서 향후 올바른 저장값 후보 `1`을 얻더라도 다음을 구별해야 합니다.

| 결과 항목 | 단일 mode byte로 말할 수 있는 범위 |
| --- | --- |
| 저장된 모드 | 입력·귀속·형식 계약 아래의 후보값 |
| 현재 상·하한이 80/75인지 | 이 조회로 확인하지 않음 |
| 충전기에 보호 설정이 적용됐는지 | Unknown |
| 전기적으로 충전이 제한되는지 | 이 조회로 입증하지 않음 |

후보값 하나를 `80% 제한 적용됨`이나 검증된 actualMode로 표시할 근거는 없습니다. 임계값 확인을 이유로 A에 읽기 요청을 추가하지 않습니다.

이는 단일 관측값과 아직 입증하지 않은 전역 불변조건의 정보 한계입니다. 정상 setter 경로에서 실제로 임계값이 어긋난 상태에 도달하는 반례를 발견했다는 뜻은 아닙니다.

기존 분석의 초기 32/32 exploratory bank 모형과 후속 동결된 48/16 모형을 같은 검증으로 합산하지 않습니다. 현재 해석은 후속 48/16 모형과 그 role anchor를 따릅니다. 같은 byte를 다른 decoder로 읽은 검산도 독립적인 제조사·실기 증거가 아닙니다. 버전·reset·USB 등 서로 다른 역할의 anchor는 그 조건부 해석을 지지하지만 공식 칩 정의나 현재 EC 이미지의 관측을 대신하지 않습니다. P04/P05 비교를 EC payload 동일성 검증으로 추가 계상하지도 않습니다.

이는 근거 계보의 정리이며 새 firmware 불일치 발견이나 bank 모델 재분석 요구가 아닙니다. 기존 CandidateProfile의 BIOS/원본 provenance와 현재 모델 적용 가정을 구분해 유지합니다. 전체 live hash나 같은 자료의 재제출을 새 조건으로 두지 않습니다.

## 실제로 공유하는 자원 구간

정상 proxy 설치·정상 private Runtime wrapper/backend 선택이라는 기존 조건에서, 알려진 Runtime EC 접근은 private 변수 처리에 중첩된 flash hook으로 이어집니다. host 인수 준비부터 반환까지 전부 같은 SMM stream에서 실행돼야 한다는 요구로 넓히지 않습니다.

| 선택 source 구간 | 자원 역할과 적용 |
| --- | --- |
| host proxy의 mask 저장·복원 | 두 legacy PIC mask port를 사용합니다. 알려진 EC indexed port와 다르며 SABI 공통 owner의 증거도 아닙니다. |
| 문자열 길이·인수 복사·retained status 읽기 | 선택 본문은 일반 memory 작업이고 직접 indexed I/O가 없습니다. 정상 retained RAM·pointer·범위·공유 buffer 게시 전제를 유지하며 전역 무부작용으로 부르지 않습니다. |
| host/non-SMM arm의 transport 선택 | nonnull 통신 method 또는 별도 legacy SMI 전달 경계입니다. provider 반환·status 읽기만으로 EC 미게시·완료·reader 신선함을 판정하지 않습니다. |
| 같은 proxy의 private SMM forwarding arm | host arm과 구별합니다. private 변수를 부르는 이 arm을 별도의 direct-host indexed 게시자로 세지 않습니다. |
| private Runtime에 중첩된 알려진 EC hook | 조회와 같은 indexed 자원을 실제로 공유하는 조건부 source 구간입니다. 이 관련 접근의 마지막 indexed I/O까지 적용 가능한 보호 순서가 필요합니다. |

통신 제공자는 이 사슬의 전달 경계입니다. 불명 본문을 별도의 숨은 EC actor로 추가하거나 반대로 모든 I/O가 없다고 단정하지 않습니다. 정상 NULL cache legacy의 같은 root 순서 근거와 초기화 완료·비재진입의 같은 실행 stream에 대한 긍정 근거는 그대로입니다. 정상 proxy 분기에 초기 host Runtime 함수를 동시에 남기지 않습니다.

이 분류는 **보호가 필요한 구간을 한정한 결과**입니다. nonnull 표준 통신의 실제 선택 handler가 조회와 같은 보호 순서에 귀속됐다는 근거를 새로 확보한 것은 아닙니다. 제공자 기계코드 자체를 유일한 해법으로 강제하지 않으며, 플랫폼의 적용 가능한 순서 계약이나 해당 자원 소유권 근거로도 연결을 설명할 수 있습니다. 바깥 WM00의 입력 저장~최종 frame 회수에는 기존 whole-exchange 협력 규약이 별도로 적용됩니다.

## SDK의 코드·문서·실제 실행을 구분

고정 plan은 metadata의 MethodID=1과 대상 사실을 비교합니다. 실제 SDK 호출은 숫자 ID를 인수로 넘기는 방식이 아니라, 같은 target/observer/parameters로 이름이 고정된 `CallSabiFunction`의 async overload에 진입하는 방식입니다. metadata 검사와 실행 API를 혼동하지 않습니다.

| 근거 층 | 확인한 범위 | 확대하지 않는 결론 |
| --- | --- | --- |
| 현재 Core/Windows 코드 | 같은 시도의 입력·대상 결합, 호출 stack 반환·해당 terminal·선택 capture join, 관련 정리 뒤 입력/owner 해제 | SDK/provider의 실제 내부 활동이나 현재 Windows 동작을 실행 검증한 것은 아님 |
| cached .NET Framework 4.8 참조 문서 | 실제 대상 API의 async overload·observer/event·Completed.Status·NewObject·Dispose 설명 | XML API 설명을 native 참조 수명·이벤트 구현 본문·실제 완료 관측으로 바꾸지 않음 |
| 기존 cached v8 대표 구현 | 기존 이벤트 snapshot·sink 제거·관리 wrapper 처리의 참고 | .NET48의 구현 동일성이나 현재 노트북 실행 증거가 아님 |
| 향후 해당 method의 실제 SDK 적용 | 전용 observer의 귀속, 외부 mutation/Dispose/독립 dispatch 배제, 적용되는 정상 terminal·late 객체 정리 계약 | 취소·throw·UI timeout으로 정상 완료나 provider 정지를 새로 생성하지 않음 |

`Completed.Status`는 비동기 operation status이며 method의 `ReturnValue`와 같은 항목이 아닙니다. 현재 binding은 둘을 합쳐 성공 계약으로 추론하지 않습니다. 새 method 반환 의미를 만들어 넣지 않으며, 정상 mapper·method 입출력 계약의 기존 적용 범위를 유지합니다. SDK 참조 XML을 확보한 것으로 실제 보호 설정 조회가 실행된 것은 아닙니다.

## 판정과 다음 적용 지점

| 항목 | 이번 판정 |
| --- | --- |
| 고정 저장값의 목적·주소 공간·조건부 모델 근거 | 기존 source로 대응 가능. 독립 증거 계보와 저장 후보의 해석 한계를 명시 |
| host proxy 전체를 EC 경쟁 구간으로 취급할 필요 | 없음. 정상 조건의 실제 공유 footprint인 private Runtime hook으로 한정 |
| SDK 입력·완료·정리의 생산 코드와 대상 API 문서 | 대응 확인. 실제 Windows/provider 실행과 내부 구현 동일성은 별도 |
| nonnull 통신의 관련 indexed 접근을 동일 보호 순서에 귀속 | 이번에도 새 실제 경로 연결은 확보하지 못함 |
| 실제 요청 생성·공개 entry·실기 빌드 | 보류. `ReadSpecificationUnavailable`, 조회·제어 `Unsupported` 유지 |

다음에 필요한 구체 근거는 **이 관련 private Runtime hook의 indexed 접근을 조회와 같은 보호 순서로 연결하는 적용 가능한 플랫폼/경로 계약**입니다. 그 근거를 source·소유권·정상 실행 영역 중 어디에서 얻을지 평가하며, 같은 GUID/operand 검색이나 이미 확인한 copy/reader 검산을 반복 성과로 세지 않습니다. 전체 writer/IRQ 부재·live gate-open·새 노트북 수집을 추가하지 않습니다.

## 검증과 변경 범위

대상 근거 crosswalk, SDK/API 문서 crosswalk, root의 한정된 proxy 자원 분류 검산과 독립 읽기 검토를 수행했습니다. [정제 기록](reports/fixed-read-applicability-audit.json)에 source·참조·검산 artifact의 pin과 한계를 남깁니다. 기존 source를 재사용한 역할 합성이며 새 provider/실제 typed dispatch 연결·실기 race 관측은 0입니다. 검사 수는 서로 겹치고 앱 테스트나 firmware 분석률이 아닙니다.

C#/SDK/test source·프로젝트·노트북용 EXE/ZIP은 변경하지 않아 이번 빌드·C# 회귀는 재실행하지 않았습니다. 628개 통과·전체 net48 Release 경고/오류0은 `ae8f8e7`의 이전 기록입니다. 실제 WMI/OEM/하드웨어/Global 객체·과거 소모 예약 접근, 삼성 원본 실행·로드·에뮬레이션, 드라이버/서비스/보안/펌웨어·클라우드 환경 변경은 없습니다. 추가 노트북 실행이나 동일 자료 제출은 필요하지 않습니다.
