# Settings 원본 확보·호출자 분석 재개 메모 — 2026-11-06 한국 시간

**분석 재개 후속:** [OEM 메뉴·상태·전송 대조](OEM_UI_SUPPORT_CONTRACT_REVIEW.md)에서 저장된 원본을 재검증하고 SUS 계약의 독립 감사·UI 메뉴 생성 연결을 완료했습니다. tail은 호출자가 덮지 않은 버퍼 내용이며 반드시 비영이거나 과거 요청과 다른 값이라는 증거는 아닙니다. setter의 후속 helper 전체 callgraph는 미완료여서 모든 하위 read-back 부재를 단정하지 않습니다. 아래는 중지 시점의 기록입니다.

사용자가 현재 작업을 저장하고 다음에 개발을 이어가도록 요청해 **새 분석을 중지했습니다.** 아래는 확보한 자료와 중간 정적 관측입니다. 프로그램 소스·테스트·EXE·기존 ZIP은 변경하지 않았고 환경도 게시하지 않았습니다. 실제 충전 제어는 Unsupported입니다.

## 확보와 컨테이너 검증 완료

게시된 새 환경에서 명령 실행, current/running·enforced, `downloadcenter.samsung.com` 허용 적용을 확인했습니다. 기존 설정을 다시 적용하거나 새 초안을 저장할 필요가 없었습니다. 다음 실제 주소의 GET은 HTTP200이었고 추가 리다이렉트 없이 원본을 받았습니다.

