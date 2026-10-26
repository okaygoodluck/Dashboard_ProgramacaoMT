@echo off
setlocal
cd /d "%~dp0"
title AUDITORIA MANUAL CCP - Reconciliacao de Status GDIS-PM

set "CCP_SERVER_MODE=true"

:: Localiza o executável Python
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

echo ========================================================
echo        AUDITORIA MANUAL DE STATUS (GDIS-PM)
echo ========================================================
echo.
echo Iniciando auditor_status.py com interface visual (--debug)...
echo.

%PY_CMD% "auditor_status.py" --debug

echo.
echo ========================================================
echo Processo finalizado.
echo ========================================================
pause
