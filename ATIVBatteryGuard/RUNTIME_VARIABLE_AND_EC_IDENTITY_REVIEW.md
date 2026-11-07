# Runtime 변수 서비스와 EC 이미지 근거 — 2026-11-07 한국 시간

후속 [Runtime 중계·고정 조회 검토](RUNTIME_PROXY_AND_FIXED_READ_REVIEW.md)에서 초기 구성 생산자와 나중의 host 함수 교체를 연결했습니다. 아래의 “별도 SMM adapter”는 SMM 전용이 아니며 host 초기화도 선택하는 주소 보정 adapter로 정정합니다. 가상주소 전환은 당시 현재 함수를 변환하며 초기 직접 함수를 복원하지 않습니다. 아래 수치는 당시 검사 기록으로 유지합니다.

**OS에 게시되는 변수 저장 진입점에서 EC 게시 후크까지 이어지는 조건부 소스 경로를 연결했습니다.** 이전의 runtime 보존만으로 추정하던 단계를 넘었지만, 현재 Windows의 실제 호출·경합을 관측한 것은 아닙니다. 실제 보호 설정 조회·충전 제어는 아직 미완료이며 제어는 Unsupported입니다.

[명령 소유권·최소 조회 설계](EC_COMMAND_OWNERSHIP_REVIEW.md)의 후속입니다. 기존 P05 원본과 저장 기록을 분석했고 하드웨어/OEM 호출·펌웨어 변수 쓰기는 하지 않았습니다. 새 실행용 요청이나 backend도 추가하지 않았습니다.

## 새로 연결한 OS 소비자

보유 `Runtime.efi`의 정상 boot 초기화는 호스트 RuntimeServices 표에 `SetVariable` wrapper를 게시합니다. 이를 SMM 내부용 별도 표의 wrapper와 구분했습니다. 초기화 실패·나중의 표 교체까지 같은 결과로 단정하지 않습니다.

선택한 경로는 다음과 같습니다.

| 구간 | 새로 확인한 연결과 조건 |
| --- | --- |
| OS에 게시된 SetVariable → 저장소 | 입력 검증·callback 조건을 통과한 nonvolatile 속성의 변수가 NV 저장 backend를 선택 |
| 구성에 따른 backend 선택 | flash adapter와 RAM adapter가 다름. 후속 분석에서 주소 보정 adapter도 host 초기화가 선택함을 확인했으며 SMM 전용으로 분류하지 않음 |
| 새 변수 추가 | 선택한 backend가 인수 전달을 거쳐 실제 begin/write/end 메서드에 사용됨 |
| 선택된 재구성 fallback | 임시 RAM 저장 뒤 선택한 persistence backend로 commit. 모든 기존 변수 수정이 이 fallback을 탄다는 뜻은 아님 |
| flash adapter → EC 후크 | 정확한 GUID 조회 결과와 메서드 receiver가 같고, 실제 게시 표의 begin/end가 앞서 연결한 조건부 EC 후크로 이어짐 |

따라서 모든 EC 게시자가 반드시 앞서 분석한 정상 SMM root/child 안에서만 실행된다고 가정할 수 없습니다. 현재 장치의 구성·flash probe 선택, callback 계속 진행·공간 상태, 실제 OS 호출은 미관측입니다. 일반 `GetVariable` 읽기에도 이 게시 경로가 있다고 보고한 것은 아닙니다. 현재 앱에 `SetVariable`이나 flash 실행 기능을 추가하지 않았습니다.

외부 소비자도 두 개를 별도로 연결했습니다. `SBDXE`의 PE 진입 경로는 정확한 flash interface를 조회한 뒤 begin/end를 연속 호출하며, 그 선택 구간에 flash 쓰기를 끼우지는 않습니다. `SMIFlash`는 InSmm 초기화와 등록된 software-SMI callback에서 다른 게시 GUID의 같은 메서드 표를 소비합니다. GUID 문자열 개수·같은 메서드 offset만으로 연결한 것이 아니며, 이 두 외부 경로 자체가 새 OS RuntimeServices 연결의 증거인 것도 아닙니다.

## guard의 역할과 남은 소유권 경계

정상 공급 경로에서는 host·SMM 변수 wrapper의 공유 guard 포인터를 확인했습니다. 진입은 busy byte 검사이며 PIC 마스크·다른 제어 필드를 저장·변경한 뒤 복원합니다. flash 메서드의 개별 guard와 변수 서비스의 외부 guard도 구분합니다. plain byte 검사 자체를 원자적인 다중 CPU 소유권 획득으로 취급하지 않습니다.

