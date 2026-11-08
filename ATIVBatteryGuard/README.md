# ATIV Battery Guard

**최신 — 조회 시험 전 오프라인 리허설 / 2026-11-08:** [시험·기록 계획](READ_TRIAL_REHEARSAL_PLAN.md)과 테스트 전용 `--offline-rehearsal`을 추가했습니다. 실제 checkpoint를 정제 JSON에 남기며 시간 초과 시 보유 상태와 가짜 정리 뒤 결과를 구분합니다. 6시나리오 통과·새11개 포함 전체628개 통과, 테스트/전체 net48 Release 빌드 경고·오류0입니다. 6개 리허설은 전체 회귀와 겹치며 실제 OEM/System.Management 호출은0입니다. 제품 코드·배포 ZIP·공개 entry 차단과 조회/제어 Unsupported는 유지합니다. 아래는 이전 기록입니다.

**최신 — 표준 통신 제공자 후보 조사 / 2026-11-08:** [조사 기록](COMMUNICATION_PROVIDER_CANDIDATE_REVIEW.md)에서 실제 게시 함수와 역방향 호출·index 밖 자료를 대조했으나 제공자→typed SMM dispatch 연결은 확보하지 못했습니다. Base2 method0은 InSmm으로 제외했고 수신자가 쓰지 않는 buffer 인수의 동일성도 추가 요구에서 제거했습니다. 코드·EXE/ZIP 변경 없이 공개 차단·조회/제어 Unsupported를 유지합니다. 아래는 이전 기록입니다.

**최신 — Runtime의 부팅 후 전송 선택 / 2026-11-08:** [정적 검토](RUNTIME_POSTBOOT_TRANSPORT_REVIEW.md)에서 선택된 BDS 분기의 알림 처리가 이미지 실행보다 앞서는 연결을 확보했습니다. 정상 proxy 교체와 초기 direct-host 예외를 분리하고, 제공자 캐시가 NULL일 때만 legacy fallback을 선택함을 확인했습니다. 제공자 오류 뒤 자동 fallback은 없으며 실제 method0→typed dispatch 연결은 미완료입니다. 코드·배포물 변경 없이 공개 차단·조회/제어 Unsupported를 유지합니다. 아래는 이전 기록입니다.

**최신 — 응답 거부 명세와 구체 참여자 범위 / 2026-11-08:** [비실행 명세](FIXED_READ_ACCEPTANCE_SPECIFICATION.md)에 실패·echo·불일치·no-copy 거부와 조건부 내용 충돌 모델을 정리했습니다. 14사례·256추상 관측 조합의 검산은 앱/실기 테스트가 아닙니다. 같은 자원으로 연결된 host Runtime 변수 저장 경로의 순서·보호는 미완료입니다. 코드·EXE/ZIP 변경 없이 공개 차단·조회/제어 Unsupported를 유지합니다. 아래는 이전 기록입니다.

**최신 — 입력 보호와 응답 포착 경계 / 2026-11-08 한국 시간:** [정적 검토](FIXED_READ_INPUT_AND_CAPTURE_REVIEW.md)는 ready 이후에도 응답 복사 보호가 필요함을 기존 전송·협력 규약에 연결했습니다. 30바이트 upload/download와 반환 prefix 10바이트의 의미상 포착, 전체 I/O 자원 수명, SMM 밖 WMI frame 회수를 구분했습니다. 실제 경합·새 reader 실행을 관측한 결과가 아니며 공개 entry 차단·조회/제어 Unsupported를 유지합니다. 코드·EXE/ZIP 변경과 새 노트북 시험은 없습니다. 아래는 이전 기록입니다.

**최신 — 고정 읽기 후보의 바이트 계약 대조 / 2026-11-08 한국 시간:** [정적 검토](FIXED_READ_BYTE_CONTRACT_REVIEW.md)는 현재 주소 입력과 반환 sample을 함께 제공할 generic 분기, payload 주소 순서와 실제 보존되는 반환 범위를 좁혔습니다. WMI 끝 4byte는 복원되지 않으며 실패/command-only 응답도 sample 자리가 zero일 수 있습니다. 기존 실패 표시를 무시한 scalar-only 해석을 피해야 하고, 현재 제품 오류나 새 보호값 관측은 아닙니다. 코드·EXE/ZIP 변경·새 노트북 시험은 없으며 public entry 차단·제어 Unsupported를 유지합니다. 617개/빌드 0/0은 이전 검증 기록입니다. 아래는 이전 기록입니다.

**최신 — 실기 읽기 명세 부재 시 SDK 진입 차단 / 2026-11-08 한국 시간:** [조건 적용·검증](READ_TRIAL_ENTRY_CONDITIONS_UPDATE.md)은 공개 SDK 시험 entry가 ReadSpecificationUnavailable로 끝나도록 변경했습니다. 형식이 맞는 임의 요청도 SDK 조회·입력 인계·등록·호출을 시작하지 않습니다. 기존 SDK 기계 연결은 내부 대역 시험으로 유지합니다. 새 8개 포함 617개 통과·전체 Release 빌드 경고/오류 0입니다. 실제 보호 조회·충전 제어는 Unsupported이며 하드웨어 영구 미지원 판정은 아닙니다. 앱/배포물 변경이나 새 노트북 실행·자료 제출은 없습니다. 아래는 이전 기록입니다.

**최신 — 고정 SDK 대상·관찰자·입력 연결 / 2026-11-08 한국 시간:** [구현·검증](WINDOWS_WMI_SDK_DISPATCH_BINDING_UPDATE.md)은 공급 target의 참조·연결된 local scope·instance/class를 확인하고 같은 observer/입력으로 typed async 메서드에 최대 한 번 진입하는 경로를 구현했습니다. borrowed target과 owned 입력의 기존 정리 대기는 유지합니다. 새 19개 포함 609개 통과·전체 Release 빌드 경고/오류 0입니다. 실행 검증은 SDK 대역이며 실제 노트북 호출·보호 조회 명령/template·앱/배포물 변경은 없습니다. 보호 조회·충전 제어는 Unsupported이고 새 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 입력 객체를 관련 종료까지 보유 / 2026-11-08 한국 시간:** [구현·검증](WINDOWS_WMI_OWNED_INPUT_LIFETIME_UPDATE.md)은 입력 준비의 소유권을 기존 Run/Close 경로에 연결했습니다. Unknown·취소·보고 예외로 입력을 먼저 해제하지 않고, 입력이 출력으로 돌아온 경우도 중복 정리를 막습니다. 새 18개 포함 590개 통과·전체 Release 빌드 경고/오류 0입니다. 실제 SDK 호출·보호 조회 명령·앱/배포물 변경은 없고 충전 제어는 Unsupported입니다. 새 노트북 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 저장 읽기 근거 대조·SDK 입력 준비 / 2026-11-08 한국 시간:** [검토·구현](WINDOWS_WMI_INPUT_PREPARATION_REVIEW.md)에서 공급된 입력 객체를 검사하고 고정 frame을 Bytes→inData 순서로 할당하는 단계를 분리했습니다. 일부 변경 뒤 오류가 나도 같은 객체는 재사용하지 않습니다. 신규 10개 포함 572개 통과·전체 Release 빌드 경고/오류 0입니다. 저장 byte reader의 읽기 의미는 조건부 근거로 유지하며 실제 조회 명령·SDK 호출·앱/배포물 변경은 없습니다. 보호 조회·충전 제어는 Unsupported이고 새 노트북 시험·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 단발 대상·요청·준비 경로 결합 / 2026-11-08 한국 시간:** [구현·검증](SINGLE_READ_PLAN_BINDING_UPDATE.md)은 A의 공급 사실 scope와 고정 요청을 묶어 준비 전에 거부/동결하고, Run에서 command/payload를 다시 받지 않습니다. 같은 plan의 재준비·fallback을 막고 software handoff1회를 검사합니다. 신규21개 포함562개 통과·실제 net48 참조 전체 Release 빌드 경고/오류0입니다. 실제 보호 read template·SDK 호출·승인이나 앱/배포 ZIP 변경은 없으며 제어는 Unsupported입니다. 새 노트북 실행/재제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 세션 시작 전 WMI 등록 준비 / 2026-11-08 한국 시간:** [구현·검증](WINDOWS_WMI_PREPARATION_UPDATE.md)은 등록/취소/실패 정리 뒤에만 단발 실행 handle을 반환합니다. Run/미사용 닫기를 한 번 결정하며 실제 호출의 Unknown은 기존 잠금·구독 대기를 유지합니다. 새15개 포함541개 통과·실제 net48 참조 전체 Release 빌드 경고/오류0입니다. 실행 검증은 SDK stand-in이며 실제 OEM 호출·앱 연결·배포 ZIP 변경은 없습니다. 보호 조회/제어 Unsupported·새 노트북 실행/재제출 불필요입니다. 아래는 이전 기록입니다.

**최신 — Windows WMI 타입 검사·이벤트 연결 / 2026-11-08 한국 시간:** [구현·검증](WINDOWS_WMI_TYPED_BINDING_UPDATE.md)에 공급된 System.Management observer/결과용 library를 추가했습니다. exact byte[]·concrete Dispose와 raw handler/구독 해제 join을 구현했고 새21개 포함526회귀·실제 net48 참조 전체 Release 빌드 경고/오류0입니다. 회귀는 동일 소스를 SDK stand-in으로 실행했으며 실제 SDK/provider·장치 호출·앱 연결·배포 ZIP 변경은 없습니다. 보호 조회/제어 Unsupported·새 노트북 실행/재제출 불필요입니다. 아래는 이전 기록입니다.

