@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Review one public post, then explicitly start native saving in Chrome.
call "%~dp0RUN_WINDOWS_TEST.cmd" --save-post --chrome
exit /b %ERRORLEVEL%
