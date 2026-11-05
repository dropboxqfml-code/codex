# 다음 개발 재개 메모

## v6 실기 관측 수신·추가 Store 역할 분석 계획

[현재 결과와 다음 수용 조건](ACPI_V6_RESULT_AND_NEXT_PLAN.md)을 먼저 읽습니다. 사용자 v6 출력에서 root Arg2 저장/반환 Field 모두 SystemMemory·Matches21ByteFrame, helper Store SystemIo, 양쪽 Region 관계 DifferentObservedDefinitions를 확인했습니다. root Store2회/직접 Arg2 1회·Sources Arg2,Literal이며 같은 입력/반환 Field 정의 참조도 유지됩니다. 선언 비교는 실제 메모리/I/O·SMI·물리 영역 분리·FF 의미를 입증하지 않습니다.

다음 최소 구현은 남은 literal Store의 대상 역할·입력/반환/보조 Field 및 Region과의 관측 정의 관계, 직접 literal 구문 종류를 분류하는 것입니다. 필요하면 같은 직접 구문 목록에서 Store/보조 호출/Return의 위치 관계만 요약하고 분기·반복·중첩은 미확정으로 닫습니다. 실행 순서·값/인수 대입·초기화·트리거 효과는 추론하지 않습니다. 원문 상수·주소·이름·버퍼는 보고하지 않고 기존 수집/API/상한·무실행/무쓰기 경계를 유지합니다.

이번에는 결과 분석·문서만 변경했습니다. v6 반복·관리자 비교·기존 자료 재제출·새 OEM 시험은 필요하지 않습니다. Partial과 기존 Flow6회는 새 오류나 고유 객체 수가 아니며 충전 제어는 Unsupported입니다. 아래는 이전 작업 당시의 기록입니다.

## 현재 구현 — Field 통로 선언·입력 역할 v6 / 2026-11-05 한국 시간

[현재 구현과 실행 안내](ACPI_FIELD_CHANNEL_UPDATE.md)를 먼저 읽습니다. 사용자 승인에 따라 [v5 후속 계획](ACPI_V5_RESULT_AND_NEXT_PLAN.md)의 후보 Arg2 저장/직접 반환 Field 주소 공간·21바이트 선언 폭 범주, 후보 Store 원천 Arg0/1/2/literal/Other, 보조 Store와의 관측 Region 정의 관계를 구현했습니다. 반복 참조와 고유 후보를 구분하며 복수 동일 폭은 MultipleCandidates, 서로 다른 폭은 Mixed, 불완전·모호함은 Unknown으로 남깁니다. 비Field·미분류 대상을 버려 단일 일치를 만들지 않습니다.

기존 Flow 지표·ObjectReferences·직접 FF 의미는 유지합니다. 폭 일치나 같은 Region 선언을 바이트 배치·입력 보존·실행·물리 주소 동일성·SMI·충전 지원으로 확대하지 않습니다. 원시 폭·이름·주소·오프셋·길이·값을 보고하지 않고 실제 영역 접근·OEM/AML/DLL 실행·예약 접근을 추가하지 않습니다. 수집은 같은 두 읽기 API와 고정 DSDT/첫 SSDT이며 기존 상한을 유지합니다.

새 배포 ACPI-FIELD-CHANNEL의 **프로그램 ZIP 하나만** 새 폴더에 풀어 일반 권한으로 실행하고 **Acpi-routing-v6 새 요약만** 확인합니다. 소스 ZIP은 개발용입니다. 새 요약은 v5에서 없던 후보 공간·폭·Region 관계를 추가하므로 의미가 있으며 기존 자료 재제출·v5 반복·관리자 비교·완료된 OEM 실험 재실행은 요청하지 않습니다. 새 v6 실기는 미관측이고 제어는 Unsupported입니다. 이후 새 정적 근거를 기존 Windows/SABI 규약과 대조하되 모델별 명령 계약·FF 의미가 입증되지 않으면 제어를 활성화하지 않습니다. 아래는 이전 작업 당시의 기록입니다.

## 이전 개발 기록

## v5 실기 결과·필드 선언과 정적 프레임 통로 계획

[현재 분석과 계획](ACPI_V5_RESULT_AND_NEXT_PLAN.md)을 먼저 읽습니다. v5 사용자 출력에서 root 이름 참조 3/3 Field, helper 3/3 Mutex/Field·Store Field SystemIo, root Store(Arg2)/Return 동일 관측 Field 정의 참조를 확인했습니다. 두 root/helper 직접 참조 관계는 미확정입니다. 선언 종류 6/6 분류는 고유 객체 6개나 실제 데이터 전달 증거가 아니며 기존 Flow 미확정6 지표는 별도 보수적 검사로 유지됩니다.

사용자는 이번에 분석·보고·계획을 요청했습니다. 실행 코드/ZIP은 바꾸지 않았고 빌드/테스트도 반복하지 않았습니다. 다음 구현은 root 저장/반환 Field의 Region 종류·고정21바이트 프레임 대응 분류, directStore의Arg0/1/2/상수/기타 source-role, root/helper의same-observedRegion 정의 관계와 보고문구 정리입니다. raw주소/offset/length/값은 내보내거나 실제영역접근하지 않고 physicalalias/실행/값전파를 추정하지 않습니다. 구조 확인 뒤에도 모델Windows 배터리 명령/FF 의미는 별도 근거가 필요합니다. v5 반복/관리자 비교/원본 재제출·새 OEM 시험은 없고 제어는 Unsupported입니다. 아래는 이전 기록입니다.

## 이름 객체·Store/Return 참조 관계 구현 — v5

[구현 범위와 실행 안내](ACPI_OBJECT_REFERENCE_UPDATE.md)를 먼저 읽습니다. v4에서 관측한 root/helper의 이름 참조를 same-table 선언 종류와 정적 참조 관계로 분류합니다. 새 ObjectReferences는 기존 Flow/UnresolvedNameReferences/FF 의미와 분리합니다. kind 분류가 실제 runtime 형식·값·별칭·동일 데이터·실행 효과를 보장하지 않습니다.

관측 Buffer/단순 Name/Mutex/Event/OperationRegion 및 지원한 단순 FieldList만 읽고 원래 이름/주소/offset/length/rawspaceId는 출력하지 않습니다. 중복/Alias/External/object-vs-method/동적CreateField 가림은 보수적으로 미확정입니다. FieldList 전체 성공 전 typed prefix는 확정하지 않고 byte재검색도 없습니다. 새 본문 고유 참조 상한64는 새보고서LimitExceeded만 만들며 기존 root 구문/Flow/직접 FF를 폐기하지 않습니다.

수집은 같은 두 Windows API·DSDT/첫 SSDT이고 실제 I/O·영역/포트/driver/물리 메모리/registry·OEM/AML·예약·값/분기평가·하드웨어 쓰기는 없습니다. 새 배포 ACPI-OBJECT-REFERENCES/Acpi-routing-v5는 프로그램 ZIP 하나만 일반 권한으로 실행합니다. v4 반복/관리자 비교/기존 자료 재제출은 필요하지 않습니다. 새 v5 분석의 실기는 미관측이고 실제 충전 제어는 Unsupported입니다. 아래는 이전 기록입니다.

## v4 보조 본문 실기 확인·다음 구현 계획

