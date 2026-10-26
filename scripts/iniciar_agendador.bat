
@echo off
setlocal
cd /d "%~dp0.."
title AGENDADOR CCP - Centro de Controle da Programacao

:: Desativa Modo de Edicao Rapida do Windows para evitar congelamento por clique do mouse
reg add "HKCU\Console" /v QuickEdit /t REG_DWORD /d 0 /f >nul 2>&1

set "CCP_SERVER_MODE=true"
python "%~dp0agendador.py"
pause
