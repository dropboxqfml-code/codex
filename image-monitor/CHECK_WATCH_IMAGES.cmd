@echo off
setlocal EnableExtensions DisableDelayedExpansion
call "%~dp0RUN_WINDOWS_TEST.cmd" --watch-images-check
exit /b %ERRORLEVEL%
