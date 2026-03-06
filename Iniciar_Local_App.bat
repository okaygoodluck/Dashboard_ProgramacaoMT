@echo off
:: ============================================================
:: INICIAR SERVIDOR E ABRIR (MODO APLICATIVO LOCAL)
:: ============================================================
:: Use este script na SUA MAQUINA para rodar o sistema e abrir
:: a interface como se fosse um programa desktop.

cd /d "%~dp0"

echo.
echo [1/2] Iniciando o servidor Streamlit...
echo (A janela preta deve ficar aberta para o sistema funcionar)
echo.

:: Inicia o servidor em uma nova janela minimizada
start /min "Servidor Dashboard" cmd /k "python -m streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0"

echo [2/2] Aguardando inicializacao (5 segundos)...
timeout /t 5 >nul

echo.
echo [INFO] Abrindo interface...

:: Tenta abrir com Edge (Padrao Windows) em modo App Local
start msedge --app=http://localhost:8501

exit
