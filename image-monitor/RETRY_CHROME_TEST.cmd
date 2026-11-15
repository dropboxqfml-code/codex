@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Run only after closing the previous dedicated test browser, as the TXT guide states.
call "%~dp0RUN_WINDOWS_TEST.cmd" --chrome --recover-closed
exit /b %ERRORLEVEL%
