# 1 GΩ 기준저항 시험

v0.6.2의 사용자 관리 저전압 모드는 연결 구성을 사용자에게 맡기고, 전압·시간·trip 입력부터 ARM → START → current·저항 그래프와 CSV 저장까지 수행합니다. 별도 프로그램 변경 없이 GUI의 **1 GΩ·1 V 시험값**을 사용할 수 있습니다.

## GUI 실행 순서

1. 새 ZIP을 풀고 `Verify-Bundle.cmd` → `Test-Simulation.cmd` → `Start-GUI.cmd`를 실행합니다.
2. 실제 시험은 **진단·상세 기록** 탭에서 SIM 연결 종료 → REAL 준비 → NI MAX와 같은 주소 → IDN → 보호 OFF를 확인합니다.
3. 기본 화면의 **1. 시험 설정**에서 사용자 관리 저전압 방식을 확인하고 **1 GΩ·1 V 시험값**을 누릅니다.
4. 요청 1 V, source 100 V 범위, 상한 10 V 이하, software trip 10 nA와 시간·저장 폴더를 검토합니다. 사용자 연결 관리 확인, 잔류 전압 확인, resistive-limit ON/OFF 정책을 직접 선택합니다.
5. **측정 설정 적용 → 2. 연결 → 3. ARM → 4. START**로 실행하고 그래프·CSV를 확인합니다. 중지는 STOP을 사용합니다.

Preset은 사용자가 눌렀을 때만 값을 넣습니다. REAL/SIM·운용 방식·확인 체크·resistive-limit 정책은 자동 승인하지 않습니다. **측정 설정 적용**은 누락된 실행 입력을 표시하며, 항목을 누르면 입력란으로 이동합니다. 미완성 설정은 별도 **초안 적용**으로 보존할 수 있습니다. 메인 준비 상태에 ARM이 비활성인 이유와 다음 작업을 표시합니다. 연결 후 수정이 필요하면 출력 OFF에서 **연결 종료 후 설정 수정**을 누르고, 수정 후 다시 연결 → ARM → START로 실행합니다.

[`operator_current_template.json`](../examples/operator_current_template.json)은 REAL·사용자 관리·0 V·미확인 초안입니다. [`simulation_1gohm_config.json`](../examples/simulation_1gohm_config.json)은 가상 1 GΩ 모델 시험입니다. 과거 [`reference_1gohm_draft.json`](../examples/reference_1gohm_draft.json)은 정격 메타데이터를 보관한 준비 파일이며, 실행에는 v0.5.0 운용 방식과 실행 입력을 설정합니다.

## 명목 계산값

| 전압 | 예상 전류 I=V/R | 저항 소모 전력 V²/R |
|---|---|---|
| 1 V | 1 nA | 1 nW |
| 5 V | 5 nA | 25 nW |
| 10 V | 10 nA | 100 nW |

이 표는 명목 1 GΩ의 계산입니다. 기준저항의 교정값·허용차·전압 계수, 누설·settling·측정 오차는 실제 결과와 함께 평가합니다. 10 nA preset은 검토 가능한 software trip이며 hardware current limit나 programmable compliance가 아닙니다.

## 운용 범위와 기록

사용자 관리 방식은 source 100 V 범위에서 **절대 10 V 이하**로 제한됩니다. 연결·정격·외부 보호는 사용자가 관리하고 이를 명시적으로 확인합니다. 정격 문서·fixture ID·과거 lid 전이 기록을 필수로 요구하지 않지만, 실제 장비의 interlock 조회 `0`·실패·오류 상태는 출력을 차단합니다. 물리적인 인터록 설치를 인증된 것으로 기록하지 않습니다. 기존 검증 fixture 방식은 원래의 정격·승인·현재 연결 `0 → 1` 관찰 절차를 유지합니다.

측정 결과는 `readings.csv`의 current와 `summary.csv`의 V/I를 비교합니다. 가상 모델은 `simulation_resistance_ohm`을 사용하지만 실제 VISA 경로는 장비 응답을 사용합니다. Current와 역산·native 저항은 다른 필드에 기록됩니다.

## 제공된 부품 정격 메타데이터

| 부품·절연 구간 | 제공된 사양 | 기록 의미 |
|---|---|---|
| 저항 | Maximum pulse voltage 30 kV | 펄스 정격; 연속 DC 정격으로 자동 전환하지 않음 |
| Triax 중심–inner shield | Working voltage 600 V peak | 해당 도체쌍 사이 전위차 정격 |
| Triax 중심/inner shield–outer shell | Working voltage 1,300 V peak | outer shell 기준의 별도 절연 정격 |
| 바나나 소스 케이블 | Max 3 kV | 제공된 최대값; 시간·CAT 조건은 추가 추정하지 않음 |

이 값은 메타데이터로 보존합니다. 케이블 정격은 6517A INPUT 한도를 바꾸지 않으며, 저항의 펄스 정격이나 낮은 소모 전력을 근거로 프로그램이 DC 정격·물리적 보호를 인증하지 않습니다. 사용자 관리 모드의 10 V 제한은 이 값으로 올릴 수 없습니다.

현재 사용자 원문에서 확인된 장비 근거는 IDN과 보호 OFF 조회까지입니다. 전압 인가·current 수집과 독립 차단·방전의 실제 결과는 별도로 검증하며, OFF 후 residual 상태는 UNVERIFIED로 남습니다.
