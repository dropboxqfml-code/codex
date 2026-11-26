# 유지보수 파일 색인

현재 기준은 [MAINTENANCE_HANDOFF.md](MAINTENANCE_HANDOFF.md)입니다. 기존 폴더/소스/검증 파일은 이동하거나 삭제하지 않았고, 긴 README/재개 메모만 [이력 폴더](docs/history/)에 보존했습니다.

## 현재 문서와 배포

| 목적 | 파일 |
| --- | --- |
| 새 대화 시작 | [NEW_CHAT_START.txt](NEW_CHAT_START.txt) |
| 유지보수 기준·제약 | [MAINTENANCE_HANDOFF.md](MAINTENANCE_HANDOFF.md), [AGENTS.md](AGENTS.md) |
| 현재 할 일 | [NEXT_DEVELOPMENT.md](NEXT_DEVELOPMENT.md) |
| 새 환경·빌드/테스트 | [DEV_ENVIRONMENT.md](DEV_ENVIRONMENT.md) |
| 사용자 사용법 | [USER_MANUAL_031_KO.txt](USER_MANUAL_031_KO.txt) |
| 배포/변경 설명 | [RELEASE_031.md](RELEASE_031.md) |
| 현재 개인용 실행 파일 묶음 | [0.3.1 MANUAL ZIP](../downloads/ATIVBatteryGuard-0.3.1-WIN10-X64-MANUAL.zip) |
| 같은 제품의 Windows 검사 도구 | [0.3.1 FINAL-CHECK ZIP](../downloads/ATIVBatteryGuard-0.3.1-FINAL-CHECK.zip) — 재검사 필수 아님 |
| 전체 추적 파일 목록 | [TRACKED_FILES_20261126.txt](docs/maintenance/TRACKED_FILES_20261126.txt) — 이 정리 시점 스냅샷 |

## 제품 소스

| 기능 | 위치 |
| --- | --- |
| 솔루션/앱 시작·기본 로컬 저장 경로 | [솔루션](ATIVBatteryGuard.sln), [App.cs](src/ATIVBatteryGuard.App/Application/App.cs) |
| 화면 배치·상태 버튼 스타일 | [MainWindow.xaml](src/ATIVBatteryGuard.App/Views/MainWindow.xaml) |
| 닫기/IME 초안 보존 | [MainWindow.cs](src/ATIVBatteryGuard.App/Views/MainWindow.cs), [ObservationNoteViewModel.cs](src/ATIVBatteryGuard.App/ViewModels/ObservationNoteViewModel.cs) |
| 표시·명령·기록/비교 연결 | [MainViewModel.cs](src/ATIVBatteryGuard.App/ViewModels/MainViewModel.cs) |
| 그래프 그리기/입력 | [Controls](src/ATIVBatteryGuard.App/Controls/)의 BatteryObservationChart.cs, BatteryObservationChartSelection.cs |
| 버전·파일 버전 | [ApplicationRelease.cs](src/ATIVBatteryGuard.Core/Models/ApplicationRelease.cs) |
| 수동 제어 클라이언트/별도 프로세스 | [WindowsManualProtectionOperationService.cs](src/ATIVBatteryGuard.App/Services/WindowsManualProtectionOperationService.cs), [helper 프로젝트](src/ATIVBatteryGuard.ManualProtectionHelper/) |
| WMI 실제 바인딩 | [WmiInterop 프로젝트](src/ATIVBatteryGuard.WmiInterop/) |
| 고정 프로필·횟수·세션/상태 | [Core/Services](src/ATIVBatteryGuard.Core/Services/)의 ManualProtection*.cs, [ManualProtectionResult.cs](src/ATIVBatteryGuard.Core/Models/ManualProtectionResult.cs) |
| 배터리 관찰/과거TXT·그래프 | [Core/Services](src/ATIVBatteryGuard.Core/Services/)의 BatteryObservationSession.cs, BatteryObservationGraph.cs, SavedBatteryObservation.cs |
| 설정·메모·최근목록·묶음·JSON | [Core/Storage](src/ATIVBatteryGuard.Core/Storage/) |
| 실제 파일 선택/저장/폴더 열기 | [LocalUserInteraction.cs](src/ATIVBatteryGuard.App/Services/LocalUserInteraction.cs) |

상태 버튼은 MainViewModel의 `IsManual80PercentActive`/`IsManualLimitDisabled`, Window의 `ManualProtectionStateButton`을 봅니다. 표시만의 수정을 위해 helper/펌웨어 경로를 바꾸지 않습니다.

## 검증 근거

