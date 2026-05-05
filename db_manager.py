import sqlite3
import pandas as pd
import datetime
import os

# Nomes dos arquivos de banco de dados (Oficiais: CCP - Centro de Controle da Programação)
DB_APP_NAME = "ccp_app.db"    # Persistente (Usuários, Configs)
DB_DATA_NAME = "ccp_data.db"  # Volátil (Dados da Demanda)
LOCAL_DB_NAME = "demanda.db"  # Temporário Local para o Extrator

# Caminhos Mestres na Rede (Tenta com e sem acento para robustez)
_REDE_ACC = r"I:\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programação\Dashboard MT"
_REDE_NORM = r"I:\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programacao\Dashboard MT"
REDE_BASE = _REDE_ACC if os.path.exists(_REDE_ACC) else _REDE_NORM

REDE_APP_PATH = os.path.join(REDE_BASE, DB_APP_NAME)
REDE_DATA_PATH = os.path.join(REDE_BASE, DB_DATA_NAME)

def _get_path(filename, network_path, alt_env_key=None):
    """Lógica de descoberta: Ambiente > Local > Rede"""
    # 1. Variável de Ambiente (Padronizada)
    env_key = f"CCP_{filename.upper().replace('.','_')}_PATH"
    env_val = os.environ.get(env_key)
    if env_val and os.path.exists(env_val):
        return env_val
    
    # 1.1 Variável de Ambiente Alternativa (Legado ou .bat)
    if alt_env_key:
        env_val = os.environ.get(alt_env_key)
        if env_val and os.path.exists(env_val):
            return env_val

    # 2. Pasta atual (Portabilidade)
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if os.path.exists(local):
        return local

    # 3. Caminho da Rede
    if os.path.exists(network_path):
        return network_path
    
    return None

def get_app_db_path():
    """Retorna o caminho do banco de sistema (prioriza rede)."""
    p = _get_path(DB_APP_NAME, REDE_APP_PATH)
    return p if p else DB_APP_NAME # Fallback para o nome padrão se nada for encontrado

def get_data_db_path():
    """Retorna o caminho do banco de dados de demanda (prioriza rede)."""
    # Aceita DEMANDA_DB_PATH que é comumente usado nos .bat
    p = _get_path(DB_DATA_NAME, REDE_DATA_PATH, alt_env_key="DEMANDA_DB_PATH")
    
    # Fallback se não encontrar o oficial, tenta o nome antigo na rede
    if not p:
        alt_network = os.path.join(REDE_BASE, "demanda_publica.db")
        if os.path.exists(alt_network):
            return alt_network
            
    return p if p else LOCAL_DB_NAME # Fallback para o local se nada for encontrado

def publicar_db_rede():
    """Copia o arquivo local 'demanda.db' para a rede como 'ccp_data.db'"""
    import shutil
    try:
        src_db = LOCAL_DB_NAME
        if os.path.exists(src_db):
            # Garante que a pasta destino existe
            os.makedirs(REDE_BASE, exist_ok=True)
            
            # Copia com sobrescrita
            shutil.copy2(src_db, REDE_DATA_PATH)
            print(f"[OK] Dados da demanda publicados na rede: {REDE_DATA_PATH}")
            return True
        else:
            print(f"[AVISO] Arquivo local '{src_db}' não encontrado para publicar.")
    except Exception as e:
        print(f"[ERRO REDE] Falha ao publicar dados na rede: {e}")
    return False

def get_connection_read():
    """Conexão para leitura de dados de demanda (Prioriza Rede)."""
    path = get_data_db_path()
    try:
        # Se for banco de rede, usa URI para modo leitura-apenas e evitar bloqueios
        if "I:" in path.upper():
            uri = f"file:{path.replace('\\','/')}?mode=ro&immutable=1"
            return sqlite3.connect(uri, uri=True, timeout=10)
        return sqlite3.connect(path, timeout=10)
    except Exception:
        return sqlite3.connect(path, timeout=10)

def get_connection_write():
    """Conexão para escrita (EXTRATOR). Sempre salva no banco local 'demanda.db'."""
    return sqlite3.connect(LOCAL_DB_NAME, timeout=30)

def get_connection_config():
    """Conexão para sistema (Usuários/Config). Prioriza 'ccp_app.db' na rede."""
    path = get_app_db_path()
    return sqlite3.connect(path, timeout=30)

