@echo off
title T&V Automation Installer
echo =======================================================
echo     T&V Automation Application Installer
echo =======================================================
echo.
echo [1/4] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Python is not installed or not added to your system PATH.
    echo Please install Python 3.10 or newer from python.org and check
    echo "Add Python to PATH" during installation.
    echo.
    pause
    exit /b
)

echo [2/4] Creating Virtual Environment (venv)...
python -m venv venv
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b
)

echo [3/4] Installing required libraries (Flask, Playwright, Pandas, xlutils)...
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install pandas playwright flask xlrd xlwt xlutils
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to install libraries.
    pause
    exit /b
)

echo [4/4] Installing Chromium browser for Playwright...
playwright install chromium
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to install Playwright browser.
    pause
    exit /b
)

echo.
echo =======================================================
echo     INSTALLATION COMPLETED SUCCESSFULLY!
echo =======================================================
echo.
echo You can now run the application by double-clicking:
echo T^&V_Automation_App.bat
echo.
pause
