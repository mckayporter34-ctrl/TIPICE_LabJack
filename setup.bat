@echo off
setlocal
REM Setup script for Windows
cd /d "%~dp0" || exit /b 1

if exist ".venv" goto :existing_env

REM Prefer the Windows Python launcher so another Python on PATH is not used.
py -3.14 core\runtime.py >nul 2>&1
if not errorlevel 1 goto :create_with_py
python3.14 core\runtime.py >nul 2>&1
if not errorlevel 1 goto :create_with_python314
python core\runtime.py >nul 2>&1
if not errorlevel 1 goto :create_with_python

echo Python 3.14.x is required. Install Python 3.14 from https://www.python.org/downloads/
echo Include the Python launcher or add Python 3.14 to PATH, then rerun setup.bat.
goto :failed

:create_with_py
echo Creating Python 3.14 virtual environment...
py -3.14 -m venv .venv
if errorlevel 1 goto :failed
goto :check_env

:create_with_python314
echo Creating Python 3.14 virtual environment...
python3.14 -m venv .venv
if errorlevel 1 goto :failed
goto :check_env

:create_with_python
echo Creating Python 3.14 virtual environment...
python -m venv .venv
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
