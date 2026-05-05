import os
import shutil

def gerar_versao_rede():
    # Caminho da raiz do projeto (um nível acima da pasta scripts)
    src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_dir = os.path.join(src_dir, 'CCP_Versao_Rede')

    print("=== Gerando Versão de Rede CCP (Centro de Controle da Programação) ===")
    print(f"Origem: {src_dir}")
    print(f"Destino: {dist_dir}")
    
    if os.path.exists(dist_dir):
        print(f"Limpando arquivos antigos em: {dist_dir}")
        for item in os.listdir(dist_dir):
            item_path = os.path.join(dist_dir, item)
            try:
                if os.path.isfile(item_path): os.remove(item_path)
                elif os.path.isdir(item_path): shutil.rmtree(item_path)
            except PermissionError:
                print(f" [!] Aviso: Não foi possível remover {item}. Arquivo em uso.")
            except Exception as e:
                print(f" [!] Erro ao remover {item}: {e}")
    else:
        os.makedirs(dist_dir)

    # Tenta copiar a pasta 'python' da raiz se ela existir (Sincronia robusta)
    python_src = os.path.join(src_dir, 'python')
    python_dest = os.path.join(dist_dir, 'python')
    if os.path.exists(python_src):
        print(" [OK] Sincronizando pasta 'python' portátil (Atualizando arquivos)...")
        try:
            # Usamos dirs_exist_ok=True para permitir atualização mesmo se a pasta estiver aberta
            shutil.copytree(python_src, python_dest, dirs_exist_ok=True)
            
            # Limpeza APENAS do pyvenv.cfg (que causa erros de venv)
            # NÃO removemos o ._pth pois ele é vital para isolação no Python portátil
            for conflict_file in ['pyvenv.cfg']:
                cf_path = os.path.join(python_dest, conflict_file)
                if os.path.exists(cf_path):
                    try:
                        os.remove(cf_path)
                    except:
                        pass
            
            # Garante que o arquivo de isolação exista (Vital para evitar erro de circular import em warnings)
            pth_file = os.path.join(python_dest, 'python314._pth')
            pth_content = ".\nLib\nLib/site-packages\nimport site\n"
            with open(pth_file, 'w', encoding='utf-8') as f:
                f.write(pth_content)
            print(" [OK] Arquivo de isolação 'python314._pth' garantido.")
            
        except Exception as e:
            print(f" [!] ERRO CRÍTICO ao copiar pasta 'python': {e}")
            print(" [!] Certifique-se de que nenhum programa está usando o Python da pasta de rede.")

    # Arquivos essenciais para o funcionamento na rede
    files_to_copy = [
        'dashboard.py',
        'extrator_demanda.py',
        'db_manager.py',
        'ccp_ui.py',
        'requirements.txt',
        'INSTALAR_DEPENDENCIAS_PORTABLE.bat',
        'Configurar_Servidor_Automatizado.bat',
        'ACESSAR_DASHBOARD.bat',
        'Iniciar_Dashboard_Local.bat',
        'calendario_programacao.html'
    ]

    for f in files_to_copy:
        src_file = os.path.join(src_dir, f)
        if os.path.exists(src_file):
            try:
                shutil.copy2(src_file, dist_dir)
                print(f" [OK] Copiado: {f}")
            except Exception as e:
                print(f" [!] ERRO ao copiar arquivo {f}: {e}")
        else:
            print(f" [!] ALERTA: Arquivo {f} não encontrado.")

    # Copia as pastas modulares
    for folder in ['components', 'views', 'scripts', '.streamlit']:
        src_folder = os.path.join(src_dir, folder)
        if os.path.exists(src_folder):
            try:
                shutil.copytree(src_folder, os.path.join(dist_dir, folder), dirs_exist_ok=True)
                print(f" [OK] Pasta {folder}/ copiada")
            except Exception as e:
                print(f" [!] ERRO ao copiar {folder}: {e}")

    # Cria arquivo de instruções para o usuário
    readme_content = """# VANGUARD COMMAND CENTER - VERSAO DE REDE

Esta versao foi preparada para ser executada direto da rede (I:/).

### INSTRUCOES DE INSTALACAO:

1. COPIAR PASTA PYTHON:
   Caso a pasta 'python' nao esteja aqui, copie a pasta portatil da raiz para ca.
   O arquivo 'ACESSAR_DASHBOARD.bat' espera encontrar o executavel em: ./python/python.exe

2. COMO ABRIR:
   Basta clicar duas vezes no arquivo 'ACESSAR_DASHBOARD.bat'.

### NOTAS:
- Nao eh necessario instalar Python no seu computador.
- Os dados sao lidos em tempo real do banco mestre na rede.
- Caso o Dashboard nao abra, verifique se voce tem acesso ao caminho da rede.

Desenvolvido por: Kennedy / Vanguard Team
"""
    
    with open(os.path.join(dist_dir, 'README_REDE.txt'), 'w', encoding='utf-8') as f:
        f.write(readme_content)
    print(" [OK] README_REDE.txt gerado.")

    print("\n[SUCESSO] Versão de Rede gerada com sucesso!")
    print(f"Local: {dist_dir}")
    print("\nPROXIMO PASSO: Se voce for usar em outro PC, garanta que a pasta 'python' esteja dentro de 'CCP_Versao_Rede'.")

if __name__ == "__main__":
    gerar_versao_rede()
