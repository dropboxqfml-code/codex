@echo off
setlocal DisableDelayedExpansion
if not exist "%~dp0runtime\pythonw.exe" (
  echo Bundled Windows Python was not found. Extract the entire ZIP first.
  pause
  exit /b 2
)
start "6517A trial program" "%~dp0runtime\pythonw.exe" -I -B "%~dp0tools\launch.py" gui
exit /b %errorlevel%
