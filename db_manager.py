import sqlite3
import pandas as pd
import datetime
import os

DB_NAME = "demanda.db"

def get_connection():
    """Retorna uma conexão com o banco de dados SQLite."""
    conn = sqlite3.connect(DB_NAME)
    return conn

def salvar_dados(df):
    """
    Salva os dados no banco de dados.
    1. Tabela 'demanda_atual': Substitui todo o conteúdo (Snapshot do momento).
    2. Tabela 'demanda_historico': Adiciona os novos dados com timestamp (Histórico).
    """
    if df is None or df.empty:
        print("Nenhum dado para salvar no banco.")
        return

    conn = get_connection()
    try:
        # Adiciona data de extração para o histórico
        timestamp = datetime.datetime.now()
        df['Data_Extracao'] = timestamp

        # 1. Salva Snapshot Atual (Replace)
        # Remove a coluna de Data_Extracao para o snapshot atual se quiser manter limpo, 
        # mas pode ser útil saber quando foi extraído. Vamos manter.
        df.to_sql('demanda_atual', conn, if_exists='replace', index=False)
        print(f"[DB] Snapshot atualizado na tabela 'demanda_atual'. ({len(df)} registros)")

        # 2. Salva Histórico (Append)
        # Idealmente, deveríamos verificar duplicatas para não inflar o banco,
        # mas como não temos ID único garantido, vamos apenas fazer append por enquanto.
        # Numa V2, podemos criar um hash da linha para evitar duplicatas exatas.
        df.to_sql('demanda_historico', conn, if_exists='append', index=False)
        print(f"[DB] Dados adicionados ao histórico na tabela 'demanda_historico'.")

    except Exception as e:
        print(f"[DB] Erro ao salvar dados: {e}")
    finally:
        conn.close()

def carregar_dados_recentes():
    """Carrega os dados da tabela 'demanda_atual'."""
    conn = get_connection()
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
    conn = get_connection()
    try:
        df = pd.read_sql("SELECT * FROM demanda_historico", conn)
        return df
    except Exception as e:
        return None
    finally:
        conn.close()
