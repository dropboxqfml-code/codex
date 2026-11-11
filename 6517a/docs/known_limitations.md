# 구현 범위와 알려진 제한

제공된 6517A 매뉴얼 원문을 사용해 명령과 parser를 개발했습니다. 실제 6517A·USB-GPIB adapter·시료·fixture는 개발 환경에 제공되지 않았습니다. 사용자는 v0.3.0 화면 실행과 NI MAX의 6517A 인식을 확인했지만, 이 프로그램의 실제 IDN/측정 성공 기록은 아직 전달되지 않았습니다. 매뉴얼 대조와 모의 transport 시험은 실제 출력 차단·방전 또는 1000 V 사용 안전성의 인증이 아닙니다.

## 매뉴얼 확인과 실장비 실행 승인의 차이

이전 단계의 매뉴얼 웹 요청은 403으로 실패했지만 사용자가 첨부한 `6517A_900_01C.pdf`(내부 6517A-900-01 Rev. D, May 2003)를 확인하여 그 장애는 해결됐습니다. [명령표](scpi_reference.md)에 파일 SHA-256과 실제 인쇄 쪽수, 쓰기/조회·상태 변경·예상 응답·실장비 미시험 여부를 기록했습니다. 예전 provisional simulator profile의 layer 1 delay와 `RDNG#` 응답 suffix를 원문과 맞게 수정했습니다.

실장비 `FVMI_CURRENT`에는 정확한 6517A 모델 식별과 출력 OFF 확인, 실제 정격·실험 승인, 설치된 interlock의 현재 연결에서의 출력 OFF/lid-open=0 → lid-closed=1 관찰, 설정 readback·오류 queue 검사, 별도 ARM·START가 필요합니다. 과거 JSON의 `commissioning` 체크만으로 현재 연결을 승인하지 않습니다. 재연결·fixture 변경·fault 후에는 새 확인과 사용자 승인이 필요하며 자동 ON·setpoint replay·측정 재개는 하지 않습니다.

출력 ON 승인은 한 번 소비되며 구성이나 연결 변경 후 재사용하지 않습니다. 이 소프트웨어 절차는 실제 인터록 접점·정격·물리적 차단 기능의 독립 검증을 대체하지 않습니다. 실제 commissioning 결과와 firmware transcript는 [기록지](commissioning_checklist.md)에 보존해야 합니다.

현재 연결에서 0 → 1 전이를 관찰해도 **이후 케이블이 계속 연결돼 있다는 증명은 아닙니다**. 3-137에 따라 케이블을 나중에 분리해도 `SYST:INT?`가 1을 반환할 수 있어 소프트웨어가 모든 분리 사건을 검출할 수 없습니다. 승인된 fixture의 케이블 고정·접근 관리와 독립적인 하드웨어 보호가 필요하며, 현재 연결 관찰을 하드웨어 인증이나 연속 감시 보증으로 해석하지 않습니다.

실장비 `NATIVE_RESISTANCE`에서는 raw current를 신뢰할 수 있는 별도 원문 명령으로 동시에 취득하는 경로를 구현하지 않았습니다. V/R의 역산 전류만으로 software trip 보호를 보장하지 않으므로 실장비 native 출력은 계속 비활성화합니다.

## 기능 상태