**최신 — callback 결과 객체 연결 / 2026-11-07:** [구현·검증](CALLBACK_SOURCE_CAPTURE_UPDATE.md)에서 명시적 dispatch/reader의 객체 선택·bounded 복사·정리를 기존 세션에 연결했습니다. 관련 정리 완료 전 capture를 게시하지 않고 완료 불명은 pending으로 유지합니다. 새15개 포함505개 통과·전체 net48 Release 빌드 경고/오류0입니다. 실제 SDK reader/event adapter·앱 연결·배포 ZIP은 그대로이며 보호 조회/충전 제어는 Unsupported입니다. 새 노트북 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 결과 표시와 host 종료 대기 / 2026-11-07:** [구현·검증](INVOCATION_HOST_LIFETIME_UPDATE.md)에서 세션의 RunAndCloseAsync를 추가했습니다. 결과를 먼저 표시하되 시간 초과·취소·표시 예외 뒤에도 실제 close를 기다립니다. 새6개 포함 전체490개 통과·전체 net48 Release 빌드 경고/오류0입니다. 실제 SDK source·앱 연결·배포 ZIP은 그대로이며 보호 조회/충전 제어는 Unsupported입니다. 새 노트북 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 공통 호출 세션 구현 / 2026-11-07:** [구현·검증](MANAGED_INVOCATION_SESSION_UPDATE.md)에서 단발 snapshot transport와 host 세션을 기존 Bound/owner에 연결했습니다. 완료 불명은 pending으로 유지하고 닫기는 source와 자기/공유 owner 정리를 기다립니다. peer의 조기 close 문제를 재현·수정했으며 새15개 포함 전체484개 통과·전체 net48 Release 빌드 경고/오류0입니다. 실제 SDK source·GUI 등록·하드웨어 호출·배포 ZIP은 그대로이며 제어는 Unsupported입니다. 추가 노트북 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — SDK 호출 수명 계약의 private 증명 / 2026-11-07:** [검토·증명](SDK_INVOCATION_LIFETIME_REVIEW.md)에서 호출 함수 종료·관련 method terminal·선택 capture 완료를 분리했습니다. 가짜 SDK의8case/48검산과 시험 빌드 경고/오류0을 확인했고 unknown 뒤 UI 반환에도 lease/slot이 유지됨을 기록했습니다. 참조 SDK는 오류 때 sink를 제거할 수 있어 늦은 완료를 항상 기대할 수 없습니다. 앱/Core/public API·배포 ZIP은 그대로이며 앱469개는 이전fc14fea 검증입니다. 실제 SDK 종료·보호 조회·충전 제어 성공을 확인한 것은 아닙니다. 추가 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — Bound 전송 직접 실패의 격리 수정 / 2026-11-07:** [수정·검증 결과](BOUND_TRANSPORT_FAILURE_QUARANTINE_UPDATE.md)에서 async Bound가 감추던 transport direct throw/null을 내부 표식으로 보존하고 cooperative owner의 resource/gate 재진입 차단을 복구했습니다. 수정 전 새 회귀4개가 실패했고 수정 뒤 전체469개 통과·전체 Release 빌드 경고/오류0입니다. 실제 반환 task의 정상 fault/cancel·로컬 거부는 기존 의미를 유지합니다. 실제 SDK의 불명 dispatch·provider 중단을 해결한 것으로 확대하지 않으며 앱 등록·기존 예약·배포 ZIP·A/B 시험 범위는 그대로입니다. 실제 제어 Unsupported·추가 실행/자료 제출 불필요입니다. 아래는 이전 기록입니다.

**최신 — 정상 반환 계약·EC 재사용·A/B 비교 / 2026-11-07:** [새 검토](WMI_ACPI_RETURN_AND_EC_REUSE_REVIEW.md)에서 공식 WMI/ACPI 계약과 모델 대응 가정 아래 정상 평가·반환을 조건부로 연결했습니다. EC 미게시·정상 ready·게시 후 오류의 재사용 조건을 구분하고, FF만으로 미실행을 판정하지 않습니다. [시험안](FIXED_MODE_READ_PROPOSAL.md)은 기본 A의1회 읽기/handshake0을 유지하며 별도 B의handshake1+조건부 읽기1 및 공유 gate 상태 변경을 명시했습니다. 두 안 모두 실제 연결 보류이며 앱·배포 ZIP은 그대로입니다. 추가 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 선택 WMI 경로와 완료 계약 / 2026-11-07:** [검토 결과](SELECTED_WMI_ROUTE_AND_COMPLETION_REVIEW.md)에서 조회의 legacy SW 경로와 별도 Runtime 변수 통신을 분리했습니다. 삼성 keyboard/jog caller의 사전 gate 호출 순서를 확인했으며 배터리 지원 근거로 확대하지 않습니다. host WMI 프레임과 EC mailbox, 정상 최종 성공과 클라이언트 취소도 구분했습니다. 비실행 시험안의 초기화 없는 최대 1회 범위는 유지하며 실제 조회·제어는 미구현입니다. 문서·정제 기록만 변경했고 추가 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 완료 경계·조건부1회 시험안 / 2026-11-07 한국 시간:** [새 검토](PROVIDER_COMPLETION_AND_READ_TRIAL_REVIEW.md)에서 선택 snapshot 완료와 다른 managed 정리, SDK/provider/EC 완료를 구분했습니다. private fake 하네스13검사·공개 참조 source6관계를 검산했으며 앱463개 회귀와 합산하지 않습니다. [시험안](FIXED_MODE_READ_PROPOSAL.md)은 초기화/handshake0·최대1WMI시도/고정 대상 byte 샘플0~1회로 구체화했습니다. 비실행 검토는 가능하고 실제 호출은 여전히 보류·충전 제어 Unsupported입니다. 앱/배포ZIP은 그대로·추가 실행/자료 제출 불필요입니다. 아래는 이전 기록입니다.

**최신 — 협력 교환 소유권 구현·조회 시험 보류 / 2026-11-07 한국 시간:** [구현·검증](COOPERATIVE_EXCHANGE_OWNERSHIP_UPDATE.md)에서 전용 owner의 유한 획득 대기·같은 thread 해제·취소/late-acquire·소유권 격리와 lazy 고정 mutex adapter를 추가했습니다. 테스트463개 통과·전체 빌드 경고/오류0이며 fake/unnamed만 검사했고 실제 OEM Global은 열지 않았습니다. 실제 status 생산자 연결은 새로 확보하지 못해 [1회 보호 조회 시험은 보류](FIXED_MODE_READ_DECISION.md)합니다. 앱 등록·OneShot/기존예약·실기호출·기존ZIP은 그대로이고 실제 제어 Unsupported·추가 실행/자료 제출 불필요입니다. 아래는 이전 기록입니다.

**최신 — 공유 채널 재진입 수정 / 2026-11-07 한국 시간:** [수정·검증 결과](SHARED_CHANNEL_COORDINATION_UPDATE.md)에서 같은 channel이나 snapshot transport를 새 래퍼로 감싸 미완료 작업을 우회하던 준비용 전송 조정 코드를 수정했습니다. C#441개 통과·전체 솔루션 빌드 경고/오류0입니다. 선택 EC 입력의 소비 시점도 더 연결했지만 실제 보호 조회·충전 제어는 여전히 미구현·Unsupported입니다. 기존 OneShot/예약·OEM 호출은 변경하지 않았고 현재 앱 흐름·배포 ZIP은 그대로이며 새 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 조회 입력·후처리·응답 귀속 / 2026-11-07 한국 시간:** [후속 분석](EC_QUERY_INPUT_AND_CLEANUP_REVIEW.md)에서 늦은 clear의 작업 상태 생산자, 읽기 주소 소비와 known ISR register 보존, Field Lock과 전체 WMI 교환의 차이를 연결했습니다. [조회 검토안](FIXED_MODE_READ_PROPOSAL.md)은 기존 작업 비훼손과 조회의 안전한 실패를 구분합니다. 실제 보호 조회·충전 제어는 미구현·Unsupported이며 문서·정제 기록만 변경했습니다. 앱·기존 ZIP은 그대로이고 추가 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 부팅 알림·EC 명령 인계 / 2026-11-07 한국 시간:** [후속 결과](EC_READ_HANDOFF_AND_BOOT_ORDER.md)에서 정상 성공 조건의 중계 설치 순서, legacy software-SMI fallback의 같은 SMM root 호출, Runtime/조회의 같은 준비 규약을 연결했습니다. 표준 통신 경로·EC 양쪽 작업 보존·전체 교환의 응답 귀속은 아직 미완료입니다. [고정 조회 검토안](FIXED_MODE_READ_PROPOSAL.md)을 갱신했으며 실제 보호 조회·충전 제어는 미구현·Unsupported입니다. 문서·정제 기록만 변경, 앱·기존 ZIP은 그대로이고 추가 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — Runtime 중계·고정 조회 검토 / 2026-11-07 한국 시간:** [후속 분석](RUNTIME_PROXY_AND_FIXED_READ_REVIEW.md)에서 정상 초기 구성의 flash 선택, 부팅 후 host 변수 함수의 SMM 중계 교체, EC 후크의 flag-only 효과를 연결했습니다. [고정 모드 한 바이트 조회 검토안](FIXED_MODE_READ_PROPOSAL.md)은 비실행 문서이며 실제 호출 준비는 미완료입니다. 통신의 정상 SMM 실행 영역·관련 indexed 접근·다른 작업 보존이 남았습니다. 실제 제어 Unsupported, 앱·기존 ZIP은 그대로이고 추가 실행·동일 자료 제출은 필요하지 않습니다. 원본 실행 시도 1건이 OS에서 차단됐으며 원본 실행·권한 변경·재시도는 없었습니다. 상세 사건 기록은 후속 분석에 있습니다. 아래는 이전 기록입니다.

