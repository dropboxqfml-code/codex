# 요구사항 추적과 acceptance 범위

v0.5.0은 기존 `verified_fixture` 경로에 더해 명시적 사용자 확인을 사용하는 `operator_low_voltage` 경로를 제공합니다. 사용자 관리 모드는 최대 10 V·100 V source range이며, 물리 fixture 문서·lid 0→1 기록을 요구하는 아래 항목은 `verified_fixture`에 적용합니다. 두 경로 모두 실제 장비 인터록·limit·출력 상태 검사, 별도 ARM/START, STOP/OFF, 원시 기록을 유지합니다. 새 운용 경로 검증은 `test_operator_mode.py`, `test_operator_runner.py`, `test_operator_ui_flow.py`와 설정 창 시험에 있습니다.

업로드 요구사항 16절의 번호를 유지합니다. 아래는 구현·시험의 추적표이며, 실제 실행 결과는 [검증 기록](validation.md)에 기록합니다. 자동 시험은 명시적으로 주입한 transport/clock/fault에 대한 소프트웨어 검증입니다. 장비 원문 확인·실장비 시험을 대체하지 않습니다.

| 번호 | 요구사항·검증할 동작 | 대표 자동 시험의 실제 이름 |
|---|---|---|
| 1 | 시작/연결/재연결/load만으로 ON 없음 | `test_explicit_arm_start_and_no_on_for_load_connect_shutdown`, `test_startup_and_config_load_never_connect_or_output_on` |
| 2 | 다른 모델 식별 시 제어 명령 전 차단 | `test_wrong_model_gets_no_control_writes` |
| 3 | ARM 전 START, 상한, NaN/Inf, geometry/time 차단 | `test_invalid_inputs`, `test_ceiling_quantization_and_positive_only`, `test_explicit_arm_start_and_no_on_for_load_connect_shutdown` |
| 4 | Manual V-Source와 설정 readback 유지 | `test_manual_vsource_and_current_autorange_independent`, `test_readback_clamp_is_not_accepted` |
| 5 | current autorange와 Auto V-Source 독립 | `test_manual_vsource_and_current_autorange_independent` |
| 6 | interlock=1만으로 commissioning 대체 불가 | `test_interlock_one_cable_absent_cannot_arm`, `test_config_flags_and_interlock_one_cannot_replace_connection_observations`, `test_query_one_and_saved_history_cannot_replace_live_commissioning` |
| 7 | interlock/readback/limit/trip 이후 전압 증가 없음 | `test_fault_aborts_no_later_voltage_and_best_effort_off`, `test_software_trip_invalidates_sample_and_no_voltage_increase`, `test_readback_clamp_is_not_accepted` |
| 8 | STOP/timeout/exception/disk/GUI close에서 OFF 시도 | `test_stop_long_wait_uses_virtual_time_and_does_not_raise_voltage`, `test_disk_failure_during_sample_aborts`, `test_single_worker_owns_io_close_requests_stop_before_shutdown` |
| 9 | OFF 실패에는 UNKNOWN, OFF 성공에도 잔류 UNVERIFIED | `test_usb_disconnect_keeps_hv_unknown_and_physical_source_may_remain_on`, `test_complete_streaming_artifacts_unique_runs_and_strict_roundtrip` |
| 10 | retry/reconnect에 ON/setpoint replay 없음 | `test_no_retries_after_timeout`, `test_startup_identify_configure_never_enable_output` |
| 11 | ASCII value/unit/status/sentinel parser | `test_manual_selected_element_order_and_attached_status_unit`, `test_manual_status_and_sentinel_values_never_become_normal_numbers`, `test_unconfigured_or_corrupt_tokens_are_not_guessed`; **원문 fixture 검증, 실제 장비 transcript 미시험** |
| 12 | 0 V/0 A/음전류/floor/overflow/underflow/REL 분리 | `test_signed_resistance_and_floor`, `test_status_is_not_normal_current`, `test_status_is_not_a_valid_measurement` |
| 13 | one-shot READ와 RNUM 기반 freshness | `test_stale_data_aborts_instead_of_becoming_new_sample`, `test_manual_profile_has_no_fictitious_arm_layer_one_delay`; 원문 trigger 경로 확인, 실제 trigger 미시험 |
| 14 | 실제 read 시작/끝·interval 기록 | `test_slow_conversion_actual_interval_is_not_requested_interval` |
| 15 | range change 이후 제외·settling | `test_range_change_and_initial_settle_kept_but_excluded` |
| 16 | stable와 resolution 분리, invalid 평균 제외·raw 보존 | `test_stability_and_resolution_remain_distinct_and_need_new_windows`, `test_summary_uses_mean_current_and_excludes_invalid_without_deletion` |
| 17 | mean(I) 저항/native R/inferred current 필드 구분 | `test_native_mode_has_no_measured_current_and_separate_native_summary`, `test_summary_uses_mean_current_and_excludes_invalid_without_deletion` |
| 18 | 미확인 series-drop 자동 보정 없음 | `test_sentinel_source_limit_and_unverified_series` |
| 19 | CSV round-trip/strict JSON/flush/incomplete 복구 | `test_incremental_csv_preserves_response_commas_newline_and_signed_values`, `test_strict_json_never_encodes_nan_inf`, `test_recover_incomplete_never_resumes_or_claims_off` |
| 20 | fake clock의 긴 dwell 중 stop 처리 | `test_stop_long_wait_uses_virtual_time_and_does_not_raise_voltage` |
| 21 | abort/logging 등 예외와 독립적인 OFF 시도 | `test_error_in_logging_and_abort_does_not_prevent_off`, `test_off_failure_and_abort_cancel_exceptions_never_skip_off` |
| 22 | GUI 외 CLI/direct call도 같은 ARM/START 정책 | `test_explicit_arm_start_and_no_on_for_load_connect_shutdown`, `test_cli_requires_typed_start_after_off_only_observations`, `test_start_requires_one_use_authorization_even_after_configure` |
| 23 | 기본 positive-only, bipolar 승인 없으면 음전압 금지 | `test_ceiling_quantization_and_positive_only` |
| 24 | transcript의 simulation 표시·실장비 미수행 명시 | `test_complete_streaming_artifacts_unique_runs_and_strict_roundtrip` + 본 문서의 미수행 기록 |

