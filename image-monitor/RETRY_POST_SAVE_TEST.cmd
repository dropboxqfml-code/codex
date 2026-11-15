@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Run only after manually closing the previous dedicated browser.
call "%~dp0RUN_WINDOWS_TEST.cmd" --save-post --chrome --recover-closed
exit /b %ERRORLEVEL%