| 근거 | 파일/폴더 |
| --- | --- |
| 0.3.1 현장 GUI/버튼 사용 확인 | [FIELD_031_PERSONAL_RESULT.md](FIELD_031_PERSONAL_RESULT.md), [field-031-personal 평가/원본](reports/field-031-personal/) |
| 0.3.1 회귀1275/배포27·빌드·원본 ZIP | [release-031-validation.json](reports/release-031-validation.json), [release-031 로그](reports/release-031/) |
| 매뉴얼 교체와 동일 실행 파일 확인 | [release-031-manual-validation.json](reports/release-031-manual-validation.json) |
| 0.3.0 최종 파일 현장 확인 | [FIELD_030_PERSONAL_RESULT.md](FIELD_030_PERSONAL_RESULT.md), [field-030-personal](reports/field-030-personal/) |
| RC3 실제 IME 닫기 보존 | [FIELD_IME_CLOSE_030_RC3_RESULT.md](FIELD_IME_CLOSE_030_RC3_RESULT.md), [field-ime-close-rc3](reports/field-ime-close-rc3/) |
| 이전 실제 IME 저장 | [FIELD_IME_030_V3_RESULT.md](FIELD_IME_030_V3_RESULT.md), [field-ime-v3](reports/field-ime-v3/) — 당시 닫기 실패와 후속 RC3 성공을 구분 |
| 빠른/20분533회·취소/충돌·잠금 재시도 | [FIELD_EXTENDED_030_V2_RESULT.md](FIELD_EXTENDED_030_V2_RESULT.md), [field-extended-v2](reports/field-extended-v2/) |
| 충전 제한·해제·재시작 유지 이력 | [PROTECTION_CONTROL_FUNCTIONAL_RESULT_AND_GUI_PLAN.md](PROTECTION_CONTROL_FUNCTIONAL_RESULT_AND_GUI_PLAN.md), [MANUAL_CONTROL_BETA_RESULT.md](MANUAL_CONTROL_BETA_RESULT.md), 과거 README의 사용자 보고 |

`reports/`는 기본 ignore 대상입니다. 필요한 새 결과만 의도적으로 추가하고 기존 원본은 수정하지 않습니다. 현재 사용자 PC의 개인 메모/기록 전체는 이 폴더에 없습니다.

## 개발·패키징 도구

| 목적 | 파일 |
| --- | --- |
| 제품 portable 회귀 | [tests 프로젝트](tests/ATIVBatteryGuard.PortableTests.csproj), tests/*.cs |
| 실제 WPF GUI self-test | [WindowsSmokeTest.cs](src/ATIVBatteryGuard.App/Diagnostics/WindowsSmokeTest.cs) — 합성 자료/동작 포함 |
| SDK 없는 사용자 Windows 파일/GUI 검사 | [ValidationCheck](validation/ATIVBatteryGuard.ValidationCheck/), [package_validation_030.py](scripts/package_validation_030.py) |
| 이전 IME/추가 검사 도구 | [ExtendedCheck](validation/ATIVBatteryGuard.ExtendedCheck/), [package_extended_030.py](scripts/package_extended_030.py) — 원인 관련 때만 검토 |
| 0.3.1 개인용 빌드 묶음 | [package_personal_031.py](scripts/package_personal_031.py) — 0.3.0 기준/4파일 변경 범위와 회귀1275 이상 필요 |
| 검증된 0.3.1에 매뉴얼만 교체 | [package_031_manual.py](scripts/package_031_manual.py) — 고정 원본 ZIP과 현장 완료 근거 필요 |
| 공통 PE/권한·바이트 검사 | [package_manual_control_beta.py](scripts/package_manual_control_beta.py) |
| 패키징 개발 Python 의존성 | [packaging-requirements.txt](docs/maintenance/packaging-requirements.txt) |
| 향후 별도 서명 배포 | [RELEASE_030_SIGNING_READINESS.md](RELEASE_030_SIGNING_READINESS.md), [FINAL_030_RELEASE_PIPELINE.md](FINAL_030_RELEASE_PIPELINE.md), scripts/Test-WindowsRelease.ps1, package_final_030.py, final_release_030.py |

030/031 패키징은 당시 소스·파일·검증 근거를 고정한 도구입니다. 미래 버전을 이름만 바꿔 통과시키거나 서명된 배포로 표시하지 않습니다. 새 버전에서는 필요한 검증 근거와 도구를 함께 정합니다.

## 과거 자료와 클라우드 전용 파일

- [docs/history/README_20261126.md](docs/history/README_20261126.md), [docs/history/NEXT_DEVELOPMENT_20261126.md](docs/history/NEXT_DEVELOPMENT_20261126.md): 정리 전 긴 문서. 원래 상대 링크를 새 위치에 맞췄으며 명령은 원래 프로젝트 루트 문맥입니다.
- 프로젝트 루트의 과거 연구/실험 문서와 `src/*Trial`, `*Check`, `*Query` 프로젝트, `downloads/`의 이전 ZIP은 근거로 보존합니다. 현재 앱 유지보수를 시작하며 실행할 목록이 아닙니다.
- `/workspace/tools`, `/workspace/work`, `bin/obj`, Python/NuGet 캐시는 클라우드의 개발용 파일입니다. GitHub에 설치 결과 전체를 저장하지 않습니다. 새 환경은 [DEV_ENVIRONMENT.md](DEV_ENVIRONMENT.md)를 따라 준비합니다.
- [MAINTENANCE-NOTES ZIP](../downloads/ATIVBatteryGuard-0.3.1-MAINTENANCE-NOTES.zip)은 문서 인수인계 묶음입니다. 프로그램 전체 소스/개인 자료 백업을 대신하지 않으며, 실제 소스는 위 GitHub 브랜치에서 받습니다.
