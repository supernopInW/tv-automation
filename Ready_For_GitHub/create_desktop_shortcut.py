import os
import subprocess

desktop_path = os.path.join(os.environ['USERPROFILE'], 'OneDrive', 'Desktop')
if not os.path.exists(desktop_path):
    desktop_path = os.path.join(os.environ['USERPROFILE'], 'Desktop')

bat_file = os.path.join(desktop_path, 'Run_TV_Automation.bat')

# Ensure batch file exists and has correct content
bat_content = """@echo off
chcp 65001 >nul
title DOAE T&V Automation App
cd /d "c:\\Users\\Admin\\Downloads\\tv_automation"
echo =======================================================
echo     DOAE T&V Automation Dashboard Application
echo =======================================================
echo.
echo กำลังเริ่มต้นเปิดระบบ T&V Automation...
echo.

start /b "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:5000"

set PORT=5000
"c:\\Users\\Admin\\Downloads\\tv_automation\\venv\\Scripts\python.exe" "c:\\Users\\Admin\\Downloads\\tv_automation\\app.py"

pause
"""

with open(bat_file, 'w', encoding='utf-8') as f:
    f.write(bat_content)

# Clean up old file if exists
old_bat = os.path.join(desktop_path, 'เปิดระบบ T&V Automation.bat')
if os.path.exists(old_bat):
    try:
        os.remove(old_bat)
    except Exception:
        pass

# Create shortcut file
shortcut_path = os.path.join(desktop_path, 'T&V Automation.lnk')

ps_cmd = f"""
$ws = New-Object -ComObject WScript.Shell
$sh = $ws.CreateShortcut('{shortcut_path}')
$sh.TargetPath = '{bat_file}'
$sh.WorkingDirectory = 'c:\\Users\\Admin\\Downloads\\tv_automation'
$sh.Description = 'Launch DOAE T&V Automation System'
$sh.Save()
"""

with open('c:\\Users\\Admin\\Downloads\\tv_automation\\make_lnk.ps1', 'w', encoding='utf-8-sig') as f:
    f.write(ps_cmd)

subprocess.run(['powershell', '-ExecutionPolicy', 'Bypass', '-File', 'c:\\Users\\Admin\\Downloads\\tv_automation\\make_lnk.ps1'], check=True)
print("Desktop shortcuts created successfully!")
