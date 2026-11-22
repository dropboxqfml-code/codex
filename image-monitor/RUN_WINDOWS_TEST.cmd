@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
if errorlevel 1 exit /b 1
set "TEST_BROWSER=edge"
set "RECOVER_CLOSED=0"
set "UV_LOOKUP_ONLY=0"
set "READ_ONLY_INSPECTION=0"
set "READ_ONLY_LIST_INSPECTION=0"
set "WATCH_TEST=0"
set "CANDIDATE_TEST=0"
set "CANDIDATE_SAVE_TEST=0"
set "CANDIDATE_FINISH=0"
set "MONITOR=0"
set "MONITOR_SAVE_TEST=0"
set "MONITOR_FINISH=0"
set "MONITOR_SAVE_BATCH=0"
set "MONITOR_BATCH_FINISH=0"
set "SAVE_POST=0"
set "RESUME_PREINPUT=0"
set "POST_SAVE_RESUME_ARGUMENT="
set "CHECK_LABEL=Windows native-save test"
set "MONITOR_DIAGNOSIS=0"
set "TEST_LIST_RECOVERY=0"
set "WATCH_DETAIL=0"
set "WATCH_IMAGES=0"
set "WATCH_IMAGES_CHECK=0"
set "MONITOR_RESUME_ONCE=0"
set "AUTO_COLLECT_ONCE=0"
set "AUTO_MONITOR=0"
set "AUTO_MONITOR_LIMIT="
if /i "%~1"=="--auto-monitor" goto auto_monitor_arguments
if /i "%~1"=="--test-auto-monitor" goto auto_monitor_arguments
if /i "%~1"=="--auto-collect-once" goto auto_collect_arguments
if /i "%~1"=="--monitor-resume-once" goto monitor_resume_arguments
if /i "%~1"=="--watch-images-check" goto watch_images_check_arguments
if /i "%~1"=="--watch-images" goto watch_images_arguments
if /i "%~1"=="--watch-detail" goto watch_detail_arguments
if /i "%~1"=="--monitor-diagnosis" goto diagnosis_arguments
if /i "%~1"=="--test-list-recovery" goto list_recovery_arguments

:parse_arguments
if "%~1"=="" goto arguments_ready
if /i "%~1"=="--chrome" goto option_chrome
if /i "%~1"=="--recover-closed" goto option_recover
if /i "%~1"=="--find-uv" goto option_lookup
if /i "%~1"=="--site-inspect" goto option_site_inspection
if /i "%~1"=="--list-inspect" goto option_list_inspection
if /i "%~1"=="--watch-test" goto option_watch_test
if /i "%~1"=="--candidate-test" goto option_candidate_test
if /i "%~1"=="--candidate-save-test" goto option_candidate_save_test
if /i "%~1"=="--candidate-finish" goto option_candidate_finish
if /i "%~1"=="--monitor" goto option_monitor
if /i "%~1"=="--monitor-save-test" goto option_monitor_save_test
if /i "%~1"=="--monitor-finish" goto option_monitor_finish
if /i "%~1"=="--monitor-save-batch" goto option_monitor_save_batch
if /i "%~1"=="--monitor-batch-finish" goto option_monitor_batch_finish
if /i "%~1"=="--save-post" goto option_save_post
if /i "%~1"=="--resume-preinput" goto option_resume_preinput
>&2 echo Unsupported test launcher argument. Use the supplied CMD files.
exit /b 2

:auto_monitor_arguments
if not "%~2"=="" exit /b 2
set "CHECK_LABEL=continuous automatic image monitoring"
if /i "%~1"=="--test-auto-monitor" set "CHECK_LABEL=automatic image monitoring for two cycles"
if /i "%~1"=="--test-auto-monitor" set "AUTO_MONITOR_LIMIT=--max-cycles 2"
set "AUTO_MONITOR=1"
set "WATCH_RESULT=AUTO_MONITOR"
set "WATCH_EXIT_CODE="
goto new_log

:auto_collect_arguments
if not "%~2"=="" exit /b 2
set "CHECK_LABEL=automatic collection for one post"
set "AUTO_COLLECT_ONCE=1"
set "WATCH_RESULT=AUTO_COLLECT_ONCE"
set "WATCH_EXIT_CODE="
goto new_log

:monitor_resume_arguments
if not "%~2"=="" exit /b 2
set "CHECK_LABEL=resume pending monitor detail"
set "MONITOR_RESUME_ONCE=1"
set "WATCH_RESULT=MONITOR_RESUME_ONCE"
set "WATCH_EXIT_CODE="
goto new_log

:watch_images_check_arguments
if not "%~2"=="" exit /b 2
set "CHECK_LABEL=verify last saved recent images"
set "WATCH_IMAGES_CHECK=1"
set "WATCH_RESULT=WATCH_IMAGES_CHECK"
set "WATCH_EXIT_CODE="
goto new_log

:watch_images_arguments
if not "%~2"=="" exit /b 2
set "CHECK_LABEL=recent watch images"
set "WATCH_IMAGES=1"
set "WATCH_RESULT=WATCH_IMAGES"
set "WATCH_EXIT_CODE="
goto new_log

:watch_detail_arguments
if not "%~2"=="" exit /b 2
set "CHECK_LABEL=watch candidate detail"
set "WATCH_DETAIL=1"
set "WATCH_RESULT=WATCH_DETAIL"
set "WATCH_EXIT_CODE="
goto new_log

:list_recovery_arguments
if not "%~2"=="" exit /b 2
set "CHECK_LABEL=list recovery test"
set "TEST_LIST_RECOVERY=1"
set "WATCH_RESULT=TEST_LIST_RECOVERY"
set "WATCH_EXIT_CODE="
goto new_log

:diagnosis_arguments
if not "%~2"=="" exit /b 2
set "CHECK_LABEL=stored list diagnosis"
set "MONITOR_DIAGNOSIS=1"
goto new_log

:option_chrome
set "TEST_BROWSER=chrome"
shift
goto parse_arguments

:option_recover
set "RECOVER_CLOSED=1"
shift
goto parse_arguments

:option_lookup
set "UV_LOOKUP_ONLY=1"
shift
goto parse_arguments

:option_site_inspection
set "READ_ONLY_INSPECTION=1"
set "CHECK_LABEL=read-only site inspection"
shift
goto parse_arguments

:option_list_inspection
set "READ_ONLY_LIST_INSPECTION=1"
set "CHECK_LABEL=read-only list search inspection"
shift
goto parse_arguments

:option_watch_test
set "WATCH_TEST=1"
set "CHECK_LABEL=bounded list-watch trial"
shift
goto parse_arguments

:option_candidate_test
set "CANDIDATE_TEST=1"
set "CHECK_LABEL=bounded candidate-detail inspection"
shift
goto parse_arguments

:option_candidate_save_test
set "CANDIDATE_SAVE_TEST=1"
set "CHECK_LABEL=reviewed candidate native-save test"
shift
goto parse_arguments

:option_candidate_finish
set "CANDIDATE_FINISH=1"
set "CHECK_LABEL=completed candidate file verification"
shift
goto parse_arguments

:option_monitor
set "MONITOR=1"
set "CHECK_LABEL=continuous list monitor"
shift
goto parse_arguments

:option_monitor_save_test
set "MONITOR_SAVE_TEST=1"
set "CHECK_LABEL=monitor candidate native-save test"
shift
goto parse_arguments

:option_monitor_finish
set "MONITOR_FINISH=1"
set "CHECK_LABEL=completed monitor candidate verification"
shift
goto parse_arguments

:option_monitor_save_batch
set "MONITOR_SAVE_BATCH=1"
set "CHECK_LABEL=bounded monitor candidate batch save"
shift
goto parse_arguments

:option_monitor_batch_finish
set "MONITOR_BATCH_FINISH=1"
set "CHECK_LABEL=completed monitor batch verification"
shift
goto parse_arguments

