# 고정 보호 모드 1회 읽기 시험 판정 — 2026-11-07 한국 시간

**판정: 조건부 비실행 시험안 검토 가능, 실제 backend 연결·실행은 보류.** [완료 경계·근거 재검토](PROVIDER_COMPLETION_AND_READ_TRIAL_REVIEW.md)를 반영했습니다. 실행 준비 조건을 제안 작성 시점까지 확대하던 표현을 정정하며, 하드웨어 영구 미지원이나 드라이버 부재 판정은 아닙니다. 실제 충전 제어는 Unsupported입니다.

| 조건 | 확인된 범위 | 남은 조건 |
| --- | --- | --- |
| 같은 자원의 software admission | 내부 resource identity·취소/timeout 뒤 미완료 작업·peer 재진입 보호를 회귀 검증 | 직접 호출·물리 endpoint의 모든 alias까지 확대하지 않음 |
| 외부 협력 잠금 | 고정 이름의 lazy adapter, owner thread 획득/해제, 취소 CAS, abandon·release 실패 격리를 fake/unnamed Mutex로 검증 | 실제 Windows Global 접근 권한·관련 OEM 참여자 규약·상호 운용 미검증 |
| 관련 하위 완료 | task와 취소 callback 종료 전 해제하지 않는 경계 구현. 선택 snapshot 완료와 다른 private disposal은 다름을 재현 | 실제 공유 입력/응답에 대한 후속 접근 종료의 계약이 필요. 무관한 cleanup·모든 외부 활동 정지는 요구하지 않음 |
| 기존 EC 작업 입력 보존 | 식별된 입력은 요청 반환 전에 inline 소비하고 query upload·reader 쓰기와 분리됨 | 조회 자원과 교차하는 구체 근거가 생긴 IRQ/status만 조사. 전체 생산자 발견은 비실행 제안의 필수조건 아님 |
| 선택 실행 영역·gate·결과 귀속 | 정상 성공 조건의 boot proxy·legacy SMM 경로·reader 보존 관계. software gate는 source 초기닫힘/현재미관측 | 선택할 provider 분기와 관련 순서·전체 교환·응답 귀속 필요. handshake0인 안은 gate오류로 끝날 수 있으며 유용성 미확정 |

모델·BIOS·제조사 원본과 여러 해석 anchor는 임시 CandidateProfile 근거로 유지합니다. live 함수 포인터·EC 전체 hash를 직접 관측하지 못했다는 사실 하나만을 절대 중단 조건으로 쓰지 않습니다. 동시에 위 실제 미완료 연결을 정상성 가정이나 사후 내용 비교만으로 메우지 않습니다.

Global 접근 권한을 별도 사전 수집하는 것도 절대 조건은 아닙니다. 유한 Acquire가 접근 거부로 끝나면 하위 호출 없이 실패할 수 있습니다. 현재 보류의 실질 근거는 관련 참여 범위·provider 완료·실행 영역과 입력 비훼손의 미완료 연결입니다.

비실행 제안에는 지금의 조건부 모델·프로파일·미관측 사항을 명시하면 됩니다. 실제 연결 전 조건은 선택 경로/대상/gate, 관련 전체 교환 소유권, 관련 완료/입력 비훼손/결과 분류의 세 묶음입니다. 동결된 status 후보·같은 GUID/내용 비교를 반복해 준비 완료로 승격하지 않고, 미확인 status 생산자 전체를 단독 중단 조건으로도 쓰지 않습니다.

[현재 구체 시험안](FIXED_MODE_READ_PROPOSAL.md)은 최대1WMI 읽기 시도·고정 대상 byte 샘플0~1회·handshake/초기화0회입니다. 쓰기·임의 주소·자동 재시도·다른 명령 fallback은 없고 gate/FF/echo/귀속 불명은 판정불가로 끝납니다. 초기 닫힌 gate를 여는 것은 별도 호출·image-data 변경이므로 숨겨 포함하지 않습니다. 기존 작업 비훼손·고정 대상 무결성을 유지하고 저장 후보값을 실제 충전 적용으로 표시하지 않습니다. 실제 코드/실행 승인은 조건부 제안 검토와 별도입니다. 사용 완료된 과거 단발 예약은 확인·초기화·삭제·재사용·우회하지 않습니다.

이번 판정에 따라 사용자에게 새 실행이나 자료 제출을 요구하지 않습니다. [비실행 설계와 조건표](FIXED_MODE_READ_PROPOSAL.md)는 이 판정을 기준으로 유지합니다.
