@echo off
REM Run script for Windows

echo Activating virtual environment...
call .venv\Scripts\activate

echo Launching application...
python main.py
pause
