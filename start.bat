@echo off
rem Startet SmartMouse im Hintergrund (Symbol unten rechts im Infobereich).
rem Beim ersten Mal wird eine eigene Python-Umgebung eingerichtet.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Richte Python-Umgebung ein...
  python -m venv .venv || (echo Python 3 fehlt: https://www.python.org/downloads/ & pause & exit /b 1)
)
.venv\Scripts\python -c "import aiohttp, qrcode, pystray, PIL" 2>nul || (
  echo Installiere Pakete...
  .venv\Scripts\python -m pip install -q -r requirements.txt || (pause & exit /b 1)
)
start "" .venv\Scripts\pythonw.exe server.py %*
