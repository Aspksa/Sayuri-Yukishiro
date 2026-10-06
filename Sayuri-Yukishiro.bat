@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Sayuri Yukishiro

echo ============================================================
echo   Sayuri Yukishiro v0.1.0
echo   Portable startup + diagnostics
echo ============================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launcher.ps1" -Root "%~dp0" -PreflightOnly
if errorlevel 1 (
    echo.
    echo [ERROR] Preflight failed. Sayuri was not started.
    pause
    exit /b 1
)

echo.
echo [OK] Diagnostics passed. Starting Sayuri in the system tray...
start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0scripts\launcher.ps1" -Root "%~dp0" -TrayHost -SkipPreflight

exit /b 0
