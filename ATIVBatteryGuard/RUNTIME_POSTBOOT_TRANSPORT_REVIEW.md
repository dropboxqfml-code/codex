# Runtime의 부팅 후 중계 선택과 조회 순서 — 2026-11-08

**관련 자원 구간 후속:** [적용 검토](FIXED_READ_APPLICABILITY_REVIEW.md)는 정상 proxy의 PIC mask/일반RAM staging/status와 실제 private Runtime hook의 EC indexed footprint를 구분했습니다. 전체 host 처리의 SMM 귀속을 요구하지 않으며 통신 경계를 별도 숨은 actor로 중복 세지 않습니다. 관련 hook의 동일 보호 순서 근거와 실제 제공자 source edge는 새로 확보하지 못했습니다.

**PI 계약 적용 후속:** [출처·계약 검토](PI_COMMUNICATION_CONTRACT_REVIEW.md)에서 공식 헤더와 대표 구현을 확보했습니다. 아래 실제 제공자 source edge는 여전히 미연결이지만 기계코드 복구만을 유일한 해법으로 고정하지 않습니다. 정상 통신 적용 가정과 관련 indexed 자원의 동일 보호 순서 근거를 구분하며 [조회 명세](FIXED_READ_TRIAL_SPECIFICATION.md)는 조건부 검토본입니다. 실제 entry·배포물은 변경하지 않았습니다.

**후속 후보 조사:** [제공자 후보·역방향 검토](COMMUNICATION_PROVIDER_CANDIDATE_REVIEW.md)는 Base2 동적 method0을 InSmm으로 제외하고, operand 후보와 index 밖 자료를 대조했습니다. 실제 표준 제공자→typed dispatch는 찾지 못했으며 해당 수신자가 쓰지 않는 incoming buffer와 retained buffer의 동일성을 추가 조건으로 요구하지 않습니다. 아래는 부팅 경로 검토 시점 기록입니다.

**선택된 부팅 분기에서 중계 설치 알림을 이미지 실행 전에 처리할 소스 연결을 확보했습니다.** 정상 교체가 완료된 분기에 초기 direct-host 게시자를 계속 남는 경쟁자로 동시에 넣지 않습니다. 실제 조회·충전 제어는 Unsupported이며, 제공자 객체의 함수에서 typed SMM dispatch로 이어지는 연결은 미완료입니다.

[응답 거부 명세](FIXED_READ_ACCEPTANCE_SPECIFICATION.md)의 후속입니다. 이번에는 저장된 CORE/NvramSmi/Runtime 원본을 데이터로 읽었습니다. 새 범위는 제한된 부팅 순서 연결과 인터페이스 객체의 공급·선택 수명입니다. 원본 실행·로드·에뮬레이션이나 하드웨어 호출은 없습니다.

## 선택된 이미지 실행 전 알림 처리 지점

기존에 확인한 BDS 고정 함수 목록에서 교체 marker의 게시가 먼저이고, 그 뒤의 선택 continuation이 이미지 실행 경로로 이어집니다. 그 경로는 실제 BootServices의 RaiseTPL 뒤 **RestoreTPL(4)**를 호출한 다음 LoadImage/StartImage를 호출합니다. 다른 선택 continuation에도 같은 낮은 TPL 복귀 지점이 있습니다.

교체 알림은 TPL8에 등록돼 있습니다. 원본 RestoreTPL의 pending mask와 dispatch loop를 대조하면, TPL4로 내릴 때 대기 중인 TPL8 알림이 처리 대상에 포함됩니다. 이미 queue에 들어간 유효한 Event·필요 버퍼·정상 callback이라는 기존 조건 아래, 해당 알림은 그 RestoreTPL이 반환하기 전에 처리됩니다. 따라서 **이 선택 분기는 이후 이미지가 실행되기 전에 교체 callback이 실행될 구체 지점**을 제공합니다. 이미 앞서 처리된 알림을 두 번 실행한다는 뜻은 아닙니다.