해당 제어 필드의 역할은 [coreboot 4.20 Lynxpoint 참고 헤더](https://raw.githubusercontent.com/coreboot/coreboot/4.20/src/southbridge/intel/lynxpoint/pch.h)의 SMI 제어 정의와 교차 확인했습니다. 저장된 삼성 ACPI의 base를 사용했으며 coreboot의 기본 base를 가져온 것은 아닙니다. 원본의 마스크·복원 패턴은 **SMI 발생 제어를 의도한 guard**라는 참고 근거가 됩니다.

이 해석은 현재 칩셋의 register 잠금·쓰기 효과, 이미 진행 중인 SMM의 정지, 모든 CPU의 배제나 공통 EC 소유권을 입증하지 않습니다. SABI 일반 callback이 같은 busy 규약에 참여한다는 연결도 확보하지 못했습니다. 반대로 실제 경합이나 이 경로의 위험 동작이 노트북에서 발생했다고 판정한 것도 아닙니다. 이를 확인하려고 변수 저장·flash·마스크 변경을 실행하지 않습니다.

## 현재 EC 이미지 근거와 버전 메타데이터

보존된 실제 사용자 TXT 17개에서는 명시적인 EC firmware major/minor·버전 필드를 확인하지 못했습니다. 현 앱과 준비/단발 도구는 `Win32_BIOS.SMBIOSBIOSVersion`을 수집하며 EC major/minor는 수집하지 않습니다. ACPI 수집 도구의 SMBIOS 제외 범위도 그대로입니다. BIOS 버전 일치와 분석 CAP의 EC 버전 anchor를 현재 EC 본문 동일성으로 합치지 않습니다.

새로 확인한 `SMBiosBoard` 경로는 EFI 변수 `ECRev1`·`ECRev2`를 읽어, 정확히 연결한 SMBIOS 제공자의 Type 0 EC release 필드에 복사·갱신합니다. 동일 GUID·실제 record finder·갱신 메서드 표와 수신 바이트의 흐름을 대조했습니다. 이 경로가 직접 현재 EC를 읽는다는 증거는 아닙니다.

보존된 PE의 정확한 이름·좁은 변형 검색에서 이 명명 변수의 생산자는 연결하지 못했습니다. 계산된 이름·비PE 변수 저장소·다른 이미지·외부 updater를 배제한 것은 아니며, 실제 EC 조회·정적 기본값·과거 updater cache 중 값의 기원과 갱신 주기는 미확정입니다. 향후 Windows가 제공하는 EC major/minor도 **펌웨어의 SMBIOS 메타데이터**와 **현재 EC에서 독립적으로 읽은 이미지 정보**를 구분해야 합니다.

현재 두 필드를 새로 수집하더라도 이 출처·신선도·본문 동일성의 간극은 닫히지 않습니다. 이번 오프라인 분석을 위해 새 수집 기능이나 동일 자료 재제출을 추가하지 않았습니다. 정보 미관측을 EC 불일치·드라이버 미설치·영구 기능 부재로 판정하지 않습니다.

## 최소 조회 설계에 반영한 판정

정상 SMM 내부의 순차화·WMI 협력 잠금 근거는 유지합니다. 그 범위를 host RuntimeServices 경로까지 자동으로 넓히지는 않습니다. busy 확인·SMI 마스크의 의도·응답 표식만으로 실행 전 명령·대상 무결성과 다른 작업의 메시지 보존을 보장했다고 하지 않습니다.

다음 핵심은 이 **OS 변수 서비스의 flash/RAM 구성 선택·후속 표 교체와 guard의 실제 동기화 범위**, 그리고 현재 모델의 EC 이미지 적합성을 입증할 직접 근거입니다. 이미 연결한 GUID·정상 SMM handler·버전 문자열을 다시 세어 기능 진전으로 보고하지 않습니다. 현 근거로는 실제 보호 조회 backend 연결을 보류하며 제어는 Unsupported를 유지합니다.

## 검증과 변경 범위

OS entry·backend·인수 전달·실제 메서드 receiver, 외부 소비자, 보존 기록과 EC 변수 소비자, SMBIOS 제공자·필드 연결을 원본 해시·바이트·표로 검산하고 독립 검토했습니다. [검사 기록](reports/runtime-variable-ec-identity-audit.json)은 새 근거와 기존 문맥을 구분합니다. byte/decode 검사는 서로 겹치며 앱 테스트나 전체 분석률이 아닙니다.

공개 참고 헤더 한 개를 기존 proxy·TLS 검증을 유지해 읽었고, 원본 크기·해시를 보존했습니다. 이는 개발 중 참고 자료 취득이며 앱의 네트워크 기능을 추가한 것이 아닙니다. 삼성 원본·사용자 TXT·전체 명령어·주소·게시 값은 배포하지 않습니다.

변경은 분석 문서·정제한 기록·재개 메모입니다. C#/WPF·Python 개발 도구·EXE·기존 ZIP은 변경하지 않았고 빌드·단위 테스트는 이번에 실행하지 않았습니다. C#437개·빌드 경고/오류0은 이전 `5d77df5`, Python88개는 이전 `e7b067a` 기록입니다.

원본 실행·에뮬레이션, 하드웨어/OEM·기존 단발 예약 접근, 드라이버·서비스·보안·펌웨어 변경은 없었습니다. 실제 충전 제어·보호 상태 조회 성공을 관측한 것은 아니며, 추가 노트북 시험·동일 자료 재제출은 필요하지 않습니다.
