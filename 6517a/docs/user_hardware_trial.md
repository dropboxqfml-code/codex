# 6517A·USB-GPIB 사용자 시험 순서

이 문서는 Windows 10/11 64-bit에서 **시험용 프로그램을 실제 PC와 장비 조합으로 검증하는 절차**입니다. 현재 개발 환경은 Linux이고 실제 6517A·USB-GPIB·fixture는 개발 환경에 제공되지 않았습니다. 사용자는 v0.3.0 GUI 화면 실행과 NI MAX에서 6517A 인식을 확인했습니다. 프로그램 자체의 IDN·측정 성공 여부는 아직 사용자 시험 기록으로 전달되지 않았습니다. 매뉴얼 대조·시뮬레이터·모의 VISA·배포 파일 검사를 실제 Windows/장비 시험으로 해석하지 않습니다. 수행한 범위는 [검증 기록](validation.md)에 구분합니다.

고전압을 자동 인가하는 self-test는 없습니다. 시료·fixture·케이블의 확인된 정격, 보호 enclosure·인터록·독립적인 차단/방전 수단과 자격 있는 담당자의 승인 아래 시험합니다. `OUTPUT OFF`는 시료 방전 완료가 아닙니다. 실제 잔류 전압 확인이 제공되지 않았으므로 프로그램은 `UNVERIFIED`를 유지합니다.

## 1. 압축 해제와 시뮬레이션

1. `6517A-USB-GPIB-Trial-0.4.2-Windows-x64.zip`과 배포 시 제공한 SHA-256을 함께 받습니다. ZIP 파일의 `Get-FileHash -Algorithm SHA256` 결과를 비교합니다. 일치하지 않으면 실행하지 않고 파일을 다시 받습니다.
2. 로컬의 쓰기 가능한 폴더에 **모든 파일**을 풉니다. ZIP 안에서 직접 실행하지 말고, `Start-GUI.cmd`와 함께 있는 runtime·app 폴더를 분리하거나 삭제하지 않습니다. 실행 전에 출력이 이미 켜진 장비가 있다면 현장 절차로 관리합니다.
3. `Start-GUI.cmd`로 GUI를 실행해 상단 `SIMULATION`과 초기 0 V, trip 미설정, START 비활성 상태를 확인합니다. 이 화면은 실장비 기능이 없다는 뜻이 아니라 의도한 기본 상태입니다. 프로그램 시작이나 설정 load만으로 장비에 연결하거나 출력 ON을 하지 않습니다.
4. `Test-Simulation.cmd`를 실행하거나 GUI에서 가상 예제 설정을 불러와 연결 → ARM → START를 시험합니다. 예제 trip과 전압은 가상 시료용이며 실제 시료 승인값이 아닙니다.
5. 결과 폴더에 `readings.csv`, `summary.csv`, `raw_io.jsonl`, `run_status.json`이 생겼는지 확인합니다. 가상 데이터의 simulation 표시, 종료 `completed`, output `OFF`, residual `UNVERIFIED`를 확인합니다. 이 결과는 Python/Qt/저장 기능 점검이며 GPIB 하드웨어 시험이 아닙니다.

Portable 패키지에는 `runtime/python.exe`, `app/src`·`app/docs`·`app/examples`, 사용자 설정용 `configs`와 실행용 CMD가 포함됩니다. `Verify-Bundle.cmd`로 내부 파일의 manifest SHA-256을 검사할 수 있습니다. Python과 Python 의존성이 포함되므로 Python·uv 설치가 필요하지 않습니다. 어댑터 driver와 VISA runtime은 다음 단계에서 별도로 설치합니다. Native Windows에서 아직 실행하지 못한 패키지라면 그 사실을 [검증 기록](validation.md)의 결과와 함께 보존합니다.

## 2. 어댑터와 VISA 준비

