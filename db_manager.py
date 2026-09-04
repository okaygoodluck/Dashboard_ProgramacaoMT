import sqlite3
import datetime
import pandas as pd
import numpy as np
import os
import sys

try:
    import streamlit as st
except ImportError:
    class _DummyCacheData:
        def __call__(self, *args, **kwargs):
            def decorator(f):
                return f
            return decorator
        def clear(self):
            pass

    class _DummySt:
        cache_data = _DummyCacheData()

    st = _DummySt()

try:
    import bcrypt
except ImportError:
    bcrypt = None

FERIADOS_BASE = ["2026-01-01", "2026-04-03", "2026-04-21", "2026-05-01", "2026-06-04", "2026-08-15", "2026-09-07", "2026-10-12", "2026-11-02", "2026-11-15", "2026-11-20", "2026-12-25"]

def get_agora_br():
    """Retorna o horário atual em Brasília (UTC-3)."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(hours=3)

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

_UNC_REDE_ACC = r"\\SACORPARQ1\GROUPS\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programação\Dashboard MT"
_UNC_REDE_NORM = r"\\SACORPARQ1\GROUPS\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programacao\Dashboard MT"
_REDE_ACC = r"I:\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programação\Dashboard MT"
_REDE_NORM = r"I:\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programacao\Dashboard MT"

_ENV_REDE_BASE = os.environ.get("CCP_DASHBOARD_DB_PATH")

_CANDIDATOS_REDE = [
    _ENV_REDE_BASE,
    _UNC_REDE_ACC,
    _UNC_REDE_NORM,
    _REDE_ACC,
    _REDE_NORM,
]

REDE_BASE = None
for cand in _CANDIDATOS_REDE:
    if cand and os.path.exists(cand):
        REDE_BASE = cand
        break

if not REDE_BASE:
    REDE_BASE = _ENV_REDE_BASE or _UNC_REDE_ACC

REDE_APP_PATH = os.path.join(REDE_BASE, DB_APP_NAME)
REDE_DATA_PATH = os.path.join(REDE_BASE, DB_DATA_NAME)

def is_server_mode() -> bool:
    """Verifica se a aplicação está rodando em modo servidor local dedicado."""
    val = os.environ.get("CCP_SERVER_MODE", "").strip().lower()
    return val in ("true", "1", "yes", "sim", "servidor", "server")

def _is_network_path(path: str) -> bool:
    """Verifica se um caminho aponta para um compartilhamento de rede (UNC ou drive mapeado)."""
    if not path:
        return False
    p = path.strip()
    if p.startswith("\\\\") or p.startswith("//"):
        return True
    drive, _ = os.path.splitdrive(p)
    if drive and drive.upper() not in ("C:", "D:"):
        return True
    return False

def _build_sqlite_ro_uri(path: str) -> str:
    """Monta URI segura no modo somente leitura (?mode=ro) compatível com caminhos locais e UNC."""
    p = path.strip()
    if p.startswith("\\\\") or p.startswith("//"):
        clean = p.lstrip("\\/").replace("\\", "/")
        return f"file:////{clean}?mode=ro"
    else:
        clean = p.replace("\\", "/").lstrip("/")
        return f"file:///{clean}?mode=ro"

def _get_path(filename, network_path, alt_env_key=None):
    """
    Lógica de descoberta:
      - Modo Servidor (CCP_SERVER_MODE=true): Ambiente > Local SSD > Rede (Fallback)
      - Modo Cliente / Home Office: Ambiente > Rede Compartilhada > Local Offline (Fallback)
    """
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

    # Se estiver no Servidor Dedicado: prioriza armazenamento local para máxima velocidade
    if is_server_mode():
        local = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        if os.path.exists(local):
            return local

        if filename == DB_DATA_NAME:
            local_demanda = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOCAL_DB_NAME)
            if os.path.exists(local_demanda):
                return local_demanda

        if network_path and os.path.exists(network_path):
            return network_path

        return None

    # Modo Cliente / Home Office:
    # 2. Caminho da Rede (Prioriza rede para sincronizar com a extração do servidor)
    if network_path and os.path.exists(network_path):
        return network_path

    # 3. Pasta atual (Portabilidade / Offline Fallback)
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if os.path.exists(local):
        return local
    
    return None

def get_app_db_path():
    """Retorna o caminho do banco de sistema (prioriza local no servidor, rede no cliente)."""
    p = _get_path(DB_APP_NAME, REDE_APP_PATH)
    return p if p else DB_APP_NAME # Fallback para o nome padrão se nada for encontrado

def get_data_db_path():
    """Retorna o caminho do banco de dados de demanda (prioriza local no servidor, rede no cliente)."""
    # Aceita DEMANDA_DB_PATH que é comumente usado nos .bat
    p = _get_path(DB_DATA_NAME, REDE_DATA_PATH, alt_env_key="DEMANDA_DB_PATH")
    
    # Fallback se não encontrar o oficial, tenta o nome antigo na rede
    if not p and REDE_BASE:
        alt_network = os.path.join(REDE_BASE, "demanda_publica.db")
        if os.path.exists(alt_network):
            return alt_network
            
    return p if p else LOCAL_DB_NAME # Fallback para o local se nada for encontrado

def publicar_db_rede(retries=3, delay_seconds=2):
    """
    Publica os dados da demanda gerados pela extração:
    1. Atualiza a cópia local do servidor (ccp_data.db) para uso do Streamlit local com latência zero.
    2. Publica réplica atômica e resiliente na rede corporativa (UNC / I:) para usuários em Home Office.
    3. Cria backup de segurança do ccp_app.db na rede para prevenir perda do histórico.
    """
    import shutil
    import time
    
    sucesso_local = False
    sucesso_rede = False
    
    src_db = LOCAL_DB_NAME
    if not os.path.exists(src_db):
        src_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOCAL_DB_NAME)
        if not os.path.exists(src_db):
            print(f"[AVISO] Arquivo local '{LOCAL_DB_NAME}' não encontrado para publicar.")
            return False

    base_dir = os.path.dirname(os.path.abspath(__file__))
    local_data_path = os.path.join(base_dir, DB_DATA_NAME)

    # 1. Sincronização Local (servidor local)
    try:
        if os.path.abspath(src_db) != os.path.abspath(local_data_path):
            shutil.copy2(src_db, local_data_path)
            print(f"[OK LOCAL] Base local do servidor atualizada: {local_data_path}")
        sucesso_local = True
    except Exception as e_local:
        print(f"[AVISO LOCAL] Falha ao atualizar cópia local ccp_data.db: {e_local}")

    # 2. Sincronização de Rede (Réplica para Home Office)
    try:
        if REDE_BASE:
            os.makedirs(REDE_BASE, exist_ok=True)
            tmp_rede_path = REDE_DATA_PATH + ".tmp"
            
            for tentativa in range(1, retries + 1):
                try:
                    shutil.copy2(src_db, tmp_rede_path)
                    try:
                        os.replace(tmp_rede_path, REDE_DATA_PATH)
                    except (PermissionError, OSError):
                        shutil.copy2(src_db, REDE_DATA_PATH)
                        if os.path.exists(tmp_rede_path):
                            try:
                                os.remove(tmp_rede_path)
                            except Exception:
                                pass
                                
                    print(f"[OK REDE] Réplica publicada com sucesso na rede: {REDE_DATA_PATH}")
                    sucesso_rede = True
                    break
                except Exception as e_tentativa:
                    print(f"[REDE RETRY] Tentativa {tentativa}/{retries} de publicar na rede falhou: {e_tentativa}")
                    if os.path.exists(tmp_rede_path):
                        try:
                            os.remove(tmp_rede_path)
                        except Exception:
                            pass
                    if tentativa < retries:
                        time.sleep(delay_seconds)
            
            if not sucesso_rede:
                print(f"[AVISO REDE] Não foi possível atualizar a réplica de rede ({REDE_DATA_PATH}) após {retries} tentativas. A base local do servidor continua operacional.")
        else:
            print("[AVISO REDE] Nenhum caminho de rede configurado para replicação.")
    except Exception as e_rede:
        print(f"[ERRO REDE] Falha crítica na publicação de rede: {e_rede}")

    # 3. Backup de segurança do ccp_app.db na rede
    try:
        local_app_db = os.path.join(base_dir, DB_APP_NAME)
        if os.path.exists(local_app_db) and REDE_BASE and os.path.exists(REDE_BASE):
            if is_server_mode():
                backup_rede_app = os.path.join(REDE_BASE, "ccp_app_backup_servidor.db")
                shutil.copy2(local_app_db, backup_rede_app)
                print(f"[BACKUP] Backup de segurança do ccp_app.db salvo na rede: {backup_rede_app}")
    except Exception as e_bkp:
        print(f"[AVISO BACKUP] Falha ao criar backup do ccp_app.db na rede: {e_bkp}")

    return sucesso_local or sucesso_rede

def get_connection_read():
    """Conexão resiliente para leitura de dados de demanda (Prioriza Rede com Fallback Local, ou Local no Servidor)."""
    path = get_data_db_path()
    
    # 1. Se for banco de rede, tenta URI modo leitura-apenas (evita locks de concorrência)
    if path and _is_network_path(path):
        try:
            uri = _build_sqlite_ro_uri(path)
            return sqlite3.connect(uri, uri=True, timeout=15)
        except Exception:
            pass

    # 2. Tenta conexão padrão com o path encontrado
    if path:
        try:
            return sqlite3.connect(path, timeout=15)
        except Exception as e:
            print(f"[DB READ] Falha na conexão de leitura ({e}). Acionando fallback local...")

    # 3. Fallback local absoluto no diretório do projeto
    try:
        local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOCAL_DB_NAME)
        return sqlite3.connect(local_path, timeout=15)
    except Exception as e_local:
        print(f"[CRÍTICO DB READ] Falha no fallback local: {e_local}")
        raise e_local

def get_connection_write():
    """Conexão para escrita (EXTRATOR). Sempre salva no banco local 'demanda.db'."""
    return sqlite3.connect(LOCAL_DB_NAME, timeout=30)

def get_connection_config(*args, **kwargs):
    """
    Conexão resiliente para a base do sistema (ccp_app.db).
    Aceita quaisquer argumentos (posicionais ou nomeados) sem falhar por variação de assinatura.
    Prioriza arquivo de rede com 3 níveis de proteção:
      1. Tenta abrir em modo leitura URI (mode=ro) se for caminho de rede
      2. Tenta conexão padrão com timeout de 30s
      3. Fallback automático para o banco local 'ccp_app.db'
    """
    read_only = kwargs.get('read_only', False)
    if len(args) > 0:
        read_only = bool(args[0])

    path = get_app_db_path()
    
    # 1. Se for leitura e for caminho de rede, tenta primeiro o modo leitura URI (evita lock de arquivo)
    if read_only and path and _is_network_path(path):
        try:
            uri = _build_sqlite_ro_uri(path)
            return sqlite3.connect(uri, uri=True, timeout=15)
        except Exception:
            pass

    # 2. Tenta conexão padrão com o arquivo
    try:
        conn = sqlite3.connect(path, timeout=30)
        try:
            conn.execute("PRAGMA journal_mode = MEMORY")
            conn.execute("PRAGMA synchronous = NORMAL")
        except Exception:
            pass
        return conn
    except Exception as e:
        print(f"[DB] Falha na conexão ccp_app.db na rede ({e}). Acionando fallback local...")
        
    # 3. Fallback absoluto para o banco local no diretório do projeto
    try:
        local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_APP_NAME)
        conn = sqlite3.connect(local_path, timeout=30)
        try:
            conn.execute("PRAGMA journal_mode = MEMORY")
        except Exception:
            pass
        return conn
    except Exception as e_local:
        print(f"[CRÍTICO DB] Falha no fallback local ccp_app.db: {e_local}")
        raise e_local

def get_connection_config_read():
    """Conexão para leitura de sistema (Usuários/Config/Eventos)."""
    return get_connection_config(read_only=True)

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

    # --- AUTO-TRAVAMENTO DE SOLICITAÇÕES EM ELABORAÇÃO (GDIS-PM) ---
    try:
        resp_col = next((c for c in df.columns if 'resp' in c.lower() and 'manobra' in c.lower()), None)
        sit_col = next((c for c in df.columns if 'situa' in c.lower()), None)
        sol_col = next((c for c in df.columns if 'solicita' in c.lower() and 'vinc' not in c.lower()), None)
        
        if resp_col and sit_col and sol_col:
            df_elab = df[df[sit_col].astype(str).str.contains('ELABORA', case=False, na=False)].copy()
            df_elab = df_elab[~df_elab[resp_col].astype(str).str.strip().isin(['', '-', 'None'])]
            if not df_elab.empty:
                novas_travas = df_elab[[sol_col, resp_col]].rename(columns={sol_col: 'Solicitação', resp_col: 'Matricula'})
                travar_solicitacoes(novas_travas)
    except Exception as e_lock:
        print(f"[DB] Aviso ao auto-atualizar travas de manobra: {e_lock}")

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

@st.cache_data(ttl=120)
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

@st.cache_data(ttl=120)
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

def registrar_transicao_regiao(sigla_regiao, matricula_nova, matricula_anterior=None):
    """
    Grava um retrato congelado da região quando ocorre troca de responsabilidade.
    Suporta busca inteligente do responsável anterior (mesmo que desvinculado previamente)
    e registro de assunção inicial a partir de 'Não Atribuído'.
    """
    sigla_clean = str(sigla_regiao).strip().upper()[:2]
    conn = get_connection_config()
    try:
        cursor = conn.cursor()
        
        # 1. Se não foi passado explicitamente, busca responsável anterior
        if matricula_anterior is None:
            cursor.execute("SELECT matricula_responsavel FROM regioes_responsaveis WHERE UPPER(sigla_regiao) = ?", (sigla_clean,))
            res_ant = cursor.fetchone()
            if res_ant and res_ant[0]:
                matricula_anterior = str(res_ant[0]).strip()
            else:
                # Se não estava em regioes_responsaveis (ex: foi desmarcada antes de salvar),
                # busca o último técnico que assumiu essa região no histórico de transições
                cursor.execute("""
                    SELECT matricula_nova, nome_novo 
                    FROM historico_transicao_regioes 
                    WHERE UPPER(sigla_regiao) = ? AND matricula_nova NOT IN ('SEM_RESPONSAVEL', '')
                    ORDER BY id DESC LIMIT 1
                """, (sigla_clean,))
                last_tr = cursor.fetchone()
                if last_tr and last_tr[0] and str(last_tr[0]).strip() != str(matricula_nova).strip():
                    matricula_anterior = str(last_tr[0]).strip()
                else:
                    matricula_anterior = "SEM_RESPONSAVEL"

        # Só ignora se o responsável anterior for exatamente o mesmo que o novo
        if str(matricula_anterior).strip() == str(matricula_nova).strip():
            return # Sem alteração real de responsável entre dois técnicos
            
        # Pega nomes dos usuários
        cursor.execute("SELECT nome FROM usuarios WHERE matricula = ?", (matricula_nova,))
        res_novo_nome = cursor.fetchone()
        nome_novo = res_novo_nome[0] if res_novo_nome else matricula_nova
        
        nome_anterior = "Não Atribuído"
        if matricula_anterior and matricula_anterior != "SEM_RESPONSAVEL":
            cursor.execute("SELECT nome FROM usuarios WHERE matricula = ?", (matricula_anterior,))
            res_ant_nome = cursor.fetchone()
            if res_ant_nome:
                nome_anterior = res_ant_nome[0]
            else:
                nome_anterior = matricula_anterior

        # Calcula passivo atual congelado da região lendo os dados mais recentes
        df = carregar_dados_recentes()
        total_pendentes = 0
        atrasadas = 0
        urgencias = 0
        alertas = 0
        em_elaboracao = 0
        aprovadas_herdadas = 0
        atrasadas_herdadas = 0
        du8_herdadas = 0
        du9_herdadas = 0
        du10_herdadas = 0
        du11_herdadas = 0
        
        if df is not None and not df.empty:
            col_reg = 'Ref_Regiao' if 'Ref_Regiao' in df.columns else df.columns[1]
            df_reg = df[df[col_reg].astype(str).str.strip().str[:2].str.upper() == sigla_clean].copy()
            
            if not df_reg.empty:
                total_pendentes = len(df_reg)
                if 'Status_Prazo' in df_reg.columns:
                    atrasadas = len(df_reg[df_reg['Status_Prazo'] == 'Atrasada'])
                    urgencias = len(df_reg[df_reg['Status_Prazo'] == 'Urgência'])
                    alertas = len(df_reg[df_reg['Status_Prazo'] == 'Alerta de Prazo'])
                if 'Is_Elaboracao' in df_reg.columns:
                    em_elaboracao = len(df_reg[df_reg['Is_Elaboracao'] == True])
                
                # REGRA NEGOCIAL: Solicitações em elaboração pertencem ao técnico que iniciou.
                # O novo técnico herda as solicitações Aprovadas da região.
                if 'Is_Aprovada' in df_reg.columns:
                    df_aprov = df_reg[df_reg['Is_Aprovada'] == True].copy()
                elif 'Is_Elaboracao' in df_reg.columns:
                    df_aprov = df_reg[df_reg['Is_Elaboracao'] != True].copy()
                else:
                    df_aprov = df_reg.copy()
                    
                aprovadas_herdadas = len(df_aprov)
                    
                col_data_inicio = next((c for c in df_aprov.columns if 'início' in c.lower() or 'inicio' in c.lower()), None)
                if col_data_inicio and not df_aprov.empty:
                    try:
                        feriados_np = np.array(FERIADOS_BASE, dtype='datetime64[D]')
                        hoje_dt = datetime.date.today()
                        hoje_util = np.busday_offset(hoje_dt, 0, roll='backward', weekmask='1111100', holidays=feriados_np)
                        
                        def _calc_du(val_d):
                            try:
                                d_obj = pd.to_datetime(val_d, dayfirst=True, errors='coerce')
                                if pd.isna(d_obj): return None
                                d_util = np.busday_offset(d_obj.date(), 0, roll='backward', weekmask='1111100', holidays=feriados_np)
                                return int(np.busday_count(hoje_util, d_util, weekmask='1111100', holidays=feriados_np))
                            except Exception:
                                return None
                                
                        df_aprov['du_calc'] = df_aprov[col_data_inicio].apply(_calc_du)
                        atrasadas_herdadas = len(df_aprov[df_aprov['du_calc'] < 8])
                        du8_herdadas = len(df_aprov[df_aprov['du_calc'] == 8])
                        du9_herdadas = len(df_aprov[df_aprov['du_calc'] == 9])
                        du10_herdadas = len(df_aprov[df_aprov['du_calc'] == 10])
                        du11_herdadas = len(df_aprov[df_aprov['du_calc'] == 11])
                    except Exception as e_du:
                        print(f"[HANDOVER] Aviso ao calcular DU: {e_du}")

        # Insere fotografia no histórico de transição
        cursor.execute('''
            INSERT INTO historico_transicao_regioes (
                sigla_regiao, matricula_anterior, nome_anterior, matricula_nova, nome_novo,
                total_pendentes, atrasadas, urgencias, alertas, em_elaboracao,
                aprovadas_herdadas, atrasadas_herdadas, du8_herdadas, du9_herdadas, du10_herdadas, du11_herdadas
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (sigla_clean, matricula_anterior, nome_anterior, matricula_nova, nome_novo,
              total_pendentes, atrasadas, urgencias, alertas, em_elaboracao,
              aprovadas_herdadas, atrasadas_herdadas, du8_herdadas, du9_herdadas, du10_herdadas, du11_herdadas))
        conn.commit()
        print(f"[HANDOVER] Transição registrada: Região {sigla_clean} ({nome_anterior} -> {nome_novo}) - Pendentes: {total_pendentes}")
    except Exception as e:
        print(f"[HANDOVER ERRO] Falha ao registrar transição de região: {e}")
    finally:
        conn.close()

def deletar_transicao_regiao(id_transicao):
    """Permite apagar uma transição registrada indevidamente."""
    conn = get_connection_config()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM historico_transicao_regioes WHERE id = ?", (id_transicao,))
        conn.commit()
        return True
    except Exception as e:
        print(f"[HANDOVER ERRO] Falha ao apagar transição: {e}")
        return False
    finally:
        conn.close()

def get_historico_transicoes(regiao=None, matricula=None):
    """
    Retorna o histórico de transições de regiões gravado no ccp_app.db.
    """
    import pandas as pd
    conn = get_connection_config()
    try:
        query = "SELECT * FROM historico_transicao_regioes WHERE 1=1"
        params = []
        if regiao and str(regiao).upper() not in ['TODAS', 'GLOBAL', 'TODAS (VISÃO GLOBAL)']:
            sigla = str(regiao).strip().upper()[:2]
            query += " AND UPPER(sigla_regiao) = ?"
            params.append(sigla)
        if matricula:
            query += " AND (matricula_anterior = ? OR matricula_nova = ?)"
            params.extend([matricula, matricula])
            
        query += " ORDER BY id DESC"
        df = pd.read_sql(query, conn, params=params)
        return df
    except Exception as e:
        print(f"[HANDOVER ERRO] Falha ao buscar histórico de transições: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

def atribuir_regioes_massa(matricula_responsavel, lista_siglas):
    """Atribui uma lista de regiões a um único responsável gravando a transição."""
    siglas_novas = set(str(s).strip().upper()[:2] for s in lista_siglas if str(s).strip())
    
    conn = get_connection_config()
    try:
        cursor = conn.cursor()
        
        # Identifica quais regiões já pertenciam a esse técnico
        cursor.execute("SELECT sigla_regiao FROM regioes_responsaveis WHERE matricula_responsavel = ?", (matricula_responsavel,))
        regioes_atuais = set(row[0].strip().upper() for row in cursor.fetchall())
        
        # Apenas regiões que foram ADICIONADAS a este técnico disparam transição
        regioes_adicionadas = siglas_novas - regioes_atuais
        
        # Registra a transição de cada nova região assumida ANTES de atualizar o mapeamento
        for sigla in sorted(list(regioes_adicionadas)):
            try:
                registrar_transicao_regiao(sigla, matricula_responsavel)
            except Exception as e_tr:
                print(f"[HANDOVER] Falha ao registrar transição para região {sigla}: {e_tr}")

        # Atualiza a tabela: remove regiões antigas que foram desmarcadas para este técnico
        cursor.execute("DELETE FROM regioes_responsaveis WHERE matricula_responsavel = ?", (matricula_responsavel,))
        for sigla in sorted(list(siglas_novas)):
            cursor.execute('''
                INSERT INTO regioes_responsaveis (sigla_regiao, matricula_responsavel)
                VALUES (?, ?)
                ON CONFLICT(sigla_regiao) DO UPDATE SET matricula_responsavel=excluded.matricula_responsavel
            ''', (sigla, matricula_responsavel))
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERRO DB] Falha ao atribuir regiões em massa: {e}")
        return False
    finally:
        conn.close()

def deduplicar_historico_eventos():
    """
    Remove duplicatas verdadeiras na tabela eventos_diarios, mantendo apenas 
    a ocorrência mais antiga para o mesmo evento no mesmo dia (solicitacao, tipo_evento, date(data_evento)).
    """
    conn = get_connection_config()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM eventos_diarios
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM eventos_diarios
                GROUP BY solicitacao, tipo_evento, date(data_evento)
            )
        """)
        removidos = cursor.rowcount
        conn.commit()
        if removidos > 0:
            print(f"[DB CLEANUP] {removidos} eventos duplicados de manobras foram limpos da tabela 'eventos_diarios'.")
        return removidos
    except Exception as e:
        print(f"[DB CLEANUP] Erro ao deduplicar histórico de eventos: {e}")
        return 0
    finally:
        conn.close()

