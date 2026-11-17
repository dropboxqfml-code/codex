@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Verify completed local-monitor candidate files without downloading them again.
call "%~dp0RUN_WINDOWS_TEST.cmd" --monitor-finish --chrome
exit /b %ERRORLEVEL%
