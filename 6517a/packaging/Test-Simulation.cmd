@echo off
setlocal DisableDelayedExpansion
echo [START] Testing simulation and result storage.
if not exist "%~dp0runtime\python.exe" (
  echo [FAIL] Bundled Python was not found. Extract the entire ZIP first.
  pause
  exit /b 2
)
if not exist "%~dp0tools\launch.py" (
  echo [FAIL] Simulation launcher was not found. Extract the entire ZIP first.
  pause
  exit /b 2
)
"%~dp0runtime\python.exe" -I -B -u "%~dp0tools\launch.py" simulate
set "test_result=%errorlevel%"
if "%test_result%"=="0" (
  echo [PASS] Simulation completed. Results are in the results folder.
) else (
  echo [FAIL] Simulation failed. Result code: %test_result%
  echo Read the error details above.
)
pause
exit /b %test_result%
