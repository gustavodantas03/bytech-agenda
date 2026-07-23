@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Bytech Agenda - Instalacao

echo ==============================================
echo       BYTECH AGENDA - INSTALACAO SEGURA
echo ==============================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Python nao foi encontrado.
    echo Instale o Python 3.11 ou superior e marque "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/5] Criando ambiente virtual...
    py -m venv .venv
    if errorlevel 1 goto :erro
) else (
    echo [1/5] Ambiente virtual encontrado.
)

echo [2/5] Atualizando o pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :erro

echo [3/5] Instalando dependencias...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :erro

echo [4/5] Validando o sistema...
".venv\Scripts\python.exe" diagnostico.py
if errorlevel 1 goto :erro

echo [5/5] Iniciando o Bytech Agenda...
echo Acesse: http://127.0.0.1:5000
".venv\Scripts\python.exe" app.py
exit /b 0

:erro
echo.
echo [ERRO] A instalacao ou validacao falhou.
echo Revise a mensagem acima. Para tentar novamente, execute este arquivo de novo.
pause
exit /b 1
