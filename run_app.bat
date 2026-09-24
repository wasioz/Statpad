@echo off
rem StatPad launcher - double-click to start the app
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw app.py
  exit /b 0
)
where python >nul 2>nul
if %errorlevel%==0 (
  start "" python app.py
  exit /b 0
)
echo Python was not found on this computer.
echo Install Python from https://www.python.org/downloads/ and try again.
pause
