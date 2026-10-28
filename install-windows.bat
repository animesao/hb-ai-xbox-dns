@echo off
chcp 65001 >nul
title Установка HB AI · Smart DNS
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-windows.ps1"
if %errorlevel% neq 0 (
    echo.
    echo Ошибка при установке.
    pause
)
