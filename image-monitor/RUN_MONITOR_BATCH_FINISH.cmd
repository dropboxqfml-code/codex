@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Reconcile only existing completed monitor batch files without saving again.
call "%~dp0RUN_WINDOWS_TEST.cmd" --monitor-batch-finish --chrome
exit /b %ERRORLEVEL%
