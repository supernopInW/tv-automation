@echo off
title Push to GitHub Repository
echo =======================================================
echo     Uploading Project to GitHub
echo     Target: https://github.com/supernopInW/tv-automation.git
echo =======================================================
echo.

set GIT_PATH="C:\Program Files\Git\cmd\git.exe"
if exist %GIT_PATH% (
    set GIT_CMD=%GIT_PATH%
) else (
    set GIT_CMD=git
)

%GIT_CMD% init
%GIT_CMD% add .
%GIT_CMD% commit -m "Initial commit - DOAE T&V Automation System (Sida & Nationwide)"
%GIT_CMD% branch -M main
%GIT_CMD% remote remove origin >nul 2>&1
%GIT_CMD% remote add origin https://github.com/supernopInW/tv-automation.git
%GIT_CMD% push -u origin main --force

echo.
echo =======================================================
echo Completed! Check your repo at: https://github.com/supernopInW/tv-automation
echo =======================================================
pause
