@echo off
rem Double-click to open the Cooking Assistant (setup runs by itself the first time only).
rem Runs start.ps1 without changing the machine-wide PowerShell script policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 pause
