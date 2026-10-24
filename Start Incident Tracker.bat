@echo off
rem Opens the Care Incident Log. Double-click this file.
cd /d "%~dp0"
start "" pythonw "%~dp0server.py"
