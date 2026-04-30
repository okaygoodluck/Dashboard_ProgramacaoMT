@echo off
setlocal EnableExtensions DisableDelayedExpansion

title Servidor Dashboard MT
echo ========================================================
echo   INICIANDO DASHBOARD MT PARA ACESSO EM REDE
echo ========================================================
echo.

pushd "%~dp0"
set "SRC_DIR=%CD%"

:: Tenta usar 'py -3' ou 'python'
set "PY_CMD=py -3"
where py >nul 2>nul
if errorlevel 1 set "PY_CMD=python"

echo Enderecos de IP desta maquina:
ipconfig | findstr "IPv4"
echo.
echo ========================================================
echo O Dashboard estara acessivel em: http://[IP_NO_SERVIDOR]:8501
echo ========================================================
echo.

:: --server.address 0.0.0.0 permite conexoes externas
:: --server.port 8501 define a porta padrao

echo INFO: Testando requirements...
%PY_CMD% -c "import streamlit, pandas, altair, streamlit_autorefresh; print('IMPORTS_OK')" >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Requirements nao instalados. Rode:
    echo %PY_CMD% -m pip install -r "requirements.txt"
    pause
    exit /b 1
)

%PY_CMD% -m streamlit run "dashboard.py" --server.address 0.0.0.0 --server.port 8501 --server.fileWatcherType none

pause
popd
