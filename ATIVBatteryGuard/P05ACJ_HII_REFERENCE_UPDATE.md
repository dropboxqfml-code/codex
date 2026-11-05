# P05ACJ 설정 참조 검사·후보 경로 구분 — 2026-11-06 한국 시간

이번에는 기존 명령표를 다시 대조하는 대신, 확보한 P05ACJ 설정 리소스의 배터리80%/100% 문구가 실제 설정 구문에 연결되는지 검사 범위를 넓혔습니다. **현재 모델의 충전 제한 명령·응답 계약은 이번에도 확정하지 못했습니다.** 실제 제어는 Unsupported입니다. 앱 실행 파일을 바꾸거나 새 노트북 시험을 요청하지 않습니다.

## 확인한 자료와 새 검사 범위

대상은 기존 CAP에서 추출한 Setup HII 리소스333,801바이트/SHA-256 `53ec78bfce49bf65858d64aaadee9fbb31abf79088ee0c9b60c28783a6ddf527`입니다. 원본 CAP의 SHA는 `052660c18e967f7f73b2881379066bde4b90b29192ce4292c8d29bef1ce92ab0`이며 [원본 인입·신뢰 한계](COMMAND_SOURCE_ARTIFACTS_AND_ACCESS.md)를 유지합니다. 이것은 이전 관측 바이트와의 일치이며 현재 노트북의 펌웨어 동일성·제조사 진위 검증이 아닙니다.

이전 ad-hoc 검사는6종 question opcode를 중심으로 살폈습니다. 새 개발용 `scripts/inspect_p05acj_hii_references.py`는 AMI의 count-prefixed 리소스 경계와 package-local scope를 확인하고,11종 표준 statement의 공통 prompt/help 헤더를 인덱싱합니다. Subtitle/Text/OneOf/CheckBox/Numeric/Password/Action/ResetButton/Ref/String/OrderedList를 포함합니다. 실제 참조를 바이트 재검색으로 만들어내지 않고, 조건·기본값·변수·펌웨어/AML을 평가하지 않습니다.

| 관측 범위 | 결과 |
| --- | --- |
| 패키지 | 전체11개, Forms10개 |
| Forms opcode | 12,447개 |
| 지원한 공통 statement 헤더 | 2,648개 |
| vendor GUID opcode | 34개. 내부 의미는 해석하지 않음 |
| Battery Life Cycle Extension | 지원한 헤더의 prompt/help/쌍 참조 모두0 |
| USB Charge In Sleep Mode | prompt/help/쌍 각각1, CheckBox |
| Smart Battery Calibration | prompt/help/쌍 각각1, Ref |

USB와 보정은 같은 리소스에서 구분된 실제 statement 참조로 관측됐습니다. 보정 도움말은 완전 방전을 통한 잔량 보정을 설명하고, USB 수면 충전은 노트북 배터리 상한과 다른 대상입니다. 배터리80%/100% 문자열만으로 조작 가능한 설정이 있다고 보지 않습니다.

**0회는 지원한 표준 헤더 범위의 미관측입니다.** vendor GUID payload·다른 리소스/볼륨·동적 문자열/메뉴 구성·현재 장치 차이를 닫은 것은 아닙니다. 전체 IFR 의미·표시 조건·사용 가능 메뉴·하드웨어 기능 부재·배터리 명령을 판정하지 않습니다. 보유 자료에서 이 문구와65/66 또는 설정 처리자를 연결하지 못했다는 한계만 기록합니다.

## 새로 구분한 배터리 시험 경로

동일 FV 파일251개에서 문자열을 정적으로 조사해 OFBD/1.efi의 배터리 신뢰성 시험 문맥을 추가로 찾았습니다. 모듈은12,864바이트/SHA-256 `a47db1b5de6ad1e3def1cf20a256373045de08a409a01409e56c5e83cf2456c5`입니다. 문자열 존재만으로 배터리 제어라고 판단하지 않고 실제 분기를 따라갔습니다.

RVA18FB–192C의 문자열 비교 분기는 설정 helper1E10으로 이어지고, 그 helper는 IN/OUT 포트 접근 helper1E80/1E85를 호출합니다. 출력 문구는 배터리 신뢰성 시험 flag 설정을 뜻합니다. 이것을80% 상한 조회/설정 계약으로 연결할 근거는 없습니다. **이 경로는 읽기 전용 진단이나 충전 제한의 대체 경로로 사용하지 않습니다.** 원본 프로그램/EFI를 실행하거나 포트/CMOS/EC를 읽거나 쓰지 않았습니다. 실행 인수·포트 주소·설정 절차는 배포하지 않습니다.

기존 Smart Battery Calibration, Battery Test Mode 문자열, 이번 시험 flag와 실제 충전 상한을 혼동하지 않습니다. 숫자나 'battery'/'charge' 문자열의 일치만으로 대체 명령을 만들지 않습니다.

