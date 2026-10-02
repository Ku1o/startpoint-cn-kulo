@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CN StarPoint - Console

echo.
echo ========================================
echo   CN StarPoint foreground console mode
echo ========================================
echo.
echo The server logs will remain visible in this window.
echo Closing this window stops the server.
echo.

rem better-sqlite3 and the current package lock require Node 24 (ABI 137).
rem Keep the system Node installation untouched; use the portable runtime here.
if not defined STARPOINT_NODE24 set "STARPOINT_NODE24=%~dp0tools\node24"
if not exist "%STARPOINT_NODE24%\node.exe" (
    echo [ERROR] Node.js 24 was not found: %STARPOINT_NODE24%\node.exe
    echo Put the portable Node 24 runtime in tools\node24 or set STARPOINT_NODE24.
    set "exitCode=1"
    goto :finish
)

set "nodeExecutable=%STARPOINT_NODE24%\node.exe"
for /f "tokens=1 delims=v." %%V in ('"%nodeExecutable%" --version') do set "nodeMajor=%%V"
if not defined nodeMajor (
    echo [ERROR] Could not read the Node.js version from: %nodeExecutable%
    set "exitCode=1"
    goto :finish
)
if %nodeMajor% LSS 24 (
    echo [ERROR] Node.js 24 or newer is required; detected major version %nodeMajor%.
    set "exitCode=1"
    goto :finish
)

if not exist ".env" (
    echo [ERROR] .env was not found in: %CD%
    set "exitCode=1"
    goto :finish
)

if not exist "out\cn-server.js" (
    echo [ERROR] out\cn-server.js was not found.
    echo Run npm run build first, then start the server again.
    set "exitCode=1"
    goto :finish
)

set "serverTemp=%CD%\tmp\cn-server"
if not exist "%serverTemp%" mkdir "%serverTemp%"
if errorlevel 1 (
    echo [ERROR] Failed to create the stable temp directory: %serverTemp%
    set "exitCode=1"
    goto :finish
)
set "TEMP=%serverTemp%"
set "TMP=%serverTemp%"

echo Starting CN StarPoint...
echo HTTP: 8001    TCP: 8003
echo Temp: %serverTemp%
echo.

set "LOG_LEVEL=info"
set "GACHA_VERBOSE_LOGS=false"
"%nodeExecutable%" --env-file=.env out/cn-server.js
set "exitCode=%errorlevel%"

echo.
echo Server process exited with code %exitCode%.

:finish
echo.
pause
exit /b %exitCode%
