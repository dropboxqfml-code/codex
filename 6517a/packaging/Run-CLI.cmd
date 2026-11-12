@echo off
setlocal DisableDelayedExpansion
"%~dp0runtime\python.exe" -I -B "%~dp0tools\launch.py" cli %*
exit /b %errorlevel%