이는 모든 Windows 부팅 경로의 증명이 아닙니다. continuation의 조건·실제 진행·등록/신호 성공·Event 수명·버퍼와 host receiver를 전제로 합니다. 다른 StartImage 호출 지점도 있으며, 조사한 StartImage 본문 자체는 이미지가 반환한 뒤 저장된 TPL로 복귀합니다. 그 본문의 복귀를 모든 이미지 진입 전의 TPL4 처리 지점으로 바꾸어 해석하지 않습니다. 현재 노트북에서 선택 분기를 통과했다고 관측한 것도 아닙니다.

## 초기화의 성공 상태와 실제 교체 조건

| 선택 source 경우 | 확인한 의미 |
| --- | --- |
| 버퍼 할당 실패 | 교체 알림 등록 전에 성공 상태 0을 반환할 수 있음 |
| 공유 버퍼 게시 실패 | 역시 등록 전 성공 0의 종료 경로로 합류할 수 있음 |
| 교체 알림 등록 helper 반환 | 그 상태를 교체 성공의 검사로 쓰지 않고 후속 인터페이스 조회 반환으로 덮음 |
| callback에 필요한 버퍼가 있고 host receiver가 유효함 | host SetVariable 슬롯을 proxy로 저장한 뒤 표 CRC를 계산 |
| CRC 계산 실패 | 선택 callback에는 이전 슬롯 저장·복원·오류 후 rollback 분기가 없음. proxy 저장 여부와 유효한 CRC를 가진 사용 가능한 표인지는 별개 |

따라서 모듈 시작의 성공 반환만으로 버퍼 준비·알림 등록·전달·정상 표를 입증하지 않습니다. 반대로 CRC 실패가 초기 direct-host 함수를 복원한다고 추론하지도 않습니다. 이는 원본의 조건부 분기이며 실제 초기화 실패나 제품 오류를 관측한 결과가 아닙니다.

## 정상 교체와 direct-host 예외를 분리

정상 pre-BDS 등록·marker/알림 전달·필요 버퍼/표 초기화와 위 선택 진행 조건을 적용하면 host 슬롯은 proxy로 교체됩니다. 기존 EBS/VA 경로는 초기 host 함수를 복원하지 않으며, 정상 VA 변환은 **당시 슬롯의 현재 함수**를 변환합니다.

이 분기에는 초기 `host SetVariable → flash → indexed post` 경로를 동시에 최종 OS 경로로 남겨 둘 근거가 없습니다. direct-host 경로를 유지하려면 미등록·미전달·구체 초기화 실패·다른 부팅 분기·후속 슬롯 교체 같은 별도 조건을 제시해야 합니다. 모든 다른 writer의 전역 부재를 증명했다는 뜻은 아닙니다.

proxy가 private SMM Runtime을 호출하고 그 코드가 기존 flash receiver를 쓰더라도 caller의 실행 문맥이 host로 되돌아가지는 않습니다. private 표 선택뿐 아니라 그 표에 의도한 변수 wrapper가 게시된 정상 조건도 유지합니다. 초기 private 표의 Unsupported stub을 정상 변수 처리자로 세지 않습니다.

변수 family guard와 SABI의 공통 가입이 미입증이라는 사실을 **정상 proxy 분기의 독립적인 추가 blocker**로 남기지 않습니다. direct-host 예외를 평가할 때에는 그 예외 구간의 실제 보호가 별도로 필요합니다. guard의 mask 의도를 모든 CPU·이미 진행 중인 SMM에 대한 배제로 확대하지 않습니다.

## 캐시된 인터페이스 객체의 실제 선택