[이번 분석과 계획](ACPI_V4_RESULT_AND_NEXT_PLAN.md)을 먼저 읽습니다. v4는 보조 해석 1/미지원 0/실패 None, Acquire·Release, helper Return 0/None·그 본문 범위의 literal FF 미관측입니다. v4의 구문 지원 목표는 실기 관측됐고 실제 FF 의미/충전 제어는 미확정입니다. root Return UnresolvedName·직접 Arg2 인수 0은 입력 미전달/잘못된 반환이 아닙니다. 미해결 6은 root+성공helper의 참조 횟수이지 객체 6개가 아니며 연결 Partial과 전체 namespace Partial을 구분합니다.

사용자는 이번에 분석·보고·계획을 요청했습니다. 실행 코드/배포물은 바꾸지 않았고 빌드/테스트를 반복하지 않았습니다. 다음 구현 우선순위는 same-table 관측 객체 Buffer/Mutex/Event/Field/OperationRegion의 종류 분류와 Store/Return의 정적 참조 관계입니다. 값/분기/별칭 평가·실제 I/O·주소 출력·OEM 호출은 없습니다. v4 반복/관리자 비교/원본 재제출은 필요하지 않습니다. 구체적인 수용 조건과 안전 경계는 새 계획을 따릅니다. 아래는 이전 기록입니다.

## v3 보조 본문 미지원 수신·확장 구문 v4

[현재 관측·구현·범위](ACPI_HELPER_SYNTAX_UPDATE.md)를 먼저 읽습니다. v3는 root Parsed·호출 1·직접 Arg2 인수 0·Return 1/UnresolvedName·보조 1/해석 0/미지원 1·미해결 참조 3입니다. 입력 미전달이나 잘못된 반환이 아니며 미해결 3은 root의 관측입니다. 현재 중단 opcode는 미확정이고 특정 Acquire로 단정하지 않습니다.

v4는 같은 수집/상한 안에서 표준 확장 AML 구문을 정적으로 소비하고 고정 실패 종류/공개 구문 이름만 보고합니다. raw opcode/위치/이름/주소/값/예외 원문은 출력하지 않습니다. Acquire timeout은 raw WORD2바이트이며 실제 대기/동기화/변환/필드 생성/Fatal/AML/OEM을 실행하지 않습니다. 동적 Load/LoadTable/Unload/namespace 정의는 미지원으로 닫습니다.

Root/기존 전체 연결 FF 의미는 유지하며 완전히 구문 해석한 보조 N개 범위의 반환/확장 구문/FF를 별도 집계합니다. N=0은 미확정, 실패 prefix는 폐기하고 scoped false를 전체 부재/실제 FF 위치로 전이하지 않습니다. 새 배포 ACPI-HELPER-SYNTAX/Acpi-routing-v4는 일반 권한·프로그램 ZIP 하나만 사용합니다. v3 반복/관리자 비교/과거 자료 재제출은 필요하지 않습니다. 실제 v4 분석은 아직 미관측이고 충전 제어는 Unsupported입니다. 이전 1회 실험·예약 표식은 유지합니다. 아래는 이전 기록입니다.

## v2 DSDT 관측 수신·연결 구문 요약 v3

[v2 관측과 v3 구현 경계](ACPI_METHOD_FLOW_UPDATE.md)를 먼저 읽습니다. DSDT 본문 Complete·namespace Partial·알려진 설명자 1·대응 메서드 1·인수 3·본문 Parsed를 관측했습니다. 직접 비교/FF 반환 미관측은 보조 본문의 부재가 아닙니다. 수집 확대 대신 후보 Return 형태·알려진 호출 수·직접 Arg2 인수·같은 테이블의 보조 정의를 깊이 2/최대 8개/전체 호출 표현식 32개 안에서 순수 정적으로 요약합니다.

중복/명시 경로/관측 객체의 shadow를 보수적으로 구분하고 unresolved 이름은 객체/무인수 호출을 단정하지 않아 Partial입니다. helper의 형식 인수를 원래 WMI 입력으로 대입하거나 실행 경로·변수 값·배터리 의미를 계산하지 않습니다. 루트 FF와 보조 FF 표식은 별개이며 불완전한 연결에서 보조 FF 여부는 미확정입니다.

새 배포는 ACPI-METHOD-FLOW / Acpi-routing-v3입니다. v2와 동일한 두 읽기 API·DSDT/첫 SSDT를 사용하며 registry/AML eval/OEM/DLL/예약/드라이버/물리 메모리/포트/쓰기/보안 변경은 없습니다. 실제 제어는 Unsupported이고 완료된 1회 실험 표식은 유지합니다. 새 v3 분석의 실기는 미관측입니다. 프로그램 ZIP 하나만 일반 권한으로 실행하며 v2 반복·관리자 비교·과거 자료/원본 ACPI 재제출은 요청하지 않습니다. 아래는 이전 기록입니다.

## DSDT 직접 읽기 수정본 — Acpi-routing-v2

[수정 근거와 범위](ACPI_DSDT_DIRECT_READ_UPDATE.md)를 먼저 읽습니다. ACPICA 고정 커밋 e85aa3b의 Windows 구현에서 DSDT 미열거를 직접 Get으로 보완하는 근거를 확보했습니다. 기존 두 읽기 API·고정 provider/ID를 유지하고 정상 목록 조회 뒤 DSDT 0이어도 직접 크기/본문을 한 번씩 읽습니다. 목록 관측·본문 읽기·구문 해석은 별도로 보고하며 첫 SSDT만 읽는 한계와 제한된 파서는 그대로입니다.

이번에는 registry SSDT 캐시 경로를 추가하지 않습니다. OEM/AML/DLL 실행·드라이버/물리 메모리/포트·예약 접근·보안 변경·펌웨어 쓰기는 없습니다. 기존 앱/요청/decoder/예약/제어 정책도 유지합니다. 새 실행 패키지는 ACPI-DSDT-DIRECT이며 예전 v1 ZIP은 그대로 보존합니다. 프로그램 ZIP 하나만 일반 권한으로 실행해 v2의 새 요약을 확인하며 소스 ZIP·기존 자료 재제출은 필요하지 않습니다. v2 실제 Windows 직접 읽기는 미검증이고 실제 충전 제어는 Unsupported입니다. 아래는 이전 기록입니다.

## ACPI 실기 결과 수신 — 정의 확보 범위 부족

[실기 결과와 다음 경계](ACPI_ROUTING_LAPTOP_RESULT.md)를 먼저 읽습니다. 사용자 요약은 Acpi-routing-v1, 목록 Complete, DSDT 0, SSDT 4, 첫 SSDT Partial, 설명자/메서드 0, 본문 NotObserved입니다. DSDT는 미열거 gate로 본문 조회를 하지 않았고 SSDT는 첫 것만 읽었습니다. Partial의 원인 구문은 출력에 없으며 기능 부재나 FF 의미를 입증하지 못했습니다.

현재 도구의 같은 실행·관리자 비교·과거 자료 재제출을 요청하지 않습니다. 같은 서명 반복 조회로 다른 SSDT를 읽을 수도 없습니다. 다음 구현 전에 현재 모델 정적 정의를 얻을 읽기 전용 Windows 자료의 실제 제공 범위와 문서 근거를 검토해야 합니다. 근거 없이 직접 DSDT 조회 성공·새 registry 경로·파서 수정 효과를 단정하거나 OEM/드라이버/포트/물리 메모리 접근으로 우회하지 않습니다.