:option_save_post
set "SAVE_POST=1"
set "CHECK_LABEL=single-post native-save test"
shift
goto parse_arguments

:option_resume_preinput
set "RESUME_PREINPUT=1"
set "POST_SAVE_RESUME_ARGUMENT=--resume-preinput"
shift
goto parse_arguments

:arguments_ready
if "%UV_LOOKUP_ONLY%"=="1" goto lookup_only
if "%MONITOR_SAVE_BATCH%"=="1" if "%MONITOR%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_SAVE_BATCH%"=="1" if "%MONITOR_SAVE_TEST%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_SAVE_BATCH%"=="1" if "%MONITOR_FINISH%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_SAVE_BATCH%"=="1" if "%CANDIDATE_FINISH%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_SAVE_BATCH%"=="1" if "%CANDIDATE_SAVE_TEST%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_SAVE_BATCH%"=="1" if "%CANDIDATE_TEST%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_SAVE_BATCH%"=="1" if "%WATCH_TEST%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_SAVE_BATCH%"=="1" if "%READ_ONLY_INSPECTION%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_SAVE_BATCH%"=="1" if "%READ_ONLY_LIST_INSPECTION%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_SAVE_BATCH%"=="1" if "%SAVE_POST%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_SAVE_BATCH%"=="1" if "%RECOVER_CLOSED%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_SAVE_BATCH%"=="1" if "%RESUME_PREINPUT%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_SAVE_BATCH%"=="1" if "%MONITOR_BATCH_FINISH%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_BATCH_FINISH%"=="1" if "%MONITOR%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_BATCH_FINISH%"=="1" if "%MONITOR_SAVE_TEST%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_BATCH_FINISH%"=="1" if "%MONITOR_FINISH%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_BATCH_FINISH%"=="1" if "%CANDIDATE_FINISH%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_BATCH_FINISH%"=="1" if "%CANDIDATE_SAVE_TEST%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_BATCH_FINISH%"=="1" if "%CANDIDATE_TEST%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_BATCH_FINISH%"=="1" if "%WATCH_TEST%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_BATCH_FINISH%"=="1" if "%READ_ONLY_INSPECTION%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_BATCH_FINISH%"=="1" if "%READ_ONLY_LIST_INSPECTION%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_BATCH_FINISH%"=="1" if "%SAVE_POST%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_BATCH_FINISH%"=="1" if "%RECOVER_CLOSED%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_BATCH_FINISH%"=="1" if "%RESUME_PREINPUT%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_BATCH_FINISH%"=="1" if "%MONITOR_SAVE_BATCH%"=="1" goto incompatible_monitor_batch_modes
if "%MONITOR_SAVE_BATCH%"=="1" if /i not "%TEST_BROWSER%"=="chrome" goto unsupported_monitor_batch_browser
if "%MONITOR_SAVE_TEST%"=="1" if "%MONITOR_FINISH%"=="1" goto incompatible_monitor_save_modes
if "%MONITOR_SAVE_TEST%"=="1" if "%MONITOR%"=="1" goto incompatible_monitor_save_modes
if "%MONITOR_SAVE_TEST%"=="1" if "%CANDIDATE_FINISH%"=="1" goto incompatible_monitor_save_modes
if "%MONITOR_SAVE_TEST%"=="1" if "%CANDIDATE_SAVE_TEST%"=="1" goto incompatible_monitor_save_modes
if "%MONITOR_SAVE_TEST%"=="1" if "%CANDIDATE_TEST%"=="1" goto incompatible_monitor_save_modes
if "%MONITOR_SAVE_TEST%"=="1" if "%WATCH_TEST%"=="1" goto incompatible_monitor_save_modes
if "%MONITOR_SAVE_TEST%"=="1" if "%READ_ONLY_INSPECTION%"=="1" goto incompatible_monitor_save_modes
if "%MONITOR_SAVE_TEST%"=="1" if "%READ_ONLY_LIST_INSPECTION%"=="1" goto incompatible_monitor_save_modes
if "%MONITOR_SAVE_TEST%"=="1" if "%SAVE_POST%"=="1" goto incompatible_monitor_save_modes
if "%MONITOR_SAVE_TEST%"=="1" if "%RECOVER_CLOSED%"=="1" goto incompatible_monitor_save_modes
if "%MONITOR_SAVE_TEST%"=="1" if "%RESUME_PREINPUT%"=="1" goto incompatible_monitor_save_modes
if "%MONITOR_FINISH%"=="1" if "%MONITOR_SAVE_TEST%"=="1" goto incompatible_monitor_finish_modes
if "%MONITOR_FINISH%"=="1" if "%MONITOR%"=="1" goto incompatible_monitor_finish_modes
if "%MONITOR_FINISH%"=="1" if "%CANDIDATE_FINISH%"=="1" goto incompatible_monitor_finish_modes
if "%MONITOR_FINISH%"=="1" if "%CANDIDATE_SAVE_TEST%"=="1" goto incompatible_monitor_finish_modes
if "%MONITOR_FINISH%"=="1" if "%CANDIDATE_TEST%"=="1" goto incompatible_monitor_finish_modes
if "%MONITOR_FINISH%"=="1" if "%WATCH_TEST%"=="1" goto incompatible_monitor_finish_modes
if "%MONITOR_FINISH%"=="1" if "%READ_ONLY_INSPECTION%"=="1" goto incompatible_monitor_finish_modes
if "%MONITOR_FINISH%"=="1" if "%READ_ONLY_LIST_INSPECTION%"=="1" goto incompatible_monitor_finish_modes
if "%MONITOR_FINISH%"=="1" if "%SAVE_POST%"=="1" goto incompatible_monitor_finish_modes
if "%MONITOR_FINISH%"=="1" if "%RECOVER_CLOSED%"=="1" goto incompatible_monitor_finish_modes
if "%MONITOR_FINISH%"=="1" if "%RESUME_PREINPUT%"=="1" goto incompatible_monitor_finish_modes
if "%MONITOR_SAVE_TEST%"=="1" if /i not "%TEST_BROWSER%"=="chrome" goto unsupported_monitor_save_browser
if "%MONITOR%"=="1" if "%CANDIDATE_FINISH%"=="1" goto incompatible_monitor_modes
if "%MONITOR%"=="1" if "%CANDIDATE_SAVE_TEST%"=="1" goto incompatible_monitor_modes
if "%MONITOR%"=="1" if "%CANDIDATE_TEST%"=="1" goto incompatible_monitor_modes
if "%MONITOR%"=="1" if "%WATCH_TEST%"=="1" goto incompatible_monitor_modes
if "%MONITOR%"=="1" if "%READ_ONLY_INSPECTION%"=="1" goto incompatible_monitor_modes
if "%MONITOR%"=="1" if "%READ_ONLY_LIST_INSPECTION%"=="1" goto incompatible_monitor_modes
if "%MONITOR%"=="1" if "%SAVE_POST%"=="1" goto incompatible_monitor_modes
if "%MONITOR%"=="1" if "%RECOVER_CLOSED%"=="1" goto incompatible_monitor_modes
if "%MONITOR%"=="1" if "%RESUME_PREINPUT%"=="1" goto incompatible_monitor_modes
if "%MONITOR%"=="1" if /i not "%TEST_BROWSER%"=="chrome" goto unsupported_monitor_browser
if "%CANDIDATE_FINISH%"=="1" if "%CANDIDATE_SAVE_TEST%"=="1" goto incompatible_candidate_finish_modes
if "%CANDIDATE_FINISH%"=="1" if "%CANDIDATE_TEST%"=="1" goto incompatible_candidate_finish_modes
if "%CANDIDATE_FINISH%"=="1" if "%WATCH_TEST%"=="1" goto incompatible_candidate_finish_modes
if "%CANDIDATE_FINISH%"=="1" if "%READ_ONLY_INSPECTION%"=="1" goto incompatible_candidate_finish_modes
if "%CANDIDATE_FINISH%"=="1" if "%READ_ONLY_LIST_INSPECTION%"=="1" goto incompatible_candidate_finish_modes
if "%CANDIDATE_FINISH%"=="1" if "%SAVE_POST%"=="1" goto incompatible_candidate_finish_modes
if "%CANDIDATE_FINISH%"=="1" if "%RECOVER_CLOSED%"=="1" goto incompatible_candidate_finish_modes
if "%CANDIDATE_FINISH%"=="1" if "%RESUME_PREINPUT%"=="1" goto incompatible_candidate_finish_modes
if "%CANDIDATE_SAVE_TEST%"=="1" if "%CANDIDATE_TEST%"=="1" goto incompatible_candidate_save_modes
if "%CANDIDATE_SAVE_TEST%"=="1" if "%WATCH_TEST%"=="1" goto incompatible_candidate_save_modes
if "%CANDIDATE_SAVE_TEST%"=="1" if "%READ_ONLY_INSPECTION%"=="1" goto incompatible_candidate_save_modes
if "%CANDIDATE_SAVE_TEST%"=="1" if "%READ_ONLY_LIST_INSPECTION%"=="1" goto incompatible_candidate_save_modes
if "%CANDIDATE_SAVE_TEST%"=="1" if "%SAVE_POST%"=="1" goto incompatible_candidate_save_modes
if "%CANDIDATE_SAVE_TEST%"=="1" if "%RECOVER_CLOSED%"=="1" goto incompatible_candidate_save_modes
if "%CANDIDATE_SAVE_TEST%"=="1" if "%RESUME_PREINPUT%"=="1" goto incompatible_candidate_save_modes
if "%CANDIDATE_SAVE_TEST%"=="1" if /i not "%TEST_BROWSER%"=="chrome" goto unsupported_candidate_save_browser
if "%CANDIDATE_TEST%"=="1" if "%WATCH_TEST%"=="1" goto incompatible_candidate_modes
if "%CANDIDATE_TEST%"=="1" if "%READ_ONLY_INSPECTION%"=="1" goto incompatible_candidate_modes
if "%CANDIDATE_TEST%"=="1" if "%READ_ONLY_LIST_INSPECTION%"=="1" goto incompatible_candidate_modes
if "%CANDIDATE_TEST%"=="1" if "%SAVE_POST%"=="1" goto incompatible_candidate_modes
if "%CANDIDATE_TEST%"=="1" if "%RECOVER_CLOSED%"=="1" goto incompatible_candidate_modes
if "%CANDIDATE_TEST%"=="1" if "%RESUME_PREINPUT%"=="1" goto incompatible_candidate_modes
if "%WATCH_TEST%"=="1" if "%READ_ONLY_INSPECTION%"=="1" goto incompatible_watch_modes
if "%WATCH_TEST%"=="1" if "%READ_ONLY_LIST_INSPECTION%"=="1" goto incompatible_watch_modes
if "%WATCH_TEST%"=="1" if "%SAVE_POST%"=="1" goto incompatible_watch_modes
if "%WATCH_TEST%"=="1" if "%RECOVER_CLOSED%"=="1" goto incompatible_watch_modes
if "%WATCH_TEST%"=="1" if "%RESUME_PREINPUT%"=="1" goto incompatible_watch_modes
if "%READ_ONLY_LIST_INSPECTION%"=="1" if "%READ_ONLY_INSPECTION%"=="1" goto incompatible_list_modes
if "%READ_ONLY_LIST_INSPECTION%"=="1" if "%SAVE_POST%"=="1" goto incompatible_list_modes
if "%READ_ONLY_LIST_INSPECTION%"=="1" if "%RECOVER_CLOSED%"=="1" goto incompatible_list_modes
if "%READ_ONLY_LIST_INSPECTION%"=="1" if "%RESUME_PREINPUT%"=="1" goto incompatible_list_modes
if "%RESUME_PREINPUT%"=="1" if "%SAVE_POST%"=="0" goto incompatible_resume
if "%RESUME_PREINPUT%"=="1" if "%RECOVER_CLOSED%"=="1" goto incompatible_resume
if "%RESUME_PREINPUT%"=="1" if "%READ_ONLY_INSPECTION%"=="1" goto incompatible_resume
if "%READ_ONLY_INSPECTION%"=="1" if "%SAVE_POST%"=="1" goto incompatible_post_modes
if "%READ_ONLY_INSPECTION%"=="1" if "%RECOVER_CLOSED%"=="1" goto incompatible_options
goto new_log

