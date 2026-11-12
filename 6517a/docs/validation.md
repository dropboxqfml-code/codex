# 검증 기록

검증 대상은 Python 3.12 Linux 소스 개발 환경, 매뉴얼 기반 parser/명령 profile, 시뮬레이터와 주입한 모의 VISA transport입니다. 실제 6517A·USB-GPIB adapter·외부 차단/방전/전압 모니터는 개발 환경에 제공되지 않았습니다. Windows 소프트웨어 CI와 실제 장비 통신은 아래에서 구분합니다. 따라서 실장비 시험 통과나 1000 V 사용 안전성 인증을 선언하지 않습니다.

현재 설치하여 검사한 버전은 Python 3.12.14, PySide6-Essentials 6.12.0, pyqtgraph 0.14.0, PyVISA 1.16.2, numpy 2.5.4, pytest 9.2.0, pytest-qt 4.5.0, Ruff 0.17.4입니다. 재현 버전은 이 프로젝트의 `uv.lock`에 기록합니다. 이 버전 확인은 adapter driver나 VISA shared library의 설치·동작 검증이 아닙니다.

## v0.8.1 자동 시작 검사·그래프 순서·연결 이름

`Start-GUI.cmd`는 Bundle 파일 검사와 Simulation 동작 검사를 순서대로 실행한 뒤 GUI를 엽니다. 시작 창은 자식 프로세스의 진행 기록을 표시하며 실패하면 메인 화면을 열지 않습니다. Simulation 결과는 일반 측정과 별도로 `diagnostics/startup-simulation`에 저장합니다.

Native Windows와 재추출 번들 검사는 실제 QProcess로 두 시작 검사를 수행하고, 모두 통과한 뒤 메인 창이 정확히 한 번 열리는지 확인합니다. 메인 창은 SIMULATION·0 V·미연결이며 VISA 연결 생성은 차단해 검사합니다. R(t)·I(t)·I–V·R–V 순서와 실제 데이터 축도 확인합니다. 공개 build report의 `automatic_startup_checks_verified`, `graph_order_verified`가 모두 true여야 게시합니다.