| 기능 | 상태 | 범위·제한 |
|---|---|---|
| 명령형 transport 시뮬레이터 | 구현 | 매뉴얼 형식·seed·clock·fault 주입; transcript에 simulation 명시 |
| Constant bias/list/staircase·cycles | 구현 | host-controlled step; 실제 timing 성능 미시험 |
| 연속 ramp·자동 중간 전압·점진적 ramp-down | 미구현 | 명시한 voltage-list만 실행; 종료 immediate_off |
| FVMI_CURRENT | 구현 | 시뮬레이션 및 승인 조건을 갖춘 VISA 경로; 실제 장비 미시험 |
| NATIVE_RESISTANCE | 시뮬레이션만 | native R/inferred current 분리; 실장비 current trip 문제로 ON 차단 |
| Native VISA USB-GPIB (`@ivi`/기본값) | 구현 | adapter driver/VISA runtime 필요; 실제 제품별 동작 미시험 |
| NI-488.2 only (`@py`) | 선택 확장이 필요한 실험적 경로 | 기본 ZIP에 PyVISA-py/gpib-ctypes 미설치; 사용자 선택 설치 후 NI-VISA 생략 가능하나 NI-488.2 driver/64-bit DLL 필요; 실제 NI 조합 미시험 |
| 원문 기반 SCPI/ASCII parser | 구현·소프트웨어 시험 | manual-derived fixture; 실제 수집 transcript 미제공 |
| ARM/START·one-use ON 승인·현재 연결 interlock 확인 | 구현 | 원문 확인과 물리적 commissioning은 구분 |
| STOP·fault latch·자동 저장 | 구현 | 단일 I/O worker·유한 timeout; 강제 종료에는 하드웨어 보호 필요 |
| 잔류 전압 독립 확인 | 미구현 | 외부 장치 미제공; 항상 UNVERIFIED |
| Hardware emergency stop/watchdog | 미구현 | 존재하지 않는 기능을 가정하지 않음 |
| Background subtraction·geometry 분석 | 명시적 설정만 허용 | 출처·승인 필수; 물리적 타당성 자동 검증 안 함 |
| 안정화 통계 | 분석용 | 자동 dwell 종료/연장·평형 인증 아님 |
| Bipolar | 기본 OFF | 음전압 명시 승인 필요; 내장 polarity sequence와 다름 |
| Host polarity pair 분석 | 미구현 | 실제 시료 선형·시간불변·대칭 가정 별도 검토 |
| Prologix/serial controller | 미구현 | serial 자동 탐색·++ 명령 전송 없음 |
| 장비 trace buffer/test sequence 수집 | 미구현 | host one-shot만 수집; 기존 autonomous 동작은 takeover/stop에서 중단 |
| 환경 센서 | 미구현 | 온도/RH는 수동·null; 장비 기본 센서로 간주하지 않음 |
| Windows x64 portable 시험 ZIP | 구현 | 포함 runtime·locked Windows wheels·CMD launcher; native Windows/실장비 실행은 별도 검증 |
| 단일 파일 Windows EXE/설치 프로그램 | 미제작 | portable ZIP과 구분; adapter/VISA driver는 별도 설치 |
| 사용자 연결 안내·진단·설정 폼 | 구현 | 기본 SIM 정상 상태 안내, 명시적 REAL 선택, IDN-only/OFF 분리; 진단 성공은 측정 승인 아님 |

## 남은 실제 시험

- 보유 6517A firmware별 ASCII 표현·고정 요소 순서·단위·status/sentinel·reading number·VSO와 실제 freshness.
- 실제 adapter EOI/terminator·resource lock·timeout/cancellation·통신 단절과 보호 OFF 동작.
- Manual source·모든 readback·zero correction range 유효성·filter/REL·one-shot trigger 설정.
- current trip 감지와 software stop 지연, source current limit, 독립 차단·실제 방전·전압 회복.
- 기준저항/blank fixture 결과와 실제 warm-up·교정·환경 조건.
- 해당 사용자 PC의 프로그램 실제 IDN·출력 OFF·측정 기록과 사용할 adapter/driver/firmware 조합.
- NI-VISA를 생략한 `@py` backend의 Windows x64 DLL 로드·GPIB 동작·실제 timeout과 resource lock 지원.

2-49와 3-108의 resistive-limit 저항값 20 MΩ/1 MΩ 불일치는 원문에서도 확인됐으며 보정 상수나 보호 보증치로 하드코딩하지 않았습니다. Source current limit는 programmable nA/µA compliance가 아닙니다.

## 중지와 데이터의 한계

대기 중 STOP 확인은 0.05 s 단위, safety polling은 0.25 s 단위에 I/O 시간이 더해집니다. 전류 trip 감지는 sample cadence와 I/O 지연에 제한됩니다. 하나의 VISA call뿐 아니라 순차 status query 묶음과 OFF 절차의 여러 call 각각이 timeout을 소비할 수 있으므로 총 stop 지연은 timeout 한 번과 같지 않습니다. Adapter/OS가 멈추거나 프로세스가 강제 종료되는 상황을 소프트웨어가 차단한다고 보장하지 않습니다. 실제 지연 상한은 장비·어댑터를 포함해 별도 측정해야 합니다.

