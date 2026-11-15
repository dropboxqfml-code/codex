@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Inspect the public search list read-only in headless Chrome.
call "%~dp0RUN_WINDOWS_TEST.cmd" --list-inspect --chrome
exit /b %ERRORLEVEL%
