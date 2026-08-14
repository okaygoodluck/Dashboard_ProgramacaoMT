@echo off
:: Procura pelo executável do Python portátil
set "PY_CMD="
if exist "%~dp0python\pythonw.exe" (
    set "PY_CMD="%~dp0python\pythonw.exe""
) else (
    set "PY_CMD=pythonw"
)

:: Inicia a interface gráfica sem prender o terminal (usando pythonw para omitir a janela preta)
start "" %PY_CMD% "%~dp0painel_controle.py"
exit
