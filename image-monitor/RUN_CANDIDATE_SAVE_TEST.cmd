@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Review and natively save one previously inspected candidate in Chrome.
call "%~dp0RUN_WINDOWS_TEST.cmd" --candidate-save-test --chrome
exit /b %ERRORLEVEL%
