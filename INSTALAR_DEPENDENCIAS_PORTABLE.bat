@echo off
setlocal EnableExtensions
title Vanguard - Instalador de Dependencias
echo ========================================================
echo   INSTALADOR DE DEPENDENCIAS (VANGUARD PORTABLE)
echo ========================================================
echo.

set "BASE_DIR=%~dp0"
cd /d "%BASE_DIR%"

set "PYTHON_EXE=%BASE_DIR%python\python.exe"
set "REQ_FILE=%BASE_DIR%requirements.txt"
set "GET_PIP=%BASE_DIR%get-pip.py"

:: 1. Verificacao de Integridade
if not exist "%PYTHON_EXE%" (
    echo [ERRO] Pasta 'python' nao encontrada!
    echo Local: %CD%
    pause
    exit /b 1
)

:: 2. Verificar PIP
echo [*] Verificando PIP...
"%PYTHON_EXE%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [!] PIP nao encontrado. Instalando via get-pip.py...
    if exist "%GET_PIP%" (
        "%PYTHON_EXE%" "%GET_PIP%" --no-warn-script-location
    ) else (
        echo [ERRO] Arquivo 'get-pip.py' nao encontrado. 
        echo Nao eh possivel instalar o PIP offline.
        pause
        exit /b 1
    )
)

:: 3. Instalar Requirements
echo.
echo [*] Instalando bibliotecas do requirements.txt...
"%PYTHON_EXE%" -m pip install -r "%REQ_FILE%" --no-warn-script-location

if errorlevel 1 (
    echo.
    echo [ERRO] Falha na instalacao das bibliotecas.
    echo Verifique sua conexao ou se a pasta esta no Desktop (C:).
    pause
    exit /b 1
)

echo.
echo ========================================================
echo [SUCESSO] Ambiente configurado!
echo Agora voce pode usar o 'Iniciar_Vanguard.bat'
echo ========================================================
echo.
pause
exit /b 0
