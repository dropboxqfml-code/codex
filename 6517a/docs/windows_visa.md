# Windows 64-bit와 USB-GPIB / VISA

## 실행 방법 선택

사용자 시험에는 Windows x64 portable ZIP을 사용합니다. 포함된 Python 3.12.14와 잠금 버전의 Windows 의존성을 사용하므로 Python·uv를 별도로 설치하지 않습니다. ZIP을 완전히 푼 뒤 `Verify-Bundle.cmd`로 내부 파일을 검사하고 `Start-GUI.cmd`로 기본 SIMULATION 화면을 시작합니다. `Test-Simulation.cmd`는 실장비 없이 기능을 확인하는 실행 경로입니다. 자세한 순서는 [사용자 시험 안내](user_hardware_trial.md)에 있습니다.

소스 개발자는 Python 3.12 64-bit와 uv를 준비하고 프로젝트 폴더에서 `uv sync --locked`, `uv run --locked python -m keithley6517a`를 실행합니다. 이 방법은 portable 배포본의 사용자 실행 조건과 구분합니다.

**USB-GPIB 어댑터 driver와 호환 VISA runtime은 배포 ZIP에 포함되지 않습니다.** 어댑터 제조사의 설치 안내를 따릅니다. Windows 10/11 64-bit가 대상이며, 현재 개발 검증은 제공된 Linux 환경에서 수행했습니다. 배포 파일·wheel tag·해시 검사와 실제 Windows GUI/어댑터 실행 검증은 [검증 기록](validation.md)에 따로 기록합니다.

## 실제 USB-GPIB 설치 확인

1. 사용자가 선택한 **NI GPIB-USB 계열**의 정확한 모델(HS/HS+ 등)을 확인하고, 해당 모델과 Windows 버전에 맞는 **NI-488.2 및 NI-VISA 64-bit**를 설치합니다. 정확한 모델/driver 조합은 아직 제공되지 않았으므로 그 조합의 동작을 시험 완료로 표시하지 않습니다. 다른 어댑터는 해당 제조사의 Windows x64 driver와 VISA를 사용합니다. Python `PyVISA`만으로 모든 어댑터가 작동하지 않습니다. 프로그램·VISA library·driver의 bitness가 호환되는지도 확인합니다.
2. NI MAX에서 adapter board와 장비 GPIB 주소를 확인합니다. `GPIB0::27::INSTR`는 형식 예시일 뿐 고정 주소가 아닙니다. 6517A는 USBTMC 장비가 아니므로 `USB::...` resource를 기대하지 않습니다.
3. 장비 전면에서 GPIB 주소와 SCPI language를 확인합니다. legacy DDC와 SCPI를 혼용하지 않습니다. 제조사 도구로 확인한 후 NI MAX·Connection Expert·별도 제어 스크립트를 닫습니다.
4. GUI의 VISA backend/library와 resource 조회 또는 진단을 사용해 model·serial·firmware를 확인합니다. 환경에 따라 기본 library, `@ivi`, 명시적 library 경로 등 PyVISA가 지원하는 선택 방식을 사용합니다.
5. Timeout·EOI·terminator를 기록합니다. 초기 LF 후보가 실제 응답과 맞는지 확인합니다. 한 제품에서 맞는 LF/EOI 동작을 다른 어댑터에 일반화하지 않습니다.

실제 resource를 선택한 IDN-only 진단은 `*IDN?`만 전송하며 출력 상태는 `UNKNOWN`으로 기록합니다. 출력 OFF가 확인되었다는 의미가 아닙니다. 정확히 6517A가 아닌 모델에는 장비별 설정·출력 제어 명령을 보내지 않습니다.

Portable 패키지의 `Check-Connection.cmd`는 resource와 backend를 받아 이 IDN-only 진단을 수행합니다. 인수 없이 실행하면 library/resource 목록을 진단합니다. 어댑터나 library가 없으면 보고서에 실패 단계와 다음 확인 항목을 남기며 자동으로 출력 ON을 재시도하지 않습니다.

Portable 폴더에서는 다음과 같이 실행할 수 있습니다. 주소는 예시입니다.

```powershell
.\Check-Connection.cmd
.\Check-Connection.cmd "GPIB0::27::INSTR" "@ivi"
# 명시적인 보호 OFF 점검; 실제 현장 조건 확인 후 실행
.\Check-Output-Off.cmd "GPIB0::27::INSTR" "@ivi"
```

소스 실행 환경의 대응 명령:

```powershell
uv run --locked python -m keithley6517a.cli diagnose --report-dir diagnostics
uv run --locked python -m keithley6517a.cli diagnose --resource "GPIB0::27::INSTR" --backend "@ivi" --report-dir diagnostics
uv run --locked python -m keithley6517a.cli identify "GPIB0::27::INSTR" --backend "@ivi"
```

## 명시적 출력 OFF 점검

기본 진단과 다르게 `diagnose --confirm-off --resource ...`는 정확히 6517A로 식별한 뒤 보호 목적 OFF/abort를 요청하고 상태를 확인합니다. 전압 설정·출력 ON은 수행하지 않습니다. 이것도 방전 확인이 아니므로 residual state는 `UNVERIFIED`입니다. 자세한 사용 조건과 물리적 비교 기록은 [사용자 시험 안내](user_hardware_trial.md)를 따릅니다.

Portable의 `Run-CLI.cmd measure --config "configs\approved-current.json"` 또는 GUI를 사용합니다. 실장비 current 측정에는 실제 정격·실험 승인과 같은 연결에서의 출력 OFF/lid-open=0 → lid-closed=1 관찰, 별도 ARM·START가 필요합니다. 과거 JSON의 체크나 IDN-only 성공이 현재 실행 승인을 대신하지 않습니다. Native resistance 실장비 START는 지원하지 않습니다.

## 사용 가능한 경로와 사용하지 않는 경로

- VISA session은 단일 worker가 소유합니다. 한 query의 전체 응답이 끝나기 전 다른 query를 보내지 않습니다. 유한 timeout을 사용하며 출력 ON·전압 설정의 자동 재전송은 하지 않습니다.
- Resource lock을 지원하면 독점 lock을 요청합니다. 다른 장비 제어 프로그램과 동시에 사용하지 않습니다.
- Prologix 또는 가상 COM 방식 controller는 일반 VISA GPIB와 다르며 이 버전에서 지원하지 않습니다. `++` 명령을 6517A로 보내거나 serial port에 무작위 명령을 보내지 않습니다.
- `pyvisa-py` 설치가 GPIB driver 설치나 모든 USB-GPIB 호환성을 보장하지 않습니다. 실제 adapter/VISA가 없는 PC에서는 시뮬레이터를 사용합니다.

진단 보고서는 local JSON/raw I/O입니다. Program version·PC architecture·선택 library/resource·장비 serial 및 오류 정보가 포함될 수 있습니다. 자동 전송하지 않으며 공유 전 사용자가 내용을 검토합니다.

PyVISA 공식 문서: https://pyvisa.readthedocs.io/en/latest/introduction/communication.html
