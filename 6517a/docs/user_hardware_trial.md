# 6517A · NI GPIB-USB 사용자 시험 순서

v0.8.2는 연결·정격을 사용자가 관리하는 저전압 시험과 기존 검증 fixture 방식을 제공합니다. 사용자 제공 기록에서 파일 무결성·실제 IDN·보호 OFF 조회 `0`은 확인됐습니다. 전압 인가·current 수집·인터록 차단·방전은 그 진단과 별도 시험입니다.

## 1. 패키지 실행

1. GitHub Release에서 `6517A-USB-GPIB-Trial-0.8.2-Windows-x64.zip`과 checksum을 받습니다. 새 쓰기 가능한 폴더에 전체를 풉니다.
2. **`Start-GUI.cmd` 하나만 실행**합니다. 시작 창이 Bundle 파일 검사 → Simulation 동작 검사 → GUI를 자동으로 진행합니다. 진행 기록을 확인할 수 있고, 실패하면 해당 단계와 기록을 확인해 재시도합니다.
3. 두 검사를 통과하면 메인 화면이 열립니다. 초기 시뮬레이션·0 V·미연결 상태가 정상이며, 기본 그래프는 R(t)입니다. 자동 가상 결과는 `diagnostics/startup-simulation`에 저장합니다. `Verify-Bundle.cmd`와 `Test-Simulation.cmd`는 개별 점검용입니다.

Python과 Python 의존성은 포함됩니다. v0.4.6부터 소스가 있는 파생 bytecode는 패키지와 고정 manifest에서 제외하며, 소스·DLL·확장 모듈·stdlib ZIP·독립 bytecode는 계속 해시 검사합니다. 배포 검사는 실제 Windows에서 새 위치에 추출한 ZIP의 실행과 캐시 생성 후 재검사를 포함합니다.

## 2. NI 연결 확인

NI MAX와 동일한 board·주소를 선택하고 NI MAX test panel과 다른 제어 프로그램을 닫습니다. 이미 호환 NI-488.2·NI-VISA 64-bit 설치가 동작하면 기존 설치를 사용합니다. 예시 resource는 `GPIB0::27::INSTR`이며 실제 보유 장비의 주소를 선택합니다.

시뮬레이션 (가상 시험)은 장비 없이 측정 흐름·그래프·저장을 확인할 때 사용합니다. 6517A를 사용하려면 장비 선택에서 **VISA · USB–GPIB**를 선택합니다. GUI의 **진단·상세 기록** 탭에서 SIM 연결을 종료한 뒤 ‘NI 실장비 연결 시험 시작’을 선택합니다. REAL 준비는 0 V·trip 미설정·사용자 확인 미선택 상태로 시작합니다. 목록 조회 → 주소 선택 → IDN → 보호 OFF 순서로 진단합니다. IDN 조회는 출력 변경을 하지 않습니다. 보호 OFF는 식별된 장비에 OFF·abort를 요청하며 진단 종료 시 session을 닫습니다. 이후 측정 연결은 별도로 수행합니다.

Portable의 직접 진단 명령은 다음과 같습니다.

```powershell
.\Check-Connection.cmd "GPIB0::27::INSTR" "@ivi"
.\Check-Output-Off.cmd "GPIB0::27::INSTR" "@ivi"
```

NI-VISA를 생략하는 `@py` 시험 기능은 `Enable-NI-Only.cmd`로 선택 확장을 명시적으로 설치한 뒤 재시작해 선택합니다. NI-488.2 driver와 호환 DLL은 계속 필요합니다. 자세한 조건은 [VISA 안내](windows_visa.md)에 있습니다.

## 3. 사용자 관리 저전압 설정

실제 시료를 사용할 때 시료 ID 아래에 길이 L·폭 W·두께 D를 mm로 입력하고 전류 방향을 선택합니다. 치수와 전류 방향은 독립적이며, 세 치수와 방향이 모두 있어야 비저항을 계산합니다. 일부 입력만으로도 저항 측정과 치수 저장을 할 수 있습니다.

