@echo off
setlocal EnableExtensions DisableDelayedExpansion
call "%~dp0RUN_WINDOWS_TEST.cmd" --test-list-recovery
exit /b %ERRORLEVEL%
