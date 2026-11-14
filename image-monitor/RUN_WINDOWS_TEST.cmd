@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
if errorlevel 1 exit /b 1
if /i "%~1"=="--find-uv" goto lookup_only

:new_log
set "LOG_FILE=%~dp0WINDOWS_TEST_RESULT-%RANDOM%-%RANDOM%.txt"
if exist "%LOG_FILE%" goto new_log
>"%LOG_FILE%" echo Image Monitor - Windows native-save test
if errorlevel 1 goto log_unavailable
>>"%LOG_FILE%" echo This file contains setup output and the synthetic-image test result.
if not exist "pyproject.toml" goto missing_project
if not exist "uv.lock" goto missing_project
if not defined LOCALAPPDATA goto missing_appdata

echo Preparing the test. Please wait; first setup can take several minutes.
call :find_uv
if defined UV_EXE goto uv_ready
echo Installing uv from the official WinGet package...
>>"%LOG_FILE%" echo STAGE: install_uv
where winget.exe >nul 2>&1
if errorlevel 1 goto missing_winget
winget.exe install --id astral-sh.uv --exact --source winget --accept-source-agreements --accept-package-agreements --disable-interactivity >>"%LOG_FILE%" 2>&1
set "INSTALL_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo WinGet exit code: %INSTALL_CODE%
if not "%INSTALL_CODE%"=="0" goto failed
call :find_uv
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
echo Starting the dedicated test browser. Keep that browser in front until the test ends.
>>"%LOG_FILE%" echo STAGE: native_probe
"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 --managed-python image-monitor native-probe --work-root "%LOCALAPPDATA%\ImageMonitorProbe" --browser edge >>"%LOG_FILE%" 2>&1
set "PROBE_CODE=%ERRORLEVEL%"
>>"%LOG_FILE%" echo Native probe exit code: %PROBE_CODE%
if not "%PROBE_CODE%"=="0" goto failed
>>"%LOG_FILE%" echo RESULT: SUCCESS
>>"%LOG_FILE%" echo The synthetic-image native-save test passed. Site monitoring was not started.
echo Test passed. Opening the result file.
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
>>"%LOG_FILE%" echo RESULT: FAILED - automation stopped; no automatic retry or recovery was performed.
>>"%LOG_FILE%" echo Send this TXT file for diagnosis. Leave any pending test browser unchanged for inspection.
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
for /f "usebackq delims=" %%U in (`call "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -Command "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); $OutputEncoding = [Console]::OutputEncoding; $found = @(Get-Command uv.exe -CommandType Application -ErrorAction SilentlyContinue)[0]; if (-not $found) { $env:Path = [Environment]::ExpandEnvironmentVariables([Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')); $found = @(Get-Command uv.exe -CommandType Application -ErrorAction SilentlyContinue)[0] }; if ($found) { [Console]::WriteLine($found.Source) }" 2^>nul`) do if not defined UV_EXE if exist "%%~fU" set "UV_EXE=%%~fU"
if defined UV_EXE exit /b 0
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" set "UV_EXE=%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe"
if defined UV_EXE exit /b 0
if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.local\bin\uv.exe"
if defined UV_EXE exit /b 0
if exist "%ProgramFiles%\WinGet\Links\uv.exe" set "UV_EXE=%ProgramFiles%\WinGet\Links\uv.exe"
if defined UV_EXE exit /b 0
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv_*") do for /r "%%~fD" %%U in (uv.exe) do if not defined UV_EXE if exist "%%~fU" set "UV_EXE=%%~fU"
exit /b 0
