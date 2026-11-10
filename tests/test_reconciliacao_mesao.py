import unittest
import sqlite3
import pandas as pd
import os
import tempfile
from unittest.mock import patch
import sys

# Adiciona o caminho raiz ao sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import db_manager

class TestReconciliacaoMesao(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_app_path = os.path.join(self.temp_dir.name, 'test_app.db')
        
        # Cria banco ccp_app em arquivo temporário
        conn = sqlite3.connect(self.db_app_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE usuarios (
                matricula TEXT PRIMARY KEY,
                nome TEXT,
                email TEXT
            )
        """)
        cur.execute("INSERT INTO usuarios VALUES ('e213727', 'PABLIANE GONCALVES MALHEIROS', 'pabliane@cemig.com.br')")
        cur.execute("INSERT INTO usuarios VALUES ('e248824', 'KASSIUS ALVES FARGNOLI', 'kassius@cemig.com.br')")
        
        cur.execute("""
            CREATE TABLE eventos_diarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                solicitacao TEXT,
                tipo_evento TEXT,
                regiao TEXT,
                matricula_responsavel TEXT,
                data_evento TIMESTAMP,
                status_detalhado TEXT
            )
        """)
        
        cur.execute("""
            CREATE TABLE fila_conciliacao (
                solicitacao TEXT PRIMARY KEY,
                sigla_regiao TEXT,
                matricula_responsavel TEXT,
                data_saida TIMESTAMP,
                status_apurado TEXT,
                data_auditoria TIMESTAMP
            )
        """)
        
        # Insere um evento existente sem status (caso de 1718322)
        cur.execute("""
            INSERT INTO eventos_diarios (solicitacao, tipo_evento, regiao, matricula_responsavel, data_evento, status_detalhado)
            VALUES ('1718322', 'TRATADA', 'BC', 'e213727', '2026-11-09 15:16:50', NULL)
        """)
        conn.commit()
        conn.close()

        # Cria duas planilhas mock do Mesão: Mesao_09_11_26.xlsx e Mesao_10_11_26.xlsx
        self.mesao_dir = os.path.join(self.temp_dir.name, 'Mesao_Diario')
        os.makedirs(self.mesao_dir, exist_ok=True)
        
        # Mesao 09/11: 1718322 Aprovada, 1713430 Aprovada
        df_m09 = pd.DataFrame([
            {'Solicitação': '1718322', 'Status Solicitação': 'APROVADA', 'Região': 'BC', 'Último Reprovador da Solicitação': None},
            {'Solicitação': '1713430', 'Status Solicitação': 'APROVADA', 'Região': 'LV', 'Último Reprovador da Solicitação': None},
        ])
        df_m09.to_excel(os.path.join(self.mesao_dir, 'Mesao_09_11_26.xlsx'), index=False)
        
        # Mesao 10/11: 1718322 REPROVADA por Pabliane, 1713430 REPROVADA por Pabliane, 1725084 REPROVADA por Kassius
        df_m10 = pd.DataFrame([
            {'Solicitação': '1718322', 'Status Solicitação': 'REPROVADA', 'Região': 'BC', 'Último Reprovador da Solicitação': 'PABLIANE GONCALVES MALHEIROS'},
            {'Solicitação': '1713430', 'Status Solicitação': 'REPROVADA', 'Região': 'LV', 'Último Reprovador da Solicitação': 'PABLIANE GONCALVES MALHEIROS'},
            {'Solicitação': '1725084', 'Status Solicitação': 'REPROVADA', 'Região': 'JF', 'Último Reprovador da Solicitação': 'KASSIUS ALVES FARGNOLI'},
        ])
        df_m10.to_excel(os.path.join(self.mesao_dir, 'Mesao_10_11_26.xlsx'), index=False)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_reconciliacao_mesao_diario_execucao_e_idempotencia(self):
        """Valida que a reconciliação insere eventos faltantes, atualiza eventos sem status e é idempotente."""
        def mock_get_conn_config(*args, **kwargs):
            return sqlite3.connect(self.db_app_path)
            
        with patch('db_manager.get_connection_config', side_effect=mock_get_conn_config), \
             patch('db_manager.get_connection_write', side_effect=mock_get_conn_config):
             
            # Primeira execução
            res1 = db_manager.reconciliar_reprovas_mesao_diario(pasta_mesao=self.mesao_dir, dias_analise=2)
            self.assertEqual(res1['status'], 'sucesso')
            self.assertEqual(res1['eventos_atualizados'], 1)  # 1718322 teve status atualizado
            self.assertEqual(res1['eventos_inseridos'], 2)    # 1713430 e 1725084 foram criadas
            
            # Validações no banco
            conn = sqlite3.connect(self.db_app_path)
            cur = conn.cursor()
            
            # 1. Solicitação 1718322 agora tem status_detalhado = 'REPROVADA'
            cur.execute("SELECT status_detalhado, matricula_responsavel FROM eventos_diarios WHERE solicitacao = '1718322'")
            row_1718322 = cur.fetchone()
            self.assertEqual(row_1718322[0], 'REPROVADA')
            self.assertEqual(row_1718322[1], 'e213727')
            
            # 2. Solicitação 1713430 foi inserida como TRATADA / REPROVADA para Pabliane (e213727)
            cur.execute("SELECT status_detalhado, matricula_responsavel, regiao FROM eventos_diarios WHERE solicitacao = '1713430'")
            row_1713430 = cur.fetchone()
            self.assertIsNotNone(row_1713430)
            self.assertEqual(row_1713430[0], 'REPROVADA')
            self.assertEqual(row_1713430[1], 'e213727')
            self.assertEqual(row_1713430[2], 'LV')
            
            # 3. Solicitação 1725084 foi inserida para Kassius (e248824)
            cur.execute("SELECT status_detalhado, matricula_responsavel, regiao FROM eventos_diarios WHERE solicitacao = '1725084'")
            row_1725084 = cur.fetchone()
            self.assertIsNotNone(row_1725084)
            self.assertEqual(row_1725084[0], 'REPROVADA')
            self.assertEqual(row_1725084[1], 'e248824')
            self.assertEqual(row_1725084[2], 'JF')

            # 4. Validação de IDEMPOTÊNCIA: rodar uma segunda vez não deve duplicar registros nem falhar
            res2 = db_manager.reconciliar_reprovas_mesao_diario(pasta_mesao=self.mesao_dir, dias_analise=2)
            self.assertEqual(res2['status'], 'sucesso')
            self.assertEqual(res2['eventos_inseridos'], 0) # Nenhuma nova inserida
            
            # Confirma que continuam existindo exatamente 3 eventos no total
            cur.execute("SELECT count(*) FROM eventos_diarios")
            self.assertEqual(cur.fetchone()[0], 3)
            
            conn.close()

if __name__ == '__main__':
    unittest.main()
