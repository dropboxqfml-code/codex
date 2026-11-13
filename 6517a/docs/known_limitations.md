# v0.9.0 구현 범위와 알려진 제한

v0.9.0은 남은 기본 기능을 통합한 시험판입니다. 사용자 시험 결과를 반영한 v1.0.0 정식 배포와 구분합니다.

제공된 6517A 매뉴얼 원문으로 명령·trigger·ASCII parser를 개발했습니다. 사용자 제공 기록에서 native NI-VISA 경로의 실제 6517A IDN과 보호 OFF 조회 `0`은 확인됐습니다. 실제 전압 인가·current 수집·인터록 차단·방전은 별도 검증 대상입니다. Windows 소프트웨어 실행과 실제 장비 결과는 [검증 기록](validation.md)에 구분합니다.

## 운용 방식과 실행 경계

| 방식 | 범위 | 필요한 실행 확인 |
|---|---|---|
| `operator_low_voltage` | Source 100 V 범위, **절대 10 V 이하** | 사용자 연결 관리 확인, software trip, residual 확인, resistive-limit 정책, 장비 OFF·interlock·readback·오류 상태 |
| `verified_fixture` | 장비·설정·입력 정격의 최솟값 이내 | 기존 정격·승인 기록, 현재 연결 OFF 상태 lid `0 → 1`, readback·오류 상태 |

사용자 관리 모드는 정격 문서·fixture ID·과거 lid 전이 이력을 필수 입력으로 요구하지 않습니다. 입력한 정격이 있으면 한도 계산에 반영하지만 프로그램이 정격·승인을 만들어 채우지는 않습니다. `fixture_installation_confirmed`를 사용자 관리 확인만으로 true로 바꾸지 않습니다. 실제 interlock 조회가 `1`이 아니거나 조회가 실패하면 두 방식 모두 출력 ON을 차단합니다. 매뉴얼 3-137에 따라 조회 `1`만으로 실제 케이블·인터록 설치가 증명되는 것은 아닙니다.

API 기본값과 기존 저장 설정은 검증 fixture 방식을 유지합니다. 새 GUI REAL 준비는 사용자 관리 저전압 방식·0 V·trip 미설정·미확인 상태에서 시작합니다. **측정 설정 적용**은 필수 실행 입력을 검사하고, 별도 **초안 적용**은 문법·수치가 유효한 미완성 입력을 보존합니다. 메인 화면은 누락 설정과 연결·ARM·START 단계를 구분해 안내합니다. 출력 OFF에서 **연결 종료 후 설정 수정**으로 돌아갈 수 있습니다. ARM은 운용 방식에 필요한 실행 입력과 실제 장비 상태를 다시 검사합니다. 설정 적용·불러오기·연결은 출력 ON이 아니며 ARM과 START는 별도입니다.

START 권한은 정확한 설정 snapshot과 연결에 묶여 한 번 소비됩니다. 설정 변경·재연결·fault 뒤에 setpoint·출력·수집을 자동 재개하지 않습니다. 실장비 `NATIVE_RESISTANCE`는 별도 측정 전류 기반 trip 채널이 없어 계속 차단합니다. 실측은 `FVMI_CURRENT`로 current를 읽고 V/I를 계산합니다.

기본 그래프 순서는 R(t) -> I(t) -> I-V -> R-V입니다. 시작 화면의 시뮬레이션은 가상 시험용이고 VISA · USB–GPIB는 장비 연결용입니다. 자동 시작 검사는 파일·소프트웨어 동작 범위이며 장비 측정 성능을 검증하지 않습니다.

## 기능 상태

