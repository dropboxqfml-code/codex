# PI 통신 계약과 고정 조회의 보호 범위 — 2026-11-08

**조건부 조회 제안을 검토할 수 있습니다. 실제 조회 준비 완료나 실행 승인은 아닙니다.** 표준 제공자의 기계코드를 복구하는 것만을 유일한 해법으로 두지 않습니다. 적용 가능한 정상 통신 계약과 플랫폼의 보호 순서 근거로도 연결을 설명할 수 있습니다. 다만 메시지 전달·함수 반환과 공유 indexed 자원의 상호 배제는 다른 성질입니다. [통합 조회 명세](FIXED_READ_TRIAL_SPECIFICATION.md)에 이 구분을 적용했습니다. 공개 entry는 `ReadSpecificationUnavailable`, 보호 조회·충전 제어는 `Unsupported`입니다.

## 출처 수준과 확보한 문구

UEFI 사이트의 PI HTML 조회는 기본 환경 프록시 연결 실패 뒤 동일 요청의 정상 프록시 재시도에서 HTTP 403으로 끝났습니다. 원문을 읽었다고 주장하거나 403의 원인을 규격 내용으로 해석하지 않습니다. 대신 공식 TianoCore 저장소에서 다음 자료를 commit으로 고정했습니다. 원문 미확보 자체를 새 실기 필수조건으로 만들지는 않습니다.

