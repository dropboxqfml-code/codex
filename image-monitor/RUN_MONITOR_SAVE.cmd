@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Natively save one inspected local-monitor candidate through the dedicated Chrome window.
call "%~dp0RUN_WINDOWS_TEST.cmd" --monitor-save-test --chrome
exit /b %ERRORLEVEL%