이번 변경은 실기 관측 문서뿐이며 새 EXE·빌드·테스트 실행은 없습니다. 353+22 및 빌드 0경고/0오류는 직전 기록입니다. 기존 요청/디코더/예약/제어 정책과 다운로드 ZIP은 그대로이며 완료된 1회 OEM 실험 재실행·표식 초기화·추가 후보는 없습니다. 충전 제어는 Unsupported입니다. 아래는 이전 기록입니다.

## ACPI 정적 연결 점검 구현

[이번 범위·출력 해석·새 자료](ACPI_STATIC_ROUTING_CHECK.md)를 먼저 읽습니다. 기존전송코드감사에서FF를만드는명백한결함없음, exactmodel공개README검색에서도펌웨어정의없음이므로 현재DSDT/첫SSDT의WMI연결정의를읽는새별도normal-asInvoker도구를준비했습니다. Windows두read API만사용, AML eval/OEM/예약/원본저장X입니다. 과거자료재제출아닌새정의요약만필요합니다.

Core제한AMLreader는static_WDG knownGUID→동일scope WMxx 후보와인수수·직접ID1/Size21비교·literalFF반환구문만요약합니다. opaqueBuffer/Package/String/Field에재동기화하지않고unknownNamespace는Partial, methodunsupported는표식폐기합니다. Partial/관측수/부정표식은전체부재·유일성·배터리의미증거가아닙니다. 모든SSDT/cross-table/보조메서드/SMM해석미지원이며FF원인해결을보장하지않습니다.

새ACPI-ROUTING-CHECK만일반권한으로실행하며oldOneShot재실행/markerreset/추가OEM/0x66없음. 현재일반앱·원래정책/decoder/예약은유지합니다. 원본테이블/GUID원문/주소/이름/경로/식별자는보고하지않습니다. 실제Windows수집경로는아직미검증이고실제충전제어는Unsupported입니다. 아래는이전기록입니다.

## 일반 앱 실기 확인·모델 계약 추가 정적 조사

[이번 조사 범위와 남은 조건](WMI_MODEL_CONTRACT_FOLLOWUP.md)을 먼저 읽습니다. 사용자가 일반 권한 시작/현재 배터리 표시를 확인했고 파일 재제출은 하지 않았습니다. 과거 결과 붙여넣기까지 확인한 것으로 확대하지 않습니다.

Linux v6.12도 조회 입력data[0]=0x80을 명시하므로 FF를근거로0으로바꾸지않습니다. SABI2 표의0xFFFF와응답FF, Windows version16과SABI2/3도구분합니다. 공개linuxhw/ACPI 커밋d6d30c6ef6f45506567f25a302c64f009d8f5f4e를blob없는실제tree로조사했으나940/930X경로없음, 다른모델AML은대입하지않았습니다. 현재모델Windows명령/selector/FF계약은여전히미확정입니다.

새계약근거없이충전어댑터/쓰기/추가OEM시도/입력보정/의미없는wrapper나반복진단을추가하지않습니다. 승인1회는완료됐고marker유지/packager폐쇄그대로입니다. 이번에는문서만변경했으며342+19/경고오류0은직전검증기록입니다. 새EXE/시험/자료재제출은없고기존일반앱을그대로사용합니다. 아래는이전기록입니다.

## 실제 응답 수신·표식FF·1회 완료·일반 앱 오프라인 검토

[이번 결과·정적 대조·프로그램 개발](WMI_ONE_SHOT_QUERY_RESULT.md)을 먼저 읽습니다. 사용자 출력 Query65-locator-v2/Elevated/ResponseReceived/Complete/Ready/requested/FrameChecked/ValidFrame/FF를 확인했습니다. 비동기완료0·출력1개·정확히21바이트/ACKAA 구조는 통과했고 payload첫바이트만FF로분류했습니다. 전체payload/명령echo/배터리의미/보호상태·충전상한은 미확정입니다. FF를OFF/ON/하드웨어미지원으로 변환하지 않습니다.

승인된1회는 소비됐으며 기존v1예약과backend/정책/decoder를그대로보존합니다. 실험재실행·표식삭제/리셋·다른계정/위치우회·추가읽기후보·0x66쓰기는없습니다. 완료기록이있는동안새OEM EXE패키징도닫았습니다. 같은자료/준비점검을다시요청하지않습니다.

이번에는 메인WPF앱에 기존consoleTEXT를user가paste해검토하는오프라인기능을추가했습니다. Core의bounded고정형식parser→고정enumreview만보관하고 원문은검토후비웁니다. 과거텍스트진위/currentdevice일치는검증하지않고 FF/0/1/Other도현재actualmode로쓰지않습니다. VM은설정/모드/로그/하드웨어와분리하고 입력변경·실패·초과·dispose를닫습니다. 새기능은추가WMI/OEM/예약접근없고기존battery/readonly진단만유지합니다.

새 RESULT-REVIEW 일반앱/소스만공유하며 실험EXE/삼성원본은포함하지않습니다. 새노트북실험/자료재제출은필요없고현재실제제어는Unsupported입니다. 다음핵심은현재모델Windows배터리명령의미·응답해석근거이며 공개hotkeys/LinuxFF처리를그대로전이하지않습니다. 아래는이전기록입니다.

## Locator-v2 Ready 실기 수신·기존 승인 조회 수정본 준비

[이번 결과·변경·실행 범위](WMI_QUERY_LOCATOR_READY_RESULT.md)를 먼저 읽습니다. 사용자 출력은 Locator-v2/Elevated/Complete/Ready/None이며 OEM/예약접근은 없습니다. 이번에 단일 활성 대상·경로와 대상 재읽기·입력CIMTYPE·메모리 버퍼까지 통과했습니다. 같은 준비 점검/자료를 반복 요청하지 않습니다.

기존 명시 승인 exact0x65/payload80+15zero/max1은 유지되고 옛 실험은 PreflightFailed로 claim/channel 전에 끝났습니다. 같은 승인을 재요청하지 않고 승인 범위의 실행을 완수하도록 기존 backend의 methodquery에만 EnsureLocatable을 반영합니다. 새 표식이나 횟수를 만들지 않고 원래 v1 예약과 위치를 그대로 사용합니다. 기존 표식이 있거나 안전하게 확보하지 못하면 무호출입니다. Ready TXT를 허가 토큰/선택 대상 근거로 입력받지 않습니다.

기존 실제 호출/콜백/출력해석·정책·예약·가드·worker/시간 제한은 그대로이며 메인 앱 미연결입니다. 새 Query65-locator-v2 판별 표시가 있는 ONE-SHOT-LOCATOR ZIP만 해당 절차로 한 번 확인합니다. 후보의 의미/펌웨어 부작용은 아직 미검증이고 실제 충전 제어는 Unsupported입니다. 호출 요청·시간 초과·결과 불명 뒤 재시도, 표식 삭제/리셋, 다른 계정/경로 우회, 0x66/다른 명령은 없습니다. 아래는 이전 기록입니다.

## 경로 정보 확보 옵션·고정 오류 분류 구현 후

[Locator-v2 구현과 확인 범위](WMI_PREFLIGHT_LOCATOR_UPDATE.md)를 먼저 읽습니다. 새 무호출 점검판은 MethodEnumeration의 고정 SELECT에만 EnsureLocatable=true를 적용하고 모델/BIOS 조회 옵션은 기존대로 유지합니다. 객체/경로 문제 여섯 종류와 정상 Boolean Active=false를 구분합니다. 과거 enum 값과 모호한 결과는 그대로 남깁니다.