:incompatible_monitor_batch_modes
>&2 echo Monitor batch operations cannot be combined with other monitoring, inspection, saving, finishing, recovery, or resume modes.
exit /b 2

:unsupported_monitor_batch_browser
>&2 echo Monitor batch saving requires the supplied Chrome launcher.
exit /b 2

:incompatible_monitor_save_modes
>&2 echo Monitor candidate saving cannot be combined with other monitoring, inspection, saving, finishing, recovery, or resume modes.
exit /b 2

:incompatible_monitor_finish_modes
>&2 echo Monitor candidate finishing cannot be combined with other monitoring, inspection, saving, finishing, recovery, or resume modes.
exit /b 2

:unsupported_monitor_save_browser
>&2 echo Monitor candidate saving requires the supplied Chrome launcher.
exit /b 2

:incompatible_monitor_modes
>&2 echo List monitoring cannot be combined with inspection, native saving, finishing, recovery, or resume.
exit /b 2

:unsupported_monitor_browser
>&2 echo List monitoring requires the supplied Chrome launcher.
exit /b 2

:incompatible_candidate_finish_modes
>&2 echo Completed candidate verification cannot be combined with saving, inspection, watching, generic recovery, or pre-input resume.
exit /b 2

:incompatible_candidate_save_modes
>&2 echo Candidate native saving cannot be combined with candidate inspection, list watching, site inspection, list inspection, post saving, native recovery, or pre-input resume.
exit /b 2

:unsupported_candidate_save_browser
>&2 echo Candidate native saving requires the supplied Chrome launcher.
exit /b 2

:incompatible_candidate_modes
>&2 echo Bounded candidate inspection cannot be combined with list watching, site inspection, list inspection, post saving, native recovery, or pre-input resume.
exit /b 2

:incompatible_watch_modes
>&2 echo Bounded list-watch trial cannot be combined with site inspection, list inspection, post saving, native recovery, or pre-input resume.
exit /b 2

:incompatible_list_modes
>&2 echo Read-only list inspection cannot be combined with site inspection, post saving, native recovery, or pre-input resume.
exit /b 2

:incompatible_options
>&2 echo Read-only site inspection cannot recover native-save state.
exit /b 2

:incompatible_post_modes
>&2 echo Read-only site inspection cannot be combined with post saving.
exit /b 2

:incompatible_resume
>&2 echo Pre-input resume requires post saving without site inspection or generic recovery.
exit /b 2

