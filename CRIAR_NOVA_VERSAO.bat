@echo off
setlocal enabledelayedexpansion

:: ============================================================
:: DASHBOARD CCP - DISPARADOR DE NOVA VERSAO (GITHUB)
:: ============================================================

title LANÇAR NOVA VERSÃO - DASHBOARD CCP

echo.
echo ============================================================
echo      PREPARANDO NOVO LANÇAMENTO PARA GITHUB
echo ============================================================
echo.

:: 1. Atualizar a pasta de distribuição (CCP_Versao_Rede)
echo [1/3] Atualizando pasta de rede (CCP_Versao_Rede)...
python scripts/gerar_versao_rede.py
if errorlevel 1 (
    echo [ERRO] Falha ao gerar a versao de rede.
    pause
    exit /b
)
echo.

:: 2. Verificar status do Git
echo [2/3] Verificando alteracoes no Git...
git status --short
echo.
echo Verifique se todas as alteracoes acima devem ser enviadas.
set /p CONFIRM="Deseja continuar com o lançamento? (S/N): "
if /i "%CONFIRM%" neq "S" exit /b

:: 3. Solicitar numero da versao
echo.
echo Digite o numero da versao (ex: 1.0.5):
set /p VERSION="v"
set TAG=v%VERSION%

echo.
echo [3/3] Criando tag %TAG% e enviando...

:: 4. Commit e Push
git add .
git commit -m "Release %TAG%: Atualizacao de rede"
git tag -a "%TAG%" -m "Versao %TAG%"
git push origin master
git push origin "%TAG%"

echo.
echo ============================================================
echo ✅ SUCESSO! Versao %TAG% enviada para o GitHub.
echo.
echo A automacao (GitHub Actions) foi iniciada.
echo Em alguns minutos o pacote (.zip) estara disponivel em:
echo https://github.com/okaygoodluck/Dashboard_ProgramacaoMT/releases
echo ============================================================
echo.
pause
