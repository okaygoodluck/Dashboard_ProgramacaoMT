import sqlite3
import unittest
import pandas as pd
import db_manager


class TestAuditorStatus(unittest.TestCase):
    def setUp(self):
        # Conexão de criação usando memória compartilhada
        self.db_uri = "file:auditor_test_db?mode=memory&cache=shared"
        self.creator_conn = sqlite3.connect(self.db_uri, uri=True)
        self.creator_conn.row_factory = sqlite3.Row
        
        # Cria tabelas necessárias
        self.creator_conn.execute("""
            CREATE TABLE usuarios (
                matricula TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                nivel TEXT NOT NULL,
                senha_provisoria INTEGER DEFAULT 1,
                email TEXT
            )
        """)
        self.creator_conn.execute("""
            CREATE TABLE eventos_diarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                solicitacao TEXT NOT NULL,
                tipo_evento TEXT NOT NULL,
                regiao TEXT,
                matricula_responsavel TEXT,
                data_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status_detalhado TEXT
            )
        """)
        self.creator_conn.execute("""
            CREATE TABLE fila_conciliacao (
                solicitacao TEXT PRIMARY KEY,
                sigla_regiao TEXT,
                matricula_responsavel TEXT,
                data_saida TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status_apurado TEXT,
                data_auditoria TIMESTAMP,
                manobra TEXT,
                usu_elaboracao TEXT
            )
        """)
        self.creator_conn.execute("""
            CREATE TABLE pendentes_snapshot (
                data TEXT,
                matricula TEXT,
                pendentes_total INTEGER,
                pendentes_iniciadas INTEGER,
                pendentes_nao_iniciadas INTEGER,
                pendentes_iniciadas_dia INTEGER,
                pendentes_dias_anteriores INTEGER,
                PRIMARY KEY (data, matricula)
            )
        """)
        self.creator_conn.commit()

    def tearDown(self):
        self.creator_conn.close()

    def test_atualizar_status_conciliado_e_refletir_em_eventos(self):
        # Insere evento prévio de TRATADA e pendência na fila_conciliacao
        self.creator_conn.execute("""
            INSERT INTO eventos_diarios (solicitacao, tipo_evento, regiao, matricula_responsavel, data_evento)
            VALUES ('123456', 'TRATADA', 'PN', 'c012345', '2026-10-26 10:00:00')
        """)
        self.creator_conn.execute("""
            INSERT INTO fila_conciliacao (solicitacao, sigla_regiao, matricula_responsavel, data_saida)
            VALUES ('123456', 'PN', 'c012345', '2026-10-26 10:00:00')
        """)
        self.creator_conn.commit()

        # Mock da fábrica de conexões
        orig_conn = db_manager.get_connection_config
        db_manager.get_connection_config = lambda *args, **kwargs: sqlite3.connect(self.db_uri, uri=True)
        try:
            # Verifica pendência
            pendentes = db_manager.get_solicitacoes_pendentes_conciliacao(limite=10)
            self.assertEqual(len(pendentes), 1)
            self.assertEqual(pendentes[0]['solicitacao'], '123456')

            # Atualiza para ELABORADA
            sucesso = db_manager.atualizar_status_conciliado(
                solicitacao='123456',
                status_apurado='ELABORADA',
                manobra='98765',
                usu_elaboracao='c012345'
            )
            self.assertTrue(sucesso)

            # Verifica fila_conciliacao atualizada
            cur = self.creator_conn.cursor()
            cur.execute("SELECT status_apurado, manobra, usu_elaboracao FROM fila_conciliacao WHERE solicitacao = '123456'")
            row = cur.fetchone()
            self.assertEqual(row['status_apurado'], 'ELABORADA')
            self.assertEqual(row['manobra'], '98765')
            self.assertEqual(row['usu_elaboracao'], 'c012345')

            # Verifica eventos_diarios refletindo o status_detalhado
            cur.execute("SELECT status_detalhado FROM eventos_diarios WHERE solicitacao = '123456'")
            ev_row = cur.fetchone()
            self.assertEqual(ev_row['status_detalhado'], 'ELABORADA')

            # Verifica que ELABORADA é intermediário e CONTINUA na fila para re-auditoria periódica
            pendentes_pos = db_manager.get_solicitacoes_pendentes_conciliacao(limite=10)
            self.assertEqual(len(pendentes_pos), 1)
            self.assertEqual(pendentes_pos[0]['solicitacao'], '123456')

            # Agora atualiza para ENVIADA PARA O CONDIS (status terminal)
            db_manager.atualizar_status_conciliado(
                solicitacao='123456',
                status_apurado='ENVIADA PARA O CONDIS'
            )
            # Verifica que agora que atingiu status terminal, encerra o ciclo de auditoria
            pendentes_terminal = db_manager.get_solicitacoes_pendentes_conciliacao(limite=10)
            self.assertEqual(len(pendentes_terminal), 0)

        finally:
            db_manager.get_connection_config = orig_conn

    def test_gargalos_pos_elaboracao(self):
        # Insere usuário
        self.creator_conn.execute("""
            INSERT INTO usuarios (matricula, nome, password_hash, nivel)
            VALUES ('c099999', 'Programador Teste', 'hash123', 'USER')
        """)
        # Insere itens na fila_conciliacao: 1 aguardando 1ª auditoria, 1 elaborada (>24h), 1 terminal CONDIS
        self.creator_conn.execute("""
            INSERT INTO fila_conciliacao (solicitacao, sigla_regiao, matricula_responsavel, data_saida, status_apurado, manobra, usu_elaboracao)
            VALUES 
                ('SOL_INTER_1', 'PN', 'c099999', datetime('now', '-30 hours'), 'ELABORADA', 'MN-900', 'c099999'),
                ('SOL_INTER_2', 'PN', 'c099999', datetime('now', '-5 hours'), NULL, NULL, NULL),
                ('SOL_TERM_3', 'PN', 'c099999', datetime('now', '-50 hours'), 'ENVIADA PARA O CONDIS', 'MN-901', 'c099999')
        """)
        self.creator_conn.commit()

        orig_conn = db_manager.get_connection_config
        db_manager.get_connection_config = lambda *args, **kwargs: sqlite3.connect(self.db_uri, uri=True)
        try:
            df_gargalos = db_manager.get_gargalos_pos_elaboracao()
            self.assertEqual(len(df_gargalos), 2)
            sols = df_gargalos['Solicitação'].tolist()
            self.assertIn('SOL_INTER_1', sols)
            self.assertIn('SOL_INTER_2', sols)
            self.assertNotIn('SOL_TERM_3', sols)

            row_inter1 = df_gargalos[df_gargalos['Solicitação'] == 'SOL_INTER_1'].iloc[0]
            self.assertIn('Alerta (> 24h)', row_inter1['Alerta'])
            self.assertEqual(row_inter1['Status Atual'], 'ELABORADA')

            row_inter2 = df_gargalos[df_gargalos['Solicitação'] == 'SOL_INTER_2'].iloc[0]
            self.assertIn('Normal (<= 24h)', row_inter2['Alerta'])
            self.assertEqual(row_inter2['Status Atual'], 'Aguardando 1ª Auditoria')
        finally:
            db_manager.get_connection_config = orig_conn

    def test_performance_d1_e_drilldown_marco_zero(self):
        # 1. Configura usuário
        self.creator_conn.execute("""
            INSERT INTO usuarios (matricula, nome, password_hash, nivel)
            VALUES ('c012345', 'Tecnico Teste', 'hash123', 'USER')
        """)
        # 2. Configura eventos do dia 26/10/2026
        self.creator_conn.execute("""
            INSERT INTO eventos_diarios (solicitacao, tipo_evento, regiao, matricula_responsavel, data_evento, status_detalhado)
            VALUES 
                ('SOL_1', 'NOVA', 'PN', 'c012345', '2026-10-26 08:00:00', NULL),
                ('SOL_2', 'TRATADA', 'PN', 'c012345', '2026-10-26 09:00:00', 'ELABORADA'),
                ('SOL_3', 'TRATADA', 'PN', 'c012345', '2026-10-26 10:00:00', 'REPROVADA'),
                ('SOL_4', 'TRATADA', 'PN', 'c012345', '2026-10-26 11:00:00', NULL),
                ('SOL_5', 'TRATADA', 'PN', 'c012345', '2026-10-26 12:00:00', 'ENVIADA PARA O CONDIS')
        """)
        self.creator_conn.execute("""
            INSERT INTO fila_conciliacao (solicitacao, sigla_regiao, matricula_responsavel, data_saida, status_apurado, manobra, usu_elaboracao)
            VALUES 
                ('SOL_2', 'PN', 'c012345', '2026-10-26 09:00:00', 'ELABORADA', 'MN-101', 'c012345'),
                ('SOL_3', 'PN', 'c012345', '2026-10-26 10:00:00', 'REPROVADA', 'MN-102', 'c012345'),
                ('SOL_5', 'PN', 'c012345', '2026-10-26 12:00:00', 'ENVIADA PARA O CONDIS', 'MN-103', 'c012345')
        """)
        self.creator_conn.commit()

        orig_conn = db_manager.get_connection_config
        orig_read = db_manager.get_connection_read
        db_manager.get_connection_config = lambda *args, **kwargs: sqlite3.connect(self.db_uri, uri=True)
        db_manager.get_connection_read = lambda *args, **kwargs: sqlite3.connect(self.db_uri, uri=True)
        try:
            # Testa get_performance_d1 com separação entre CONDIS e Elaboradas
            df_perf = db_manager.get_performance_d1('Tecnico Teste', '2026-10-26', '2026-10-26')
            self.assertFalse(df_perf.empty)
            row = df_perf.iloc[0]
            self.assertEqual(row['Novas'], 1)
            self.assertEqual(row['Tratadas'], 4)
            self.assertEqual(row['Enviadas_Condis'], 1)
            self.assertEqual(row['Elaboradas'], 1)
            self.assertEqual(row['Reprovadas'], 1)
            self.assertEqual(row['Pendentes_Conciliacao'], 1)

            # Testa get_detalhe_drilldown_performance para CONDIS
            df_drill_condis = db_manager.get_detalhe_drilldown_performance('Tecnico Teste', '26/10/2026', 'Enviadas ao CONDIS (ou Legado)')
            self.assertEqual(len(df_drill_condis), 1)
            self.assertEqual(df_drill_condis['Situação'].iloc[0], 'ENVIADA PARA O CONDIS')

            # Testa get_detalhe_drilldown_performance para Elaboradas
            df_drill_elab = db_manager.get_detalhe_drilldown_performance('Tecnico Teste', '26/10/2026', 'Elaboradas (Aguardando CONDIS)')
            self.assertEqual(len(df_drill_elab), 1)
            self.assertEqual(df_drill_elab['Situação'].iloc[0], 'ELABORADA')

            # Testa get_detalhe_drilldown_performance para Reprovadas
            df_drill_rep = db_manager.get_detalhe_drilldown_performance('Tecnico Teste', '26/10/2026', 'Reprovadas / Canceladas')
            self.assertEqual(len(df_drill_rep), 1)
            self.assertEqual(df_drill_rep['Situação'].iloc[0], 'REPROVADA')

        finally:
            db_manager.get_connection_config = orig_conn
            db_manager.get_connection_read = orig_read


if __name__ == '__main__':
    unittest.main()
