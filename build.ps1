# Baut dist\SmartMouse.exe – eine einzelne Datei, auf dem Ziel-PC ist kein Python nötig.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path .venv\Scripts\python.exe)) { python -m venv .venv }
.\.venv\Scripts\python -m pip install -q -r requirements.txt pyinstaller
.\.venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name SmartMouse `
  --add-data "static;static" --icon static\icon-192.png --hidden-import pystray._win32 server.py
Write-Host "Fertig: dist\SmartMouse.exe"
