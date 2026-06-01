@echo off
setlocal
cd /d "%~dp0"
title SERVIDOR CCP - Centro de Controle da Programacao

:: --- CONFIGURACOES DO SERVIDOR ---
set "PORT=8501"
:: ---------------------------------

echo ========================================================
echo        INICIANDO SERVIDOR CENTRAL CCP (PORTA %PORT%)
echo ========================================================
echo.

:: 1. Localizar Python (Prioridade para o Sistema no Servidor)
set "PY_CMD=python"
where python >nul 2>&1
if errorlevel 1 (
    if exist "%~dp0python\python.exe" (
        set "PY_CMD="%~dp0python\python.exe""
    ) else (
        echo [ERRO] Python nao encontrado no sistema nem na pasta local.
        pause
        exit /b 1
    )
)

:: 2. Identificar IP do Servidor (para mostrar o link)
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr "IPv4"') do set "SERVER_IP=%%a"
set "SERVER_IP=%SERVER_IP: =%"

echo [*] Servidor sendo iniciado em: http://%SERVER_IP%:%PORT%
echo [*] Pressione CTRL+C para encerrar o servidor.
echo.

:: 3. Executar Streamlit em modo Servidor
:: --server.address 0.0.0.0 permite conexao externa
:: --server.port define a porta fixa
:: --server.headless evita abrir browser no servidor
%PY_CMD% -m streamlit run "dashboard.py" ^
    --server.address 0.0.0.0 ^
    --server.port %PORT% ^
    --server.headless true ^
    --server.fileWatcherType none ^
    --browser.gatherUsageStats false

if errorlevel 1 (
    echo.
    echo [ERRO] O servidor parou inesperadamente.
    pause
)