직육면체 전체 단면을 전극이 덮는 모델에서 `ρ=R×A/ℓ`입니다. D 방향이면 `A=L×W, ℓ=D`이고 mm²·mm를 m²·m로 환산해 Ω·m로 저장합니다. 예를 들어 20×10×2 mm 시료를 D 방향으로 측정한 1 GΩ는 1×10⁸ Ω·m입니다. 실제 전극 접촉 면적이 더 작으면 해당 유효 면적을 사용해야 합니다. 입력 치수는 전극 접촉이나 측정 조건을 자동 검증한 기록이 아닙니다.

설정·metadata에 치수와 방향을 보존하며 `readings.csv`의 `resistivity_ohm_m`에 계산값을 저장합니다. 기존 자동·선택 구간 TXT는 시간·저항·전압·전류의 네 열을 유지합니다.

기본 화면의 **1. 시험 설정**에서 운용 방식 **사용자 관리 저전압**(`operator_low_voltage`)을 선택합니다. 메인 GUI의 새 REAL 준비는 이 방식을 기본으로 사용합니다. 이 모드는 source **100 V 범위**를 사용하되 명령 전압·상한을 **절대 10 V 이하**로 제한합니다.

1 GΩ 기준저항 시험은 **1 GΩ·1 V 시험값** 버튼으로 시작합니다. 요청 전압 1 V, software trip 10 nA와 명목 저항 1 GΩ를 넣으며, 시간·요약 window·저장 폴더는 검토해 바꿉니다. 버튼은 REAL/SIM과 운용 방식, 사용자 확인 체크, resistive-limit 정책을 바꾸지 않습니다.

다음 실행 입력을 확인합니다.

- 사용자 연결 관리 확인: 연결·정격·외부 보호를 사용자가 관리한다는 확인입니다.
- Software current trip: A 단위로 입력하며, preset 10 nA도 사용자가 검토·변경합니다.
- 잔류 전압 확인: 출력 OFF와 방전 확인의 차이를 확인합니다.
- Resistive-limit 정책: ON 또는 OFF를 명시적으로 선택합니다.

이 방식에서는 정격 문서·fixture ID·과거 lid 전이 이력을 필수 입력으로 요구하지 않습니다. 입력한 정격이 있다면 전압 한도 계산에 반영합니다. 물리적인 인터록 설치가 확인된 것으로 자동 기록하지 않습니다.

**측정 설정 적용**은 필수 입력을 검사합니다. 누락 항목 전체를 표시하고 해당 항목을 누르면 입력란으로 이동합니다. 문법·수치 범위가 유효한 미완성 입력은 별도 **초안 적용**으로 보존할 수 있습니다. 초안은 ARM 준비 완료를 뜻하지 않습니다. 완성한 설정은 기본 화면의 **설정 저장**으로 `configs`에 저장합니다. [`operator_current_template.json`](../examples/operator_current_template.json)은 미확인 0 V 준비 파일입니다.

## 4. 연결 → ARM → START → STOP

메인 화면은 상단 4단계와 왼쪽 준비 상태에 현재 단계·다음 작업을 표시합니다. 판독·그래프는 **측정**, 통신 진단·상세 기록은 **진단·상세 기록** 탭에서 봅니다.

1. **측정 설정 적용** 후 **2. 연결**을 누릅니다. 정확한 모델 식별과 소스 OFF 확인을 수행합니다.
2. **3. ARM**을 누릅니다. 설정을 고정하고 실제 readback·오류 큐·전류 범위·zero correction·저장 준비를 검사합니다. 이때 source는 OFF와 zero setpoint를 유지합니다.
3. 인가 계획·상한·trip을 검토한 뒤 별도로 **4. START**를 누릅니다. 수집이 시작되면 그래프와 판독값, elapsed time, run 폴더를 확인합니다.
4. **STOP**으로 중지하거나 계획한 시간이 끝날 때까지 수집합니다. 완료·오류·취소 이유와 최종 output을 확인합니다.

