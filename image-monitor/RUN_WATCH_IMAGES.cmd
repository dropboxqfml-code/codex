@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Check recent watch candidates and offer one eligible post for native saving.
call "%~dp0RUN_WINDOWS_TEST.cmd" --watch-images
exit /b %ERRORLEVEL%
