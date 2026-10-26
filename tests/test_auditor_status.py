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
        db_manager.get_connection_config = lambda: sqlite3.connect(self.db_uri, uri=True)
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

            # Verifica que não está mais pendente
            pendentes_pos = db_manager.get_solicitacoes_pendentes_conciliacao(limite=10)
            self.assertEqual(len(pendentes_pos), 0)

        finally:
            db_manager.get_connection_config = orig_conn


if __name__ == '__main__':
    unittest.main()
