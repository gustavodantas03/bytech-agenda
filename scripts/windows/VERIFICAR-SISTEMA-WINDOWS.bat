@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Ambiente virtual nao encontrado.
    echo Execute primeiro: INSTALAR-E-EXECUTAR-WINDOWS.bat
    pause
    exit /b 1
)
".venv\Scripts\python.exe" diagnostico.py
pause
