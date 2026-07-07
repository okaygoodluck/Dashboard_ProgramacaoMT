@echo off
title CCP - Sandbox de Testes

echo ===================================================
echo   CCP - PREPARANDO AMBIENTE DE TESTE (SANDBOX)
echo ===================================================
echo.

echo [1] Fazendo backup/clone dos bancos de producao para teste...
copy /Y ccp_app.db ccp_app_TESTE.db
copy /Y demanda.db demanda_TESTE.db
copy /Y ccp_data.db ccp_data_TESTE.db
echo.

echo [2] Aplicando Variaveis de Ambiente de Teste...
set CCP_CCP_APP_DB_PATH=ccp_app_TESTE.db
set CCP_CCP_DATA_DB_PATH=ccp_data_TESTE.db
set CCP_LOCAL_DB_PATH=demanda_TESTE.db
echo.

echo [3] Executando Extrator Real apontando para Bancos de Teste...
echo (O navegador deve abrir para fazer a extracao oficial)
python extrator_demanda.py
echo.

echo [3.1] Iniciando o Agendador de Testes (Simulador Continuo) em outra janela...
start "Agendador de Testes" cmd /c "set CCP_CCP_APP_DB_PATH=ccp_app_TESTE.db && set CCP_CCP_DATA_DB_PATH=ccp_data_TESTE.db && set CCP_LOCAL_DB_PATH=demanda_TESTE.db && python agendador_teste.py"
echo.

echo [4] Subindo o Dashboard Visual na porta 8502 (http://localhost:8502)...
echo         ATENCAO: Este e o ambiente de testes!
echo ===================================================
streamlit run dashboard.py --server.port 8502

pause
