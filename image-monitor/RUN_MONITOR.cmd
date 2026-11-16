@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Open the local list-monitoring screen; start and stop watching there.
call "%~dp0RUN_WINDOWS_TEST.cmd" --monitor --chrome
exit /b %ERRORLEVEL%
