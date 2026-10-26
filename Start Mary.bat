@echo off
rem Opens Mary. Double-click this file.
rem For now she opens in the web browser; the full-screen desktop version (desktop.py --mary) comes next.
cd /d "%~dp0"
start "" pythonw "%~dp0server.py" --no-browser
timeout /t 2 /nobreak >nul
start "" "http://localhost:8765/mary.html"
