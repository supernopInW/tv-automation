@echo off
title Upload to GitHub - supernopInW/tv-automation
echo =======================================================
echo     Uploading Project to GitHub
echo     Target: https://github.com/supernopInW/tv-automation.git
echo =======================================================
echo.

git init
git add .
git commit -m "Initial commit - DOAE T&V Automation System (Sida & Nationwide)"
git branch -M main
git remote remove origin >nul 2>&1
git remote add origin https://github.com/supernopInW/tv-automation.git
git push -u origin main --force

echo.
echo =======================================================
echo Execution completed!
echo Check your repository at: https://github.com/supernopInW/tv-automation
echo =======================================================
pause