| 기능 | 상태·범위 |
|---|---|
| 사용자 관리 저전압 current 시험 | 구현; 10 V/100 V-range 제한, 실제 장비 상태 검사와 별도 START |
| 검증 fixture current 시험 | 기존 구현; 정격·승인·현재 연결 lid 전이 조건 유지 |
| 1 GΩ·1 V preset | 명시적 클릭으로 시험값 입력; 운용 방식·REAL/SIM·확인 체크·정책은 자동 승인하지 않음 |
| 측정 설정 적용·초안 적용·설정 저장 | 필수값 검증과 초안 보존 구분; 연결·ARM·START와 분리 |
| 준비 상태·단계 안내 | 누락 항목과 다음 작업 표시, 연결 OFF 상태에서 종료 후 설정 수정 |
| 기본 화면·상세 탭 | 판독·그래프 중심 기본 화면; 고급 설정·진단·기록은 별도 탭 |
| 자동 시작 검사 | Start-GUI.cmd에서 Bundle → Simulation → GUI 자동 진행; 검사는 장비 연결 없이 수행 |
| Simulation 진행 표시 | 시작 창·CMD 및 `simulate --progress`에서 단계·판독·결과 경로 표시 |
| 예상 남은 시간·진행률 | dwell·전압 단계·반복 횟수 기준 예상치; 향후 통신·판독 지연과 종료 처리 시간은 불포함 |
| 여러 저장 결과 비교 | 공통 경과 시간 구간에서 I(t)·R(t)·ρ(t) 겹침; 활성 파일의 통계·선택 TXT |
| 분석 설정 저장·다시 열기 | 비교 목록·순서·구간·활성 파일·탭을 JSON으로 보존; 원본 경로·해시 확인 |
| 진단 ZIP 저장 | 최근 측정·연결 진단·시작 검사·GUI 로그를 로컬 ZIP으로 저장; 자동 전송 없음 |
| 분석용 TXT | 매 판독을 `analysis.txt`에 저장; 비저항 조건이 없으면 네 열, 완성되면 시간/R/ρ/V/I 다섯 열; 첫 행 물리량·단위, 이후 SI 수치·결측 `nan` |
| 시료 치수·비저항 | L/W/D(mm)와 전류 방향으로 직육면체 단면적·경로 길이를 환산; 완료된 기하조건에서만 겉보기 체적 비저항(Ω·m) 계산 |
| 이전 결과 변환 | `export-analysis`로 CSV를 장비 연결 없이 TXT로 변환; 기존 파일 덮어쓰기 없음 |
| 명령형 transport 시뮬레이터 | 매뉴얼 형식·seed·clock·fault 주입; `simulation_resistance_ohm` 모델값과 실제 VISA 판독 분리 |
| 정전압/list/staircase·cycles | Host-controlled step; 연속 ramp·자동 중간점·점진 ramp-down은 미구현 |
| Native 저항 판독 | 시뮬레이션만; native R와 역산 전류를 실제 measured current로 표시하지 않음 |
| Native VISA USB-GPIB | 해당 사용자 PC의 발견·IDN·보호 OFF 기록 확인; 전체 제품·driver 조합 인증은 아님 |
| NI-488.2 only `@py` | 선택 확장 필요; NI-VISA 생략 가능, NI-488.2는 계속 필요; 실제 조합 미시험 |
| SCPI/ASCII parser·freshness | 매뉴얼 fixture·소프트웨어 시험; 실제 전압 인가 뒤 reading-number·상태·단위 transcript는 별도 검증 |
| STOP·fault latch·저장 | 단일 I/O worker, 유한 timeout, 오류 시 OFF 시도 |
| 잔류 전압·하드웨어 emergency stop | 외부 장치 제어 미구현; residual은 UNVERIFIED |
| Background·geometry·bipolar | 명시적 값·가정이 필요한 선택 기능; 물리적 타당성 자동 검증 없음 |
| 안정화 통계 | 분석용; 자동 dwell 종료·연장·평형 인증은 아님 |
| Host polarity-pair·trace/test-sequence 수집 | 미구현; host one-shot을 사용 |
| 환경 센서·series-drop 자동 보정 | 기본 자동 측정·보정 없음; 수동 기록과 verified 값만 사용 |
| Prologix/serial controller | 미지원; 가상 COM·자동 `++` 전송 없음 |
| Windows portable ZIP | Python·locked wheels·CMD 포함; 새 위치 CLI/GUI·무결성 회귀를 배포 검사에 포함 |
| 단일 EXE·NI driver bundling | 미제작; NI 드라이버·native VISA runtime은 포함하지 않음 |

