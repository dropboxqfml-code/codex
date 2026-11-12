# 측정·분석 규칙

## 설정과 실행

설정 JSON의 기본 숫자는 SI 단위를 사용하며 `sample_length_mm`, `sample_width_mm`, `sample_depth_mm`는 이름대로 mm 단위입니다. NaN/Infinity, 음수·0 시간, 잘못된 전압 방향과 point 수, 0 이하 두께·면적·입력 치수를 오류로 처리합니다. 상한과 시간 계획은 ARM에서 검증하고 immutable snapshot으로 고정합니다. 변경하려면 중지 후 다시 ARM합니다. `current_trip_A`와 잔류 전하 경고 확인은 예제 시뮬레이션에서도 명시합니다.

입력 예제는 설정 필드를 최상위에 둔 flat JSON입니다. 실행 폴더의 `config.json`은 `schema_version`·`software`·`settings` wrapper로 저장하며 software version·Git commit·dirty 상태·`source_sha256`을 함께 기록합니다. `RunConfig.load`와 GUI/CLI 설정 load는 두 형식을 모두 지원하므로 저장된 승인 snapshot을 다시 검토·불러올 수 있습니다. load만으로 연결·출력·측정을 재개하지 않습니다. Git commit은 당시 저장소 HEAD이며 미커밋 구현의 실제 소스 구분에는 dirty 상태와 source fingerprint도 함께 확인하세요.

정전압은 `voltages` 한 개, list sweep는 여러 전압을 지정합니다. 선형 staircase 생성 도우미는 시작·종료·step 방향과 마지막 점을 검증합니다. `cycles`는 같은 계획의 반복을 구분합니다. `dwell_s`, `min_dwell_s`, `exclude_initial_s`, `summary_window_s`, `range_settle_s`는 별도 설정입니다. 기본 정전압 예시는 dwell 300 s·마지막 30 s 요약이며, 짧은 시뮬레이션 예제는 실행 편의를 위한 가상 값입니다. 특정 1 s/60 s 대기만으로 실제 시료 안정화가 보장되지 않습니다.

실제 수집 계획은 `voltages`에 명시한 각 점 사이의 step입니다. 자동으로 중간 전압을 삽입하는 연속 ramp나 점진적 ramp-down은 구현하지 않았습니다. 작은 전압 간격이 필요하면 승인된 점들을 명시적으로 생성·검토하세요. 별도의 smooth-ramp 설정 항목은 없으며 지원하지 않는 JSON 필드는 오류로 처리합니다. 종료 정책은 `immediate_off`입니다.

`sample_interval_s`는 희망 간격입니다. NPLC/f_line은 적분 시간의 추정치이며 전체 sample interval이 아닙니다. autorange, filter, autozero, 통신 overhead가 추가됩니다. monotonic 읽기 시작·끝, 실제 경과 시간, 전압 명령 이후 시간을 데이터에 기록합니다. 전압 명령 시각은 독립 측정한 DUT 전압 상승 에지가 아닙니다. 긴 dwell 중에도 샘플과 상태를 수집하며 stop을 확인합니다.

대기 중 stop event는 0.05 s 단위로 확인하고 safety 상태는 0.25 s 단위와 I/O 소요 시간으로 polling합니다. Software current trip은 전류 sample cadence와 I/O 지연에 영향을 받습니다. 이미 진행 중인 하나의 I/O뿐 아니라 한 묶음의 상태 query와 protective OFF 절차의 각 call에도 timeout이 적용될 수 있으므로, 총 stop 시간은 timeout 한 번과 같지 않습니다. Timeout은 소프트웨어 I/O 대기의 제한이며 어댑터·OS 정지나 실제 출력 차단의 보증이 아닙니다. 이는 Linux fake-clock/모의 transport에서 검증한 구현 동작이며 실장비 지연 상한이나 실제 보호 성능을 보장하지 않습니다.

## 데이터의 의미

`FVMI_CURRENT`에서 `current_raw_A`는 설정 NPLC/filter를 통과한 장비 판독의 원문 수치입니다. 무처리 ADC raw data가 아닙니다. `voltage_programmed_readback_V`는 source 설정값 조회이며 DUT 양단 전압 측정이 아닙니다. `resistance_apparent_ohm=V_programmed/I_raw`는 해당 배선의 겉보기 저항입니다. `native_r_ohm`에는 값을 채우지 않습니다.

`NATIVE_RESISTANCE`는 Manual V-Source·normal resistance의 장비 저항 판독을 `native_r_ohm`에 저장합니다. 추가 전류를 동시에 얻는 원문 명령이 확인되지 않았으므로 `current_raw_A`는 null입니다. `current_inferred_A=V/R`는 역산값으로 별도 저장합니다. 실장비 native 모드는 역산값만으로 software current trip을 보장할 수 없어 차단됩니다.

