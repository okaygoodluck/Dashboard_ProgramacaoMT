import os
import shutil
import sys
import subprocess
import zipfile

def build_package():
    print("========================================================")
    print("   CCP - CENTRO DE CONTROLE DA PROGRAMACAO")
    print("           BUILDER PORTATIL (LOCAL)")
    print("========================================================")

    # Definir diretórios
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_name = "CCP_Portable_Ready"
    dist_dir = os.path.join(root_dir, dist_name)
    zip_name = "CCP_Portable.zip"
    zip_path = os.path.join(root_dir, zip_name)
    
    print(f"[*] Raiz: {root_dir}")
    print(f"[*] Pasta de Build: {dist_dir}")

    # 1. Limpeza da pasta de destino e ZIP antigo
    if os.path.exists(dist_dir):
        print(f"[*] Limpando pasta de build...")
        shutil.rmtree(dist_dir, ignore_errors=True)
    
    if os.path.exists(zip_path):
        print(f"[*] Removendo ZIP antigo...")
        os.remove(zip_path)
        
    os.makedirs(dist_dir)

    # 2. Whitelist de arquivos essenciais
    essential_files = [
        'dashboard.py',
        'extrator_demanda.py',
        'db_manager.py',
        'ccp_ui.py',
        'requirements.txt',
        'calendario_programacao.html'
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
            # No caso da pasta scripts, vamos evitar copiar o próprio build_portable para não gerar loop
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
        
        print(" [OK] Runtime Python configurado com isolamento total.")
    else:
        print("[!] ERRO CRITICO: Pasta 'python' nao encontrada na raiz!")
        return

    # 5. Criar Inicializador CCP
    launch_script = """@echo off
setlocal
cd /d "%~dp0"
title CCP - Centro de Controle da Programacao
echo [*] Iniciando Dashboard CCP...
set "PY_DIR=%~dp0python"
set "PY_EXE=%PY_DIR%\\python.exe"
:: Garantir isolamento
set PYTHONNOUSERSITE=1
set PYTHONPATH=
"%PY_EXE%" -m streamlit run dashboard.py --server.fileWatcherType none --browser.gatherUsageStats false --server.headless true
if errorlevel 1 (
    echo [ERRO] Falha ao iniciar o CCP. Verifique se os arquivos estao completos.
    pause
)
"""
    with open(os.path.join(dist_dir, "Iniciar_CCP.bat"), "w") as f:
        f.write(launch_script)
    print(" [OK] Iniciar_CCP.bat criado.")

    # 6. Criar Pacote ZIP Final
    print(f"[*] Criando pacote final {zip_name}...")
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(dist_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, dist_dir)
                    zipf.write(file_path, arcname)
        print(f" [OK] ZIP criado com sucesso em: {zip_path}")
    except Exception as e:
        print(f" [!] Erro ao criar ZIP: {e}")

    print("\n========================================================")
    print(f" [SUCESSO] CCP PRONTO PARA DISTRIBUICAO!")
    print(f" Local: {zip_path}")
    print("========================================================")

if __name__ == "__main__":
    build_package()
