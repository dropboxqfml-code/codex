# ATIV Battery Guard

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
