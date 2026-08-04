@echo off
title DOAE T&V Automation App
echo =======================================================
echo     DOAE T&V Automation Dashboard Application
echo =======================================================
echo.
echo Starting Application Server...
echo.

:: Wait 3 seconds then open the web page in the default browser
start /b "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:5000"

:: Start Flask server in the foreground
set PORT=5000
"c:\Users\Admin\Downloads\tv_automation\venv\Scripts\python.exe" "c:\Users\Admin\Downloads\tv_automation\app.py"

echo.
echo Server stopped.
pause
