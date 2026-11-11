# 검증 기록

검증 대상은 Python 3.12 Linux 소스 개발 환경, 매뉴얼 기반 parser/명령 profile, 시뮬레이터와 주입한 모의 VISA transport입니다. 실제 6517A·Windows·USB-GPIB adapter·외부 차단/방전/전압 모니터는 제공되지 않았습니다. 따라서 실장비 시험 통과나 1000 V 사용 안전성 인증을 선언하지 않습니다.

현재 설치하여 검사한 버전은 Python 3.12.14, PySide6-Essentials 6.12.0, pyqtgraph 0.14.0, PyVISA 1.16.2, numpy 2.5.4, pytest 9.2.0, pytest-qt 4.5.0, Ruff 0.17.4입니다. 재현 버전은 이 프로젝트의 `uv.lock`에 기록합니다. 이 버전 확인은 adapter driver나 VISA shared library의 설치·동작 검증이 아닙니다.

## v0.3.0 사용자 시험 배포 검증

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
