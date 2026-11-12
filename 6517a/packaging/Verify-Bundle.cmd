@echo off
setlocal DisableDelayedExpansion
echo [START] Checking bundle files. This may take a while.
if not exist "%~dp0runtime\python.exe" (
  echo [FAIL] Bundled Python was not found. Extract the entire ZIP first.
  pause
  exit /b 2
)
if not exist "%~dp0tools\verify_bundle.py" (
  echo [FAIL] Verification tool was not found. Extract the entire ZIP first.
  pause
  exit /b 2
)
"%~dp0runtime\python.exe" -I -B -u "%~dp0tools\verify_bundle.py" --progress --save-report
set "verify_result=%errorlevel%"
if "%verify_result%"=="0" (
  echo [PASS] Bundle file integrity verified.
) else (
  echo [FAIL] Bundle check failed. Result code: %verify_result%
  echo Read the error details above.
)
pause
exit /b %verify_result%
