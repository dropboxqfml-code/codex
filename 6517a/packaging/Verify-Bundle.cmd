@echo off
setlocal DisableDelayedExpansion
"%~dp0runtime\python.exe" -I "%~dp0tools\verify_bundle.py"
set "verify_result=%errorlevel%"
pause
exit /b %verify_result%
