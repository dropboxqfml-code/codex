# Windows 부팅 방식으로 조회 경로 범위 구분 — 2026-11-08

**기존 삼성 파일 정보 보고서에 현재 Windows의 BIOS/UEFI 부팅 방식을 추가했습니다.** 기존 자료에는 없던 정보이며, 미확정 Runtime 경로가 현재 부팅에 적용되는지 좁히기 위한 표준 읽기 전용 메타데이터입니다. 실제 보호 설정을 읽거나 충전 제한을 활성화하는 기능은 아닙니다. 공개 SDK 시험 entry는 `ReadSpecificationUnavailable`, 보호 조회·충전 제어는 `Unsupported`를 유지합니다.

[프로그램 ZIP](../downloads/ATIVBatteryGuard-BOOT-FIRMWARE.zip) · [SHA-256](../downloads/ATIVBatteryGuard-BOOT-FIRMWARE-SHA256SUMS.txt) · [정제 검증 기록](reports/boot-firmware-validation.json)

## 확인 방법과 결과의 의미

ZIP 하나를 새 폴더에 전부 풀고 `ATIVBatteryGuard.exe`를 일반 권한으로 실행합니다. 기존 **삼성 파일 정보 만들기**를 선택하면 TXT에 **현재 Windows 부팅 방식**의 조회 상태와 `관측: BIOS / UEFI / Unknown`이 표시됩니다. 분석 ZIP이나 삼성 DLL을 함께 풀 필요는 없습니다.

새 정보는 이 두 항목만 전달할 수 있습니다. 전체 TXT·기존 진단·삼성 DLL·EXE를 다시 제출할 필요는 없습니다. 새 OEM 호출 시험이나 관리자 비교도 아닙니다.

| 관측 | 적용할 수 있는 해석 | 확대하지 않는 결론 |
| --- | --- | --- |
| 정상 조회 · BIOS | 현재 Windows가 legacy BIOS 방식으로 부팅함. 표준 Windows EFI 변수 API에서 Runtime proxy로 가는 특정 OS 소비경로는 적용 대상에서 제외 가능 | 다른 firmware/SMM 호출자·드라이버·보호 기능·저장된 hook 자체가 없다는 뜻은 아님 |
| 정상 조회 · UEFI | 현재 Windows가 UEFI 방식으로 부팅함. 해당 OS 경로를 배제할 수 없음 | 실제 proxy/cache·typed dispatch·indexed 보호 순서나 충전 제어 지원을 확인한 것은 아님 |
| 정상 조회 · Unknown | API 성공과 유형 불명을 구분해 보존 | BIOS나 UEFI로 추정하지 않음 |
| 권한 거부·API 미가용·오류·시간 초과·형식 오류 | 해당 조회 상태를 표시하고 경로 판단 보류 | 실패 때 남은 out 값이나 기본값을 BIOS로 해석하지 않음 |
| 예전 IPC v5 결과 | 부팅 정보는 `NotCollected`로 보존 | 옛 보고서에 현재 부팅 관측을 새로 만들어 넣지 않음 |

현재 클라우드에서 사용자 노트북의 부팅 결과를 관측한 것은 아닙니다. BIOS 결과가 나온다고 자동으로 실기 시험을 허용하거나 실제 제어를 활성화하지 않습니다. 관련 경로와 남은 보호 조건에 적용하는 검토가 별도로 필요합니다.

## 공식 계약과 구현 범위

MicrosoftDocs/sdk-api의 commit `656e9656bfaef34dd29cd7ee9e1146aec17e924c`에서 다음 공식 문서를 읽고 pin을 보존했습니다.

