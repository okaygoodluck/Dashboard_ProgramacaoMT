import os
import shutil
import sys
import subprocess
import zipfile

# Caminhos da Rede (Sincronizado com db_manager.py)
_UNC_FQDN_ACC = r"\\SACORPARQ1.cemig.ad.corp\GROUPS\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programação\Dashboard MT"
_UNC_FQDN_NORM = r"\\SACORPARQ1.cemig.ad.corp\GROUPS\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programacao\Dashboard MT"
_UNC_REDE_ACC = r"\\SACORPARQ1\GROUPS\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programação\Dashboard MT"
_UNC_REDE_NORM = r"\\SACORPARQ1\GROUPS\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programacao\Dashboard MT"
_REDE_ACC = r"I:\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programação\Dashboard MT"
_REDE_NORM = r"I:\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programacao\Dashboard MT"

_CANDIDATOS_BUILD = [
    os.environ.get("CCP_DASHBOARD_DB_PATH"),
    _UNC_FQDN_ACC,
    _UNC_FQDN_NORM,
    _UNC_REDE_ACC,
    _UNC_REDE_NORM,
    _REDE_ACC,
    _REDE_NORM
]
REDE_BASE = next((c for c in _CANDIDATOS_BUILD if c and os.path.exists(c)), _UNC_FQDN_ACC)

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
        try:
            shutil.rmtree(dist_dir)
        except Exception as e:
            print(f" [!] Aviso na limpeza total: {e}. Executando limpeza seletiva...")
            # Limpar resíduos de builds anteriores se rmtree falhar (ex: arquivos bloqueados no python)
            for item in os.listdir(dist_dir):
                item_path = os.path.join(dist_dir, item)
                if item == "python":
                    continue  # Mantém o runtime python se estiver em uso
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path, ignore_errors=True)
                else:
                    try: os.remove(item_path)
                    except: pass

    # Extensões proibidas em builds (qualquer tipo de banco de dados ou journal)
    DB_EXTENSIONS = ('.db', '.bd', '.sqlite', '.sqlite3', '.db-journal', '.db-wal', '.db-shm')

    # Garantir que nenhum banco de dados ou script legado sobreviveu
    for root, dirs, files in os.walk(dist_dir):
        for f in files:
            if f.lower().endswith(DB_EXTENSIONS) or f in ('extrator_demanda.py', 'agendador.py', 'requirements.txt'):
                try: os.remove(os.path.join(root, f))
                except: pass
    
    if os.path.exists(zip_path):
        print(f"[*] Removendo ZIP antigo...")
        try:
            os.remove(zip_path)
        except:
            pass
        
    os.makedirs(dist_dir, exist_ok=True)

    # 2. Whitelist de arquivos essenciais do Cliente Portátil (Thin Client)
    # NÃO incluir bancos de dados (.db): a versão portátil conecta 100% na base oficial da rede
    essential_files = [
        '.env',
        'dashboard.py',
        'db_manager.py',
        'ccp_ui.py'
    ]

    print("[*] Copiando arquivos essenciais da interface...")
    for f in essential_files:
        src = os.path.join(root_dir, f)
        if os.path.exists(src):
            shutil.copy2(src, dist_dir)
            print(f" [OK] {f}")
        else:
            print(f" [!] AVISO: {f} não encontrado.")

    # 3. Copiar pastas modulares da interface
    essential_folders = ['components', 'views', '.streamlit']
    for folder in essential_folders:
        src = os.path.join(root_dir, folder)
        if os.path.exists(src):
            shutil.copytree(src, os.path.join(dist_dir, folder), dirs_exist_ok=True)
            print(f" [OK] Pasta {folder}/")

    # 3.1. Copiar apenas os scripts auxiliares do cliente (sincronização de e-mails)
    essential_scripts = [
        'sync_emails.ps1',
        'send_reset_email.ps1'
    ]
    scripts_dest = os.path.join(dist_dir, 'scripts')
    if os.path.exists(scripts_dest):
        shutil.rmtree(scripts_dest, ignore_errors=True)
    os.makedirs(scripts_dest, exist_ok=True)
    print("[*] Copiando scripts essenciais...")
    for script in essential_scripts:
        src = os.path.join(root_dir, 'scripts', script)
        if os.path.exists(src):
            shutil.copy2(src, scripts_dest)
            print(f" [OK] scripts/{script}")

    # 4. Sincronizar Python Portátil
    python_src = os.path.join(root_dir, 'python')
    python_dest = os.path.join(dist_dir, 'python')
    
    if os.path.exists(python_src):
        print("[*] Preparando Runtime Python...")
        shutil.copytree(python_src, python_dest, dirs_exist_ok=True)
        
        # PRÉ-INSTALAR DEPENDÊNCIAS
        print(" [*] Verificando dependências no ambiente portátil...")
        py_exe = os.path.join(python_dest, 'python.exe')
        req_path = os.path.join(root_dir, 'requirements.txt')
        
        import glob
        pth_files = glob.glob(os.path.join(python_dest, "python*._pth"))
        for pth in pth_files:
            try: os.remove(pth)
            except: pass

        try:
            env = os.environ.copy()
            env["PYTHONNOUSERSITE"] = "1"
            subprocess.run([py_exe, "-m", "pip", "install", "-r", req_path, "--disable-pip-version-check"], env=env, check=True)
            print(" [OK] Dependências instaladas com sucesso no pacote portátil!")
        except Exception as e:
            print(f" [!] Erro ao instalar dependências: {e}")

        # MOVER DLLs para a raiz (Garante que o Windows encontre _socket, _ssl, etc.)
        dlls_dir = os.path.join(python_dest, 'DLLs')
        if os.path.exists(dlls_dir):
            print(" [*] Movendo DLLs para a raiz do Python...")
            for f in os.listdir(dlls_dir):
                shutil.copy2(os.path.join(dlls_dir, f), python_dest)
            shutil.rmtree(dlls_dir, ignore_errors=True)

        # Remover pastas desnecessárias para economizar espaço
        share_dir = os.path.join(python_dest, 'share')
        if os.path.exists(share_dir):
            shutil.rmtree(share_dir, ignore_errors=True)
        include_dir = os.path.join(python_dest, 'include')
        if os.path.exists(include_dir):
            shutil.rmtree(include_dir, ignore_errors=True)

        # CRIAR o arquivo de isolação correto (.pth)
        # Inclui o diretório raiz (.), pasta do app pai (..), Lib e site-packages
        pth_content = ".\n..\nLib\nLib/site-packages\npython314.zip\nimport site\n"
        with open(os.path.join(python_dest, "python314._pth"), "w") as f:
            f.write(pth_content)
        
        print(" [OK] Runtime Python configurado com isolamento total e vínculo ao app.")
    else:
        print("[!] ERRO CRITICO: Pasta 'python' nao encontrada na raiz!")
        return

    # 5. Criar Inicializador CCP
    launch_script = """@echo off
setlocal
cd /d "%~dp0"
title CCP - Centro de Controle da Programacao

set "PY_DIR=%~dp0python"
set "PY_EXE=%PY_DIR%\\python.exe"
:: Garantir isolamento
set PYTHONNOUSERSITE=1
set PYTHONPATH=

echo [*] Iniciando Dashboard CCP...
"%PY_EXE%" -m streamlit run dashboard.py --server.fileWatcherType none --browser.gatherUsageStats false
if errorlevel 1 (
    echo [ERRO] Falha ao iniciar o CCP. Verifique se os arquivos estao completos.
    pause
)
"""
    with open(os.path.join(dist_dir, "Iniciar_CCP.bat"), "w") as f:
        f.write(launch_script)
    print(" [OK] Iniciar_CCP.bat criado (otimizado, sem verificacao de pip).")

    # 6. Criar Pacote ZIP Final
    print(f"[*] Criando pacote final {zip_name}...")
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(dist_dir):
                # Excluir pastas desnecessárias do arquivo compactado
                dirs[:] = [d for d in dirs if d != '__pycache__' and not d.startswith('.')]
                for file in files:
                    # Garantir que nenhum banco de dados ou bytecode (.pyc) entre no ZIP
                    if file.lower().endswith(DB_EXTENSIONS) or file.endswith('.pyc'):
                        continue
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
