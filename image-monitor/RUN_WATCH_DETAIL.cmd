@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Inspect one pending post from the latest verified trial scan.
call "%~dp0RUN_WINDOWS_TEST.cmd" --watch-detail
exit /b %ERRORLEVEL%
