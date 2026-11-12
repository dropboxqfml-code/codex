# Windows 64-bit와 USB-GPIB / VISA

v0.5.0에서는 NI-VISA/NI-488.2 연결 경로를 그대로 사용하며 사용자 관리 저전압 시험 모드를 선택할 수 있습니다. 새 모드의 연결·정격은 사용자가 관리하고 프로그램은 최대 10 V와 장비 상태·오류 처리를 적용합니다. 측정 순서는 [사용자 시험 안내](user_hardware_trial.md)를 따릅니다.

## 실행 방법 선택

사용자 시험에는 Windows x64 portable ZIP을 사용합니다. 포함된 Python 3.12.14와 잠금 버전의 Windows 의존성을 사용하므로 Python·uv를 별도로 설치하지 않습니다. ZIP을 완전히 푼 뒤 `Verify-Bundle.cmd`로 내부 파일을 검사하고 `Start-GUI.cmd`로 기본 SIMULATION 화면을 시작합니다. `Test-Simulation.cmd`는 실장비 없이 기능을 확인하는 실행 경로입니다. 자세한 순서는 [사용자 시험 안내](user_hardware_trial.md)에 있습니다.

소스 개발자는 Python 3.12 64-bit와 uv를 준비하고 프로젝트 폴더에서 `uv sync --locked`, `uv run --locked python -m keithley6517a`를 실행합니다. 이 방법은 portable 배포본의 사용자 실행 조건과 구분합니다.

**NI-488.2 장치 driver와 NI GPIB DLL은 배포 ZIP에 포함되지 않습니다.** 기본 native VISA 경로의 VISA runtime도 별도이며, 호환되는 기존 설치를 사용할 수 있습니다. 선택 가능한 `@py` 대안은 NI-VISA를 요구하지 않지만 NI-488.2 driver를 여전히 요구합니다. 어댑터 제조사의 설치 안내를 따릅니다. Windows 10/11 64-bit가 대상이며, 현재 소스 개발 검증은 제공된 Linux 환경에서 수행합니다. 이전 v0.3.0 GitHub Release CI의 Windows 236개 시험·native 번들 smoke 통과와 사용자 PC의 GUI 실행 확인은 실제 NI 통신 시험과 구분합니다. 배포 파일·wheel tag·해시 검사와 실제 Windows GUI/어댑터 실행 검증은 [검증 기록](validation.md)에 따로 기록합니다.

## 실제 USB-GPIB 설치 확인

1. 사용자는 **NI MAX에서 6517A가 보인다**고 확인했습니다. 현재 설치를 바로 바꾸기보다 그 GPIB board·주소와 정확한 어댑터 모델(HS/HS+ 등)을 기록합니다. 기본 경로는 해당 모델과 Windows 버전에 맞는 **NI-488.2 및 NI-VISA 64-bit**를 사용하며 이미 호환되는 설치가 있으면 재설치하지 않습니다. 정확한 모델/driver 조합은 아직 제공되지 않았으므로 그 조합의 동작을 시험 완료로 표시하지 않습니다. 다른 어댑터는 해당 제조사의 Windows x64 driver와 VISA를 사용합니다. Python `PyVISA`만으로 모든 어댑터가 작동하지 않습니다. 프로그램·VISA library·driver의 bitness가 호환되는지도 확인합니다.
2. NI MAX에서 adapter board와 장비 GPIB 주소를 확인합니다. `GPIB0::27::INSTR`는 형식 예시일 뿐 고정 주소가 아닙니다. 6517A는 USBTMC 장비가 아니므로 `USB::...` resource를 기대하지 않습니다.
3. 장비 전면에서 GPIB 주소와 SCPI language를 확인합니다. legacy DDC와 SCPI를 혼용하지 않습니다. 제조사 도구로 확인한 후 NI MAX·Connection Expert·별도 제어 스크립트를 닫습니다.
4. GUI 연결 안내의 ‘NI 실장비 연결 시험 시작 (출력 ON 없음)’을 선택하고 VISA backend/library와 resource 조회 또는 진단을 사용해 model·serial·firmware를 확인합니다. 실장비 모드 선택 자체는 I/O나 출력 ON이 아닙니다. 환경에 따라 기본 library, `@ivi`, 명시적 library 경로 등 PyVISA가 지원하는 선택 방식을 사용합니다.
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

