@echo off
setlocal
cd /d "%~dp0\..\.."
echo Iniciando o worker de confirmacoes e lembretes...
py scripts\evolution\executar_worker.py
pause