단일 활성 대상·경로·입력 검증, DirectRead와 6초 예산·부모/작업자 각10초 제한을 유지합니다. 기존 실험 backend/정책/예약/메인 앱은 변경하지 않았습니다. Ready에서도 OEM 호출·예약 접근은 없고 충전 제어는 Unsupported입니다. 새 LOCATOR ZIP을 별도 공유하며 삼성 원본/이전 실험 EXE는 제외합니다.

다음 실기 확인은 새 점검판 `(Locator-v2)`의 단계와 세부 원인 분류뿐입니다. 과거 자료나 같은 이전 실행 결과를 다시 요청하지 않습니다. 기존 실험 EXE 재실행·표식 삭제·추가 OEM 시험으로 이어가지 않습니다. 경로 정보 확보가 실제 이전 실패를 해결했는지는 아직 미확정입니다. 아래는 이전 기록입니다.

## 무호출 점검 결과 수신 — 메서드 대상 열거 조건 불일치

[이번 결과와 다음 수정 범위](WMI_PREFLIGHT_ENUMERATION_RESULT.md)를 먼저 읽습니다. 사용자 출력은 Elevated·Complete·MethodEnumeration·InactiveOrInvalidTarget입니다. 이번 실행은 고정 모델/BIOS·상세 metadata/binder/id1·ROOT\WMI 연결을 통과했고 TargetRead/입력CIMTYPE/버퍼 준비에는 도달하지 않았습니다. OEM 호출과 예약 접근은 없습니다.

이 분류는 반환 객체/경로 구조 실패와 명시적 Active=false를 합치므로 Active=false·한 행·전체 열거 완료를 단정하지 않습니다. SELECT Active 결과에 경로를 요구하면서 EnsureLocatable을 지정하지 않은 점을 우선 검토합니다. 공식 API 문서에서 옵션 의미와 기본 false를 확인했으나 실제 경로 누락은 아직 미확정입니다. 이전 Unavailable과도 맞는 구조 실패 가설이며 동일 원인을 확정하지 않습니다.

다음은 무호출 도구의 고정 오류 분류 세분화와 메서드 대상 쿼리의 EnsureLocatable 적용 검토입니다. 기존 단일 활성 대상/경로 검증을 삭제하지 않고 원문 경로도 보고하지 않습니다. 이번에는 문서만 반영했으며 기존 EXE 재실행·자료 재제출·표식 삭제·추가 OEM 실행은 요청하지 않습니다. 329개/6프로젝트0경고오류는 이전 배포 기록이고 이번에는 빌드/테스트를 재실행하지 않았습니다. 아래는 이전 기록입니다.

## 무호출 사전 검증 점검 도구 구현 후

[이번 구현과 실행 범위](WMI_PREFLIGHT_ONLY_CHECK.md)를 먼저 읽습니다. 이전 Elevated·PreflightFailed·Unavailable·InvocationRequested=false 결과의 실패 위치를 확인하기 위해 별도 WmiPreflightCheck를 추가했습니다. 고정 준비 조건과 DirectRead 옵션·6초 예산을 그대로 재현하며 단계와 오류 enum만 출력합니다. 기존 실험 프로젝트와 예약/호출 정책은 변경하지 않았습니다.

새 EXE는 OEM 메서드 실행·후보 프레임·실험 runner·예약 접근이 전혀 없습니다. 메모리 입력 객체 생성까지만 하고 모두 해제합니다. 부모/작업자 각각10초 제한, asInvoker·같은 계정 수동 관리자 실행, 고정 쿼리와 개인정보 제한을 유지합니다. Ready도 실제 보호 상태나 충전 제어를 뜻하지 않습니다.

새 확인은 WMI-PREFLIGHT-ONLY ZIP의 새 EXE 출력뿐입니다. 이전 WmiOneShotQuery를 재실행하거나 표식을 삭제하지 않습니다. 기존 TXT/DLL/파일 목록·권한 비교 재제출도 필요 없습니다. 실패 원인을 확인하기 전에 조건/쿼리 옵션을 완화하지 않습니다. 이번 준비가 통과해도 이전 실패 원인 해결이나 추가 OEM 시험 승인을 추정하지 않습니다.

현재 전체329개 통과·6개 프로젝트와 테스트 프로젝트 빌드 경고/오류0개입니다. Windows 실기와 OEM 호출은 클라우드에서 수행하지 않았고 실제 충전 제어는 Unsupported입니다. 새 실행 ZIP은 삼성 원본과 기존 실험 EXE를 제외하고 별도로 공유합니다. 환경 설정 게시는 없습니다. 아래는 이전 기록입니다.

## 1회 도구 결과 수신 — 사전 검증 중단·무호출

[실제 결과와 보고 전용 보완](WMI_ONE_SHOT_PREFLIGHT_RESULT.md)을 먼저 읽습니다. 2026-11-04 사용자 출력은 Elevated·PreflightFailed·Unavailable·InvocationRequested=false·응답/표식 미관측입니다. 이 상태 조합에서는 Prepare가Complete가되기전에끝나고 예약/채널에진입하지않았습니다. 이번실행의후보요청은없었지만기존예약파일부재나추가실행허가를단정하지않습니다.

기존 '메타데이터확인불가'는공통Unavailable문구라 실패위치를증명하지않습니다. 고정사전검증단계만보고하는패치를구현했고 모든호출가드/쿼리옵션/예약/1회제한/실행메서드는유지합니다. 정확한원인을찍어조건을제거하지않고 이번에는새실험EXE·재실행·표식삭제를요청하지않습니다. 이전자료재제출도필요없습니다. 전체325개통과·5개프로젝트빌드경고오류0개이며 actualWindows/OEM실행은추가하지않았습니다. 아래는이전이력입니다.

## 한정 OEM 후보 실험 명시 승인·도구 구현 후

사용자가 “그래 이번 테스트를 위해서 승인할게. 반드시 필요한 작업만 수행하도록해. 노트북의 보안을 위해서 하드웨어 안전 규칙을 꼭 지켜야해.”라고 검토서 범위를 승인했습니다. [승인 기록·구현·실행 안내](WMI_ONE_SHOT_QUERY_APPROVAL.md)를 먼저 읽습니다. 같은 승인 재요청 없이 이 한정 실험의 구현/검증/프로그램 공유를 완료합니다. 후보가 안전하거나 모델 적합성이 입증됐다는 결과는 아닙니다.

새 WmiOneShotQuery는 별도 asInvoker·같은 계정 수동 관리자·fixed0x65 payload80+15zero·최대1회입니다. 모델Product.Name/BIOS exact·token·상세metadata/id1·전체완료1rowActiveTrue·입력준비·영속CreateNew예약이 모두 맞아야 요청합니다. 원래 앱은 연결하지 않고 0x66/다른명령·DLLinit·driver/service/ACL/보안변경·포트IO·자동상승은 없습니다.

Native는 managed async InvokeMethod 한 지점만 있고 Completed.Status0+정확히1개일 때만 고정output을읽습니다. 이 상태는 즉시ExecMethod HR을 확보했다는 뜻이 아닙니다. generic콜백collector를portable로검증하고 늦은/중복/실패/cancel/정리경합을닫습니다. 부모와내부worker각10s감시·6s사전검증예산이있고native종료/복구를보장하지않습니다. 예약표식을삭제/리셋/우회하지않습니다.

