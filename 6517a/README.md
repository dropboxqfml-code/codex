# Keithley 6517A · USB-GPIB 시험용 프로그램

Windows 10/11 64-bit용 v0.6.1 프로그램입니다. NI GPIB-USB와 6517A를 연결해 전압·시간·software current trip을 입력하고, ARM → START로 current 측정과 I(t)·R(t)·I–V·R–V 그래프 및 CSV 저장을 실행합니다. 정전압과 전압 목록을 지원하며 상위 폴더의 이미지 중복 검색 앱과 독립적으로 동작합니다.

연결 구성은 사용자가 관리하는 **저전압 시험 모드**와 기존 **검증 fixture 모드**를 선택합니다. 시작 화면은 SIMULATION·0 V이며, REAL 준비도 0 V·trip 미설정·사용자 확인 미선택에서 시작합니다. 설정 불러오기·초안 적용·연결만으로 출력 ON을 하지 않습니다.

## Windows에서 실행

[Windows ZIP 다운로드](https://github.com/dropboxqfml-code/codex/releases/download/6517a-v0.6.1/6517A-USB-GPIB-Trial-0.6.1-Windows-x64.zip)와 [SHA-256](https://github.com/dropboxqfml-code/codex/releases/download/6517a-v0.6.1/6517A-USB-GPIB-Trial-0.6.1-Windows-x64.zip.sha256)을 받습니다. 새 쓰기 가능한 폴더에 모두 풀고 `Verify-Bundle.cmd` → `Test-Simulation.cmd` → `Start-GUI.cmd`를 실행합니다. Python과 Python 의존성은 포함돼 있습니다. 호환되는 기존 NI-488.2·NI-VISA 64-bit 설치를 사용하며, 드라이버 설치 상태와 이 프로그램의 통신 결과는 구분합니다.

`Verify-Bundle.cmd`는 START → 처리 파일 수 → PASS/FAIL을 표시합니다. `Test-Simulation.cmd`도 연결·ARM·전압 단계·판독·요약·OFF·완료를 실행 중 표시하고, 끝나면 결과 폴더와 PASS/FAIL을 남깁니다. 실패한 경우 창에 표시된 단계와 종료 코드를 확인합니다.

## 메인 화면과 실행 순서

기본 화면에는 장비·주소, 시험 설정, 준비 상태, 판독값과 그래프를 표시합니다. 상단 **1 설정 → 2 연결 → 3 ARM → 4 START**에서 현재 단계와 다음 작업을 확인합니다. 세부 설정은 왼쪽 **고급**, 연결 진단·장비 기록은 오른쪽 **진단·상세 기록** 탭에 있습니다.

![v0.6.1 기본 화면: 가상 1 GΩ 측정 후 값·그래프·다음 단계](docs/images/v060-main-simulation.png)

가상 측정 화면이며 실제 장비 측정 결과가 아닙니다.

1. 왼쪽 **1. 시험 설정**에서 전압·시간·trip을 입력합니다. 누락된 필수값은 설정 창에 표시되며 해당 항목을 누르면 입력란으로 이동합니다.
2. **측정 설정 적용**으로 필수 설정을 검증하고 **2. 연결**을 누릅니다. **초안 적용**은 미완료 입력을 보존하는 별도 버튼입니다.
3. **3. ARM**으로 장비 설정·readback·오류 큐·저장 준비를 검증합니다. 이때 출력은 OFF입니다.
4. ARM이 완료되면 **4. START**로 전압 인가와 수집을 시작합니다. 전압·전류·저항과 그래프를 확인하고 필요할 때 **STOP**을 누릅니다.

ARM이 비활성화되면 준비 상태에 누락 설정 또는 장비 조건을 표시합니다. START는 ARM 완료 전에는 대기합니다. 연결 후 미완료 설정을 발견하면 출력 OFF 상태에서 **연결 종료 후 설정 수정**을 누릅니다. 연결 종료 뒤 설정 창을 열며, 수정 후 다시 연결 → ARM → START로 진행합니다.

## 1 GΩ 저전압 시험 시작

실장비 준비는 **진단·상세 기록 → NI 실장비 연결 시험 시작**에서 NI MAX와 같은 주소로 IDN·보호 OFF를 확인합니다. NI MAX test panel은 닫습니다. 이미 확인한 진단을 반복할 필요 없이 기본 화면의 장비·주소와 현재 측정 설정을 확인할 수 있습니다.

**1. 시험 설정**에서 운용 방식 **사용자 관리 저전압**을 확인하고 **1 GΩ·1 V 시험값**을 누릅니다. 요청 1 V, source 범위 100 V, 상한 10 V 이하, software trip 10 nA, 명목 기준저항 1 GΩ가 입력됩니다. 다음 세 항목은 직접 선택합니다.

- 사용자 연결 관리 확인
- 잔류 전압 확인
- Resistive-limit ON/OFF 정책

Preset은 REAL/SIM·운용 방식이나 위 확인을 자동 승인하지 않습니다. 시간·저장 폴더를 검토한 뒤 **측정 설정 적용 → 연결 → ARM → START**로 실행합니다. 결과 폴더에 `readings.csv`, `summary.csv`, `raw_io.jsonl`, `run_status.json`을 저장합니다.

1 GΩ의 명목 계산은 1 V에서 1 nA입니다. Preset의 10 nA는 검토·변경할 수 있는 software trip이며 장비의 programmable compliance가 아닙니다. 실제 판독은 기준저항의 교정값·허용차, settling·누설과 함께 비교합니다. [1 GΩ 시험](docs/reference_1gohm_trial.md)과 [사용자 시험 순서](docs/user_hardware_trial.md)에 상세 절차가 있습니다.

## 두 운용 방식

| 방식 | 실행 범위 | 연결·확인 처리 |
|---|---|---|
| `operator_low_voltage` · 사용자 관리 | **절대 10 V 이하**, source 100 V 범위 | 사용자 연결 관리 확인과 trip·resistive-limit 정책·잔류 전압 확인이 필요합니다. 정격 문서·fixture ID·과거 lid 전이 기록은 필수 입력이 아닙니다. |
| `verified_fixture` · 검증 fixture | 장비·설정·입력한 정격의 최솟값 이내 | 기존 정격·승인 기록 및 현재 연결의 OFF 상태 lid `0 → 1` 확인을 사용합니다. API 기본값과 기존 저장 설정은 이 방식입니다. |

두 방식 모두 실제 장비의 interlock 조회가 `1`이어야 하며, `0`·조회 실패·상태 오류에는 출력 ON을 차단합니다. 사용자 관리 모드가 물리적 인터록 설치를 인증한 것으로 기록되지는 않습니다. 실장비 `NATIVE_RESISTANCE`는 별도 측정 전류 보호가 없어 계속 차단하며, 실측은 `FVMI_CURRENT`로 진행합니다.

출력 OFF는 시료 방전 확인이 아닙니다. 잔류 전압은 `UNVERIFIED`로 남습니다. STOP은 단일 worker가 수행하는 software stop이며 VISA call·OS·통신 지연을 포함합니다.

## 시뮬레이션과 소스 실행

GUI의 SIMULATION 상태에서 같은 preset을 사용하면 `simulation_resistance_ohm=1e9`인 가상 모델을 사용합니다. 이 값은 실장비 transport나 실제 current 판독을 대체하지 않습니다. 기본 모델의 absorption·offset·noise가 포함되므로 명목 V/R와 차이가 있을 수 있습니다.

```bash
cd 6517a
uv sync --locked
uv run --locked python -m keithley6517a
uv run --locked python -m keithley6517a.cli simulate --config examples/simulation_1gohm_config.json --fast --progress
```

[`operator_current_template.json`](examples/operator_current_template.json)은 REAL·사용자 관리·0 V·미확인 초안입니다. GUI에서 완성한 실측 설정을 저장한 뒤 CLI에서 사용할 수도 있습니다.

```powershell
.\Run-CLI.cmd measure --config "configs\operator-current.json"
```

사용자 관리 모드의 CLI는 OPEN/CLOSED fixture 절차 대신 해당 운용 설정을 검사하고, ARM 후 실행 계획과 명시적 `START` 입력을 요구합니다. 검증 fixture 모드는 기존 OPEN → CLOSED → ARM → START 절차를 유지합니다. `--fast`는 시뮬레이션 전용입니다.

## 연결 진단과 선택 NI-only 확장

`Check-Connection.cmd`는 resource 목록 또는 선택 주소의 IDN-only 조회입니다. `Check-Output-Off.cmd`는 선택한 6517A에 보호 목적 OFF·abort를 요청하는 별도 동작입니다. 진단 결과와 원문 통신은 로컬에 저장합니다. 사용자 제공 기록에서 native NI-VISA 경로의 IDN과 보호 OFF 조회 `0`은 확인됐으며, 실제 전압 인가·current 수집 결과는 별도로 검증해야 합니다.

NI-VISA를 생략하는 `@py` 대안은 GUI를 닫고 `Enable-NI-Only.cmd`로 선택 확장을 설치한 뒤 명시적으로 선택합니다. 기본 ZIP에는 PyVISA-py·gpib-ctypes가 포함되지 않으며 NI-488.2 드라이버는 계속 필요합니다. [Windows VISA 안내](docs/windows_visa.md)를 참고하세요.

## 데이터와 검증

각 run은 `config.json`, `metadata.json`, `readings.csv`, `summary.csv`, `events.jsonl`, `raw_io.jsonl`, `run_status.json`을 저장합니다. Current와 계산 저항 `V/I`는 native 저항·역산 전류와 구분하며 raw·과도 구간을 보존합니다. 그래프는 signed-linear/symlog 표시와 부호·0을 유지하고 smoothing을 적용하지 않습니다.

```bash
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
# GUI가 없는 Linux
QT_QPA_PLATFORM=offscreen uv run --locked pytest -q
```

소프트웨어 검사, Windows 번들 실행과 실제 장비 시험의 범위는 [검증 기록](docs/validation.md)에 구분합니다. 공개 Release의 `Windows-software-tests.xml`과 `build-report.json`은 해당 CI 실행 결과입니다.

- [구현 범위와 제한](docs/known_limitations.md)
- [측정·분석 규칙](docs/measurement_protocol.md)
- [매뉴얼 명령표](docs/scpi_reference.md)
- [검증 fixture commissioning](docs/commissioning_checklist.md)
- [기존 결선 검토 문서](docs/wiring_and_safety.md)