**최신 — Runtime OS 소비자와 EC 메타데이터 경계 / 2026-11-07 한국 시간:** [새 분석 결과](RUNTIME_VARIABLE_AND_EC_IDENTITY_REVIEW.md)에서 OS 변수 저장 진입점→선택한 NV backend→EC 게시 후크를 조건부 소스 경로로 연결했습니다. SMBIOS EC 필드는 변수에서 채워지며 현재 EC 본문 직접 조회·동일성 증거가 아닙니다. 실제 장치 호출·보호 설정 조회·충전 제어 성공은 미관측이고 제어는 Unsupported입니다. 문서·정적 기록만 변경했으며 앱·기존 ZIP은 그대로입니다. 새 수집·실기·동일 자료 재제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 명령 소유권과 최소 조회 설계 / 2026-11-07 한국 시간:** [후속 검토](EC_COMMAND_OWNERSHIP_REVIEW.md)에서 EC 내부의 대체 poll·포인터 writer, 펌웨어 게시자의 부팅/SMM 문맥, 과거 서비스 WSABI와 현재 세 변형의 협력 잠금을 연결했습니다. 정상 SMM 실행 세대의 순차화 근거와 보호 모드 한 바이트 조회의 설계 조건을 정리했으며, 현재 장치의 안전한 실행 계약은 여전히 미완료입니다. 실제 제어 Unsupported, 앱·기존 ZIP은 그대로이고 새 실행·자료 재제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 조회 간섭 후보의 실제 역할 연결 / 2026-11-07 한국 시간:** [후속 결과](EC_QUERY_INTERFERENCE_REVIEW.md)에서 다른 결과 작성자는 별도 명령 handler, 완료 지우기는 조건부 scheduler 후처리로 연결했습니다. 알려진 ISR 분기·AP 작업·조회 자체의 호출 사슬도 좁혔습니다. 정적 후보에는 유리한 근거이지만 실제 보호 조회·충전 제어 성공은 아니며 공유 명령·대상 무결성은 여전히 미확정입니다. 문서·검사 기록만 변경했고 앱·기존 ZIP은 그대로입니다. 새 실행·자료 재제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 보호 상태 조회 경로의 성립 조건 / 2026-11-07 한국 시간:** [범용 읽기·SMM 동기화 검토](BOUNDED_READ_ROUTE_FEASIBILITY.md)에서 정적 경로의 존재와 현재 장치의 안전한 호출 계약을 구분했습니다. 전용 OEM getter만을 필수 조건으로 두지 않으며 요청 비교가 일부 오래된 응답을 거부할 가능성은 있지만, 결과 생산자·교환 전체의 배제는 미입증입니다. 실제 보호 상태 조회·충전 제어는 미구현이고 Unsupported입니다. 문서·정적 검사 기록만 갱신했으며 앱·기존 ZIP은 그대로입니다. 새 실행·자료 재제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — Amor3 공식 원본 확보·개발 검사 추가 / 2026-11-07 한국 시간:** [새 원본과 검증](AMOR3_OEM_SOURCE_ACQUISITION.md)에서 현재 계열 목록의 SamsungSystemConfiguration 1.0.0.7을 확보하고 오프라인 검사기에 크기·해시 pin을 추가했습니다. Python 88개 통과. 선택한 Monitor 호출은 팬 제어이며 새 보호 조회는 미확보입니다. Windows 앱·기존 ZIP은 그대로, 실제 제어 Unsupported이고 추가 실행·자료 재제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 외부·간접 후보 경계 정리 / 2026-11-07 한국 시간:** [후속 검토](EXTERNAL_INDIRECT_CONTRACT_BOUNDARIES.md)에서 외부 GUID 후보의 공통 구간과 간접 호출·반환 경로를 대조했지만 새 보호 조회 계약은 확보하지 못했습니다. 확인 범위에서 실제 조회 코드를 추가할 근거가 부족해 기능 추가 없이 Unsupported를 유지합니다. 앱·기존 ZIP은 그대로이고 추가 실행·동일 자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 고정 조회 소비자 대조 / 2026-11-07 한국 시간:** [후속 결과](FIXED_QUERY_CONSUMER_REVIEW.md)에서 현재 삼성 전력 조회의 전류·전압 생산자와 숫자 소비자, ACPI 대체 조회의 제공자를 연결했습니다. 보호 상태 조회는 확보하지 못했고 대체 분기의 오류 폐기를 확인했습니다. 목적이 식별된 경로는 보호 조회 후보에서 분리하며 실제 제어는 Unsupported입니다. 앱·기존 ZIP은 그대로이고 추가 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 충전기 응답 조회 후보 / 2026-11-07 한국 시간:** [후속 분석](CHARGER_READBACK_AND_PROJECTION.md)에서 버스 수신 word를 반환하는 코드 후보와 정책 활동값의 상태 페이지 반영을 연결했습니다. 활동 스냅샷은 보호 모드의 직접 미러가 아니며, 범용 버스 조회도 현재 모델의 안전한 Windows 보호 조회로 확정하지 않았습니다. 실제 제어는 Unsupported이고 앱·기존 ZIP은 그대로입니다. 추가 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 오류 보존 조회 경로와 신선도 검산 / 2026-11-07 한국 시간:** [후속 결과](EC_FRESHNESS_AND_ERROR_PATHS.md)에서 첫 오류를 보존하는 별도 조회와 일반 중계의 오래된 응답 가능 조건을 확인했습니다. 별도 조회의 고정 비트 하나는 AC 전원 상태이며 보호 모드와의 연결은 미확정입니다. 기존 Windows DLL의 협력 잠금도 현재 보호 상태 확인이나 가려진 송신 오류 복구를 보장하지 않습니다. 실제 제어는 Unsupported이고 앱·기존 ZIP은 그대로입니다. 추가 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 저장값 조회 후보와 Windows 중계 연결 / 2026-11-07 한국 시간:** [후속 분석](EC_READBACK_AND_WINDOWS_BRIDGE.md)에서 보호 모드 저장값을 읽는 별도 EC 코드 후보와 WMI 공유 버퍼·등록 callback의 연결을 찾았습니다. 기존 삼성 호출자도 같은 형식을 사용하지만 선택한 용도는 LED·키보드이며 배터리 지원 증거는 아닙니다. 응답 신선도·현재 장치 적합성은 미검증이고 실제 제어는 미구현·Unsupported입니다. 앱·기존 ZIP은 그대로이며 추가 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 충전 보호 코드 후보 / 2026-11-07 한국 시간:** [조건부 EC 정적 해석 결과](EC_CHARGE_PROTECTION_CANDIDATE.md)에서 SBS 잔량 생산→80/75 비교→충전 억제·복원 요청을 연결했습니다. 실제 장치 동작·Windows 전달·신뢰할 설정 재조회는 미검증이며 실제 제어는 미구현·Unsupported입니다. 앱·기존 ZIP은 그대로이고 이번 빌드·단위 테스트는 반복하지 않았습니다. 새 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — EC 업데이트 영역 연결 / 2026-11-07 한국 시간:** [분석 결과와 한계](EC_UPDATE_REGION_RESULT.md)에서 미분류96KiB가 업데이트 인터페이스의EC영역에포함됨을실제소비·분류코드로연결했습니다. 충전보호처리자·안전한명령은확보하지못했고현재자료로실제제어구현은막혀있습니다. 아키텍처나칩을추측해제어하지않으며미구현·Unsupported를유지합니다. 앱·기존ZIP은미변경이고이번빌드·단위테스트는반복하지않았습니다. 새실행·자료제출은필요하지않습니다. 아래는이전기록입니다.

**최신 — native SABI 드라이버 검토 / 2026-11-07 한국 시간:** [보유 x64 드라이버의 전달·완료 경로](NATIVE_SABI_DRIVER_REVIEW.md)를 DLL과 대조했습니다. 일반 중계의 완료는 배터리 명령 성공이나 보호 설정 확인이 아니며 새 제어 경로는 확보하지 못했습니다. 명령 인벤토리의 생성자 후보 오분류 6개도 정정했습니다. 앱·기존 ZIP은 유지하고 이번 빌드·단위 테스트는 반복하지 않았습니다. 실제 제어는 미구현·Unsupported이고 새 실행·자료 제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 전송 취소 처리 보강 / 2026-11-07 한국 시간:** [수정 내용과 검증](WMI_CANCELLATION_BOUNDARY_UPDATE.md)에서 채널 취소 callback이 막힐 때 timeout/cancel 결과도 반환하지 못하던 결함을 수정했습니다. 이전 작업과 callback이 모두 끝나기 전 새 요청은 거부합니다. C#437/Python85 통과, 전체 빌드 경고·오류0입니다. 개발 소스를 제공하며 현재 앱의 실제 장치 경로는 변경하지 않습니다. 충전 제한은 계속 미구현·Unsupported이고 새 실행·업로드는 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 과거 P04ACJ 원본 비교 / 2026-11-06:** [P04/P05 비교 결과](P04_P05_FIRMWARE_COMPARISON.md)를 저장했습니다. 같은 940X3G 계열의 공식 P04 원본을 확보해 SABI 등록 경로·설정 화면 데이터를 대조했지만 현재 모델 보호 조회·제어 계약은 찾지 못했습니다. 실제 제어는 미구현·Unsupported이며 기존 프로그램을 유지합니다. 이번에는 정적 근거·문서만 갱신했고 빌드·단위 테스트를 반복하지 않았습니다. 추가 노트북 시험·자료 재제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 남은 직접 조회 후보 검토 / 2026-11-06:** [직접 호출·삭제 호출자·레거시 중계·SSDT 대응](REMAINING_QUERY_PATHS_REVIEW.md)을 추가 확인했습니다. 새 보호 설정 조회 handler나 응답 계약은 확보하지 못했으며 실제 제어는 Unsupported입니다. 이번에는 문서·정적 근거만 갱신했고 프로그램과 기존 ZIP은 유지합니다. 빌드·단위 테스트는 반복하지 않았습니다. 새 실행·노트북 시험·업로드는 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 펌웨어 조회 경계·요청 범위 보강 / 2026-11-06:** [분석·코드·검증 안내](FIRMWARE_QUERY_BOUNDARY_UPDATE.md)에서256슬롯 조회 구조에 맞춰 순수 요청 준비 범위를0..255로 좁혔습니다. UInt16 프레임 형식은 유지하고 raw frame 우회도 같은 검사로 거부합니다. 캡슐 ACPI와 간접 참조도 추가 대조했지만 실제 보호 설정 조회는 여전히 미구현·Unsupported입니다. 이번 제공물은 개발 소스이며 기존 프로그램을 그대로 사용합니다. 새 노트북 시험·업로드는 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 배터리 보호 접근 후속 분석 / 2026-11-06:** [현재 계열의 추가 원본·간접 경로 대조](BATTERY_PROTECTION_ACCESS_FOLLOWUP.md)를 완료했습니다. 공식2.0.0.78/2.2.0.21을 확보해 같은940X3G 계열의 과거 배터리 caller를 확인했습니다. 펌웨어 등록 후보56개와 별칭·동적 화면도 추적했지만 현재 모델의 handler·신뢰할 보호 상태 재조회는 미확정입니다. 실제 제어는 Unsupported이며 프로그램은 변경하지 않습니다. 이번 빌드·단위 테스트는 미실행이고 새 시험·업로드는 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — OEM 후속 처리와 전체 펌웨어 볼륨 대조 / 2026-11-06:** [이번 분석 결과](CONTROL_CONTRACT_CLOSURE_REVIEW.md)에서 현재 SUS의 후속 처리가 팝업용 INI 설정임을 x86/x64로 확인했습니다. P05ACJ의 나머지6개 볼륨·표준 압축 섹션과 같은 배포 목록의 제조사 매뉴얼도 확인했지만, 배터리65/66 처리·신뢰할 보호 상태 read-back은 아직 입증하지 못했습니다. 실제 제어는 Unsupported이며 기존 프로그램을 유지합니다. 이번에는 문서만 변경했고 빌드·단위 테스트를 반복하지 않았습니다. 새 시험·업로드는 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 현재 계열 원본과 설명 반영판 / 2026-11-06:** [새 근거·변경·검증](CURRENT_MODEL_OEM_EVIDENCE_UPDATE.md)에서940X3G 카탈로그의Settings2.2.0.18을확보하고기존x64Sabi3와바이트일치를확인했습니다. 이연결과비교OEM해석을앱오프라인설명에반영했으며현재지원·보호설정은여전히미확정입니다. C#435·Python85통과,빌드경고오류0. [프로그램 ZIP](../downloads/ATIVBatteryGuard-OEM-CALLER-EVIDENCE.zip) 하나만새폴더에풀어일반권한으로실행할수있습니다. 새시험·업로드는필요없고실제제어Unsupported입니다. 아래는이전기록입니다.

