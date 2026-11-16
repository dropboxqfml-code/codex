@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Verify already completed candidate files and resolve only a confirmed closed save.
call "%~dp0RUN_WINDOWS_TEST.cmd" --candidate-finish
exit /b %ERRORLEVEL%
