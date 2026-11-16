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
set "SAVE_POST=0"
set "RESUME_PREINPUT=0"
set "POST_SAVE_RESUME_ARGUMENT="
set "CHECK_LABEL=Windows native-save test"

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
if /i "%~1"=="--save-post" goto option_save_post
if /i "%~1"=="--resume-preinput" goto option_resume_preinput
>&2 echo Unsupported test launcher argument. Use the supplied CMD files.
exit /b 2

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
if "%CANDIDATE_FINISH%"=="0" if "%CANDIDATE_SAVE_TEST%"=="0" if "%CANDIDATE_TEST%"=="0" if "%WATCH_TEST%"=="0" if "%READ_ONLY_LIST_INSPECTION%"=="0" if "%READ_ONLY_INSPECTION%"=="0" if "%SAVE_POST%"=="0" >>"%LOG_FILE%" echo This file contains setup output and the synthetic-image test result.
if "%SAVE_POST%"=="1" >>"%LOG_FILE%" echo Single-post native image saving requires review in the dedicated Chrome app window.
if "%RESUME_PREINPUT%"=="1" >>"%LOG_FILE%" echo Verified pre-input resume was explicitly requested. Generic native recovery will not run.
if "%READ_ONLY_INSPECTION%"=="1" >>"%LOG_FILE%" echo Read-only public-page DOM inspection. No image saving is attempted.
if "%READ_ONLY_LIST_INSPECTION%"=="1" >>"%LOG_FILE%" echo Read-only public search-list DOM inspection in a headless browser. No image saving or monitoring is attempted.
if "%WATCH_TEST%"=="1" >>"%LOG_FILE%" echo Bounded public-list discovery trial: two cycles in headless mode, about two minutes after setup.
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
if "%CANDIDATE_FINISH%"=="0" >>"%LOG_FILE%" echo Selected browser: %TEST_BROWSER%
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
echo Running two list-discovery cycles in headless %TEST_BROWSER%. Allow about two minutes after setup.
echo This bounded trial persists a separate watch baseline and candidates; it leaves image jobs and files untouched.
echo No continuous program or native image saving starts. One TXT will open automatically when the trial ends.
>>"%LOG_FILE%" echo STAGE: watch_test
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor watch-test --work-root "%LOCALAPPDATA%\ImageMonitorWatch" --browser "%TEST_BROWSER%" >>"%LOG_FILE%" 2>&1
set "WATCH_TEST_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Bounded list-watch trial exit code: %WATCH_TEST_CODE%
if not "%WATCH_TEST_CODE%"=="0" goto failed
>>"%LOG_FILE%" echo RESULT: COMPLETED_OR_SAFELY_WAITING - BOUNDED_LIST_WATCH_TRIAL
>>"%LOG_FILE%" echo See the JSON status above for completed, waiting, or busy. No images were saved.
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
if "%CANDIDATE_FINISH%"=="1" >>"%LOG_FILE%" echo RESULT: STOPPED - COMPLETED_CANDIDATE_VERIFICATION. Existing files and unresolved state are preserved.
if "%CANDIDATE_FINISH%"=="1" >>"%LOG_FILE%" echo Send this TXT for diagnosis. No browser was launched or forced closed and no image was saved again.
if "%CANDIDATE_SAVE_TEST%"=="1" >>"%LOG_FILE%" echo RESULT: STOPPED - REVIEWED_CANDIDATE_NATIVE_SAVE. No automatic retry or recovery was performed.
if "%CANDIDATE_SAVE_TEST%"=="1" >>"%LOG_FILE%" echo Send this TXT file for diagnosis. Leave any pending browser unchanged for inspection.
if "%SAVE_POST%"=="1" >>"%LOG_FILE%" echo RESULT: STOPPED - SINGLE_POST_NATIVE_SAVE. No automatic retry was performed.
if "%SAVE_POST%"=="1" >>"%LOG_FILE%" echo Send this TXT file for diagnosis. Leave any pending browser unchanged for inspection.
if "%CANDIDATE_FINISH%"=="0" if "%CANDIDATE_SAVE_TEST%"=="0" if "%CANDIDATE_TEST%"=="0" if "%WATCH_TEST%"=="0" if "%READ_ONLY_LIST_INSPECTION%"=="0" if "%READ_ONLY_INSPECTION%"=="0" if "%SAVE_POST%"=="0" >>"%LOG_FILE%" echo RESULT: FAILED - automation stopped; no automatic retry was performed.
if "%CANDIDATE_FINISH%"=="0" if "%CANDIDATE_SAVE_TEST%"=="0" if "%CANDIDATE_TEST%"=="0" if "%WATCH_TEST%"=="0" if "%READ_ONLY_LIST_INSPECTION%"=="0" if "%READ_ONLY_INSPECTION%"=="0" if "%SAVE_POST%"=="0" >>"%LOG_FILE%" echo Send this TXT file for diagnosis. Leave any pending test browser unchanged for inspection.
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