**최신 — OEM 메뉴·상태 대조 / 2026-11-06:** [재개한 분석 결과](OEM_UI_SUPPORT_CONTRACT_REVIEW.md)에서 비교용 Settings2.0.0.89의 지원 결과→로컬 UI 속성→배터리 child/헤더 생성까지 연결했습니다. FF·메뉴 부재·화면 변경·초기화1을 현재 하드웨어의 미지원/적용 확인으로 사용하지 않습니다. tail 재사용과 setter 반환의 한계도 독립 감사로 정밀화했습니다. 현재 모델 적용성은 미확정이며 실제 제어Unsupported입니다. 앱/배포파일은 유지하고 새 시험·업로드는 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — 원본 확보·중간 분석 저장 / 2026-11-06:** 사용자 요청으로 개발을 중지하고 [재개 메모](SETTINGS_CALLER_ANALYSIS_HANDOFF.md)를 저장했습니다. 확인된 Settings ZIP을200으로 받아 실제Win8모듈·SUS/Cmd배터리 함수와 조건부 쓰기를 정적으로 조사했습니다. 버퍼 재사용·오류/메뉴 캐시 때문에 과거 단발과 입력/의미가 같다고 단정할 수 없습니다. 현재 모델 적용성과 UI 연결은 미완료이며 실제 제어Unsupported입니다. 앱·기존ZIP은 유지하고 새 시험·업로드는 필요하지 않습니다. 아래는 이전 기록입니다.

**최신 — ZIP 최종 호스트 확인 / 2026-11-06:** [새 접근 결과](SETTINGS_BOM_PACKAGE_UPDATE.md)에서 게시된 org.downloadcenter 허용 적용과 실제302를 확인했습니다. 정확한 ZIP 목적지는 downloadcenter.samsung.com이며 현재 HEAD는CONNECT403입니다. 이 한 호스트 추가 초안을 저장·재조회했고 기존6호스트/설정은 보존했습니다. 원본 ZIP·내부caller는 아직 미확보입니다. 이번에는 문서만 갱신해 프로그램·소스코드·테스트·기존ZIP은 유지하고 빌드/테스트를 반복하지 않았습니다. 새 다운로드·시험·업로드 불필요, 실제 제어Unsupported. 아래는 이전 기록입니다.

**최신 — Settings 비교 원본 식별 / 2026-11-06:** [실제 BOM 분석·새 검사 기능](SETTINGS_BOM_PACKAGE_UPDATE.md)에서 Easy Settings2.0.0.89의 정확한 원본 파일명 BASW-83876A21.ZIP을 확인했습니다. 모델930X5J의 비교 자료이며 현재 ATIV 지원 근거는 아닙니다. stdin 전용 BOM 검사를 추가하고 기존 SOAP/JSON 상한을 유지합니다. Python85개·실제응답10개 대조를 통과했습니다. ZIP 목적지 org.downloadcenter.samsung.com 한 호스트 추가 초안을 저장했으며 게시 후 실제 바이트·내부Win8모듈·배터리 caller를 확인해야 합니다. [개발 소스 ZIP](../downloads/ATIVBatteryGuard-SETTINGS-BOM-SOURCE.zip)은 실행 교체판이 아닙니다. 기존 프로그램을 그대로 사용하고 새 시험·업로드는 필요하지 않습니다. 실제 제어Unsupported. 아래는 이전 기록입니다.

**최신 — 공개 카탈로그 조회·서비스 오류 구분 / 2026-11-06:** [새 개발·근거·다음 작업](SAMSUNG_UPDATE_CATALOG_REVIEW.md)에 사용자 시리얼 없는 공개 모델 검색과 비교 모델 W7 카탈로그 조회 성공을 기록했습니다. 현재 계열의 시도한 W8 요청404와 비교 목록 XML2개를 구분하며, Settings 원본과 배터리 계약은 아직 미확보입니다. 새 오프라인 stdin 검사기는 HTTP200을 서비스 성공으로 오인하지 않습니다. Python74개 테스트와 실제 저장 응답8개 대조를 통과했습니다. [개발 소스 ZIP](../downloads/ATIVBatteryGuard-UPDATE-CATALOG-SOURCE.zip)은 실행 프로그램 교체판이 아닙니다. 기존 프로그램을 그대로 사용하며 새 시험·업로드는 필요하지 않습니다. 실제 제어Unsupported. 실제 BOM 호스트 appmanager.samsungmobile.com 하나를 추가한 환경 초안은 저장됐고 게시 후 적용 확인이 필요합니다. 아래는 이전 기록입니다.

**최신 — Settings 원문·버전 후보 확인 / 2026-11-06:** [새 원문 분석](SETTINGS_VERSION_SOURCE_REVIEW.md)에서 NP940X3G의2.1.0.20 배포 기록과 구형 Series7의2.0.0.89 시험을 구분했습니다. UI탭 제거는 현재 모델의 펌웨어 지원 부재나 구버전 호환성 증명이 아닙니다. 비교 원본 후보와 원문에 명시된 삼성 SWUpdate 위치를 좁혔고, orcaservice.samsungmobile.com 한 호스트 추가 초안을 저장·재조회했습니다(requires_publish=true). 기존 NBR 접근은 해결됐으며 환경을 다시 게시하지 않았습니다. 앱·프로그램은 유지하고 실제 제어는 Unsupported입니다. 아래는 이전 기록입니다.

**최신 — OEM 원본 접근 준비 / 2026-11-06:** [조사 결과·확인된 접근 조건](OEM_SOURCE_ACCESS_STATUS.md)을 기록했습니다. 제한적 공개 검색에서 현재 모델의 배터리 caller는 미확보이며, 이전 사용자 제공 Settings/Easy Settings 원문은 CONNECT403으로 차단됩니다. www.nbrchive.net 한 호스트만 환경 초안에 추가·재조회했고 기존 설정은 보존했습니다(saved/requires_publish=true). 환경 게시 후 적용과 원문 접근을 재확인해야 하며 에이전트가 게시하지 않았습니다. 새 프로그램이나 시험은 없고 제어는 Unsupported입니다. 아래는 이전 기록입니다.

**최신 — P05ACJ 설정 참조 검사 / 2026-11-06:** [새 분석·개발 도구](P05ACJ_HII_REFERENCE_UPDATE.md)는 고정 HII 리소스의11개 package·12,447 opcode를 읽고11종 표준 statement 헤더를 검사합니다. USB 충전/배터리 보정 참조는 관측됐지만 배터리 수명 연장 참조는 지원한 헤더에서 미관측입니다. 전체 기능 부재 판정은 아닙니다. 새로 구분한 배터리 신뢰성 시험 경로는 포트 쓰기를 포함해 대체 제어로 사용하지 않습니다. Python60개 통과. 앱 실행 파일은 변경하지 않아 기존 CALLER-CONTRACT-REVIEW를 사용하며 새 시험·업로드는 필요하지 않습니다. 현재 모델의 배터리 계약 근거가 없어 제어는 Unsupported입니다. 아래는 이전 단계 기록입니다.

**최신 — Windows 호출자 대조와 native 응답 해석 수정:** [새 근거·코드 변경](WINDOWS_CALLER_CONTRACT_UPDATE.md)에 구형 OEM의 DLL 선택과 시작 가드, P05ACJ의 별도0B flag 경로를 대조했습니다. 과거65의FF와0B 소스 flag는 별개입니다. 기존 native11바이트 디코더의0/1/FF→보호 OFF/ON·미지원 추정을 제거하고 opaque 표식만 반환하도록 수정했습니다. 실제 앱의 하드웨어 호출 경로는 추가하지 않았고 제어는 Unsupported입니다. C#435개·Python48개 통과, 빌드 경고·오류0개. [프로그램 ZIP](../downloads/ATIVBatteryGuard-CALLER-CONTRACT-REVIEW.zip) 하나만 새 폴더에 풀어 일반 권한으로 실행할 수 있으며 새 시험·업로드는 필요하지 않습니다. 아래는 이전 단계 기록입니다.

**최신 — 외부 등록 추적과 원본 검사 보강:** [새 분석·개발 결과](P05ACJ_EXTERNAL_REGISTRATION_REVIEW.md)에서 GUID 포함 후보34개와 실제 복구한 외부 등록경로10개를 구분했습니다. 비슷한80/81 입력을 사용하는 USB/AlwaysOn 명령과 UEFI 변수 쓰기를 포함하는7C 설정 경로는 배터리 대체 조회로 사용하지 않습니다. 개발용 검사기는 관측 P05ACJ의 길이·해시를 고정하며 Python46개 통과입니다. 앱 실행 파일은 바꾸지 않았고 사용자의 직전판 실행을 수신했습니다. 기존 프로그램을 그대로 사용하며 새 시험·업로드는 필요하지 않습니다. 실제 제어는 Unsupported입니다. 아래는 이전 단계 기록입니다.

**최신 개발 — P05ACJ 응답 근거 반영판:** 실제 P05ACJ 이미지에서 여러 실패 조건이 ACK AA와 FF+0 데이터를 만드는 공통 경로를 찾았습니다. [근거·구현·한계](FIRMWARE_REPLY_EVIDENCE_UPDATE.md)에 실제 원본 해시와 구형 OEM 호출자의 오류 무시 동작을 기록했습니다. 순수 디코더에는 데이터16바이트 접두부 비교를 추가하고, 기존 GUI의 과거 FF 결과 설명을 보완했습니다. 과거 첫 FF만으로 패턴·원인을 확정하지 않으며 실제 충전 제어는 Unsupported입니다. [프로그램 ZIP](../downloads/ATIVBatteryGuard-FIRMWARE-REPLY-EVIDENCE.zip) 하나만 새 폴더에 풀어 일반 권한으로 실행합니다. 새 시험·자료 재제출은 필요하지 않습니다. 아래는 이전 단계의 기록입니다.

