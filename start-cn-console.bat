@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CN StarPoint - Console

set "LOG_LEVEL=info"
set "GACHA_VERBOSE_LOGS=false"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-cn-logged.ps1" -Foreground
set "exitCode=%errorlevel%"
echo.
echo Server process exited with code %exitCode%.
pause
exit /b %exitCode%