[BASW-83876A21.ZIP](https://downloadcenter.samsung.com/content/SW/201407/20140715105012027/BASW-83876A21.ZIP)

| 대상 | 바이트 | SHA-256 |
| --- | ---: | --- |
| 수신 ZIP | 126,414,820 | `a501fde3b9870e3840d1b4561255c70e3cece4e9426c1070ff8481446d8ba3b7` |
| Win7 EasySettingsSetup.msi | 68,843,008 | `decec529c8ee07826d17a1926c27e5b2d539ac532047c3fe7874815cc671c569` |
| Win8 SettingsSetup.msi | 61,521,920 | `83883e2e0a363931934d74ea5f3ab122202ab2edc0af2944cc9a7d9336573369` |
| Win8 sSettings.exe | 2,623,808 | `8cdea163b0e3349e4651046265afda89a1e8c7f4d4a021209b44b905c3e581f2` |
| Win8 EasyControlCenter2.dll | 3,457,856 | `83c17bd9c0238d135fbebbbdb030b8c290deda923b169e109f24216a7c032185` |
| 공통 EasySettingsCmd.dll | 1,188,672 | `648b0facab46ee8837c70b0a337546b826cf01a7087b1949dbe8758ff76a4f73` |

ZIP은 디렉터리2개를 포함한9항목/파일7개이며 CRC·중복/대소문자 충돌·심볼릭 링크·위험 경로 검사를 통과했습니다. 실제 비압축 합계131,598,830과 수신 길이는 이번 BOM의 크기 필드와 일치했습니다. 이는 이번 관측의 일치이며 메타데이터 크기나 FileVer를 암호학적 검증으로 취급하지 않습니다.

실제 내부 Win8 MSI와 Settings 파일2.0.0.89를 확인했습니다. MSI ProductVersion은 양쪽2.0.1이며 파일 버전과 별개입니다. MSI File table은 Win7 349개/Win8 302개를 매핑했습니다. Win8 CAB302개를 고정 비공개 디렉터리에 데이터로 추출했고 선언 크기와 대조했습니다. 외부 Inst.ini의 Win7/Win8 선택은 OS 분기이며 모델 지원 가드가 아닙니다.

원본 설치·EXE/DLL/CLR 로드·OEM/AML 실행은 하지 않았습니다. trusted ZIP/7zip·MSI 데이터 파서·pefile/capstone으로만 읽었습니다. 받은 파일의 출처·길이·해시는 고정했지만 제조사 서명 신뢰·현재 ATIV 적용성은 별도로 미확정입니다.

## 호출자 정적 관측 — 전체 교차 검토는 미완료

### SUS getter/setter와 과거 단발 입력의 차이

CmdServer/SUS.dll1.0.5.7 x86의 SHA는 `650f8fc4480ee64e377553886f7c67530afd9773e1f85d4154f46da903235a89`입니다. Win7·Win8의 대응 파일이 같습니다.

- Getter export RVA FE20 → CC10은16바이트를0으로 준비해0x0B를 먼저 호출합니다. 반환 첫 바이트 bit3 또는 그 호출 결과의 AL 비영이면 outStatus2입니다.
- 통과하면 **같은 버퍼의 첫 바이트만0x80으로 바꾸고0x65를 호출합니다. 호출자는0x0B 직후 나머지15바이트를 덮지 않습니다.** 그 값이 실제로 비영인지·0x0B가 모두 썼는지는 미확정입니다. 과거 단발 시험의 고정80+zeros와 전체 입력·호출 순서의 동등성을 단정할 수 없습니다.
- 0x65 첫FF는 outStatus2, 첫01은1, 나머지는0입니다. 0x65 API 결과는 검사하지 않고 외부 getter API는1을 반환합니다. 이 분류만으로 현재 보호 상태나 실패 원인을 검증하지 못합니다.
- Setter export FDE0 → CB80은0x66/첫81 또는80을 전송하고, 하위 결과 검사 없이1을 반환합니다. 이 성공 반환은 실제 적용·read-back 증거가 아닙니다.

SOSI/SUS1.0.6.1 x86 SHA `c6a3e78ab6a4899c76e2cac5d816f8dc86a3596518bfa8a45c379e2a10b9ee95`, x64 SHA `d471164bd5a997bed4620121188f0b18d246c1532bd95f76b882d7c4a729d5ac`도 두 OS 패키지에서 같습니다. 이 변형은11바이트를 재사용하고0x0B API 결과 검사가 없습니다. getter는 x86 C170/x64 DA10입니다. **x64 setter 명령 본문은10F20이며5EC0는 popup/config helper입니다.** 서로 다른 변형과 RVA를 혼합하지 않습니다.

이는 비교용 OEM 호출자의 계약 차이입니다. 현재 모델의0x0B 실제 응답, P05ACJ의 동적 flag 값·0x65 처리자·FF 원인은 확인하지 않았습니다. 선행 호출 누락을 새 OEM 시험이나 추가 승인 필요로 해석하지 않습니다. 기존1회 예약 표식은 읽거나 변경하지 않습니다.

### Cmd 상태·메뉴 지원·조건부 쓰기

공유 EasySettingsCmd.dll의 분석 대상은 위 SHA648b…입니다. 현재까지 고정한 실행 본문은 다음과 같습니다.

| 본문 RVA | 관측 |
| --- | --- |
| 5FBD0 / GetStatus | SUS getter 실패 시 캐시2. 결과 index0에 캐시 반환. 설명 문자열 D4658은1=enable/0=disable/2=not support라고 이름 붙임 |
| 5F930 / OnEnable, 7AB80 / OnDisable | SUS setter1/0의 반환1에 따라 소프트웨어 캐시1/0 갱신. 이 반환은 read-back 비교에 조건부인 성공이 아님. 하위 helper 전체는 미검토 |
| 83250 / GetMenuExistStatus, 2C780 helper | getter 성공이고 상태2가 아닐 때 메뉴 지원1, 그외0. 이후 지원 결과를 캐시 |
| 9D660 / EASYCMD_Init | getter 갱신과 지원 캐시 초기화 호출 포함 |
| 5FD60 / SetCountFile | 호스트 EXE 폴더 conf.ini의 BatteryLifeExtender/nValue=-1이면 getter 호출, 출력0일 때 setter0 호출. getter 반환 무시 |

OEM의 `not support`는 여러 조건을 합친 UI 열거값입니다. 이를 현재 노트북의 기능 부재로 옮기지 않습니다. setter 반환에 따라 바뀌는 캐시도 펌웨어 적용 성공이 아닙니다. SetCountFile의 조건부 쓰기 때문에 이 원본을 읽기 전용 진단으로 실행하지 않습니다. conf.ini 값을 펌웨어 부팅 횟수로 해석하지 않았습니다.

### 전송·모델 문자열·UI 연결

Wrapper는 호스트 EXE 디렉터리의 DLL에서 GetEasySettingsModuleType()==0을 선택해 EASYCMD 주소를 연결합니다. 이는 BIOS 전송 DLL 선택과 별개입니다. MSI상 EasySettingsCmd.dll과 Server.exe는 같은 CmdServer 논리 디렉터리입니다.

Cmd DLL의9850은 GetVersionExW의 보고 버전을 분류하고8C60은 해당 enum으로 SABI3/WSABI/SABI2를 선택합니다. major6/minor2·3 분류는 WSABI 쪽입니다. SUS1.0.5.7 loader B280에도 별도 선택 로직이 있습니다. enum9의 GetBiosMode gate는 SMBIOS 조회이며 배터리 보호 조회가 아닙니다. 현재 Windows10 프로세스의 보고 버전·실제 DLL 검색 결과·선택은 미관측입니다.

확인한 WSABI 표본은 payload16/frame21, native Sabi3는 payload11/입력26·출력16이며 둘 다 ACK+4/data+5입니다. 새로운 변형 해시를 기존 사용자 wsabi 해시에 전용하지 않습니다. 변형별 전체 해시는 비공개 전송 기록에 있습니다.

940X3G 문자열은 Cmd DLL의 C61E8, 직접 참조956B에서 일반 모델 분류 enum0x24로 연결됩니다. 확인된 소비처에는 화면 밝기가 있으며 BLE 지원 allowlist 관계는 미입증입니다. 확인한 BLE 핵심 본문에서 모델 helper8A70/89C0 직접 호출은 미관측입니다. 930X3G/P05ACJ 토큰 미관측도 기능 부재 증거가 아닙니다. 모델 분류 helper는 OEM 초기화·selector4 경로를 포함해 수동 진단으로 실행하지 않습니다.

Win8 UI에서 sSettings.exe는 EasySettingsAPI를 통해 ControlCenter를 만듭니다. EasyControlCenter2.dll의 GetStatus wrapper254C0은 CmdBatteryLifeExtend::GetStatus를 찾아 명령 실행·결과 index0을 읽고, 명령 핸들이 없으면2를 반환합니다. 호출 지점25400을 확인했습니다. 메뉴/모델 속성·XML·실제 화면 표시까지의 전체 연결은 아직 미완료입니다.

## 비공개 저장 위치와 재개 순서

현재 작업공간의 개발 캐시 기준은 `.cache/ativ-command-research/20261106/swupdate/bom-after-publish/`입니다. 원본 ZIP·MSI·CAB·추출 파일·원문 디스어셈블리는 저장소나 배포 ZIP에 넣지 않습니다.

- `settings-2.0.0.89.original.zip`, `settings-final-zip-after-publish.private.json`: 원본과 수신 기록.
- `layout-review/`: 외부 ZIP manifest, Win7/Win8 MSI File table 매핑.
- `settings-static-input/`: 두 MSI와 Inst.ini.
- `settings-static-extracted/win7/battery-contract-findings.private.md` 및 JSON: SUS 계약·변형·loader 근거.
- `settings-static-extracted/win8/cmd-review/cmd-contract-findings.private.md` 및 JSON: Cmd 상태·메뉴·초기화·조건부 쓰기.
- `settings-static-extracted/win8/transport-review/transport-findings.private.md` 및 JSON: Wrapper/전송 선택·ABI.
- `settings-static-extracted/win8/model-scope-review/model-scope-findings.private.json`: 모델 문자열의 한정 문맥.
- `settings-static-extracted/win8/ui-review/`: UI import·문자열·상태 wrapper/caller의 중간 기록.

재개 시 AGENTS.md와 이 문서를 읽고 현재 캐시·해시를 확인합니다. 캐시가 없으면 위에 고정한 공개 주소에서 정상 요청으로 다시 받아 관측 SHA와 먼저 대조합니다. 사용자 원본 재제출은 필요하지 않습니다.

1. SUS 변형·Cmd 계약·전송 선택을 해시/RVA 기준으로 독립 교차 검토하고 UI 메뉴/상태 연결을 마무리합니다. 원본을 실행하지 않습니다.
2. 현재 모델/BIOS/Windows에 적용되는 계약과 비교 자료의 범위를 구분합니다. 버퍼 재사용을 추측 요청 인코더나 새로운 OEM 시퀀스로 구현하지 않습니다.
3. 근거가 닫힌 범위만 기존 오프라인 결과 설명에 반영할지 결정합니다. 현재 첫FF 기록은 전체 응답·입력 동등성·현재 지원을 입증하지 않습니다. 제어 어댑터를 활성화하지 않습니다.

이번에는 빌드·테스트를 실행하지 않았습니다. C#435/Python85는 직전 검증 기록입니다. 기존 프로그램·다운로드 파일은 그대로이며 새 노트북 시험·관리자 비교·업로드·추가 OEM 호출·드라이버/서비스/보안 변경은 필요하지 않습니다.
