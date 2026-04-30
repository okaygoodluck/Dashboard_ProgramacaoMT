@echo off
setlocal EnableExtensions DisableDelayedExpansion

pushd "%~dp0" >nul
set "SRC_DIR=%CD%"

set "SILENT=0"
set "CHECK=0"
for %%A in (%*) do (
  if /I "%%~A"=="--silent" set "SILENT=1"
  if /I "%%~A"=="--check" set "CHECK=1"
)

set "LOCAL_ROOT=%LOCALAPPDATA%\Dashboard_MT"
set "LOG_DIR=%LOCAL_ROOT%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>nul
set "LOG_FILE=%LOG_DIR%\dashboard_start.log"

>> "%LOG_FILE%" echo ========================================================
>> "%LOG_FILE%" echo INICIO: %DATE% %TIME%
>> "%LOG_FILE%" echo SRC_DIR=%SRC_DIR%

set "PY_CMD=py -3"
where py >nul 2>nul
if errorlevel 1 set "PY_CMD=python"

>> "%LOG_FILE%" echo PY_CMD=%PY_CMD%

call %PY_CMD% -c "import sys; print(sys.executable)" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo [ERRO] Python nao encontrado no PC.
  echo [ERRO] Instale Python 64-bit e garanta que o comando ^(py ou python^) funcione.
  >> "%LOG_FILE%" echo ERRO: Python nao encontrado no PC.
  popd >nul
  if "%SILENT%"=="0" pause
  exit /b 1
)

set "STREAMLIT_SERVER_FILE_WATCHER_TYPE=none"
if exist "%SRC_DIR%\ccp_data.db" set "DEMANDA_DB_PATH=%SRC_DIR%\ccp_data.db"
if exist "%SRC_DIR%\ccp_data.db" set "CCP_CCP_DATA_DB_PATH=%SRC_DIR%\ccp_data.db"

>> "%LOG_FILE%" echo INFO: Testando requirements...
call %PY_CMD% -c "import streamlit, pandas, altair, streamlit_autorefresh; print('IMPORTS_OK')" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo [ERRO] Requirements nao instalados no Python deste PC.
  echo [ERRO] Rode:
  echo %PY_CMD% -m pip install -r "%SRC_DIR%\requirements.txt"
  echo.
  echo Se nao tiver permissao, tente:
  echo %PY_CMD% -m pip install --user -r "%SRC_DIR%\requirements.txt"
  >> "%LOG_FILE%" echo ERRO: Requirements nao instalados.
  popd >nul
  if "%SILENT%"=="0" pause
  exit /b 1
)

if "%CHECK%"=="1" (
  echo [OK] Python e requirements OK.
  echo Log: %LOG_FILE%
  popd >nul
  exit /b 0
)

>> "%LOG_FILE%" echo INFO: Iniciando Streamlit...
>> "%LOG_FILE%" echo CMD=%PY_CMD% -m streamlit run dashboard.py --server.fileWatcherType none
call %PY_CMD% -m streamlit run "dashboard.py" --server.fileWatcherType none >> "%LOG_FILE%" 2>&1

>> "%LOG_FILE%" echo FIM: %DATE% %TIME%
popd >nul
