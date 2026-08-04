$ErrorActionPreference = "SilentlyContinue"
# Resolve project root from this script (no Thai literals in file = encoding-safe)
$wd = Split-Path -Parent $PSScriptRoot
if (-not $wd) { $wd = (Get-Location).Path }
$py = Join-Path $wd "venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $py)) { $py = "python" }

$conns = Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue
if ($conns) {
  $conns | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
    if ($_ -and $_ -gt 0) { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
  }
}
Start-Sleep -Seconds 1

Write-Output ("WD=" + $wd)
Write-Output ("PY=" + $py)
Start-Process -FilePath $py -ArgumentList "app.py" -WorkingDirectory $wd -WindowStyle Hidden
Start-Sleep -Seconds 4

# Verify HTML via Python (UTF-8 safe for Thai content)
$verifyPy = Join-Path $wd "scripts\_verify_home.py"
& $py $verifyPy
