@echo off
setlocal DisableDelayedExpansion
if "%~1"=="" (
  "%~dp0runtime\python.exe" -I -B "%~dp0tools\launch.py" diagnose
) else if "%~2"=="" (
  "%~dp0runtime\python.exe" -I -B "%~dp0tools\launch.py" diagnose "%~1"
) else (
  "%~dp0runtime\python.exe" -I -B "%~dp0tools\launch.py" diagnose "%~1" "%~2"
)
set "check_result=%errorlevel%"
echo Connection check result code: %check_result%
pause
exit /b %check_result%
