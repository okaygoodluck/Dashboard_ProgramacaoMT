@echo off
title Iniciando CCP - Centro de Controle da Programacao
chcp 65001 >nul
color 0B

echo ========================================================
echo        CCP - Centro de Controle da Programacao
echo ========================================================
echo.

:: Detecta se existe um Python Portatil na pasta do projeto
set PYTHON_EXE=python
if exist "python_portatil\python.exe" (
    set PYTHON_EXE="python_portatil\python.exe"
    echo [INFO] Python Portatil detectado na pasta 'python_portatil'!
) else if exist "python\python.exe" (
    set PYTHON_EXE="python\python.exe"
    echo [INFO] Python Portatil detectado na pasta 'python'!
) else (
    echo [INFO] Python Portatil nao encontrado. Usando Python do sistema.
)

echo.
echo [1/2] Verificando dependencias (isso pode levar alguns instantes)...
%PYTHON_EXE% -m pip install -r requirements.txt --disable-pip-version-check
if %errorlevel% neq 0 (
    color 0E
    echo.
    echo [AVISO] Falha ao verificar/instalar bibliotecas (Possivel bloqueio de rede/proxy).
    echo Tentando iniciar o sistema mesmo assim caso elas ja estejam instaladas...
    echo.
) else (
    echo [OK] Todas as dependencias estao prontas.
)

echo.
echo [2/2] Iniciando o Dashboard...
echo.
%PYTHON_EXE% -m streamlit run dashboard.py

pause