출력 OFF는 잔류 전압 0의 증명이 아닙니다. `SOUR:VOLT?`와 VSO는 독립 DUT 전압 측정이 아니며, VSO=0·작은 전류·경과 시간으로 접촉 가능 여부를 판정하지 않습니다. 잔류 전압 상태는 `UNVERIFIED`를 유지합니다. Incomplete-run 복구는 활동 중인 run이 없는 directory에서 명시적 `cli recover DIRECTORY`로만 수행하고 전압을 재인가하지 않습니다.

## 시험 배포본의 범위

Windows x64 portable 패키지는 관리형 CPython runtime과 `uv.lock`의 Windows wheel을 포함하는 시험 배포 형태입니다. 사용자 PC에 Python·uv를 별도로 설치할 필요가 없지만 어댑터 제조사 driver와 NI GPIB DLL은 포함하지 않습니다. 기본 native VISA의 호환 runtime도 포함하지 않습니다. `@py`에 필요한 Python 패키지는 기본 ZIP에 사전 설치하지 않으며 선택 확장으로 사용자 PC에 설치합니다. 그 경로 역시 NI-488.2 driver를 요구합니다. 배포본 제작 시 TLS·다운로드 해시·wheel tag·파일 manifest를 확인하고, 그 결과를 [검증 기록](validation.md)에 남깁니다. 이 정적 구성 검사는 Native Windows에서 GUI/DLL/VISA library를 실제 로드했다는 증거가 아닙니다.

진단은 resource 열거·IDN-only 또는 명시적으로 선택한 OFF 점검으로 구분합니다. OFF 점검에서도 출력 ON이나 전압 설정을 하지 않습니다. `ok`나 IDN 성공은 실제 측정·인터록·독립 차단·방전의 종합 검증을 뜻하지 않습니다. 진단 보고서·raw I/O는 로컬 저장만 하며 사용자 검토 없이 전송하지 않습니다.

시험 설정 대화상자의 정격·승인·trip 필드는 사용자가 확인한 실제 값이 필요합니다. 프로그램이 기본값이나 예제를 근거로 시료 정격을 채우지 않습니다. 저장된 체크 기록은 현재 연결의 interlock 관찰을 대체하지 않으며, 폼 적용은 연결/ARM/START가 아닙니다.

이전 v0.2.0 설정 파일도 실장비 ARM 전에 `commissioning.hardware_protection_reviewed=true`를 독립 하드웨어 보호 검토 후 명시해야 합니다. 설정 load나 버전 변경으로 자동 승인하지 않습니다.


## Backend 선택의 한계

NI MAX에서 인식되는 현재 PC에서는 우선 기존 native VISA 경로를 사용합니다. `@py`는 사용자가 NI-VISA를 생략하기 위해 명시적으로 선택하는 실험적 대안입니다. 기본값/빈 backend도 `@ivi`로 고정하므로 선택 확장을 설치했다는 이유로 자동 선택되지 않습니다. 두 backend 사이에서 전압 설정이나 출력 ON을 자동 재시도하지 않습니다. Backend/resource 변경 또는 재연결 후에는 이전 연결의 commissioning과 START 승인을 재사용하지 않습니다.

NI-488.2의 지원 timeout 단계 때문에 요청값과 실제 적용값이 다를 수 있습니다. 실제 적용 timeout이 보고돼도 전체 STOP 지연을 보증하지는 않습니다. 다른 제어 프로그램과 NI MAX test panel을 닫고, 인터록·독립적인 차단·방전 수단을 사용하는 조건은 backend와 무관하게 유지합니다.

선택 확장 installer는 안내와 라이선스 확인 후 사용자가 `INSTALL`을 입력한 경우에만 hash-pinned wheel을 인터넷에서 설치합니다. `extensions/ni4882`의 기존 내용은 덮어쓰지 않으며 불완전한 설치를 성공으로 활성화하지 않습니다. 확장이 추가된 배포본의 재배포 조건은 상위 라이선스를 별도로 검토해야 하며 앱·NI driver의 라이선스를 자동으로 변경하지 않습니다.
