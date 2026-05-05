@echo off
setlocal
cd /d "%~dp0"
title Publicador de Release - Vanguard

echo ========================================================
echo         PUBLICADOR DE VERSAO PARA GITHUB
echo ========================================================
echo.

:: 1. Verificar se estamos em um repositorio Git
if not exist ".git" (
    echo [ERRO] Esta pasta nao eh um repositorio Git!
    pause
    exit /b 1
)

:: 2. Solicitar Mensagem de Commit
echo [*] Descreva brevemente as alteracoes (Ex: Correcao de bugs):
set /p commit_msg="> "
if "%commit_msg%"=="" set commit_msg="Update Vanguard"

:: 3. Adicionar e Comitar
echo.
echo [*] Salvando alteracoes localmente...
git add .
git commit -m "%commit_msg%"

:: 4. Solicitar Tag de Versao
echo.
echo [*] Digite a nova versao (Ex: v1.0.5):
echo (DICA: Use sempre 'v' seguido de numeros)
set /p version_tag="> "

if "%version_tag%"=="" (
    echo [AVISO] Nenhuma tag informada. O código sera enviado, mas nenhum Release sera gerado.
    echo Pressione CTRL+C para cancelar ou qualquer tecla para apenas dar o Push...
    pause >nul
)

:: 5. Enviar para o GitHub
echo.
echo [*] Enviando para o GitHub...
git push origin HEAD

if not "%version_tag%"=="" (
    echo.
    echo [*] Criando e enviando Tag %version_tag%...
    git tag %version_tag%
    git push origin %version_tag%
    
    echo.
    echo ========================================================
    echo [SUCESSO] Codigo enviado e Tag criada!
    echo.
    echo O GitHub agora esta gerando o pacote ZIP automaticamente.
    echo Voce podera baixa-lo em alguns minutos na aba 'Releases'.
    echo ========================================================
) else (
    echo.
    echo [OK] Codigo enviado.
)

echo.
pause
