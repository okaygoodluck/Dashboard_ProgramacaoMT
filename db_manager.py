import sqlite3
import datetime
import pandas as pd
import os
import sys

def get_agora_br():
    """Retorna o horário atual em Brasília (UTC-3)."""
    return datetime.datetime.utcnow() - datetime.timedelta(hours=3)

# Nomes dos arquivos de banco de dados (Oficiais: CCP - Centro de Controle da Programação)
DB_APP_NAME = "ccp_app.db"    # Persistente (Usuários, Configs)
DB_DATA_NAME = "ccp_data.db"  # Volátil (Dados da Demanda)
LOCAL_DB_NAME = os.environ.get("CCP_LOCAL_DB_PATH", "demanda.db")  # Temporário Local para o Extrator

# Caminhos Mestres na Rede
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass # Permite rodar sem a biblioteca python-dotenv, caso não esteja instalada ainda

_ENV_REDE_BASE = os.environ.get("CCP_DASHBOARD_DB_PATH")
_REDE_ACC = r"I:\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programação\Dashboard MT"
_REDE_NORM = r"I:\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programacao\Dashboard MT"

if _ENV_REDE_BASE and os.path.exists(_ENV_REDE_BASE):
    REDE_BASE = _ENV_REDE_BASE
else:
    REDE_BASE = _REDE_ACC if os.path.exists(_REDE_ACC) else _REDE_NORM

REDE_APP_PATH = os.path.join(REDE_BASE, DB_APP_NAME)
REDE_DATA_PATH = os.path.join(REDE_BASE, DB_DATA_NAME)

def _get_path(filename, network_path, alt_env_key=None):
    """Lógica de descoberta: Ambiente > Rede > Local"""
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

    # 2. Caminho da Rede (Prioriza rede para manter tudo atualizado)
    if os.path.exists(network_path):
        return network_path

    # 3. Pasta atual (Portabilidade / Offline Fallback)
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if os.path.exists(local):
        return local
    
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
    conn = sqlite3.connect(path, timeout=30)
    try:
        # Resolve 'disk I/O error' em unidades de rede evitando a criação do arquivo -journal
        conn.execute("PRAGMA journal_mode = MEMORY")
        conn.execute("PRAGMA synchronous = NORMAL")
    except Exception:
        pass
    return conn

