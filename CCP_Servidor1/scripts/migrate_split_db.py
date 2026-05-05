import sqlite3
import os
import shutil

# --- CONFIGURAÇÕES ---
REDE_DIR = r"I:\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programação\Dashboard MT"
DB_ORIGINAL = os.path.join(REDE_DIR, "demanda_publica.db")

# Novos Nomes
DB_DATA = os.path.join(REDE_DIR, "vanguard_data.db")
DB_APP = os.path.join(REDE_DIR, "vanguard_app.db")

def migrate():
    print("=== INICIANDO MIGRAÇÃO DE BANCO DE DADOS ===")
    
    if not os.path.exists(DB_ORIGINAL):
        print(f"[ERRO] Banco original não encontrado: {DB_ORIGINAL}")
        return

    # 1. Backup de segurança
    backup_path = DB_ORIGINAL + ".bak"
    shutil.copy2(DB_ORIGINAL, backup_path)
    print(f"[OK] Backup criado em: {backup_path}")

    # 2. Criar Banco de APLICAÇÃO (Célebro Persistente)
    print(f"[1/3] Criando {os.path.basename(DB_APP)} (Usuários e Configs)...")
    conn_orig = sqlite3.connect(DB_ORIGINAL)
    conn_app = sqlite3.connect(DB_APP)
    
    # Copia tabela de usuários
    try:
        # Pega o schema
        res = conn_orig.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='usuarios'")
        create_sql = res.fetchone()[0]
        conn_app.execute(create_sql)
        
        # Copia os dados
        usuarios = conn_orig.execute("SELECT * FROM usuarios").fetchall()
        col_names = [description[0] for description in conn_orig.execute("SELECT * FROM usuarios").description]
        placeholders = ",".join(["?"] * len(col_names))
        conn_app.executemany(f"INSERT INTO usuarios ({','.join(col_names)}) VALUES ({placeholders})", usuarios)
        conn_app.commit()
        print("    -> [OK] Tabela 'usuarios' migrada com sucesso.")
    except Exception as e:
        print(f"    -> [AVISO] Tabela 'usuarios' não encontrada ou erro: {e}")

    # Copia tabela de Log
    try:
        res = conn_orig.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='log_acesso'")
        create_sql = res.fetchone()[0]
        conn_app.execute(create_sql)
        logs = conn_orig.execute("SELECT * FROM log_acesso").fetchall()
        col_names = [description[0] for description in conn_orig.execute("SELECT * FROM log_acesso").description]
        placeholders = ",".join(["?"] * len(col_names))
        conn_app.executemany(f"INSERT INTO log_acesso ({','.join(col_names)}) VALUES ({placeholders})", logs)
        conn_app.commit()
        print("    -> [OK] Tabela 'log_acesso' migrada com sucesso.")
    except Exception as e:
        print(f"    -> [AVISO] Tabela 'log_acesso' não encontrada ou erro: {e}")

    conn_app.close()

    # 3. Criar Banco de DADOS (Dados de Extração)
    print(f"[2/3] Criando {os.path.basename(DB_DATA)} (Demandas e Snapshot)...")
    # Apenas copia o original e remove as tabelas de usuários para limpar
    shutil.copy2(DB_ORIGINAL, DB_DATA)
    conn_data = sqlite3.connect(DB_DATA)
    conn_data.execute("DROP TABLE IF EXISTS usuarios")
    conn_data.execute("DROP TABLE IF EXISTS log_acesso")
    conn_data.execute("VACUUM")
    conn_data.close()
    print("    -> [OK] Tabela de dados limpa e preparada.")

    conn_orig.close()
    
    print("\n[3/3] FINALIZANDO...")
    print("Bancos criados na rede:")
    print(f" - APP: {DB_APP}")
    print(f" - DATA: {DB_DATA}")
    print("\n[SUCESSO] Migração concluída. O arquivo antigo 'demanda_publica.db' pode ser removido após validação.")

if __name__ == "__main__":
    migrate()
