@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Run a bounded public-list discovery trial in headless Chrome.
call "%~dp0RUN_WINDOWS_TEST.cmd" --watch-test --chrome
exit /b %ERRORLEVEL%