:new_log
set "LOG_FILE=%~dp0WINDOWS_TEST_RESULT-%RANDOM%-%RANDOM%.txt"
if exist "%LOG_FILE%" goto new_log
>"%LOG_FILE%" echo Image Monitor - %CHECK_LABEL%
if errorlevel 1 goto log_unavailable
if "%AUTO_COLLECT_ONCE%"=="1" >>"%LOG_FILE%" echo Save the eligible body images of at most one monitored post. Keep dedicated Chrome in front during saving.
if "%AUTO_MONITOR%"=="1" goto check_project
if "%AUTO_COLLECT_ONCE%"=="1" goto check_project
if "%MONITOR_RESUME_ONCE%"=="1" >>"%LOG_FILE%" echo Check the next pending post from the previous monitor session in background Chrome if its turn is due.
if "%MONITOR_RESUME_ONCE%"=="1" goto check_project
if "%WATCH_IMAGES_CHECK%"=="1" >>"%LOG_FILE%" echo Verify the files from the most recent completed watch save against their local records.
if "%WATCH_IMAGES_CHECK%"=="1" goto check_project
if "%WATCH_IMAGES%"=="1" >>"%LOG_FILE%" echo Check up to three pending recent posts and offer one eligible post for saving in dedicated Chrome.
if "%WATCH_IMAGES%"=="1" goto check_project
if "%WATCH_DETAIL%"=="1" >>"%LOG_FILE%" echo Inspect at most one pending post from the last verified list scan in headless Chrome.
if "%WATCH_DETAIL%"=="1" goto check_project
if "%MONITOR_DIAGNOSIS%"=="1" >>"%LOG_FILE%" echo Reading the saved list profile and the latest monitor review from local records.
if "%MONITOR_DIAGNOSIS%"=="1" goto check_project
if "%TEST_LIST_RECOVERY%"=="1" goto check_project
if "%MONITOR_SAVE_BATCH%"=="0" if "%MONITOR_BATCH_FINISH%"=="0" if "%MONITOR_SAVE_TEST%"=="0" if "%MONITOR_FINISH%"=="0" if "%MONITOR%"=="0" if "%CANDIDATE_FINISH%"=="0" if "%CANDIDATE_SAVE_TEST%"=="0" if "%CANDIDATE_TEST%"=="0" if "%WATCH_TEST%"=="0" if "%READ_ONLY_LIST_INSPECTION%"=="0" if "%READ_ONLY_INSPECTION%"=="0" if "%SAVE_POST%"=="0" >>"%LOG_FILE%" echo This file contains setup output and the synthetic-image test result.
if "%SAVE_POST%"=="1" >>"%LOG_FILE%" echo Single-post native image saving requires review in the dedicated Chrome app window.
if "%RESUME_PREINPUT%"=="1" >>"%LOG_FILE%" echo Verified pre-input resume was explicitly requested. Generic native recovery will not run.
if "%READ_ONLY_INSPECTION%"=="1" >>"%LOG_FILE%" echo Read-only public-page DOM inspection. No image saving is attempted.
if "%READ_ONLY_LIST_INSPECTION%"=="1" >>"%LOG_FILE%" echo Read-only public search-list DOM inspection in a headless browser. No image saving or monitoring is attempted.
if "%WATCH_TEST%"=="1" >>"%LOG_FILE%" echo Bounded public-list discovery trial: up to two cycles in headless mode, about two minutes after setup.
if "%WATCH_TEST%"=="1" >>"%LOG_FILE%" echo The separate watch database persists baseline and candidate records. The image-job queue and image files are untouched.
if "%WATCH_TEST%"=="1" >>"%LOG_FILE%" echo No continuous program or native image saving is started. This single TXT opens automatically when the trial ends.
if "%CANDIDATE_TEST%"=="1" >>"%LOG_FILE%" echo Read-only inspection of at most two previously stored candidate posts, with at least 60 seconds between requests.
if "%CANDIDATE_TEST%"=="1" >>"%LOG_FILE%" echo Uses the existing watch baseline and candidates. No new list scan, image saving, or continuous monitoring is started.
if "%CANDIDATE_TEST%"=="1" >>"%LOG_FILE%" echo This single TXT opens automatically when the inspection ends. Already attempted candidates are not automatically retried.
if "%CANDIDATE_SAVE_TEST%"=="1" >>"%LOG_FILE%" echo Native saving of one previously inspected candidate, at most two reviewed images.
if "%CANDIDATE_SAVE_TEST%"=="1" >>"%LOG_FILE%" echo Review the dedicated Chrome window and click its save-start button once. Keep that window in front until saving finishes.
if "%CANDIDATE_SAVE_TEST%"=="1" >>"%LOG_FILE%" echo Existing watch records are retained; image jobs and files use a separate work directory. No automatic recovery or continuous monitoring is started.
if "%CANDIDATE_FINISH%"=="1" >>"%LOG_FILE%" echo Offline verification of the already completed candidate image files and metadata.
if "%CANDIDATE_FINISH%"=="1" >>"%LOG_FILE%" echo Shared pending state is cleared only after the prior dedicated browser is verified closed and all saved artifacts match.
if "%CANDIDATE_FINISH%"=="1" >>"%LOG_FILE%" echo Only the dedicated test browser may receive a normal close request after saved-file and exact ownership checks. Personal browser windows are not used.
if "%CANDIDATE_FINISH%"=="1" >>"%LOG_FILE%" echo No browser is launched or forced closed, no images are saved again, and no Start button is required. This TXT opens automatically.
if "%MONITOR%"=="1" >>"%LOG_FILE%" echo Local status screen for list discovery and automatic candidate inspection. Background reader: Chrome.
if "%MONITOR%"=="1" >>"%LOG_FILE%" echo Watching begins only after you choose Start in the screen. Use Pause, Stop, or Exit there.
if "%MONITOR%"=="1" >>"%LOG_FILE%" echo After a successful list check, the monitor can inspect one unattempted candidate before the next list check.
if "%MONITOR%"=="1" >>"%LOG_FILE%" echo Existing saved monitor images are verified locally when the screen opens; no site request or native input starts for this check.
if "%MONITOR%"=="1" >>"%LOG_FILE%" echo Watching inspects candidates in the background. To save one eligible post, stop watching and request a save in the dashboard, then confirm in dedicated Chrome.
if "%MONITOR_SAVE_TEST%"=="1" >>"%LOG_FILE%" echo Native saving of one frozen candidate from the local monitor, up to ten verified body images.
if "%MONITOR_SAVE_TEST%"=="1" >>"%LOG_FILE%" echo Review the dedicated Chrome window and click its save-start button once. Keep that window in front until saving finishes.
if "%MONITOR_SAVE_TEST%"=="1" >>"%LOG_FILE%" echo Existing watch records and earlier saved files are preserved. This save uses its separate monitor output directory.
if "%MONITOR_SAVE_TEST%"=="1" >>"%LOG_FILE%" echo No automatic recovery, new list scan, or continuous image saving is started. This single TXT opens automatically.
if "%MONITOR_FINISH%"=="1" >>"%LOG_FILE%" echo Offline verification of already completed monitor candidate files and metadata in their separate output directory.
if "%MONITOR_FINISH%"=="1" >>"%LOG_FILE%" echo Pending state is cleared only after exact saved-file and owned-browser checks. Existing files and prior trial records are preserved.
if "%MONITOR_FINISH%"=="1" >>"%LOG_FILE%" echo No new browser or Start button is needed. Only the owned prior browser may receive a normal close request; no images are downloaded again.
if "%MONITOR_SAVE_BATCH%"=="1" >>"%LOG_FILE%" echo Bounded native saving of at most two new, previously inspected monitor candidates.
if "%MONITOR_SAVE_BATCH%"=="1" >>"%LOG_FILE%" echo Verified completed monitor saves are recorded and skipped without saving them again. Earlier files and selections are preserved.
if "%MONITOR_SAVE_BATCH%"=="1" >>"%LOG_FILE%" echo For each new post, click save-start once in its dedicated Chrome window and keep that window in front until saving finishes.
if "%MONITOR_SAVE_BATCH%"=="1" >>"%LOG_FILE%" echo Uses a separate batch output directory and durable attempt ledger. Interrupted attempts are not automatically retried.
if "%MONITOR_SAVE_BATCH%"=="1" >>"%LOG_FILE%" echo No new list or detail inspection, continuous collection, or automatic recovery is started. This single TXT opens automatically.
if "%MONITOR_BATCH_FINISH%"=="1" >>"%LOG_FILE%" echo Offline reconciliation of already completed monitor batch images and metadata.
if "%MONITOR_BATCH_FINISH%"=="1" >>"%LOG_FILE%" echo Only exactly bound completed files and owned-browser state may be reconciled. Earlier files, selections, and unresolved work are preserved.
if "%MONITOR_BATCH_FINISH%"=="1" >>"%LOG_FILE%" echo No new browser, save-start button, image saving, or automatic native retry is started. This single TXT opens automatically.
if "%MONITOR_BATCH_FINISH%"=="0" if "%MONITOR_FINISH%"=="0" if "%MONITOR%"=="0" if "%CANDIDATE_FINISH%"=="0" >>"%LOG_FILE%" echo Selected browser: %TEST_BROWSER%
:check_project
if not exist "pyproject.toml" goto missing_project
if not exist "uv.lock" goto missing_project
if not defined LOCALAPPDATA goto missing_appdata

