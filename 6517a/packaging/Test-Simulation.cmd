@echo off
setlocal DisableDelayedExpansion
"%~dp0runtime\python.exe" -I -B "%~dp0tools\launch.py" simulate
set "test_result=%errorlevel%"
echo Simulation result code: %test_result%
pause
exit /b %test_result%