def sanitizar_eventos_tratadas_ativas():
    """
    Remove registros indevidos de 'TRATADA' para solicitações que continuam
    ativas e presentes em 'demanda_atual'. Isso desbloqueia as solicitações
    para que os técnicos recebam o devido crédito quando forem efetivamente finalizadas.
    """
    conn_app = get_connection_config()
    conn_data = get_connection_read()
    try:
        df_cur = pd.read_sql("SELECT * FROM demanda_atual", conn_data)
        if df_cur.empty:
            return 0
        sol_col = next((c for c in df_cur.columns if 'solicita' in c.lower() and 'vinc' not in c.lower()), None)
        if not sol_col:
            return 0
        sols_ativas = [str(s).strip() for s in df_cur[sol_col].dropna().unique()]
        sols_ativas_sem_zero = [s.lstrip('0') for s in sols_ativas]
        todas_ativas = list(set(sols_ativas + sols_ativas_sem_zero))
        
        cursor = conn_app.cursor()
        removidos_total = 0
        for i in range(0, len(todas_ativas), 500):
            chunk = todas_ativas[i:i+500]
            placeholders = ','.join(['?'] * len(chunk))
            cursor.execute(f"""
                DELETE FROM eventos_diarios 
                WHERE tipo_evento = 'TRATADA' 
                AND (solicitacao IN ({placeholders}) OR LTRIM(solicitacao, '0') IN ({placeholders}))
            """, chunk + chunk)
            removidos_total += cursor.rowcount
            
        conn_app.commit()
        if removidos_total > 0:
            print(f"[SANITY] {removidos_total} registros falsos-positivos de 'TRATADA' foram removidos (solicitações ainda ativas na fila).")
        return removidos_total
    except Exception as e:
        print(f"[SANITY ERRO] Falha ao sanitizar tratadas ativas: {e}")
        return 0
    finally:
        conn_app.close()
        conn_data.close()

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

        # 8. Tabela de Histórico de Transição de Regiões (Handover Snapshot)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS historico_transicao_regioes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sigla_regiao TEXT NOT NULL,
                matricula_anterior TEXT,
                nome_anterior TEXT,
                matricula_nova TEXT NOT NULL,
                nome_novo TEXT NOT NULL,
                data_transicao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_pendentes INTEGER DEFAULT 0,
                atrasadas INTEGER DEFAULT 0,
                urgencias INTEGER DEFAULT 0,
                alertas INTEGER DEFAULT 0,
                em_elaboracao INTEGER DEFAULT 0,
                aprovadas_herdadas INTEGER DEFAULT 0,
                atrasadas_herdadas INTEGER DEFAULT 0,
                du8_herdadas INTEGER DEFAULT 0,
                du9_herdadas INTEGER DEFAULT 0,
                du10_herdadas INTEGER DEFAULT 0,
                du11_herdadas INTEGER DEFAULT 0
            )
        ''')

        # Migração automática de schema para bancos pré-existentes
        for col_n in ['aprovadas_herdadas', 'atrasadas_herdadas', 'du8_herdadas', 'du9_herdadas', 'du10_herdadas', 'du11_herdadas']:
            try:
                conn.execute(f"ALTER TABLE historico_transicao_regioes ADD COLUMN {col_n} INTEGER DEFAULT 0")
            except Exception:
                pass

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
        # 9. Auto-recomposição do histórico de pendentes se a tabela estiver vazia
        cursor.execute("SELECT COUNT(*) FROM pendentes_snapshot")
        if cursor.fetchone()[0] == 0:
            print("[INIT] Tabela 'pendentes_snapshot' vazia. Recompondo histórico inicial de pendentes...")
        # 10. Auto-deduplicação do histórico de eventos diários
        deduplicar_historico_eventos()
        # 11. Sanitização de registros indevidos de TRATADA para solicitações que continuam ativas
        sanitizar_eventos_tratadas_ativas()
            
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

def destravar_solicitacoes(lista_solicitacoes):
    """Remove travas no banco para solicitações que não estão mais Em Elaboração.
    """
    if not lista_solicitacoes:
        return False
        
    conn = get_connection_config()
    try:
        cursor = conn.cursor()
        placeholders = ','.join(['?'] * len(lista_solicitacoes))
        query = f"DELETE FROM solicitacoes_travadas WHERE solicitacao IN ({placeholders})"
        cursor.execute(query, lista_solicitacoes)
        conn.commit()
        return True
    except Exception as e:
        print(f"[DB] Erro ao destravar solicitacoes: {e}")
        return False
    finally:
        conn.close()

def registrar_snapshot_pendentes(df_atual):
    """Calcula e grava o snapshot de pendentes do dia para cada usuário com base nas regiões atribuídas e travadas."""
    if df_atual is None or df_atual.empty:
        return

    conn = None
    try:
        conn = get_connection_config()
        cursor = conn.cursor()
        data_hoje = get_agora_br().strftime('%Y-%m-%d')
        
        # Obter todos os usuários com regiões ou travadas
        cursor.execute("SELECT DISTINCT matricula_responsavel FROM regioes_responsaveis WHERE matricula_responsavel IS NOT NULL")
        users_regioes = set(row[0] for row in cursor.fetchall() if row[0])
        
        cursor.execute("SELECT DISTINCT matricula FROM solicitacoes_travadas WHERE matricula IS NOT NULL")
        users_travadas = set(row[0] for row in cursor.fetchall() if row[0])
        
        todos_usuarios = users_regioes.union(users_travadas)
        if not todos_usuarios:
            return
        
        df_pend = df_atual.copy()
        
        # Coalesce e normaliza a coluna de Situação
        sit_cols = [c for c in df_pend.columns if 'situa' in c.lower()]
        sit_series = pd.Series('', index=df_pend.index)
        for c in sit_cols:
            v = df_pend[c].fillna('').astype(str).str.strip().str.upper()
            mask = (sit_series == '') & (~v.isin(['NONE', '', 'NAN']))
            sit_series.loc[mask] = v.loc[mask]
        df_pend['Situacao_Clean'] = sit_series
        
        # Coalesce e normaliza a coluna de Solicitação ID
        sol_cols = [c for c in df_pend.columns if 'solicita' in c.lower() and 'vinc' not in c.lower()]
        sol_series = pd.Series('', index=df_pend.index)
        for c in sol_cols:
            v = df_pend[c].fillna('').astype(str).str.strip().str.lstrip('0')
            mask = (sol_series == '') & (~v.isin(['NONE', '', 'NAN']))
            sol_series.loc[mask] = v.loc[mask]
        df_pend['Solicitacao_Clean'] = sol_series

        resp_cols = [c for c in df_pend.columns if 'resp' in c.lower()]
        resp_col = resp_cols[0] if resp_cols else df_pend.columns[2]
        df_pend['Resp_Clean'] = df_pend[resp_col].astype(str).str.strip()

        reg_col = 'Ref_Regiao' if 'Ref_Regiao' in df_pend.columns else df_pend.columns[1]
        df_pend['Regiao_Sigla'] = df_pend[reg_col].astype(str).str.strip().str[:2].str.upper()

        # Filtra apenas demandas que contam como pendentes
        df_pendentes = df_pend[df_pend['Situacao_Clean'].isin(['APROVADA', 'EM ELABORAÇÃO', 'EM ELABORACAO'])].copy()
        
        for matricula in todos_usuarios:
            cursor.execute("SELECT solicitacao FROM solicitacoes_travadas WHERE matricula = ?", (matricula,))
            travadas = [str(row[0]).strip().lstrip('0') for row in cursor.fetchall() if str(row[0]).strip() and str(row[0]).strip() not in ['None', 'nan', '0']]
            
            mask = (df_pendentes['Resp_Clean'] == matricula)
            if travadas:
                mask = mask | ((df_pendentes['Solicitacao_Clean'] != '') & (df_pendentes['Solicitacao_Clean'] != 'None') & df_pendentes['Solicitacao_Clean'].isin(travadas))
                
            df_user = df_pendentes[mask]
            
            total = len(df_user)
            iniciadas = len(df_user[df_user['Situacao_Clean'].str.contains('ELABORA', na=False)])
            nao_iniciadas = len(df_user[df_user['Situacao_Clean'] == 'APROVADA'])
            
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
        if conn is not None:
            conn.close()

def recompor_snapshot_historico():
    """
    Recompõe e backfila o histórico de pendentes_snapshot lendo a tabela demanda_historico
    para todas as datas disponíveis.
    """
    conn_data = None
    conn_app = None
    try:
        conn_data = get_connection_read()
        cursor_data = conn_data.cursor()
        
        # Verifica se demanda_historico existe
        cursor_data.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='demanda_historico';")
        if not cursor_data.fetchone():
            conn_data.close()
            return

        df_hist = pd.read_sql("SELECT * FROM demanda_historico", conn_data)
        conn_data.close()

        if df_hist.empty:
            return

        df_hist['Data_Ref'] = pd.to_datetime(df_hist['Data_Extracao']).dt.strftime('%Y-%m-%d')
        datas = sorted(df_hist['Data_Ref'].unique())

        conn_app = get_connection_config(read_only=False)
        cursor_app = conn_app.cursor()

        cursor_app.execute("SELECT DISTINCT matricula FROM usuarios WHERE matricula IS NOT NULL")
        users_app = set(row[0] for row in cursor_app.fetchall() if row[0])
        
        resp_cols_all = [c for c in df_hist.columns if 'resp' in c.lower()]
        resp_col_all = resp_cols_all[0] if resp_cols_all else df_hist.columns[2]
        users_hist = set(df_hist[resp_col_all].dropna().astype(str).str.strip().unique())
        
        todos_usuarios = users_app.union(users_hist) - {'', 'None', 'nan', '-'}

        if not todos_usuarios:
            conn_app.close()
            return

        # Pre-carrega todas as travas em memória para evitar queries repetidas dentro do loop
        cursor_app.execute("SELECT matricula, solicitacao FROM solicitacoes_travadas WHERE matricula IS NOT NULL")
        travadas_map = {}
        for row_mat, row_sol in cursor_app.fetchall():
            mat_clean = str(row_mat).strip()
            sol_clean = str(row_sol).strip().lstrip('0')
            if sol_clean and sol_clean not in ['None', 'nan', '0']:
                travadas_map.setdefault(mat_clean, set()).add(sol_clean)

        rows_to_insert = []

        for d in datas:
            df_day_all = df_hist[df_hist['Data_Ref'] == d]
            max_dt = df_day_all['Data_Extracao'].max()
            df_day = df_day_all[df_day_all['Data_Extracao'] == max_dt].copy()

            resp_cols = [c for c in df_day.columns if 'resp' in c.lower()]
            resp_col = resp_cols[0] if resp_cols else df_day.columns[2]
            df_day['Resp_Clean'] = df_day[resp_col].astype(str).str.strip()

            sit_cols = [c for c in df_day.columns if 'situa' in c.lower()]
            sit_series = pd.Series('', index=df_day.index)
            for c in sit_cols:
                v = df_day[c].fillna('').astype(str).str.strip().str.upper()
                mask = (sit_series == '') & (~v.isin(['NONE', '', 'NAN']))
                sit_series.loc[mask] = v.loc[mask]
            df_day['Situacao_Clean'] = sit_series

            sol_cols = [c for c in df_day.columns if 'solicita' in c.lower() and 'vinc' not in c.lower()]
            sol_series = pd.Series('', index=df_day.index)
            for c in sol_cols:
                v = df_day[c].fillna('').astype(str).str.strip().str.lstrip('0')
                mask = (sol_series == '') & (~v.isin(['NONE', '', 'NAN']))
                sol_series.loc[mask] = v.loc[mask]
            df_day['Solicitacao_Clean'] = sol_series

            reg_col = 'Ref_Regiao' if 'Ref_Regiao' in df_day.columns else df_day.columns[1]
            df_day['Regiao_Sigla'] = df_day[reg_col].astype(str).str.strip().str[:2].str.upper()

            df_pendentes = df_day[df_day['Situacao_Clean'].isin(['APROVADA', 'EM ELABORAÇÃO', 'EM ELABORACAO'])].copy()

            for matricula in todos_usuarios:
                travadas = travadas_map.get(matricula, set())

                mask = (df_pendentes['Resp_Clean'] == matricula)
                if travadas:
                    mask = mask | ((df_pendentes['Solicitacao_Clean'] != '') & (df_pendentes['Solicitacao_Clean'] != 'None') & df_pendentes['Solicitacao_Clean'].isin(travadas))

                df_user = df_pendentes[mask]
                total = len(df_user)
                iniciadas = len(df_user[df_user['Situacao_Clean'].str.contains('ELABORA', na=False)])
                nao_iniciadas = len(df_user[df_user['Situacao_Clean'] == 'APROVADA'])

                rows_to_insert.append((d, matricula, total, iniciadas, nao_iniciadas))

        if rows_to_insert:
            cursor_app.executemany("""
                INSERT INTO pendentes_snapshot (data, matricula, pendentes_total, pendentes_iniciadas, pendentes_nao_iniciadas)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(data, matricula) DO UPDATE SET
                    pendentes_total=excluded.pendentes_total,
                    pendentes_iniciadas=excluded.pendentes_iniciadas,
                    pendentes_nao_iniciadas=excluded.pendentes_nao_iniciadas
            """, rows_to_insert)
            conn_app.commit()
            print(f"[DB] Snapshots de pendentes recompostos com sucesso: {len(rows_to_insert)} registros de {len(datas)} datas.")

    except Exception as e:
        print(f"[DB] Erro ao recompor histórico de pendentes: {e}")
    finally:
        if conn_app:
            conn_app.close()

# Inicializa o banco de dados completo ao carregar o módulo
init_database()

def registrar_eventos_diarios(df_antigo, df_novo):
    """
    Compara o df_antigo com o df_novo para registrar eventos de produtividade
    no banco de dados (NOVA, INICIADA, TRATADA).
    Ignora a primeira execução do dia para não herdar tratadas da madrugada.
    """
    conn = None
    try:
        conn = get_connection_config()
        cursor = conn.cursor()
        data_evento_aplicar = get_agora_br().strftime('%Y-%m-%d %H:%M:%S')
        
        # --- BLOQUEIO TEMPORÁRIO (DADO SUJO) ---
        # Ignora gravações históricas até amanhã, para iniciar do zero.
        if get_agora_br().strftime('%Y-%m-%d') < '2026-07-11':
            return
            
        if df_antigo is None or df_antigo.empty:
            df_antigo = pd.DataFrame(columns=['Solicitação', 'Ref_Regiao', 'Situação'])
            
        if df_novo is None or df_novo.empty:
            return
            
        # Protege as tabelas originais na memória
        df_antigo_copy = df_antigo.copy()
        df_novo_copy = df_novo.copy()
            
        # Carrega dicionarios
        df_travadas = pd.read_sql("SELECT solicitacao, matricula FROM solicitacoes_travadas", conn)
        travadas_dict = df_travadas.set_index('solicitacao')['matricula'].to_dict() if not df_travadas.empty else {}
        
        df_regioes = pd.read_sql("SELECT sigla_regiao, matricula_responsavel FROM regioes_responsaveis", conn)
        regioes_dict = df_regioes.set_index('sigla_regiao')['matricula_responsavel'].to_dict() if not df_regioes.empty else {}
        
        def get_responsavel(sol_id, regiao_str, row_dict=None):
            # Prioridade 1: Resp. Manobra do registro extraído do GDIS-PM
            if row_dict:
                for k, v in row_dict.items():
                    if 'resp' in k.lower() and 'manobra' in k.lower() and pd.notna(v):
                        v_str = str(v).strip()
                        if v_str and v_str != '-' and len(v_str) >= 4 and not v_str.upper().startswith('NÃO'):
                            return v_str
            
            # Prioridade 2: Solicitacao travada no banco
            sol_id_str = str(sol_id).strip()
            sol_id_norm = sol_id_str.lstrip('0')
            if sol_id_str in travadas_dict:
                return travadas_dict[sol_id_str]
            if sol_id_norm in travadas_dict:
                return travadas_dict[sol_id_norm]
            
            # Prioridade 3: Dono fixo da região
            sigla = str(regiao_str).strip()[:2].upper() if pd.notna(regiao_str) else ""
            if sigla in regioes_dict:
                return regioes_dict[sigla]
                
            return "Não Atribuído"

        # Garante a existência da coluna Ref_Regiao em ambos para evitar KeyError
        if 'Ref_Regiao' not in df_antigo_copy.columns:
            df_antigo_copy['Ref_Regiao'] = ''
        if 'Ref_Regiao' not in df_novo_copy.columns:
            df_novo_copy['Ref_Regiao'] = ''
            
        # Normaliza os nomes das colunas de chaves (evita problemas com encode utf8/latin1)
        for df_t in [df_antigo_copy, df_novo_copy]:
            for col in list(df_t.columns):
                col_lower = col.lower()
                if 'solicita' in col_lower and 'vinc' not in col_lower:
                    df_t.rename(columns={col: 'Solicitacao_ID'}, inplace=True)
                elif 'situa' in col_lower:
                    df_t.rename(columns={col: 'Situacao_Norm'}, inplace=True)
            if 'Solicitacao_ID' in df_t.columns:
                df_t['Solicitacao_ID'] = df_t['Solicitacao_ID'].astype(str).str.strip().str.lstrip('0')
        
        antigas_dict = df_antigo_copy.set_index('Solicitacao_ID').to_dict('index') if 'Solicitacao_ID' in df_antigo_copy.columns else {}
        novas_dict = df_novo_copy.set_index('Solicitacao_ID').to_dict('index') if 'Solicitacao_ID' in df_novo_copy.columns else {}
        
        eventos_para_inserir = []
        
        # 1. Novas e Iniciadas
        for sol_id, row_nova in novas_dict.items():
            if sol_id not in antigas_dict:
                regiao = row_nova.get('Ref_Regiao', '')
                sigla = str(regiao).strip()[:2].upper() if pd.notna(regiao) else ""
                matricula = get_responsavel(sol_id, regiao, row_nova)
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
                    matricula = get_responsavel(sol_id, regiao, row_nova)
                    eventos_para_inserir.append((sol_id, 'INICIADA', sigla, matricula, data_evento_aplicar))
                    
        # 2. Tratadas (com barreira de segurança contra quedas anormais de extração)
        if len(antigas_dict) > 50 and len(novas_dict) < 0.6 * len(antigas_dict):
            print(f"[EVENTOS ALERTA] Queda massiva anormal na extração ({len(antigas_dict)} -> {len(novas_dict)}). Abortando registro de tratadas por segurança.")
        else:
            for sol_id, row_antiga in antigas_dict.items():
                if sol_id not in novas_dict:
                    regiao = row_antiga.get('Ref_Regiao', '')
                    sigla = str(regiao).strip()[:2].upper() if pd.notna(regiao) else ""
                    matricula = get_responsavel(sol_id, regiao, row_antiga)
                    eventos_para_inserir.append((sol_id, 'TRATADA', sigla, matricula, data_evento_aplicar))
                
        if eventos_para_inserir:
            cursor = conn.cursor()
            hoje_str = get_agora_br().strftime('%Y-%m-%d')
            
            # Anti-duplicação diária: evita reinserir o mesmo evento no mesmo dia (últimas 24h)
            cursor.execute("""
                SELECT solicitacao, tipo_evento 
                FROM eventos_diarios 
                WHERE date(data_evento) >= date(?, '-1 day')
            """, (hoje_str,))
            existentes_recentes = set((str(row[0]).strip().lstrip('0'), str(row[1]).strip()) for row in cursor.fetchall())
            
            eventos_unicos = []
            for ev in eventos_para_inserir:
                chave = (str(ev[0]).strip().lstrip('0'), str(ev[1]).strip())
                if chave not in existentes_recentes:
                    eventos_unicos.append(ev)
                    existentes_recentes.add(chave) # Adiciona para evitar duplicatas dentro do próprio lote
            
            if eventos_unicos:
                cursor.executemany('''
                    INSERT INTO eventos_diarios (solicitacao, tipo_evento, regiao, matricula_responsavel, data_evento)
                    VALUES (?, ?, ?, ?, ?)
                ''', eventos_unicos)
                conn.commit()
                print(f"[DB] {len(eventos_unicos)} eventos únicos registrados de produtividade.")
            else:
                print(f"[DB] Nenhum evento novo para registrar (já contabilizados no ciclo atual).")
            
    except Exception as e:
        print(f"[DB] Erro ao registrar eventos: {e}")
    finally:
        if conn:
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

        # Garante linha contínua para todas as datas do período (com ffill para o estoque de Pendências/Em Elaboração no FDS)
        try:
            all_dates = pd.date_range(start=data_inicio, end=data_fim, freq='D').strftime('%Y-%m-%d')
            df_full = pd.DataFrame({'Data': all_dates})
            
            if not df_perf.empty:
                df_perf = pd.merge(df_full, df_perf, on='Data', how='left')
            else:
                df_perf = df_full
                df_perf['Novas'] = 0
                df_perf['Tratadas'] = 0
                df_perf['Iniciadas'] = 0
                df_perf['Pendentes'] = 0
                df_perf['Pendentes_Iniciadas'] = 0
                df_perf['Pendentes_Nao_Iniciadas'] = 0

            df_perf['Novas'] = df_perf['Novas'].fillna(0).astype(int)
            df_perf['Tratadas'] = df_perf['Tratadas'].fillna(0).astype(int)
            df_perf['Iniciadas'] = df_perf['Iniciadas'].fillna(0).astype(int)
            
            # Estoque de pendências (Em Elaboração) propaga o valor do dia útil anterior (ffill) se não houver trabalho no FDS
            df_perf['Pendentes_Iniciadas'] = df_perf['Pendentes_Iniciadas'].replace(0, np.nan).ffill().fillna(0).astype(int)
            df_perf['Pendentes'] = df_perf['Pendentes'].replace(0, np.nan).ffill().fillna(0).astype(int)
            df_perf['Pendentes_Nao_Iniciadas'] = df_perf['Pendentes_Nao_Iniciadas'].replace(0, np.nan).ffill().fillna(0).astype(int)
            df_perf = df_perf.sort_values('Data')
        except Exception:
            pass
            
        return df_perf
    except Exception as e:
        print(f"Erro em get_performance_d1: {e}")
        return pd.DataFrame(columns=['Data', 'Novas', 'Tratadas', 'Iniciadas', 'Pendentes', 'Pendentes_Iniciadas', 'Pendentes_Nao_Iniciadas'])
    finally:
        if 'conn_app' in locals() and conn_app:
            try:
                conn_app.close()
            except Exception:
                pass
        if 'conn_data' in locals() and conn_data:
            try:
                conn_data.close()
            except Exception:
                pass

def get_lista_regioes_eventos():
    """Retorna lista ordenada de todas as regiões presentes em eventos_diarios e demanda_atual."""
    conn_app = get_connection_config()
    regioes = set()
    try:
        cursor = conn_app.cursor()
        try:
            cursor.execute("SELECT DISTINCT regiao FROM eventos_diarios WHERE regiao IS NOT NULL AND regiao != ''")
            for row in cursor.fetchall():
                if row[0] and str(row[0]).strip():
                    regioes.add(str(row[0]).strip().upper())
        except Exception:
            pass
    except Exception as e:
        print(f"Erro em get_lista_regioes_eventos: {e}")
    finally:
        if 'conn_app' in locals() and conn_app:
            try: conn_app.close()
            except Exception: pass
            
    # Complementa com regiões disponíveis dos dados gerais
    try:
        reg_data = get_regioes_disponiveis_data()
        regioes.update(reg_data)
    except Exception:
        pass
        
    return sorted(list(regioes - {'', 'NONE', 'NAN', '-'}))

@st.cache_data(ttl=120)
def get_fluxo_diario_novas_tratadas(data_inicio=None, data_fim=None, regiao=None, responsavel=None):
    """
    Retorna consolidação diária global ou por região/responsável de solicitações Novas e Tratadas.
    """
    import pandas as pd
    import datetime
    
    if data_fim is None:
        data_fim = datetime.date.today().strftime('%Y-%m-%d')
    if data_inicio is None:
        data_inicio = (datetime.date.today() - datetime.timedelta(days=15)).strftime('%Y-%m-%d')
        
    conn_app = get_connection_config()
    try:
        query = """
            SELECT 
                date(e.data_evento) as data,
                e.tipo_evento,
                COUNT(*) as qtd
            FROM eventos_diarios e
            LEFT JOIN usuarios u ON e.matricula_responsavel = u.matricula
            WHERE date(e.data_evento) BETWEEN ? AND ?
            AND e.tipo_evento IN ('NOVA', 'TRATADA')
        """
        params = [data_inicio, data_fim]
        
        if regiao and str(regiao).upper() not in ['TODAS', 'GLOBAL', 'TODAS (VISÃO GLOBAL)', 'TODAS (VISAO GLOBAL)']:
            reg_clean = str(regiao).strip().upper()
            sigla = reg_clean[:2]
            query += " AND (UPPER(e.regiao) = ? OR UPPER(substr(e.regiao, 1, 2)) = ?)"
            params.extend([reg_clean, sigla])
            
        if responsavel and str(responsavel).upper() not in ['TODOS', 'GLOBAL', 'TODOS (VISÃO GLOBAL)', 'TODOS (VISAO GLOBAL)']:
            resp_clean = str(responsavel).strip().upper()
            query += " AND UPPER(u.nome) = ?"
            params.append(resp_clean)
            
        query += " GROUP BY date(e.data_evento), e.tipo_evento"
        
        df_ev = pd.read_sql(query, conn_app, params=params)
        
        if df_ev.empty:
            return pd.DataFrame(columns=['Data', 'Novas', 'Tratadas'])
            
        df_pivot = df_ev.pivot(index='data', columns='tipo_evento', values='qtd').fillna(0).reset_index()
        for col in ['NOVA', 'TRATADA']:
            if col not in df_pivot.columns:
                df_pivot[col] = 0
                
        df_pivot = df_pivot.rename(columns={'data': 'Data', 'NOVA': 'Novas', 'TRATADA': 'Tratadas'})
        df_pivot['Novas'] = df_pivot['Novas'].astype(int)
        df_pivot['Tratadas'] = df_pivot['Tratadas'].astype(int)
        df_pivot = df_pivot.sort_values('Data')
        
        return df_pivot
    except Exception as e:
        print(f"Erro em get_fluxo_diario_novas_tratadas: {e}")
        return pd.DataFrame(columns=['Data', 'Novas', 'Tratadas'])
    finally:
        if 'conn_app' in locals() and conn_app:
            try: conn_app.close()
            except Exception: pass

@st.cache_data(ttl=120)
def get_rank_saldo_regioes(data_inicio=None, data_fim=None, responsavel=None):
    """
    Retorna o ranking de regiões por Saldo do Período (Novas - Tratadas),
    ordenado do maior saldo positivo (pior acúmulo de passivo) para o menor.
    """
    import pandas as pd
    import datetime
    
    if data_fim is None:
        data_fim = datetime.date.today().strftime('%Y-%m-%d')
    if data_inicio is None:
        data_inicio = (datetime.date.today() - datetime.timedelta(days=15)).strftime('%Y-%m-%d')
        
    conn_app = get_connection_config()
    try:
        query = """
            SELECT 
                UPPER(TRIM(e.regiao)) as Regiao,
                SUM(CASE WHEN e.tipo_evento = 'NOVA' THEN 1 ELSE 0 END) as Novas,
                SUM(CASE WHEN e.tipo_evento = 'TRATADA' THEN 1 ELSE 0 END) as Tratadas,
                (SUM(CASE WHEN e.tipo_evento = 'NOVA' THEN 1 ELSE 0 END) - SUM(CASE WHEN e.tipo_evento = 'TRATADA' THEN 1 ELSE 0 END)) as Saldo
            FROM eventos_diarios e
            LEFT JOIN usuarios u ON e.matricula_responsavel = u.matricula
            WHERE date(e.data_evento) BETWEEN ? AND ?
              AND e.regiao IS NOT NULL AND TRIM(e.regiao) != ''
        """
        params = [data_inicio, data_fim]
        
        if responsavel and str(responsavel).upper() not in ['TODOS', 'GLOBAL', 'TODOS (VISÃO GLOBAL)', 'TODOS (VISAO GLOBAL)']:
            resp_clean = str(responsavel).strip().upper()
            query += " AND UPPER(u.nome) = ?"
            params.append(resp_clean)
            
        query += """
            GROUP BY UPPER(TRIM(e.regiao))
            ORDER BY Saldo DESC, Novas DESC
        """
        df_rank = pd.read_sql(query, conn_app, params=params)
        return df_rank
    except Exception as e:
        print(f"Erro em get_rank_saldo_regioes: {e}")
        return pd.DataFrame(columns=['Regiao', 'Novas', 'Tratadas', 'Saldo'])
    finally:
        if 'conn_app' in locals() and conn_app is not None:
            try:
                conn_app.close()
            except Exception:
                pass

def limpar_cache_dados():
    """Limpa o cache do Streamlit para forçar a re-leitura de dados novos."""
    try:
        if hasattr(st, "cache_data") and hasattr(st.cache_data, "clear"):
            st.cache_data.clear()
            print("[DB] Cache de dados limpo com sucesso.")
    except Exception as e:
        print(f"[DB] Erro ao limpar cache: {e}")