def salvar_dados(df, regioes_confirmadas_vazias=None):
    """
    Salva os dados no banco de dados com suporte a auto-migração de colunas e Memória de Segurança (Smart Merge).
    """
    if regioes_confirmadas_vazias is None:
        regioes_confirmadas_vazias = []

    if df is None or df.empty:
        print("Nenhum dado extraído na rodada. O banco de dados não será alterado para evitar apagão.")
        return
    
    # --- SMART MERGE: MEMÓRIA DE SEGURANÇA (Camada 3) ---
    df_antigo = None
    try:
        df_antigo = carregar_dados_recentes()
        if df_antigo is not None and not df_antigo.empty:
            regioes_novas = set(df['Ref_Regiao'].unique())
            regioes_antigas = set(df_antigo['Ref_Regiao'].unique())
            
            # Identifica regiões que estavam no banco, não vieram agora e não foram explicitamente confirmadas como vazias
            regioes_ausentes = (regioes_antigas - regioes_novas) - set(regioes_confirmadas_vazias)
            
            if regioes_ausentes:
                print(f"[DB] ALERTA: Regiões ausentes suspeitas detectadas: {regioes_ausentes}")
                print("[DB] Acionando Memória de Segurança (Smart Merge) para preservar histórico...")
                
                # Resgata do banco antigo apenas as regiões que sumiram sem confirmação
                df_preservado = df_antigo[df_antigo['Ref_Regiao'].isin(regioes_ausentes)]
                
                # Concatena os dados preservados com o dataframe atual
                df = pd.concat([df, df_preservado], ignore_index=True)
                print(f"[DB] {len(df_preservado)} registros antigos preservados na tabela atual.")
    except Exception as e:
        print(f"[DB] Falha no Smart Merge (ignorando e salvando apenas dados novos): {e}")

    # --- REGISTRO DE EVENTOS DE PRODUTIVIDADE ---
    try:
        registrar_eventos_diarios(df_antigo, df)
    except Exception as e:
        print(f"[DB] Erro ao disparar registro de eventos: {e}")

    # --- SNAPSHOT DE PENDENTES (Para D-1 independente do histórico) ---
    try:
        registrar_snapshot_pendentes(df)
    except Exception as e:
        print(f"[DB] Erro ao salvar snapshot de pendentes: {e}")

    conn = get_connection_write()
    try:
        # Adiciona data de extração apenas para os registros NOVOS (ou sobrescreve geral? O timestamp é do snapshot)
        # É melhor sobrescrever geral para o snapshot
        timestamp = get_agora_br()
        df['Data_Extracao'] = timestamp

        # --- AUTO-MIGRAÇÃO DE COLUNAS ---
        def sync_schema(table_name, target_df):
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            existing_cols = [col[1] for col in cursor.fetchall()]
            
            if existing_cols:
                for col in target_df.columns:
                    if col not in existing_cols:
                        # Mapeamento inteligente de tipos (Pandas -> SQLite)
                        dtype_str = str(target_df[col].dtype).lower()
                        sql_type = "TEXT"
                        if "int" in dtype_str:
                            sql_type = "INTEGER"
                        elif "float" in dtype_str:
                            sql_type = "REAL"
                        elif "datetime" in dtype_str:
                            sql_type = "DATETIME"
                        elif "bool" in dtype_str:
                            sql_type = "BOOLEAN"
                            
                        print(f"[DB] Adicionando coluna '{col}' ({sql_type}) na tabela '{table_name}'...")
                        cursor.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "{col}" {sql_type}')
            conn.commit()

        # 1. Salva Snapshot Atual (Replace - não precisa de migração pois apaga e cria)
        df.to_sql('demanda_atual', conn, if_exists='replace', index=False)
        print(f"[DB] Snapshot atualizado na tabela 'demanda_atual'. ({len(df)} registros totais consolidados)")

        # 2. Salva Histórico (Append - exige sincronia de colunas)
        sync_schema('demanda_historico', df)
        df.to_sql('demanda_historico', conn, if_exists='append', index=False)
        print("[DB] Dados adicionados ao histórico na tabela 'demanda_historico'.")

    except Exception as e:
        print(f"[DB] Erro ao salvar dados: {e}")
        raise e  # Propaga para que o Extrator saiba que falhou
    finally:
        conn.close()

def salvar_regioes_sistema(df_regioes):
    """
    Salva a lista completa de malhas e regiões identificadas no sistema de origem (GDIS),
    garantindo que todas as regiões existam como opção de filtro e atribuição, mesmo que tenham 0 demandas.
    """
    if df_regioes is None or df_regioes.empty:
        return
        
    conn = get_connection_write()
    try:
        df_regioes.to_sql('regioes_sistema', conn, if_exists='replace', index=False)
        print(f"[DB] Mapeamento de regiões do sistema salvo com sucesso. ({len(df_regioes)} regiões)")
    except Exception as e:
        print(f"[DB] Erro ao salvar regioes_sistema: {e}")
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

# --- NOVAS FUNÇÕES DE SEGURANÇA E GESTÃO ---

def verificar_login(matricula, password):
    """Verifica as credenciais do usuário com migração suave para bcrypt."""
    import hashlib
    import bcrypt
    
    conn = get_connection_config()
    try:
        cursor = conn.cursor()
        # COLLATE NOCASE para permitir c012345 ou C012345
        cursor.execute("SELECT matricula, nome, nivel, senha_provisoria, password_hash FROM usuarios WHERE matricula = ? COLLATE NOCASE", (matricula,))
        user_row = cursor.fetchone()
        
        if not user_row:
            return None
            
        stored_hash = user_row[4]
        
        # Verifica se o hash é antigo (plain SHA-256 é 64 chars hex)
        if len(stored_hash) == 64 and not stored_hash.startswith('$'):
            senha_hash_sha256 = hashlib.sha256(password.encode()).hexdigest()
            if stored_hash == senha_hash_sha256:
                # Migração suave para bcrypt
                novo_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                conn.execute("UPDATE usuarios SET password_hash = ? WHERE matricula = ? COLLATE NOCASE", (novo_hash, matricula))
                conn.commit()
                return user_row[:4]
            return None
        else:
            # Formato novo bcrypt
            try:
                if bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
                    return user_row[:4]
            except Exception as e:
                print(f"[AUTH] Erro ao checar bcrypt: {e}")
            return None
            
    except Exception as e:
        print(f"[AUTH] Erro interno verificar_login: {e}")
        return None
    finally:
        conn.close()