- 사용자가 선택한 장비는 **NI GPIB-USB 계열**입니다. 정확한 HS/HS+ 등의 모델명을 확인하고, 그 모델과 Windows 버전을 지원하는 **NI-488.2 및 NI-VISA 64-bit**를 NI의 설치 안내에 따라 준비합니다. 정확한 모델·driver 버전은 아직 확인되지 않았으므로 특정 조합이 시험 완료라고 표시하지 않습니다. 다른 제조사의 경우 해당 어댑터용 driver와 VISA를 사용합니다.
- 사용자는 이미 NI MAX에서 6517A가 보인다고 확인했습니다. 그 화면에 표시된 adapter board와 장비 주소를 기록해 프로그램에서도 동일하게 선택합니다. 6517A 전면의 GPIB 주소와 SCPI 언어 설정을 확인합니다. DDC mode를 혼용하지 않습니다.
- `GPIB0::27::INSTR`는 주소 형식의 예시입니다. 장비가 USB-GPIB 어댑터 뒤에 있으므로 `USB::...` resource가 나온다고 가정하지 않습니다.
- 제조사 도구로 확인한 뒤 NI MAX·Connection Expert·다른 제어 프로그램을 닫습니다. 프로그램 하나의 worker가 선택한 session을 소유하도록 합니다.
- `pyvisa`나 `pyvisa-py` 설치만으로 어댑터 driver가 준비되었다고 판단하지 않습니다. 가상 COM/Prologix controller는 이 배포의 VISA GPIB 경로와 다르며 지원하지 않습니다.

기존 NI-VISA 경로를 먼저 사용합니다. NI-VISA를 생략하는 대안이 필요한 경우에만 GUI를 닫고 `Enable-NI-Only.cmd`를 실행합니다. 안내와 라이선스 조건을 확인하고 `INSTALL`을 입력해 선택 확장을 설치한 뒤 GUI를 다시 시작하고 backend를 `@py`로 명시적으로 선택합니다. 이 선택 설치에는 인터넷 연결이 필요합니다. 이 경로는 사용자 PC에 선택 확장으로 설치한 PyVISA-py/gpib-ctypes로 **기존 NI-488.2 driver와 64-bit GPIB DLL**을 호출하는 실험적 대안입니다. 기본 ZIP에 두 Python 패키지를 사전 설치하지 않습니다. 선택 설치 위치는 `extensions/ni4882`이며, 완료 표식과 파일 해시가 맞는 기존 설치는 재사용하며, 불완전하거나 변경된 폴더를 덮어쓰거나 성공으로 처리하지 않습니다. 두 NI 구성요소를 모두 없애는 기능이 아니며 장치 protocol을 USBTMC로 바꾸지 않습니다. Driver/DLL이 없거나 bitness가 맞지 않으면 진단에서 중단하며 다른 backend로 자동 전환하지 않습니다. 실제 장비 시험은 아직 미수행입니다.

상세 설명은 [Windows VISA 안내](windows_visa.md)를 참고하세요.

## 3. 출력 변경 없는 연결 진단

연결 안내의 ‘NI 실장비 연결 시험 시작 (출력 ON 없음)’ 버튼으로 REAL 모드를 명시적으로 선택합니다. SIM 연결 중이면 먼저 연결을 종료합니다. 이 버튼은 실장비 준비를 0 V·trip 미설정·미승인 상태로 초기화하며 가상 설정을 실장비 승인으로 재사용하지 않습니다. 장비를 조회하거나 출력을 변경하지 않습니다. 기본 VISA/`@ivi`를 확인하고 ‘1. GPIB 목록 조회’ 후 NI MAX와 같은 실제 주소를 고릅니다. 이어 ‘2. 선택 주소 IDN 확인’을 실행합니다. 연결 진단 또는 `Check-Connection.cmd`로 선택한 resource의 IDN을 확인합니다. 이 단계는 resource 열거와 `*IDN?` 조회만 수행하며 전압 설정이나 출력 ON·OFF를 요청하지 않습니다. 따라서 결과의 output 상태는 `UNKNOWN`입니다.

