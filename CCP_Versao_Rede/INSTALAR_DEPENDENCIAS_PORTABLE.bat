@echo off
setlocal EnableExtensions DisableDelayedExpansion

title Vanguard Command Center - Instalador de Dependencias
echo ========================================================
echo   INSTALADOR DE DEPENDENCIAS (VANGUARD PORTABLE)
echo ========================================================
echo.

:: Navega para a pasta do script
set "BASE_DIR=%~dp0"
cd /d "%BASE_DIR%"

set "PYTHON_EXE=%BASE_DIR%python\python.exe"
set "REQ_FILE=%BASE_DIR%requirements.txt"

:: CORREÇÃO PARA HOME OFFICE: Força o Python a encontrar sua própria pasta Lib
set "PYTHONHOME=%BASE_DIR%python"
set "PYTHONPATH=%BASE_DIR%python\Lib;%BASE_DIR%python\DLLs;%BASE_DIR%python\Lib\site-packages"

:: 1. VERIFICA SE O PYTHON EXISTE
if not exist "%PYTHON_EXE%" (
    echo [ERRO] Pasta 'python' nao encontrada neste diretorio.
    echo Certifique-se de que a pasta 'python' ^(portatil^) foi colada aqui.
    echo Caminho esperado: %PYTHON_EXE%
    echo.
    pause
    exit /b 1
)

:: 2. VERIFICA REQUIREMENTS
if not exist "%REQ_FILE%" (
    echo [ERRO] Arquivo 'requirements.txt' nao encontrado.
    pause
    exit /b 1
)

echo [1/2] Verificando sistema PIP...
"%PYTHON_EXE%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [!] PIP nao encontrado. Instalando via get-pip.py...
    if exist "%BASE_DIR%python\get-pip.py" (
        "%PYTHON_EXE%" "%BASE_DIR%python\get-pip.py"
    ) else (
        echo [ERRO] get-pip.py nao encontrado. Tentando ensurepip...
        "%PYTHON_EXE%" -m ensurepip --default-pip
    )
)

echo.
echo [2/2] Instalando bibliotecas necessarias...
echo --------------------------------------------------------
echo DICA: Se a instalacao falhar ou for muito lenta no I:,
echo copie esta pasta para o C: (Desktop), rode este instalador
echo la e depois mova a pasta de volta para a rede.
echo --------------------------------------------------------
echo.

"%PYTHON_EXE%" -m pip install -r "%REQ_FILE%"

if errorlevel 1 (
    echo.
    echo [ERRO] Houve um problema na instalacao. 
    echo Verifique sua conexao com a internet ou permissoes de rede.
    echo.
    pause
) else (
    echo.
    echo [SUCESSO] Todas as dependencias foram instaladas!
    echo Agora voce pode abrir o Dashboard pelo ACESSAR_DASHBOARD.bat
    echo.
    pause
)

popd
exit /b 0
