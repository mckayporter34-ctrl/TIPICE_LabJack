@echo off
setlocal
REM Setup script for Windows
cd /d "%~dp0" || exit /b 1

if exist ".venv" goto :existing_env

REM Prefer the lab's Python 3.9, while accepting newer compatible installations.
py -3.9 core\runtime.py >nul 2>&1
if not errorlevel 1 goto :create_with_py
python3.9 core\runtime.py >nul 2>&1
if not errorlevel 1 goto :create_with_python39
python core\runtime.py >nul 2>&1
if not errorlevel 1 goto :create_with_python
py -3 core\runtime.py >nul 2>&1
if not errorlevel 1 goto :create_with_py3

echo Python 3.9.12 or newer is required. Install Python from https://www.python.org/downloads/
echo Include the Python launcher or add Python to PATH, then rerun setup.bat.
goto :failed

:create_with_py
echo Creating Python 3.9 virtual environment...
py -3.9 -m venv .venv
if errorlevel 1 goto :failed
goto :check_env

:create_with_python39
echo Creating Python 3.9 virtual environment...
python3.9 -m venv .venv
if errorlevel 1 goto :failed
goto :check_env

:create_with_python
echo Creating Python virtual environment...
python -m venv .venv
if errorlevel 1 goto :failed
goto :check_env

:create_with_py3
echo Creating Python virtual environment...
py -3 -m venv .venv
if errorlevel 1 goto :failed
goto :check_env

:existing_env
if exist ".venv\Scripts\python.exe" goto :check_env
echo The existing .venv is incomplete or was created for another operating system.
echo Rename .venv to an unused backup name, then rerun setup.bat.
goto :failed

:check_env
".venv\Scripts\python.exe" core\runtime.py
if errorlevel 1 goto :failed

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo Setup complete! You can now use run.bat to launch the application.
pause
exit /b 0

:failed
echo Setup failed. Review the error above before running the application.
pause
exit /b 1