def salvar_dados(df):
    """
    Salva os dados no banco de dados com suporte a auto-migração de colunas.
    """
    if df is None or df.empty:
        print("Nenhum dado para salvar no banco.")
        return
    
    conn = get_connection_write()
    try:
        # Adiciona data de extração
        timestamp = datetime.datetime.now()
        df['Data_Extracao'] = timestamp

        # --- AUTO-MIGRAÇÃO DE COLUNAS ---
        def sync_schema(table_name, target_df):
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            existing_cols = [col[1] for col in cursor.fetchall()]
            
            if existing_cols:
                for col in target_df.columns:
                    if col not in existing_cols:
                        print(f"[DB] Adicionando coluna nova '{col}' na tabela '{table_name}'...")
                        # SQLite só permite adicionar colunas uma por uma
                        cursor.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "{col}" TEXT')
            conn.commit()

        # 1. Salva Snapshot Atual (Replace - não precisa de migração pois apaga e cria)
        df.to_sql('demanda_atual', conn, if_exists='replace', index=False)
        print(f"[DB] Snapshot atualizado na tabela 'demanda_atual'. ({len(df)} registros)")

        # 2. Salva Histórico (Append - exige sincronia de colunas)
        sync_schema('demanda_historico', df)
        df.to_sql('demanda_historico', conn, if_exists='append', index=False)
        print("[DB] Dados adicionados ao histórico na tabela 'demanda_historico'.")

    except Exception as e:
        print(f"[DB] Erro ao salvar dados: {e}")
        raise e  # Propaga para que o Extrator saiba que falhou
    finally:
        conn.close()

def carregar_dados_recentes():
    """Carrega os dados da tabela 'demanda_atual'."""
    conn = get_connection_read()
    try:
        # Verifica se tabela existe
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='demanda_atual';")
        if not cursor.fetchone():
            return None

        df = pd.read_sql("SELECT * FROM demanda_atual", conn)
        return df
    except Exception as e:
        print(f"[DB] Erro ao carregar dados: {e}")
        return None
    finally:
        conn.close()

def carregar_historico():
    """Carrega todo o histórico."""
    conn = get_connection_read()
    try:
        df = pd.read_sql("SELECT * FROM demanda_historico", conn)
        return df
    except Exception:
        return None
    finally:
        conn.close()

# --- NOVAS FUNÇÕES DE SEGURANÇA E GESTÃO ---

def verificar_login(matricula, password):
    """Verifica as credenciais do usuário."""
    import hashlib
    senha_hash = hashlib.sha256(password.encode()).hexdigest()
    
    conn = get_connection_config()
    try:
        cursor = conn.cursor()
        # COLLATE NOCASE para permitir c012345 ou C012345
        cursor.execute("SELECT matricula, nome, nivel, senha_provisoria FROM usuarios WHERE matricula = ? COLLATE NOCASE AND password_hash = ?", (matricula, senha_hash))
        return cursor.fetchone()
    except Exception:
        return None
    finally:
        conn.close()

def atualizar_senha(matricula, nova_senha):
    """Atualiza a senha do usuário e remove a flag de provisória."""
    import hashlib
    senha_hash = hashlib.sha256(nova_senha.encode()).hexdigest()
    
    conn = get_connection_config()
    try:
        conn.execute("UPDATE usuarios SET password_hash = ?, senha_provisoria = 0 WHERE matricula = ? COLLATE NOCASE", (senha_hash, matricula))
        conn.commit()
        return True
    except Exception as e:
        error_msg = str(e)
        print(f"[ERRO DB] Falha ao atualizar senha: {error_msg}")
        return error_msg
    finally:
        conn.close()

def listar_usuarios():
    """Retorna lista de todos os usuários."""
    conn = get_connection_config()
    try:
        return pd.read_sql("SELECT matricula, nome, nivel FROM usuarios ORDER BY nome", conn)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()

