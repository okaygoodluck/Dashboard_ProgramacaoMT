@echo off
:: ============================================================
:: ATALHO PARA ACESSAR O DASHBOARD (MODO APLICATIVO)
:: ============================================================
:: Este script abre o navegador em modo "App" (sem barra de endereços)
:: apontando para o servidor onde o Dashboard está rodando.

set "URL=http://10.23.5.4:8501"

echo.
echo [INFO] Procurando Google Chrome...

:: Tenta Google Chrome (64-bit)
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    start "" "%ProgramFiles%\Google\Chrome\Application\chrome.exe" --app=%URL%
    exit
)

:: Tenta Google Chrome (32-bit)
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    start "" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" --app=%URL%
    exit
)

:: Tenta Google Chrome (Local AppData)
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" (
    start "" "%LocalAppData%\Google\Chrome\Application\chrome.exe" --app=%URL%
    exit
)

echo.
echo [INFO] Chrome nao encontrado. Tentando Microsoft Edge...

:: Tenta Microsoft Edge (Vem instalado no Windows)
start msedge --app=%URL%

exit