0 V에서 저항은 null입니다. 0 A나 noise floor 이하에서 저항을 0 Ω·정확한 큰 값으로 저장하지 않고 `NOT_RESOLVED`로 구분합니다. 음전류·음저항은 부호를 보존합니다. 그래프는 음수를 버리지 않는 signed linear/symlog 방식을 사용합니다. overflow/underflow/zero-check/reference/out-of-limit는 유효 평균에서 제외하지만 raw sample을 삭제하지 않습니다.

source current limit이면 실제 DUT 전압이 설정 전압이라는 전제가 깨집니다. 해당 점의 V/I를 유효 저항으로 보고하지 않고 abort합니다. source current limit query 실패를 false로 바꾸지 않습니다. 인터록·limit 상태 query는 판독과 동시인 원자적 snapshot이 아니므로 query 시각을 별도로 기록합니다.

## 제외 구간과 요약

전압 변경 직후 자료는 transient/settling, 지정 window는 acquiring으로 구분합니다. Current range가 바뀌면 range-change event와 추가 제외 구간을 적용합니다. 실제 전환 시점은 알 수 없으므로 관련 구간의 불확실성을 표시합니다. 샘플이 summary에 포함되는지 여부는 `valid_for_summary`와 `quality_flags`로 확인합니다.

일정 전압에서 대표 저항은 `V/mean(I_corrected)`입니다. `mean(V/I_i)`와 동일하지 않습니다. I mean·median·standard deviation·min/max·N·slope·실제 window를 보존합니다. 시간상관을 무시한 s/sqrt(N)을 보장하거나 근거 없는 총 불확도를 생성하지 않습니다.

안정화 통계는 같은 range의 원시 유효 sample에 적용합니다. 최소 dwell·sample 수, 상대 drift/scatter와 절대 기준을 따로 설정합니다. `STABLE`은 선택한 통계 기준을 통과했다는 뜻이며 intrinsic DC conduction의 증명이 아닙니다. `NOT_STABLE`, `NOT_RESOLVED`, 유효 자료 부족을 구분합니다. 이 버전은 dwell 계획을 임의로 자동 연장하거나 안정 판정만으로 측정을 조기 종료하지 않습니다.

## 보정과 해석

기본은 background subtraction을 하지 않습니다. 사용 시 `background_approved`, `background_reference`와 동일 전압·시간·환경·배선에서 검증한 background를 명시합니다. 0 V 전류를 유한 전압 fixture leakage로 자동 대체하지 않습니다. 보정 전 raw current와 보정값을 따로 보존합니다.

직렬저항·burden·누설 경로가 확인되지 않았으므로 자동 series-drop 보정은 하지 않으며 `SERIES_DROP_UNVERIFIED`를 남깁니다. 6517A internal resistive-limit의 상충된 값 중 하나를 선택하지 않습니다. Geometry를 명시한 경우에만 `ρ=R×A/ℓ`를 계산하며 겉보기 체적 비저항입니다. 표면 전류·접촉이 분리되지 않았으면 intrinsic bulk resistivity로 단정하지 않습니다.

직육면체 치수 L/W/D를 mm로 기록하고 `current_path_axis`를 L/W/D 중에서 선택합니다. L 방향은 `A=W×D, ℓ=L`, W 방향은 `A=L×D, ℓ=W`, D 방향은 `A=L×W, ℓ=D`입니다. 면적에는 `10⁻⁶`, 길이에는 `10⁻³`을 곱해 m²·m로 환산합니다. 세 치수와 전류 방향이 모두 있어야 새 비저항을 계산하며, 일부만 입력된 경우에는 치수 기록과 저항 측정을 유지하고 비저항은 비웁니다.

이 모델은 전극이 해당 단면 전체를 덮는 경우입니다. 실제 유효 접촉 면적이 다르거나 원형 전극·guard 전극을 사용하면 해당 전극 기하조건을 사용해야 합니다. 기존 `area_m2`·`thickness_m` 입력은 새 치수·방향이 전혀 없는 설정에서 계속 지원하며, 새 치수가 일부라도 있으면 기존 기하조건으로 조용히 대체하지 않습니다.

FVMI 비저항은 기존 보정 저항 `resistance_corrected_ohm`, native 모드에서는 `native_r_ohm`을 기반으로 계산합니다. 계산할 저항이 없거나 유한한 결과를 표현할 수 없으면 `resistivity_ohm_m`을 비웁니다. mm 입력과 방향, SI 환산값은 저장 설정·metadata에서 추적합니다. 자동·선택 구간 `analysis.txt`의 시간/R/V/I 네 열에는 비저항 열을 추가하지 않습니다.

