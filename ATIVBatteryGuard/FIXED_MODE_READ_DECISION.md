# 고정 보호 모드 1회 읽기 시험 판정 — 2026-11-07 한국 시간

**판정: 보류. 현재 자료로 새 하드웨어 조회를 실행하거나 그 실행 코드를 연결하지 않습니다.** [협력 교환 구현·검증](COOPERATIVE_EXCHANGE_OWNERSHIP_UPDATE.md)을 반영한 판정이며, 하드웨어 영구 미지원이나 드라이버 부재 판정은 아닙니다. 실제 충전 제어는 Unsupported입니다.

| 조건 | 확인된 범위 | 남은 조건 |
| --- | --- | --- |
| 같은 자원의 software admission | 내부 resource identity·취소/timeout 뒤 미완료 작업·peer 재진입 보호를 회귀 검증 | 직접 호출·물리 endpoint의 모든 alias까지 확대하지 않음 |
| 외부 협력 잠금 | 고정 이름의 lazy adapter, owner thread 획득/해제, 취소 CAS, abandon·release 실패 격리를 fake/unnamed Mutex로 검증 | 실제 Windows Global 접근 권한·관련 OEM 참여자 규약·상호 운용 미검증 |
| 실제 하위 완료·프로세스 수명 | task와 취소 callback 종료 전 해제하지 않는 경계 구현 | 실제 provider의 success/fault/cancel 완료 계약·프로세스 종료 후 외부 진행은 미입증. 기존 OneShot을 그대로 연결하지 않음 |
| 기존 EC 작업 입력 보존 | 식별된 입력은 요청 반환 전에 inline 소비하고 query upload와 분리됨 | 관련 외부 status/IRQ·hardware continuation 의미는 새로 연결하지 못함 |
| 실행 영역과 결과 귀속 | 정상 성공 조건의 boot proxy·legacy SMM 경로·고정 reader의 선택 보존 관계 | 표준 통신의 실제 provider→typed dispatch와 전체 WMI 교환·응답 귀속 계약은 미완료 |

모델·BIOS·제조사 원본과 여러 해석 anchor는 임시 CandidateProfile 근거로 유지합니다. live 함수 포인터·EC 전체 hash를 직접 관측하지 못했다는 사실 하나만을 절대 중단 조건으로 쓰지 않습니다. 동시에 위 실제 미완료 연결을 정상성 가정이나 사후 내용 비교만으로 메우지 않습니다.

Global 접근 권한을 별도 사전 수집하는 것도 절대 조건은 아닙니다. 유한 Acquire가 접근 거부로 끝나면 하위 호출 없이 실패할 수 있습니다. 현재 보류의 실질 근거는 관련 참여 범위·provider 완료·실행 영역과 입력 비훼손의 미완료 연결입니다.

재검토의 기준은 **해당 미완료 조건을 줄이는 새 근거**입니다. 현재 동결한 인접 status 후보·같은 GUID 검색·같은 잠금/내용 비교를 반복해 준비 완료로 승격하지 않습니다. 실제 Global 협력·provider 완료와 관련 실행 영역/하드웨어 연결이 검토 가능한 근거로 이어질 때 이 표를 갱신합니다.

그때도 목표는 저장 보호 모드의 고정 한 바이트1회 읽기이며 쓰기·임의 주소·자동 재시도·다른 명령 fallback은 없습니다. 기존 작업 비훼손·조회의 안전한 실패·고정 대상 무결성·오귀속 방지를 유지하고 저장 후보값을 실제 충전 적용으로 표시하지 않습니다. 구체 조건이 충족된 뒤에만 별도 승인 대상인 실제 시험안을 제시합니다. 사용 완료된 과거 단발 예약은 확인·초기화·삭제·재사용·우회하지 않습니다.

이번 판정에 따라 사용자에게 새 실행이나 자료 제출을 요구하지 않습니다. [비실행 설계와 조건표](FIXED_MODE_READ_PROPOSAL.md)는 이 판정을 기준으로 유지합니다.