def atualizar_nivel_usuario(matricula, novo_nivel):
    """Altera o nível de acesso de um usuário."""
    conn = get_connection_config()
    try:
        conn.execute("UPDATE usuarios SET nivel = ? WHERE matricula = ? COLLATE NOCASE", (novo_nivel, matricula))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def criar_usuario(matricula, nome, nivel):
    """Cria um novo usuário com senha padrão '12345'."""
    import hashlib
    senha_padrao = "12345"
    senha_hash = hashlib.sha256(senha_padrao.encode()).hexdigest()
    
    conn = get_connection_config()
    try:
        conn.execute("""
            INSERT INTO usuarios (matricula, nome, password_hash, nivel, senha_provisoria)
            VALUES (?, ?, ?, ?, 1)
        """, (matricula.strip(), nome.strip(), senha_hash, nivel))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def deletar_usuario(matricula):
    """Remove um usuário do sistema."""
    conn = get_connection_config()
    try:
        conn.execute("DELETE FROM usuarios WHERE matricula = ? COLLATE NOCASE", (matricula,))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def resetar_senha(matricula):
    """Reseta a senha para '12345' e marca como provisória."""
    import hashlib
    senha_padrao = "12345"
    senha_hash = hashlib.sha256(senha_padrao.encode()).hexdigest()
    
    conn = get_connection_config()
    try:
        conn.execute("""
            UPDATE usuarios 
            SET password_hash = ?, senha_provisoria = 1 
            WHERE matricula = ? COLLATE NOCASE
        """, (senha_hash, matricula))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def get_mapeamento_regioes():
    """Retorna o mapeamento atual de regiões x técnicos."""
    conn = get_connection_config()
    try:
        query = """
        SELECT r.sigla_regiao, u.nome as responsavel, u.matricula
        FROM regioes_responsaveis r
        LEFT JOIN usuarios u ON r.matricula_responsavel = u.matricula
        """
        return pd.read_sql(query, conn)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()

def atualizar_responsavel_regiao(sigla_regiao, matricula_responsavel):
    """Atualiza o técnico responsável por uma região específica."""
    conn = get_connection_config()
    try:
        conn.execute('''
            INSERT INTO regioes_responsaveis (sigla_regiao, matricula_responsavel)
            VALUES (?, ?)
            ON CONFLICT(sigla_regiao) DO UPDATE SET matricula_responsavel=excluded.matricula_responsavel
        ''', (sigla_regiao, matricula_responsavel))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def get_regioes_disponiveis_data():
    """Busca todas as siglas de regiões presentes nos dados de demanda atual."""
    conn = get_connection_read()
    try:
        # Pega as primeiras 2 letras da coluna Ref_Regiao
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT Ref_Regiao FROM demanda_atual")
        regioes = set()
        for row in cursor.fetchall():
            if row[0] and len(row[0]) >= 2:
                regioes.add(row[0][:2].upper().strip())
        return sorted(list(regioes))
    except Exception:
        return []
    finally:
        conn.close()

def atribuir_regioes_massa(matricula_responsavel, lista_siglas):
    """Atribui uma lista de regiões a um único responsável."""
    conn = get_connection_config()
    try:
        cursor = conn.cursor()
        
        # 1. Primeiro, remove todas as atribuições atuais deste técnico
        # Isso permite que, se o usuário desmarcar uma região, ela seja removida
        cursor.execute("DELETE FROM regioes_responsaveis WHERE matricula_responsavel = ?", (matricula_responsavel,))
        
        # 2. Agora insere as novas seleções
        for sigla in lista_siglas:
            cursor.execute('''
                INSERT INTO regioes_responsaveis (sigla_regiao, matricula_responsavel)
                VALUES (?, ?)
                ON CONFLICT(sigla_regiao) DO UPDATE SET matricula_responsavel=excluded.matricula_responsavel
            ''', (sigla, matricula_responsavel))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

# --- GESTÃO DE SESSÕES PERSISTENTES (VANGUARD STAY) ---

