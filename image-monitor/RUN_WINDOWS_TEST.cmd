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
set "CHECK_LABEL=Windows native-save test"

:parse_arguments
if "%~1"=="" goto arguments_ready
if /i "%~1"=="--chrome" goto option_chrome
if /i "%~1"=="--recover-closed" goto option_recover
if /i "%~1"=="--find-uv" goto option_lookup
if /i "%~1"=="--site-inspect" goto option_site_inspection
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

:arguments_ready
if "%UV_LOOKUP_ONLY%"=="1" goto lookup_only
if "%READ_ONLY_INSPECTION%"=="1" if "%RECOVER_CLOSED%"=="1" goto incompatible_options
goto new_log

:incompatible_options
>&2 echo Read-only site inspection cannot recover native-save state.
exit /b 2

:new_log
set "LOG_FILE=%~dp0WINDOWS_TEST_RESULT-%RANDOM%-%RANDOM%.txt"
if exist "%LOG_FILE%" goto new_log
>"%LOG_FILE%" echo Image Monitor - %CHECK_LABEL%
if errorlevel 1 goto log_unavailable
if "%READ_ONLY_INSPECTION%"=="0" >>"%LOG_FILE%" echo This file contains setup output and the synthetic-image test result.
if "%READ_ONLY_INSPECTION%"=="1" >>"%LOG_FILE%" echo Read-only public-page DOM inspection. No image saving is attempted.
>>"%LOG_FILE%" echo Selected browser: %TEST_BROWSER%
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
if "%READ_ONLY_INSPECTION%"=="1" goto start_site_inspection
rem Recovery is only enabled by the dedicated, user-initiated retry launcher.
if "%RECOVER_CLOSED%"=="0" goto start_probe
echo Checking that the previous test browser is closed...
>>"%LOG_FILE%" echo STAGE: recover_previous_probe
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor native-recover --confirm-browser-closed >>"%LOG_FILE%" 2>&1
set "RECOVERY_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Explicit recovery exit code: %RECOVERY_CODE%
if not "%RECOVERY_CODE%"=="0" goto failed

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
if "%READ_ONLY_INSPECTION%"=="0" >>"%LOG_FILE%" echo RESULT: FAILED - automation stopped; no automatic retry was performed.
if "%READ_ONLY_INSPECTION%"=="0" >>"%LOG_FILE%" echo Send this TXT file for diagnosis. Leave any pending test browser unchanged for inspection.
if "%READ_ONLY_INSPECTION%"=="1" >>"%LOG_FILE%" echo RESULT: FAILED - READ_ONLY_SITE_INSPECTION. No image saving was attempted.
if "%READ_ONLY_INSPECTION%"=="1" >>"%LOG_FILE%" echo Send this TXT file for diagnosis. Native-save recovery was not performed.
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
