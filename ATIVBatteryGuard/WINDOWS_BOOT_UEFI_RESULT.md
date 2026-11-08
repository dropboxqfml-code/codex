# 부팅 방식 사용자 실행 결과 — 2026-11-08 수신

사용자가 전달한 실행 결과는 다음과 같습니다.

```text
조회 상태: 정상 조회 완료 (Complete).
관측: UEFI. 현재 Windows는 UEFI 방식으로 부팅했습니다.
```

요청한 두 항목이 모두 전달됐습니다. 이 결과는 **해당 실행 당시의 UEFI 부팅 관측**으로 기록합니다. 실행 시각·권한·노트북의 배포 파일 해시는 전달되지 않았으며 수신일을 실행일로 추정하지 않습니다. 새 부팅 항목의 조회·표시는 사용자 보고로 확인됐지만 전체 GUI·SDK·펌웨어 기능을 검증한 결과는 아닙니다.

UEFI이므로 legacy BIOS 부팅을 근거로 **표준 Windows EFI 변수 API → Runtime proxy라는 특정 OS 소비경로를 제외하는 안은 이 관측에 적용할 수 없습니다.** 해당 경로를 분석 범위에 유지합니다. 실제 EFI 변수 API 접근 성공·현재 proxy/cache·통신 제공자 존재·typed 처리기 선택·같은 indexed 보호 순서는 이 결과에 포함되지 않습니다. Secure Boot·관리자 권한·배터리 보호 모드·충전 제어 상태도 추론하지 않습니다.

따라서 실제 보호 조회 전의 순서 조건은 여전히 미완료이며, 공개 SDK entry `ReadSpecificationUnavailable`과 보호 조회·충전 제어 `Unsupported`를 유지합니다. 기존 정상 legacy fallback·정상 SMM stream의 조건부 긍정 근거도 유지합니다. UEFI 관측은 legacy fallback의 cache가 nonnull이라는 뜻이 아닙니다. Windows의 부팅 방식과 proxy 내부 통신 대안은 다른 구분입니다.

[정제 관측 기록](reports/windows-boot-user-observation.json)에 사용자 보고와 미관측 사항을 구분했습니다. [기능·공식 계약](WINDOWS_BOOT_FIRMWARE_UPDATE.md), [미완료 순서 판정](INDEXED_ORDERING_CONTRACT_REVIEW.md)은 같은 범위를 적용합니다.

추가 TXT·DLL·EXE·관리자 비교·같은 부팅 조회 반복은 필요하지 않습니다. 이번 결과만으로 동결한 GUID/operand·entry/state·metadata/P04 조사를 재개하거나 firmware 시험 코드를 연결하지 않습니다. 재개에는 여전히 관련 실제 경로·플랫폼 순서 계약·공유 자원 owner의 구체적인 새 근거가 필요합니다.

이번 변경은 관측 기록과 문서뿐입니다. 코드·EXE/ZIP을 바꾸지 않아 빌드·C# 회귀는 재실행하지 않았습니다. 646개 통과·portable/전체 net48 Release 경고·오류0은 `f474e6f`의 이전 검증입니다. 클라우드에서 실제 Windows/API·OEM/하드웨어/Global 객체·과거 예약에 접근하거나 설정을 변경하지 않았습니다.
