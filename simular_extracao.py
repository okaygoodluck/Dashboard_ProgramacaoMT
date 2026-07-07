import sqlite3
import pandas as pd
import db_manager
import random

print("=== SIMULADOR DE EXTRAÇÃO (TESTE DE EVENTOS) ===")
print(f"Bancos configurados: APP={db_manager.get_app_db_path()}, LOCAL={db_manager.LOCAL_DB_NAME}")

try:
    # 1. Lê a última demanda salva no banco local
    conn = db_manager.get_connection_write()
    df = pd.read_sql("SELECT * FROM demanda_atual", conn)
    conn.close()

    if df.empty:
        print("Erro: O banco de testes está vazio.")
        exit(1)

    # 2. Escolhe 2 solicitações aleatórias que estão "Aprovada"
    aprovadas = df[df['Situação'].str.contains('APROVADA', na=False, case=False)]
    
    if aprovadas.empty:
        print("Aviso: Não há solicitações 'Aprovada' para simular o início. Pegando qualquer uma.")
        candidatos = df.index.tolist()
    else:
        candidatos = aprovadas.index.tolist()
        
    escolhidos = random.sample(candidatos, min(2, len(candidatos)))
    
    solicitacoes_afetadas = []
    
    for idx in escolhidos:
        sol_id = df.at[idx, 'Solicitação']
        solicitacoes_afetadas.append(sol_id)
        # Muda o status para "Em elaboração"
        df.at[idx, 'Situação'] = "Em elaboração"
        print(f"[*] Simulando início de tratamento na solicitação: {sol_id}")

    # 3. Invoca o db_manager para salvar (Isso disparará os eventos no ccp_app_TESTE.db)
    print("Invocando db_manager.salvar_dados()...")
    db_manager.salvar_dados(df)
    
    print("\nSimulação concluída com sucesso!")
    print("O motor de eventos do db_manager já deve ter gravado as mudanças.")
    
except Exception as e:
    print(f"Erro no simulador: {e}")
