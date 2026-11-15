@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Use the dedicated Chrome test profile; never fall back to another browser.
call "%~dp0RUN_WINDOWS_TEST.cmd" --chrome
exit /b %ERRORLEVEL%
