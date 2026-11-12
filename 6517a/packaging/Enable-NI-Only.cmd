@echo off
setlocal
"%~dp0runtime\python.exe" -I -B "%~dp0tools\install_ni_only.py"
set "extension_result=%errorlevel%"
echo Optional extension installation result: %extension_result%
pause
exit /b %extension_result%