echo Preparing the test. Please wait; first setup can take several minutes.
call :find_uv 2>>"%LOG_FILE%"
if defined UV_EXE goto uv_ready
echo Installing uv from the official WinGet package...
>>"%LOG_FILE%" echo STAGE: install_uv
where winget.exe >nul 2>&1
if errorlevel 1 goto missing_winget
winget.exe install --id astral-sh.uv --exact --source winget --accept-source-agreements --accept-package-agreements --disable-interactivity >>"%LOG_FILE%" 2>&1
set "INSTALL_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo WinGet exit code: %INSTALL_CODE%
if not "%INSTALL_CODE%"=="0" goto failed
call :find_uv 2>>"%LOG_FILE%"
if defined UV_EXE goto uv_ready
>>"%LOG_FILE%" echo uv was not found on the process PATH, persistent Windows PATH, or known installation paths.
goto failed

:uv_ready
>>"%LOG_FILE%" echo STAGE: check_uv
"%UV_EXE%" --version >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto failed
echo Preparing Python 3.12.14...
>>"%LOG_FILE%" echo STAGE: install_python
"%UV_EXE%" --no-progress python install 3.12.14 >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto failed
echo Installing locked project dependencies...
>>"%LOG_FILE%" echo STAGE: install_dependencies
"%UV_EXE%" --no-progress sync --locked --extra windows --python 3.12.14 --managed-python >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto failed
if "%AUTO_MONITOR%"=="1" goto start_auto_monitor
if "%AUTO_COLLECT_ONCE%"=="1" goto start_auto_collect
if "%MONITOR_RESUME_ONCE%"=="1" goto start_monitor_resume
if "%WATCH_IMAGES_CHECK%"=="1" goto check_watch_images
if "%WATCH_IMAGES%"=="1" goto start_watch_images
if "%WATCH_DETAIL%"=="1" goto start_watch_detail
if "%TEST_LIST_RECOVERY%"=="1" goto test_list_recovery
if "%MONITOR_DIAGNOSIS%"=="1" goto read_monitor_diagnosis
if "%MONITOR_SAVE_BATCH%"=="1" goto start_monitor_save_batch
if "%MONITOR_BATCH_FINISH%"=="1" goto start_monitor_batch_finish
if "%MONITOR_SAVE_TEST%"=="1" goto start_monitor_save_test
if "%MONITOR_FINISH%"=="1" goto start_monitor_finish
if "%MONITOR%"=="1" goto start_monitor
if "%CANDIDATE_FINISH%"=="1" goto start_candidate_finish
if "%CANDIDATE_SAVE_TEST%"=="1" goto start_candidate_save_test
if "%CANDIDATE_TEST%"=="1" goto start_candidate_test
if "%WATCH_TEST%"=="1" goto start_watch_test
if "%READ_ONLY_LIST_INSPECTION%"=="1" goto start_list_inspection
if "%READ_ONLY_INSPECTION%"=="1" goto start_site_inspection
rem Recovery is only enabled by the dedicated, user-initiated retry launcher.
if "%RECOVER_CLOSED%"=="0" goto recovery_finished
echo Checking that the previous test browser is closed...
>>"%LOG_FILE%" echo STAGE: recover_previous_probe
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor native-recover --confirm-browser-closed >>"%LOG_FILE%" 2>&1
set "RECOVERY_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Explicit recovery exit code: %RECOVERY_CODE%
if not "%RECOVERY_CODE%"=="0" goto failed

:recovery_finished
if "%SAVE_POST%"=="1" goto start_post_save
goto start_probe

:start_probe
echo Starting the dedicated %TEST_BROWSER% test browser. Keep that browser in front until the test ends.
>>"%LOG_FILE%" echo STAGE: native_probe
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor native-probe --work-root "%LOCALAPPDATA%\ImageMonitorProbe" --browser "%TEST_BROWSER%" >>"%LOG_FILE%" 2>&1
set "PROBE_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Native probe exit code: %PROBE_CODE%
if not "%PROBE_CODE%"=="0" goto failed
>>"%LOG_FILE%" echo RESULT: SUCCESS
>>"%LOG_FILE%" echo The synthetic-image native-save test passed. Site monitoring was not started.
echo Test passed. Opening the result file.
start "" notepad.exe "%LOG_FILE%"
exit /b 0

:start_post_save
echo Starting a dedicated %TEST_BROWSER% session for one public post.
echo Review the Chrome app window, then click its save-start button to begin.
>>"%LOG_FILE%" echo STAGE: post_save
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor save-post --work-root "%LOCALAPPDATA%\ImageMonitorPostSave" --browser "%TEST_BROWSER%" %POST_SAVE_RESUME_ARGUMENT% >>"%LOG_FILE%" 2>&1
set "POST_SAVE_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Single-post save exit code: %POST_SAVE_CODE%
if not "%POST_SAVE_CODE%"=="0" goto failed
>>"%LOG_FILE%" echo RESULT: SUCCESS - SINGLE_POST_NATIVE_SAVE
>>"%LOG_FILE%" echo The reviewed post's image jobs completed. Continuous monitoring was not started.
echo Post saving finished. Opening the result file.
start "" notepad.exe "%LOG_FILE%"
exit /b 0

:start_site_inspection
echo Inspecting the public page in a dedicated %TEST_BROWSER% session. Please wait.
>>"%LOG_FILE%" echo STAGE: site_inspection
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor site-inspect --work-root "%LOCALAPPDATA%\ImageMonitorInspection" --browser "%TEST_BROWSER%" >>"%LOG_FILE%" 2>&1
set "INSPECTION_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Read-only inspection exit code: %INSPECTION_CODE%
if not "%INSPECTION_CODE%"=="0" goto failed
>>"%LOG_FILE%" echo RESULT: SUCCESS - READ_ONLY_SITE_INSPECTION
>>"%LOG_FILE%" echo A read-only DOM report was created. No images were saved or monitored.
echo Site inspection finished. Opening the result file.
start "" notepad.exe "%LOG_FILE%"
exit /b 0

:start_list_inspection
echo Inspecting the public search list in a headless %TEST_BROWSER% session. Please wait.
>>"%LOG_FILE%" echo STAGE: list_inspection
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor list-inspect --work-root "%LOCALAPPDATA%\ImageMonitorListInspection" --browser "%TEST_BROWSER%" >>"%LOG_FILE%" 2>&1
set "LIST_INSPECTION_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Read-only list inspection exit code: %LIST_INSPECTION_CODE%
if not "%LIST_INSPECTION_CODE%"=="0" goto failed
>>"%LOG_FILE%" echo RESULT: SUCCESS - READ_ONLY_LIST_INSPECTION
>>"%LOG_FILE%" echo A read-only search-list report was created. No images were saved or monitored.
echo List inspection finished. Opening the result file.
start "" notepad.exe "%LOG_FILE%"
exit /b 0

:start_monitor_save_batch
echo Verifying completed saves and preparing at most two new monitor candidates.
echo For each new Chrome post, click save-start once and keep its window in front until saving finishes.
>>"%LOG_FILE%" echo STAGE: monitor_save_batch
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor monitor-save-batch --watch-root "%LOCALAPPDATA%\ImageMonitorWatch" --legacy-root "%LOCALAPPDATA%\ImageMonitorMonitorSave" --work-root "%LOCALAPPDATA%\ImageMonitorBatch" >>"%LOG_FILE%" 2>&1
set "MONITOR_BATCH_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Monitor batch save exit code: %MONITOR_BATCH_CODE%
if not "%MONITOR_BATCH_CODE%"=="0" goto failed
>>"%LOG_FILE%" echo RESULT: COMPLETED_OR_SAFELY_WAITING - MONITOR_BATCH_NATIVE_SAVE
>>"%LOG_FILE%" echo See the JSON status for completed, waiting, busy, or no new candidates. Already completed files were not saved again.
echo Monitor batch saving finished. Opening the result file.
start "" notepad.exe "%LOG_FILE%"
exit /b 0

