@echo off
cd /d "%~dp0"
if "%~1"=="" (
  echo Drag an audio or video recording onto this file.
  echo Start Start-Receiver.cmd first. See README.md for setup.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" device.py enqueue "%~1"
if errorlevel 1 goto done
".venv\Scripts\python.exe" device.py send --token-file laptop-state\device.token
:done
pause
