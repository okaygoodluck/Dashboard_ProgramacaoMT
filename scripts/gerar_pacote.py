import os
import shutil

def gerar_pacote():
    # Caminho da raiz do projeto (um nível acima da pasta scripts)
    src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_dir = os.path.join(src_dir, 'CCP_Servidor')

    print(f"=== Gerando Pacote: Centro de Controle da Programação (Servidor) ===")
    print(f"Origem: {src_dir}")
    print(f"Destino: {dist_dir}")
    
    if os.path.exists(dist_dir):
        print("Tentando limpar pasta anterior...")
        try:
            shutil.rmtree(dist_dir)
            os.makedirs(dist_dir, exist_ok=True)
        except PermissionError:
            print("AVISO: Não foi possível deletar a pasta completa (arquivo em uso). Prosseguindo com a sobrescrita dos arquivos...")
    else:
        os.makedirs(dist_dir)

    files_to_copy = [
        'dashboard.py',
        'extrator_demanda.py',
        'db_manager.py',
        'ccp_ui.py',
        'requirements.txt',
        'INSTALAR_DEPENDENCIAS_PORTABLE.bat',
        'Configurar_Servidor_Automatizado.bat',
        'Iniciar_Dashboard_Servidor.bat',
        'Iniciar_Dashboard_Local.bat',
        'Iniciar_Dashboard_Oculto.vbs'
    ]

    for f in files_to_copy:
        src_file = os.path.join(src_dir, f)
        if os.path.exists(src_file):
            shutil.copy2(src_file, dist_dir)
            print(f" OK: {f}")
        else:
            print(f" ALERTA: Arquivo {f} não encontrado.")

    # Copia as pastas modulares
    for folder in ['components', 'views', 'scripts', '.streamlit']:
        src_folder = os.path.join(src_dir, folder)
        if os.path.exists(src_folder):
            try:
                shutil.copytree(src_folder, os.path.join(dist_dir, folder), dirs_exist_ok=True)
                print(f" OK: pasta {folder}/")
            except Exception as e:
                print(f" ERRO ao copiar {folder}: {e}")

    # Cria pasta de relatórios vazia
    rel_dir = os.path.join(dist_dir, 'relatorios')
    if not os.path.exists(rel_dir):
        os.makedirs(rel_dir)
        print(" OK: pasta relatorios/ criada")

    print("\n[SUCESSO] Pacote gerado com sucesso!")
    print(f"Acesse a pasta: {dist_dir}")

if __name__ == "__main__":
    gerar_pacote()