:start_monitor_batch_finish
echo Verifying existing completed monitor batch files and owned-browser state offline.
echo No new Chrome window, save-start button, or image saving is needed.
>>"%LOG_FILE%" echo STAGE: monitor_batch_finish
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor monitor-batch-finish --watch-root "%LOCALAPPDATA%\ImageMonitorWatch" --legacy-root "%LOCALAPPDATA%\ImageMonitorMonitorSave" --work-root "%LOCALAPPDATA%\ImageMonitorBatch" >>"%LOG_FILE%" 2>&1
set "MONITOR_BATCH_FINISH_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Monitor batch verification exit code: %MONITOR_BATCH_FINISH_CODE%
if not "%MONITOR_BATCH_FINISH_CODE%"=="0" goto failed
>>"%LOG_FILE%" echo RESULT: COMPLETED_OR_NO_PENDING - MONITOR_BATCH_VERIFICATION
>>"%LOG_FILE%" echo See the JSON status for completed, no pending work, or busy. Existing completed files and unresolved attempts are preserved.
echo Monitor batch verification finished. Opening the result file.
start "" notepad.exe "%LOG_FILE%"
exit /b 0

:start_monitor_save_test
echo Starting dedicated Chrome for one previously inspected local-monitor candidate.
echo Click its save-start button once, then keep that Chrome window in front until saving finishes.
>>"%LOG_FILE%" echo STAGE: monitor_save_test
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor monitor-save-test --watch-root "%LOCALAPPDATA%\ImageMonitorWatch" --work-root "%LOCALAPPDATA%\ImageMonitorMonitorSave" --browser "%TEST_BROWSER%" >>"%LOG_FILE%" 2>&1
set "MONITOR_SAVE_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Monitor candidate native save exit code: %MONITOR_SAVE_CODE%
if not "%MONITOR_SAVE_CODE%"=="0" goto failed
>>"%LOG_FILE%" echo RESULT: COMPLETED_OR_SAFELY_WAITING - MONITOR_CANDIDATE_NATIVE_SAVE
>>"%LOG_FILE%" echo See the JSON status for completed, waiting, busy, or no candidate. Earlier completed files are preserved.
echo Monitor candidate saving finished. Opening the result file.
start "" notepad.exe "%LOG_FILE%"
exit /b 0

:start_monitor_finish
echo Verifying already completed monitor candidate files and owned-browser state offline.
echo No new Chrome window or Start button is needed. Existing files will not be downloaded again.
>>"%LOG_FILE%" echo STAGE: monitor_finish
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor monitor-finish --watch-root "%LOCALAPPDATA%\ImageMonitorWatch" --work-root "%LOCALAPPDATA%\ImageMonitorMonitorSave" >>"%LOG_FILE%" 2>&1
set "MONITOR_FINISH_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Completed monitor candidate verification exit code: %MONITOR_FINISH_CODE%
if not "%MONITOR_FINISH_CODE%"=="0" goto failed
>>"%LOG_FILE%" echo RESULT: COMPLETED_OR_NO_PENDING - MONITOR_CANDIDATE_VERIFICATION
>>"%LOG_FILE%" echo See the JSON status for completed, no pending save, or busy. Existing files are preserved.
echo Monitor candidate verification finished. Opening the result file.
start "" notepad.exe "%LOG_FILE%"
exit /b 0

:start_auto_monitor
if defined AUTO_MONITOR_LIMIT echo The two-cycle test stops automatically and opens its result in Notepad.
if not defined AUTO_MONITOR_LIMIT echo Press ENTER in this window between saves to stop and open the result.
echo Keep dedicated Chrome in front during a save.
>>"%LOG_FILE%" echo STAGE: auto_monitor
set "IMAGE_MONITOR_CONSOLE_PROGRESS=1"
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor auto-monitor --watch-root "%LOCALAPPDATA%\ImageMonitorWatch" --legacy-root "%LOCALAPPDATA%\ImageMonitorMonitorSave" --work-root "%LOCALAPPDATA%\ImageMonitorBatch" %AUTO_MONITOR_LIMIT% >>"%LOG_FILE%" 2>&1
set "WATCH_EXIT_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Auto monitor exit code: %WATCH_EXIT_CODE%
goto finish_watch_result

:start_auto_collect
echo If dedicated Chrome opens, switch to it and leave it in front until saving finishes.
>>"%LOG_FILE%" echo STAGE: auto_collect_once
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor auto-collect-once --watch-root "%LOCALAPPDATA%\ImageMonitorWatch" --legacy-root "%LOCALAPPDATA%\ImageMonitorMonitorSave" --work-root "%LOCALAPPDATA%\ImageMonitorBatch" >>"%LOG_FILE%" 2>&1
set "WATCH_EXIT_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Auto collect once exit code: %WATCH_EXIT_CODE%
goto finish_watch_result

:start_monitor_resume
echo Checking the pending monitor detail. The result TXT will open automatically.
>>"%LOG_FILE%" echo STAGE: monitor_resume_once
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor monitor-resume-once --work-root "%LOCALAPPDATA%\ImageMonitorWatch" >>"%LOG_FILE%" 2>&1
set "WATCH_EXIT_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Monitor resume once exit code: %WATCH_EXIT_CODE%
goto finish_watch_result

:check_watch_images
echo Verifying the last completed watch save on this PC.
>>"%LOG_FILE%" echo STAGE: watch_images_check
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor watch-images-check --watch-root "%LOCALAPPDATA%\ImageMonitorWatch" --legacy-root "%LOCALAPPDATA%\ImageMonitorCandidateSave" --work-root "%LOCALAPPDATA%\ImageMonitorWatchImages" >>"%LOG_FILE%" 2>&1
set "WATCH_EXIT_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Watch images check exit code: %WATCH_EXIT_CODE%
goto finish_watch_result

:start_watch_images
echo Checking stored recent posts. If the dedicated Chrome window opens, click Save Start and keep it in front until finished.
>>"%LOG_FILE%" echo STAGE: watch_images
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor watch-images --watch-root "%LOCALAPPDATA%\ImageMonitorWatch" --legacy-root "%LOCALAPPDATA%\ImageMonitorCandidateSave" --work-root "%LOCALAPPDATA%\ImageMonitorWatchImages" --browser chrome >>"%LOG_FILE%" 2>&1
set "WATCH_EXIT_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Watch images exit code: %WATCH_EXIT_CODE%
goto finish_watch_result

:start_watch_detail
echo Checking the most recent list scan and its pending candidate in headless Chrome.
>>"%LOG_FILE%" echo STAGE: watch_detail
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor watch-detail --work-root "%LOCALAPPDATA%\ImageMonitorWatch" --browser chrome >>"%LOG_FILE%" 2>&1
set "WATCH_EXIT_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Watch detail exit code: %WATCH_EXIT_CODE%

:finish_watch_result
if not "%WATCH_EXIT_CODE%"=="0" goto watch_result_failed
>>"%LOG_FILE%" echo RESULT: %WATCH_RESULT%
goto open_watch_result

:watch_result_failed
>>"%LOG_FILE%" echo RESULT: STOPPED - %WATCH_RESULT%
if not defined WATCH_EXIT_CODE set "WATCH_EXIT_CODE=1"

:open_watch_result
start "" notepad.exe "%LOG_FILE%"
exit /b %WATCH_EXIT_CODE%

