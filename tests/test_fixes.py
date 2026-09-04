import unittest
import sqlite3
import pandas as pd
import os
import sys

sys.path.insert(0, os.path.abspath('.'))
import db_manager

class TestDemandAnalysisFixes(unittest.TestCase):
    
    def test_transition_lookup_and_registration(self):
        """Verifica se registrar_transicao_regiao recupera o histórico e não falha silenciosamente."""
        conn = db_manager.get_connection_config()
        cursor = conn.cursor()
        
        # Cria uma transição de teste para uma sigla fictícia 'TX'
        cursor.execute("DELETE FROM historico_transicao_regioes WHERE sigla_regiao = 'TX'")
        cursor.execute("DELETE FROM regioes_responsaveis WHERE sigla_regiao = 'TX'")
        conn.commit()
        
        # 1. Transição inicial a partir de Não Atribuído
        db_manager.registrar_transicao_regiao('TX', 'c057573')
        
        cursor.execute("SELECT matricula_anterior, nome_anterior, matricula_nova, total_pendentes FROM historico_transicao_regioes WHERE sigla_regiao = 'TX' ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        self.assertIsNotNone(row, "Transição para TX não foi registrada!")
        self.assertEqual(row[0], "SEM_RESPONSAVEL")
        self.assertEqual(row[1], "Não Atribuído")
        self.assertEqual(row[2], "c057573")
        
        # 2. Agora simula desassociação da região (ficou sem registro em regioes_responsaveis)
        # e novo técnico assume 'TX'
        db_manager.registrar_transicao_regiao('TX', 'c058106')
        
        cursor.execute("SELECT matricula_anterior, matricula_nova FROM historico_transicao_regioes WHERE sigla_regiao = 'TX' ORDER BY id DESC LIMIT 1")
        row2 = cursor.fetchone()
        self.assertIsNotNone(row2)
        # Deve ter recuperado 'c057573' do histórico como responsável anterior!
        self.assertEqual(row2[0], "c057573")
        self.assertEqual(row2[1], "c058106")
        
        # Limpa dados de teste
        cursor.execute("DELETE FROM historico_transicao_regioes WHERE sigla_regiao = 'TX'")
        conn.commit()
        conn.close()

    def test_sanitization_tratadas_ativas(self):
        """Verifica se sanitizar_eventos_tratadas_ativas mantém zero falsos positivos."""
        removidos = db_manager.sanitizar_eventos_tratadas_ativas()
        self.assertIsInstance(removidos, int)
        
        # Verifica que nenhuma tratada restante está em demanda_atual
        conn_app = db_manager.get_connection_config()
        conn_data = db_manager.get_connection_read()
        
        df_cur = pd.read_sql("SELECT * FROM demanda_atual", conn_data)
        sol_col = next((c for c in df_cur.columns if 'solicita' in c.lower() and 'vinc' not in c.lower()), None)
        sols_cur = set(df_cur[sol_col].astype(str).str.strip().str.lstrip('0'))
        
        df_ev = pd.read_sql("SELECT solicitacao FROM eventos_diarios WHERE tipo_evento = 'TRATADA'", conn_app)
        sols_ev = set(df_ev['solicitacao'].astype(str).str.strip().str.lstrip('0'))
        
        conflitos = sols_cur.intersection(sols_ev)
        self.assertEqual(len(conflitos), 0, f"Ainda existem {len(conflitos)} solicitações ativas marcadas como TRATADA!")
        
        conn_app.close()
        conn_data.close()

if __name__ == '__main__':
    unittest.main()