ARM이 비활성인 경우 왼쪽 준비 상태에 누락된 설정을 표시합니다. 설정이 완성됐으면 연결 대기·ARM 대기·장비 조건 확인 등의 다음 단계를 표시합니다. START는 ARM을 완료해야 활성화됩니다. 버튼 위에 마우스를 두어도 대기 이유를 확인할 수 있습니다.

연결 후 설정이 미완료라면 출력 OFF에서 **연결 종료 후 설정 수정**을 누릅니다. 연결 종료가 완료되면 설정 창을 열어 첫 누락 입력을 안내합니다. 수정·적용 후 다시 연결 → ARM → START로 실행합니다. 검증 fixture의 현재 연결 인터록 관찰은 **진단·상세 기록** 탭에서 수행합니다.

모든 운용 방식에서 실제 장비 interlock 조회는 `1`이어야 합니다. `0`·조회 실패·current limit·readback 또는 장비 오류에는 출력 ON을 차단하거나 수집을 중지하고 OFF를 시도합니다. 사용자 관리 모드에서도 이 검사를 생략하지 않습니다. 조회 `1`은 물리적 설치 인증으로 표시하지 않습니다.

설정 불러오기·연결·ARM은 자동 출력 ON이 아닙니다. START 권한은 한 번 소비되고 설정·연결 변경 뒤 재사용하지 않습니다. STOP은 software stop이며 진행 중인 I/O와 여러 순차 query의 timeout이 지연에 더해질 수 있습니다. 최종 OFF는 방전 완료의 증거가 아니며 residual 상태는 UNVERIFIED입니다.

## 저장 결과 다시 열기

측정 작업이 끝나 출력 OFF가 확인되면 **저장 결과 분석**을 누릅니다. 과거 결과는 해당 폴더의 `readings.csv`를 엽니다. 저장값을 읽는 작업이며 장비 연결·ARM·START를 실행하지 않습니다.

시작·끝 시간(s)을 지정해 구간을 적용하면 I(t)·R(t), 전류·저항의 평균·표본 표준편차·유효 개수를 확인할 수 있습니다. 양 끝 시각은 포함합니다. 요약 구간 전에 STOP한 자료도 분석하며, 오류 판독은 통계에서 제외합니다. 개별 저항값의 평균은 실행 요약의 V/mean(I)와 별개입니다.

선택 구간은 네 열 TXT로 따로 저장합니다. 선택 행의 순서·SI 수치·누락값을 보존하며 원본 CSV나 전체 판독용 `analysis.txt`를 변경하지 않습니다. 기존 파일명은 덮어쓰지 않으므로 새 이름을 선택합니다.

v0.8.0 이후 사용자 STOP은 OFF와 저장이 확인되면 `stopped`로 기록합니다. 정상 완료는 `completed`, 장비/통신·저장 오류는 `aborted`로 구분하며 OFF 미확인은 계속 UNKNOWN으로 남습니다. 이전 버전의 상태 파일은 다시 쓰지 않습니다.

## 5. 기존 검증 fixture 방식

`verified_fixture`는 API 기본값이며 기존 저장 설정에 적용됩니다. 이 방식은 시료·fixture·케이블 정격과 승인 기록, fixture ID·담당자, 설치·독립 보호 기록 및 현재 연결의 OFF 상태 lid `0 → 1` 확인을 유지합니다. 운용 방식이 바뀌었다고 기존 승인값이나 실제 관찰을 새로 만든 것으로 처리하지 않습니다.

