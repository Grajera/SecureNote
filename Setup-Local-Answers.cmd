@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 goto end
.venv\Scripts\python.exe -m pip install -r requirements-rag.txt
if errorlevel 1 goto end
.venv\Scripts\python.exe ask.py download-model
:end
pause
