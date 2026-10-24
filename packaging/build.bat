@echo off
rem Builds the Care Incident Log app. Double-click this file; results land in dist\.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe py -3.12 -m venv .venv || python -m venv .venv
.venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt || goto :failed
.venv\Scripts\python build.py || goto :failed
echo.
echo Done. The installer and zip are in the dist folder.
pause
exit /b 0
:failed
echo.
echo The build stopped with an error (see above).
pause
exit /b 1
