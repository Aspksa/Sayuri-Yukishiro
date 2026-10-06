@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Sayuri Yukishiro

set "SAYURI_VERSION=unknown"
if exist "%~dp0VERSION" set /p SAYURI_VERSION=<"%~dp0VERSION"

echo ============================================================
echo   Sayuri Yukishiro v%SAYURI_VERSION%
echo   Portable startup + diagnostics
echo ============================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launcher.ps1" -PreflightOnly
if errorlevel 1 (
    echo.
    echo [ERROR] Preflight failed. Sayuri was not started.
    pause
    exit /b 1
)

echo.
echo [OK] Diagnostics passed. Starting Sayuri in the system tray...
start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0scripts\launcher.ps1" -TrayHost -SkipPreflight

exit /b 0
