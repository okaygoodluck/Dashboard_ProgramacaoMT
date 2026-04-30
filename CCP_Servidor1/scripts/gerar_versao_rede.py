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
        print(f"Tentando limpar pasta anterior: {dist_dir}")
        try:
            shutil.rmtree(dist_dir)
            os.makedirs(dist_dir, exist_ok=True)
        except PermissionError:
            print("AVISO: Pasta de rede em uso. Prosseguindo com a atualização via sobrescrita...")
    else:
        os.makedirs(dist_dir)

    # Arquivos essenciais para o funcionamento na rede
    files_to_copy = [
        'dashboard.py',
        'extrator_demanda.py',
        'db_manager.py',
        'ccp_ui.py',
        'requirements.txt',
        'INSTALAR_DEPENDENCIAS_PORTABLE.bat',
        'Configurar_Servidor_Automatizado.bat',
        'ACESSAR_DASHBOARD.bat'
    ]

    for f in files_to_copy:
        src_file = os.path.join(src_dir, f)
        if os.path.exists(src_file):
            shutil.copy2(src_file, dist_dir)
            print(f" [OK] Copiado: {f}")
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
   Cole a sua pasta 'python' (portatil) dentro desta pasta aqui.
   O arquivo 'ACESSAR_DASHBOARD.bat' espera encontrar o executavel em: ./python/python.exe

2. COMO ABRIR:
   Basta clicar duas vezes no arquivo 'ACESSAR_DASHBOARD.bat'.

### NOTAS:
- Nao eh necessario instalar Python no seu computador.
- Os dados sao lidos em tempo real do banco mestre na rede (ccp_data.db).
- Caso o Dashboard nao abra, verifique se voce tem acesso ao caminho:
  I:\\IT\\ODCO\\PROGRAMACAO_MT\\1 - Sistemas da programação\\Dashboard MT

Desenvolvido por: Kennedy / Vanguard Team
"""
    
    with open(os.path.join(dist_dir, 'README_REDE.txt'), 'w', encoding='utf-8') as f:
        f.write(readme_content)
    print(" [OK] README_REDE.txt gerado.")

    print("\n[SUCESSO] Versão de Rede gerada com sucesso!")
    print(f"Local: {dist_dir}")
    print("\nPROXIMO PASSO: Coloque a pasta 'python' dentro de 'Vanguard_Versao_Rede' e pronto!")

if __name__ == "__main__":
    gerar_versao_rede()