def atualizar_senha(matricula, nova_senha):
    """Atualiza a senha do usuário e remove a flag de provisória."""
    import bcrypt
    senha_hash = bcrypt.hashpw(nova_senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    conn = get_connection_config()
    try:
        conn.execute("UPDATE usuarios SET password_hash = ?, senha_provisoria = 0 WHERE matricula = ? COLLATE NOCASE", (senha_hash, matricula))
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERRO DB] Falha ao atualizar senha: {e}")
        return False
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

def criar_usuario(matricula, nome, nivel):
    """Cria um novo usuário com senha padrão '12345'."""
    import bcrypt
    senha_padrao = "12345"
    senha_hash = bcrypt.hashpw(senha_padrao.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
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

def alterar_nivel_usuario(matricula, novo_nivel):
    """Altera o nível de acesso de um usuário existente."""
    conn = get_connection_config()
    try:
        conn.execute("UPDATE usuarios SET nivel = ? WHERE matricula = ? COLLATE NOCASE", (novo_nivel, matricula))
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
    import bcrypt
    senha_padrao = "12345"
    senha_hash = bcrypt.hashpw(senha_padrao.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
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

def get_regioes_disponiveis_data():
    """Busca todas as siglas de regiões presentes no sistema, garantindo visibilidade mesmo para regiões vazias."""
    conn = get_connection_read()
    regioes = set()
    try:
        cursor = conn.cursor()
        
        # 1. Tenta buscar das regiões capturadas direto do sistema GDIS (Mais confiável)
        try:
            cursor.execute("SELECT DISTINCT Ref_Regiao FROM regioes_sistema")
            for row in cursor.fetchall():
                if row[0] and len(row[0]) >= 2:
                    regioes.add(row[0][:2].upper().strip())
        except Exception:
            pass

        # 2. Busca também da demanda atual (Fallback caso regioes_sistema falhe ou não exista)
        try:
            cursor.execute("SELECT DISTINCT Ref_Regiao FROM demanda_atual")
            for row in cursor.fetchall():
                if row[0] and len(row[0]) >= 2:
                    regioes.add(row[0][:2].upper().strip())
        except Exception:
            pass
            
    except Exception as e:
        print(f"[DB] Erro ao buscar regiões: {e}")
    finally:
        conn.close()
        
    # 3. Adiciona as regiões que já foram atribuídas no painel ADM (Garante consistência da interface)
    conn_app = get_connection_config()
    try:
        cursor_app = conn_app.cursor()
        cursor_app.execute("SELECT DISTINCT sigla_regiao FROM regioes_responsaveis")
        for row in cursor_app.fetchall():
            if row[0]:
                regioes.add(row[0].strip().upper())
    except Exception:
        pass
    finally:
        conn_app.close()

    return sorted(list(regioes))

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

        # 3. Tabela de Travamento de Responsabilidade (Option A)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS solicitacoes_travadas (
                solicitacao TEXT PRIMARY KEY,
                matricula TEXT NOT NULL,
                data_trava TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matricula) REFERENCES usuarios (matricula)
            )
        ''')

        # 4. Tabela de Sessões Persistentes
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sessoes_persistentes (
                token TEXT PRIMARY KEY,
                matricula TEXT NOT NULL,
                data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data_expiracao TIMESTAMP NOT NULL
            )
        ''')

        # 5. Tabela de Histórico de KPIs Diários
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

        # 6. Tabela de Eventos Diários
        conn.execute('''
            CREATE TABLE IF NOT EXISTS eventos_diarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                solicitacao TEXT NOT NULL,
                tipo_evento TEXT NOT NULL,
                regiao TEXT,
                matricula_responsavel TEXT,
                data_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 7. Tabela de Snapshot de Pendentes (Persistente para D-1)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pendentes_snapshot (
                data TEXT NOT NULL,
                matricula TEXT NOT NULL,
                pendentes_total INTEGER DEFAULT 0,
                pendentes_iniciadas INTEGER DEFAULT 0,
                pendentes_nao_iniciadas INTEGER DEFAULT 0,
                PRIMARY KEY (data, matricula)
            )
        ''')

        # 8. Criar usuário ADM padrão se a tabela de usuários estiver vazia
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM usuarios")
        if cursor.fetchone()[0] == 0:
            import bcrypt
            # Login mestre para o usuário atual (Kennedy)
            senha_padrao = "12345"
            senha_hash = bcrypt.hashpw(senha_padrao.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
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
    expiracao = get_agora_br() + datetime.timedelta(days=30)
    
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
        ''', (token, get_agora_br()))
        result = cursor.fetchone()
        
        if result:
            matricula = result[0]
            # Busca dados completos do usuário
            cursor.execute("SELECT matricula, nome, nivel, senha_provisoria FROM usuarios WHERE matricula = ? COLLATE NOCASE", (matricula,))
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
    conn = get_connection_config()
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

def get_solicitacoes_travadas():
    """Retorna as solicitações que já estão travadas em um responsável (Em elaboração)."""
    conn = get_connection_config()
    try:
        query = """
        SELECT st.solicitacao, u.nome as responsavel_travado, st.matricula as matricula_travada
        FROM solicitacoes_travadas st
        LEFT JOIN usuarios u ON st.matricula = u.matricula
        """
        return pd.read_sql(query, conn)
    except Exception as e:
        print(f"[DB] Erro ao buscar solicitacoes travadas: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

def travar_solicitacoes(df_novas):
    """Insere no banco as solicitações que devem ser travadas a um responsável.
    df_novas deve ter as colunas 'Solicitação' e 'Matricula'.
    """
    if df_novas is None or df_novas.empty:
        return False
        
    conn = get_connection_config()
    try:
        cursor = conn.cursor()
        for _, row in df_novas.iterrows():
            solicitacao = str(row['Solicitação']).strip()
            matricula = str(row['Matricula']).strip()
            
            cursor.execute('''
                INSERT INTO solicitacoes_travadas (solicitacao, matricula)
                VALUES (?, ?)
                ON CONFLICT(solicitacao) DO NOTHING
            ''', (solicitacao, matricula))
        conn.commit()
        return True
    except Exception as e:
        print(f"[DB] Erro ao travar solicitacoes: {e}")
        return False
    finally:
        conn.close()

def registrar_snapshot_pendentes(df_atual):
    """Calcula e grava o snapshot de pendentes do dia para cada usuário com base nas regiões atribuídas e travadas."""
    try:
        conn = get_connection_config()
        cursor = conn.cursor()
        data_hoje = get_agora_br().strftime('%Y-%m-%d')
        
        # Obter todos os usuários com regiões ou travadas
        cursor.execute("SELECT DISTINCT matricula_responsavel FROM regioes_responsaveis")
        users_regioes = set(row[0] for row in cursor.fetchall())
        
        cursor.execute("SELECT DISTINCT matricula FROM solicitacoes_travadas")
        users_travadas = set(row[0] for row in cursor.fetchall())
        
        todos_usuarios = users_regioes.union(users_travadas)
        
        # Filtra apenas demandas que contam como pendentes
        df_pendentes = df_atual[df_atual['Situação'].isin(['APROVADA', 'EM ELABORAÇÃO', 'EM ELABORACAO'])]
        
        for matricula in todos_usuarios:
            cursor.execute("SELECT sigla_regiao FROM regioes_responsaveis WHERE matricula_responsavel = ?", (matricula,))
            regioes = [row[0] for row in cursor.fetchall()]
            
            cursor.execute("SELECT solicitacao FROM solicitacoes_travadas WHERE matricula = ?", (matricula,))
            travadas = [row[0] for row in cursor.fetchall()]
            
            # Filtra df para o usuário
            mask = pd.Series(False, index=df_pendentes.index)
            if regioes:
                mask = mask | df_pendentes['Ref_Regiao'].str[:2].isin(regioes)
            if travadas:
                mask = mask | df_pendentes['Solicitação'].isin(travadas)
                
            df_user = df_pendentes[mask]
            
            total = len(df_user)
            iniciadas = len(df_user[df_user['Situação'].isin(['EM ELABORAÇÃO', 'EM ELABORACAO'])])
            nao_iniciadas = len(df_user[df_user['Situação'] == 'APROVADA'])
            
            # Insere ou atualiza
            cursor.execute("""
                INSERT INTO pendentes_snapshot (data, matricula, pendentes_total, pendentes_iniciadas, pendentes_nao_iniciadas)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(data, matricula) DO UPDATE SET
                    pendentes_total=excluded.pendentes_total,
                    pendentes_iniciadas=excluded.pendentes_iniciadas,
                    pendentes_nao_iniciadas=excluded.pendentes_nao_iniciadas
            """, (data_hoje, matricula, total, iniciadas, nao_iniciadas))
            
        conn.commit()
    except Exception as e:
        print(f"[DB] Erro no registro de snapshot de pendentes: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

# Inicializa o banco de dados completo ao carregar o módulo
init_database()

def registrar_eventos_diarios(df_antigo, df_novo):
    """
    Compara o df_antigo com o df_novo para registrar eventos de produtividade
    no banco de dados (NOVA, INICIADA, TRATADA).
    Ignora a primeira execução do dia para não herdar tratadas da madrugada.
    """
    try:
        conn = get_connection_config()
        cursor = conn.cursor()
        
        # Para consultar o historico precisamos da conexao de escrita (demanda.db)
        conn_hist = get_connection_write()
        cursor_hist = conn_hist.cursor()
        
        # --- PREVENÇÃO DA MADRUGADA ---
        # Verifica se já houve alguma extração salva HOJE no banco
        hoje_br = get_agora_br().strftime('%Y-%m-%d')
        cursor_hist.execute("SELECT COUNT(DISTINCT Data_Extracao) FROM demanda_historico WHERE date(Data_Extracao) = ?", (hoje_br,))
        extracoes_hoje = cursor_hist.fetchone()[0]
        
        data_evento_aplicar = get_agora_br().strftime('%Y-%m-%d %H:%M:%S')
        if extracoes_hoje == 0:
            print("[DB] Primeira extração do dia detectada. Atribuindo eventos pendentes (madrugada) ao final do dia anterior para preservar estoque de hoje.")
            cursor_hist.execute("SELECT MAX(Data_Extracao) FROM demanda_historico WHERE date(Data_Extracao) < ?", (hoje_br,))
            ultima_extracao = cursor_hist.fetchone()[0]
            if ultima_extracao:
                data_evento_aplicar = str(ultima_extracao)[:19]
                
        conn_hist.close()
            
        if df_antigo is None or df_antigo.empty:
            df_antigo = pd.DataFrame(columns=['Solicitação', 'Ref_Regiao', 'Situação'])
            
        if df_novo is None or df_novo.empty:
            return
            
        # Carrega dicionarios
        df_travadas = pd.read_sql("SELECT solicitacao, matricula FROM solicitacoes_travadas", conn)
        travadas_dict = df_travadas.set_index('solicitacao')['matricula'].to_dict() if not df_travadas.empty else {}
        
        df_regioes = pd.read_sql("SELECT sigla_regiao, matricula_responsavel FROM regioes_responsaveis", conn)
        regioes_dict = df_regioes.set_index('sigla_regiao')['matricula_responsavel'].to_dict() if not df_regioes.empty else {}
        
        def get_responsavel(sol_id, regiao_str):
            sol_id_str = str(sol_id).strip()
            if sol_id_str in travadas_dict:
                return travadas_dict[sol_id_str]
            
            sigla = str(regiao_str).strip()[:2].upper() if pd.notna(regiao_str) else ""
            if sigla in regioes_dict:
                return regioes_dict[sigla]
                
            return "Não Atribuído"

        # Garante a existência da coluna Ref_Regiao em ambos para evitar KeyError
        if 'Ref_Regiao' not in df_antigo.columns:
            df_antigo['Ref_Regiao'] = ''
        if 'Ref_Regiao' not in df_novo.columns:
            df_novo['Ref_Regiao'] = ''
            
        # Normaliza os nomes das colunas de chaves (evita problemas com encode utf8/latin1)
        for df_t in [df_antigo, df_novo]:
            for col in list(df_t.columns):
                col_lower = col.lower()
                if 'solicita' in col_lower and 'vinc' not in col_lower:
                    df_t.rename(columns={col: 'Solicitacao_ID'}, inplace=True)
                elif 'situa' in col_lower:
                    df_t.rename(columns={col: 'Situacao_Norm'}, inplace=True)
        
        antigas_dict = df_antigo.set_index('Solicitacao_ID').to_dict('index')
        novas_dict = df_novo.set_index('Solicitacao_ID').to_dict('index')
        
        eventos_para_inserir = []
        
        # 1. Novas e Iniciadas
        for sol_id, row_nova in novas_dict.items():
            if sol_id not in antigas_dict:
                regiao = row_nova.get('Ref_Regiao', '')
                sigla = str(regiao).strip()[:2].upper() if pd.notna(regiao) else ""
                matricula = get_responsavel(sol_id, regiao)
                eventos_para_inserir.append((sol_id, 'NOVA', sigla, matricula, data_evento_aplicar))
            else:
                row_antiga = antigas_dict[sol_id]
                sit_antiga = str(row_antiga.get('Situacao_Norm', '')).upper()
                sit_nova = str(row_nova.get('Situacao_Norm', '')).upper()
                
                was_elaboracao = 'ELABORA' in sit_antiga
                is_elaboracao = 'ELABORA' in sit_nova
                
                if not was_elaboracao and is_elaboracao:
                    regiao = row_nova.get('Ref_Regiao', '')
                    sigla = str(regiao).strip()[:2].upper() if pd.notna(regiao) else ""
                    matricula = get_responsavel(sol_id, regiao)
                    eventos_para_inserir.append((sol_id, 'INICIADA', sigla, matricula, data_evento_aplicar))
                    
        # 2. Tratadas
        for sol_id, row_antiga in antigas_dict.items():
            if sol_id not in novas_dict:
                regiao = row_antiga.get('Ref_Regiao', '')
                sigla = str(regiao).strip()[:2].upper() if pd.notna(regiao) else ""
                matricula = get_responsavel(sol_id, regiao)
                eventos_para_inserir.append((sol_id, 'TRATADA', sigla, matricula, data_evento_aplicar))
                
        if eventos_para_inserir:
            cursor = conn.cursor()
            
            # Anti-Duplicação: Verifica quais eventos já foram registrados para a data-alvo
            data_dedup = data_evento_aplicar[:10]
            cursor.execute("SELECT solicitacao, tipo_evento FROM eventos_diarios WHERE date(data_evento) = ?", (data_dedup,))
            existentes = set((str(row[0]).strip(), str(row[1]).strip()) for row in cursor.fetchall())
            
            eventos_unicos = []
            for ev in eventos_para_inserir:
                chave = (str(ev[0]).strip(), str(ev[1]).strip())
                if chave not in existentes:
                    eventos_unicos.append(ev)
                    existentes.add(chave) # Adiciona na lista de existentes para não duplicar caso venha duas vezes na mesma lista
            
            if eventos_unicos:
                cursor.executemany('''
                    INSERT INTO eventos_diarios (solicitacao, tipo_evento, regiao, matricula_responsavel, data_evento)
                    VALUES (?, ?, ?, ?, ?)
                ''', eventos_unicos)
                conn.commit()
                print(f"[DB] {len(eventos_unicos)} eventos registrados de produtividade.")
            else:
                print(f"[DB] Nenhum evento novo para registrar (todos já existiam hoje).")
            
    except Exception as e:
        print(f"[DB] Erro ao registrar eventos: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

def get_performance_d1(nome_responsavel, data_inicio=None, data_fim=None):
    """
    Retorna consolidação D-1 para um responsável específico:
    Novas, Tratadas e Pendentes (Aprovada/Em elaboração) por dia.
    """
    import pandas as pd
    import datetime
    
    if data_fim is None:
        data_fim = datetime.date.today().strftime('%Y-%m-%d')
    if data_inicio is None:
        data_inicio = (datetime.date.today() - datetime.timedelta(days=15)).strftime('%Y-%m-%d')
        
    conn_app = get_connection_config()
    conn_data = get_connection_read()
    try:
        cursor = conn_app.cursor()
        cursor.execute("SELECT matricula FROM usuarios WHERE nome = ?", (nome_responsavel,))
        res = cursor.fetchone()
        if not res:
            return pd.DataFrame()
        matricula = res[0]
        
        query_eventos = """
            SELECT 
                date(data_evento) as data,
                tipo_evento,
                COUNT(*) as qtd
            FROM eventos_diarios
            WHERE matricula_responsavel = ?
            AND date(data_evento) BETWEEN ? AND ?
            GROUP BY date(data_evento), tipo_evento
        """
        df_eventos = pd.read_sql(query_eventos, conn_app, params=[matricula, data_inicio, data_fim])
        
        if df_eventos.empty:
            df_perf = pd.DataFrame(columns=['Data', 'Novas', 'Tratadas', 'Pendentes'])
        else:
            df_pivot = df_eventos.pivot(index='data', columns='tipo_evento', values='qtd').fillna(0).reset_index()
            for col in ['NOVA', 'TRATADA', 'INICIADA']:
                if col not in df_pivot.columns:
                    df_pivot[col] = 0
            df_pivot = df_pivot.rename(columns={'data': 'Data', 'NOVA': 'Novas', 'TRATADA': 'Tratadas', 'INICIADA': 'Iniciadas'})
            df_perf = df_pivot[['Data', 'Novas', 'Tratadas', 'Iniciadas']]
            
        # --- PENDENTES: Ler do snapshot persistente (ccp_app.db) ---
        cursor.execute("SELECT data, pendentes_total, pendentes_iniciadas, pendentes_nao_iniciadas FROM pendentes_snapshot WHERE matricula = ? AND data BETWEEN ? AND ? ORDER BY data", (matricula, data_inicio, data_fim))
        rows_pend = cursor.fetchall()
        
        if rows_pend:
            df_pendentes = pd.DataFrame(rows_pend, columns=['Data', 'Pendentes', 'Pendentes_Iniciadas', 'Pendentes_Nao_Iniciadas'])
            
            if not df_perf.empty and not df_pendentes.empty:
                df_perf = pd.merge(df_perf, df_pendentes, on='Data', how='outer').fillna(0)
            elif not df_pendentes.empty:
                df_perf = df_pendentes
                df_perf['Novas'] = 0
                df_perf['Tratadas'] = 0
                df_perf['Iniciadas'] = 0
        else:
            df_perf['Pendentes'] = 0
            df_perf['Pendentes_Iniciadas'] = 0
            df_perf['Pendentes_Nao_Iniciadas'] = 0
                
        if not df_perf.empty:
            df_perf['Novas'] = df_perf.get('Novas', 0).astype(int)
            df_perf['Tratadas'] = df_perf.get('Tratadas', 0).astype(int)
            df_perf['Iniciadas'] = df_perf.get('Iniciadas', 0).astype(int)
            df_perf['Pendentes'] = df_perf.get('Pendentes', 0).astype(int)
            df_perf['Pendentes_Iniciadas'] = df_perf.get('Pendentes_Iniciadas', 0).astype(int)
            df_perf['Pendentes_Nao_Iniciadas'] = df_perf.get('Pendentes_Nao_Iniciadas', 0).astype(int)
            df_perf = df_perf.sort_values('Data')
            
        return df_perf
    except Exception as e:
        print(f"Erro em get_performance_d1: {e}")
        return pd.DataFrame(columns=['Data', 'Novas', 'Tratadas', 'Iniciadas', 'Pendentes', 'Pendentes_Iniciadas', 'Pendentes_Nao_Iniciadas'])
    finally:
        conn_app.close()