## NI-VISA를 생략하는 선택 경로

v0.5.0 기본 ZIP에는 다음 대체 Python 패키지를 사전 설치하지 않습니다. 사용자가 NI-VISA를 생략하는 대안을 선택한 경우에만 선택 확장으로 설치합니다. 정확한 버전과 해시는 `uv.lock` 및 선택 확장 요구사항에 기록합니다.

- PyVISA-py 0.8.1: `@py` backend.
- gpib-ctypes 0.3.0: 기존 NI/Linux GPIB C API의 Python binding.

Portable 사용자는 GUI를 닫고 `Enable-NI-Only.cmd`를 명시적으로 실행합니다. 안내와 상위 라이선스를 확인한 뒤 `INSTALL`을 입력하면 `app/ni-only-requirements.txt`의 해시로 고정한 두 Python wheel을 인터넷에서 받아 `extensions/ni4882`에 설치합니다. 장비 I/O나 NI driver 설치는 하지 않습니다. 설치 성공 뒤 GUI를 다시 시작하고 `@py`를 명시적으로 선택합니다. 소스 개발 환경에서는 `uv sync --locked --extra ni-only`를 사용합니다. 기본 native VISA 시험에는 이 선택 확장이 필요하지 않습니다. `@py` 선택만으로 설치를 시작하지 않습니다. 완료 표식·버전·파일 해시가 맞는 기존 설치는 재사용합니다. 불완전하거나 변경된 확장 폴더는 덮어쓰지 않으며 중단된 설치는 성공으로 활성화하지 않습니다. 이미 존재하거나 불완전한 폴더 오류가 나면 프로그램을 닫은 뒤 그 폴더와 installer 기록을 보존하고 검토합니다. 사용자 PC에서 확장을 설치한 배포본을 다시 배포하려면 상위 라이선스 조건을 별도로 확인해야 하며, 이 설치가 앱이나 NI driver의 라이선스를 변경하지 않습니다.

| 선택 | 필요한 사용자 PC 구성 | 지원 범위 |
|---|---|---|
| 기본값 또는 `@ivi` | NI-488.2 + 호환 NI-VISA 64-bit | NI MAX에서 인식되는 현재 PC의 첫 시험에 권장 |
| `@py` — NI-488.2 only · experimental | 선택 Python 확장 + NI-488.2 + Windows Python과 맞는 GPIB DLL | NI-VISA 생략 가능; 실제 NI 어댑터 동작 미검증 |
| 임의 VISA library 경로 | 해당 library와 어댑터 driver | 경로·bitness를 사용자가 확인 |

`@py`는 NI GPIB-USB를 generic USBTMC 장치로 취급하지 않습니다. NI-488.2를 제거하거나 driver 없이 USB 장치를 직접 제어하는 경로도 아닙니다. Windows에서는 `gpib-32.dll` 또는 `ni4882.dll` 같은 NI library를 현재 Python 프로세스가 로드할 수 있어야 합니다. `gpib-32.dll`의 파일명만으로 32/64-bit 호환 여부를 판단하지 않습니다. 이 패키지의 Python은 64-bit이므로 맞는 NI driver/DLL이 필요합니다. DLL을 다른 PC나 임의 배포본에서 복사해 해결하도록 안내하지 않습니다.

기본값/빈 backend는 `@ivi`로 명시적으로 고정합니다. 선택 확장을 설치했어도 NI-VISA 누락을 이유로 `@py`를 자동 선택하지 않습니다.

