# 6517A · NI GPIB-USB 사용자 시험 순서

v0.5.0은 연결·정격을 사용자가 관리하는 저전압 시험과 기존 검증 fixture 방식을 제공합니다. 사용자 제공 기록에서 파일 무결성·실제 IDN·보호 OFF 조회 `0`은 확인됐습니다. 전압 인가·current 수집·인터록 차단·방전은 그 진단과 별도 시험입니다.

## 1. 패키지 실행

1. GitHub Release에서 `6517A-USB-GPIB-Trial-0.5.0-Windows-x64.zip`과 checksum을 받습니다. 새 쓰기 가능한 폴더에 전체를 풉니다.
2. `Verify-Bundle.cmd`로 START → CHECK → PASS를 확인합니다. 실패 시 `diagnostics/bundle-verification-*.json`의 파일명·사유를 확인합니다. 보고서를 쓸 수 없으면 WARN과 `report_saved=false`가 표시됩니다.
3. `Test-Simulation.cmd`로 가상 수집·저장을 확인하고 `Start-GUI.cmd`를 엽니다. GUI의 초기 SIMULATION·0 V·미연결 상태가 정상입니다.

Python과 Python 의존성은 포함됩니다. v0.4.6부터 소스가 있는 파생 bytecode는 패키지와 고정 manifest에서 제외하며, 소스·DLL·확장 모듈·stdlib ZIP·독립 bytecode는 계속 해시 검사합니다. 배포 검사는 실제 Windows에서 새 위치에 추출한 ZIP의 실행과 캐시 생성 후 재검사를 포함합니다.

## 2. NI 연결 확인

NI MAX와 동일한 board·주소를 선택하고 NI MAX test panel과 다른 제어 프로그램을 닫습니다. 이미 호환 NI-488.2·NI-VISA 64-bit 설치가 동작하면 기존 설치를 사용합니다. 예시 resource는 `GPIB0::27::INSTR`이며 실제 보유 장비의 주소를 선택합니다.

GUI에서 SIM 연결을 종료한 뒤 ‘NI 실장비 연결 시험 시작’을 선택합니다. REAL 준비는 0 V·trip 미설정·사용자 확인 미선택 상태로 시작합니다. 목록 조회 → 주소 선택 → IDN → 보호 OFF 순서로 진단합니다. IDN 조회는 출력 변경을 하지 않습니다. 보호 OFF는 식별된 장비에 OFF·abort를 요청하며 진단 종료 시 session을 닫습니다. 이후 측정 연결은 별도로 수행합니다.

Portable의 직접 진단 명령은 다음과 같습니다.

```powershell
.\Check-Connection.cmd "GPIB0::27::INSTR" "@ivi"
.\Check-Output-Off.cmd "GPIB0::27::INSTR" "@ivi"
```

NI-VISA를 생략하는 `@py` 시험 기능은 `Enable-NI-Only.cmd`로 선택 확장을 명시적으로 설치한 뒤 재시작해 선택합니다. NI-488.2 driver와 호환 DLL은 계속 필요합니다. 자세한 조건은 [VISA 안내](windows_visa.md)에 있습니다.

## 3. 사용자 관리 저전압 설정

‘4. 시료·시험 설정 입력’에서 운용 방식 **사용자 관리 저전압**(`operator_low_voltage`)을 선택합니다. 메인 GUI의 새 REAL 준비는 이 방식을 기본으로 사용합니다. 이 모드는 source **100 V 범위**를 사용하되 명령 전압·상한을 **절대 10 V 이하**로 제한합니다.

1 GΩ 기준저항 시험은 **1 GΩ·1 V 시험값** 버튼으로 시작합니다. 요청 전압 1 V, software trip 10 nA와 명목 저항 1 GΩ를 넣으며, 시간·요약 window·저장 폴더는 검토해 바꿉니다. 버튼은 REAL/SIM과 운용 방식, 사용자 확인 체크, resistive-limit 정책을 바꾸지 않습니다.

다음 실행 입력을 확인합니다.

- 사용자 연결 관리 확인: 연결·정격·외부 보호를 사용자가 관리한다는 확인입니다.
- Software current trip: A 단위로 입력하며, preset 10 nA도 사용자가 검토·변경합니다.
- 잔류 전압 확인: 출력 OFF와 방전 확인의 차이를 확인합니다.
- Resistive-limit 정책: ON 또는 OFF를 명시적으로 선택합니다.

이 방식에서는 정격 문서·fixture ID·과거 lid 전이 이력을 필수 입력으로 요구하지 않습니다. 입력한 정격이 있다면 전압 한도 계산에 반영합니다. 물리적인 인터록 설치가 확인된 것으로 자동 기록하지 않습니다.

문법·수치 범위가 유효하면 미완성 설정도 초안으로 적용할 수 있습니다. ‘초안 적용’은 연결·ARM·START를 실행하지 않습니다. 화면의 ARM 준비 상태를 확인하고, 완성한 설정은 ‘설정 내보내기’로 `configs`에 저장합니다. [`operator_current_template.json`](../examples/operator_current_template.json)은 미확인 0 V 준비 파일입니다.

