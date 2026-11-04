# 사전 검증 실기 결과 분석 — 대상 열거 단계

## 이번 관측

사용자가 전달한 WmiPreflightCheck 출력에서 아래 고정 상태를 확인했습니다. 원본 TXT는 저장소나 배포물에 복사하지 않습니다. 분석 기준은 배포 커밋 `74d18a7a26ed5dadad83c0cc2281972b57c9a6cc`입니다.

| 항목 | 관측값 | 해석 |
| --- | --- | --- |
| 토큰 | Elevated | 이번 점검은 관리자 토큰으로 진행됐습니다. |
| 사전 검증 상태 | Complete | 관측한 단계의 조건 판정이 끝났다는 뜻이며 전체 준비 성공이 아닙니다. |
| 단계 | MethodEnumeration | 메서드 인스턴스 열거·대상 조건 검사 중 중단됐습니다. |
| 원인 분류 | InactiveOrInvalidTarget | 활성 상태 또는 반환 객체·경로 조건 중 하나를 충족하지 못했습니다. |
| OEM 호출 / 예약 접근 | 모두 없음 | 이 별도 도구에는 해당 실행 경로가 없습니다. 기존 예약 유무는 알 수 없습니다. |

이 실행에서는 권한 거부나 시간 초과가 아니라 자체 대상 검증 조건의 불일치가 보고됐습니다. 모든 다른 작업의 권한이나 시간 제한까지 검증한 결과는 아닙니다.

## 코드 흐름으로 확인되는 범위

`ReadOnlyPreparationProbe.Collect()`가 MethodEnumeration에 도달했으므로 이번 실행에서는 고정 모델·BIOS 조건, 상세 클래스/입출력 정의의 binder 생성, MethodId=1, 로컬 ROOT\WMI 연결까지 통과했습니다. 열거자의 MoveNext가 적어도 한 번 성공한 흐름에서 이 분류가 나옵니다.

TargetRead에는 도달하지 않았습니다. 따라서 관측 대상을 다시 읽는 단계, 입력 매개변수/CIMTYPE 검사, 메모리 DataBuffer 생성은 이번에 미실시입니다. 이전에 검토했던 입력 qualifier나 버퍼 생성 문제를 이번 실패의 원인으로 단정하지 않습니다.

## 아직 하나로 구분되지 않은 분기

소스의 MethodEnumeration에서 InactiveOrInvalidTarget이 나오는 조건은 다음과 같습니다.

| 검사 | 가능한 중단 조건 | 이번 TXT에서 구분 가능 여부 |
| --- | --- | --- |
| 반환 객체 | ManagementObject로 해석할 수 없음 | 구분 불가 |
| Path | 없음, 인스턴스 경로가 아님, 고정 클래스와 불일치 | 구분 불가 |
| RelativePath | 비어 있거나 길이 제한 초과 | 구분 불가 |
| Active | 앞의 구조 검사가 모두 유효하고 전체 열거 완료·정확히 한 행이지만 Boolean false | 구분 불가 |

따라서 **Active=false, 전체 열거 완료, 정확히 한 행을 확정할 수 없습니다.** 여러 구조 조건을 한 오류 분류로 합친 것이 현재 보고의 한계입니다. Active는 WMI 인스턴스의 속성이며 배터리 보호 ON/OFF와도 다릅니다.

## 다음으로 검토할 구현 지점

현재 쿼리는 `SELECT Active FROM WmiAcpiMethod`이고, 결과의 `row.Path`와 `RelativePath`를 즉시 요구합니다. 그런데 EnumerationOptions에는 **EnsureLocatable이 지정되지 않았습니다.**

Microsoft 공식 [EnumerationOptions API 문서 원본](https://github.com/dotnet/dotnet-api-docs/blob/main/xml/System.Management/EnumerationOptions.xml)의 EnsureLocatable 설명은 쿼리 결과의 `__PATH`, `__RELPATH`, `__SERVER`가 NULL이 아니도록 하는 옵션이며 기본값은 false라고 명시합니다. [공식 구현의 고정 버전](https://github.com/dotnet/runtime/blob/v8.0.0/src/libraries/System.Management/src/System/Management/ManagementOptions.cs)에서도 같은 기본값과 플래그를 확인했습니다. 이 옵션은 쿼리에 적용되며 단순 인스턴스 열거에는 적용되지 않습니다. 현재 코드는 ObjectQuery의 고정 SELECT를 사용합니다.

즉, **필요한 경로 정보를 요청하는 옵션 없이 반환 객체의 경로를 필수로 검증하는 불일치**가 검토 우선순위입니다. 제공자가 이번에 실제로 경로를 생략했는지는 TXT에 기록되지 않았으므로 아직 가설입니다. 쿼리 투영이 반드시 경로를 없앤다거나 옵션 추가만으로 해결된다고 단정하지 않습니다.

이전 실험 backend에서도 같은 객체/경로 검사 실패는 FixedFailure 예외로 바뀌어 Unavailable이 됩니다. 반면 유효한 단일 행의 Active=false만으로 중단되면 TargetMismatch + Complete가 됩니다. 따라서 [이전 Unavailable 결과](WMI_ONE_SHOT_PREFLIGHT_RESULT.md)와 함께 보면 객체/경로 확인을 먼저 검토할 이유가 있습니다. 두 실행은 서로 다른 시점이므로 같은 원인이었다는 증명은 아닙니다.

## 다음 개발 범위

1. 먼저 무호출 점검 도구에서 반환 객체·경로 없음·비인스턴스·클래스 불일치·상대 경로 오류·명시적 비활성을 고정 enum으로 구분하도록 설계합니다. 경로·키·계정 원문은 보고하지 않습니다.
2. 같은 고정 SELECT와 단일 활성 대상 검사를 유지하면서 메서드 대상 쿼리에 EnsureLocatable을 명시하는 수정안을 검토합니다. 범위를 다른 모델/쿼리로 넓히거나 SELECT *로 바꾸지 않습니다.
3. 경로 조건 삭제, 경로/키 추측, 단일 대상·Active 조건 완화 없이 합성 자료와 소스 검토로 먼저 검증합니다. 기존 1회 실험의 호출 경로를 자동으로 고치거나 실행하도록 연결하지 않습니다.

이번에는 **분석 기록만 반영**했습니다. 실행 코드·기존 실험·예약·하드웨어 정책을 변경하지 않았고 새 EXE를 만들거나 OEM을 실행하지 않았습니다. 이전 파일을 다시 제출하거나 같은 점검/실험을 재실행할 필요가 없습니다. 기존 예약 표식도 그대로 둡니다. 실제 충전 제어는 계속 Unsupported입니다.

329개 테스트 통과·여섯 프로젝트 빌드 경고/오류0개는 직전 배포의 검증 기록입니다. 이번 문서 분석을 위해 빌드나 테스트를 다시 수행하지 않았습니다. 독립적인 소스 대조로 위 분기와 미진입 범위를 확인했습니다.
