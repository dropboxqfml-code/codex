@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Inspect up to two stored candidate posts in headless Chrome.
call "%~dp0RUN_WINDOWS_TEST.cmd" --candidate-test --chrome
exit /b %ERRORLEVEL%
