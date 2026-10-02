@echo off
title CCP - Dashboard em Modo de Teste Local (Isolado)
chcp 65001 >nul

echo ========================================================
echo   CCP - DASHBOARD EM MODO DE TESTE LOCAL (ISOLADO)
echo ========================================================
echo.
echo [INFO] Conectando exclusivamente a base de dados local:
echo        - ccp_data.db (nesta pasta)
echo        - ccp_app.db (nesta pasta)
echo.
echo [SEGURANCA] Nenhuma informacao sera lida ou gravada na rede.
echo.

:: Ativa flags de seguranca para modo teste
set CCP_MODO_TESTE=1
set CCP_FORCAR_LOCAL=1
set CCP_NAO_COPIAR_REDE=1

:: Detecta se existe um Python Portatil na pasta do projeto
set PY_CMD=python
if exist "%~dp0python\python.exe" (
    set PY_CMD="%~dp0python\python.exe"
    echo [INFO] Usando Python Portatil: %~dp0python\python.exe
) else (
    echo [INFO] Usando Python do sistema.
)

echo.
echo [INICIANDO] Abrindo Dashboard de Teste na porta 8503...
echo Acesse: http://localhost:8503
echo ========================================================
cd /d "%~dp0"
%PY_CMD% -m streamlit run dashboard.py --server.port 8503 --server.fileWatcherType none

pause
