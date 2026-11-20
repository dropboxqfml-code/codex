@echo off
setlocal EnableExtensions DisableDelayedExpansion
call "%~dp0RUN_WINDOWS_TEST.cmd" --auto-collect-once
exit /b %ERRORLEVEL%