## 구현한 개발 도구의 경계

- 입력은 고정 리소스의 길이·SHA를 먼저 대조합니다. 다른 바이트는 해석 전에 거부하며 CLI는 기대 해시나 token 사양 덮어쓰기를 허용하지 않습니다. token 라벨은 이 리소스의 보존 en-US 문자열 분석에만 묶여 있습니다.
- 입력1MiB, package64개, Forms opcode32,768개, scope깊이64 상한을 둡니다. 길이·개수·끝 경계·scope 오류나 상한 초과가 있으면 참조 결과를 모두 폐기합니다. 앞부분에서 찾은 참조를 부분 성공으로 내보내지 않습니다.
- 파일 stat/fstat와 cap+1 읽기로 과대 파일·파일 증가 경쟁을 제한하고 링크/비정규 파일을 거부합니다. 입력 경로·사용자 이름·원문 예외·변수값·원시 주소/ID/오프셋은 출력하지 않습니다.
- 출력은 고정 범주·참조 수·statement 종류·내용 해시뿐입니다. references가0이어도 기능 부재나 메뉴 숨김을 판정하지 않으며, 모든 모델/제조사/계약/하드웨어 권한은false입니다.
- Python 표준 라이브러리만 사용합니다. 다운로드·추출·외부 프로세스·native 로더·네트워크·OEM/UEFI/AML 실행 기능이 없습니다. 노트북 사용자용 진단이나 실제 앱 호출 경로에 추가하지 않았습니다.

## 검증과 현재 배포

Python 전체 **60개 통과**(reports/p05acj-hii-python-tests.log). 신규12개는 조건부 scope를 평가하지 않는 헤더 인덱싱, prompt/help/쌍 구분,11종 statement, vendor/미지원/non-Forms payload의 가짜 token 무시, package-local scope, 길이/개수/순서·늦은 실패의 원자적 폐기, 숫자형 크기·상한, hash 선검사, CLI 덮어쓰기/경로 비노출, stat/fstat 이후 파일 증가의 cap+1 읽기를 검사합니다.

실제 고정 리소스의 `ObservedResourceIndexed` 결과는 reports/p05acj-hii-reference-review.json에 저장했습니다. 별도의 보존 범용 byte-walk 결과와 package/opcode 수 및 두 참조의 종류/횟수를 대조했습니다. 내용 전체의 의미나 visibility를 검증한 것이 아닙니다. static 분석은 trusted pefile2024.8.26/Capstone5.0.6으로 데이터로만 읽었고 제조사 코드는 실행하지 않았습니다.

C#/WPF/실행 파일은 변경하지 않아 빌드와 C# 테스트를 이번에 반복하지 않았습니다. 직전435개·빌드 경고/오류0개는 [직전 버전](WINDOWS_CALLER_CONTRACT_UPDATE.md)의 기록입니다. 현재 프로그램은 CALLER-CONTRACT-REVIEW 그대로 사용합니다. 새 개발 소스는 [소스 ZIP](../downloads/ATIVBatteryGuard-HII-REFERENCE-SOURCE.zip)으로 제공하며 실행에 필요하지 않습니다. 원본 펌웨어·삼성 파일·사용자 자료·실행 파일은 포함하지 않습니다.

## 남은 근거와 다음 작업의 기준

새 공개 근거도 제한적으로 확인했습니다. GitHub의 repository 검색2개(940X3G+Settings, Samsung+Settings+BatteryLifeExtender), issue 검색1개(930X3G+battery)는 각0건이었습니다. 저장소/이슈 인덱스의 해당 질의 결과일 뿐 전체 공개 코드나 제조사 기능의 부재를 뜻하지 않습니다. 검색 기록과 원본은 비공개 개발 캐시에 보존했습니다.

현재 보유 자료에서는 **현재 모델의 OEM 배터리 caller/지원 조건 → 펌웨어 처리자 → 상태/상한 응답 계약**을 입증할 연결을 찾지 못했습니다. 같은 진단이나 다른 기능의 비슷한 명령을 더 실행해도 이 근거가 생기는 것은 아닙니다. 제어 구현은 모델별 계약 근거 부족으로 보류하며 기존 Unsupported·완료된 실험 예약을 유지합니다. 추가 업로드·반복 진단·관리자 비교·OEM 재호출·보안/드라이버/펌웨어 변경은 요청하지 않습니다.

다음 구현을 열 수 있는 근거는 적용 모델이 확인되는 OEM 배터리 호출자/지원 조건 또는 해당 펌웨어 처리 계약입니다. 그러한 새 출처가 확보되기 전에는 UI에 실제 제어를 추가하거나 쓰기를 허용하지 않습니다.
