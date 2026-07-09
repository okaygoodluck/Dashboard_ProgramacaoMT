import os
import shutil
import zipfile

def build_server_package():
    print("========================================================")
    print("   CCP - CENTRO DE CONTROLE DA PROGRAMACAO")
    print("           BUILDER PARA SERVIDOR (APENAS CODIGO)")
    print("========================================================")

    # Definir diretórios
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_name = "CCP_Servidor_Ready"
    dist_dir = os.path.join(root_dir, dist_name)
    zip_name = "CCP_Servidor_Codigo.zip"
    zip_path = os.path.join(root_dir, zip_name)
    
    print(f"[*] Raiz: {root_dir}")
    print(f"[*] Pasta de Build: {dist_dir}")

    # 1. Limpeza
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir, ignore_errors=True)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    os.makedirs(dist_dir, exist_ok=True)

    # 2. Arquivos de Código e Configuração
    essential_files = [
        'dashboard.py',
        'extrator_demanda.py',
        'db_manager.py',
        'ccp_ui.py',
        'requirements.txt',
        'calendario_programacao.html',
        'Iniciar_CCP_Servidor.bat'
    ]

    print("[*] Copiando arquivos de codigo...")
    for f in essential_files:
        src = os.path.join(root_dir, f)
        if os.path.exists(src):
            shutil.copy2(src, dist_dir)
            print(f" [OK] {f}")

    # 3. Copiar pastas modulares (apenas as necessárias para rodar)
    essential_folders = ['components', 'views', '.streamlit']
    for folder in essential_folders:
        src = os.path.join(root_dir, folder)
        if os.path.exists(src):
            shutil.copytree(src, os.path.join(dist_dir, folder), dirs_exist_ok=True)
            print(f" [OK] Pasta {folder}/")

    # 3.1. Copiar apenas os scripts essenciais (excluir scripts de build e github)
    essential_scripts = [
        'agendador.py',
        'iniciar_agendador.bat',
        'configurar_credenciais.py',
        'configurar_credenciais.bat',
        'sync_emails.ps1'
    ]
    scripts_dest = os.path.join(dist_dir, 'scripts')
    os.makedirs(scripts_dest, exist_ok=True)
    print("[*] Copiando scripts essenciais...")
    for script in essential_scripts:
        src = os.path.join(root_dir, 'scripts', script)
        if os.path.exists(src):
            shutil.copy2(src, scripts_dest)
            print(f" [OK] scripts/{script}")

    # 4. Criar ZIP (Sem a pasta python)
    print(f"[*] Criando pacote para servidor {zip_name}...")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(dist_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, dist_dir)
                zipf.write(file_path, arcname)

    print("\n[SUCESSO] PACOTE DE SERVIDOR PRONTO!")
    print(f" Arquivo: {zip_path}")
    print(" (Este pacote nao contem o Python, use o do sistema no servidor)")

if __name__ == "__main__":
    build_server_package()
