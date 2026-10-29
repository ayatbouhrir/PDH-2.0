@echo off
setlocal
powershell.exe -NoProfile -File "%~dp0scripts\bootstrap-windows.ps1" %*
exit /b %ERRORLEVEL%