:test_list_recovery
echo Checking the monitored list in background Chrome. The result TXT will open automatically.
>>"%LOG_FILE%" echo STAGE: test_list_recovery
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor test-list-recovery --watch-root "%LOCALAPPDATA%\ImageMonitorWatch" >>"%LOG_FILE%" 2>&1
set "WATCH_EXIT_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Test list recovery exit code: %WATCH_EXIT_CODE%
goto finish_watch_result

:read_monitor_diagnosis
>>"%LOG_FILE%" echo STAGE: stored_list_diagnosis
call :get_stored_list_diagnosis
set "DIAGNOSIS_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Diagnosis exit code: %DIAGNOSIS_CODE%
if not "%DIAGNOSIS_CODE%"=="0" goto failed
>>"%LOG_FILE%" echo RESULT: STORED_LIST_DIAGNOSIS
start "" notepad.exe "%LOG_FILE%"
exit /b 0

:get_stored_list_diagnosis
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor monitor-diagnosis --work-root "%LOCALAPPDATA%\ImageMonitorWatch" >>"%LOG_FILE%" 2>&1
exit /b %ERRORLEVEL%

:start_monitor
echo Opening the local monitoring screen and checking existing saved results offline.
echo Choose Start to watch the list and inspect candidate posts in the background.
echo Use Pause or Stop as needed, then choose Exit when finished. One result TXT will open.
>>"%LOG_FILE%" echo STAGE: monitor
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor monitor --work-root "%LOCALAPPDATA%\ImageMonitorWatch" --save-root "%LOCALAPPDATA%\ImageMonitorMonitorSave" --batch-root "%LOCALAPPDATA%\ImageMonitorBatch" >>"%LOG_FILE%" 2>&1
set "MONITOR_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo List monitor exit code: %MONITOR_CODE%
if not "%MONITOR_CODE%"=="0" goto failed
>>"%LOG_FILE%" echo RESULT: CLOSED_OR_BUSY - LIST_MONITOR
>>"%LOG_FILE%" echo See the JSON status above for the final monitoring state. Existing records and image files are preserved.
echo List monitoring ended. Opening the result file.
start "" notepad.exe "%LOG_FILE%"
exit /b 0

:start_candidate_finish
echo Verifying the existing saved candidate images and closed-browser state offline.
echo No browser window or Start button is needed. The existing files will not be downloaded again.
>>"%LOG_FILE%" echo STAGE: candidate_finish
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor candidate-finish --watch-root "%LOCALAPPDATA%\ImageMonitorWatch" --work-root "%LOCALAPPDATA%\ImageMonitorCandidateSave" >>"%LOG_FILE%" 2>&1
set "CANDIDATE_FINISH_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Completed candidate verification exit code: %CANDIDATE_FINISH_CODE%
if not "%CANDIDATE_FINISH_CODE%"=="0" goto failed
>>"%LOG_FILE%" echo RESULT: COMPLETED_OR_NO_PENDING - COMPLETED_CANDIDATE_VERIFICATION
>>"%LOG_FILE%" echo See the JSON status above for completed, no pending save, or busy. Existing image files are preserved.
echo Completed candidate verification finished. Opening the result file.
start "" notepad.exe "%LOG_FILE%"
exit /b 0

:start_candidate_save_test
echo Starting the dedicated Chrome window for one previously inspected candidate.
echo Review its post, click the save-start button once, then keep that window in front until saving finishes.
>>"%LOG_FILE%" echo STAGE: candidate_save_test
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor candidate-save-test --watch-root "%LOCALAPPDATA%\ImageMonitorWatch" --work-root "%LOCALAPPDATA%\ImageMonitorCandidateSave" --browser "%TEST_BROWSER%" >>"%LOG_FILE%" 2>&1
set "CANDIDATE_SAVE_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Candidate native save exit code: %CANDIDATE_SAVE_CODE%
if not "%CANDIDATE_SAVE_CODE%"=="0" goto failed
>>"%LOG_FILE%" echo RESULT: COMPLETED_OR_SAFELY_WAITING - REVIEWED_CANDIDATE_NATIVE_SAVE
>>"%LOG_FILE%" echo See the JSON status above for completed, waiting, busy, or no candidate. Existing completed files are preserved.
echo Candidate saving finished. Opening the result file.
start "" notepad.exe "%LOG_FILE%"
exit /b 0

:start_candidate_test
echo Inspecting at most two stored candidates in headless %TEST_BROWSER%. Allow about two minutes after setup.
echo Existing baseline and candidate records are retained. No native-save button or foreground window is required.
>>"%LOG_FILE%" echo STAGE: candidate_test
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor candidate-test --work-root "%LOCALAPPDATA%\ImageMonitorWatch" --browser "%TEST_BROWSER%" >>"%LOG_FILE%" 2>&1
set "CANDIDATE_TEST_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Bounded candidate inspection exit code: %CANDIDATE_TEST_CODE%
if not "%CANDIDATE_TEST_CODE%"=="0" goto failed
>>"%LOG_FILE%" echo RESULT: COMPLETED_OR_SAFELY_WAITING - BOUNDED_CANDIDATE_INSPECTION
>>"%LOG_FILE%" echo See the JSON status above for completed, waiting, busy, no pending candidates, or no baseline. No images were saved.
echo Candidate inspection finished. Opening the result file.
start "" notepad.exe "%LOG_FILE%"
exit /b 0

:start_watch_test
if not exist "%LOCALAPPDATA%\ImageMonitorWatch\watch.sqlite" goto live_watch_trial
>>"%LOG_FILE%" echo STAGE: historical_monitor_list_diagnosis
call :get_stored_list_diagnosis
>>"%LOG_FILE%" echo Historical diagnosis exit code: %ERRORLEVEL%

:live_watch_trial
echo Running up to two list-discovery cycles in headless %TEST_BROWSER%. Allow about two minutes after setup.
echo This bounded trial persists a separate watch baseline and candidates; it leaves image jobs and files untouched.
echo No continuous program or native image saving starts. One TXT will open automatically when the trial ends.
>>"%LOG_FILE%" echo STAGE: watch_test
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor watch-test --work-root "%LOCALAPPDATA%\ImageMonitorWatch" --browser "%TEST_BROWSER%" >>"%LOG_FILE%" 2>&1
set "WATCH_TEST_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Bounded list-watch trial exit code: %WATCH_TEST_CODE%
if not "%WATCH_TEST_CODE%"=="0" goto failed
>>"%LOG_FILE%" echo RESULT: BOUNDED_LIST_WATCH_TRIAL
>>"%LOG_FILE%" echo See the JSON status for completion, a verified recent window with a history gap, waiting, or busy.
echo List-watch trial finished. Opening the result file.
start "" notepad.exe "%LOG_FILE%"
exit /b 0

