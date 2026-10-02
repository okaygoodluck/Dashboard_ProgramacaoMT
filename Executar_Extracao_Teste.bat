@echo off
title CCP - Extracao em Modo de Teste Local (Isolado)
chcp 65001 >nul

echo ========================================================
echo   CCP - EXTRACAO EM MODO DE TESTE LOCAL (ISOLADO)
echo ========================================================
echo.
echo [ATENCAO] Esta execucao ira extrair os dados e salvar
echo           APENAS na pasta local do projeto.
echo           NENHUM dado sera copiado para a rede corporativa.
echo.

:: Ativa flags de seguranca para modo teste
set CCP_MODO_TESTE=1
set CCP_NAO_COPIAR_REDE=1
set CCP_FORCAR_LOCAL=1

:: Detecta se existe um Python Portatil na pasta do projeto
set PY_CMD=python
if exist "%~dp0python\python.exe" (
    set PY_CMD="%~dp0python\python.exe"
    echo [INFO] Usando Python Portatil: %~dp0python\python.exe
) else (
    echo [INFO] Usando Python do sistema.
)

echo.
echo [INICIANDO] Executando extrator_demanda.py em modo teste...
echo ========================================================
cd /d "%~dp0"
%PY_CMD% extrator_demanda.py --teste

echo.
echo ========================================================
echo Extracao de teste finalizada.
echo Para visualizar os dados, execute: Iniciar_Dashboard_Teste.bat
echo ========================================================
pause