첨부된 6517A 원문 Figure 3-19와 3-77~78 설명을 반영한 parser fixture와 실제 명령 경로 테스트를 제공합니다. Fixture는 원문에서 구성한 합성 자료이며 실제 수집 transcript가 아닙니다. 실장비 설정·trigger acceptance, 실제 timing·USB-GPIB 단절·native Windows 동작은 미수행입니다. 실장비 current 출력은 현재 연결에서의 interlock 관찰·정격/실험 승인·ARM·one-use START에 의해 제한되며, 실장비 native 출력은 측정 전류 보호 미검증으로 계속 차단됩니다.

자동 시험은 다음 파일에서 확인할 수 있습니다. Parameterized case도 실제 실행한 경우에만 통과 수에 포함합니다.

- [`test_config_analysis.py`](../tests/test_config_analysis.py): 설정 경계·strict JSON·immutable snapshot·positive-only·부호/floor/status·mean-current 저항·안정/분해능·geometry.
- [`test_driver.py`](../tests/test_driver.py): 무출력 연결·모델 차단·Manual source·readback·one-shot freshness·취소/abort/log 예외와 독립적인 OFF·UNKNOWN·승인 없는 real enable 차단·parser.
- [`test_runner_storage.py`](../tests/test_runner_storage.py): 상태 머신·run loop·safety fault·중지·실제 시각·range exclusion·CSV/JSON/flush·복구·저장 오류·직접 API 정책.
- [`test_parser_manual.py`](../tests/test_parser_manual.py): Figure 3-19의 요소 순서·status/unit·`rdg#`·standby VSO·sentinel·손상 token·지원하지 않는 layer 1 delay 거부.
- [`test_instrument_manual.py`](../tests/test_instrument_manual.py): 원문 명령 profile·일회 START 승인·snapshot·현재 연결의 interlock 관찰·native 실장비 차단.
- [`test_real_workflow.py`](../tests/test_real_workflow.py): 실제 장비가 아닌 모의 transport를 VISA 경로로 주입하여 interlock 승인·current run·고장·CLI 명시 입력을 검사.
- [`test_ui.py`](../tests/test_ui.py): 자동 연결/ON 없음·worker 소유·close stop·signed-log·stale timestamp.

체적 비저항·background·bipolar 등 선택 기능은 설정·가정이 명시된 범위만 제공합니다. hardware interlock·enclosure·실제 차단·방전의 독립 시험은 [commissioning 기록지](commissioning_checklist.md)로 별도 관리합니다.
