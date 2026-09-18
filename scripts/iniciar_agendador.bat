
@echo off
setlocal
cd /d "%~dp0.."
title AGENDADOR CCP - Centro de Controle da Programacao
set "CCP_SERVER_MODE=true"
python "%~dp0agendador.py"
pause
