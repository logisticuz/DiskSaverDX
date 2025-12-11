@echo off
SETLOCAL ENABLEEXTENSIONS

REM Root folder = where this .bat is located
set "ROOT=%~dp0"

REM Path to venv python
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"

REM Path to GUI script
set "GUI_SCRIPT=%ROOT%src\disk_gui.py"

REM Verify venv python
if not exist "%VENV_PY%" (
    echo ❌ Could not find virtualenv python:
    echo    "%VENV_PY%"
    echo Make sure your venv is named .venv at the repo root.
    pause
    exit /b 1
)

REM Start GUI hidden as administrator (no terminal window)
powershell -WindowStyle Hidden -Command ^
    "Start-Process '%VENV_PY%' -ArgumentList @('%GUI_SCRIPT%') -Verb RunAs -WindowStyle Hidden"

EXIT /B
