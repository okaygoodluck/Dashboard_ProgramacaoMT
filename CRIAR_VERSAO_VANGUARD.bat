@echo off
setlocal
cd /d "%~dp0"
title Gerador de Pacote Vanguard
echo ========================================================
echo        GERADOR DE PACOTE VANGUARD PORTABLE
echo ========================================================
echo.

:: Tenta usar o python local se existir, senao usa o do sistema
set "PY_CMD=python"
if exist "python\python.exe" set "PY_CMD=python\python.exe"

%PY_CMD% scripts\build_portable.py

if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao gerar o pacote.
) else (
    echo.
    echo [OK] Processo concluido.
)

pause
