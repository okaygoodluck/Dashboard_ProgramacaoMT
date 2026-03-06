@echo off
setlocal
TITLE Dashboard Analise de Demanda

:: --- INICIO DO LOG ---
echo ==========================================
echo INICIANDO SCRIPT DE ATALHO
echo Data/Hora: %DATE% %TIME%
echo ==========================================

:: 1. DEFINICAO DE VARIAVEIS
set "PROJETO_DIR=I:\IT\ODCO\PUBLICA\Kennedy\Projetos\analise_demanda"
set "PYTHON_EXE=D:\Users\c057573\AppData\Local\Programs\Python\Python314\python.exe"

echo.
echo [1/4] Verificando diretorio do projeto...
echo Caminho: "%PROJETO_DIR%"

if not exist "%PROJETO_DIR%" (
    color 4f
    echo.
    echo [ERRO CRITICO] A pasta do projeto nao foi encontrada.
    echo Verifique se o disco I: esta mapeado e acessivel.
    echo.
    echo Pressione qualquer tecla para sair...
    pause >nul
    exit /b 1
) else (
    echo Diretorio encontrado.
)

echo.
echo [2/4] Entrando na pasta do projeto...
cd /d "%PROJETO_DIR%"
if %errorlevel% neq 0 (
    color 4f
    echo [ERRO] Nao foi possivel acessar a pasta. Permissao negada ou erro de disco.
    pause
    exit /b 1
)

echo.
echo [3/4] Verificando Python...
if not exist "%PYTHON_EXE%" (
    echo [AVISO] O Python especifico nao foi encontrado em:
    echo "%PYTHON_EXE%"
    echo Tentaremos usar o comando 'python' global do sistema.
    set "PYTHON_EXE=python"
) else (
    echo Python encontrado.
)

echo.
echo [4/4] Executando Dashboard...
echo Comando: "%PYTHON_EXE%" -m streamlit run dashboard.py
echo.
echo --------------------------------------------------------
echo O navegador deve abrir em instantes.
echo Mantenha esta janela aberta enquanto usa o sistema.
echo --------------------------------------------------------
echo.

"%PYTHON_EXE%" -m streamlit run dashboard.py

:: Captura o erro se houver
if %errorlevel% neq 0 (
    color 4f
    echo.
    echo ========================================================
    echo [ERRO] O SISTEMA PAROU DE FUNCIONAR
    echo ========================================================
    echo Codigo de erro: %errorlevel%
    echo.
    echo Verifique as mensagens acima para identificar o problema.
    echo.
    echo Pressione qualquer tecla para fechar esta janela...
    pause >nul
) else (
    echo.
    echo Sistema encerrado normalmente.
    pause
)
