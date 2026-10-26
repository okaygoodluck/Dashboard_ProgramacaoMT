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

def obter_dia_util_anterior(data_str) -> str:
    """Retorna o dia útil imediatamente anterior (YYYY-MM-DD), desconsiderando fins de semana e feriados."""
    try:
        import numpy as np
        import pandas as pd
        feriados_np = np.array(FERIADOS_BASE, dtype='datetime64[D]')
        dt = pd.to_datetime(data_str).date()
        ontem_util = np.busday_offset(dt, -1, roll='backward', weekmask='1111100', holidays=feriados_np)
        return str(ontem_util)
    except Exception:
        import datetime
        dt = datetime.datetime.strptime(str(data_str)[:10], '%Y-%m-%d').date()
        delta = 3 if dt.weekday() == 0 else 1
        return str(dt - datetime.timedelta(days=delta))

# Nomes dos arquivos de banco de dados (Oficiais: CCP - Centro de Controle da Programação)
DB_APP_NAME = "ccp_app.db"    # Persistente (Usuários, Configs)
DB_DATA_NAME = "ccp_data.db"  # Volátil (Dados da Demanda)
LOCAL_DB_NAME = os.environ.get("CCP_LOCAL_DB_PATH", "demanda.db")  # Temporário Local para o Extrator

# Matrículas de emissores de avisos (assumem apenas para emitir aviso, crédito permanece com quem iniciou)
MATRICULAS_AVISO = {'e263445', 'e204855'}

def normalizar_matricula(mat) -> str:
    """
    Normaliza matrículas da Cemig:
    - Converte para minúsculas e remove espaços
    - Fallback inteligente para matrículas sem zero à esquerda (ex: c58106 -> c058106)
    """
    if not mat or not isinstance(mat, str):
        return ""
    m = mat.strip()
    if not m:
        return ""
    prefix = m[0].lower()
    rest = m[1:]
    if prefix in ('c', 'e') and rest.isdigit():
        if len(rest) == 5:
            return f"{prefix}0{rest}"
        return f"{prefix}{rest}"
    return m

# Caminhos Mestres na Rede
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass # Permite rodar sem a biblioteca python-dotenv, caso não esteja instalada ainda

_UNC_FQDN_ACC = r"\\SACORPARQ1.cemig.ad.corp\GROUPS\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programação\Dashboard MT"
_UNC_FQDN_NORM = r"\\SACORPARQ1.cemig.ad.corp\GROUPS\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programacao\Dashboard MT"
_UNC_REDE_ACC = r"\\SACORPARQ1\GROUPS\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programação\Dashboard MT"
_UNC_REDE_NORM = r"\\SACORPARQ1\GROUPS\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programacao\Dashboard MT"
_REDE_ACC = r"I:\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programação\Dashboard MT"
_REDE_NORM = r"I:\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programacao\Dashboard MT"

_ENV_REDE_BASE = os.environ.get("CCP_DASHBOARD_DB_PATH")

_CANDIDATOS_REDE = [
    _ENV_REDE_BASE,
    _UNC_FQDN_ACC,
    _UNC_FQDN_NORM,
    _UNC_REDE_ACC,
    _UNC_REDE_NORM,
    _REDE_ACC,
    _REDE_NORM,
]

REDE_BASE = None
if os.environ.get("CCP_MODO_TESTE") == "1" or os.environ.get("CCP_FORCAR_LOCAL") == "1":
    REDE_BASE = _ENV_REDE_BASE or "."
else:
    for cand in _CANDIDATOS_REDE:
        if cand and os.path.exists(cand):
            REDE_BASE = cand
            break

if not REDE_BASE:
    REDE_BASE = _ENV_REDE_BASE or _UNC_FQDN_ACC

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
    # 0. Modo de Teste Isolado / Forçar Local: Prioridade Máxima
    if os.environ.get("CCP_MODO_TESTE") == "1" or os.environ.get("CCP_FORCAR_LOCAL") == "1":
        local = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        if os.path.exists(local):
            return local

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
            # Proteção contra desatualização: se a rede possuir versão mais recente de ccp_app.db, sincroniza automaticamente
            if filename == DB_APP_NAME and network_path and os.path.exists(network_path):
                try:
                    if os.path.getmtime(network_path) > os.path.getmtime(local) + 30:
                        import shutil
                        shutil.copy2(network_path, local)
                        print(f"[SYNC AUTO] Cópia local de {filename} atualizada a partir da rede.")
                except Exception as e_sync:
                    pass
                return local

            # Para dados de demanda (ccp_data.db): se a base da rede for mais recente que o SSD local (extração em outro PC), usa a rede
            if filename == DB_DATA_NAME and network_path and os.path.exists(network_path):
                try:
                    if os.path.getmtime(network_path) > os.path.getmtime(local) + 300:
                        return network_path
                except Exception:
                    pass
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

def get_db_status() -> dict:
    """
    Retorna o diagnóstico da base de dados ativa:
    - is_network: True se os dados de demanda estão sendo lidos da rede corporativa (UNC ou drive mapeado)
    - data_path: caminho absoluto do banco de dados de demanda em uso
    - app_path: caminho absoluto do banco de configurações/usuários
    - rede_base: pasta base de rede identificada ou configurada
    - is_server: True se a aplicação está rodando em modo servidor dedicado
    """
    data_path = get_data_db_path()
    app_path = get_app_db_path()
    is_network = _is_network_path(data_path) if data_path else False
    return {
        "is_network": is_network,
        "data_path": data_path,
        "app_path": app_path,
        "rede_base": REDE_BASE,
        "is_server": is_server_mode()
    }

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

    # 1.1 Trava de Segurança de Teste: Não replica na rede se estiver em modo de teste
    if os.environ.get("CCP_MODO_TESTE") == "1" or os.environ.get("CCP_NAO_COPIAR_REDE") == "1":
        print("\n[MODO TESTE ATIVO] Base local ccp_data.db atualizada com sucesso.")
        print("[SEGURANÇA] Cópia para a rede corporativa BLOQUEADA (Ambiente de Teste Isolado).")
        return sucesso_local

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

    # 3. Publicação e Backup do ccp_app.db na rede
    try:
        local_app_db = os.path.join(base_dir, DB_APP_NAME)
        if os.path.exists(local_app_db) and REDE_BASE and os.path.exists(REDE_BASE):
            if is_server_mode():
                # Publica réplica atômica do ccp_app.db na rede para sincronizar clientes
                tmp_app_path = REDE_APP_PATH + ".tmp"
                try:
                    shutil.copy2(local_app_db, tmp_app_path)
                    try:
                        os.replace(tmp_app_path, REDE_APP_PATH)
                    except (PermissionError, OSError):
                        shutil.copy2(local_app_db, REDE_APP_PATH)
                        if os.path.exists(tmp_app_path):
                            try:
                                os.remove(tmp_app_path)
                            except Exception:
                                pass
                    print(f"[OK REDE] ccp_app.db publicado com sucesso na rede: {REDE_APP_PATH}")
                except Exception as e_pub:
                    print(f"[AVISO REDE] Falha ao atualizar cópia ccp_app.db na rede: {e_pub}")

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
            # Não auto-travar emissores de aviso (a solicitação permanece com quem iniciou a análise)
            df_elab = df_elab[~df_elab[resp_col].astype(str).str.strip().str.lower().isin(MATRICULAS_AVISO)]
            if not df_elab.empty:
                novas_travas = df_elab[[sol_col, resp_col]].rename(columns={sol_col: 'Solicitação', resp_col: 'Matricula'})
                novas_travas['Matricula'] = novas_travas['Matricula'].apply(normalizar_matricula)
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