새 도구의 Windows 실기 결과는 아직없으며 다음은 승인된1회출력만받는 단계입니다. 이전TXT/DLL/파일목록/권한비교재제출은필요없습니다. 어떤후보표식도 actualMode/ONOFF/충전상한지원으로바꾸지않고 Unsupported를 유지합니다.

현재전체322개+Python6개통과,5개프로젝트빌드경고/오류0개입니다. 실제OEM/Windows실기미실행입니다. 소스와미서명실험ZIP만검증해공유합니다. 승인된1회결과를받기전다른명령/추가실험/예약표식초기화를추가하지않습니다. 아래는 이전 개발 이력입니다.

## 다음 실제 단계의 범위 변경 검토서 준비

[한정 OEM 조회 후보 실험 검토서](WMI_ONE_SHOT_QUERY_REVIEW.md)를 먼저 읽습니다. 내부 메모리 통합은 완료됐고 추가voria/hotkeys callsite조사에서도 현재모델WMI 배터리명령 의미·안전성·응답계약은확정하지못했습니다. 새로운일반추상화/반복진단을추가하지않았습니다.

조회후보0x65·payload80+0x00*15·한정1회·별도asInvoker/같은계정수동관리자실행·시간초과/무호출/출력제한을 검토서로 구체화했습니다. 경로간 전이 가설과 예기치않은 firmware동작 가능성을명시했으며 실제OEM실행구현·EXE·실험은 아직미승인·미구현·미실행입니다. 원래사용자의OEM금지와AGENTS의명시승인/검증조건을 개발계속지시나 이전속성관리자비교승인으로 덮지 않습니다.

다음 사용자답변은 이 미검증 후보의 한정 실험으로 범위를변경할지입니다. 승인전에는 InvokeMethod·드라이버/포트IO·DLL초기화 등실제경로를추가하지않습니다. 승인받으면같은범위에승인을반복요청하지않고구현·검증·다운로드공유를완료합니다. 설정/쓰기명령의구현과0x66/다른OEM명령·메인앱관리자실행·자동상승은범위밖입니다. 미검증펌웨어부작용의부재를보장하지않습니다.

이번에는문서와연구만변경했습니다. 297개·빌드경고오류0은이전검증기록이며 재실행하지않았습니다. 이전원본자료제출과같은규약진단은필요하지않습니다. 아래는이전개발이력입니다.

## 메모리 채널 연결·통합 검증 후

[이번 채널·전체 경로·연구 한계](WMI_BOUND_CHANNEL_AND_PIPELINE.md)를 먼저 읽습니다. 바인더와 명시 snapshot transport를 연결하는 BoundFrameChannel을 추가했으며 기존 FrameExchange를 그대로 사용합니다. TryWrapFrame은21/magic/예약0을 복사 후 검증합니다. MethodReplyStatus와 InvalidEnvelope로 중첩 오류를 보존하고 기존byte decoder 상세는null·bool수락조건은 그대로 유지합니다. 이미 결합한 응답의 재포장은 거부합니다.

실제 Windows/native/OEM 구현·기본 transport·인스턴스 선택·앱 등록은 없습니다. 취소token을 전달하고 늦은 snapshot을 성공 게시하지 않으며 실제 작업 완료까지 기존 조정기의 Busy를 유지합니다. 이는 인스턴스별 협조적 제한이고 공유 transport 전역 잠금이나 native 강제 종료가 아닙니다.

노트북에서 새로 실행·제출할 항목은 없습니다. 클래스 형식 확인은 완료됐고 내부 경로가 모의 통합 검증으로 연결됐습니다. 다음 개발 우선순위는 현재 모델 배터리 명령 의미·읽기 안전성·실제 응답 계약 근거입니다. 공개 포크/이슈 후속 조사에서도 새 근거는 확보하지 못했습니다. Windows1/Linux0/firmwareopcode를 치환하지 않고 실제 읽기·쓰기는 Unsupported를 유지합니다.

전체297개 통과·실패/건너뜀0개, 4개 프로젝트 빌드 경고/오류0개입니다. Python배포suite는이번에반복하지않았고 이전6개는이전기록입니다. 새소스ZIP을별도검증합니다. 아래는 이전 개발 이력입니다.

## 형식 일치 실기 결과 수신·오프라인 메서드 바인더 구현 후

[이번 실제 관측·코드·남은 조건](WMI_MATCHED_BINDING_AND_OFFLINE_ENVELOPE.md)을 먼저 읽습니다. 판독기2에서 두 클래스Complete, GUID후보일치, CallSabiFunction존재, WindowsMethodId1, in/out ScalarObject+CIMTYPE DataBuffer, BytesUInt8[]=True를 확인했습니다. EmbeddedInstance는 미관측/없음으로 보존하고 권한 수준은 새로 단정하지 않습니다. 이전 Unknown이 해소됐으므로 같은 메타데이터·파일 목록·관리자 비교를 반복 요청하지 않습니다.

WsabiWmiMethodBinder는 상세 근거가 모두 있는 Complete 보고서에서만 만들어지고 bool만 true인 호환 보고서는 거부합니다. 고정 inData/Bytes 요청 포장과 outData/Bytes 추출을 기존 codec에 연결하지만 메모리 snapshot만 다룹니다. HRESULT 우선, 실패 시 데이터 제거, 깊은 복사·읽기 전용 map과 false capability를 유지합니다. CreateInstance/InvokeMethod/liveWMI/OEM채널/앱등록은 없습니다.

이번에는 내부 계층의 검증된 소스를 전달하며 새 노트북 실행 항목은 없습니다. 저장 기록과 공개 ACPI 인덱스 조사에서도 현재 모델 배터리 명령의 의미·읽기 안전성·실제 응답 계약은 추가 확보하지 못했습니다. Windows1을 Linux0/펌웨어opcode로 치환하거나 Sabi3후보를 WMI에 대입하지 않습니다. 실제 읽기·쓰기는 미구현이며 Unsupported를 유지합니다.

이번 전체286개 통과·실패/건너뜀0개, 4개 프로젝트 빌드 경고/오류0개입니다. 이전Python6개는 이번에 반복 실행하지 않았으며 소스ZIP만 별도로 검증합니다. 아래는 이전 단계 이력입니다.

## 실제 규약 결과 반영·CIMTYPE 보완 후

[이번 실제 관측과 수정](WMI_PARAMETER_RESULT_AND_CIMTYPE_REVIEW.md)을 먼저 읽습니다. 공개 GUID 후보 일치, CallSabiFunction 존재, Windows WmiMethodId=1, DataBuffer.Bytes UInt8[]=True를 확인했습니다. in/out Unknown이므로 입력/출력의 구체 클래스는 미확정입니다. 도구에 토큰 표시가 없어 이번 권한 수준도 새로 단정하지 않습니다. 원본 TXT는 저장소·배포물에 넣지 않습니다.

단일 Object의 구체 클래스를 EmbeddedInstance만으로 검사했던 한계를 공식 CIMTYPE object:EmbedClass 근거로 보완했습니다. 실제 CIMTYPE는 아직 미관측입니다. 새 판독기2는 두 qualifier의 독립 상태·충돌·형식 오류를 enum으로 보관하고 부분/실패를 일치로 승격하지 않습니다. 메서드 번호1은 그대로 보존하며 Linux0이나 프레임 내부 펌웨어 명령으로 치환하지 않습니다. 모든 상태에서 호출·하드웨어 기능은 차단합니다.

