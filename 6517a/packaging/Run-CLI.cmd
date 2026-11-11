@echo off
setlocal DisableDelayedExpansion
"%~dp0runtime\python.exe" -I "%~dp0tools\launch.py" cli %*
exit /b %errorlevel%
