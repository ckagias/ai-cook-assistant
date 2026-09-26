@echo off
rem Double-click to set up and open the app window (runs setup-window.ps1 without changing
rem the machine-wide PowerShell script policy).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-window.ps1" %*
if errorlevel 1 pause
