@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Inspect the public page read-only in a dedicated Chrome session.
call "%~dp0RUN_WINDOWS_TEST.cmd" --site-inspect --chrome
exit /b %ERRORLEVEL%
