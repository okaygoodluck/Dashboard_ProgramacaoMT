@echo off
setlocal
cd /d "%~dp0"
title Gerador de Pacotes CCP

echo ========================================================
echo         GERANDO PACOTES ZIP (PORTATIL E SERVIDOR)
echo ========================================================
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

echo.
echo ========================================================
echo [SUCESSO] Pacotes gerados com sucesso na raiz do projeto!
echo - CCP_Portable.zip
echo - CCP_Servidor_Codigo.zip
echo ========================================================
pause
