@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Verify completed monitor saves and natively save at most two new inspected candidates.
call "%~dp0RUN_WINDOWS_TEST.cmd" --monitor-save-batch --chrome
exit /b %ERRORLEVEL%
