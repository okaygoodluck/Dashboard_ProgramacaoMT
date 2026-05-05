import os
import shutil
import sys
import subprocess

def build_package():
    print("========================================================")
    print("   VANGUARD PORTABLE BUILDER (CLEAN START)")
    print("========================================================")

    # Definir diretórios
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_name = "CCP_Versao_Rede"
    dist_dir = os.path.join(root_dir, dist_name)
    
    print(f"[*] Root: {root_dir}")
    print(f"[*] Dist: {dist_dir}")

    # 1. Limpeza da pasta de destino (Robustez contra arquivos travados)
    if os.path.exists(dist_dir):
        print(f"[*] Limpando pasta de destino...")
        # Tenta remover o que for possível sem travar o script todo
        for item in os.listdir(dist_dir):
            item_path = os.path.join(dist_dir, item)
            try:
                if os.path.isfile(item_path): os.remove(item_path)
                elif os.path.isdir(item_path): shutil.rmtree(item_path, ignore_errors=True)
            except:
                pass
    else:
        os.makedirs(dist_dir)

    # 2. Whitelist de arquivos essenciais
    essential_files = [
        'dashboard.py',
        'extrator_demanda.py',
        'db_manager.py',
        'ccp_ui.py',
        'requirements.txt',
        'calendario_programacao.html',
        'INSTALAR_DEPENDENCIAS_PORTABLE.bat',
        'get-pip.py'
    ]

    print("[*] Copiando arquivos essenciais...")
    for f in essential_files:
        src = os.path.join(root_dir, f)
        if os.path.exists(src):
            shutil.copy2(src, dist_dir)
            print(f" [OK] {f}")
        else:
            print(f" [!] AVISO: {f} não encontrado.")

    # 3. Copiar pastas modulares
    essential_folders = ['components', 'views', 'scripts', '.streamlit']
    for folder in essential_folders:
        src = os.path.join(root_dir, folder)
        if os.path.exists(src):
            shutil.copytree(src, os.path.join(dist_dir, folder), dirs_exist_ok=True)
            print(f" [OK] Pasta {folder}/")

    # 4. Sincronizar Python Portátil
    python_src = os.path.join(root_dir, 'python')
    python_dest = os.path.join(dist_dir, 'python')
    
    if os.path.exists(python_src):
        print("[*] Preparando Runtime Python...")
        shutil.copytree(python_src, python_dest, dirs_exist_ok=True)
        
        # MOVER DLLs para a raiz (Garante que o Windows encontre _socket, _ssl, etc.)
        dlls_dir = os.path.join(python_dest, 'DLLs')
        if os.path.exists(dlls_dir):
            print(" [*] Movendo DLLs para a raiz do Python...")
            for f in os.listdir(dlls_dir):
                shutil.copy2(os.path.join(dlls_dir, f), python_dest)
            shutil.rmtree(dlls_dir, ignore_errors=True)

        # CRIAR o arquivo de isolação correto (.pth)
        # Como as DLLs estao na raiz, basta incluir a raiz e a Lib
        pth_content = ".\nLib\nLib/site-packages\npython314.zip\n"
        with open(os.path.join(python_dest, "python314._pth"), "w") as f:
            f.write(pth_content)
        
        print(" [OK] Runtime Python 3.14 com ESTRUTURA FLATTEN configurada.")
    else:
        print("[!] ERRO CRITICO: Pasta 'python' nao encontrada na raiz!")
        return

    # 5. Criar Inicializador Simplificado
    launch_script = """@echo off
setlocal
cd /d "%~dp0"
title Vanguard Command Center
echo [*] Iniciando Dashboard...
set "PY_DIR=%~dp0python"
set "PY_EXE=%PY_DIR%\\python.exe"
:: Garantir isolamento
set PYTHONNOUSERSITE=1
set PYTHONPATH=
"%PY_EXE%" -m streamlit run dashboard.py --server.fileWatcherType none
if errorlevel 1 (
    echo [ERRO] Falha ao iniciar. Verifique se as dependencias estao instaladas.
    pause
)
"""
    with open(os.path.join(dist_dir, "Iniciar_Vanguard.bat"), "w") as f:
        f.write(launch_script)
    print(" [OK] Iniciar_Vanguard.bat criado.")

    # 6. Self-Test (Verificação de Integridade Agressiva - APENAS NO WINDOWS)
    if os.name == 'nt':
        print("[*] Executando teste de integridade agressivo...")
        py_exe = os.path.join(python_dest, "python.exe")
        test_script = "import ssl, socket, warnings; print('SSL_FILE:', ssl.__file__); print('SSL_VER:', getattr(ssl, 'OPENSSL_VERSION', 'MISSING')); print('PYTHON_OK')"
        try:
            # Forçar PATH no ambiente do subprocesso
            env = os.environ.copy()
            env["PYTHONNOUSERSITE"] = "1"
            env["PYTHONPATH"] = ""
            env["PATH"] = f"{python_dest};{os.path.join(python_dest, 'DLLs')};" + env.get("PATH", "")
            
            result = subprocess.run([py_exe, "-c", test_script], 
                                  capture_output=True, text=True, timeout=15,
                                  env=env)
            
            if "PYTHON_OK" in result.stdout and "MISSING" not in result.stdout:
                print(" [OK] Teste de isolacao total passou!")
            else:
                print("\n[!!!] ERRO DE INTEGRIDADE DETECTADO [!!!]")
                print(f"Saida: {result.stdout}")
                print(f"Erro: {result.stderr}")
                print("O pacote gerado esta CORROMPIDO e nao deve ser usado.")
                sys.exit(1)
        except Exception as e:
            print(f" [!] Falha fatal no teste de integridade local: {e}")
            sys.exit(1)
    else:
        print("[*] Ambiente Linux detectado (GitHub). Pulando teste de execucao do .exe...")

    print("\n[SUCESSO] Pacote gerado com sucesso em:")
    print(f" -> {dist_dir}")

if __name__ == "__main__":
    build_package()