:missing_project
>>"%LOG_FILE%" echo Setup stopped: pyproject.toml or uv.lock is missing. Fully extract the ZIP first.
goto failed
:missing_appdata
>>"%LOG_FILE%" echo Setup stopped: LOCALAPPDATA is unavailable in this Windows session.
goto failed
:missing_winget
>>"%LOG_FILE%" echo uv is not installed and WinGet is unavailable. Send this file for help.
goto failed
:failed
if "%AUTO_MONITOR%"=="1" goto watch_result_failed
if "%AUTO_COLLECT_ONCE%"=="1" goto watch_result_failed
if "%MONITOR_RESUME_ONCE%"=="1" goto watch_result_failed
if "%WATCH_IMAGES_CHECK%"=="1" goto watch_result_failed
if "%WATCH_IMAGES%"=="1" goto watch_result_failed
if "%WATCH_DETAIL%"=="1" goto watch_result_failed
if "%MONITOR_DIAGNOSIS%"=="1" goto diagnosis_failed
if "%TEST_LIST_RECOVERY%"=="1" goto watch_result_failed
if "%MONITOR_SAVE_BATCH%"=="1" >>"%LOG_FILE%" echo RESULT: STOPPED - MONITOR_BATCH_NATIVE_SAVE. No automatic retry or recovery was performed.
if "%MONITOR_SAVE_BATCH%"=="1" >>"%LOG_FILE%" echo Send this TXT for diagnosis. Preserve the pending browser, attempt ledger, and all existing files.
if "%MONITOR_BATCH_FINISH%"=="1" >>"%LOG_FILE%" echo RESULT: STOPPED - MONITOR_BATCH_VERIFICATION. Existing files and unresolved attempt records are preserved.
if "%MONITOR_BATCH_FINISH%"=="1" >>"%LOG_FILE%" echo Send this TXT for diagnosis. No new browser or native input was started and no image was saved again.
if "%MONITOR_SAVE_TEST%"=="1" >>"%LOG_FILE%" echo RESULT: STOPPED - MONITOR_CANDIDATE_NATIVE_SAVE. No automatic retry or recovery was performed.
if "%MONITOR_SAVE_TEST%"=="1" >>"%LOG_FILE%" echo Send this TXT for diagnosis. Preserve any pending browser and existing saved files.
if "%MONITOR_FINISH%"=="1" >>"%LOG_FILE%" echo RESULT: STOPPED - MONITOR_CANDIDATE_VERIFICATION. Completed files and unresolved state are preserved.
if "%MONITOR_FINISH%"=="1" >>"%LOG_FILE%" echo Send this TXT for diagnosis. No new browser or native input was started and no image was downloaded again.
if "%MONITOR%"=="1" >>"%LOG_FILE%" echo RESULT: STOPPED - LIST_MONITOR. No native image saving or recovery was started.
if "%MONITOR%"=="1" >>"%LOG_FILE%" echo Send this TXT for diagnosis. Existing records and image files are preserved.
if "%CANDIDATE_FINISH%"=="1" >>"%LOG_FILE%" echo RESULT: STOPPED - COMPLETED_CANDIDATE_VERIFICATION. Existing files and unresolved state are preserved.
if "%CANDIDATE_FINISH%"=="1" >>"%LOG_FILE%" echo Send this TXT for diagnosis. No browser was launched or forced closed and no image was saved again.
if "%CANDIDATE_SAVE_TEST%"=="1" >>"%LOG_FILE%" echo RESULT: STOPPED - REVIEWED_CANDIDATE_NATIVE_SAVE. No automatic retry or recovery was performed.
if "%CANDIDATE_SAVE_TEST%"=="1" >>"%LOG_FILE%" echo Send this TXT file for diagnosis. Leave any pending browser unchanged for inspection.
if "%SAVE_POST%"=="1" >>"%LOG_FILE%" echo RESULT: STOPPED - SINGLE_POST_NATIVE_SAVE. No automatic retry was performed.
if "%SAVE_POST%"=="1" >>"%LOG_FILE%" echo Send this TXT file for diagnosis. Leave any pending browser unchanged for inspection.
if "%MONITOR_SAVE_BATCH%"=="0" if "%MONITOR_BATCH_FINISH%"=="0" if "%MONITOR_SAVE_TEST%"=="0" if "%MONITOR_FINISH%"=="0" if "%MONITOR%"=="0" if "%CANDIDATE_FINISH%"=="0" if "%CANDIDATE_SAVE_TEST%"=="0" if "%CANDIDATE_TEST%"=="0" if "%WATCH_TEST%"=="0" if "%READ_ONLY_LIST_INSPECTION%"=="0" if "%READ_ONLY_INSPECTION%"=="0" if "%SAVE_POST%"=="0" >>"%LOG_FILE%" echo RESULT: FAILED - automation stopped; no automatic retry was performed.
if "%MONITOR_SAVE_BATCH%"=="0" if "%MONITOR_BATCH_FINISH%"=="0" if "%MONITOR_SAVE_TEST%"=="0" if "%MONITOR_FINISH%"=="0" if "%MONITOR%"=="0" if "%CANDIDATE_FINISH%"=="0" if "%CANDIDATE_SAVE_TEST%"=="0" if "%CANDIDATE_TEST%"=="0" if "%WATCH_TEST%"=="0" if "%READ_ONLY_LIST_INSPECTION%"=="0" if "%READ_ONLY_INSPECTION%"=="0" if "%SAVE_POST%"=="0" >>"%LOG_FILE%" echo Send this TXT file for diagnosis. Leave any pending test browser unchanged for inspection.
if "%READ_ONLY_INSPECTION%"=="1" >>"%LOG_FILE%" echo RESULT: FAILED - READ_ONLY_SITE_INSPECTION. No image saving was attempted.
if "%READ_ONLY_INSPECTION%"=="1" >>"%LOG_FILE%" echo Send this TXT file for diagnosis. Native-save recovery was not performed.
if "%READ_ONLY_LIST_INSPECTION%"=="1" >>"%LOG_FILE%" echo RESULT: FAILED - READ_ONLY_LIST_INSPECTION. No image saving was attempted.
if "%READ_ONLY_LIST_INSPECTION%"=="1" >>"%LOG_FILE%" echo Send this TXT file for diagnosis. Native-save recovery was not performed.
if "%WATCH_TEST%"=="1" >>"%LOG_FILE%" echo RESULT: STOPPED - BOUNDED_LIST_WATCH_TRIAL. No image saving was attempted.
if "%WATCH_TEST%"=="1" >>"%LOG_FILE%" echo Send this TXT file for diagnosis. Native-save recovery was not performed.
if "%CANDIDATE_TEST%"=="1" >>"%LOG_FILE%" echo RESULT: STOPPED - BOUNDED_CANDIDATE_INSPECTION. No image saving was attempted.
if "%CANDIDATE_TEST%"=="1" >>"%LOG_FILE%" echo Send this TXT file for diagnosis. Native-save recovery was not performed.
echo Test stopped. Opening the result file; please send that TXT file for help.
start "" notepad.exe "%LOG_FILE%"
exit /b 1

:diagnosis_failed
>>"%LOG_FILE%" echo RESULT: STOPPED - STORED_LIST_DIAGNOSIS
start "" notepad.exe "%LOG_FILE%"
exit /b 1

:log_unavailable
echo Could not create the result TXT. Extract the ZIP into a writable folder such as Downloads.
pause
exit /b 1

:lookup_only
call :find_uv
if not defined UV_EXE exit /b 1
echo "%UV_EXE%"
exit /b 0

:find_uv
set "UV_EXE="
for /f "delims=" %%U in ('where uv.exe 2^>nul') do if not defined UV_EXE if exist "%%~fU" set "UV_EXE=%%~fU"
if defined UV_EXE exit /b 0
rem WinGet updates persistent PATH, not this already-running CMD process.
rem Read and expand Machine/User PATH in a child only; never modify registry or policy.
for /f "usebackq delims=" %%U in (`call "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -Command "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); $OutputEncoding = [Console]::OutputEncoding; $found = @(Get-Command uv.exe -CommandType Application -ErrorAction SilentlyContinue)[0]; if (-not $found) { $env:Path = [Environment]::ExpandEnvironmentVariables([Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')); $found = @(Get-Command uv.exe -CommandType Application -ErrorAction SilentlyContinue)[0] }; if ($found) { [Console]::WriteLine($found.Source) }"`) do if not defined UV_EXE if exist "%%~fU" set "UV_EXE=%%~fU"
if defined UV_EXE exit /b 0
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" set "UV_EXE=%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe"
if defined UV_EXE exit /b 0
if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.local\bin\uv.exe"
if defined UV_EXE exit /b 0
if exist "%ProgramFiles%\WinGet\Links\uv.exe" set "UV_EXE=%ProgramFiles%\WinGet\Links\uv.exe"
if defined UV_EXE exit /b 0
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv_*") do for /r "%%~fD" %%U in (uv.exe) do if not defined UV_EXE if exist "%%~fU" set "UV_EXE=%%~fU"
exit /b 0
