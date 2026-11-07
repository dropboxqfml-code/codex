# 고정 보호 모드 1회 읽기 시험 판정 — 2026-11-07 한국 시간

**판정: 조건부 비실행 시험안 검토 가능, 실제 backend 연결·실행은 보류.** [SDK 호출 수명 계약과 private 증명](SDK_INVOCATION_LIFETIME_REVIEW.md)을 반영했습니다. 정상 평가·반환은 모델 대응 가정 아래 동결하고, 실제 SDK의 불명 dispatch·관련 참여 규약·선택 안의 유용성을 별도로 남깁니다. 하드웨어 영구 미지원이나 드라이버 부재 판정은 아니며 실제 충전 제어는 Unsupported입니다.

| 조건 | 확인된 범위 | 남은 조건 |
| --- | --- | --- |
| 같은 자원의 software admission | 내부 identity·미완료/취소·peer 보호와 Bound의 direct throw/null provenance를 검증. owner가 resource+gate 양쪽 격리 | 실제 SDK 내부 오류가 이미 ordinary async fault가 된 경우까지 판정하지 않음. 직접 호출·임의 alias 전체를 막지 않음 |
| 외부 협력 잠금 | lazy adapter·owner thread 해제·취소/abandon 격리 검증. 알려진 OEM4개의 정상 Call은 전체 교환 구간 보호 | 선택 OEM allocation 예외의 함수내 unwind에는 mutex guard 없음. 상위 처리·현재 참여/권한·상호 운용은 미관측 |
| 관련 하위 완료 | 기존 정상 Backend는SDK정상반환+선택completion을기다림. private proof에서call exit/관련terminal/capture3축과unknown때lease·slot보존을검산 | 참조SDK음수상태가sink를제거해late terminal을보장하지않음. 실제adapter의terminal출처/소실정책·프로세스수명은private상태모델만으로확정되지않음 |
| 기존 EC 작업 입력 보존 | 식별된 입력은 요청 반환 전에 inline 소비하고 query upload·reader 쓰기와 분리됨 | 조회 자원과 교차하는 구체 근거가 생긴 IRQ/status만 조사. 전체 생산자 발견은 비실행 제안의 필수조건 아님 |
| 선택 실행 영역·gate·결과 귀속 | WMI→AML→PCH legacy SW→SABI generic 경로 연결. 별도 typed 변수 경로와 분리. gate는 초기닫힘/현재미관측 | 관련 게시자 순서·전체 교환·응답 귀속 필요. handshake0의 유용성 미확정. 다른 기능 caller의 사전 handshake를 보호 조회 지원으로 확대하지 않음 |

모델·BIOS·제조사 원본과 여러 해석 anchor는 임시 CandidateProfile 근거로 유지합니다. live 함수 포인터·EC 전체 hash를 직접 관측하지 못했다는 사실 하나만을 절대 중단 조건으로 쓰지 않습니다. 동시에 위 실제 미완료 연결을 정상성 가정이나 사후 내용 비교만으로 메우지 않습니다.

Global 접근 권한을 별도 사전 수집하는 것도 절대 조건은 아닙니다. 유한 Acquire가 접근 거부로 끝나면 하위 호출 없이 실패할 수 있습니다. 조회 진입 자체의 typed provider 발견도 필수조건에서 제외합니다. 남는 것은 gate를 포함한 선택 안의 유용성·관련 참여와 마지막 접근/재사용·입력 비훼손·응답 귀속이며, 별도 Runtime 경로는 실제 관련 게시자 조건으로만 평가합니다.

이전 fc14fea 수정은 wrapper 유무에 따라 달라지던 보수 정책을 일치시켰습니다. 당시 새6회귀 포함469개와 전체 Release 빌드 경고/오류0을 검증했습니다. quarantine이나 lease 해제가 공급자의 실제 작업을 중단시키지는 않으며, 실제 backend·기존 예약·시험 횟수는 변경하지 않았습니다.

위469개는fc14fea의검증기록입니다. 후속private시험은8case/48검산·시험build0이며앱/Core/API를변경하지않았습니다. unknown진단과actual-end Task를분리해조기해제를막는계약은검산했지만,SDK가제거한terminal을새로만들거나실제종료를증명하지는못합니다. terminal미수신은pending으로남고시험finally의합성cleanup은실기근거가아닙니다.

세부 WMxx/Arg2 매핑의 공식 원문 미확보만을 별도 blocker로 세지 않습니다. 정상 mapper와 보존된 모델 선언의 대응 가정을 유지하고, 새 원문·provider 코드·관련 trace·반례가 생길 때만 정상 반환 항목을 다시 엽니다. 내부 미게시 분기가 존재해도 외부 FF만으로 실제 미게시를 식별할 수 없고, SDK dispatch 예외의 faulted Task는 종료 증거가 아닙니다.

비실행 제안에는 지금의 조건부 모델·프로파일·미관측 사항을 명시하면 됩니다. 실제 연결 전 조건은 선택 경로/대상/gate, 관련 전체 교환 소유권, 관련 완료/입력 비훼손/결과 분류의 세 묶음입니다. 동결된 status 후보·같은 GUID/내용 비교를 반복해 준비 완료로 승격하지 않고, 미확인 status 생산자 전체를 단독 중단 조건으로도 쓰지 않습니다.

[현재 기본 안 A](FIXED_MODE_READ_PROPOSAL.md)는 최대1WMI 읽기 시도·고정 대상 byte 샘플0~1회·handshake/초기화0회입니다. 별도 비실행 대안 B는 사전에 정한 handshake1회와 조건부 읽기1회, 최대2method이며 공유 gate의 image-data 상태 변경을 명시했습니다. B는 A 실패 후 fallback이나 승인된 실행이 아닙니다. 임의 입력·재시도·설정 쓰기·사후 reset은 없고 gate/FF/echo/귀속 불명은 판정불가입니다. 실제 코드/실행 승인은 별도이며 사용 완료된 과거 단발 예약은 확인·초기화·삭제·재사용·우회하지 않습니다.

이번 판정에 따라 사용자에게 새 실행이나 자료 제출을 요구하지 않습니다. [비실행 설계와 조건표](FIXED_MODE_READ_PROPOSAL.md)는 이 판정을 기준으로 유지합니다.