시뮬레이션 선택은 장비 없이 측정·그래프·저장을 시험하는 기능으로 유지하고, 연결 항목은 `VISA · USB–GPIB`로 표시합니다. 결과 분석 기능의 변경과 v0.9.0 통합 기능은 이번 수정 범위에 포함하지 않습니다. 실행 결과는 [v0.8.1 Release](https://github.com/dropboxqfml-code/codex/releases/tag/6517a-v0.8.1)의 Windows JUnit·build report에서 확인합니다.

2026-11-12 Linux 개발 환경에서 전체 **520개**, Ruff·포맷 검사를 통과했습니다. 시작 검사 순서·실시간 진행·실패 차단·재시도·취소 및 취소 중 실행기 시작 실패를 검사했습니다. 실제 QProcess로 파일 검증과 CLI 가상 측정(52행·출력 OFF)을 실행하고 미연결 GUI·R 우선 그래프·검사 자료 분리를 확인했습니다. 파일 변조 시 GUI가 열리지 않으며, 배포 생성 중 임시 검사 자료 삭제가 실패하면 패키징도 중단합니다.

## v0.8.0 종료 분류·오프라인 결과 분석

정상 완료·사용자 STOP·장비/통신 오류를 구분합니다. 합성 1 GΩ run을 두 판독 뒤 STOP하여 `stopped`·출력 OFF·CSV/TXT 보존·미완료 단계 요약 미생성을 검사합니다. 이후 disconnect도 정상 STOP 기록을 보존하는지 확인합니다. OFF 또는 저장 실패는 오류로 남아야 합니다.

Native Windows smoke는 번들의 1 GΩ CSV를 결과 분석 창으로 열고 시간 구간을 선택합니다. 구간 행 수·전류/저항 평균·표본 표준편차·선택 TXT 수치를 CSV와 독립 비교하며 원본·기존 출력 파일의 보존과 장비 session 미생성을 검사합니다. 재추출한 번들에서도 같은 검사를 수행합니다. 공개 build report의 `saved_result_review_verified`, `user_stop_classification_verified`가 모두 true여야 게시합니다.

실행 결과는 [v0.8.0 Release](https://github.com/dropboxqfml-code/codex/releases/tag/6517a-v0.8.0)의 Windows JUnit·build report에서 확인합니다. 이 검사는 시뮬레이션·저장 파일 분석 범위이며 실제 시료의 전압 인가·전류 측정 검증과 구분합니다.

2026-11-12 Linux 개발 환경에서 전체 **497개 통과**, Ruff·포맷 검사를 통과했습니다. START 전·ARM 준비 중·취득 중 STOP과 동시 오류 우선 처리, OFF/저장 실패의 오류 분류, 파일 저장 완료 후 UI 동작, 이전 결과의 포함 경계 구간·통계·TXT를 검사했습니다. 가상 1 GΩ 20행을 취득 후 중지하고 0.5~1.5 s의 10행을 선택해 내보내는 GUI 흐름을 수동 확인했습니다. 분석 창을 닫은 뒤 메인 창과 worker가 정상 종료하는 배포 GUI 순서도 확인했습니다.

## v0.7.1 Windows GUI 완료 대기 검사

Windows에서는 가상 시계를 사용해도 CSV·TXT의 디스크 동기화에 실제 시간이 걸립니다. GUI 통합 검사는 출력 OFF와 writer 종료를 함께 확인한 뒤 최종 상태 파일을 읽도록 보완했습니다. 완료 대기는 20초로 제한하고 FAULT·HV_STATE_UNKNOWN은 즉시 실패시키며, 실패 시 상태·판독 수·로그를 남깁니다. 실제 장비의 I/O timeout이나 출력 제어 조건을 변경하지 않습니다. Windows 실행 결과는 [v0.7.1 Release](https://github.com/dropboxqfml-code/codex/releases/tag/6517a-v0.7.1)의 JUnit·build report에서 확인합니다.

## v0.7.0 분석용 텍스트 저장

기존 결과에 `analysis.txt`를 추가합니다. 첫 행에 네 개 물리량·단위를 기록하고 이후에는 탭으로 구분한 경과 시간·저항·source 설정 readback·원시 전류의 SI 수치만 저장합니다. 모든 판독 행을 보존하며 누락값은 `nan`으로 표시합니다. 이전 CSV 변환은 장비 연결 없이 수행하고 기존 파일을 덮어쓰지 않습니다.

Native Windows smoke는 기본 simulation과 1 GΩ simulation 모두에서 TXT 헤더·네 열·행 수·각 수치를 원본 CSV와 독립적으로 비교합니다. 이 검사는 재추출된 번들에서도 수행되며 `analysis_text_export_verified=true`를 확인해야 통과합니다. 구체적인 실행 결과는 [v0.7.0 Release](https://github.com/dropboxqfml-code/codex/releases/tag/6517a-v0.7.0)의 Windows JUnit·build report로 구분합니다.

2026-11-12 Linux 개발 환경의 전체 자동 테스트 **433개**, Ruff 검사와 포맷 검사를 통과했습니다. TXT 생성 실패의 ON 차단, 기록 실패의 OFF 처리, 모든 행·정밀도·부호·결측 처리, 기존 CSV 변환의 덮어쓰기 방지와 잘못된 입력 정리를 확인했습니다. 전달받은 146행 CSV도 실제 변환하여 TXT의 모든 수치가 원본과 일치함을 확인했습니다.

사용자가 전달한 후속 1 GΩ ZIP은 `simulation=true` 기록입니다. 1 V에서 146개 판독, 평균 전류 약 1.000064 nA·평균 겉보기 저항 약 0.999936 GΩ를 확인했습니다. 약 145.7 s에 사용자 STOP 후 출력 OFF가 기록됐습니다. 300 s 시험의 마지막 30 s 요약 구간 전에 중지해 `summary.csv`가 비어 있으며, 분석 TXT는 이와 관계없이 146개 판독을 내보내야 합니다. 이 첨부를 실제 VISA 전류 수집 검증으로 분류하지 않습니다.

## v0.6.2 Windows 배포 실행기

GitHub의 `windows-latest` 실행기가 할당되지 않아 소프트웨어 검사 시작 전에 서버 오류가 발생했습니다. 배포 워크플로를 지원되는 `windows-2022` 실행기로 변경했습니다. 프로그램 동작·의존성·검증 기준은 동일하며, [v0.6.2 Release](https://github.com/dropboxqfml-code/codex/releases/tag/6517a-v0.6.2)의 Windows JUnit·build report에서 실제 실행 결과를 확인합니다.

## v0.6.1 배포 이미지 포함 검사

기본 화면 미리보기 이미지가 portable source allowlist에서 빠지는 항목을 수정했습니다. 실제 배포용 파일을 복사한 뒤 README가 참조하는 이미지의 존재와 원본 일치를 검사합니다. 2026-11-12 Linux 개발 환경에서 전체 **411개 통과**, Ruff·포맷 검사를 통과했습니다. Windows 결과는 [v0.6.1 Release](https://github.com/dropboxqfml-code/codex/releases/tag/6517a-v0.6.1)의 `Windows-software-tests.xml`·`build-report.json`에서 별도로 확인합니다. 프로그램 동작은 아래 v0.6.0 변경을 포함합니다.

## v0.6.0 진행 표시·준비 상태·화면 정리

`Test-Simulation.cmd`는 START와 사전검사, 연결·ARM·START·전압 단계·판독·요약·OFF·완료 및 최종 PASS/FAIL·종료 코드를 표시합니다. CLI의 `simulate --progress`는 stderr를 즉시 flush하고 stdout의 최종 JSON 형식을 유지합니다.

설정 창은 필수 입력을 검사하는 **측정 설정 적용**과 미완료 입력을 보존하는 **초안 적용**을 구분합니다. 누락 항목을 모아 보여 주며 항목에서 입력란으로 이동합니다. 메인 화면은 설정 누락, 연결 대기, ARM 대기, START 가능, 측정 완료를 구분하고 출력 OFF에서 연결 종료 후 설정 수정으로 돌아갑니다. 기본 화면은 설정 요약·판독·그래프 중심이며 고급 설정과 진단·로그는 별도 탭에 둡니다.

| 검증 대상 | 확인할 동작 |
|---|---|
| Simulation 진행 | 최종 JSON 전 단계 출력, 실패 종료 코드, CMD의 사전 안내·최종 결과 |
| 설정 준비 | 운용 방식별 모든 누락 항목, ready/draft 구분, 누락 입력 이동 |
| 메인 흐름 | ARM·START 비활성 사유와 단계 안내, 연결 OFF에서 수정 후 재연결 |
| 보호 회귀 | 확인 자동 승인 없음, 설정·연결·ARM에서 ON 없음, 기존 한도·실제 장비 조건 유지 |
| 배포 | Windows 전체 검사·번들 CLI/GUI·추출 후 무결성 및 가상 1 GΩ 실행 |

v0.6.0 실행 결과는 [해당 Release](https://github.com/dropboxqfml-code/codex/releases/tag/6517a-v0.6.0)의 `Windows-software-tests.xml`·`build-report.json`과 함께 기록합니다. 이 문서의 이전 버전 시험 수는 해당 버전의 역사 기록입니다. 화면 안내 변경으로 실제 6517A의 전압 인가·current 수집을 검증한 것으로 간주하지 않습니다.

2026-11-12 Linux 개발 환경에서 전체 **410개 통과**, Ruff 검사와 포맷 검사를 통과했습니다. 연결된 실제 설정의 누락 목록, SIM 초안의 ARM 차단, 연결 후 별도 ARM과 START, OFF에서 연결 종료 후 설정 수정, 중단 이유와 마지막 판독값 표시를 회귀 검사했습니다. 화면은 1280×820에서 가상 1 GΩ 실행과 준비 미완료 상태를 확인했습니다. Windows 검증 결과는 배포 CI 보고서에서 별도로 확인합니다.

## v0.5.0 사용자 관리 저전압 측정 흐름

이번 버전은 사용자 관리 저전압 경로(`operator_low_voltage`)와 기존 검증 fixture 경로(`verified_fixture`)를 구분합니다. 사용자 관리 경로는 source 100 V 범위·절대 10 V 이하이며, 연결·정격·외부 보호는 사용자가 관리한다는 명시적 확인을 사용합니다. 정격 문서·fixture ID·과거 lid 전이 이력은 필수 입력이 아닙니다. 실제 장비의 interlock `1`, OFF·current limit·zero check·readback·오류 상태와 별도 ARM/START는 검사합니다. 물리적 설치 확인 필드를 사용자 확인만으로 true로 만들지 않습니다. 기존 fixture 경로의 정격·승인·현재 연결 `0 → 1` 관찰 조건은 유지합니다.

설정창은 문법·수치가 유효한 미완성 초안을 적용할 수 있고 ARM 준비 여부를 따로 표시합니다. 명시적 1 GΩ·1 V preset은 1 V·10 nA trip·명목 1 GΩ·가상 모델 1 GΩ를 입력하지만 REAL/SIM·운용 방식·확인 체크·resistive-limit 정책을 바꾸지 않습니다. 초기 SIM 및 REAL 준비는 0 V로 시작합니다. `simulation_resistance_ohm`은 가상 transport만 사용하며 실제 VISA current를 대신하지 않습니다.

| 검증 대상 | 확인할 동작 |
|---|---|
| 사용자 관리 설정 | 10 V·100 V-range 경계, 명시적 확인·trip·정책, 초안과 ARM 검증 구분 |
| 장비 실행 | interlock `0`·오류·상태 불일치 시 ON 차단, 설정·START snapshot·일회 권한 유지 |
| 기존 fixture 회귀 | 기존 정격·승인 및 현재 연결 lid 전이 경로 유지 |
| GUI | preset·예상 current, 초안 적용만으로 연결·ON 없음, 운용 방식 표시와 기록 |
| 가상 1 GΩ | 실제 transport와 구분된 모델, current·V/I·CSV 결과 |
| Windows 배포 | 전체 검사·번들 CLI/GUI·선택 installer·추출/캐시/변조 회귀 및 게시 게이트 |

다음은 v0.5.0 최종 로컬 실행 기록입니다. 이 기록 시점의 새 Windows CI는 실행 전이며, 이후 실제 Windows 결과는 해당 Release의 `Windows-software-tests.xml`·`build-report.json`에서 확인합니다.

| 항목 | v0.5.0 로컬 결과 |
|---|---|
| 전체 자동 테스트 | Linux offscreen **371개 통과**, 8.27 s |
| Ruff check / format | 통과; Python 파일 59개 |
| 설치 metadata | locked sync로 v0.5.0 적용 확인 |
| 1 GΩ simulation CLI | 실제 실행: reading 11개·summary 1개, completed / OFF / residual UNVERIFIED; 가상 모델 1e9 Ω 기록 확인 |
| GUI 전체 실행 흐름 | 모의 VISA 버스를 주입한 preset → 연결 → ARM → START → CSV·OFF 경로를 전체 시험에 포함 |
| 실제 장비 current 측정 | 미수행; 사용자 제공 기록은 아래 v0.4.6 IDN·보호 OFF 관찰 범위 |

모의 VISA를 사용하는 실측 소프트웨어 경로와 시뮬레이션은 실제 장비 전압 인가 성공을 뜻하지 않습니다. 새 사용자 관리 모드의 실제 current 결과는 아직 제공되지 않았습니다.

## v0.4.6 GitHub Release의 Windows 실행 증거

[CI 실행 43151775381](https://github.com/dropboxqfml-code/codex/actions/runs/43151775381)의 Windows 검사와 게시가 성공했습니다. 공개 [Windows-software-tests.xml](https://github.com/dropboxqfml-code/codex/releases/download/6517a-v0.4.6/Windows-software-tests.xml)은 320개 시험, 실패·오류·건너뜀 0개를 기록했습니다. 공개 build report는 `native_windows_execution_verified=true`, `relocated_windows_execution_verified=true`, `hardware_verified=false`입니다.

한글·공백이 있는 새 경로의 번들 CLI/GUI 실행, 캐시 46개 생성 후 무결성 PASS, 소스·DLL 변조 FAIL, 복원 후 PASS와 manifest 불변을 확인했습니다. 아래 v0.4.6 로컬 제작 시점의 Windows 실행 전 표시는 이 추가 CI 이전 기록으로 보존합니다.

## v0.4.6 사용자 PC 후속 진단과 1 GΩ 시험 준비

사용자가 제공한 후속 기록에서 파일 무결성 6,885개가 모두 통과하고 오류가 없음을 확인했습니다. Discovery와 실제 6517A IDN 진단도 성공했습니다. 보호 OFF 진단은 `:OUTP1?`를 두 번 조회해 모두 `0`을 받았으며 최종 `output_state=OFF`, `output_OFF_confirmed=true`, 이슈 없음으로 기록됐습니다. 출력 ON·측정 시작 명령은 없었습니다. 여러 OFF/abort 명령은 연결 시와 종료 정리 시의 보호 절차이며 통신 실패 재시도를 뜻하지 않습니다.

이 기록에는 장비 오류 큐 조회, 인터록 전이, 실제 전류 판독·전압 인가, 잔류 전압 확인이 없습니다. 방전은 UNVERIFIED입니다. 아래 이전 배포 시점의 OFF 미확인 기록과 구분합니다.

다음 대상은 사용자가 지정한 1 GΩ 기준저항입니다. [`reference_1gohm_draft.json`](../examples/reference_1gohm_draft.json)에 확인된 통신 설정과 명목 저항만 반영하고, 미정인 전압·정격·trip·fixture 승인은 비워 둡니다. 설정을 읽을 수 있으나 ARM은 거부되어야 하는 0 V 준비 초안입니다. [시험 준비 문서](reference_1gohm_trial.md)에 계산값과 이후 GUI 단계를 기록합니다. 실제 측정 조건은 아직 미확정입니다.

## v0.4.6 소스 기반 캐시 배포 오류 수정

사용자 제공 v0.4.5 검사 보고서는 7,271개 파일 통과와 368개 해시 불일치를 기록했으며, 실패는 모두 소스 기반 `__pycache__/*.pyc`였습니다. 공개 원본 ZIP의 manifest 7,639개 중 캐시 754개는 원본에서는 해시가 맞지만, native smoke가 만든 캐시를 배포한 탓에 추출·실행 후 재생성되면 내용이 바뀔 수 있었습니다. ZIP의 소스 수정 시각 정밀도 차이와 동일 소스 import에 따른 캐시 해시 변화를 별도 임시 폴더에서 재현했습니다.

해당 파생 캐시를 manifest와 ZIP에서 제외하고 실행 진입점·선택 설치 하위 프로세스에 `-B`를 적용했습니다. 소스·확장 모듈·DLL·표준 라이브러리 ZIP·소스 없는 bytecode의 검증은 유지합니다. 검증기가 기존 해시 불일치를 무시하도록 바꾸지는 않았습니다. Windows 배포 게이트는 새 위치에 실제 ZIP 추출, CLI/GUI 실행, 캐시 생성 후 PASS, 소스·DLL 변조 FAIL, 복원 후 PASS와 manifest 불변을 확인하도록 추가했습니다. 그 결과는 `build-report.json`의 `relocated_windows_execution_verified`와 `relocation_check`에 기록됩니다.

사용자 제공 IDN-only 원문에는 실제 VISA 경로의 `*IDN?` 송신과 6517A 응답이 있으며 `simulation=false`, `ok=true`, 이슈 없음이 확인됩니다. 이 사용자 PC에서 native NI-VISA 경로의 장비 식별은 성공했습니다. 출력 상태는 UNKNOWN, OFF 확인은 false, 측정 시작과 출력 ON 명령은 false, 잔류 전압은 UNVERIFIED이므로 전체 측정·차단·방전 검증으로 확대하지 않습니다. 아래 과거 IDN 미수행 표시는 당시 배포 기록입니다.

| 항목 | v0.4.6 로컬 검증 |
|---|---|
| 전체 테스트 | Linux offscreen 320개 통과, 실패·건너뜀 없음, 6.90 s |
| Ruff check / format | 통과; Python 파일 55개 |
| 배포 회귀 | 전체 44개; 실제 캐시 생성→ZIP 추출→다른 위치 import→재검사 PASS, 소스·확장 모듈·stdlib ZIP 변조 FAIL, 독립 bytecode 계속 검증 포함 |
| Windows 실행·이동 후 검사 | 이 로컬 기록 시점에는 새 CI 전; 해당 Release의 JUnit 및 build report로 확인 |
| 실제 장비 근거 | 사용자 제공 v0.4.5 native IDN-only 성공; 출력 OFF·측정·방전은 미확인 |

## v0.4.5 파일 검사 진행·결과 표시

사용자는 `Verify-Bundle.cmd` 실행 후 화면 변화를 보지 못했고, GUI에서는 NI MAX와 동일한 GPIB 주소를 가져왔다고 보고했습니다. IDN 확인은 아직 누르지 않았다고 확인했으므로 장비 식별·통신 성공으로 기록하지 않습니다. 기존 검사기는 전체 파일 해시가 끝난 뒤에만 출력하는 구조였지만, 이것이 사용자 PC에서 나타난 현상의 확정 원인인지는 알 수 없습니다.

CMD에 Python 실행 전 START와 누락 파일 안내, 처리 파일 수, PASS/FAIL·종료 코드 표시를 추가했습니다. `--save-report`로 요청한 경우에만 `diagnostics/bundle-verification-*.json`을 저장합니다. 보고서 저장 실패는 WARN과 `report_saved=false`로 드러내고 파일 무결성 결과와 구분합니다. Builder는 저장 옵션을 사용하지 않으며 native Windows 빌드에서는 번들 Python으로 검사기를 실행합니다.

| 항목 | v0.4.5 로컬 검증 |
|---|---|
| 전체 테스트 | Linux offscreen 318개 통과, 실패·건너뜀 없음, 6.67 s |
| Ruff check / format | 통과; Python 파일 54개 |
| 파일 검사 회귀 | 배포 코드 전체 42개; 첫 해시 전 진행 표시, 정상·누락·변조·manifest 오류, 보고서 저장 실패, builder 호출 시 보고서 미생성 포함 |
| Windows 실행 | 이 로컬 기록 시점에는 새 CI 실행 전; 해당 Release의 CI·JUnit·build report로 구분 |
| 실제 6517A IDN·측정 | 미수행; 사용자의 주소 조회 보고와 구분 |

## v0.4.4 연결 안내와 NI-488.2-only 선택 경로

사용자는 안내된 CMD 실행 뒤 v0.3.0 시뮬레이션 화면이 열렸으며 NI MAX에서 6517A가 보인다고 확인했습니다. 이는 사용자 관찰 기록입니다. 실제 프로그램의 IDN/출력 OFF/전류 판독 결과 파일은 아직 전달되지 않았으므로 측정 성공으로 표시하지 않습니다.

이번 변경은 정상 기본 SIMULATION 화면에서 실제 NI 연결 시험으로 넘어가는 단계 안내와, NI-VISA를 생략하기 위한 명시적 `@py` 대안을 추가합니다. 기본 native VISA를 유지하며 backend 오류 뒤 자동 재접속·명령 재전송은 하지 않습니다. PyVISA-py 0.8.1/gpib-ctypes 0.3.0의 선택 설치와 NI-488.2 driver/DLL의 준비 상태를 구분합니다. 기본 ZIP에는 이 두 대체 패키지를 사전 설치하지 않습니다.

기본 환경에서 선택 extra를 제거한 뒤 다음 검증을 실행했습니다. 308개 통과·6.94 s는 CI 환경 수정 전의 동일 기능 소스에 대한 Linux 로컬 검증 기록입니다. 이어 소스 버전을 v0.4.1로 수정한 뒤 전체 검증을 다시 실행하고 설치 metadata의 잠금 동기화도 확인했습니다. 아래 v0.4.1 결과는 로컬 재검증의 역사 기록으로 보존합니다. 이번 v0.4.4 배포는 Windows 전체 자동 테스트와 번들 Windows CLI/GUI·선택 확장 설치 smoke를 직접 게이트로 사용합니다. Linux CI의 시스템 패키지 설치가 Windows 검증을 막지 않도록 분리했으며, 로컬 Linux 전체 검증 기록은 보존합니다. 실제 Windows 결과는 해당 CI 로그와 `build-report.json`에서 확인합니다.

이전 v0.4.2의 CI Qt bootstrap은 실제 offscreen `PlotWidget` 렌더 프로브를 먼저 실행하고, 그 프로브가 실패할 때만 APT fallback을 수행합니다. 별도의 `libOpenGL` CDLL 로드 성공을 실제 GUI 실행의 필수 사전조건으로 사용하지 않습니다. 이는 CI 준비 단계의 판정 수정이며 실제 장비 시험의 성공을 뜻하지 않습니다.

| 항목 | v0.4.4 및 동일 기능 소스의 로컬 검증 기록 |
|---|---|
| v0.4.4 실제 전체 검증 | Linux offscreen에서 309개 통과, 실패·건너뜀 없음, 6.65 s; 별칭 경로 회귀 포함 |
| v0.4.4 metadata·형식 검사 | locked offline sync로 metadata v0.4.4 적용; Ruff check/format 54개 파일 통과 |
| v0.4.3 배포 코드·설치 metadata | 배포 코드 32개 통과, 0.16 s; locked offline sync로 metadata v0.4.3 적용; Ruff check/format 54개 파일 통과 |
| v0.4.2 배포 코드 재검증 | 32개 통과, 0.21 s; 전체 308개는 아래 v0.4.1 기록과 새 CI 결과로 구분 |
| v0.4.2 준비 절차 | locked offline sync로 설치 metadata v0.4.2 적용, Ruff check/format 54개 파일 통과, Bash/YAML 검사 통과 |
| v0.4.2 실제 Qt 프로브 | offscreen PlotWidget 생성·그래프 표시·이미지 캡처 통과; 이 실행에서 APT 미사용 |
| v0.4.1 실제 전체 재검증 | Linux offscreen에서 **308개 통과**, 실패·건너뜀 없음, 7.81 s |
| 동일 기능 소스의 이전 전체 검증 | Linux offscreen에서 **308개 통과**, 실패·건너뜀 없음, 6.94 s |
| v0.4.1 Ruff check / format | 실제 재실행 통과; Python 파일 54개 format 검사 통과 |
| v0.4.1 설치 metadata 적용 | 캐시된 개발 환경에서 `uv sync --locked --offline` 성공; 설치 metadata v0.4.1 적용 |
| Linux Qt bootstrap 로컬 점검 | 필수 library 누락 목록 `[]`; offscreen QWidget startup 통과 |
| Release workflow 정적 점검 | Bash `bash -n` 및 YAML 구조 검사 통과; 원격 CI 성공을 뜻하지 않음 |
| v0.4.1 Windows CI | 이 로컬 기록 시점에는 실행 전·대기 중 |
| 주요 경계 시험 | NI backend 29개, 연결 안내 16개, 새 실장비 준비 통합 10개, 배포 코드 33개; 기존 시험과 함께 전체 실행 |
| 기본 환경과 선택 확장 분리 | `uv sync --locked` 기본 환경에서 전체 시험 통과; PyVISA-py/gpib-ctypes가 사전 설치돼 있어야 통과하는 구성으로 시험하지 않음 |
| simulation CLI | v0.4.0 동일 기능 소스에서 실제 실행: reading 52개·summary 5개, completed / OFF / residual UNVERIFIED |
| offscreen GUI | v0.4.0 동일 기능 소스/FakeClock로 52개 판독 완료, OUTPUT_OFF_CONFIRMED / OFF / residual UNVERIFIED; 미연결 REAL 준비 0 V·trip 미설정과 새 연결 안내 화면 시각 확인 |
| 선택 확장 미설치 `@py` 진단 | 실제 기본 환경에서 `NI_BACKEND_DEPENDENCY_MISSING` 기록·보고서 저장; output UNKNOWN, 장비 I/O 없음 |
| 기본 portable rehearsal | v0.4.0 동일 기능 소스의 ZIP 116,633,738 bytes; static 파일 6,884개 내부 SHA-256과 ZIP CRC 통과; 선택 확장 Python 파일 미포함, installer·hash-pinned 요구사항 포함 |
| 실제 NI-488.2-only 통신·사용자 PC의 IDN/측정 | 미수행 |
| 물리적 차단·방전·잔류 전압 확인 | 미수행; UNVERIFIED |

SIM→REAL 준비는 가상 전압·trip·승인을 재사용하지 않고 0 V·trip 미설정·미승인 상태를 만듭니다. 이미 연결된 SIM session은 먼저 종료하며, 실장비 준비 버튼만으로 I/O나 출력 ON을 수행하지 않습니다. 모의/실제 transport 진단과 현재 연결의 승인을 구분하고 과거 OFF 진단으로 ARM 조건을 충족하지 않는지 검사했습니다.

새 화면 예시는 [미연결 실장비 준비 안내](../examples/live-connection-guide.png)와 [시뮬레이션 완료 화면](../examples/gui-simulation.png)입니다. 실장비 준비 그림의 주소는 예시이며 실제 NI 응답을 취득한 화면이 아닙니다.

선택 확장 installer는 사용자의 명시적 `INSTALL` 입력 후 두 개의 hash-pinned pure wheel을 인터넷에서 설치합니다. 기본 배포 ZIP에는 이 대체 Python 패키지나 NI driver/DLL을 넣지 않습니다. 완전한 표식·버전·해시가 맞는 기존 설치 재사용, 불완전하거나 변경된 폴더 보존·덮어쓰기 거부도 검사합니다. 이 소프트웨어 시험은 실제 NI DLL/어댑터 동작이나 확장 추가 배포본의 재배포 조건 검토를 대신하지 않습니다.

## v0.4.1 CI 진행 기록

[CI 실행 43041312629](https://github.com/dropboxqfml-code/codex/actions/runs/43041312629)은 이 변경을 결정한 시점에 Qt APT 설치 단계가 지연 중이었습니다. 완료 결과를 확인하지 않았으므로 실패로 단정하지 않습니다. v0.4.2에서는 실제 PlotWidget 렌더 프로브를 우선하는 수정으로 별도 CI를 진행하며, 이 기록 시점의 Windows v0.4.2 시험은 아직 실행 전입니다.

## Windows 경로 별칭 수정

[Windows v0.4.3 CI](https://github.com/dropboxqfml-code/codex/actions/runs/43044513737)와 [진단 실행](https://github.com/dropboxqfml-code/codex/actions/runs/43045737403)에서 선택 확장 설치 smoke의 경로 비교가 실패했습니다. 설치가 반환한 정규 경로와 Windows TEMP의 짧은 별칭 경로가 같은 폴더여도 문자열 비교에서 달라질 수 있었습니다. 임시 루트를 먼저 정규화해 manifest·파일 해시 검증을 유지하고, 별칭 경로 회귀 시험을 추가했습니다. 이 실패 실행에서는 native 번들 검사와 게시가 수행되지 않았습니다. v0.4.4의 실제 Windows 결과는 새 CI와 Release 보고서에서 확인합니다.

## v0.4.0 CI 중단 기록

[CI 실행 43039479711](https://github.com/dropboxqfml-code/codex/actions/runs/43039479711)은 Linux OS 패키지 설치 단계에서 exit 100으로 중단됐습니다. 코드 검사나 자동 테스트가 실패한 결과가 아니며, 해당 실행에서는 코드 검사·Windows 시험·배포가 실행되지 않았습니다. 기존 tag는 변경하지 않고 CI 환경을 수정한 v0.4.1로 다시 배포를 시도했습니다.

## v0.3.0 GitHub Release의 추가 Windows 검증

이전 로컬 검증 뒤 GitHub Release 작업에서 Windows 실행 검증을 수행했습니다. [CI 실행 43031877419](https://github.com/dropboxqfml-code/codex/actions/runs/43031877419)의 Linux·Windows 검사와 배포가 성공했으며, 공개 Release의 [Windows-software-tests.xml](https://github.com/dropboxqfml-code/codex/releases/download/6517a-v0.3.0/Windows-software-tests.xml)에는 **236개 통과, 실패·오류·건너뜀 0개**가 기록됐습니다. 번들 Windows 인터프리터의 synthetic CLI/GUI smoke도 통과했습니다.

이는 v0.3.0 Windows 소프트웨어 실행의 증거이며 실제 6517A·NI GPIB-USB 통신 검증이 아닙니다. 해당 Release의 `build-report.json`은 `native_windows_execution_verified=true`, `hardware_verified=false`로 구분됩니다. 아래 v0.3.0 표의 Windows 미수행 표시는 이 추가 CI 실행 전 로컬 제작 시점의 역사 기록입니다.

## v0.3.0 이전 로컬 사용자 시험 배포 검증

이번 변경은 Windows 사용자용 portable 시험 ZIP, 출력 변경 없는 VISA 진단, 명시적 OFF 점검, JSON 편집 없이 시험 설정을 준비하는 폼과 사용자 시험 절차를 추가합니다. Native Windows와 실제 6517A·USB-GPIB는 제공되지 않았습니다.

| 항목 | 현재 결과 |
|---|---|
| v0.3.0 전체 자동 테스트 | Linux offscreen에서 **236개 통과**, 실패/건너뜀 없음, 6.29 s |
| Ruff check / format | 프로젝트 전체 Ruff check 통과; Python 파일 48개 format 검사 통과 |
| Linux offscreen GUI·시험 설정 폼·모의 VISA 진단 | 전체 시험 포함: 진단 25개·설정 폼 12개·trial 통합 8개·배포 코드 15개·기존 176개 통과 |
| v0.3.0 simulation CLI | 실제 실행: reading 52개·summary 5개, completed / OFF / residual UNVERIFIED |
| v0.3.0 offscreen GUI | 실제 simulator/FakeClock로 52개 판독 완료, OFF / residual UNVERIFIED; GUI·시험 설정 화면 확인 |
| NI-VISA 미설치 진단 | 현재 개발 환경에서 `VISA_BACKEND_UNAVAILABLE`를 구분해 JSON/raw I/O 저장; 연결 성공으로 표시하지 않음 |
| Windows x64 runtime/wheels·ZIP 구성·무결성 | Rehearsal 배포본의 내부 SHA-256 manifest와 ZIP CRC 검사 통과; 공식 runtime 및 hash-locked Windows wheels 사용 |
| Native Windows GUI/DLL/VISA 실행 | 미수행 |
| 실제 6517A·USB-GPIB·fixture 측정 | 미수행 |
| 실제 hardware 차단·방전·잔류 전압 확인 | 미수행; UNVERIFIED |

배포 rehearsal에서는 static 파일 6,878개의 내부 해시와 ZIP CRC를 검증했습니다. PE audit는 application/runtime 바이너리 326개의 x64 구성을 확인했고, upstream pip의 사용하지 않는 distlib installer template 4개(32-bit/ARM)는 별도 목록으로 구분했습니다. 이 파일 구성 검사는 Windows에서 DLL을 실제 로드한 검사가 아닙니다. 최종 ZIP의 외부 SHA-256은 배포 checksum 파일에 별도 기록하며 문서에 자기 참조 hash를 넣지 않습니다.

Portable ZIP에는 Python 3.12.14 runtime과 잠금 버전 Windows wheel이 포함됩니다. 공식 runtime 다운로드 검증·wheel 해시·Windows tag·배포 manifest 검사와 실제 Windows 실행 검증은 서로 구분합니다. 모의 transport에서 `simulation=false` 설정으로 real 경로를 시험하더라도 실제 하드웨어 시험이라고 표시하지 않습니다.

현재 화면 예시는 [`gui-simulation.png`](../examples/gui-simulation.png)와 [`trial-setup.png`](../examples/trial-setup.png)입니다. 실제 장비가 아닌 offscreen GUI 화면으로 확인했습니다. 시험 설정 폼 적용만으로 연결/ARM/START가 실행되지 않는지와 기존 승인 파일에 독립 하드웨어 보호 검토를 자동 부여하지 않는지도 검사했습니다.

진단의 IDN-only 성공과 OFF 확인은 관찰 결과입니다. `hardware_verified=false`를 유지하며 실제 측정·인터록·독립 차단·방전의 종합 검증으로 확대하지 않습니다. 사용자 PC의 첫 실제 결과는 [시험 기록 양식](user_hardware_trial.md)에 남깁니다.

## 이전 v0.2.0 검증 기록

2026-11-11에 다음 명령과 기능 검증을 실행했습니다. 시험 수가 0이거나 실행하지 않은 명령을 통과로 세지 않습니다.

| 항목 | 결과 |
|---|---|
| 예제 JSON load·simulation ARM 설정 검증 | 통과: simulation 예제 validate, real template load만 수행 |
| 자동 테스트 | `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`: v0.2.0: **176개 통과**, 실패/건너뜀 없음, 5.84 s |
| Ruff check / format | 프로젝트 전체 통과; Python 파일 37개 format 검사 통과 |
| CLI simulation run | `simulate --config examples/simulation_config.json --fast --output examples/manual_verified_simulation` 통과: v0.2.0 reading 52개, summary 5개, completed / OFF / residual UNVERIFIED |
| CLI 300 s constant bias | `constant_bias_config.json --fast` 통과: v0.2.0 reading 300개, summary 1개, completed / OFF / residual UNVERIFIED |
| CLI native resistance | `native_resistance_config.json --fast` 통과: v0.2.0 reading 31개, summary 3개; measured current 전체 비움·native/inferred 전체 분리 확인 |
| Offscreen GUI | `tests/test_ui.py` 7개 통과(실제 runner 및 commissioning GUI 포함); v0.2.0 FakeClock 시뮬레이터 GUI 52개 reading 완료 및 화면 확인 |
| 실제 6517A·USB-GPIB | 미수행; 원문 기반 current 경로는 승인 guard를 갖추었으나 실제 출력/통신 검증 아님 |
| Windows native 동작·실행 파일 | 미수행 |
| 독립 잔류 전압·방전 확인 | 미수행; UNVERIFIED |
| 기존 이미지 검색 앱 회귀 | 57개 통과, 1개 건너뜀 |
| Wheel package build | v0.2.0 wheel 생성 통과; `/tmp/6517a-dist`에 개발용 wheel 생성. Windows 실행 파일 검증과 별개 |

이전 웹 요청의 HTTP 403은 사용자가 제공한 PDF 첨부로 해결됐습니다. 첨부 원문 `6517A-900-01 Rev. D, May 2003`(343 pages, SHA-256 `3c02f1e97a0fd101cbc77a09aae87b1d0ce43e45b9bc46d433e671e8dea78adb`)에서 사용하는 명령·trigger·Figure 3-19 형식과 status/sentinel을 대조했습니다. 원문 확인, 원문에서 구성한 합성 fixture, 모의 transport 시험, 실제 장비 시험은 서로 구분합니다. 실제 수집 transcript는 제공되지 않았으며 모든 예제의 metadata/raw transcript에서 simulation 여부를 확인하세요.

GUI 검증은 시작·설정 load 시 미연결/ON 없음, 단일 worker의 I/O 소유, close 요청 시 STOP 우선, 음수·0을 보존하는 signed-log, 기존 timestamp를 유지하는 stale 표시를 포함합니다. 화면 예시는 [`examples/gui-simulation.png`](../examples/gui-simulation.png)이며 실제 장비가 아닌 simulator run입니다.

이전 원문 기반 리스트 sweep 예제는 소스 저장소의 `examples/manual_verified_simulation/20261111T060755_62af542b8ab84ffe87f976a5378bbf5f`에 있습니다. 이 역사 데이터 폴더는 portable ZIP에 포함하지 않으며 현재 버전의 가상 결과는 `Test-Simulation.cmd`로 생성합니다. v0.2.0 reading 52개, summary 5개, summary 유효 reading 25개이며 종료는 completed / OFF / residual UNVERIFIED입니다. Metadata의 `manual_verified=true`는 원문 대조를 뜻하며 `hardware_verified=false`, `simulation=true`와 구분됩니다. `config.json`의 version·commit·dirty·소스 fingerprint를 함께 확인하세요. 모든 raw reading의 `rdg#` suffix가 반영됐으며 실제 장비 수집 데이터가 아닙니다.

소스 저장소의 `examples/sample_simulation/20261111T054332_a1f76da2b46946488b1388ee185de711`은 **v0.1.0 역사 자료**로 유지합니다. 그 당시의 provisional `RDNG#` grammar와 원문 미확인 metadata를 포함하므로 현재 parser/명령 형식의 검증 자료로 재사용하지 않습니다.

매뉴얼 반영 후에는 layer 1의 존재하지 않는 delay 경로 제거, source root 경로 대조, function별 NPLC·filter·reference 설정, `rdg#` suffix·standby VSO·sentinel 처리, 현재 연결에 묶인 출력 OFF `0` → `1` commissioning과 one-use START 승인, CLI의 명시적 `OPEN`·`CLOSED`·`START` 의도 확인을 소프트웨어에서 검사합니다. Native resistance 실제 출력은 별도 측정 전류 보호가 검증되지 않아 계속 차단합니다.