@st.cache_data(ttl=600)
def carregar_conjuntos_restritos():
    """
    Carrega as planilhas 'Alimentadores do Conjuntos.xlsx' e 'Conjuntos Restritos.xlsx'
    a partir de REDE_BASE ou caminhos candidatos corporativos.
    Retorna: (map_alim_to_sigla, set_conj_restritos, map_sigla_to_nome)
    """
    if os.environ.get("CCP_MODO_TESTE") == "1" or os.environ.get("CCP_FORCAR_LOCAL") == "1":
        candidatos_dir = [REDE_BASE or "."]
    else:
        candidatos_dir = [
            REDE_BASE,
            _UNC_FQDN_ACC,
            _UNC_FQDN_NORM,
            _UNC_REDE_ACC,
            _UNC_REDE_NORM,
            _REDE_ACC,
            _REDE_NORM,
        ]
    dir_valido = None
    for d in candidatos_dir:
        if d and os.path.exists(d):
            dir_valido = d
            break
            
    if not dir_valido:
        return {}, set(), {}

    f_alim = os.path.join(dir_valido, "Alimentadores do Conjuntos.xlsx")
    f_restr = os.path.join(dir_valido, "Conjuntos Restritos.xlsx")

    if not os.path.exists(f_alim) or not os.path.exists(f_restr):
        return {}, set(), {}

    try:
        df_alim = pd.read_excel(f_alim)
        df_restr = pd.read_excel(f_restr)

        col_alim = next((c for c in df_alim.columns if 'alimentador' in c.lower()), df_alim.columns[1] if len(df_alim.columns) > 1 else None)
        col_sigla_alim = next((c for c in df_alim.columns if 'sigla' in c.lower() or 'conj' in c.lower()), df_alim.columns[0])

        df_alim['alim_clean'] = df_alim[col_alim].astype(str).str.replace(' ', '').str.upper().str.strip()
        df_alim['sigla_clean'] = df_alim[col_sigla_alim].astype(str).str.upper().str.strip()

        # Priorizar correspondência onde o alimentador inicia com a sigla do conjunto
        # (ex: MAGT312 começa com MAGT, evitando que MAGT312 seja associado a URAT ou outras siglas em duplicidade)
        df_alim['prefix_match'] = df_alim.apply(
            lambda r: len(r['sigla_clean']) if r['alim_clean'].startswith(r['sigla_clean']) else 0, axis=1
        )
        df_alim = df_alim.sort_values(by=['alim_clean', 'prefix_match'], ascending=[True, True])
        df_alim = df_alim.drop_duplicates(subset=['alim_clean'], keep='last')

        map_alim_to_sigla = dict(zip(df_alim['alim_clean'], df_alim['sigla_clean']))

        col_sigla_restr = next((c for c in df_restr.columns if 'sigla' in c.lower()), None)
        col_nome_restr = next((c for c in df_restr.columns if 'conjunto' in c.lower()), None)
        col_restri_restr = next((c for c in df_restr.columns if 'restri' in c.lower()), None)

        if col_sigla_restr:
            df_restr['sigla_clean'] = df_restr[col_sigla_restr].astype(str).str.upper().str.strip()
        else:
            df_restr['sigla_clean'] = df_restr.iloc[:, 3].astype(str).str.upper().str.strip()

        if col_restri_restr:
            df_sub = df_restr[df_restr[col_restri_restr].astype(str).str.upper().str.contains('RESTRIT')]
            if df_sub.empty:
                df_sub = df_restr
        else:
            df_sub = df_restr

        set_conj_restritos = set(df_sub['sigla_clean'].dropna().unique())
        map_sigla_to_nome = dict(zip(df_restr['sigla_clean'], df_restr[col_nome_restr])) if col_nome_restr else {}

        return map_alim_to_sigla, set_conj_restritos, map_sigla_to_nome
    except Exception as e:
        print(f"[CONJUNTOS RESTRITOS] Erro ao carregar planilhas: {e}")
        return {}, set(), {}

def atualizar_email_decp_bd(map_email):
    """Atualiza a coluna Tem_Email_DECP na tabela demanda_atual para as solicitações mapeadas."""
    if not map_email:
        return
    conn = get_connection_write()
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(demanda_atual)")
        cols = [c[1] for c in cursor.fetchall()]
        if 'Tem_Email_DECP' not in cols:
            cursor.execute("ALTER TABLE demanda_atual ADD COLUMN Tem_Email_DECP BOOLEAN DEFAULT 0")

        col_sol = next((c for c in cols if 'solicita' in c.lower() and 'status' not in c.lower()), None)
        if col_sol:
            for solic, tem_email in map_email.items():
                cursor.execute(f"UPDATE demanda_atual SET Tem_Email_DECP = ? WHERE CAST({col_sol} AS TEXT) = ?", (1 if tem_email else 0, str(solic)))
        conn.commit()
    except Exception as e:
        print(f"[DB] Erro ao atualizar status de email DECP: {e}")
    finally:
        conn.close()

def atualizar_email_urgencia_bd(map_email):
    """Atualiza a coluna Tem_Email na tabela demanda_atual para as solicitações mapeadas."""
    if not map_email:
        return
    conn = get_connection_write()
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(demanda_atual)")
        cols = [c[1] for c in cursor.fetchall()]
        if 'Tem_Email' not in cols:
            cursor.execute("ALTER TABLE demanda_atual ADD COLUMN Tem_Email BOOLEAN DEFAULT 0")

        col_sol = next((c for c in cols if 'solicita' in c.lower() and 'status' not in c.lower()), None)
        if col_sol:
            for solic, tem_email in map_email.items():
                cursor.execute(f"UPDATE demanda_atual SET Tem_Email = ? WHERE CAST({col_sol} AS TEXT) = ?", (1 if tem_email else 0, str(solic)))
        conn.commit()
    except Exception as e:
        print(f"[DB] Erro ao atualizar status de email Urgência: {e}")
    finally:
        conn.close()

# --- NOVAS FUNÇÕES DE SEGURANÇA E GESTÃO ---

def verificar_login(matricula, password):
    """Verifica as credenciais do usuário com suporte a leitura em bases somente leitura."""
    import hashlib
    import bcrypt
    
    conn = get_connection_config_read()
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
                # Migração suave para bcrypt (apenas tenta se o banco for gravável)
                try:
                    conn_w = get_connection_config()
                    novo_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    conn_w.execute("UPDATE usuarios SET password_hash = ? WHERE matricula = ? COLLATE NOCASE", (novo_hash, matricula))
                    conn_w.commit()
                    conn_w.close()
                except Exception:
                    pass
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
        return pd.read_sql("SELECT matricula, nome, nivel, email FROM usuarios ORDER BY nome", conn)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()

@st.cache_data(ttl=300)
def get_mapa_matricula_nome():
    """Retorna dicionário mapeando matrícula normalizada para nome completo do usuário."""
    df_u = listar_usuarios()
    if df_u.empty:
        return {}
    res = {}
    for _, row in df_u.iterrows():
        m = normalizar_matricula(str(row['matricula']))
        if m:
            res[m.lower()] = str(row['nome']).strip()
    return res

