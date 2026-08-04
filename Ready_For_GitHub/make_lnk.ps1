
$ws = New-Object -ComObject WScript.Shell
$sh = $ws.CreateShortcut('C:\Users\Admin\OneDrive\Desktop\T&V Automation.lnk')
$sh.TargetPath = 'C:\Users\Admin\OneDrive\Desktop\Run_TV_Automation.bat'
$sh.WorkingDirectory = 'c:\Users\Admin\Downloads\tv_automation'
$sh.Description = 'Launch DOAE T&V Automation System'
$sh.Save()