274개 및 Python6개 통과, 4개 프로젝트 빌드 경고/오류0개입니다. 수정 도구의 Windows 실기는 미검증입니다. 새 확인은 in/out CIMTYPE·판정이며 기존 진단·DLL·권한 비교 재요청이나 관리자 실행을 하지 않습니다. 실제 배터리 명령의 모델 적합성·읽기 안전성·응답 계약은 아직 미확보이며 OEM 채널 미연결과 Unsupported를 유지합니다. 아래는 이전 이력입니다.

## 비동기 프레임 처리와 정적 클래스 규약 도구 구현 후

[이번 코드·규약·새 실기 확인 항목](WMI_EXCHANGE_AND_BINDING_CHECK.md)을 먼저 읽습니다. 비동기 조정기는 가짜 채널만으로 검증했으며 실제 WMI/OEM 채널이나 앱 등록 경로는 없습니다. 시간 초과·취소 후 실제 작업 완료까지 Busy를 유지합니다. 협조적 제한을 native 강제 종료로 해석하지 않습니다.

별도 asInvoker WmiContractCheck는 WmiAcpiMethod/DataBuffer 클래스 정의만 읽습니다. 공개 GUID 후보 일치, CallSabiFunction의 WmiMethodId, inData/outData EmbeddedInstance와 Bytes의 UInt8[] 정의를 확인합니다. 실제 GUID 원문·인스턴스·토큰·보안 설명자는 수집하지 않습니다. 메서드 ID는 펌웨어 배터리 명령이 아니며 형식 일치도 실제 배열 길이·ACK·호출 안전성·배터리 지원을 입증하지 않습니다.

전체262개 및 Python6개 통과·4개 프로젝트 빌드 경고/오류0개입니다. 새 도구의 Windows 결과는 아직 받지 않았습니다. 다음 사용자 확인은 새 정적 필드의 일반 실행 출력뿐이며 기존 진단·원본 DLL·한 번의 관리자 비교를 반복 요청하지 않습니다. 새 도구도 관리자 실행을 요청하지 않습니다. 권한 거부·시간 초과는 그대로 보존합니다.

추가 공개 모델 자료3건도 현재 모델의 Windows 배터리 조회 계약을 확정하지 못했습니다. 실제 배터리 읽기는 모델별 명령 의미·읽기 안전성·응답 계약이 남아 있으며 Unsupported와 기존 쓰기 차단을 유지합니다. 이전 한정 비교 승인은 완료됐고 OEM·권한 상승·드라이버/서비스/ACL 변경으로 확장하지 않습니다. 아래는 이전 개발 이력입니다.

## 구조적 WMI 응답 디코더 구현 후

[추가 공개 근거와 코드](WMI_REPLY_DECODER_AND_PUBLIC_EVIDENCE.md): gh2o/samsung-wmi와 djpohly/samsung-wmi의 고정 원문에서 21바이트 프레임·payload16 구조를 독립 확인했습니다. 현재 모델, Windows 클래스·메서드와의 동일성, 배터리 조회0x65, version16 의미를 입증하는 자료는 아니므로 새 호출 대상이나 명령으로 사용하지 않았습니다.

순수 WsabiWmiReplyDecoder와 불변 결과 객체를 구현하고 기존 bool 검증기를 호환 위임으로 바꿨습니다. API 미완료·없음·형식·차원·길이·ACK를 구분하며 payload0/1/FF를 배터리 상태로 해석하지 않습니다. 정확한21바이트만 지원하는 기존 범위와 Sabi3 x64 ABI 분리를 유지합니다.

전체244개 통과·빌드 경고/오류0개입니다. 이번에는 소스 구현과 정적 연구를 전달하며 새 OEM 실행 파일이나 반복 노트북 진단은 요구하지 않습니다. 다음 실제 배터리 읽기의 미검증 조건은 여전히 모델별 명령 의미·안전성·정확한 응답 계약입니다. 이전 한정 관리자 비교 승인을 OEM 호출로 확대하지 않습니다.

## 일반·관리자 비교 결과 수신 — 비교 완료

[두 실행의 실제 결과](WMI_PERMISSION_COMPARISON_RESULT.md)를 확인했습니다. 일반 토큰은 WmiAcpiVersion Active=True/version=16을 읽고 WmiAcpiMethod를 Enumerate에서 0x80041003으로 거부받았습니다. 상승 토큰은 두 클래스 모두 Complete이고 각각 활성 행 1개, version=16입니다. 이번 승인은 한정된 속성 비교였으며 결과 수신으로 완료됐습니다.

이는 메서드 실행 허가·배터리 보호 상태·명령 지원을 확인한 결과가 아닙니다. version16은 해석하지 않은 UInt32이며 두 클래스의 행도 키로 연결하지 않았습니다. 이전 메인 앱의 양쪽 AccessDenied와 이번 새 도구의 일반 토큰 버전 성공은 별도 빌드·시점 관측으로 보존합니다. PacketPrivacy나 Connect의 인과를 단정하지 않습니다.

다음 검증 대상은 새로운 잔량/파일/권한 반복 진단이 아니라 현재 모델의 배터리 조회 명령 의미·입력/응답 계약·실제 read-back 근거입니다. 현재 자료 대조로는 그 연결 고리를 확정하지 못했습니다. 승인 범위를 OEM 호출·상시 관리자·자동 상승·서비스/드라이버/ACL 변경으로 확대하지 않습니다.

단일 조회의 관리자 관련 설명을 좁히고 합성 회귀 사례를 추가했습니다. 전체238개 통과·빌드 경고/오류0개이며 새 OEM 실행 파일은 만들지 않았습니다. 아래는 이전 이력입니다.

## 한정된 관리자 읽기 비교 승인

2026-11-03 사용자가 같은 Windows 계정에서 별도 WmiAccessCheck로 일반 권한과 한 번의 관리자 권한으로 고정 두 WMI 속성만 읽어 비교하는 절차를 승인했습니다. [실행 안내](WMI_PERMISSION_COMPARISON_RUN.md)에 범위를 기록했습니다. 프로그램 공유나 이 한정 비교에 같은 승인을 다시 요청하지 않습니다.

실제 Windows 노트북 결과는 아직 받지 않았습니다. 기존 검증된 asInvoker ZIP을 그대로 사용하고 메인 앱의 관리자 실행·서비스/드라이버·ACL 변경·OEM 메서드·삼성 DLL 실행은 하지 않습니다. 다른 계정 자격 증명이 필요하거나 토큰 상태가 불분명하면 비교를 확대하지 않습니다. 아래 승인 대기 설명은 당시 이력입니다.

## PacketPrivacy 적용 후에도 권한 거부 지속

사용자 TXT samsung-files-20261102T154749에서도 두 WMI 클래스가 AccessDenied입니다. SABI NotFound와 Samsung 후보 7개 Stopped/Manual도 같습니다. 암호화 명시만으로 해결되지 않았음을 기록하고 같은 파일 목록·기존 TXT·삼성 원본을 다시 요청하지 않습니다.

[별도 asInvoker 권한 비교 도구](WMI_PERMISSION_COMPARISON_REVIEW.md)를 소스·실행 파일·테스트까지 준비했습니다. 현재 토큰 상승 여부와 고정 읽기의 Connect/Query/Enumerate/ReadProperties 단계를 확인하지만 UAC·runas·ACL 변경·임의 쿼리·파일 쓰기는 없습니다. 메인 앱에서 실행하지 않으며 관리자 비교 실행은 아직 승인받거나 수행하지 않았습니다.

