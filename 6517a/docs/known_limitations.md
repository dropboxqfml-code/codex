# v0.7.0 구현 범위와 알려진 제한

제공된 6517A 매뉴얼 원문으로 명령·trigger·ASCII parser를 개발했습니다. 사용자 제공 기록에서 native NI-VISA 경로의 실제 6517A IDN과 보호 OFF 조회 `0`은 확인됐습니다. 실제 전압 인가·current 수집·인터록 차단·방전은 별도 검증 대상입니다. Windows 소프트웨어 실행과 실제 장비 결과는 [검증 기록](validation.md)에 구분합니다.

## 운용 방식과 실행 경계

| 방식 | 범위 | 필요한 실행 확인 |
|---|---|---|
| `operator_low_voltage` | Source 100 V 범위, **절대 10 V 이하** | 사용자 연결 관리 확인, software trip, residual 확인, resistive-limit 정책, 장비 OFF·interlock·readback·오류 상태 |
| `verified_fixture` | 장비·설정·입력 정격의 최솟값 이내 | 기존 정격·승인 기록, 현재 연결 OFF 상태 lid `0 → 1`, readback·오류 상태 |

사용자 관리 모드는 정격 문서·fixture ID·과거 lid 전이 이력을 필수 입력으로 요구하지 않습니다. 입력한 정격이 있으면 한도 계산에 반영하지만 프로그램이 정격·승인을 만들어 채우지는 않습니다. `fixture_installation_confirmed`를 사용자 관리 확인만으로 true로 바꾸지 않습니다. 실제 interlock 조회가 `1`이 아니거나 조회가 실패하면 두 방식 모두 출력 ON을 차단합니다. 매뉴얼 3-137에 따라 조회 `1`만으로 실제 케이블·인터록 설치가 증명되는 것은 아닙니다.

API 기본값과 기존 저장 설정은 검증 fixture 방식을 유지합니다. 새 GUI REAL 준비는 사용자 관리 저전압 방식·0 V·trip 미설정·미확인 상태에서 시작합니다. **측정 설정 적용**은 필수 실행 입력을 검사하고, 별도 **초안 적용**은 문법·수치가 유효한 미완성 입력을 보존합니다. 메인 화면은 누락 설정과 연결·ARM·START 단계를 구분해 안내합니다. 출력 OFF에서 **연결 종료 후 설정 수정**으로 돌아갈 수 있습니다. ARM은 운용 방식에 필요한 실행 입력과 실제 장비 상태를 다시 검사합니다. 설정 적용·불러오기·연결은 출력 ON이 아니며 ARM과 START는 별도입니다.

START 권한은 정확한 설정 snapshot과 연결에 묶여 한 번 소비됩니다. 설정 변경·재연결·fault 뒤에 setpoint·출력·수집을 자동 재개하지 않습니다. 실장비 `NATIVE_RESISTANCE`는 별도 측정 전류 기반 trip 채널이 없어 계속 차단합니다. 실측은 `FVMI_CURRENT`로 current를 읽고 V/I를 계산합니다.

## 기능 상태

| 기능 | 상태·범위 |
|---|---|
| 사용자 관리 저전압 current 시험 | 구현; 10 V/100 V-range 제한, 실제 장비 상태 검사와 별도 START |
| 검증 fixture current 시험 | 기존 구현; 정격·승인·현재 연결 lid 전이 조건 유지 |
| 1 GΩ·1 V preset | 명시적 클릭으로 시험값 입력; 운용 방식·REAL/SIM·확인 체크·정책은 자동 승인하지 않음 |
| 측정 설정 적용·초안 적용·설정 저장 | 필수값 검증과 초안 보존 구분; 연결·ARM·START와 분리 |
| 준비 상태·단계 안내 | 누락 항목과 다음 작업 표시, 연결 OFF 상태에서 종료 후 설정 수정 |
| 기본 화면·상세 탭 | 판독·그래프 중심 기본 화면; 고급 설정·진단·기록은 별도 탭 |
| Simulation 진행 표시 | CMD 및 `simulate --progress`에서 단계·판독·결과 경로 표시 |
| 분석용 TXT | 매 판독을 `analysis.txt` 네 열로 자동 저장; 첫 행 물리량·단위, 이후 SI 수치·결측 `nan` |
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