| 원본에서 연결한 관계 | 해석 |
| --- | --- |
| 초기 LocateProtocol의 출력 → 캐시 | 호출이 나중에 사용하는 실제 객체 포인터를 같은 슬롯에 받음 |
| 초기 조회 오류 → 같은 조회 helper를 protocol notification으로 등록 | 나중에 제공자가 게시되면 같은 캐시가 채워질 수 있음. 초기 오류만으로 영구 fallback을 추론하지 않음 |
| 호출 시 캐시가 NULL | 이미 연결한 별도 legacy software-SMI fallback 선택. 이 helper 안에서는 재조회하지 않음 |
| 호출 시 캐시가 nonnull | 그 실제 객체를 This로 전달하고 method0 호출 |
| nonnull 제공자 호출의 반환 | 상태별 검사 없이 legacy 구간을 건너뜀. 제공자 오류가 자동 fallback이나 재시도를 뜻하지 않음 |
| VA callback | 같은 캐시의 객체 포인터를 조건부 변환. method0의 구현이나 새 전송 경로를 선택한 증거는 아님 |

캐시의 소스 초기 값이 NULL인 것은 현재도 NULL이라는 증거가 아닙니다. 제공자 반환 상태나 이후 shared status만으로 typed handler가 실행됐다고 판단하지도 않습니다.

## 남은 순서 연결의 정확한 위치

| 조건부 부팅 후 경로 | 현재 판정 |
| --- | --- |
| 정상 proxy 설치 + NULL 인터페이스 + 정상 legacy 수신/private 변수 초기화 | 기존에 연결한 같은 정상 SMM root의 순서 근거 적용 가능 |
| 정상 proxy 설치 + nonnull 인터페이스 | 실제 공급된 객체의 method0 구현에서 해당 typed GUID dispatch로 가는 source 연결이 미확정 |
| 교체 조건 미충족으로 direct-host 경로가 남는 예외 | 해당 예외에 적용할 보호·순서 필요. 정상 교체 분기와 섞거나 현재 활성이라고 단정하지 않음 |

알려진 server의 등록·메시지 GUID 일치·private 변수 core는 재사용한 근거입니다. 그 사실을 아직 찾지 못한 실제 제공자 함수의 호출 edge로 대신하지 않습니다. legacy Communicate의 별도 객체·record·queue 경로도 표준 인터페이스 객체의 method0과 합치지 않습니다.

다음 소스 목표는 **LocateProtocol이 공급하는 구체 객체와 method0의 구현을 실제 typed dispatch에 연결하는 것**입니다. 같은 GUID 개수 검색·초기 direct 경로의 반복 검산·미관측 live 포인터를 새 절대조건으로 만드는 작업으로 넓히지 않습니다. 호출 준비나 승인된 실기 시험으로 진행한 결과는 아닙니다.

## 검증과 변경 범위

선택 부팅 경로 검산은 원본 3개 pin, 명령 37개, 제한/짧은 본문 decode 148행, typed/list 관계 7개, 합성 관계 10개를 통과했습니다. 객체 경로는 source 49행과 같은 캐시 참조 5개, root는 별도 원본 decode 46개·재사용 phase block 14개·mask/분기 관계 10개를 검산했습니다. 독립 읽기 검토와 [정제 기록](reports/runtime-postboot-transport-audit.json)에 범위·해시를 남깁니다.

숫자는 서로 겹치며 앱 테스트·고유 발견·firmware 분석률로 합산하지 않습니다. 새로 좁힌 부팅 순서 연결은 1개이고 새 firmware 함수·게시자·실제 race 발견은 0입니다. 실제 제공자→typed dispatcher 연결을 새로 닫은 수는 0입니다. 선택 부팅 경로 분석 중 선택적인 PE metadata 조회가 AttributeError로 끝난 기록은 증거에서 제외했으며 최종 검산기는 통과했습니다.

C#/SDK/프로젝트·앱·기존 EXE/ZIP은 변경하지 않아 빌드/C# 테스트는 재실행하지 않았습니다. 617개·빌드 경고/오류 0은 62f2d2e의 이전 기록입니다. 공개 ReadSpecificationUnavailable·조회/제어 Unsupported를 유지합니다. 실제 SDK/OEM/하드웨어/Global 객체·과거 소모 예약 접근, 원본 실행·로드·에뮬레이션, 드라이버/서비스/보안/펌웨어·클라우드 환경 변경, 실행용 요청·주소 조합·frame·nonce/생성기 추가는 없습니다. 새 노트북 실행·자료 제출도 필요하지 않습니다.