## 4. 연결 → ARM → START → STOP

1. 설정을 적용한 뒤 **연결**을 누릅니다. 정확한 모델 식별과 소스 OFF 확인을 수행합니다.
2. **ARM**을 누릅니다. 설정을 고정하고 실제 readback·오류 큐·전류 범위·zero correction·저장 준비를 검사합니다. 이때 source는 OFF와 zero setpoint를 유지합니다.
3. 인가 계획·상한·trip을 검토한 뒤 별도로 **START**를 누릅니다. 수집이 시작되면 그래프와 판독값, elapsed time, run 폴더를 확인합니다.
4. **STOP**으로 중지하거나 계획한 시간이 끝날 때까지 수집합니다. 완료·오류·취소 이유와 최종 output을 확인합니다.

모든 운용 방식에서 실제 장비 interlock 조회는 `1`이어야 합니다. `0`·조회 실패·current limit·readback 또는 장비 오류에는 출력 ON을 차단하거나 수집을 중지하고 OFF를 시도합니다. 사용자 관리 모드에서도 이 검사를 생략하지 않습니다. 조회 `1`은 물리적 설치 인증으로 표시하지 않습니다.

설정 불러오기·연결·ARM은 자동 출력 ON이 아닙니다. START 권한은 한 번 소비되고 설정·연결 변경 뒤 재사용하지 않습니다. STOP은 software stop이며 진행 중인 I/O와 여러 순차 query의 timeout이 지연에 더해질 수 있습니다. 최종 OFF는 방전 완료의 증거가 아니며 residual 상태는 UNVERIFIED입니다.

## 5. 기존 검증 fixture 방식

`verified_fixture`는 API 기본값이며 기존 저장 설정에 적용됩니다. 이 방식은 시료·fixture·케이블 정격과 승인 기록, fixture ID·담당자, 설치·독립 보호 기록 및 현재 연결의 OFF 상태 lid `0 → 1` 확인을 유지합니다. 운용 방식이 바뀌었다고 기존 승인값이나 실제 관찰을 새로 만든 것으로 처리하지 않습니다.

GUI에서는 설정 적용 → 연결 → ‘인터록 열림 확인’ → ‘인터록 닫힘 확인’ → ARM → 별도 START 순서로 실행합니다. 고전압 설정은 해당 방식의 전체 조건과 장비·설정·입력 정격의 최솟값을 적용합니다. 사용자 관리 모드의 10 V 한도를 올려 고전압 경로로 바꾸지는 않습니다. 기존 [commissioning 기록지](commissioning_checklist.md)와 [결선 검토](wiring_and_safety.md)는 검증 fixture 경로의 상세 참고 문서입니다.

## 6. CLI와 시뮬레이션

GUI에서 완성·저장한 설정으로 CLI를 실행합니다.

```powershell
.\Run-CLI.cmd measure --config "configs\operator-current.json"
.\Run-CLI.cmd simulate --config "app\examples\simulation_1gohm_config.json" --fast
```

실측 사용자 관리 모드는 정적 fixture 서류와 OPEN/CLOSED 입력을 요구하지 않고, 운용 설정·실제 장비 상태를 검사한 뒤 별도 `START` 입력을 받습니다. 검증 fixture 모드는 기존 OPEN → CLOSED 관찰을 유지합니다. `--fast`는 시뮬레이션만 지원합니다.

시뮬레이션에서 `simulation_resistance_ohm=1e9`는 가상 저항 모델입니다. 명목 1 V/1 GΩ는 1 nA이나 absorption·offset·noise 때문에 가상 판독도 차이가 있을 수 있습니다. 이 모델값을 실제 VISA 판독 대신 사용하지 않습니다. 실장비는 `FVMI_CURRENT`로 실제 전류를 읽고 V/I를 계산하며, native 저항 출력 모드는 차단합니다.

## 7. 결과 파일과 문제 보고

한 run의 폴더 전체를 보존합니다. `config.json`·`metadata.json`은 실행 설정과 운용 방식을, `readings.csv`는 실제 판독과 원문·quality flag를, `summary.csv`는 유효 평균 구간을 기록합니다. `events.jsonl`·`raw_io.jsonl`·`run_status.json`으로 명령·중지 이유·최종 상태를 대조합니다. Source 설정값이나 VSO를 독립 측정한 DUT 전압으로 표시하지 않습니다.

문제가 있으면 버전, Windows·어댑터·backend 정보, 실패 단계와 해당 진단/run 폴더를 보존합니다. 파일은 로컬 저장이며 자동 업로드하지 않습니다. 전달 전 시리얼과 로컬 경로를 검토합니다. 활동 중인 run이 없는 폴더에서만 복구 명령을 사용합니다. 복구는 incomplete run을 interrupted로 기록하며 전압 인가나 수집을 재개하지 않습니다.
