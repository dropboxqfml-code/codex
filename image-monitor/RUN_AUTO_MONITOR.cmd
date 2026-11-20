@echo off
setlocal EnableExtensions DisableDelayedExpansion
call "%~dp0RUN_WINDOWS_TEST.cmd" --auto-monitor
exit /b %ERRORLEVEL%
