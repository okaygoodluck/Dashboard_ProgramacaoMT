import sqlite3
import pandas as pd
import db_manager

def run():
    print("Conectando aos bancos...")
    conn_data = sqlite3.connect(db_manager.get_data_db_path())
    
    # Carrega todo o histórico de hoje
    df_hist = pd.read_sql("SELECT * FROM demanda_historico WHERE date(Data_Extracao) = date('now') ORDER BY Data_Extracao", conn_data)
    timestamps = df_hist['Data_Extracao'].unique()
    
    if len(timestamps) < 2:
        print("Poucas extrações hoje para comparar.")
        return
        
    print(f"Encontradas {len(timestamps)} extrações hoje. Reconstruindo eventos...")
    
    # Compara a primeira extração de hoje com a última de ontem (se existir)
    # Mas para simplificar, vamos comparar apenas as de hoje iterativamente
    for i in range(len(timestamps) - 1):
        ts_antigo = timestamps[i]
        ts_novo = timestamps[i+1]
        
        df_antigo = df_hist[df_hist['Data_Extracao'] == ts_antigo].copy()
        df_novo = df_hist[df_hist['Data_Extracao'] == ts_novo].copy()
        
        print(f"[{i+1}/{len(timestamps)-1}] Comparando {ts_antigo} com {ts_novo}...")
        db_manager.registrar_eventos_diarios(df_antigo, df_novo)
        
    print("Concluído!")

if __name__ == '__main__':
    run()