- [GetFirmwareType](https://github.com/MicrosoftDocs/sdk-api/blob/656e9656bfaef34dd29cd7ee9e1146aec17e924c/sdk-api-src/content/winbase/nf-winbase-getfirmwaretype.md): 표준 Kernel32 조회, BOOL 성공/실패와 실패 시 GetLastError 계약.
- [FIRMWARE_TYPE](https://github.com/MicrosoftDocs/sdk-api/blob/656e9656bfaef34dd29cd7ee9e1146aec17e924c/sdk-api-src/content/winnt/ne-winnt-firmware_type.md): BIOS와 UEFI를 실제 부팅 방식으로 설명하고 Unknown과 미구현 Max를 구분.
- [SetFirmwareEnvironmentVariableW](https://github.com/MicrosoftDocs/sdk-api/blob/656e9656bfaef34dd29cd7ee9e1146aec17e924c/sdk-api-src/content/winbase/nf-winbase-setfirmwareenvironmentvariablew.md): legacy BIOS 방식에서 표준 EFI 변수 API가 지원되지 않는다는 범위 근거. **이 함수는 문서만 참고했으며 선언·호출·dummy probe·권한 변경을 추가하지 않았습니다.**

추가된 native 호출은 기존 보고서 worker 안의 `GetFirmwareType` 최대1회뿐입니다. 앱 시작·주기적 배터리 조회에 새 수집을 연결하지 않았습니다. 기존 worker 전체의 10초 한도와 실패 시 관측을 폐기하는 규약을 유지합니다. 부팅 정보만 별도의 반복·fallback·권한 상승으로 다시 조회하지 않습니다.

worker의 시간 초과는 완료 보고서를 회수하지 못한 상태입니다. 그 상태만으로 GetFirmwareType 자체가 멈췄다는 원인을 판정하지 않습니다.

표시 모델은 조회 상태와 유형 enum만 보유합니다. raw native 오류 코드·예외 원문·경로·계정·serial·고유 ID는 결과에 넣지 않습니다. 읽기 실패는 out 값을 버리고, 미정의 성공 유형은 InvalidResponse로 분류합니다. 로컬 IPC v6는 두 정수 필드와 enum/status-type 조합을 검사하며, 문자열·boolean·소수·지수 등 강제 변환이나 불일치를 받지 않습니다. v5의 부팅 항목 없는 결과만 호환합니다. 파일·드라이버 조회 실패와 독립적으로 완료된 부팅 관측은 보존합니다.

## 별도로 확인한 새 source 범위

기존의 동결된 P05 GUID/operand·entry/state 검색은 반복하지 않았습니다.

- P05의 231개 pinned PE에 새로 한정한 Debug/CodeView·COFF symbol·Export directory metadata는 모두 선언 범위가 비어 있었습니다. 그 metadata로 새로운 공급자/entry를 선택하지 못했습니다. 본문·일반 문자열·GUID 검색을 재실행하거나 전체 제공자 부재로 판정하지 않습니다.
- 이미 보존된 동일 모델 P04의 changed FV4/5/6 출력313개에서 표준 통신 GUID를 한 번 선택 검사했습니다. 알려진 Nvram 소비자 한 곳만 관측했고 새 등록 후보는 없었습니다. 선택 framework 세 모듈의 code/data section은 P05와 같았지만 전체 이미지·상수 영역까지 같다는 뜻은 아닙니다. 이 결과를 P05의 실제 통신 경로나 현재 부팅 증거로 사용하지 않습니다.

두 범위 모두 새 공급자·typed 경로·공통 보호 순서 근거는 0이며 동결했습니다. 새 메타데이터 기능을 통신 경로 복구로 보고하지 않습니다. [이전 미완료 판정](INDEXED_ORDERING_CONTRACT_REVIEW.md)은 실제 해당 순서의 새 근거가 생길 때 갱신합니다.

## 검증과 배포 경계

새18개를 포함한 C# **646개 통과·실패0·skip0**입니다. 기존628개도 재실행했습니다. 새10개는 모델/native 대역·오류/개인정보·ABI, 8개는 IPC 호환·형식·관측 분리·권한 비활성 검증입니다. portable 테스트 빌드와 전체 net48 참조 Release 빌드는 각각 경고·오류0입니다. 실제 Windows/.NET48 runtime·GUI·GetFirmwareType 호출은 이 클라우드에서 실행하지 않았습니다.

ZIP은 프로그램3개 파일, 안내, build metadata, 체크섬의 **6개 항목**입니다. 빌드 바이트 일치·내부 체크섬·CRC·관리 x64·.NET48 설정·컴파일된 manifest의 asInvoker/uiAccess=false를 확인했습니다. 미서명 개발 빌드이며 Windows 실기 검증 결과를 만들어 넣지 않았습니다. 기존 다운로드 파일은 보존합니다.

삼성 원본·펌웨어·사용자 TXT·다른 실험 실행 파일은 포함하지 않습니다. 드라이버/서비스/보안 설정 변경, 삼성 DLL 초기화·OEM 명령·EFI 변수 접근·펌웨어 쓰기·새 단발 예약·과거 소모 예약 접근/재사용은 없습니다. 새 boot 결과는 제어 capability나 승인 flag가 아닙니다. 실제 충전 제어는 계속 Unsupported입니다.