**명령 원본 후보와 접근 조건 구체화:** [최신 조사·개발용 검사기·네트워크 검토 초안](COMMAND_SOURCE_ARTIFACTS_AND_ACCESS.md)에 정확한 P05ACJ 패키지 이름과 구형 Battery Life Extender 공개 LFS 객체를 기록했습니다. 현재는 목록/포인터만 확보했고 실제 원본은 네트워크 정책으로 차단됐습니다. 필요한 두 호스트만 초안에 추가했으며 환경을 게시하지 않았습니다. 새 명령·FF 의미·충전 지원을 확인한 것은 아니고 앱·기존 ZIP은 유지합니다. 아래는 이전 작업 당시의 기록입니다.

**동일 BIOS 공개 정적 자료 확보:** 940X3G/930X3G·P05ACJ를 같은 수집 실행의 메타데이터로 확인한 ACPI 덤프를 찾았습니다. [새 근거와 명령 구분](P05ACJ_BATTERY_COMMAND_EVIDENCE.md)에서 WMI 중계의 선행Zero·고정0x10 반환과 별도 표준 배터리 정보/상태/알림 임계값 경로를 대조했습니다. 충전 상한이나0x65/FF 계약을 확인한 결과는 아니며 새 명령을 실행하지 않습니다. 앱·배포 ZIP은 유지하고 기존 자료 재제출·진단 반복은 요청하지 않습니다. 아래는 이전 작업 당시의 기록입니다.

**v7 실기 결과 수신:** Integer Literal Store1회가 입력/반환과 같은 SystemMemory·21바이트 Field/Region을 참조하며, 보조 Store와는 다른 관측 선언입니다. 같은 직접 목록의 소스 배치는 Literal Store → Arg2 Store → 보조 호출 → Return입니다. [분석과 다음 계획](ACPI_V7_RESULT_AND_NEXT_PLAN.md)은 중계 구문 세분화보다 모델별 Windows 배터리 명령·응답 계약의 근거 확보를 우선합니다. 실제 실행·FF 의미·충전 지원은 미확정입니다. 이번에는 분석·계획만 기록하며 v7 반복·관리자 비교·기존 자료 재제출은 필요하지 않습니다. 아래는 이전 작업 당시의 기록입니다.

**현재 배포 — Literal Store 대상·구문 배치 요약 / Acpi-routing-v7 (2026-11-05 한국 시간):** [v6 후속 계획](ACPI_V6_RESULT_AND_NEXT_PLAN.md)에 따라 직접 Literal Store의 구문 종류·대상 Field와 입력/반환/보조 Field 및 Region의 관측 정의 관계, 같은 직접 구문 목록의 앞뒤 배치를 추가했습니다. [변경·해석·실행 안내](ACPI_STORE_ROLE_UPDATE.md)와 [프로그램 ZIP](../downloads/ATIVBatteryGuard-ACPI-STORE-ROLES.zip)을 따릅니다. **프로그램 ZIP 하나만** 새 폴더에 전부 풀고 일반 권한으로 실행합니다. 소스 ZIP은 개발용입니다. 분기·반복·중첩·복수 후보는 미확정/복수 분류로 남기며 실제 실행 순서·값 전파·FF 원인을 추론하지 않습니다. 기존 수집 범위와 안전 제한은 유지하고 실제 제어는 Unsupported입니다. 새 v7 실기는 아직 미관측입니다. 아래는 이전 작업 당시의 기록이며 과거 실행 절차를 다시 수행하라는 안내가 아닙니다.

**v6 실기 결과 수신:** 입력 저장/반환 Field는 모두 SystemMemory·21바이트 선언 폭 일치이며 보조 Store는 SystemIo의 다른 관측 Region 정의를 참조합니다. 후보 Field Store2회 중1회는 직접 Arg2, 나머지는 Literal 원천입니다. [분석과 다음 계획](ACPI_V6_RESULT_AND_NEXT_PLAN.md)에 추가 Store 대상·literal 종류·제한된 구문 위치 관계의 분석 조건을 기록했습니다. FF 의미와 실제 제어는 미확정입니다. 이번에는 결과 분석만 기록하고 새 프로그램을 배포하지 않으며 v6 반복·관리자 비교·기존 자료 재제출은 필요하지 않습니다. 아래는 이전 작업 당시의 기록입니다.

**현재 배포 — Field·프레임 통로 선언 요약 / Acpi-routing-v6 (2026-11-05 한국 시간):** [변경·해석·실행 안내](ACPI_FIELD_CHANNEL_UPDATE.md)에 따라 후보 입력/반환 Field의 선언 공간과 고정21바이트 프레임에 대한 폭 분류, 직접 Store 입력 역할, 보조 Store와의 Region 선언 관계를 추가했습니다. 관측 선언의 구문만 비교하며 실제 값·주소·물리 영역·AML/OEM 실행을 확인하지 않습니다. 복수/혼합/미확정을 단일 일치로 바꾸지 않으며 FF 의미와 실제 충전 제어는 여전히 미확정/Unsupported입니다.

[프로그램 ZIP](../downloads/ATIVBatteryGuard-ACPI-FIELD-CHANNEL.zip) **하나만** 새 폴더에 모두 풀고 `ATIVBatteryGuard.AcpiRoutingCheck.exe`를 **일반 권한**으로 실행합니다. 소스 ZIP은 개발용이며 함께 풀 필요가 없습니다. **Acpi-routing-v6 새 요약만** 확인하며 이전 TXT/DLL/EXE·원본 ACPI 재제출, v5 반복·관리자 비교·OEM 재실행은 필요하지 않습니다. 수집 API·대상·안전 상한과 기존 실험 예약은 유지합니다. 새 v6 Windows 실기는 아직 미관측이며 자동 검증 결과는 [VALIDATION.md](VALIDATION.md)를 따릅니다. 아래는 각 단계 당시의 기록입니다.

## 이전 개발 기록

**v5 실기 결과 수신:** 후보 3/3회 Field·보조 3/3회 Mutex/Field 종류 분류, 후보 입력 저장/반환의 동일 관측 Field 참조와 보조 SystemIo Field Store 구문을 확인했습니다. [분석 및 다음 개발 계획](ACPI_V5_RESULT_AND_NEXT_PLAN.md)은 필드 선언 형태·정적 프레임 통로 확인을 우선합니다. FF 의미와 실제 제어는 미확정입니다. 이번에는 분석·계획만 기록하고 코드/ZIP을 변경하지 않으며 v5 반복·관리자 비교·기존 자료 재제출은 필요하지 않습니다. 아래는 이전 기록입니다.

**객체·참조 관계 요약 — Acpi-routing-v5:** [직전 계획](ACPI_V4_RESULT_AND_NEXT_PLAN.md)에 따라 같은 테이블의 관측 이름 정의 종류와 Store/Return의 참조 관계를 분류합니다. [변경 범위·실행 안내](ACPI_OBJECT_REFERENCE_UPDATE.md)와 [프로그램 ZIP](../downloads/ATIVBatteryGuard-ACPI-OBJECT-REFERENCES.zip)을 따릅니다. 프로그램 ZIP 하나만 새 폴더에 풀어 일반 권한으로 실행합니다. 값·분기·별칭·실제 데이터 전달을 평가하지 않으며 Field/OperationRegion을 실제로 읽거나 쓰지 않습니다. FF 의미와 충전 제어는 미확정이고 새 v5 실기는 아직 미관측입니다. 아래는 이전 기록입니다.

**v4 실기 확인:** 보조 본문 1개 해석·미지원 0·실패 None·Acquire/Release 구문을 관측해 v4의 직접 목표를 확인했습니다. 연결 Partial과 FF 의미 미확정은 유지합니다. [분석 및 다음 개발 계획](ACPI_V4_RESULT_AND_NEXT_PLAN.md)은 이름 객체 종류와 Store/Return의 정적 참조 관계를 우선하며 이번에는 실행 코드/ZIP을 변경하지 않습니다. v4 반복 실행·관리자 비교·기존 자료 재제출은 필요하지 않습니다. 아래는 이전 단계 기록입니다.

**보조 본문 구문 점검 — Acpi-routing-v4:** v3에서 호출 표현식/보조 정의 1개를 관측했으나 보조 본문이 미지원으로 끝났습니다. [v4](ACPI_HELPER_SYNTAX_UPDATE.md)는 수집 범위를 유지하며 표준 확장 구문의 정적 읽기·고정 중단 원인·해석 완료한 보조 본문 범위의 반환 구문을 보고합니다. [프로그램 ZIP](../downloads/ATIVBatteryGuard-ACPI-HELPER-SYNTAX.zip) 하나만 새 폴더에 풀어 일반 권한으로 실행합니다. 실제 대기/동기화/AML/OEM 실행은 없고 FF 의미와 충전 제어는 미확정입니다. 아래는 이전 기록입니다.

**메서드 연결 구문 요약 — Acpi-routing-v3:** v2 실기에서 DSDT 직접 읽기와 알려진 설명자/메서드 각 1개·인수 3개·본문 Parsed를 확인했습니다. [v3 변경과 실행 안내](ACPI_METHOD_FLOW_UPDATE.md)는 같은 수집 범위를 유지하며 후보의 반환 형태·직접 Arg2 전달·제한된 보조 정의 연결을 정적으로 요약합니다. [프로그램 ZIP](../downloads/ATIVBatteryGuard-ACPI-METHOD-FLOW.zip) 하나만 새 폴더에 풀고 일반 권한으로 실행합니다. 메서드 실행이나 값/실행 분기 추론은 없고 FF 의미·충전 제어는 미확정입니다. 아래는 이전 기록입니다.

**DSDT 직접 읽기 수정본 — Acpi-routing-v2:** 공개 ACPICA 구현에서 Windows 목록에 없는 DSDT를 직접 읽는 근거를 확인해 기존 미열거 gate를 수정했습니다. [변경 근거·범위·실행 안내](ACPI_DSDT_DIRECT_READ_UPDATE.md)와 [프로그램 ZIP](../downloads/ATIVBatteryGuard-ACPI-DSDT-DIRECT.zip)을 따릅니다. 프로그램 ZIP 하나만 새 폴더에 풀고 일반 권한으로 실행합니다. OEM/AML 실행·예약 접근·레지스트리 읽기는 없으며 실제 충전 제어는 Unsupported입니다. 새 직접 읽기 경로의 Windows 실기는 아직 미검증입니다. 아래는 이전 단계 기록입니다.

**ACPI 점검 실기 결과 수신:** [전달된 결과 분석](ACPI_ROUTING_LAPTOP_RESULT.md)에서 목록 조회 Complete·DSDT 0·SSDT 4·첫 SSDT Partial을 확인했습니다. 현재 모델의 WMI 정의와 FF 의미는 확보하지 못했습니다. 같은 점검 도구를 다시 실행하거나 기존 자료를 재제출할 필요는 없습니다. 이번에는 관측과 수집 한계만 기록했고 실행 코드·배포 ZIP은 변경하지 않았습니다. 아래 실행 안내는 이전 단계 기록입니다.

