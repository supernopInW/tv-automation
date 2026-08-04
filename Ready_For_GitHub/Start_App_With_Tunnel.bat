@echo off
title T&V Automation App with Tunnel
echo =======================================================
echo     Starting T&V Automation App ^& Ngrok Tunnel
echo =======================================================
echo.
echo Starting Flask application...
start cmd /k ".\venv\Scripts\python.exe app.py"

echo Waiting 5 seconds for the app to start...
timeout /t 5 /nobreak >nul

echo Starting Ngrok Tunnel (Persistent Link)...
start cmd /k ".\ngrok.exe http --domain=unneeded-extending-exile.ngrok-free.dev 5000"

echo.
echo =======================================================
echo Both services have been started in separate windows!
echo Your persistent link is:
echo https://unneeded-extending-exile.ngrok-free.dev
echo =======================================================
pause
