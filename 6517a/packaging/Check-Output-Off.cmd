@echo off
setlocal DisableDelayedExpansion
if "%~1"=="" (
  echo Usage: Check-Output-Off.cmd GPIB0::27::INSTR [VISA-backend]
  echo This explicitly requests protective OUTPUT OFF. It never requests OUTPUT ON.
  pause
  exit /b 2
)
if "%~2"=="" (
  "%~dp0runtime\python.exe" -I -B "%~dp0tools\launch.py" confirm-off "%~1"
) else (
  "%~dp0runtime\python.exe" -I -B "%~dp0tools\launch.py" confirm-off "%~1" "%~2"
)
set "off_result=%errorlevel%"
echo OFF check result code: %off_result%
pause
exit /b %off_result%