현재 모델의 WMI 분기를 더 좁히기 위해 [ACPI 정적 연결 점검](ACPI_STATIC_ROUTING_CHECK.md)을 구현했습니다. Windows 내장 API로 DSDT/첫 SSDT만 읽고 제한된 구문 사실을 요약합니다. AML 실행·OEM 호출·예약 접근·원본 테이블 저장은 없습니다. 아직 FF 의미를 해결하거나 실제 제어를 구현한 결과는 아닙니다.

[새 ACPI 점검 도구](../downloads/README.md)를 일반 권한으로 실행해 새 요약만 확인할 수 있습니다. 기존 배터리 진단/TXT/DLL의 재제출은 필요하지 않으며 원본 ACPI도 제출하지 않습니다. 기존 1회 실험은 재실행하지 않고 예약 표식을 유지합니다. 아래는 이전 기록입니다.

사용자가 현재 일반 앱의 **일반 권한 실행과 배터리 표시 정상 동작**을 확인했습니다. [후속 모델별 계약 조사](WMI_MODEL_CONTRACT_FOLLOWUP.md)에서는 조회 입력0x80의 별도 공개 근거를 확인하고 공개 ACPI의 실제 트리까지 대조했지만, 현재 모델의 Windows 배터리 명령/FF 의미를 확정할 새 근거는 확보하지 못했습니다. 이번에는 실행 코드를 변경하지 않았으며 현재 앱을 그대로 사용합니다. 새 시험이나 자료 재제출은 필요하지 않습니다.

[승인된 조회의 실제 결과](WMI_ONE_SHOT_QUERY_RESULT.md)는 ResponseReceived·FrameChecked·ValidFrame·표식FF입니다. WMI 응답 수신과 구조 검증은 성공했지만 배터리 보호 상태와 후보 의미는 미확정입니다. 승인된1회는 완료됐으므로 실험을 재실행하거나 예약 표식을 삭제하지 않습니다.

새 일반 앱의 **과거 WMI 실험 결과 검토**에서 이미 받은 출력을 추가 호출 없이 확인할 수 있습니다. 원문은 검토 후 비우고 저장하지 않으며 과거 텍스트를 현재 장치 상태로 승격하지 않습니다. [RESULT-REVIEW 프로그램·소스](../downloads/README.md)는 관리자 권한 없이 실행하고 실험 EXE·삼성 원본 DLL을 포함하지 않습니다. 실제 충전 제어는 계속 Unsupported입니다. 새 실험/자료 재제출은 필요하지 않습니다. 아래는 이전 기록입니다.

[Locator-v2 실기 결과와 승인 조회 수정본](WMI_QUERY_LOCATOR_READY_RESULT.md): 사용자 노트북에서 Elevated·Complete·Ready·None을 확인했습니다. OEM 호출과 예약 접근은 없었고 전체 준비 검사는 통과했습니다. 검증된 경로 정보 옵션을 기존 승인 1회 조회 도구에만 반영했습니다.

새 **Query65-locator-v2**는 고정 후보0x65를 최대1회 요청하는 한정 실험입니다. 원래 요청·가드·동일 영속 예약 표식을 유지하며 기존 표식이 있으면 호출하지 않습니다. [새 실행·소스 ZIP과 절차](../downloads/README.md)를 따르고 예약 표식 삭제·재시도·다른 명령 시험은 하지 않습니다. 후보 의미와 부작용은 여전히 미검증이며 실제 충전 제어는 Unsupported입니다. 아래는 이전 기록입니다.

[경로 정보 확보 보완판 Locator-v2](WMI_PREFLIGHT_LOCATOR_UPDATE.md)를 구현했습니다. OEM 호출 없는 점검 도구의 메서드 대상 쿼리에만 EnsureLocatable을 추가하고 객체·경로 오류와 명시적 Active=false를 구분합니다. 기존 단일 활성 대상/입력 검증과 시간 제한을 유지하며 실제 충전 제어는 계속 Unsupported입니다.

[새 LOCATOR 프로그램·소스](../downloads/README.md)를 새 폴더에 풀고 `ATIVBatteryGuard.WmiPreflightCheck.exe`만 같은 계정에서 수동 관리자 실행해 `(Locator-v2)` 표시가 있는 새 출력만 전달합니다. OEM 호출과 예약 접근은 없으며 이전 실험 EXE 재실행·예약 표식 삭제·과거 자료 재제출은 필요하지 않습니다. 아래는 이전 개발 기록입니다.

[새 점검 도구의 실기 결과](WMI_PREFLIGHT_ENUMERATION_RESULT.md)를 분석했습니다. Elevated 상태에서 모델/BIOS·메서드 정의 검사는 통과했으나 MethodEnumeration의 대상 조건에서 중단됐습니다. Active=false와 객체/경로 문제를 아직 구분할 수 없어 경로 정보 확보 옵션과 고정 오류 분류를 다음 수정 대상으로 정리했습니다. OEM 호출·예약 접근은 없었고 같은 도구의 재실행이나 기존 자료 재제출은 필요하지 않습니다. 이번 변경은 분석 문서뿐입니다.

[OEM 호출 없는 사전 검증 점검 도구](WMI_PREFLIGHT_ONLY_CHECK.md)를 추가했습니다. 이전 Elevated 실패 결과에서 빠졌던 준비 단계와 고정 오류 종류를 출력하며, 기존 실험의 조건·쿼리 옵션은 유지합니다. OEM 호출과 예약 표식 접근은 없고 실제 충전 제어는 계속 Unsupported입니다.

[새 점검 프로그램·소스 다운로드](../downloads/README.md)의 **WMI-PREFLIGHT-ONLY**를 사용합니다. 새 폴더의 **ATIVBatteryGuard.WmiPreflightCheck.exe만 같은 계정에서 수동 관리자 실행**하고 새 출력만 전달하면 됩니다. 이전 WmiOneShotQuery는 재실행하지 않고 예약 표식도 건드리지 않습니다. 과거 TXT나 삼성 DLL을 다시 제출할 필요는 없습니다.

현재 전체329개 테스트 통과, 여섯 프로젝트 빌드 경고·오류0개입니다. 새 도구의 Windows 실기는 아직 미검증입니다. 아래는 과거 단계 기록이며 기존 실험의 실행 안내는 현재의 재실행 지시가 아닙니다.

[1회 도구의 실제 결과](WMI_ONE_SHOT_PREFLIGHT_RESULT.md)를 확인했습니다. Elevated 상태에서 사전 검증이 중단됐고 OEM 호출 요청·후보 응답은 없었습니다. 공통 오류 문구만으로 실패 위치를 특정할 수 없어 고정 단계 보고만 보완합니다. 호출 조건과 1회 제한은 그대로 유지하며 이번에는 새 실행이나 예약 표식 삭제를 요청하지 않습니다. 아래는 이전 개발 이력입니다.

[사용자가 승인한 한정 조회 후보 실험](WMI_ONE_SHOT_QUERY_APPROVAL.md)을 별도 도구로 구현했습니다. 고정0x65 후보·같은 계정의 수동 관리자 실행·최대1회만 허용합니다. 모델/BIOS·규약·단일 활성 대상이 모두 맞고 영속 예약을 확보해야 요청하며, 재실행·다른 명령·자동 권한 상승·메인 앱 연결은 없습니다.

최종 보고서는 후보 표식만 분류하며 실제 보호 상태나 충전 제어 지원으로 바꾸지 않습니다. 삼성 원본 DLL은 포함하지 않습니다. [실행·소스 다운로드](../downloads/README.md)와 승인 문서의 한 번 실행 절차를 따릅니다. 새 도구의 Windows 실기는 아직 미검증이고 실제 충전 제어는 계속 Unsupported입니다.

이번 전체322개 테스트와 Python6개 통과, 전체5개 프로젝트 빌드 경고·오류0개입니다. 실제 Windows/OEM 호출은 클라우드에서 실행하지 않았습니다. 아래는 이전 개발 이력입니다.

[다음 단계 검토서](WMI_ONE_SHOT_QUERY_REVIEW.md)를 준비했습니다. 추가 공개자료를 대조했지만 현재 모델의 Windows WMI 배터리 조회 계약은 여전히 미확정입니다. 미검증 조회후보0x65를 별도 도구에서 한정1회 시험할지 검토하는 문서이며 실제 OEM 실행 코드·새 EXE·실기 시도는 아직 없습니다.

현재 사용자 제한과 프로젝트 규칙에 따른 범위 변경 승인이 먼저 필요합니다. 이전 관리자 속성 비교나 일반적인 개발 계속 지시를 OEM 실험 승인으로 확대하지 않습니다. 기존 프로그램·소스는 그대로 보존하고 실제 충전 제어는 계속 Unsupported입니다. 아래는 이전 개발·검증 이력입니다.

현재는 [메모리 채널 연결과 전체 경로 통합 검증](WMI_BOUND_CHANNEL_AND_PIPELINE.md) 단계입니다. 기존 비동기 요청 조정기·메서드 바인더·응답 검증기를 명시적으로 주입한 snapshot 경계로 연결했습니다. 중첩 필드 오류와 바이트 오류를 구분해 보존하고 취소·시간 초과는 기존 조정기를 재사용합니다.

실제 WMI/OEM 구현·객체 생성·메서드 실행·앱 등록은 없고 가짜 transport로 검증합니다. 이번에는 개발 소스를 전달하며 노트북에서 같은 규약 진단을 다시 실행할 필요가 없습니다. 현재 모델의 배터리 명령 의미·안전성·실제 응답 계약은 여전히 미확정이며 실제 설정 읽기와 충전 제어는 미구현·Unsupported입니다.

이번 전체 테스트 **297개 통과·실패/건너뜀0개**, 전체 빌드 **경고·오류0개**입니다. 아래는 이전 단계 이력입니다.

현재는 [WMI 형식 일치 실기 확인 후 메모리용 바인더 구현](WMI_MATCHED_BINDING_AND_OFFLINE_ENVELOPE.md) 단계입니다. 판독기2에서 GUID 후보·메서드·입출력 DataBuffer·Bytes UInt8[]가 모두 일치했고 Windows 메서드 번호1을 확인했습니다. 같은 규약 진단은 완료됐으므로 다시 실행할 필요가 없습니다.

