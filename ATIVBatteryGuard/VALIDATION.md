# Settings 앱 분석판 검증 기록

## 공식 지원 검토판의 현재 상태

새 제품 시작 구성은 OEM 파일 수집기와 확인 콜백을 전달하지 않습니다. 수집 명령은 비활성화되고 직접 비동기 호출도 작업 없이 반환합니다. 기존 수집 코드는 소스 이력과 회귀 검증을 위해 보관하며 현재 제품 경로에서 사용하지 않습니다.

문의문 복사는 장치 정보 조회 완료 후에만 사용할 수 있고, 조회 갱신 중의 오래된 값과 종료 후 복사를 차단합니다. 공개 장치 정보 필드만 사용하며 상세 오류와 경로를 문의문에서 제외합니다. 클립보드에 복사할 뿐 실제 문의 제출·네트워크 통신은 수행하지 않습니다.

이 변경을 포함한 전체 portable suite는 **114개 통과·실패 0개·건너뜀 0개**, 실제 WPF 빌드는 경고·오류 0개입니다. Windows에서 새 문의 복사 동작은 아직 미검증입니다. 아래 표와 수집 절차는 이전 단계의 기록입니다.


2026-10-31 한국 시간 기준입니다. 이전 WMI 진단판의 확인 결과와 이번 Settings 수집 변경을 구분합니다.

## 이전 WMI 정의 진단판

| 항목 | 실제 확인 결과 |
| --- | --- |
| .NET Framework 4.8 x64 WPF 빌드 | 성공, 경고 0개·오류 0개 |
| 공유 Core·ViewModel 및 WMI 정책 회귀 테스트 | 78개 통과·실패 0개·건너뜀 0개 |
| 실행 파일 정적 검사 | x64 GUI, .NET 4.8 참조, 관리 진입점 확인 |
| 실제 XAML 컴파일 산출물 | `app.baml`, `views/mainwindow.baml` 포함 확인 |
| 일반 권한 manifest | `asInvoker` 포함 확인 |
| Windows 노트북 앱 실행 | 사용자 화면으로 창·배터리 표시 확인 |
| 실제 WMI 클래스 정의 | 사용자 TXT에서 정확한 클래스 3개·메서드 서명 확인, 조회 오류 없음 |

사용자 최신 관측은 배터리 62%, AC 연결 안 됨, 방전 중이며 Win32와 WMI 잔량이 일치했습니다. 이전 0%는 과거 관측이며 현재 고정값이 아닙니다. 클래스 정의 조회는 메서드를 실행하거나 충전 제한을 적용한 시험이 아닙니다.

## 새 Settings 앱 파일 수집

| 항목 | 현재 상태 |
| --- | --- |
| 새 변경의 WPF 빌드 | 성공, 경고 0개·오류 0개 |
| 새 변경의 portable 회귀 테스트 | 108개 통과·실패 0개·건너뜀 0개 |
| 새 수집 기능의 Windows 동작 | 미검증, 새 ZIP 결과 필요 |
| Windows GUI 자동 self-test | 미실행 |
| 실제 충전 제한 | 구현하지 않음, 항상 미지원 |

새 suite는 기존 78개와 Settings 경계 검사 30개를 이번 변경에서 다시 실행했습니다. pure 정책과 공유 Core·ViewModel의 회귀 검증이며, Windows Registry 열거·파일 수집을 실행한 결과가 아닙니다.

재실행할 주요 명령입니다. `dotnet`은 .NET 8 SDK를 사용합니다.

```sh
dotnet restore ATIVBatteryGuard.sln
dotnet build ATIVBatteryGuard.sln -c Release --no-restore -p:UseSharedCompilation=false -m:1
dotnet run --project tests/ATIVBatteryGuard.PortableTests.csproj -c Release --no-restore -p:UseSharedCompilation=false -- --report reports/portable-tests.json
python scripts/package_preview.py --test-report reports/portable-tests.json
```

Windows용 `scripts/Test-Windows.ps1`은 제공하지만 이 환경에서는 실행하지 않았습니다. 빌드 성공·클래스 발견·파일 수집 성공을 실제 충전 제어 성공으로 해석하지 않습니다. 과거 149개 또는 이전 WMI 판의 78개 시험 기록을 새 변경의 시험 수치로 재사용하지 않았습니다.

## 위치 누락 수정판

사용자 ZIP에서 앱 등록만 있고 설치·아이콘 위치가 없는 원인을 확인했습니다. 수정 후 전체 portable suite는 108개이며 등록 불일치/제공 경로의 대체 조회 금지와 고정 후보 범위를 검사합니다. 새 native 대체 조회는 Windows 결과가 필요합니다.