GUI에서는 설정 적용 → 연결 → ‘인터록 열림 확인’ → ‘인터록 닫힘 확인’ → ARM → 별도 START 순서로 실행합니다. 고전압 설정은 해당 방식의 전체 조건과 장비·설정·입력 정격의 최솟값을 적용합니다. 사용자 관리 모드의 10 V 한도를 올려 고전압 경로로 바꾸지는 않습니다. 기존 [commissioning 기록지](commissioning_checklist.md)와 [결선 검토](wiring_and_safety.md)는 검증 fixture 경로의 상세 참고 문서입니다.

## 6. CLI와 시뮬레이션

GUI에서 완성·저장한 설정으로 CLI를 실행합니다.

```powershell
.\Run-CLI.cmd measure --config "configs\operator-current.json"
.\Run-CLI.cmd simulate --config "app\examples\simulation_1gohm_config.json" --fast --progress
```

실측 사용자 관리 모드는 정적 fixture 서류와 OPEN/CLOSED 입력을 요구하지 않고, 운용 설정·실제 장비 상태를 검사한 뒤 별도 `START` 입력을 받습니다. 검증 fixture 모드는 기존 OPEN → CLOSED 관찰을 유지합니다. `--fast`는 시뮬레이션만 지원합니다. `--progress`는 중간 진행을 stderr에 즉시 표시하며 stdout의 최종 JSON은 유지합니다.

시뮬레이션에서 `simulation_resistance_ohm=1e9`는 가상 저항 모델입니다. 명목 1 V/1 GΩ는 1 nA이나 absorption·offset·noise 때문에 가상 판독도 차이가 있을 수 있습니다. 이 모델값을 실제 VISA 판독 대신 사용하지 않습니다. 실장비는 `FVMI_CURRENT`로 실제 전류를 읽고 V/I를 계산하며, native 저항 출력 모드는 차단합니다.

## 7. 결과 파일과 문제 보고

한 run의 폴더 전체를 보존합니다. `config.json`·`metadata.json`은 실행 설정과 운용 방식을, `readings.csv`는 실제 판독과 원문·quality flag를, `summary.csv`는 유효 평균 구간을 기록합니다. `events.jsonl`·`raw_io.jsonl`·`run_status.json`으로 명령·중지 이유·최종 상태를 대조합니다. Source 설정값이나 VSO를 독립 측정한 DUT 전압으로 표시하지 않습니다.

`analysis.txt`는 별도 조작 없이 함께 저장됩니다. 탭 구분 열 순서는 **Time (s), Resistance (Ohm), Voltage (V), Current (A)**이며 첫 행의 물리량·단위 외에는 숫자만 기록합니다. 시간은 시작 후 경과 시간, 저항은 native 값 또는 원시 V/I, 전압은 source 설정 readback, 전류는 원시 판독입니다. SI 단위·부호·0을 유지하고 누락값은 `nan`으로 표시합니다. 유효 요약 구간 밖의 판독도 저장하며 STOP 전에 취득한 행도 유지합니다. 품질 판단에는 `readings.csv`의 플래그를 함께 사용합니다.

이전 결과는 다음 명령으로 변환합니다. 장비와 통신하지 않으며 기본 출력은 원본 CSV와 같은 폴더의 `analysis.txt`입니다. 기존 파일이 있으면 덮어쓰지 않고 중지하므로 다른 이름을 `--output`으로 지정합니다.

```powershell
.\Run-CLI.cmd export-analysis "results\RUN\readings.csv"
.\Run-CLI.cmd export-analysis "results\RUN\readings.csv" --output "results\RUN\analysis-copy.txt"
```

문제가 있으면 버전, Windows·어댑터·backend 정보, 실패 단계와 해당 진단/run 폴더를 보존합니다. 파일은 로컬 저장이며 자동 업로드하지 않습니다. 전달 전 시리얼과 로컬 경로를 검토합니다. 활동 중인 run이 없는 폴더에서만 복구 명령을 사용합니다. 복구는 incomplete run을 interrupted로 기록하며 전압 인가나 수집을 재개하지 않습니다.