다음 필요한 결정은 이 한정된 별도 도구로 일반 권한과 한 번의 관리자 권한에서 같은 두 속성을 읽어 비교할지입니다. 프로젝트 AGENTS.md의 명시적 승인 조건을 따릅니다. 비교 성공을 보장하지 않으며, 충전 명령·삼성 DLL·서비스/드라이버 변경은 범위 밖입니다. 이번 테스트237개 및 전체 솔루션 빌드 경고·오류 0개이며 Windows 실기는 미검증입니다.

## 실제 WMI 권한 결과 반영 후

사용자 TXT samsung-files-20261102T152127에서 SABI NotFound, Samsung 후보 7개 모두 Stopped/Manual, 두 WMI 클래스 AccessDenied를 확인했습니다. 앱 실행·TXT 생성 성공을 인스턴스 조회 성공으로 바꾸지 않습니다. 같은 자료나 삼성 DLL/EXE를 다시 요청하지 않습니다.

[이번 근거·구현](WMI_ACCESS_RESULT_AND_TRANSPORT_REVIEW.md)에 따라 현재 사용자 권한으로 PacketPrivacy를 명시하고, 관측을 독립적으로 설명하는 화면/보고서 요약과 순수 wsabi 요청 프레임 인코더를 추가했습니다. 기본 Impersonate를 명시하는 것만이 수정 근거가 아닙니다. RequiresEncryption이 실제 원인인지, ACL·제공자 권한 문제인지, 새 연결에서 해결되는지는 아직 미검증입니다.

전체 228개 테스트와 별도 배포 검증 6개 통과, WPF/XAML 빌드 경고·오류 0개입니다. 인코더는 실행에 연결하지 않았으며 OEM 메서드·삼성 DLL·드라이버/서비스 변경은 하지 않습니다. 실제 제어는 계속 Unsupported입니다. 다음 실제 읽기는 모델·명령·응답 계약과 접근 권한 검증이 선행되어야 하며 권한 상승·ACL 수정은 자동 진행하지 않습니다.

## WMI 인스턴스 속성 조회 구현 후

사용자가 커널 드라이버 확인판의 실제 노트북 실행과 samsung-files TXT 생성을 확인했습니다. TXT 내용은 업로드되지 않았으므로 조회 성공·드라이버 상태까지 확인했다고 해석하지 않습니다. 같은 자료나 삼성 DLL/EXE를 다시 요청하지 않습니다.

저장된 다음 방향에 따라 [WMI 인스턴스·버전·활성 속성 조회](SAMSUNG_WMI_INSTANCE_INSPECTION.md)를 구현했습니다. ROOT\WMI의 WmiAcpiVersion.Active/version과 WmiAcpiMethod.Active만 읽고 클래스별 결과를 구분합니다. InstanceName·키·경로·식별자·DataBuffer는 읽지 않으며 OEM 메서드·삼성 DLL·서비스 변경은 실행하지 않습니다. 버전 원값·Active는 모델 호환성이나 배터리 보호 상태가 아닙니다.

이번 전체 소스 테스트 217개 및 별도 배포 검증 6개 통과, WPF/XAML 빌드 경고·오류 0개입니다. 실제 Windows 제공자의 새 속성 조회는 미검증입니다. 다음 실제 상태 읽기/제어는 명령 의미·모델 적합성·응답 계약이 확보되는 별도 단계이며 Unsupported 쓰기 차단을 유지합니다. 아래는 이전 단계 이력입니다.

## 커널 드라이버 읽기 전용 조회 구현 후

기준 커밋 `4492bbaa6f9cb87a9fb7c24969c6f1efcf6b6bd9`에서 이어서 [삼성/SABI 커널 드라이버 상태 조회](SAMSUNG_KERNEL_DRIVER_INSPECTION.md)를 구현했습니다. 기존 삼성 파일 정보 버튼에 로컬 `Win32_SystemDriver`의 이름 후보 등록·실행 상태·시작 방식과 SABI 이름 결과 비교를 통합했습니다. 이름 후보만 분류하며 원래 서비스 이름·전체 경로·사용자 이름·고유 식별자는 내보내지 않습니다. 정상 완료의 미관측, 일부 관측, 권한 거부, 오류와 시간 초과를 구분합니다.

이번 환경에서 공유 소스 204개 통과, WPF/XAML x64 net48 빌드 경고·오류 0개입니다. Windows의 새 드라이버 조회는 아직 실기 미검증입니다. 기존 SABI 이름 NotFound를 드라이버 미설치나 배터리 기능 부재로 확정하지 않으며, 등록·Running 관측도 충전 제어 가능으로 승격하지 않습니다. 드라이버 설치·시작·중지, 삼성 DLL 초기화, OEM 명령, 펌웨어 쓰기는 연결하지 않았습니다.

다음 실기 확인은 새 드라이버 섹션의 로컬 관측을 확인하는 범위입니다. 이전 배터리 진단·파일 목록·DLL을 다시 요청하지 않습니다. 기존 WMI 전송 구조·순수 응답 검증 코드와 알려진 DLL 분석은 유지합니다. 실제 상태 조회/제어는 호출 규약과 모델 적합성 근거가 확보되는 별도 단계입니다. 아래 메모들은 이전 작업 이력입니다.

## SABI 이름 결과 수신·WMI 규약 검토 후

`samsung-files-20261101T132149`에서 SABI 연결 이름 NotFound를 확인했습니다. 기존 파일들의 해시·버전은 직전 보고서와 같습니다. [이번 관측과 별도 WMI 전송 분석](SABI_LINK_RESULT_AND_WMI_REVIEW.md)을 우선 읽으세요. Sabi3 초기화로 바로 진행하지 않습니다. 기존 서비스 wsabi는 WMI에 21바이트 입력·16바이트 payload를 전달하며 SABI 장치 이름 조회와 독립된 경로입니다. 정확한 제공자 응답 길이와 모델별 배터리 명령 지원은 아직 미검증입니다.

같은 진단·파일 목록·DLL을 다시 요청할 필요는 없습니다. 이번 변경은 Sabi3 선행 조건 설명과 순수 WMI 응답 검증 코드이며 새 실행용 ZIP을 만들지 않습니다. 다음 구현은 기존 WMI 경로의 인스턴스/버전/활성 상태와 호출·응답 조건을 확인하는 방향입니다. 실제 보호 상태 조회와 모든 쓰기는 아직 연결하지 않습니다.

## 제공받은 Sabi3 x64 분석 후

요청한 x64 DLL을 받아 해시 일치를 확인하고 정적으로 분석했습니다. [확정된 규약과 구현](SABI3_NATIVE_ABI_REVIEW.md)을 우선 읽으세요. 실제 버퍼 접근은 11바이트이므로 기존 공개 예제 기반 4바이트 decoder를 수정했습니다. 이 DLL이나 x86을 다시 요청할 필요는 없습니다. 다음 실제 관측은 새 TXT의 **SABI 장치 연결 이름**입니다. QueryDosDevice는 이름 조회만 하며 장치를 열거나 DLL/IOCTL을 실행하지 않습니다.

## 초기화 규약 검토 단계

