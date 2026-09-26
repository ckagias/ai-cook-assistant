@echo off
rem Runs setup.ps1 without changing the machine-wide PowerShell script policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
if errorlevel 1 pause