전압 인가 후 전류에는 conduction 외에도 충전·흡수·polarization·fixture leakage·offset·noise가 포함될 수 있습니다. 시뮬레이터의 `V/R + sum(A*exp(-t/tau)) + offset + drift*t + noise`는 시험 모델이며 실제 시료 physics 검증이 아닙니다. raw I(t)와 이력을 우선 해석하세요.

## 파일과 복구

고유 run 폴더마다 설정 snapshot과 장비 식별·simulation truth를 보존합니다. `readings.csv`는 SI 열과 손실 없는 raw response를 CSV 인코딩합니다. strict JSON에서 비유한 수는 쓰지 않습니다. 샘플별 flush, 중요 event 즉시 기록, atomic status 갱신을 사용합니다. 저장 실패는 OFF를 시도하고 중지합니다. 중단된 run은 명시적인 `cli recover DIRECTORY`로 `interrupted`로 표시하며 자동 재인가·재개하지 않습니다. 복구는 해당 directory에 활동 중인 run이 없는 것을 확인한 후 실행하세요. 다른 프로세스의 실행 중 상태를 복구 대상으로 변경하지 마세요.

`analysis.txt`는 분석 도구로 바로 가져올 수 있는 탭 구분 파일입니다. 첫 행은 `Time (s)`, `Resistance (Ohm)`, `Voltage (V)`, `Current (A)`이고 다음 행부터 네 개의 수치만 기록합니다. 다음 열을 같은 순서로 내보냅니다.

| TXT 열 | 원본 값 |
|---|---|
| Time (s) | `elapsed_s`: 측정 시작 후 경과 시간 |
| Resistance (Ohm) | `native_r_ohm`이 있으면 해당 값, 그 외 `resistance_apparent_ohm` |
| Voltage (V) | `voltage_programmed_readback_V`: source 설정 readback |
| Current (A) | `current_raw_A`: 원시 판독 전류 |

SI 단위·부호·0·저장 정밀도를 유지하며 누락값은 숫자형 결측 표기인 `nan`으로 채웁니다. Native 모드의 역산 전류를 원시 전류 대신 넣지 않습니다. 전압 열은 시료 단자 전압의 독립 실측값이 아닙니다. `valid_for_summary`로 행을 거르지 않으므로 과도·제외·STOP 전 자료도 CSV와 같은 순서로 보존합니다. 이 파일에는 품질 플래그나 추가 메타데이터를 넣지 않으며 해석 시 기존 CSV·JSON을 함께 확인합니다.

파일은 ARM 시 준비하고 각 판독마다 기록·flush·fsync합니다. TXT 저장 실패도 수집 실패로 전달해 OFF 처리를 진행합니다. 완료·STOP 때 데이터를 한꺼번에 생성하는 방식이 아니므로 이미 저장한 행은 남습니다. 이전 CSV는 `export-analysis readings.csv [--output output.txt]`로 장비 연결 없이 변환할 수 있으며 원본과 기존 출력 파일을 덮어쓰지 않습니다.


## 저장 결과의 선택 구간 분석

오프라인 분석은 `readings.csv`의 저장값을 읽습니다. 시작·끝 경과 시간은 양 끝을 포함하며 원본 행 순서를 유지합니다. `valid_for_summary=false`만으로 판독을 버리지 않으므로 자동 요약 시간 창 이전 자료도 선택할 수 있습니다. 오류 상태·비정상 판독·안전 관련 오류 플래그는 통계에서 제외하고 유효 개수를 표시합니다. 원시 행은 선택 TXT에서 보존합니다.

표시 저항은 native 값이 있으면 그 값이고 그 외에는 저장된 겉보기 V/I입니다. 선택 구간의 저항 평균은 개별 저항 판독의 산술평균이며 실행 요약의 `V/mean(I)`와 별개입니다. 표준편차는 표본 표준편차(n−1)이며 유효 값 0개는 평균·표준편차 없음, 1개는 평균만 표시합니다. 임의의 smoothing·보정이나 안정 판정은 추가하지 않습니다.

선택 TXT는 자동 `analysis.txt`와 같은 헤더·네 열을 사용합니다. 선택한 원시 행의 결측·부호·정밀도를 보존하고 원본과 기존 출력 파일을 덮어쓰지 않습니다.

사용자 STOP은 OFF 확인·저장 완료 뒤 `stopped`로 확정합니다. OFF 미확인·장비/통신·저장 실패는 `aborted`/FAULT 또는 HV_STATE_UNKNOWN으로 남으며 사용자 중지로 숨기지 않습니다. 중간 STOP으로 완료하지 못한 전압 단계의 요약을 임의로 만들지 않습니다.