Portable 폴더의 대응 명령은 다음과 같습니다. 주소는 예시이며 실제로 NI MAX에 표시된 board/address로 바꿉니다.

```powershell
.\Check-Connection.cmd
.\Check-Connection.cmd "GPIB0::27::INSTR" "@ivi"
```

Python 소스 실행 환경의 대응 명령은 다음과 같습니다.

```powershell
uv run --locked python -m keithley6517a.cli diagnose --report-dir diagnostics
uv run --locked python -m keithley6517a.cli diagnose --resource "실제 GPIB resource" --backend "@ivi" --report-dir diagnostics
```

NI-VISA를 생략하는 대안을 시험할 때만 위 명령의 `@ivi`를 `@py`로 바꿉니다. 먼저 `Check-Connection.cmd "실제 GPIB resource" "@py"`의 IDN-only 진단을 사용하고, 보고서의 backend·driver 오류와 실제 적용 timeout을 확인합니다. NI의 GPIB timeout 단계 때문에 요청 2,000 ms가 실제 3,000 ms로 적용될 수 있으며 요청값을 지연 보증으로 사용하지 않습니다.

목록이 비어 있으면 제조사 driver/board/address를 확인합니다. VISA shared library가 없다는 오류면 먼저 호환 VISA runtime과 64-bit 조합을 확인합니다. IDN이 6517B 등 다른 모델이면 그 장비의 제어 명령을 보내지 않고 중단합니다. Timeout 또는 형식 오류에 대해 주소를 무작위로 탐색하거나 출력 ON을 자동 재전송하지 않습니다.

연결 안내에서 진단 성공 여부와 다음 동작을 확인합니다. IDN 성공은 model이 6517A라는 조회 결과이며 OFF/방전/ARM 승인이 아닙니다. 모의 transport나 SIMULATION 결과는 실장비 진단 통과로 표시하지 않습니다. 재연결이나 resource/backend 변경 후에는 과거 성공 표시를 현재 연결의 승인으로 재사용하지 않습니다.

GUI가 열리지 않으면 Test-Simulation.cmd의 console 오류와 diagnostics/launcher-error*.json 생성 여부를 확인합니다. Launcher 보고서가 생기기 전 runtime 자체가 실행되지 못할 수도 있으므로 보고서가 없다고 성공으로 보지 않습니다. 진단 JSON의 실패 단계·원문 오류·권장 확인을 읽습니다. 진단 보고서는 local 파일이며 자동 전송되지 않습니다. 장비 serial·resource·local library 경로가 포함될 수 있으므로 다른 사람에게 전달하기 전 내용을 검토합니다.

## 4. 명시적인 보호 OFF 점검

이 단계는 IDN-only와 다르게 **정확히 6517A로 식별된 장비에 보호 목적 출력 OFF와 abort를 요청**합니다. 현장 담당자가 출력·시료의 상태를 관리할 수 있는 조건에서 수행합니다. GUI의 ‘3. 선택 장비 보호 OFF 시험’ 또는 CLI의 명시적인 `--confirm-off`를 선택합니다.

```powershell
uv run --locked python -m keithley6517a.cli diagnose --resource "실제 GPIB resource" --backend "@ivi" --confirm-off --report-dir diagnostics
```

Portable에서는 `.\Check-Output-Off.cmd "실제 GPIB resource" "@ivi"`를 사용합니다. resource를 생략하면 출력 점검을 진행하지 않습니다. 보고서의 OFF 확인과 장비 전면 상태를 비교해 기록합니다. OFF 요청/확인이 실패하면 상태는 `UNKNOWN`이며 현장에서 독립적인 차단 수단을 사용합니다. 재연결·프로그램 종료·USB 분리가 출력을 차단한다고 가정하지 않습니다. 이 시험에 고전압 인가나 초보자용 USB 분리 시험을 추가하지 않습니다.

