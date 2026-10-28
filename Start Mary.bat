@echo off
rem Opens Mary full screen. Double-click this file.
rem Close her from her menu (the three dots), or press Alt+F4.
cd /d "%~dp0"
if exist "%~dp0packaging\.venv\Scripts\pythonw.exe" (start "" "%~dp0packaging\.venv\Scripts\pythonw.exe" "%~dp0desktop.py" --mary) else (start "" pythonw "%~dp0desktop.py" --mary)
