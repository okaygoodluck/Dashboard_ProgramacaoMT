@echo off
title CCP - Simular Dados de Teste (Instantaneo)
chcp 65001 >nul

echo ========================================================
echo   CCP - GERAR DADOS SIMULADOS DE TESTE (INSTANTANEO)
echo ========================================================
echo.
echo [INFO] Injetando solicitacoes ficticias com CHI >= 1500
echo        e pendencias de e-mail DECP na base local.
echo.

:: Ativa flags de seguranca para modo teste
set CCP_MODO_TESTE=1
set CCP_NAO_COPIAR_REDE=1
set CCP_FORCAR_LOCAL=1

:: Detecta se existe um Python Portatil na pasta do projeto
set PY_CMD=python
if exist "%~dp0python\python.exe" (
    set PY_CMD="%~dp0python\python.exe"
)

cd /d "%~dp0"
%PY_CMD% scripts\simular_dados_teste.py

echo.
pause
