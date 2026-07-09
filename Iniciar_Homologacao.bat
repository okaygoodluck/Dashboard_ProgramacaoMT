@echo off
title CCP - Ambiente de Homologacao
chcp 65001 >nul

echo ===================================================
echo   CCP - PREPARANDO AMBIENTE DE HOMOLOGACAO
echo ===================================================
echo.

:: Encontrar caminho da rede de forma inteligente para evitar problemas com 'çã' no Windows
set "REDE_BASE="
for /D %%I in ("I:\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programa*") do (
    if exist "%%I\Dashboard MT\ccp_app.db" (
        set "REDE_BASE=%%I\Dashboard MT"
    )
)

echo [1] Copiando bancos de dados para a pasta segura...
if not exist "_ambiente_homologacao" mkdir "_ambiente_homologacao"

if defined REDE_BASE (
    echo [*] Conexao com a rede Cemig confirmada!
    echo [*] Clonando ccp_app.db e ccp_data.db fresquinhos da producao...
    copy /Y "%REDE_BASE%\ccp_app.db" "_ambiente_homologacao\ccp_app_HOMOLOG.db"
    copy /Y "%REDE_BASE%\ccp_data.db" "_ambiente_homologacao\ccp_data_HOMOLOG.db"
) else (
    echo [AVISO] Rede da Cemig indisponivel no momento.
    echo [*] A homologacao iniciara com um banco de dados em branco.
)

:: demanda.db e sempre mantido localmente devido ao extrator
if exist demanda.db (
    echo [*] Clonando base de extracao local demanda.db...
    copy /Y demanda.db "_ambiente_homologacao\demanda_HOMOLOG.db"
)
echo.

echo [2] Injetando Variaveis de Ambiente de Homologacao...
set CCP_CCP_APP_DB_PATH=%~dp0_ambiente_homologacao\ccp_app_HOMOLOG.db
set CCP_CCP_DATA_DB_PATH=%~dp0_ambiente_homologacao\ccp_data_HOMOLOG.db
set CCP_LOCAL_DB_PATH=%~dp0_ambiente_homologacao\demanda_HOMOLOG.db

:: [CORRECAO DE SEGURANCA]: Enganar a variavel global de rede para o extrator
:: Isso garante que se o extrator rodar aqui, ele nao publique no "I:\" verdadeiro.
if not exist "_ambiente_homologacao\sandbox_rede" mkdir "_ambiente_homologacao\sandbox_rede"
set CCP_DASHBOARD_DB_PATH=%~dp0_ambiente_homologacao\sandbox_rede
echo.

:: Detecta se existe um Python Portatil na pasta do projeto
set PYTHON_EXE=python
if exist "python\python.exe" (
    set PYTHON_EXE="python\python.exe"
    echo [INFO] Python Portatil detectado na pasta 'python'!
) else (
    echo [INFO] Python Portatil nao encontrado. Usando Python do sistema.
)

echo.
echo [3] Iniciando o Dashboard na porta 8502 (http://localhost:8502)...
echo         ATENCAO: Este e o ambiente de HOMOLOGACAO!
echo ===================================================
%PYTHON_EXE% -m streamlit run dashboard.py --server.port 8502

pause
