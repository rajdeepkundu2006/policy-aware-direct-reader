@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 exit /b 1
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 exit /b 1
)
if not exist ".env" (
    copy /y .env.example .env >nul
    echo Enter your PostgreSQL password in .env, then run this command again.
    exit /b 1
)
.venv\Scripts\python.exe manage.py %*
