@echo off
SETLOCAL ENABLEEXTENSIONS

:: Namn på din Python-fil
SET script_name=diskdisk.py

:: Kontroll: Finns Python?
where python >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo ❌ Python hittades inte i PATH. Avbryter.
    pause
    exit /b
)

:: Starta med administratörsrättigheter
powershell -Command "Start-Process python -ArgumentList '%script_name%' -Verb RunAs"