새 내부 코드는 확인된 상세 메타데이터에서 고정 중첩 입출력을 요청 인코더·응답 검증기에 연결합니다. 메모리 snapshot만 처리하며 실제 WMI/OEM 전송은 연결하지 않았습니다. 이번에는 개발 소스를 제공하고 새 노트북 실행을 요청하지 않습니다. 모델별 배터리 명령의 의미·안전성·실제 응답 계약은 남아 있으며 실제 충전 제어는 계속 Unsupported입니다.

이번 전체 테스트 **286개 통과·실패/건너뜀0개**, 4개 프로젝트 빌드 **경고·오류0개**입니다. 새 OEM 호출이나 노트북 충전 제어의 검증 결과는 아닙니다. 아래는 이전 단계 이력입니다.

현재는 [실제 WMI 규약 결과 반영과 CIMTYPE 판독 보완](WMI_PARAMETER_RESULT_AND_CIMTYPE_REVIEW.md) 단계입니다. 사용자 출력에서 공개 GUID 후보 일치·CallSabiFunction 존재·Windows 메서드 번호1·Bytes UInt8[]를 확인했으며 입출력 클래스는 Unknown입니다. 이전 도구의 불완전한 EmbeddedInstance 단독 판정을 표준 CIMTYPE와 함께 읽도록 수정했습니다. 실제 노트북 CIMTYPE 값은 아직 미관측입니다.

[입출력 형식 판독 보완판 다운로드](../downloads/README.md): 기존과 같은 ATIVBatteryGuard.WmiContractCheck.exe를 일반적으로 실행하며 상단에 판독기2가 표시됩니다. 고정 메타데이터만 읽고 qualifier 누락·불일치·충돌·형식 오류를 구분합니다. 기존 자료·관리자 비교는 다시 필요하지 않습니다. 전체274개 테스트와 Python6개 통과, 전체 빌드 경고·오류0개입니다. 수정 도구의 Windows 실기는 미검증이며 실제 배터리 보호 설정 조회·충전 제어는 계속 미구현입니다. 아래는 이전 단계 이력입니다.

현재 개발은 [WMI 비동기 프레임 처리와 클래스 규약 확인](WMI_EXCHANGE_AND_BINDING_CHECK.md)입니다. 취소·시간 초과 후 실제 작업 종료까지 중복을 차단하는 코드를 가짜 채널로 검증했고, 공개 WMI 전송과 Windows 클래스의 연결을 확인하는 별도 일반 권한 도구를 추가했습니다. 실제 OEM 전송 구현은 연결하지 않았습니다.

[새 확인 도구 다운로드](../downloads/README.md): ZIP을 새 폴더에 모두 풀고 ATIVBatteryGuard.WmiContractCheck.exe를 일반적으로 더블클릭합니다. 새 GUID 후보 일치 여부·메서드 번호·입출력 정의만 확인합니다. 이전 TXT·DLL·일반/관리자 비교는 다시 필요하지 않습니다. 관리자 실행은 요청하지 않습니다.

전체 테스트 **262개 통과**, Core·WPF·두 별도 도구 빌드 **경고·오류 0개**, Python 배포 검증 **6개 통과**입니다. 새 도구의 Windows 실기는 미검증이며 실제 충전 제어는 계속 미지원입니다. 아래 단계별 수치와 승인 대기는 당시 이력입니다.

[최신 개발: 구조적 WMI 응답 디코더](WMI_REPLY_DECODER_AND_PUBLIC_EVIDENCE.md)를 구현했습니다. API 미완료·응답 형식·길이·ACK 오류를 구분하고 실패 시 이전 데이터를 제거합니다. 기존 bool API와 지원 범위를 유지하며 배터리 상태 해석·실제 OEM 호출은 추가하지 않았습니다.

추가 공개 소스 두 곳에서 21바이트 전송 구조를 교차 확인했습니다. 현재 모델의 배터리 명령 계약은 여전히 미검증입니다. 전체 테스트244개 통과, 솔루션 빌드 경고·오류0개이며 실제 충전 제어는 계속 미지원입니다.

[권한 비교 결과 수신](WMI_PERMISSION_COMPARISON_RESULT.md): 일반 토큰에서 버전 클래스 Active=True/version16을 읽었고, 메서드 클래스는 열거에서 거부됐습니다. 상승 토큰에서는 두 클래스의 속성을 읽었습니다. 실제 배터리 명령이나 보호 상태를 확인한 결과는 아니며 충전 제어는 계속 미지원입니다. 비교 단계는 완료됐고 같은 진단을 다시 요청하지 않습니다.

[최신: WMI 권한 거부 지속과 별도 비교 도구](WMI_PERMISSION_COMPARISON_REVIEW.md): PacketPrivacy 적용 후에도 두 클래스 AccessDenied가 유지된 실제 결과를 확인했습니다. 자동 권한 상승 없이 현재 토큰과 실패 단계를 읽는 별도 asInvoker 도구를 준비했습니다. 관리자 비교는 아직 승인·실행하지 않았으며 메인 앱과 충전 제어는 그대로 일반 권한·미지원입니다.

이번 전체 테스트 237개 통과, WPF·Core·별도 비교 도구 빌드 경고·오류 0개입니다. 새 도구의 Windows 실기 실행은 미검증입니다. 아래는 이전 작업 이력입니다.

[최신 WMI 권한 결과와 다음 구현](WMI_ACCESS_RESULT_AND_TRANSPORT_REVIEW.md): 실제 TXT에서 SABI 이름 미관측, Samsung 이름 후보 7개 Stopped/Manual, 두 WMI 클래스 AccessDenied를 확인했습니다. 일반 사용자 권한을 유지한 암호화 WMI 연결을 명시하고 저장 성공과 조회 결과를 구분하는 화면 요약을 추가했습니다. 실제 거부 원인·해결 여부는 아직 미검증입니다.

기존 서비스 wsabi 규약의 순수 요청 인코더도 준비했으나 실제 호출 경로에는 연결하지 않았습니다. 이번 테스트 228개 및 배포 검증 6개 통과, WPF/XAML 빌드 경고·오류 0개입니다. 실제 설정 읽기·충전 제어는 계속 미검증·미지원이며 아래 설명은 이전 단계 이력입니다.

[다음 단계: 삼성 WMI 인스턴스·버전·활성 속성 확인](SAMSUNG_WMI_INSTANCE_INSPECTION.md)을 구현했습니다. 기존 삼성 파일 보고서에 로컬 WmiAcpiVersion의 Active/version과 WmiAcpiMethod의 Active를 클래스별로 표시합니다. 인스턴스 이름·장치 식별자는 읽지 않으며 OEM 메서드는 실행하지 않습니다. Active를 배터리 보호 상태로 해석하지 않고 실제 충전 제어는 계속 미지원입니다.

이전 드라이버 확인판의 노트북 실행·TXT 생성은 사용자가 확인했습니다. TXT 내부의 조회 결과는 아직 전달받지 않았습니다. 이번 공유 소스 테스트는 **217개 통과**, 별도 배포 검증 **6개 통과**, WPF/XAML 빌드는 **경고·오류 0개**입니다. 새 WMI 값 조회의 실제 Windows 동작은 아직 미검증이며 아래 기록은 이전 단계 이력입니다.

[현재 개발: 삼성/SABI 커널 드라이버 상태 조회](SAMSUNG_KERNEL_DRIVER_INSPECTION.md)를 구현했습니다. 기존 **삼성 파일 정보 만들기** 결과에 이름 후보의 등록·실행 상태·시작 방식과 SABI 연결 이름 비교를 함께 표시합니다. 정상 조회의 후보 미관측과 오류·시간 초과를 구분하고 원래 서비스 이름·경로·사용자 이름·식별자는 보고하지 않습니다. 드라이버·서비스 변경, 삼성 DLL 초기화, OEM 명령은 실행하지 않으며 실제 충전 제어는 계속 미지원입니다.

현재 환경에서 공유 소스 테스트 **204개 통과·실패/건너뜀 0개**, x64 net48 WPF/XAML 빌드 **경고·오류 0개**를 확인했습니다. 새 Windows WMI 조회의 실제 노트북 동작은 아직 미검증입니다. 아래 이전 단계의 검증 수치와 관측 기록은 이력입니다.

[제공받은 x64 Sabi3 정적 분석](SABI3_NATIVE_ABI_REVIEW.md)에서 실제 11바이트 호출자 버퍼와 초기화·드라이버 경로를 확인했습니다. 코드를 수정하고 장치를 열지 않는 SABI 연결 이름 조회를 추가했습니다. 실제 OEM 함수는 아직 호출하지 않습니다.

후속 사용자 TXT에서 SABI 연결 이름 NotFound를 확인했습니다. [최신 관측과 별도 WMI 전송 구조](SABI_LINK_RESULT_AND_WMI_REVIEW.md)에 근거와 한계를 기록하고 Sabi3 선행 조건 설명·순수 WMI 응답 검증을 보완했습니다. 이번 소스 변경을 확인하기 위해 같은 TXT를 다시 만들 필요는 없습니다.

이번 소스 검증은 191개 테스트 통과·WPF 빌드 경고/오류 0개입니다. 실행용 ZIP은 이전 SABI-LINK-CHECK판을 유지하며 이번 변경으로 새 ZIP을 만들지 않았습니다. 실제 WMI 메서드와 충전 제어는 아직 실행하지 않습니다.

[최신 초기화·드라이버 규약 검토](SABI3_INITIALIZATION_REVIEW.md): 함수 참조의 실제 Windows 결과를 확인하고, 응답을 해석하는 순수 코드를 추가했습니다. 다음 단계에는 x64 Sabi3.dll의 구현 자체를 정적으로 확인해야 하며 현재 DLL 초기화·OEM 조회·실제 제어는 실행하지 않습니다.

현재는 사용자가 실제 DLL 식별 결과를 제공해 Sabi3 연동 준비를 진행하고 있습니다. [이번 결과와 구현 범위](SABI3_COMPATIBILITY_REVIEW.md)를 참고하세요. 실행용 개발 미리보기와 명시적인 배포 검증 모드를 구분하며, 이전 보안 관련 문서는 이력으로 보관합니다.

현재 개발판은 **삼성 파일 정보 만들기**로 두 DLL과 두 EXE의 버전·구조·오프라인 서명·정적 참조·함수 이름을 로컬 TXT에 저장합니다. [범위·사용법·검증 한계](SAMSUNG_FILE_INSPECTION.md)를 참고하세요. 삼성 코드를 실행하지 않으며 실제 충전 제어는 계속 미지원입니다.

