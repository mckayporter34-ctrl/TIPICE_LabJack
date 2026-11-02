@echo off
setlocal
REM Run script for Windows
cd /d "%~dp0" || exit /b 1

if not exist ".venv\Scripts\python.exe" (
    echo Please run setup.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" core\runtime.py
if errorlevel 1 (
    pause
    exit /b 1
)

echo Launching application...
".venv\Scripts\python.exe" main.py
set "app_exit=%errorlevel%"
pause
exit /b %app_exit%
