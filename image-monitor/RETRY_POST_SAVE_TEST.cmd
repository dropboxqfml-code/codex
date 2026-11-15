@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Resume only the verified pre-input failure after closing its dedicated browser.
call "%~dp0RUN_WINDOWS_TEST.cmd" --save-post --chrome --resume-preinput
exit /b %ERRORLEVEL%
