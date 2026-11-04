# WMI 사전 검증 경로 정보 보완 — Locator-v2

**실기 결과 수신:** 사용자 노트북에서 Elevated·Complete·Ready·None, OEM 호출/예약 접근 없음을 확인했습니다. [전체 해석과 기존 승인 조회 수정본](WMI_QUERY_LOCATOR_READY_RESULT.md)에 기록했습니다. 같은 무호출 점검을 반복할 필요는 없습니다. 아래는 최초 배포 기록입니다.

2026-11-04, [직전 실기 분석](WMI_PREFLIGHT_ENUMERATION_RESULT.md)의 다음 수정 범위인 경로 정보 확보 옵션과 오류 분류 세분화를 구현했습니다. 대상은 OEM 호출 없는 별도 WmiPreflightCheck입니다. 이전 실험의 실행 코드·예약·정책과 메인 앱은 그대로 보존합니다.

## 변경 내용

`SELECT Active FROM WmiAcpiMethod`에만 `EnsureLocatable=true`를 지정합니다. 이 옵션은 쿼리 결과의 위치 정보를 확보하도록 WMI에 요청합니다. 모델·BIOS 쿼리의 옵션은 기본 false를 유지합니다. 고정 쿼리, DirectRead, 전체 열거 완료·정확히 한 행·Active=True, 고정 클래스와 경로 길이, 입력 형식 검사는 그대로입니다. 대상을 추측하거나 검사를 건너뛰는 경로는 없습니다.

근거는 Microsoft의 [공식 API 설명](https://github.com/dotnet/dotnet-api-docs/blob/main/xml/System.Management/EnumerationOptions.xml)과 [고정 버전 구현](https://github.com/dotnet/runtime/blob/v8.0.0/src/libraries/System.Management/src/System/Management/ManagementOptions.cs)입니다. 옵션은 경로 정보를 요청하지만 기존 실패가 경로 누락 때문이었다는 증거나 실제 제공자의 성공 보장은 아닙니다.

기존 `InactiveOrInvalidTarget`은 과거 결과를 그대로 해석하기 위해 남기고 다음 오류를 추가했습니다. 원문 객체·경로·키는 보고서에 저장하지 않습니다.

| 새 오류 | 의미 |
| --- | --- |
| RowObjectUnavailable | 반환 행을 대상 객체로 확인하지 못함 |
| PathMissing | 경로 정보가 없음 |
| PathNotInstance | 경로가 인스턴스를 가리키지 않음 |
| PathClassMismatch | 경로의 클래스가 고정 대상과 다름 |
| RelativePathMissing | 상대 경로가 없음 |
| RelativePathTooLong | 상대 경로가 기존 길이 제한을 초과함 |
| TargetInactive | 정상 Boolean 형식으로 읽은 Active가 false |

Active 필드 없음·형식 불일치·잘못된 값은 기존 별도 오류를 유지합니다. `TargetInactive`도 배터리 보호 OFF/ON을 뜻하지 않습니다. `Complete`는 관측 단계의 판정 완료이며 `Ready`도 준비 검사 통과만 뜻합니다. 모두 실제 충전 제어는 Unsupported입니다.

## 실행 범위와 새 확인 항목

새 출력의 고정 표시는 **점검판: 경로 정보 확보 보완판 (Locator-v2)**입니다. 같은 EXE 이름의 이전 파일과 혼동하지 않도록 새 ZIP 이름을 사용합니다.

1. [새 LOCATOR ZIP](../downloads/README.md) 전체를 이전 도구와 다른 새 로컬 폴더에 압축 해제합니다.
2. 같은 Windows 계정에서 새 폴더의 `ATIVBatteryGuard.WmiPreflightCheck.exe`만 수동 관리자 실행합니다. 다른 관리자 계정의 암호가 필요하면 중단합니다. 자동 권한 상승은 없습니다.
3. `(Locator-v2)` 표시와 사전 검증 단계·원인 분류·준비 조건을 확인하고 새 출력만 복사해 전달합니다. 준비 완료여도 OEM 실행으로 이어지지 않습니다.

OEM 호출·예약 파일 읽기/쓰기/삭제·삼성 DLL 실행·드라이버/서비스/ACL/보안 설정 변경·펌웨어 쓰기·네트워크 통신은 없습니다. 입력 객체와 DataBuffer 생성은 메모리 준비만 합니다. 부모와 작업자의 독립 10초 제한, 사전 검증의 6초 예산도 유지합니다.

이전 `WmiOneShotQuery.exe`는 재실행하지 않으며 기존 예약 표식도 삭제·초기화하지 않습니다. 과거 TXT·삼성 DLL·EXE·파일 목록·권한 비교 결과는 다시 제출할 필요가 없습니다. 새 Windows 점검판의 실기 결과는 아직 받지 않았습니다.

## 검증

전체 솔루션과 portable 테스트를 Release 빌드하고, 오류 분류·엄격한 준비 완료 조건·개인정보 제한과 과거 enum/모호한 결과 보존을 검사합니다. 실제 Windows WMI나 OEM 명령은 클라우드에서 실행하지 않습니다.

이번 전체330개와 Python 배포 검증10개가 통과했고, 여섯 프로젝트 및 테스트 프로젝트 빌드는 각각 경고·오류0개입니다.

패키저는 메서드 쿼리에만 적용된 옵션, 새 바이너리의 옵션 setter와 점검판 표시, 호출/예약 참조 부재, x64/asInvoker, 전체 소스 대응, 고정 파일 목록과 ZIP CRC·SHA-256을 확인합니다. 실행 ZIP에는 삼성 원본 DLL과 이전 실험 EXE가 없습니다. 정확한 이번 검증 수치는 [VALIDATION](VALIDATION.md)에 기록합니다.
