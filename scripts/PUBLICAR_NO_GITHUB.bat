@echo off
setlocal
cd /d "%~dp0.."
title Publicador CCP - Centro de Controle da Programacao

echo ========================================================
echo         PUBLICADOR DE VERSAO CCP (LOCAL-FIRST)
echo ========================================================
echo.

:: 1. Verificar se estamos em um repositorio Git
if not exist ".git" (
    echo [ERRO] Esta pasta nao eh um repositorio Git!
    pause
    exit /b 1
)

:: 2. Limpeza Preventiva do Git (Garantir que Python/DB nao subam)
echo [*] Verificando se ha arquivos pesados para remover do Git...
git rm -r --cached python >nul 2>&1
git rm --cached demanda.db >nul 2>&1

:: 3. Solicitar Mensagem de Commit
echo.
echo [*] Descreva brevemente as alteracoes (Ex: Melhoria na interface):
set /p commit_msg="> "
if "%commit_msg%"=="" set commit_msg="Update CCP"

:: 4. Adicionar e Comitar (Apenas codigo)
echo.
echo [*] Salvando codigo localmente...
git add .
git commit -m "%commit_msg%"

:: 5. Gerar Pacotes ZIP Locais
echo.
echo [*] Gerando pacote CCP_Portable.zip (Home Office)...
if exist "python\python.exe" (
    "python\python.exe" scripts\build_portable.py
) else (
    python scripts\build_portable.py
)

if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao gerar o pacote ZIP Portatil.
    pause
    exit /b 1
)

echo.
echo [*] Gerando pacote CCP_Servidor_Codigo.zip (Servidor Central)...
if exist "python\python.exe" (
    "python\python.exe" scripts\build_server.py
) else (
    python scripts\build_server.py
)

if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao gerar o pacote ZIP Servidor.
    pause
    exit /b 1
)

:: 6. Solicitar Tag de Versao
echo.
echo [*] Digite a nova versao (Ex: v1.0.5):
set /p version_tag="> "

:: 7. Enviar para o GitHub
echo.
echo [*] Enviando codigo para o GitHub...
git push origin HEAD

if not "%version_tag%"=="" (
    echo [*] Criando e enviando Tag %version_tag%...
    git tag %version_tag%
    git push origin %version_tag%
)

echo.
echo ========================================================
echo [SUCESSO] Codigo enviado!
echo.
echo [*] Os arquivos 'CCP_Portable.zip' e 'CCP_Servidor_Codigo.zip' foram gerados na raiz.
echo [*] Vou abrir a pagina de Releases agora. 
echo [*] Basta clicar em 'Draft a new release' e arrastar os arquivos ZIP.
echo ========================================================
echo.
start https://github.com/okaygoodluck/Dashboard_ProgramacaoMT/releases
pause