def criar_usuario(matricula, nome, nivel, email=""):
    """Cria um novo usuário com senha padrão '12345'."""
    import bcrypt
    senha_padrao = "12345"
    senha_hash = bcrypt.hashpw(senha_padrao.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    conn = get_connection_config()
    try:
        conn.execute("""
            INSERT INTO usuarios (matricula, nome, password_hash, nivel, senha_provisoria, email)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (matricula.strip(), nome.strip(), senha_hash, nivel, email.strip().lower() if email else ""))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def atualizar_email_usuario(matricula, novo_email):
    """Atualiza o e-mail de um usuário existente."""
    conn = get_connection_config()
    try:
        conn.execute("UPDATE usuarios SET email = ? WHERE matricula = ? COLLATE NOCASE", (novo_email.strip().lower(), matricula))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def init_tabela_recuperacao():
    """Garante a existência da tabela recuperacao_senhas."""
    conn = get_connection_config()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recuperacao_senhas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matricula TEXT NOT NULL,
                codigo TEXT NOT NULL,
                expira_em DATETIME NOT NULL,
                tentativas INTEGER DEFAULT 0,
                usado BOOLEAN DEFAULT 0,
                criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    except Exception as e:
        print(f"[DB] Erro ao criar tabela recuperacao_senhas: {e}")
    finally:
        conn.close()

def enviar_email_codigo_recuperacao(destinatario, codigo, nome):
    """Dispara e-mail com o código de 6 dígitos via PowerShell e Outlook local."""
    import subprocess
    import json
    import os
    
    import html
    
    path_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "send_reset_email.ps1")
    if not os.path.exists(path_script):
        return False, "Script de envio send_reset_email.ps1 não encontrado."
        
    nome_escaped = "".join(f"&#{ord(c)};" if ord(c) > 127 else html.escape(c) for c in str(nome))
    
    cmd = [
        "powershell.exe",
        "-ExecutionPolicy", "Bypass",
        "-File", path_script,
        destinatario,
        str(codigo),
        nome_escaped
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=20)
        output = res.stdout.strip()
        if output:
            try:
                dados = json.loads(output)
                if dados.get("sucesso"):
                    return True, "E-mail enviado com sucesso."
                else:
                    return False, dados.get("erro", "Erro desconhecido retornado pelo Outlook.")
            except Exception:
                pass
        if res.returncode == 0:
            return True, "E-mail enviado."
        return False, res.stderr.strip() or "Falha no processo de envio do Outlook."
    except subprocess.TimeoutExpired:
        return False, "Tempo limite esgotado ao tentar comunicar com o Outlook. Verifique se o aplicativo está aberto."
    except Exception as e:
        return False, f"Erro ao disparar e-mail: {e}"

def solicitar_codigo_recuperacao(matricula):
    """
    Localiza o usuário pela matrícula, gera código de 6 dígitos e dispara e-mail corporativo.
    Retorna: (sucesso: bool, mensagem: str, email_mascarado: str)
    """
    import random
    from datetime import datetime, timedelta
    
    init_tabela_recuperacao()
    mat_clean = str(matricula).strip()
    
    conn = get_connection_config_read()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT matricula, nome, email FROM usuarios WHERE matricula = ? COLLATE NOCASE", (mat_clean,))
        user_row = cursor.fetchone()
        if not user_row:
            return False, "Matrícula não encontrada no sistema.", None
            
        mat_db, nome_db, email_db = user_row
        if not email_db or not str(email_db).strip() or str(email_db).strip().upper() == 'DESLIGADO' or '@' not in str(email_db):
            return False, "Este usuário não possui e-mail cadastrado ou está inativo. Contate o Administrador.", None
            
        email_clean = str(email_db).strip().lower()
        
        # Gera PIN aleatório seguro de 6 dígitos
        codigo = f"{random.SystemRandom().randint(100000, 999999)}"
        expira_em = datetime.now() + timedelta(minutes=10)
        
        # Salva o código na tabela
        conn_w = get_connection_config()
        try:
            # Invalida códigos anteriores não usados para esta matrícula
            conn_w.execute("UPDATE recuperacao_senhas SET usado = 1 WHERE matricula = ? AND usado = 0", (mat_db,))
            conn_w.execute("""
                INSERT INTO recuperacao_senhas (matricula, codigo, expira_em, tentativas, usado)
                VALUES (?, ?, ?, 0, 0)
            """, (mat_db, codigo, expira_em.strftime('%Y-%m-%d %H:%M:%S')))
            conn_w.commit()
        finally:
            conn_w.close()
            
        # Dispara o e-mail via Outlook
        ok, msg_envio = enviar_email_codigo_recuperacao(email_clean, codigo, nome_db)
        if not ok:
            return False, f"Não foi possível enviar o e-mail pelo Outlook: {msg_envio}. Verifique se o Outlook está aberto na sua máquina.", None
            
        # Mascara o e-mail para privacidade (ex: an****@cemig.com.br)
        partes_email = email_clean.split('@')
        nome_user = partes_email[0]
        dominio = partes_email[1] if len(partes_email) > 1 else 'cemig.com.br'
        if len(nome_user) <= 3:
            mask_user = nome_user[0] + "***"
        else:
            mask_user = nome_user[:2] + "****" + nome_user[-1]
        email_mascarado = f"{mask_user}@{dominio}"
        
        return True, "Código enviado com sucesso!", email_mascarado
    except Exception as e:
        return False, f"Erro interno ao solicitar recuperação: {e}", None
    finally:
        conn.close()

def validar_e_redefinir_senha_recuperacao(matricula, codigo, nova_senha):
    """
    Valida o código de 6 dígitos e, se correto, atualiza a senha do usuário.
    Retorna: (sucesso: bool, mensagem: str)
    """
    from datetime import datetime
    
    if len(str(nova_senha).strip()) < 4:
        return False, "A nova senha deve possuir pelo menos 4 caracteres."
        
    mat_clean = str(matricula).strip()
    cod_clean = str(codigo).strip()
    
    conn = get_connection_config()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, codigo, expira_em, tentativas 
            FROM recuperacao_senhas 
            WHERE matricula = ? AND usado = 0 
            ORDER BY id DESC LIMIT 1
        """, (mat_clean,))
        reg = cursor.fetchone()
        
        if not reg:
            return False, "Nenhuma solicitação de recuperação ativa para esta matrícula. Solicite um novo código."
            
        reg_id, cod_db, expira_str, tentativas = reg
        
        # Verifica expiração
        try:
            expira_dt = datetime.strptime(str(expira_str)[:19], '%Y-%m-%d %H:%M:%S')
            if datetime.now() > expira_dt:
                conn.execute("UPDATE recuperacao_senhas SET usado = 1 WHERE id = ?", (reg_id,))
                conn.commit()
                return False, "O código de verificação expirou (validade de 10 min). Solicite um novo código."
        except Exception:
            pass
            
        # Verifica limite de tentativas
        if tentativas >= 3:
            conn.execute("UPDATE recuperacao_senhas SET usado = 1 WHERE id = ?", (reg_id,))
            conn.commit()
            return False, "Limite de 3 tentativas excedido por segurança. Solicite um novo código."
            
        # Verifica se o código confere
        if cod_clean != str(cod_db).strip():
            conn.execute("UPDATE recuperacao_senhas SET tentativas = tentativas + 1 WHERE id = ?", (reg_id,))
            conn.commit()
            restantes = 2 - tentativas
            if restantes > 0:
                return False, f"Código incorreto. Você ainda tem {restantes} tentativa(s)."
            else:
                return False, "Código incorreto. Limite de tentativas excedido. Solicite um novo código."
                
        # Código válido! Marca como usado e atualiza a senha
        conn.execute("UPDATE recuperacao_senhas SET usado = 1 WHERE id = ?", (reg_id,))
        conn.commit()
        
        ok_senha = atualizar_senha(mat_clean, nova_senha)
        if ok_senha:
            return True, "Senha redefinida com sucesso! Você já pode acessar o sistema."
        else:
            return False, "Erro ao gravar a nova senha no banco de dados."
    except Exception as e:
        return False, f"Erro interno ao redefinir senha: {e}"
    finally:
        conn.close()

def verificar_se_codigo_recuperacao(matricula, codigo_digitado):
    """Verifica se o valor digitado corresponde a um código de recuperação ativo e válido."""
    if not matricula or not codigo_digitado:
        return False
    cod_str = str(codigo_digitado).strip()
    if len(cod_str) != 6 or not cod_str.isdigit():
        return False
    from datetime import datetime
    conn = get_connection_config_read()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, expira_em, tentativas, usado 
            FROM recuperacao_senhas 
            WHERE matricula = ? COLLATE NOCASE AND codigo = ? AND usado = 0
            ORDER BY id DESC LIMIT 1
        """, (str(matricula).strip(), cod_str))
        row = cursor.fetchone()
        if not row:
            return False
        _, expira_em_str, tentativas, usado = row
        if usado or tentativas >= 3:
            return False
        expira_dt = datetime.strptime(str(expira_em_str)[:19], '%Y-%m-%d %H:%M:%S')
        if datetime.now() > expira_dt:
            return False
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
    path = get_app_db_path()
    if not is_server_mode() and path and _is_network_path(path):
        return 0

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
    path = get_app_db_path()
    if not is_server_mode() and path and _is_network_path(path):
        return 0

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

            # Limpa também da fila_conciliacao caso tenha retornado à fila ativa sem apuração
            try:
                cursor.execute(f"""
                    DELETE FROM fila_conciliacao 
                    WHERE status_apurado IS NULL 
                    AND (solicitacao IN ({placeholders}) OR LTRIM(solicitacao, '0') IN ({placeholders}))
                """, chunk + chunk)
            except Exception:
                pass
            
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
    path = get_app_db_path()
    # Em modo cliente conectado à rede, a base já é mantida e gerenciada pelo servidor.
    # Evita tentativas de criação/limpeza em pastas somente leitura da rede.
    if not is_server_mode() and path and _is_network_path(path):
        return

    conn = get_connection_config()
    try:
        # 1. Tabela de Usuários
        conn.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                matricula TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                nivel TEXT NOT NULL,
                senha_provisoria INTEGER DEFAULT 1,
                email TEXT
            )
        ''')
        
        # Migração defensiva: garante a coluna email se tabela já existia sem ela
        try:
            cur_chk = conn.cursor()
            cur_chk.execute("PRAGMA table_info(usuarios)")
            cols_chk = [c[1] for c in cur_chk.fetchall()]
            if 'email' not in cols_chk:
                conn.execute("ALTER TABLE usuarios ADD COLUMN email TEXT")
        except Exception:
            pass

        # Tabela de Recuperação de Senhas
        conn.execute('''
            CREATE TABLE IF NOT EXISTS recuperacao_senhas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matricula TEXT NOT NULL,
                codigo TEXT NOT NULL,
                expira_em DATETIME NOT NULL,
                tentativas INTEGER DEFAULT 0,
                usado BOOLEAN DEFAULT 0,
                criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
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
                pendentes_iniciadas_dia INTEGER DEFAULT 0,
                pendentes_dias_anteriores INTEGER DEFAULT 0,
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

        for col_n in ['pendentes_iniciadas_dia', 'pendentes_dias_anteriores']:
            try:
                conn.execute(f"ALTER TABLE pendentes_snapshot ADD COLUMN {col_n} INTEGER DEFAULT 0")
            except Exception:
                pass

        # 9. Tabela de Fila de Conciliação de Status (Auditoria Remota de Saídas)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS fila_conciliacao (
                solicitacao TEXT PRIMARY KEY,
                sigla_regiao TEXT,
                matricula_responsavel TEXT,
                data_saida TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status_apurado TEXT,
                data_auditoria TIMESTAMP,
                manobra TEXT,
                usu_elaboracao TEXT
            )
        ''')

        # Migração defensiva: garante a coluna status_detalhado em eventos_diarios
        try:
            cur_chk = conn.cursor()
            cur_chk.execute("PRAGMA table_info(eventos_diarios)")
            cols_chk = [c[1] for c in cur_chk.fetchall()]
            if 'status_detalhado' not in cols_chk:
                conn.execute("ALTER TABLE eventos_diarios ADD COLUMN status_detalhado TEXT")
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
        # 9. Auto-recomposição do histórico de pendentes se pendentes_iniciadas_dia estiver zerado
        cursor.execute("SELECT COALESCE(SUM(pendentes_iniciadas_dia), 0) FROM pendentes_snapshot")
        if cursor.fetchone()[0] == 0:
            print("[INIT] Colunas pendentes_iniciadas_dia não preenchidas. Recompondo histórico inicial de pendentes...")
            recompor_snapshot_historico()
        # 10. Auto-deduplicação do histórico de eventos diários
        deduplicar_historico_eventos()
        # 11. Sanitização de registros indevidos de TRATADA para solicitações que continuam ativas
        sanitizar_eventos_tratadas_ativas()
            
        conn.commit()
    except Exception as e:
        print(f"[ERRO INIT] Falha ao inicializar tabelas: {e}")
    finally:
        conn.close()

def get_session_connection():
    """
    Retorna conexão para persistência local de sessões/tokens.
    Salva no banco local 'ccp_local.db' para garantir escrita mesmo quando a base de rede for somente leitura.
    """
    local_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ccp_local.db")
    conn = sqlite3.connect(local_db, timeout=10)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sessoes_persistentes (
            token TEXT PRIMARY KEY,
            matricula TEXT NOT NULL,
            data_expiracao TIMESTAMP NOT NULL
        )
    ''')
    return conn

def gerar_token_sessao(matricula):
    """Gera um novo token de sessão com validade de 30 dias com persistência local resiliente."""
    import secrets
    import datetime
    
    token = secrets.token_urlsafe(32)
    expiracao = (get_agora_br() + datetime.timedelta(days=30)).isoformat()
    
    # 1. Prioriza persistência local segura (ccp_local.db - sempre gravável na estação do usuário)
    try:
        conn_local = get_session_connection()
        conn_local.execute('''
            INSERT OR REPLACE INTO sessoes_persistentes (token, matricula, data_expiracao)
            VALUES (?, ?, ?)
        ''', (token, matricula, expiracao))
        conn_local.commit()
        conn_local.close()
        return token
    except Exception as e_loc:
        print(f"[AUTH AVISO] Falha ao gravar sessão no banco local: {e_loc}")

    # 2. Fallback: tenta banco corporativo caso seja gravável (modo servidor/ADM)
    try:
        conn = get_connection_config()
        conn.execute('''
            INSERT INTO sessoes_persistentes (token, matricula, data_expiracao)
            VALUES (?, ?, ?)
        ''', (token, matricula, expiracao))
        conn.commit()
        conn.close()
        return token
    except Exception:
        pass
        
    return token

def validar_token_sessao(token):
    """Verifica se um token é válido e retorna os dados do usuário."""
    if not token:
        return None
        
    matricula = None
    agora_iso = get_agora_br().isoformat()
    
    # 1. Verifica primeiro no banco local de sessões
    try:
        conn_local = get_session_connection()
        cursor = conn_local.cursor()
        cursor.execute('''
            SELECT matricula FROM sessoes_persistentes 
            WHERE token = ? AND data_expiracao > ?
        ''', (token, agora_iso))
        result = cursor.fetchone()
        conn_local.close()
        if result:
            matricula = result[0]
    except Exception:
        pass

    # 2. Fallback: verifica no banco da rede se não achou no local
    if not matricula:
        try:
            conn = get_connection_config_read()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT matricula FROM sessoes_persistentes 
                WHERE token = ? AND data_expiracao > ?
            ''', (token, agora_iso))
            result = cursor.fetchone()
            conn.close()
            if result:
                matricula = result[0]
        except Exception:
            pass
        
    if matricula:
        # Busca dados atualizados do usuário na base corporativa oficial em modo leitura
        try:
            conn_user = get_connection_config_read()
            cursor = conn_user.cursor()
            cursor.execute("SELECT matricula, nome, nivel, senha_provisoria FROM usuarios WHERE matricula = ? COLLATE NOCASE", (matricula,))
            user_data = cursor.fetchone()
            conn_user.close()
            return user_data
        except Exception as e:
            print(f"[AUTH] Erro ao buscar dados de usuário do token: {e}")
            
    return None

def remover_sessao(token):
    """Remove um token de sessão (logout) nos bancos local e de rede."""
    if not token:
        return True
    try:
        conn_local = get_session_connection()
        conn_local.execute("DELETE FROM sessoes_persistentes WHERE token = ?", (token,))
        conn_local.commit()
        conn_local.close()
    except Exception:
        pass
    try:
        conn = get_connection_config()
        conn.execute("DELETE FROM sessoes_persistentes WHERE token = ?", (token,))
        conn.commit()
        conn.close()
    except Exception:
        pass
    return True

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
                ON CONFLICT(solicitacao) DO UPDATE SET matricula=excluded.matricula
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
        
        data_ontem_util = obter_dia_util_anterior(data_hoje)
        cursor.execute("SELECT solicitacao FROM eventos_diarios WHERE tipo_evento = 'INICIADA' AND date(data_evento) >= ?", (data_ontem_util,))
        sols_iniciadas_hoje_ontem = set(str(r[0]).strip().lstrip('0') for r in cursor.fetchall())

        for matricula in todos_usuarios:
            cursor.execute("SELECT solicitacao FROM solicitacoes_travadas WHERE matricula = ?", (matricula,))
            travadas = [str(row[0]).strip().lstrip('0') for row in cursor.fetchall() if str(row[0]).strip() and str(row[0]).strip() not in ['None', 'nan', '0']]
            
            mask = (df_pendentes['Resp_Clean'] == matricula)
            if travadas:
                mask = mask | ((df_pendentes['Solicitacao_Clean'] != '') & (df_pendentes['Solicitacao_Clean'] != 'None') & df_pendentes['Solicitacao_Clean'].isin(travadas))
                
            df_user = df_pendentes[mask]
            
            total = len(df_user)
            df_elabora = df_user[df_user['Situacao_Clean'].str.contains('ELABORA', na=False)]
            iniciadas = len(df_elabora)
            nao_iniciadas = len(df_user[df_user['Situacao_Clean'] == 'APROVADA'])
            
            # Faixa Amarela: Em elaboração (Hoje e Ontem útil)
            iniciadas_hoje_ontem = len(df_elabora[df_elabora['Solicitacao_Clean'].isin(sols_iniciadas_hoje_ontem)])
            # Faixa Vermelha: Em elaboração há +2 dias úteis
            mais_2_dias = max(0, iniciadas - iniciadas_hoje_ontem)
            
            cursor.execute("""
                INSERT INTO pendentes_snapshot (
                    data, matricula, pendentes_total, pendentes_iniciadas, pendentes_nao_iniciadas,
                    pendentes_iniciadas_dia, pendentes_dias_anteriores
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(data, matricula) DO UPDATE SET
                    pendentes_total=excluded.pendentes_total,
                    pendentes_iniciadas=excluded.pendentes_iniciadas,
                    pendentes_nao_iniciadas=excluded.pendentes_nao_iniciadas,
                    pendentes_iniciadas_dia=excluded.pendentes_iniciadas_dia,
                    pendentes_dias_anteriores=excluded.pendentes_dias_anteriores
            """, (data_hoje, matricula, total, iniciadas, nao_iniciadas, iniciadas_hoje_ontem, mais_2_dias))
            
        conn.commit()
    except Exception as e:
        print(f"[DB] Erro no registro de snapshot de pendentes: {e}")
    finally:
        if conn is not None:
            conn.close()

def recompor_snapshot_historico():
    """
    Recompõe o histórico das colunas pendentes_iniciadas_dia e pendentes_dias_anteriores
    cruzando diretamente a tabela pendentes_snapshot com eventos_diarios (INICIADA e TRATADA).
    """
    conn_app = None
    try:
        conn_app = get_connection_config(read_only=False)
        cursor_app = conn_app.cursor()

        # Verifica se as colunas existem
        cursor_app.execute("PRAGMA table_info(pendentes_snapshot)")
        cols = [r[1] for r in cursor_app.fetchall()]
        if 'pendentes_iniciadas_dia' not in cols:
            cursor_app.execute("ALTER TABLE pendentes_snapshot ADD COLUMN pendentes_iniciadas_dia INTEGER DEFAULT 0")
        if 'pendentes_dias_anteriores' not in cols:
            cursor_app.execute("ALTER TABLE pendentes_snapshot ADD COLUMN pendentes_dias_anteriores INTEGER DEFAULT 0")
        conn_app.commit()

        # 1. Carrega todos os snapshots de pendentes existentes
        df_snap = pd.read_sql("SELECT data, matricula, pendentes_iniciadas FROM pendentes_snapshot", conn_app)
        if df_snap.empty:
            return

        # 2. Carrega eventos INICIADA e TRATADA
        df_ev = pd.read_sql("""
            SELECT 
                date(data_evento) as dt,
                matricula_responsavel as mat,
                solicitacao,
                tipo_evento
            FROM eventos_diarios
            WHERE tipo_evento IN ('INICIADA', 'TRATADA')
        """, conn_app)

        iniciadas_dia = {}
        tratadas_dia = {}
        if not df_ev.empty:
            df_ini = df_ev[df_ev['tipo_evento'] == 'INICIADA']
            iniciadas_dia = df_ini.groupby(['dt', 'mat'])['solicitacao'].apply(
                lambda s: set(str(x).strip().lstrip('0') for x in s)
            ).to_dict()

            df_trat = df_ev[df_ev['tipo_evento'] == 'TRATADA']
            tratadas_dia = df_trat.groupby(['dt', 'mat'])['solicitacao'].apply(
                lambda s: set(str(x).strip().lstrip('0') for x in s)
            ).to_dict()

        # 3. Identifica solicitações travadas e suas datas do primeiro evento INICIADA
        df_trav = pd.read_sql("SELECT solicitacao, matricula, date(data_trava) as dt_trava FROM solicitacoes_travadas", conn_app)
        travadas_por_user = {}
        if not df_trav.empty:
            travadas_por_user = df_trav.groupby('matricula')['solicitacao'].apply(
                lambda s: set(str(x).strip().lstrip('0') for x in s)
            ).to_dict()

        primeiro_inicio = {}
        if not df_ev.empty:
            df_ini_all = df_ev[df_ev['tipo_evento'] == 'INICIADA']
            primeiro_inicio = df_ini_all.groupby('solicitacao')['dt'].min().to_dict()

        # 4. Calcula o split para cada snapshot
        updates = []
        for _, row in df_snap.iterrows():
            d = row['data']
            m = row['matricula']
            pend_ini = int(row['pendentes_iniciadas'] or 0)

            if pend_ini <= 0:
                updates.append((0, 0, d, m))
                continue

            dt_ontem_util = obter_dia_util_anterior(d)

            # Demandas iniciadas na janela de Hoje e Ontem útil [dt_ontem_util, d]
            sols_ini_janela = set()
            for (dt_ev, mat_ev), s_set in iniciadas_dia.items():
                if mat_ev == m and dt_ontem_util <= dt_ev <= d:
                    sols_ini_janela.update(s_set)

            sols_trat = tratadas_dia.get((d, m), set())
            sols_ini_nao_tratadas = sols_ini_janela - sols_trat

            # Demandas travadas que comprovadamente iniciaram antes de dt_ontem_util (+2 dias úteis)
            sols_user_trav = travadas_por_user.get(m, set())
            travadas_anteriores = sum(1 for s in sols_user_trav if primeiro_inicio.get(s, d) < dt_ontem_util)

            qtd_ini_janela = len(sols_ini_nao_tratadas)
            max_ini_janela = max(0, pend_ini - travadas_anteriores)
            pend_hoje_ontem = min(qtd_ini_janela, max_ini_janela)
            pend_mais_2d = max(0, pend_ini - pend_hoje_ontem)

            updates.append((pend_hoje_ontem, pend_mais_2d, d, m))

        if updates:
            cursor_app.executemany("""
                UPDATE pendentes_snapshot
                SET pendentes_iniciadas_dia = ?, pendentes_dias_anteriores = ?
                WHERE data = ? AND matricula = ?
            """, updates)
            conn_app.commit()
            print(f"[DB] Snapshots de pendentes recompostos com sucesso: {len(updates)} registros atualizados.")
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
            # Prioridade 1: Resp. Manobra do registro extraído do GDIS-PM (se não for emissor de aviso)
            if row_dict:
                for k, v in row_dict.items():
                    if 'resp' in k.lower() and 'manobra' in k.lower() and pd.notna(v):
                        v_str = normalizar_matricula(str(v).strip())
                        if v_str and v_str != '-' and len(v_str) >= 4 and not v_str.upper().startswith('NÃO') and v_str.lower() not in MATRICULAS_AVISO:
                            return v_str
            
            # Prioridade 2: Solicitacao travada no banco (técnico que iniciou a análise)
            sol_id_str = str(sol_id).strip()
            sol_id_norm = sol_id_str.lstrip('0')
            if sol_id_str in travadas_dict:
                t_mat = normalizar_matricula(travadas_dict[sol_id_str])
                if t_mat.lower() not in MATRICULAS_AVISO:
                    return t_mat
            if sol_id_norm in travadas_dict:
                t_mat = normalizar_matricula(travadas_dict[sol_id_norm])
                if t_mat.lower() not in MATRICULAS_AVISO:
                    return t_mat
            
            # Prioridade 3: Dono fixo da região
            sigla = str(regiao_str).strip()[:2].upper() if pd.notna(regiao_str) else ""
            if sigla in regioes_dict:
                return normalizar_matricula(regioes_dict[sigla])
                
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
        
        # Blindagem de Segurança: Se a base antiga estiver vazia ou com volume anômalo (>80 novas em um ciclo de 15min),
        # aborta a inserção de 'NOVA' para prevenir poluição histórica com o estoque legado.
        ignorar_novas_em_massa = False
        if not antigas_dict:
            print("[EVENTOS ALERTA] Base comparativa antiga vazia. Ignorando geração de eventos NOVA para não poluir o histórico com o estoque legado.")
            ignorar_novas_em_massa = True
        else:
            candidatas_novas_count = sum(1 for s in novas_dict.keys() if s not in antigas_dict)
            if candidatas_novas_count > 80:
                print(f"[EVENTOS ALERTA] Volume anômalo de solicitações novas ({candidatas_novas_count}). Abortando registro de NOVA por segurança.")
                ignorar_novas_em_massa = True

        # 1. Novas e Iniciadas
        for sol_id, row_nova in novas_dict.items():
            if sol_id not in antigas_dict:
                if not ignorar_novas_em_massa:
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

                # Alimentação da fila de conciliação para as demandas tratadas que precisam de auditoria de status
                tratadas_novas = [
                    (str(ev[0]).strip().lstrip('0'), str(ev[2]).strip(), str(ev[3]).strip(), ev[4])
                    for ev in eventos_unicos if ev[1] == 'TRATADA'
                ]
                if tratadas_novas:
                    try:
                        cursor.executemany('''
                            INSERT INTO fila_conciliacao (solicitacao, sigla_regiao, matricula_responsavel, data_saida)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(solicitacao) DO UPDATE SET
                                data_saida = excluded.data_saida,
                                sigla_regiao = excluded.sigla_regiao,
                                matricula_responsavel = excluded.matricula_responsavel
                            WHERE status_apurado IS NULL
                        ''', tratadas_novas)
                    except Exception as e_fila:
                        print(f"[DB] Aviso ao alimentar fila_conciliacao: {e_fila}")

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
                SUM(CASE WHEN tipo_evento = 'NOVA' THEN 1 ELSE 0 END) as Novas,
                SUM(CASE WHEN tipo_evento = 'INICIADA' THEN 1 ELSE 0 END) as Iniciadas,
                SUM(CASE WHEN tipo_evento = 'TRATADA' THEN 1 ELSE 0 END) as Tratadas,
                SUM(CASE WHEN tipo_evento = 'TRATADA' AND UPPER(status_detalhado) IN ('ELABORADA', 'ENVIADA PARA O CONDIS', 'ENVIANDO PARA CONDIS') THEN 1 ELSE 0 END) as Elaboradas,
                SUM(CASE WHEN tipo_evento = 'TRATADA' AND UPPER(status_detalhado) IN ('REPROVADA', 'CANCELADA') THEN 1 ELSE 0 END) as Reprovadas,
                SUM(CASE WHEN tipo_evento = 'TRATADA' AND (status_detalhado IS NULL OR TRIM(status_detalhado) = '') AND date(data_evento) >= '2026-10-26' THEN 1 ELSE 0 END) as Pendentes_Conciliacao
            FROM eventos_diarios
            WHERE matricula_responsavel = ?
            AND date(data_evento) BETWEEN ? AND ?
            GROUP BY date(data_evento)
        """
        df_eventos = pd.read_sql(query_eventos, conn_app, params=[matricula, data_inicio, data_fim])
        
        if df_eventos.empty:
            df_perf = pd.DataFrame(columns=[
                'Data', 'Novas', 'Tratadas', 'Iniciadas', 'Elaboradas', 'Reprovadas', 'Pendentes_Conciliacao', 'Pendentes'
            ])
        else:
            df_perf = df_eventos.rename(columns={'data': 'Data'})
            for col in ['Novas', 'Tratadas', 'Iniciadas', 'Elaboradas', 'Reprovadas', 'Pendentes_Conciliacao']:
                if col not in df_perf.columns:
                    df_perf[col] = 0
            
        # --- PENDENTES: Ler do snapshot persistente (ccp_app.db) ---
        cursor.execute("""
            SELECT 
                data, 
                pendentes_total, 
                pendentes_iniciadas, 
                pendentes_nao_iniciadas,
                COALESCE(pendentes_iniciadas_dia, 0),
                COALESCE(pendentes_dias_anteriores, 0)
            FROM pendentes_snapshot 
            WHERE matricula = ? AND data BETWEEN ? AND ? 
            ORDER BY data
        """, (matricula, data_inicio, data_fim))
        rows_pend = cursor.fetchall()
        
        if rows_pend:
            df_pendentes = pd.DataFrame(rows_pend, columns=[
                'Data', 'Pendentes', 'Pendentes_Iniciadas', 'Pendentes_Nao_Iniciadas',
                'Pendentes_Iniciadas_Dia', 'Pendentes_Dias_Anteriores'
            ])
            
            if not df_perf.empty and not df_pendentes.empty:
                df_perf = pd.merge(df_perf, df_pendentes, on='Data', how='outer').fillna(0)
            elif not df_pendentes.empty:
                df_perf = df_pendentes
                df_perf['Novas'] = 0
                df_perf['Tratadas'] = 0
                df_perf['Iniciadas'] = 0
                df_perf['Elaboradas'] = 0
                df_perf['Reprovadas'] = 0
                df_perf['Pendentes_Conciliacao'] = 0
        else:
            df_perf['Pendentes'] = 0
            df_perf['Pendentes_Iniciadas'] = 0
            df_perf['Pendentes_Nao_Iniciadas'] = 0
            df_perf['Pendentes_Iniciadas_Dia'] = 0
            df_perf['Pendentes_Dias_Anteriores'] = 0
                
        if not df_perf.empty:
            df_perf['Novas'] = df_perf.get('Novas', 0).astype(int)
            df_perf['Tratadas'] = df_perf.get('Tratadas', 0).astype(int)
            df_perf['Elaboradas'] = df_perf.get('Elaboradas', 0).astype(int)
            df_perf['Reprovadas'] = df_perf.get('Reprovadas', 0).astype(int)
            df_perf['Pendentes_Conciliacao'] = df_perf.get('Pendentes_Conciliacao', 0).astype(int)
            df_perf['Iniciadas'] = df_perf.get('Iniciadas', 0).astype(int)
            df_perf['Pendentes'] = df_perf.get('Pendentes', 0).astype(int)
            df_perf['Pendentes_Iniciadas'] = df_perf.get('Pendentes_Iniciadas', 0).astype(int)
            df_perf['Pendentes_Nao_Iniciadas'] = df_perf.get('Pendentes_Nao_Iniciadas', 0).astype(int)
            df_perf['Pendentes_Iniciadas_Dia'] = df_perf.get('Pendentes_Iniciadas_Dia', 0).astype(int)
            df_perf['Pendentes_Dias_Anteriores'] = df_perf.get('Pendentes_Dias_Anteriores', 0).astype(int)

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
                df_perf['Elaboradas'] = 0
                df_perf['Reprovadas'] = 0
                df_perf['Pendentes_Conciliacao'] = 0
                df_perf['Iniciadas'] = 0
                df_perf['Pendentes'] = 0
                df_perf['Pendentes_Iniciadas'] = 0
                df_perf['Pendentes_Nao_Iniciadas'] = 0
                df_perf['Pendentes_Iniciadas_Dia'] = 0
                df_perf['Pendentes_Dias_Anteriores'] = 0

            # Preenche NaNs de eventos com 0
            df_perf['Novas'] = df_perf['Novas'].fillna(0).astype(int)
            df_perf['Tratadas'] = df_perf['Tratadas'].fillna(0).astype(int)
            df_perf['Elaboradas'] = df_perf['Elaboradas'].fillna(0).astype(int)
            df_perf['Reprovadas'] = df_perf['Reprovadas'].fillna(0).astype(int)
            df_perf['Pendentes_Conciliacao'] = df_perf['Pendentes_Conciliacao'].fillna(0).astype(int)
            df_perf['Iniciadas'] = df_perf['Iniciadas'].fillna(0).astype(int)

            # Para dias sem snapshot (ex: fins de semana sem extração), propaga o estoque de pendências do dia útil anterior
            df_perf['Pendentes_Iniciadas'] = df_perf['Pendentes_Iniciadas'].ffill().fillna(0).astype(int)
            df_perf['Pendentes'] = df_perf['Pendentes'].ffill().fillna(0).astype(int)
            df_perf['Pendentes_Nao_Iniciadas'] = df_perf['Pendentes_Nao_Iniciadas'].ffill().fillna(0).astype(int)
            df_perf['Pendentes_Iniciadas_Dia'] = df_perf['Pendentes_Iniciadas_Dia'].fillna(0).astype(int)

            # Saldo exato: dias anteriores = (pendentes em elaboração - iniciadas no próprio dia)
            df_perf['Pendentes_Dias_Anteriores'] = (df_perf['Pendentes_Iniciadas'] - df_perf['Pendentes_Iniciadas_Dia']).clip(lower=0).astype(int)
            
            df_perf = df_perf.sort_values('Data')
        except Exception:
            pass
            
        return df_perf
    except Exception as e:
        print(f"Erro em get_performance_d1: {e}")
        return pd.DataFrame(columns=[
            'Data', 'Novas', 'Tratadas', 'Elaboradas', 'Reprovadas', 'Pendentes_Conciliacao',
            'Iniciadas', 'Pendentes', 'Pendentes_Iniciadas', 'Pendentes_Nao_Iniciadas',
            'Pendentes_Iniciadas_Dia', 'Pendentes_Dias_Anteriores'
        ])
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

def get_detalhe_drilldown_performance(resp_nome, data_str, nome_serie):
    """
    Retorna DataFrame com as solicitações e regiões para o drill-down do gráfico de performance:
    Colunas: ['Solicitação', 'Região', 'Situação', 'Data de Início']
    """
    conn_app = get_connection_config()
    conn_data = get_connection_read()
    try:
        cursor = conn_app.cursor()
        cursor.execute("SELECT matricula FROM usuarios WHERE nome = ? OR matricula = ?", (resp_nome, resp_nome))
        res = cursor.fetchone()
        if not res:
            return pd.DataFrame(columns=['Solicitação', 'Região', 'Situação', 'Data de Início', 'Nº Manobra', 'Usu. Elaboração'])
        mat = res[0]
        
        dt_iso = pd.to_datetime(data_str, dayfirst=True).strftime('%Y-%m-%d')
        serie_lower = str(nome_serie).lower()
        df_ev = pd.DataFrame()
        
        if 'aprovadas' in serie_lower or 'nova' in serie_lower:
            df_ev = pd.read_sql("""
                SELECT solicitacao, regiao, data_evento as data_ref
                FROM eventos_diarios
                WHERE matricula_responsavel = ? AND tipo_evento = 'NOVA' AND date(data_evento) = ?
            """, conn_app, params=[mat, dt_iso])
            
        elif ('reprovada' in serie_lower or 'cancelada' in serie_lower) and 'tratada' not in serie_lower:
            df_ev = pd.read_sql("""
                SELECT e.solicitacao, e.regiao, e.data_evento as data_ref,
                       e.status_detalhado, fc.manobra, fc.usu_elaboracao
                FROM eventos_diarios e
                LEFT JOIN fila_conciliacao fc ON e.solicitacao = fc.solicitacao
                WHERE e.matricula_responsavel = ? AND e.tipo_evento = 'TRATADA' AND date(e.data_evento) = ?
                  AND UPPER(e.status_detalhado) IN ('REPROVADA', 'CANCELADA')
            """, conn_app, params=[mat, dt_iso])
            
        elif 'tratadas' in serie_lower or 'elaborada' in serie_lower or 'condis' in serie_lower:
            if dt_iso >= '2026-10-26' and ('elaborada' in serie_lower or 'condis' in serie_lower):
                df_ev = pd.read_sql("""
                    SELECT e.solicitacao, e.regiao, e.data_evento as data_ref,
                           e.status_detalhado, fc.manobra, fc.usu_elaboracao
                    FROM eventos_diarios e
                    LEFT JOIN fila_conciliacao fc ON e.solicitacao = fc.solicitacao
                    WHERE e.matricula_responsavel = ? AND e.tipo_evento = 'TRATADA' AND date(e.data_evento) = ?
                      AND (UPPER(e.status_detalhado) IN ('ELABORADA', 'ENVIADA PARA O CONDIS', 'ENVIANDO PARA CONDIS')
                           OR e.status_detalhado IS NULL)
                """, conn_app, params=[mat, dt_iso])
            else:
                df_ev = pd.read_sql("""
                    SELECT e.solicitacao, e.regiao, e.data_evento as data_ref,
                           e.status_detalhado, fc.manobra, fc.usu_elaboracao
                    FROM eventos_diarios e
                    LEFT JOIN fila_conciliacao fc ON e.solicitacao = fc.solicitacao
                    WHERE e.matricula_responsavel = ? AND e.tipo_evento = 'TRATADA' AND date(e.data_evento) = ?
                """, conn_app, params=[mat, dt_iso])
            
        elif 'hoje e ontem' in serie_lower or 'iniciadas' in serie_lower or 'do dia' in serie_lower:
            dt_ontem_util = obter_dia_util_anterior(dt_iso)
            df_ev = pd.read_sql("""
                SELECT solicitacao, regiao, data_evento as data_ref
                FROM eventos_diarios
                WHERE matricula_responsavel = ? AND tipo_evento = 'INICIADA' 
                AND date(data_evento) BETWEEN ? AND ?
            """, conn_app, params=[mat, dt_ontem_util, dt_iso])
            
        elif '+2' in serie_lower or 'anteriores' in serie_lower:
            dt_ontem_util = obter_dia_util_anterior(dt_iso)
            df_trav = pd.read_sql("""
                SELECT st.solicitacao, ed.regiao, min(ed.data_evento) as data_ref
                FROM solicitacoes_travadas st
                LEFT JOIN eventos_diarios ed ON st.solicitacao = ed.solicitacao
                WHERE st.matricula = ?
                GROUP BY st.solicitacao
                HAVING date(data_ref) < ?
            """, conn_app, params=[mat, dt_ontem_util])
            df_ev = df_trav
            
        if df_ev.empty:
            return pd.DataFrame(columns=['Solicitação', 'Região', 'Situação', 'Data de Início', 'Nº Manobra', 'Usu. Elaboração'])
            
        sols = df_ev['solicitacao'].dropna().astype(str).str.strip().tolist()
        df_dem = pd.DataFrame()
        if sols:
            try:
                placeholders = ','.join(['?'] * len(sols))
                cursor_d = conn_data.cursor()
                cursor_d.execute("PRAGMA table_info(demanda_atual)")
                cols = [r[1] for r in cursor_d.fetchall()]
                c_sol = next((c for c in cols if 'solicit' in c.lower() and 'vinc' not in c.lower()), None)
                c_data = next((c for c in cols if 'início' in c.lower() or 'inicio' in c.lower()), None)
                c_sit = next((c for c in cols if 'situa' in c.lower()), None)
                c_reg = next((c for c in cols if 'regi' in c.lower()), None)
                
                if c_sol:
                    cols_select = [f'"{c_sol}" as solicitacao']
                    if c_data: cols_select.append(f'"{c_data}" as dt_inicio')
                    if c_sit: cols_select.append(f'"{c_sit}" as situacao')
                    if c_reg: cols_select.append(f'"{c_reg}" as regiao_dem')
                    
                    q = f"SELECT {', '.join(cols_select)} FROM demanda_atual WHERE \"{c_sol}\" IN ({placeholders})"
                    df_dem = pd.read_sql(q, conn_data, params=sols)
            except Exception:
                pass
                
        if not df_dem.empty:
            df_ev['solicitacao_str'] = df_ev['solicitacao'].astype(str).str.strip()
            df_dem['solicitacao_str'] = df_dem['solicitacao'].astype(str).str.strip()
            df_res = pd.merge(df_ev, df_dem, on='solicitacao_str', how='left')
            df_res['Região'] = df_res['regiao'].combine_first(df_res.get('regiao_dem')).fillna('ND')
            df_res['Data de Início'] = df_res.get('dt_inicio', '-')
            df_res['Solicitação'] = df_res['solicitacao_x']
        else:
            df_res = df_ev.copy()
            df_res['Solicitação'] = df_res['solicitacao']
            df_res['Região'] = df_res['regiao'].fillna('ND')
            df_res['Data de Início'] = '-'
            
        def _definir_sit(row):
            st_det = row.get('status_detalhado')
            if pd.notna(st_det) and str(st_det).strip():
                return str(st_det).strip().upper()
            if 'situacao' in row and pd.notna(row['situacao']) and str(row['situacao']).strip():
                return str(row['situacao']).strip().upper()
            if any(k in serie_lower for k in ['tratada', 'elaborada', 'reprovada', 'condis', 'cancelada']):
                return 'AGUARDANDO CONCILIAÇÃO' if dt_iso >= '2026-10-26' else 'TRATADA (LEGADO)'
            return 'APROVADA' if 'aprovadas' in serie_lower else 'EM ELABORAÇÃO'

        df_res['Situação'] = df_res.apply(_definir_sit, axis=1)
        df_res['Nº Manobra'] = df_res.get('manobra', '').fillna('-')
        df_res['Usu. Elaboração'] = df_res.get('usu_elaboracao', '').fillna('-')

        cols_ret = ['Solicitação', 'Região', 'Situação', 'Data de Início', 'Nº Manobra', 'Usu. Elaboração']
        return df_res[cols_ret].drop_duplicates()
    except Exception as e:
        print(f"[DB] Erro em get_detalhe_drilldown_performance: {e}")
        return pd.DataFrame(columns=['Solicitação', 'Região', 'Situação', 'Data de Início', 'Nº Manobra', 'Usu. Elaboração'])
    finally:
        if 'conn_app' in locals() and conn_app:
            conn_app.close()
        if 'conn_data' in locals() and conn_data:
            conn_data.close()


def get_solicitacoes_pendentes_conciliacao(limite=50):
    """
    Retorna lista de dicionários com solicitações que saíram da grade ativa
    e ainda aguardam conciliação de status no GDIS-PM.
    """
    conn = get_connection_config()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT solicitacao, sigla_regiao, matricula_responsavel, data_saida
            FROM fila_conciliacao
            WHERE status_apurado IS NULL
            ORDER BY data_saida ASC
            LIMIT ?
        """, (limite,))
        rows = cursor.fetchall()
        return [
            {
                'solicitacao': str(row[0]).strip().lstrip('0'),
                'sigla_regiao': str(row[1]).strip() if row[1] else '',
                'matricula_responsavel': str(row[2]).strip() if row[2] else '',
                'data_saida': row[3]
            }
            for row in rows
        ]
    except Exception as e:
        print(f"[DB] Erro ao buscar pendências de conciliação: {e}")
        return []
    finally:
        if conn:
            conn.close()


def atualizar_status_conciliado(solicitacao, status_apurado, manobra=None, usu_elaboracao=None):
    """
    Atualiza o status real apurado na tela de Consulta do GDIS-PM para uma solicitação
    na fila_conciliacao e reflete o status_detalhado em eventos_diarios.
    """
    conn = get_connection_config()
    try:
        cursor = conn.cursor()
        sol_norm = str(solicitacao).strip().lstrip('0')
        agora = get_agora_br().strftime('%Y-%m-%d %H:%M:%S')
        
        # 1. Atualiza na fila_conciliacao
        cursor.execute("""
            UPDATE fila_conciliacao
            SET status_apurado = ?,
                data_auditoria = ?,
                manobra = COALESCE(?, manobra),
                usu_elaboracao = COALESCE(?, usu_elaboracao)
            WHERE solicitacao = ? OR LTRIM(solicitacao, '0') = ?
        """, (status_apurado, agora, manobra, usu_elaboracao, sol_norm, sol_norm))
        
        # 2. Reflete o status detalhado em eventos_diarios
        cursor.execute("""
            UPDATE eventos_diarios
            SET status_detalhado = ?
            WHERE (solicitacao = ? OR LTRIM(solicitacao, '0') = ?)
              AND tipo_evento = 'TRATADA'
        """, (status_apurado, sol_norm, sol_norm))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"[DB] Erro ao atualizar status conciliado ({solicitacao}): {e}")
        return False
    finally:
        if conn:
            conn.close()




