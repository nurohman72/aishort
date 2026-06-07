@echo off
REM ==========================================
REM NurClipper - Start Script
REM ==========================================

echo ==========================================
echo   NurClipper - AI YouTube Shorts Automation
echo ==========================================
echo.

REM Check if virtual environment exists
if not exist "venv\" (
    echo [ERROR] Virtual environment not found!
    echo Please run the following commands first:
    echo.
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in virtual environment!
    pause
    exit /b 1
)

echo [INFO] Starting NurClipper Web Server...
echo ==========================================
echo.
echo Server will start on: http://localhost:8000
echo.
echo Press Ctrl+C to stop the server
echo.

REM Start the web server
python web_server.py

REM Deactivate virtual environment when done
deactivate

pause
