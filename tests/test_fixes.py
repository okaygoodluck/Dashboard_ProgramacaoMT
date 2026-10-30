import unittest
import sqlite3
import pandas as pd
import os
import sys

sys.path.insert(0, os.path.abspath('.'))
import db_manager

class TestDemandAnalysisFixes(unittest.TestCase):
    
    def test_transition_lookup_and_registration(self):
        """Verifica se registrar_transicao_regiao recupera o histórico e não falha silenciosamente (Isolado em Memória)."""
        from unittest.mock import patch
        
        uri = "file:test_mem_fixes?mode=memory&cache=shared"
        conn = sqlite3.connect(uri, uri=True)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS regioes_responsaveis (
            sigla_regiao TEXT PRIMARY KEY,
            matricula_responsavel TEXT
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS historico_transicao_regioes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_transicao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sigla_regiao TEXT,
            matricula_anterior TEXT,
            nome_anterior TEXT,
            matricula_nova TEXT,
            nome_novo TEXT,
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
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
            matricula TEXT PRIMARY KEY,
            nome TEXT
        )''')
        cursor.execute("INSERT OR REPLACE INTO usuarios VALUES ('c057573', 'KENNEDY VIEIRA GARITO')")
        cursor.execute("INSERT OR REPLACE INTO usuarios VALUES ('c058106', 'LUIZ GUSTAVO CARMO DE ARAUJO')")
        conn.commit()

        def mock_get_conn(read_only=False):
            return sqlite3.connect(uri, uri=True)

        try:
            with patch('db_manager.get_connection_config', side_effect=mock_get_conn):
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
        finally:
            conn.close()

    def test_sanitization_tratadas_ativas(self):
        """Verifica se sanitizar_eventos_tratadas_ativas mantém zero falsos positivos (Isolado em Memória)."""
        from unittest.mock import patch
        
        uri_app = "file:test_mem_san_app?mode=memory&cache=shared"
        uri_data = "file:test_mem_san_data?mode=memory&cache=shared"
        
        conn_app = sqlite3.connect(uri_app, uri=True)
        conn_app.execute("CREATE TABLE eventos_diarios (solicitacao TEXT, tipo_evento TEXT)")
        conn_app.execute("INSERT INTO eventos_diarios VALUES ('123456', 'TRATADA'), ('789012', 'TRATADA')")
        conn_app.commit()
        
        conn_data = sqlite3.connect(uri_data, uri=True)
        conn_data.execute("CREATE TABLE demanda_atual (Solicitacao TEXT)")
        conn_data.execute("INSERT INTO demanda_atual VALUES ('123456')")
        conn_data.commit()
        
        try:
            with patch('db_manager.get_connection_config', side_effect=lambda read_only=False: sqlite3.connect(uri_app, uri=True)), \
                 patch('db_manager.get_connection_read', side_effect=lambda: sqlite3.connect(uri_data, uri=True)), \
                 patch('db_manager.get_app_db_path', return_value="local_test.db"), \
                 patch('db_manager._is_network_path', return_value=False):
                removidos = db_manager.sanitizar_eventos_tratadas_ativas()
                self.assertEqual(removidos, 1)
                
                df_ev = pd.read_sql("SELECT solicitacao FROM eventos_diarios WHERE tipo_evento = 'TRATADA'", conn_app)
                self.assertEqual(df_ev['solicitacao'].tolist(), ['789012'])
        finally:
            conn_app.close()
            conn_data.close()

    def test_db_status_diagnostics(self):
        """Verifica se get_db_status() retorna o diagnóstico completo da base de dados."""
        status = db_manager.get_db_status()
        self.assertIn("is_network", status)
        self.assertIn("data_path", status)
        self.assertIn("app_path", status)
        self.assertIn("rede_base", status)
        self.assertIn("is_server", status)
        self.assertIsInstance(status["is_network"], bool)

    def test_session_persistence_local(self):
        """Verifica se gerar_token_sessao e validar_token_sessao gravam e leem localmente com sucesso."""
        token = db_manager.gerar_token_sessao('c057573')
        self.assertIsNotNone(token)
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 10)
        
        user_info = db_manager.validar_token_sessao(token)
        self.assertIsNotNone(user_info)
        self.assertEqual(user_info[0].lower(), 'c057573')
        
        # Testa remoção de sessão
        db_manager.remover_sessao(token)
        user_info_apos = db_manager.validar_token_sessao(token)
        self.assertIsNone(user_info_apos)

    def test_nova_attribution_and_historical_uniqueness(self):
        """Verifica se NOVA pertence estritamente ao dono da região e se trava de unicidade impede reingresso falso."""
        from unittest.mock import patch
        
        uri_app = "file:test_nova_attr_app?mode=memory&cache=shared"
        conn_app = sqlite3.connect(uri_app, uri=True)
        conn_app.execute("""
            CREATE TABLE eventos_diarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                solicitacao TEXT,
                tipo_evento TEXT,
                regiao TEXT,
                matricula_responsavel TEXT,
                data_evento TIMESTAMP
            )
        """)
        conn_app.execute("CREATE TABLE solicitacoes_travadas (solicitacao TEXT, matricula TEXT)")
        conn_app.execute("CREATE TABLE regioes_responsaveis (sigla_regiao TEXT PRIMARY KEY, matricula_responsavel TEXT)")
        # CL pertence a e270047
        conn_app.execute("INSERT INTO regioes_responsaveis VALUES ('CL', 'e270047')")
        # Solicitação 999999 já nasceu em 2026-10-14
        conn_app.execute("INSERT INTO eventos_diarios (solicitacao, tipo_evento, regiao, matricula_responsavel, data_evento) VALUES ('999999', 'NOVA', 'CL', 'e270047', '2026-10-14 10:00:00')")
        conn_app.commit()

        try:
            with patch('db_manager.get_connection_config', side_effect=lambda read_only=False: sqlite3.connect(uri_app, uri=True)), \
                 patch('db_manager.get_agora_br', return_value=pd.to_datetime('2026-10-27 10:00:00')):
                
                df_antigo = pd.DataFrame([
                    {'Solicitação': '111111', 'Ref_Regiao': 'CL', 'Situação': 'APROVADA', 'Resp. Manobra': '-'}
                ])
                # df_novo traz uma nova real (222222 com Resp. Manobra = c060795) e uma repetida histórica (999999)
                df_novo = pd.DataFrame([
                    {'Solicitação': '111111', 'Ref_Regiao': 'CL', 'Situação': 'APROVADA', 'Resp. Manobra': '-'},
                    {'Solicitação': '222222', 'Ref_Regiao': 'CL', 'Situação': 'APROVADA', 'Resp. Manobra': 'c060795'},
                    {'Solicitação': '999999', 'Ref_Regiao': 'CL', 'Situação': 'APROVADA', 'Resp. Manobra': 'c060795'}
                ])

                db_manager.registrar_eventos_diarios(df_antigo, df_novo)

                # Verifica eventos gerados
                df_res = pd.read_sql("SELECT solicitacao, tipo_evento, matricula_responsavel FROM eventos_diarios WHERE date(data_evento) = '2026-10-27'", conn_app)
                
                # 222222 deve ser inserida como NOVA para o dono da região (e270047), NUNCA para c060795
                self.assertEqual(len(df_res), 1)
                self.assertEqual(df_res['solicitacao'].iloc[0], '222222')
                self.assertEqual(df_res['matricula_responsavel'].iloc[0], 'e270047')

                # 999999 NÃO deve ser reinserida como NOVA
                self.assertNotIn('999999', df_res['solicitacao'].tolist())
        finally:
            conn_app.close()

    def test_blindar_titularidade_historica_novas(self):
        """Testa se a blindagem histórica realinha NOVAs ocorridas antes da transição de região."""
        import sqlite3
        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE historico_transicao_regioes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sigla_regiao TEXT,
                matricula_anterior TEXT,
                matricula_nova TEXT,
                data_transicao TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE regioes_responsaveis (
                sigla_regiao TEXT PRIMARY KEY,
                matricula_responsavel TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE eventos_diarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                solicitacao TEXT,
                tipo_evento TEXT,
                regiao TEXT,
                matricula_responsavel TEXT,
                data_evento TIMESTAMP
            )
        """)
        # Transição: Região SL passou de c059565 para e248824 em 2026-10-24 10:00:00
        cur.execute("INSERT INTO historico_transicao_regioes (sigla_regiao, matricula_anterior, matricula_nova, data_transicao) VALUES ('SL', 'c059565', 'e248824', '2026-10-24 10:00:00')")
        cur.execute("INSERT INTO regioes_responsaveis VALUES ('SL', 'e248824')")
        
        # Evento 1: ocorrido em 20/10 (anterior à transição) mas erroneamente marcado com e248824
        cur.execute("INSERT INTO eventos_diarios (solicitacao, tipo_evento, regiao, matricula_responsavel, data_evento) VALUES ('1001', 'NOVA', 'SL', 'e248824', '2026-10-20 08:30:00')")
        # Evento 2: ocorrido em 25/10 (posterior à transição) legitimamente com e248824
        cur.execute("INSERT INTO eventos_diarios (solicitacao, tipo_evento, regiao, matricula_responsavel, data_evento) VALUES ('1002', 'NOVA', 'SL', 'e248824', '2026-10-25 08:30:00')")
        conn.commit()

        corrigidos = db_manager.blindar_titularidade_historica_novas(cur)
        conn.commit()

        self.assertEqual(corrigidos, 1)

        cur.execute("SELECT solicitacao, matricula_responsavel FROM eventos_diarios ORDER BY solicitacao")
        rows = dict(cur.fetchall())
        self.assertEqual(rows['1001'], 'c059565')
        self.assertEqual(rows['1002'], 'e248824')
        conn.close()

    def test_normalizar_codigo_alimentador(self):
        """Testa normalizacao canonica de alimentadores prevenindo discrepancia de digitos."""
        self.assertEqual(db_manager.normalizar_codigo_alimentador('LAD 005'), 'LAD5')
        self.assertEqual(db_manager.normalizar_codigo_alimentador('LAD 05'), 'LAD5')
        self.assertEqual(db_manager.normalizar_codigo_alimentador('LAD5'), 'LAD5')
        self.assertEqual(db_manager.normalizar_codigo_alimentador('SLAD203'), 'SLAD203')
        self.assertEqual(db_manager.normalizar_codigo_alimentador('BBI 010'), 'BBI10')
        self.assertEqual(db_manager.normalizar_codigo_alimentador('BBI 002'), 'BBI2')
        self.assertEqual(db_manager.normalizar_codigo_alimentador(None), '')

    def test_is_alimentador_restrito(self):
        """Testa verificacao de alimentador em conjunto restrito com resolucao regional."""
        # LAD 005 na regiao JF pertence ao conjunto SND (Santos Dumont), que e RESTRITO
        self.assertTrue(db_manager.is_alimentador_restrito('LAD 005', 'JF - JUIZ DE FORA'))
        self.assertTrue(db_manager.is_alimentador_restrito('LAD 05', 'JF'))
        self.assertTrue(db_manager.is_alimentador_restrito('LAD005', 'JF'))
        self.assertTrue(db_manager.is_alimentador_restrito('LAD 005', None))
        # Alimentador nao restrito
        self.assertFalse(db_manager.is_alimentador_restrito('SLAD203', 'SL'))
        self.assertFalse(db_manager.is_alimentador_restrito(None, 'JF'))

if __name__ == '__main__':
    unittest.main()

