@echo off
REM Get the directory where this batch file is located
set "current_dir=%~dp0"

REM Path to the Python script to run
set "script_to_run=%current_dir%manager.py"

REM Path to virtual environment's Python executable
set "venv_python=%current_dir%myenv\Scripts\python.exe"

REM Run the Python script
"%venv_python%" "%script_to_run%"

REM Keep the window open
pause
