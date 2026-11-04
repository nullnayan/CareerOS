@echo off
title CareerOS - Start
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\nayan\Downloads\careeros_scaffold\careeros\scripts\CareerOS-Control.ps1" -Mode Start -ConfigFile "%~dp0CareerOS.toml"
if errorlevel 1 pause
