# 복원·정의 진단판 검증 기록

2026-10-31 한국 시간 기준입니다.

| 항목 | 실제 확인 결과 |
|---|---|
| .NET Framework 4.8 x64 WPF 빌드 | 성공, 경고 0개·오류 0개 |
| 공유 Core·ViewModel 및 WMI 정책 회귀 테스트 | 78개 통과·실패 0개·건너뜀 0개 |
| 실행 파일 정적 검사 | x64 GUI, .NET 4.8 참조, 관리 진입점 확인 |
| 실제 XAML 컴파일 산출물 | `app.baml`, `views/mainwindow.baml` 포함 확인 |
| 일반 권한 manifest | `asInvoker` 포함 확인 |
| 독립 코드 검토 | 메타데이터 진단의 실행·쓰기·외부 통신 경로 발견하지 못함 |
| Windows에서 새 앱 GUI 실행 | 미실행 |
| 노트북의 실제 WMI 클래스 정의 조회 | 미실행, 새 TXT 결과 필요 |
| 실제 충전 제한 | 구현하지 않음, 항상 미지원 |

Linux에서 실제로 사용한 주요 명령입니다. `dotnet`은 준비된 .NET SDK 8.0.427입니다.

```sh
dotnet restore ATIVBatteryGuard.sln
dotnet build ATIVBatteryGuard.sln -c Release --no-restore -p:UseSharedCompilation=false -m:1
dotnet run --project tests/ATIVBatteryGuard.PortableTests.csproj -c Release --no-restore -p:UseSharedCompilation=false -- --report reports/portable-tests.json
python scripts/package_preview.py --test-report reports/portable-tests.json
```

Windows용 `scripts/Test-Windows.ps1`은 제공하지만 이 환경에서는 실행하지 않았습니다. 빌드 성공이나 WMI 클래스 발견을 실제 충전 제어 성공으로 해석하지 않습니다. 이전 배포본의 149개 시험 기록도 이번 결과로 재사용하지 않았습니다.
