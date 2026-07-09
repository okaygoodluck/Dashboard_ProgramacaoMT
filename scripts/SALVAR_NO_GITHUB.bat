@echo off
setlocal
cd /d "%~dp0.."
title Sincronizador Git - Salvando Alteracoes

echo ========================================================
echo         SALVAR CODIGO NO GITHUB (SYNC SIMPLES)
echo ========================================================
echo.

:: 1. Verificar se estamos em um repositorio Git
if not exist ".git" (
    echo [ERRO] Esta pasta nao eh um repositorio Git!
    pause
    exit /b 1
)

:: 2. Limpeza Preventiva do Git (Garantir que bancos pesados nao subam)
echo [*] Verificando regras preventivas...
git rm --cached demanda.db >nul 2>&1
git rm --cached ccp_app_HOMOLOG.db >nul 2>&1
git rm --cached demanda_HOMOLOG.db >nul 2>&1

:: 3. Solicitar Mensagem de Commit
echo.
echo [*] Descreva o que voce alterou no codigo:
set /p commit_msg="> "
if "%commit_msg%"=="" set commit_msg="Atualizacao rapida de codigo"

:: 4. Adicionar e Comitar (Apenas codigo)
echo.
echo [*] Salvando codigo localmente...
git add .
git commit -m "%commit_msg%"

:: 5. Enviar para o GitHub
echo.
echo [*] Enviando alteracoes para o GitHub...
git push origin HEAD

echo.
echo ========================================================
echo [SUCESSO] Suas alteracoes de codigo foram salvas no Github!
echo ========================================================
pause
