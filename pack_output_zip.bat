@echo off
setlocal EnableExtensions

REM Wrapper for the PowerShell implementation.
REM Usage:
REM   pack_output_zip.bat           -> auto thread count
REM   pack_output_zip.bat 6         -> fixed thread count

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "PS_SCRIPT=%SCRIPT_DIR%\pack_output_zip.ps1"
set "LOG_FILE=%SCRIPT_DIR%\pack_output_zip.last.log"

echo [INFO] Starting build...
echo [INFO] Log file: %LOG_FILE%

if not exist "%PS_SCRIPT%" (
  echo [ERROR] Missing script: %PS_SCRIPT%
  pause
  exit /b 1
)

if "%~1"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -LogFile "%LOG_FILE%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -Threads %~1 -LogFile "%LOG_FILE%"
)

set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo [ERROR] Build failed, see log: %LOG_FILE%
  pause
)

exit /b %RC%
