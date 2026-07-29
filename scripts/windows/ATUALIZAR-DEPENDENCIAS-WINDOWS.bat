@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Ambiente virtual nao encontrado.
    echo Execute primeiro: INSTALAR-E-EXECUTAR-WINDOWS.bat
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
".venv\Scripts\python.exe" diagnostico.py
pause
