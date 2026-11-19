@echo off
setlocal EnableExtensions DisableDelayedExpansion
call "%~dp0RUN_WINDOWS_TEST.cmd" --monitor-resume-once
exit /b %ERRORLEVEL%