def init_database():
    """Inicializa o banco de dados do zero se não existir (Auto-Healing)."""
    conn = get_connection_config()
    try:
        # 1. Tabela de Usuários
        conn.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                matricula TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                nivel TEXT NOT NULL,
                senha_provisoria INTEGER DEFAULT 1
            )
        ''')
        
        # 2. Tabela de Responsáveis por Região
        conn.execute('''
            CREATE TABLE IF NOT EXISTS regioes_responsaveis (
                sigla_regiao TEXT PRIMARY KEY,
                matricula_responsavel TEXT,
                FOREIGN KEY (matricula_responsavel) REFERENCES usuarios (matricula)
            )
        ''')

        # 3. Tabela de Sessões Persistentes
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sessoes_persistentes (
                token TEXT PRIMARY KEY,
                matricula TEXT NOT NULL,
                data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data_expiracao TIMESTAMP NOT NULL
            )
        ''')

        # 4. Tabela de Histórico de KPIs Diários
        conn.execute('''
            CREATE TABLE IF NOT EXISTS vanguard_daily_kpis (
                data_ref TEXT PRIMARY KEY,
                total_demandas INTEGER,
                atrasadas INTEGER,
                alertas INTEGER,
                urgencias INTEGER,
                no_prazo INTEGER,
                confirmadas_total INTEGER,
                timestamp_captura TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 5. Criar usuário ADM padrão se a tabela de usuários estiver vazia
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM usuarios")
        if cursor.fetchone()[0] == 0:
            import hashlib
            # Login mestre para o usuário atual (Kennedy)
            senha_padrao = "12345"
            senha_hash = hashlib.sha256(senha_padrao.encode()).hexdigest()
            conn.execute("""
                INSERT INTO usuarios (matricula, nome, password_hash, nivel, senha_provisoria)
                VALUES ('c057573', 'Kennedy Garito', ?, 'ADM', 1)
            """, (senha_hash,))
            print("[INIT] Banco de dados novo detectado. Usuário ADM 'c057573' criado (senha: 12345).")
        
        conn.commit()
    except Exception as e:
        print(f"[ERRO INIT] Falha ao inicializar tabelas: {e}")
    finally:
        conn.close()

def gerar_token_sessao(matricula):
    """Gera um novo token de sessão com validade de 30 dias."""
    import secrets
    import datetime
    
    token = secrets.token_urlsafe(32)
    expiracao = datetime.datetime.now() + datetime.timedelta(days=30)
    
    conn = get_connection_config()
    try:
        conn.execute('''
            INSERT INTO sessoes_persistentes (token, matricula, data_expiracao)
            VALUES (?, ?, ?)
        ''', (token, matricula, expiracao))
        conn.commit()
        return token
    except Exception:
        return None
    finally:
        conn.close()

def validar_token_sessao(token):
    """Verifica se um token é válido e retorna os dados do usuário."""
    import datetime
    
    conn = get_connection_config()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT matricula FROM sessoes_persistentes 
            WHERE token = ? AND data_expiracao > ?
        ''', (token, datetime.datetime.now()))
        result = cursor.fetchone()
        
        if result:
            matricula = result[0]
            # Busca dados completos do usuário
            cursor.execute("SELECT matricula, nome, nivel FROM usuarios WHERE matricula = ? COLLATE NOCASE", (matricula,))
            return cursor.fetchone()
        return None
    finally:
        conn.close()

def remover_sessao(token):
    """Remove um token de sessão (logout)."""
    conn = get_connection_config()
    try:
        conn.execute("DELETE FROM sessoes_persistentes WHERE token = ?", (token,))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def salvar_kpi_diario(kpis):
    """
    Salva o snapshot de KPIs do dia.
    kpis: dict com chaves matching vanguard_daily_kpis
    """
    import datetime
    hoje = datetime.date.today().isoformat()
    
    conn = get_connection_config()
    try:
        conn.execute('''
            INSERT INTO vanguard_daily_kpis 
            (data_ref, total_demandas, atrasadas, alertas, urgencias, no_prazo, confirmadas_total)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(data_ref) DO UPDATE SET
                total_demandas=excluded.total_demandas,
                atrasadas=excluded.atrasadas,
                alertas=excluded.alertas,
                urgencias=excluded.urgencias,
                no_prazo=excluded.no_prazo,
                confirmadas_total=excluded.confirmadas_total,
                timestamp_captura=CURRENT_TIMESTAMP
        ''', (
            hoje, 
            kpis.get('total', 0), 
            kpis.get('atrasadas', 0), 
            kpis.get('alertas', 0), 
            kpis.get('urgencias', 0), 
            kpis.get('no_prazo', 0), 
            kpis.get('confirmadas', 0)
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"[KPI] Erro ao salvar snapshot: {e}")
        return False
    finally:
        conn.close()

def get_historico_kpis(dias=30):
    """Recupera o histórico de KPIs dos últimos N dias."""
    conn = get_connection_read()
    try:
        query = f"SELECT * FROM vanguard_daily_kpis ORDER BY data_ref DESC LIMIT {dias}"
        df = pd.read_sql(query, conn)
        if not df.empty:
            df = df.sort_values('data_ref')
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()

# Inicializa o banco de dados completo ao carregar o módulo
init_database()