`SOUR:VOLT?`나 VSO=0, 작은 전류, 몇 초의 대기만으로 시료 방전 완료를 판정하지 않습니다. 방전 확인은 승인된 외부 절차로 별도 수행합니다.

## 5. 실제 current 시험 설정

먼저 [결선과 안전 정책](wiring_and_safety.md)과 [commissioning 기록지](commissioning_checklist.md)를 확인합니다. 배선 변경은 출력 OFF 및 실제 방전 확인 후 수행합니다. 이 프로그램의 1차 지원 결선은 승인된 저측 FVMI뿐이며 floating/high-side 측정은 지원하지 않습니다.

연결 안내의 ‘4. 시료·시험 설정 입력’으로 시험 설정 대화상자를 열고 다음 실제 정보를 입력합니다. 설정 적용 자체는 연결·ARM·START가 아닙니다. 포함된 app/examples 템플릿을 직접 덮어쓰지 말고 사용자 승인 설정을 configs 안의 별도 파일로 저장합니다. 배포 기본 파일은 manifest 무결성 검사 대상입니다.

| 입력 | 확인할 내용 |
|---|---|
| 장비 연결 | 선택한 resource, VISA backend/library, 유한 timeout, EOI·terminator |
| 시료·fixture | sample ID, fixture ID, 담당 승인자, 실험 승인 문서/기록 |
| 전압 한계 | 시료·fixture·케이블의 실제 정격, 작업용 software ceiling |
| 보호 정책 | 사용자가 검토한 software current trip, resistive-limit ON/OFF 정책, 독립 하드웨어 보호 |
| 시간·전압 계획 | 승인된 낮은 전압부터 시작하는 목록, dwell·제외 구간·평균 window·NPLC·sample interval |
| 사전 확인 | 물리적 설치·lid 전이 점검 기록, 독립 하드웨어 보호 검토, 잔류 전압 경고 확인 |
| 데이터 | 쓰기 가능한 저장 폴더, 환경/시료 메모 |

초기 목표 0 V와 software ceiling 10 V는 개발상의 보수적 기본값이며 안전 전압 보증이 아닙니다. 시료/fixture/케이블 정격과 trip을 추측하거나 가상 예제에서 복사하지 않습니다. 확인되지 않은 값은 빈 상태로 두고 실장비 ARM을 진행하지 않습니다. V-Source의 고정 하드웨어 current limit와 software trip, 외부 보호는 별개입니다. nA/µA programmable compliance로 표시하지 않습니다.

이전 v0.2.0 승인 파일을 쓰는 경우에도 독립 하드웨어 보호를 실제로 검토한 뒤 `commissioning.hardware_protection_reviewed=true`를 명시해야 합니다. 이전 파일을 불러왔다는 이유로 이 항목을 자동 승인하지 않습니다.

기본 실장비 시험은 `FVMI_CURRENT`입니다. 실제 측정 전류를 별도로 검증하지 못한 `NATIVE_RESISTANCE` 실장비 출력은 계속 차단합니다. 정격이 확인된 기준저항과 허용된 낮은 전압의 비교부터 시작하고, 실제 전면값과 PC의 단위·부호·모드·시간을 대조합니다.

## 6. 현재 연결의 인터록 확인과 측정