최신 import 함수 TXT의 Windows 결과를 확인했습니다. [초기화 규약 검토 및 다음 대상](SABI3_INITIALIZATION_REVIEW.md)을 우선 읽으세요. 공개 자료와 기존 분석 ZIP에 현재 Sabi3 초기화 구현이 없어 다음 분석에는 크기 28,976바이트인 x64 Sabi3.dll 자체가 필요합니다. 동일 TXT를 다시 만들 단계가 아닙니다.

공개 참조 계약의 응답을 해석하는 순수 decoder를 구현했습니다. 미지원(0xFF), OFF(0), ON(1), 기타·API 오류·길이 오류를 구분하고 실제 하드웨어 관측이나 80% 상한으로 승격하지 않습니다. 실제 DLL 호출은 아직 연결하지 않았습니다.

## 실제 파일 식별 결과 수신 후

`samsung-files-20261101T105906`에서 Sabi3 3.2.0.0 x64/x86 및 예상 함수 5개, 여러 wsabi 변형과 두 EXE를 확인했습니다. [이번 분석 및 구현](SABI3_COMPATIBILITY_REVIEW.md)을 우선 읽으세요. 현재 단계는 DLL 전체를 다시 찾는 것이 아니라 정적 함수 참조로 초기화·드라이버 연결을 검토하는 것입니다. 현재 앱에서 삼성 파일 정보 버튼의 결과에 import 함수와 후보 판정을 추가했습니다. 실제 OEM 함수는 호출하지 않습니다.

## 작업 재개 후 구현

사용자가 개발 재개를 요청해 파일 식별과 표준 PE 참조/함수 조회를 구현했습니다. [삼성 파일 정보 기능](SAMSUNG_FILE_INSPECTION.md)은 명시적 버튼으로 원본 복사·삼성 코드 실행 없이 로컬 TXT를 만듭니다. 아래 메모와 이전 배포 기준은 재개 전 이력입니다. 새 기능의 Windows 실기 실행은 아직 미검증입니다.

다음 확인 자료는 새 버튼으로 생성되는 `samsung-files-*.txt`입니다. 기존 배터리 진단이나 삼성 바이너리를 반복 제출할 필요는 없습니다. 그 결과로 현재 DLL의 ABI·초기화 부작용·모델 적합성을 검토한 뒤 근거가 확보될 때 실제 설정 조회 단계로 진행합니다.

## 재개 기준

사용자는 남은 사용량을 고려해 이번에는 파일 역할 정리와 다음 개발 준비만 요청했습니다. 설치 경로는 `C:\Program Files (x86)\Samsung\Setting`이며 참고 정보입니다. 클라우드에서 직접 접근한 경로가 아닙니다. 삼성 파일을 이번 단계에서 추출·로드·실행하지 않았습니다.

- 실제 기기: Samsung 940X3G/930X3G, BIOS P05ACJ.128.140819.dg, Windows 10 Home 19045 x64, Samsung Settings 2.2.0.
- Settings와 BIOS에는 배터리 보호 메뉴가 없다는 사용자 보고가 있음. 다시 점검하도록 요구하지 않음.
- 배터리 표시·읽기 전용 진단은 확인됨. 최신 TXT는 52%, AC 연결, 충전 중이며 두 잔량 조회가 일치함.
- 표준 요청 지원 값은 `0x80000000`. 표준 충전·방전 요청 지원 비트가 없으며 이 경로를 제어에 사용하지 않음.
- 실제 80%/100% 제어는 Unsupported. 잔량·사용자 선택값·실제 설정은 계속 분리함.
- 현재 앱 소스/배포 기준 커밋: `9a9e1a7db16fe705a42236c366e027c5a41b91e1`. 이후 변경은 조사 문서뿐임.
- [현재 실행용 ZIP](https://github.com/dropboxqfml-code/codex/raw/9a9e1a7db16fe705a42236c366e027c5a41b91e1/downloads/ATIVBatteryGuard-DIAGNOSTIC-ASSESSMENT.zip). 138개 테스트 통과·빌드 경고/오류 0개는 해당 앱 버전의 기록이며 이번 문서 정리에서 재실행한 결과가 아님.

## 이번에 확보한 파일 단서

사용자는 위 폴더에서 `Sabi3.dll`, `wsabi.dll`, `BatteryToast.exe`, `PowerAudit.exe`의 존재를 보고했습니다. `charge` 키워드 일치 파일은 없었습니다. 실제 버전·비트 수·서명·함수·참조 관계는 아직 확인하지 않았습니다.

- `Sabi3.dll`: 공개 Windows 원본에 배터리 보호 조회·변경 호출 근거가 있음. 가장 먼저 조사할 대상.
- `wsabi.dll`: 삼성 WMI/COM 중계 후보. 이전 팬·정숙 모드 분석과 이번 설치 파일의 동일성부터 구분해야 함.
- `BatteryToast.exe`: 배터리 알림 보조 프로그램일 가능성. 이름에 따른 추정이며 기능을 확인한 결과가 아님.
- `PowerAudit.exe`: 전원 점검 보조 프로그램일 가능성. 이름에 따른 추정이며 읽기 전용인지도 미확인.

[DLL 후보 목록과 출처](SAMSUNG_DLL_CANDIDATES.md), [공개 제어 규약 검토](PUBLIC_CONTROL_PROTOCOL_REVIEW.md)를 함께 읽을 것. 공개 소스의 명령 후보를 현재 DLL의 ABI나 WMI 입력으로 곧바로 취급하지 않음.

## 다음 작업 순서

1. **실행하지 않는 로컬 파일 식별 기능부터 준비한다.** 위 네 파일의 파일명·버전·제품 설명·32/64비트 구조·서명 상태를 확인하는 범위를 설계한다. 원본 바이너리를 복사·업로드하는 기존 수집 기능을 다시 켜지 않는다. 서명 확인도 앱의 네트워크 통신 0건 조건을 지키며, 오프라인에서 확인되지 않은 상태와 서명 불일치를 구분한다.
2. **참조 관계와 내보낸 함수 정보를 정적으로 확인한다.** Sabi3의 필요한 함수가 있는지, EXE가 어느 DLL을 참조하는지 확인한다. 정적 참조가 없더라도 간접 로드·프로세스 간 통신 가능성을 배제하지 않는다. 이름·함수 존재·서명만으로 제어 가능하다고 표시하지 않는다.
3. **현재 DLL에 맞는 호출 계약과 조회의 부작용을 검토한다.** 공개 예제와 버전·호출 규약·드라이버 의존성을 대조한다. DLL이 x86이면 현재 x64 앱에서 직접 호출할 수 없으므로 향후 분리 구성을 검토한다. 이 단계까지는 DLL 초기화·OEM 메서드 호출을 추가하지 않는다.
4. **근거가 확보되면 실제 상태 읽기 어댑터를 먼저 구현한다.** 조회 성공, 미지원, 오류, 상태 불명을 구분한다. 공개 예제처럼 미지원 응답을 ‘보호 OFF’로 바꾸지 않는다. 사용자 선택값이나 잔량으로 실제 설정을 대신하지 않는다.
5. **실제 변경은 모델 적합성과 안전성이 확인된 후속 단계로 둔다.** 현재 물리 어댑터의 쓰기 차단을 유지한다. 커널/펌웨어 제어 추가는 AGENTS.md의 별도 승인·검증 조건을 따른다.

지금은 같은 배터리 진단이나 삼성 파일의 추가 제출을 요청할 필요가 없습니다. 다음 개발은 파일 식별에서 출발하며, 실제 제어를 이미 구현했다고 표현하지 않습니다.