치수 기반 비저항은 전극이 전류 방향에 수직인 전체 단면을 덮는 직육면체 모델입니다. 전극 유효 면적이 더 작거나 원형·guard 전극을 사용하는 경우에는 해당 전극 기하조건을 사용해야 합니다. 치수와 방향이 일부만 있으면 저항 측정과 입력 기록은 유지하지만 비저항은 비웁니다. 새 치수·방향이 전혀 없을 때는 기존 `area_m2`·`thickness_m` 설정을 지원합니다. 시료 ID만 있거나 부분 치수·전류 방향 미지정이면 자동·선택 TXT는 시간/R/V/I 네 열입니다. 완성된 L/W/D·방향 또는 기존 면적·경로 길이가 있으면 시간/R/ρ/V/I 다섯 열을 사용합니다. `Resistivity (Ohm m)`는 SI 단위 Ω·m입니다. 실행 시작에 열 수를 고정하므로 완성된 기하조건에서 비저항 값이 전부 없는 0 V 실행도 다섯 열과 `nan`을 유지합니다.

## 측정·중지·데이터의 한계

`analysis.txt`는 요약 제외 행도 포함하는 수치 파일이며 품질 판정을 뜻하지 않습니다. 플래그·조건은 기존 CSV·JSON에서 확인합니다. 전압 열은 source 설정 readback이고 저항은 native 판독 또는 원시 V/I입니다. Native 모드의 누락된 원시 전류는 `nan`이며 역산 전류로 대체하지 않습니다.

1 GΩ preset의 1 V → 1 nA는 명목 계산입니다. 교정값·허용차·전압 계수·누설·settling과 실제 판독을 비교해야 하며 시뮬레이션 결과로 대체하지 않습니다. 가상 모델에는 absorption·offset·noise가 포함될 수 있습니다.

Software current trip은 sample cadence와 I/O 지연 뒤 동작하며 장비의 programmable compliance가 아닙니다. 2-49와 3-108의 internal resistive-limit 저항값 20 MΩ/1 MΩ 불일치는 보정 상수나 보호 보증치로 채택하지 않았습니다.

대기 중 STOP 확인은 0.05 s 단위, safety polling은 0.25 s 단위에 I/O 시간이 더해집니다. 여러 순차 query·OFF call이 각각 timeout을 소비할 수 있으므로 총 중지 시간이 timeout 한 번과 같지 않습니다. Adapter·OS 정지나 강제 종료의 차단을 소프트웨어가 보장하지 않습니다. 장비 status와 reading은 원자적 snapshot이 아닙니다.

출력 OFF, `SOUR:VOLT?`·VSO=0, 작은 전류·경과 시간은 독립 DUT 방전 측정이 아닙니다. residual은 UNVERIFIED를 유지합니다. Incomplete-run 복구는 활동 중인 run이 없는 폴더에서 명시적으로 수행하며 interrupted 기록만 만들고 전압·수집을 재개하지 않습니다.

## 남은 실제 시험

- 보유 firmware의 측정 설정·zero correction·range·filter/REL·one-shot trigger readback과 실제 current 응답.
- 전류 trip·source limit·STOP 지연·통신 단절·독립 차단·방전과 전압 회복.
- 기준저항·blank 결과, warm-up·교정·환경 조건과 판독 비교.
- `@py`의 Windows DLL 로드·실제 GPIB·timeout·resource lock 지원.

진단의 `ok`는 선택한 발견·IDN·보호 OFF 동작의 결과이며 전체 측정·물리적 보호 인증이 아닙니다. 진단/run 파일은 로컬에 저장하고 자동 전송하지 않습니다. Backend 오류 뒤 자동 전환·명령 재전송·출력 ON 재시도는 하지 않습니다.

## 배포와 선택 확장

v0.4.6부터 소스 기반 `__pycache__/*.pyc`를 manifest·ZIP에서 제외하고 진입점의 캐시 쓰기를 억제합니다. 소스·DLL·확장 모듈·stdlib ZIP·독립 bytecode는 계속 해시 검사합니다. 배포 게이트는 새 위치에서 CLI/GUI 실행, 캐시 재생성 후 PASS, 소스·DLL 변조 FAIL, 복원 후 PASS를 확인합니다.