| 자료 | 확인한 내용 | 적용 한계 |
| --- | --- | --- |
| [UDK2014 SmmCommunication.h](https://github.com/tianocore/edk2/blob/3ccd6d8b75b7fab66a35da9e77312eaca167c0f0/MdePkg/Include/Protocol/SmmCommunication.h) | PI 1.2의 인터페이스라고 명시. non-SMM driver와 SMM handler 간 send/receive, 반환 시 CommSize를 설명 | 공식 프로젝트의 표준 전사 헤더입니다. 규격 원문이나 P05의 채택 PI 버전 증명이 아닙니다. 성공 문구는 **“The message was successfully posted.”**이며 명시적인 synchronous 문장은 없습니다. |
| [UDK2014 PiSmmCis.h](https://github.com/tianocore/edk2/blob/3ccd6d8b75b7fab66a35da9e77312eaca167c0f0/MdePkg/Include/Pi/PiSmmCis.h) | SmiManage의 HandlerType, NULL의 root 의미, SMM 내 handler 등록 | 특정 통신 제공자가 실제로 어느 HandlerType을 전달하고 어느 CPU/root에서 호출하는지는 보여주지 않습니다. |
| [UDK2014 UefiAcpiDataTable.h](https://github.com/tianocore/edk2/blob/3ccd6d8b75b7fab66a35da9e77312eaca167c0f0/MdePkg/Include/Uefi/UefiAcpiDataTable.h) | HeaderGuid를 메시지 형식 구분자로 설명 | 이 문구만을 실제 GUID dispatch 호출 edge로 바꾸지 않습니다. |
| [UDK2014 PiSmmIpl.c](https://github.com/tianocore/edk2/blob/3ccd6d8b75b7fab66a35da9e77312eaca167c0f0/MdeModulePkg/Core/PiSmmCore/PiSmmIpl.c#L418) | 대표 구현에서 공유 입력 → Trigger → 반환 뒤 결과 읽기, 별도 조건의 직접 SmiManage(HeaderGuid) → 반환 순서 | **참조 구현**입니다. P05 제공자 본문, Trigger의 하위 계약, 모든 통신의 동일 root 귀속 증거로 사용하지 않습니다. |
| edk2-stable202408의 [SmmCommunication.h](https://github.com/tianocore/edk2/blob/b158dad150bf02879668f72ce306445250838201/MdePkg/Include/Protocol/SmmCommunication.h), [MmCommunication.h](https://github.com/tianocore/edk2/blob/b158dad150bf02879668f72ce306445250838201/MdePkg/Include/Protocol/MmCommunication.h), [PiSmmCis.h](https://github.com/tianocore/edk2/blob/b158dad150bf02879668f72ce306445250838201/MdePkg/Include/Pi/PiSmmCis.h), [PiMmCis.h](https://github.com/tianocore/edk2/blob/b158dad150bf02879668f72ce306445250838201/MdePkg/Include/Pi/PiMmCis.h) | 현대 MM 명칭·SMM alias와 관련 인터페이스 설명의 비교 자료 | 2024년 정의를 2014년 BIOS의 구현·준수 증명으로 소급하지 않습니다. |

UDK2014는 공식 저장소의 **branch**이며 위 고정 commit을 사용했습니다. 이름에 포함된 연도만으로 그 head의 모든 파일을 2014년 작성본이라고 단정하지 않습니다. 취득한 8개 파일의 URL·크기·해시·선택 줄은 [정제 기록](reports/pi-contract-application-audit.json)에 남깁니다. 원문 자료 전체나 삼성 원본을 배포하지 않습니다.

## 참조 구현이 보여주는 순서

PiSmmIpl.c의 선택 Communicate 본문에서 non-SMM이고 entry가 등록된 분기는 공유 buffer/size를 저장하고 Trigger를 호출한 뒤 크기·상태를 읽습니다. 별도 direct 분기는 HeaderGuid를 SmiManage에 전달하고, 그 호출에서 돌아온 뒤 크기와 반환 상태를 처리합니다.

direct 분기를 모두 “이미 SMM 안”으로 부르지 않습니다. 해당 참조 코드에는 가상주소 전환 전·SMRAM open/unlocked 등의 조건에서 바깥 호출자에게도 허용되는 경로가 있습니다. 이 초기화기 경로를 P05 Windows 기간에 남는 direct-host 게시자로 추가하지도 않습니다. 대표 코드의 국소 호출 순서와 그 하위 구현의 동기·실행 영역 보장은 별도입니다.

정상 API가 선택된 등록 handler와 결과를 반환한다는 계약을 설계 전제로 명시할 수는 있습니다. 그것을 헤더의 성공 코드 한 줄에서 도출했다거나 P05의 실제 제공자 함수를 발견했다고 보고하지 않습니다. API 정상 전달·반환, 실제 P05의 handler 선택, 해당 handler의 동일 보호 순서 귀속을 각각 구분합니다.

## 남는 차이는 동일 자원의 보호 순서

두 개의 제한된 부분순서 모형을 검산했습니다. 실제 PI 전체·P05 scheduler·CPU·EC의 모델이나 에뮬레이터가 아닙니다. 이벤트는 주소와 명령을 포함하지 않는 기호입니다.

- 각 호출의 enter → index 선택 → data 접근 → return을 지킨 70개 순서에도, 다른 호출이 선택과 접근 사이에 index를 바꾸는 기호상 순서가 있습니다. 각 호출이 동기로 돌아온다는 전제만으로 이를 제외할 수 없습니다. 같은 자원에 대한 두 handler의 비중첩 전제를 추가하면 허용 순서는 2개이고 이 모형의 간섭은 없어집니다.
- 입력 저장 → handler enter → handler return → 공유 frame 읽기의 두 교환에서 70개 순서를 살폈습니다. handler 구간끼리는 순차여도 반환 후 frame 읽기 전에 다음 입력이 쓰이는 순서가 있습니다. 전체 교환 소유권 전제를 추가하면 허용 순서는 2개가 됩니다.

이는 제한된 약속만으로 빠진 순서 관계를 추론할 수 없다는 검산입니다. **현재 P05에 그런 경쟁자가 있거나 실제 race가 발생했다는 발견은 아닙니다.** 두 집합은 서로 다른 추상 모형이며 140개 앱 테스트·펌웨어 coverage로 합산하지 않습니다. 이미 확보한 SMM/WSABI 보호 경계를 재사용한 명세 적용이며 새 firmware 함수 발견은 0개입니다.

## P05 분기에 적용한 판단

| 분기 또는 구간 | 이번 적용 |
| --- | --- |
| 정상 proxy 설치 + NULL cache + 정상 legacy 수신/private wrapper 초기화 | 기존에 연결한 같은 정상 root의 순서 근거를 유지합니다. 표준 제공자를 추가 필수조건으로 두지 않습니다. |
| 정상 proxy 설치 + nonnull 표준 객체 | 정상 전달·반환 계약을 명시한 조건부 설계는 가능합니다. 같은 indexed 자원의 보호 순서에 귀속된다는 근거는 별도로 적용해야 합니다. 제공자 본문 복구는 가능한 해법 중 하나이며 유일한 해법은 아닙니다. |
| 정상 교체 조건이 성립하지 않는 direct-host 예외 | 그 예외에 해당하는 보호가 필요합니다. 정상 proxy 분기에 초기 host 경로를 동시에 남기지 않습니다. 현재 예외가 발생했다고 관측하지 않았습니다. |
| 바깥 WMI 입력 저장·최종 frame 회수 | 식별된 WSABI 협력 호출자의 전체 교환 소유권을 적용합니다. PI 통신·같은 SMM root만으로 이 바깥 구간까지 보호하지 않습니다. |

기존 inline 입력 소비·buffer 분리·ISR 보존·정상 legacy 순서의 긍정 근거는 유지합니다. 알려진 worker의 입력 비훼손을 다시 미해결로 돌리거나 모든 writer/IRQ 부재·live hash·gate-open 관측을 요구하지 않습니다. source 초기 gate 닫힘은 A의 값 획득 유용성 한계입니다.

따라서 이번 결과는 **검토 가능한 조건부 명세 완성, 실행 연결 보류**입니다. 남은 것은 관련 indexed 게시자의 동일 보호 순서 귀속과, 고정 template 및 실제 SDK 수명에 이 계약을 적용하는 검토입니다. 새 제공자 기계코드나 현재 하드웨어 값을 확보한 결과는 아닙니다. 같은 후보/GUID/operand 검색은 동결합니다.

## 검증과 변경 범위

원문 파일은 데이터로 읽고 출처·문구·선택 참조 구현을 대조했습니다. root의 기호 순서 검산과 기존 proof pin 2개 검증을 통과했습니다. 독립 읽기 검토 결과와 출처 pin은 정제 기록에 보관합니다. C#/SDK/테스트·배포 EXE/ZIP을 바꾸지 않아 이번 빌드/C# 테스트는 재실행하지 않았습니다. **628개 통과와 전체 net48 Release 경고·오류 0은 ae8f8e7의 이전 검증 기록**입니다.

실제 WMI/OEM/하드웨어/Global 객체·사용 완료된 과거 예약 접근·재사용, 삼성 원본 실행·로드·에뮬레이션, 실행 요청·주소 조합·frame·난수 생성기, 드라이버/서비스/보안/펌웨어·클라우드 환경 변경은 없습니다. 지금 노트북에서 실행하거나 자료를 다시 제출할 일은 없습니다.