이 경로는 driver import·binding의 실제 준비 상태를 사전 검사합니다. Missing driver, 잘못된 DLL bitness, 사용 불가 API를 성공이나 빈 정상 데이터로 바꾸지 않습니다. 기본 VISA에서 실패했다고 자동으로 `@py`로 바꾸거나, 오류가 난 전압/ON 명령을 새 backend에 재전송하지 않습니다. Backend를 바꾸려면 먼저 연결을 종료하고 새로 선택·진단합니다.

```powershell
.\Check-Connection.cmd "실제 GPIB resource" "@py"
# IDN-only 시험과 현장 조건 확인 뒤 별도로 요청하는 OFF 점검
.\Check-Output-Off.cmd "실제 GPIB resource" "@py"
```

소스 실행에서는 동일하게 `diagnose --backend "@py" --resource "실제 GPIB resource"`를 사용합니다. NI-488.2의 timeout은 정해진 단계로 적용되므로 요청 2,000 ms가 실제 3,000 ms로 반올림될 수 있습니다. 보고서에 기록된 요청값·실제 적용값을 구분하고 총 software stop 지연은 실제 장비에서 별도로 확인합니다. `@py`의 resource lock 지원도 native VISA와 같다고 가정하지 말고 다른 제어 프로그램을 닫습니다.

근거: [PyVISA-py 설치 문서](https://github.com/pyvisa/pyvisa-py/blob/main/docs/source/installation.rst), [gpib-ctypes 프로젝트](https://pypi.org/project/gpib-ctypes/). 선택 의존성의 설치 지원과 mock 시험은 실제 Windows x64·NI 어댑터 조합의 검증을 대신하지 않습니다.

## 명시적 출력 OFF 점검

기본 진단과 다르게 `diagnose --confirm-off --resource ...`는 정확히 6517A로 식별한 뒤 보호 목적 OFF/abort를 요청하고 상태를 확인합니다. 전압 설정·출력 ON은 수행하지 않습니다. 이것도 방전 확인이 아니므로 residual state는 `UNVERIFIED`입니다. 자세한 사용 조건과 물리적 비교 기록은 [사용자 시험 안내](user_hardware_trial.md)를 따릅니다.

Portable의 `Run-CLI.cmd measure --config "configs\approved-current.json"` 또는 GUI를 사용합니다. 실장비 current 측정에는 실제 정격·실험 승인과 같은 연결에서의 출력 OFF/lid-open=0 → lid-closed=1 관찰, 별도 ARM·START가 필요합니다. 과거 JSON의 체크나 IDN-only 성공이 현재 실행 승인을 대신하지 않습니다. Native resistance 실장비 START는 지원하지 않습니다.

## 사용 가능한 경로와 사용하지 않는 경로

- VISA session은 단일 worker가 소유합니다. 한 query의 전체 응답이 끝나기 전 다른 query를 보내지 않습니다. 유한 timeout을 사용하며 출력 ON·전압 설정의 자동 재전송은 하지 않습니다.
- Resource lock을 지원하면 독점 lock을 요청합니다. 다른 장비 제어 프로그램과 동시에 사용하지 않습니다.
- Prologix 또는 가상 COM 방식 controller는 일반 VISA GPIB와 다르며 이 버전에서 지원하지 않습니다. `++` 명령을 6517A로 보내거나 serial port에 무작위 명령을 보내지 않습니다.
- 선택 확장의 `pyvisa-py`/gpib-ctypes도 GPIB driver 설치나 모든 USB-GPIB 호환성을 보장하지 않습니다. 실제 adapter/driver가 없는 PC에서는 시뮬레이터를 사용합니다.

진단 보고서는 local JSON/raw I/O입니다. Program version·PC architecture·선택 library/resource·장비 serial 및 오류 정보가 포함될 수 있습니다. 자동 전송하지 않으며 공유 전 사용자가 내용을 검토합니다.

PyVISA 공식 문서: https://pyvisa.readthedocs.io/en/latest/introduction/communication.html
