@echo off
setlocal EnableExtensions

REM Wrapper for the PowerShell implementation.
REM Usage:
REM   pack_output_zip.bat           -> auto thread count
REM   pack_output_zip.bat 6         -> fixed thread count

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "PS_SCRIPT=%SCRIPT_DIR%\pack_output_zip.ps1"

if not exist "%PS_SCRIPT%" (
  echo [ERROR] Missing script: %PS_SCRIPT%
  exit /b 1
)

if "%~1"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -Threads %~1
)

exit /b %ERRORLEVEL%