1. REAL VISA를 명시적으로 선택하고 연결합니다. 장비 식별과 보호 OFF가 확인되었는지 확인합니다.
2. 현재 연결의 OUTPUT OFF 상태에서 승인된 fixture의 lid를 직접 열어 ‘인터록 열림 확인’을 누릅니다. 조회 0이 필요합니다.
3. lid를 닫고 ‘인터록 닫힘 확인’을 누릅니다. 같은 fixture·연결에서 조회 1이 필요합니다. 조회 1만으로는 설치를 입증하지 못하며, 이후 케이블 분리를 항상 검출할 수도 없습니다(매뉴얼 3-137).
4. ARM으로 설정 readback·오류 queue·저장 준비와 실행 snapshot을 확인합니다. ARM은 출력 ON이 아닙니다.
5. 전압 계획과 승인된 제한을 검토한 뒤 별도 START를 누릅니다. 설정 변경이나 재연결 뒤에는 측정을 자동 재개하지 않습니다.
6. 판독 시각·상태·quality flag·실제 sample interval을 관찰합니다. current trip·source limit·인터록/통신/저장 오류에는 추가 전압 상승을 중단하고 OFF를 시도합니다.
7. STOP은 software stop입니다. 진행 중인 VISA call 및 여러 순차 call의 timeout 때문에 지연될 수 있습니다. 실제 하드웨어 emergency stop을 대신하지 않습니다.
8. 종료 시 장비 전면·`run_status.json`의 output 상태를 비교하고, 독립적인 잔류 전압 확인 절차를 별도 수행합니다.

Portable에서는 `.\Run-CLI.cmd measure --config "configs\approved-current.json"`처럼 사용자가 승인·저장한 파일을 지정합니다. CLI `measure --config 승인파일.json`은 OFF 상태에서 `OPEN`·`CLOSED`를 입력받아 조회를 검사한 뒤 ARM하고, 별도의 `START` 입력을 요구합니다. 입력 문자열이나 체크박스는 실제 하드웨어 인증이 아닙니다.

## 7. 시험 결과 보존과 문제 보고

한 run의 고유 폴더 전체를 보존합니다. `config.json`은 승인된 설정과 소프트웨어 fingerprint, `metadata.json`은 장비 식별과 승인·환경 정보, `raw_io.jsonl`은 원문 통신을 담습니다. `readings.csv`에는 과도·제외·오류 구간도 남으며 `summary.csv`만을 보고 raw 기록을 버리지 않습니다.

`run_status.json`의 `completed`·`aborted`·`interrupted`, 종료 이유, 최종 output 및 residual 상태를 구분합니다. `OUTPUT_OFF_CONFIRMED`라는 UI 상태는 출력 명령 상태를 뜻하며 파일 저장 완료나 접촉 가능 상태를 뜻하지 않습니다. 저장 오류가 발생한 run을 정상 결과로 간주하지 않습니다.

문제를 전달할 때 아래 양식을 함께 작성합니다. 진단·run 파일은 사용자가 검토하고 필요한 범위만 직접 전달하며, 비밀키나 계정 암호를 기록하지 않습니다.

| 항목 | 사용자 시험 기록 |
|---|---|
| 시험 날짜·담당자 | |
| 프로그램 버전·ZIP SHA-256 | |
| Windows 버전·64-bit 여부 | |
| USB-GPIB 제조사·정확한 모델·driver 버전 | |
| VISA 제조사·runtime 버전·선택 backend/library (`@ivi`/`@py`) | |
| `@py` 선택 시 NI-488.2·GPIB DLL bitness 및 실제 적용 timeout | |
| Resource·장비 model/serial/firmware | |
| IDN-only 진단 폴더·성공/오류 단계 | |
| 보호 OFF 진단·전면 비교·OFF/UNKNOWN 결과 | |
| Fixture·기준저항·정격/승인 기록 참조 | |
| 현재 연결 interlock open=0 / closed=1 결과 | |
| 승인된 저전압·trip·NPLC·시간 계획 | |
| ARM·START·STOP 결과와 실제 지연 관찰 | |
| Run 폴더·status·output·residual 상태 | |
| 증상·예상 결과·실제 결과·재현 단계 | |

실험을 멈춘 뒤 활동 중인 run이 없는 저장 폴더에서만 `recover`를 실행합니다. Incomplete run을 `interrupted`로 표시할 뿐 전압을 재인가하거나 측정을 재개하지 않습니다.