현재 함수 참조 분석·Sabi3 준비 판정 변경의 공유 소스 테스트는 173개 통과·실패 0개·건너뜀 0개이며 실제 WPF 빌드는 경고·오류 0개입니다. 이전 파일 식별은 사용자 TXT로 확인됐고 이번 확장 기능의 Windows 실기 실행은 아직 미검증입니다.

[최신 공개 제어 규약 조사](PUBLIC_CONTROL_PROTOCOL_REVIEW.md): 구형 Windows SABI3 명령 후보와 Galaxy Book ACPI 규약을 찾았으나 현재 ATIV의 DLL 없는 Windows 제어 경로는 미검증입니다. 실제 충전 제어는 계속 미지원입니다.

[설치 폴더에서 확인할 DLL 후보](SAMSUNG_DLL_CANDIDATES.md): 사용자 제공 `Setting` 경로를 참고용으로 기록하고 `Sabi3.dll`·`wsabi.dll`의 근거와 추가 검색 패턴을 구분했습니다. 실제 폴더 목록을 클라우드에서 열람한 결과는 아닙니다.

[사용량 초기화 후 다음 개발 메모](NEXT_DEVELOPMENT.md): 사용자가 찾은 두 DLL과 `BatteryToast.exe`·`PowerAudit.exe`의 확인 수준 및 다음 작업 순서를 정리했습니다.

## 현재 배터리 진단 결과 해석판

삼성 DLL 추출 없이 표준 Windows 배터리 드라이버의 요청 지원 여부를 읽는 진단을 추가했습니다. **진단 파일 만들기**로 생성되는 TXT의 ‘Windows 표준 배터리 드라이버의 요청 지원 여부’ 섹션에서 볼 수 있습니다. BatteryCharge/BatteryDischarge 지원 비트는 80% 충전 상한 지원의 증거가 아니며, 결과가 있어도 실제 제어는 미지원으로 유지합니다.

GENERIC_READ, QUERY_TAG(대기 0), QUERY_INFORMATION(정보 수준 0)만 사용합니다. 자체 보조 프로세스의 10초 제한과 최대 8개 인터페이스·16 KiB 결과 한도를 적용합니다. 장치 경로·태그·시리얼번호·고유 ID를 보고하지 않습니다. SET 요청이나 OEM 메서드는 실행하지 않습니다. 앱 시작이나 주기적 표시에서는 보조 조회를 실행하지 않습니다.

최신 진단에서 Windows 조회 성공과 `0x80000000`을 확인했습니다. 시스템 배터리 표시만 있고 표준 충전·방전 요청 지원 비트는 없습니다. 삼성 OEM 충전 상한의 가능성은 별도 미검증입니다.

현재 해석판은 이 차이를 메인 화면과 진단 TXT에서 설명합니다. 조회가 불완전하면 판단 불가로 남기고 재조회 시 이전 결과를 지웁니다. 같은 진단 파일을 다시 전달할 필요는 없습니다. 회귀 테스트 **138개 통과·실패 0개·건너뜀 0개**입니다. 새 해석 화면의 Windows 실행은 아직 미검증입니다. [구조·출처·검증 한계](WINDOWS_BATTERY_QUERY.md)에 상세히 기록했습니다. 아래 버전별 설명은 이전 단계의 이력입니다.


## 삼성 파일 추출 제외판의 현재 조건

사용자의 Samsung Settings에서 DLL을 추출할 수 없다는 조건으로 진행합니다. WPF 배포 프로젝트에서 삼성 파일 수집기와 위치 탐색기를 컴파일 제외했고 수집 확인 창과 UI도 제거했습니다. 장치 조회·로컬 설정·시뮬레이션·공식 문의문 복사는 유지합니다. 추출한 삼성 DLL은 필요하지 않습니다. 자체 Core DLL과 Windows 내장 프레임워크는 앱 구성 요소입니다.

Microsoft 공식 문서에서 일반 배터리 설정 요청 경로는 확인했지만, 검토한 인터페이스에는 지속되는 80% 충전 상한 항목이 없습니다. OEM WMI 입력 규약은 아직 확보하지 못했으며 실제 제어는 미지원입니다. [DLL 추출 없는 개발 경로와 실제 확인한 출처](DLL_INDEPENDENT_RESEARCH.md)를 참고하세요.

아래 수집 관련 설명은 이전 단계의 기록이며 현재 배포 기능이 아닙니다.


Samsung ATIV Book 9 Plus 계열을 위한 Windows 10 x64 배터리 상태·로컬 설정·읽기 전용 진단 앱입니다. C# / WPF / MVVM / .NET Framework 4.8을 사용합니다.

**현재 실제 80%/100% 충전 제한은 지원하지 않습니다.** 사용자 선택값, 실제 하드웨어 상태, Windows가 보고한 배터리 잔량은 별도로 표시합니다. Mock 모드는 메모리 안에서만 동작하는 시뮬레이션입니다.

이 디렉터리는 기존 자체 배포본의 C# 코드를 복원하고 프로젝트·화면·테스트·문서를 재구성한 작업본입니다. 원본 주석·테스트·문서 전체를 복구한 것은 아닙니다. 출처와 제한은 [RECOVERY.md](RECOVERY.md)에 기록합니다.

## Windows 10 빌드

개발용 PC에 다음 구성이 필요합니다.

- Visual Studio 2022의 **.NET 데스크톱 개발** 워크로드
- **.NET Framework 4.8 개발자 팩/대상 팩**
- .NET 8 SDK (SDK 형식 프로젝트와 portable 테스트용)

Visual Studio에서 `ATIVBatteryGuard.sln`을 열고 Release 구성을 빌드합니다. 개발자 터미널에서는 이 디렉터리를 기준으로 실행합니다.

```powershell
dotnet build ATIVBatteryGuard.sln -c Release
```

빌드된 `ATIVBatteryGuard.exe`와 같은 폴더의 앱 DLL·구성 파일을 함께 유지해 실행합니다. 일반 사용자 권한으로 실행하며, 관리자 권한 실행이나 드라이버 설치는 요구하지 않습니다.

Windows에서 빌드·회귀 테스트·제한 시간 90초의 GUI self-test를 함께 실행하려면 다음 명령을 사용합니다. 이 스크립트는 현재 Linux 환경에서 실행하지 않았습니다.

```powershell
powershell -File scripts/Test-Windows.ps1
```

## 현재 공식 지원 검토판

제품 시작 구성에서 OEM 파일 수집기를 해제했고 해당 버튼은 비활성화됩니다. 추가 삼성 파일 업로드는 요청하지 않습니다. 대신 장치 정보를 포함한 공식 문의문을 미리 보고 복사할 수 있습니다. 문의는 자동 전송하지 않습니다. 이 변경은 공식 사용권이나 충전 지원 여부를 확인했다는 뜻이 아닙니다.

실행용 파일은 `ATIVBatteryGuard-SUPPORT-REVIEW.zip`입니다. 새 suite는 114개 통과·실패 0개·건너뜀 0개이며 WPF 빌드는 경고·오류 0개입니다. 실제 새 Windows 문의 복사 동작은 미검증입니다. 아래 수집 관련 설명은 이전 단계의 구현 이력입니다.

## 동작 범위

- Windows 내장 배터리 API로 잔량·AC 연결·충전 상태 조회
- 사용자 희망 설정을 `%LOCALAPPDATA%\ATIVBatteryGuard\settings.json`에 저장
- 기본 실제 제어 어댑터의 모든 쓰기 요청 거부
- Mock 모드의 80%/100% 선택 시뮬레이션
- 모델·BIOS·Windows 정보와 읽기 전용 진단의 로컬 저장
- 삼성 WMI 클래스 `WmiAcpiVersion`, `WmiAcpiMethod`, `DataBuffer`의 **정의만** 확인하는 진단
- 사용자 확인 후 설치된 Samsung Settings 앱의 EXE·DLL을 제한적으로 복사하는 정적 분석 ZIP

진단은 삼성 DLL을 로드하거나 WMI 제어 메서드를 호출하지 않습니다. 클래스가 발견되어도 충전 제한 지원으로 판단하지 않습니다. 유효한 Windows 배터리 측정값을 그대로 표시하며, 0%도 유효한 값입니다.

Settings 분석은 HKLM의 정확한 Samsung Settings 등록 정보와 허용된 전용 설치 폴더에 한정합니다. **Settings 분석 파일 만들기**를 누른 뒤 포함 내용을 확인해야 추가 분석용 경로 탐색·복사를 시작합니다. 설치·아이콘 경로가 모두 없는 등록 앱에만 전용 후보 폴더 최대 6곳을 확인합니다. 제공된 경로가 거부된 경우에는 대체 조회를 하지 않습니다. 파일을 확보하지 못하면 원인을 기록한 보고서만 ZIP으로 생성합니다. 실행용 배포 파일 이름은 `ATIVBatteryGuard-SETTINGS-ANALYSIS.zip`입니다.

## 검증

2026-10-31(한국 시간) 이전 WMI 정의 진단판은 .NET Framework 4.8 x64 WPF/XAML 빌드와 portable 테스트 **78개 통과, 실패 0개, 건너뜀 0개**를 확인했습니다. 사용자의 후속 화면과 진단 파일에서 Windows 앱 실행, 배터리 62%·AC 연결 안 됨·방전 중 표시, 세 WMI 클래스의 실제 정의 조회도 확인했습니다. 이전의 0%는 당시의 정상 관측이며 현재 값으로 고정하지 않습니다.

새 Settings 앱 분석 기능의 .NET Framework 4.8 x64 WPF 빌드는 **경고 0개·오류 0개**로 성공했습니다. 새 경계 검사 30개를 포함한 portable 회귀 테스트는 **108개 통과·실패 0개·건너뜀 0개**입니다. 이번에 실제로 다시 실행한 결과이며 과거 테스트 수치를 재사용하지 않았습니다.

```powershell
dotnet run --project tests/ATIVBatteryGuard.PortableTests.csproj -c Release -- --report reports/portable-tests.json
```

WMI 정의 진단판의 노트북 실행은 확인됐지만 새 Settings 파일 수집의 Windows 동작은 아직 검증하지 않았습니다. 검증 범위와 Windows 수동 확인 절차는 [TEST_PLAN.md](TEST_PLAN.md)를 참고하세요.

사용법은 [USER_GUIDE.md](USER_GUIDE.md), 계층 구조는 [ARCHITECTURE.md](ARCHITECTURE.md), 하드웨어 근거는 [HARDWARE_RESEARCH.md](HARDWARE_RESEARCH.md), 개인정보와 권한은 [SECURITY.md](SECURITY.md)에 설명합니다.