기본 ZIP에는 NI driver·native VISA·선택 `@py` 패키지가 포함되지 않습니다. 선택 installer는 명시적 INSTALL 후 hash-pinned pure wheel만 설치하고, 기존 불완전·변경된 확장 폴더를 덮어쓰지 않습니다. 해당 확장을 포함한 배포본의 라이선스 조건은 별도 검토하며 app·NI driver 라이선스를 자동 변경하지 않습니다.


## v0.9.0 저장 결과 분석 범위

저장 결과 분석은 최대 64개 실행의 `readings.csv` 또는 해당 폴더를 읽어 I(t)·R(t)·ρ(t)를 겹쳐 표시합니다. 각 실행의 시작 후 경과 시간을 공통 축으로 사용하며 보간·시간 이동·정규화를 하지 않습니다. 전체 구간은 모든 파일의 시간 범위를 포함합니다. 선택한 공통 구간에서 활성 파일의 통계와 선택 TXT를 제공하며 서로 다른 파일의 행을 한 TXT로 합치지 않습니다. 분석은 저장값·품질 플래그를 사용하며 원본 결과를 수정하지 않습니다.

구간의 저항 산술평균은 자동 실행 요약의 V/mean(I)와 다릅니다. 비저항은 CSV의 저장값만 분석하며 저장값이 없을 때 새로 계산하지 않습니다. v0.8.2 CSV에 저장된 비저항은 그대로 분석·다섯 열 TXT 내보내기가 가능합니다. 단일 값의 표본 표준편차는 계산하지 않으며, 오류 판독은 통계 개수에서 제외합니다. STOP으로 끝난 실행에서도 원시 판독 전체는 기존 CSV·자동 TXT에 남고 완료하지 않은 단계의 요약은 생성하지 않습니다.

분석 설정 JSON은 원본 데이터를 내장하지 않습니다. 목록·순서·적용 시간 구간·활성 파일·탭과 원본 확인 정보를 저장합니다. 세션 파일 기준 상대 경로를 사용하고 Windows의 다른 드라이브 파일은 절대 경로를 사용합니다. CSV 및 `metadata.json`·`config.json`·`run_status.json`의 존재 여부와 SHA-256을 확인하므로 원본이 없거나 저장 시점과 달라지면 명확한 오류를 표시합니다. 같은 파일 구조를 함께 옮기면 다시 열 수 있습니다. 기록 중인 파일을 기준으로 설정을 저장하면 이후 판독 추가로 확인 값이 달라질 수 있으므로 종료된 결과를 사용합니다. 변경된 원본을 분석하려면 결과를 다시 선택해 새 설정으로 저장합니다. 다시 열기는 현재 분석 화면만 바꾸며 측정 설정이나 장비 세션을 만들지 않습니다.

예상 남은 시간과 진행률은 계획한 dwell을 기준으로 표시합니다. 실제 통신·판독 지연, 아직 실행하지 않은 장비 명령과 종료 처리 시간은 정확히 예측하지 않습니다. 종료 처리 중·STOP·오류 상태는 따로 표시하며 예상 0초를 출력 OFF 확인으로 사용하지 않습니다.

진단 ZIP은 선택된 최근 기록과 GUI 로그를 로컬에 보관하는 기능입니다. 프로그램·드라이버 전체나 모든 과거 run을 백업하지 않으며 원본 파일이 누락되거나 크기 상한을 넘으면 `manifest.json`에 이유를 남깁니다. 수집 상한은 파일당 64 MiB·자료 합계 128 MiB이며 GUI 로그는 최근 1 MiB를 보관합니다. 시료 정보·장비 일련번호·로컬 경로·통신 원문을 포함할 수 있고 자동 업로드하지 않습니다. 측정·준비 작업 중과 ARMED 상태에서는 사용할 수 없고, ZIP 저장은 장비 조회·보호 OFF 시험을 새로 실행하지 않습니다.
