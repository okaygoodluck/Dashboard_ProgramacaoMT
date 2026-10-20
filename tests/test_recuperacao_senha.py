import unittest
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath('.'))
import db_manager

class TestRecuperacaoSenha(unittest.TestCase):

    def setUp(self):
        db_manager.init_tabela_recuperacao()
        conn = db_manager.get_connection_config()
        cursor = conn.cursor()
        # Garante usuário de teste
        cursor.execute("DELETE FROM usuarios WHERE matricula = 'c999999'")
        cursor.execute("DELETE FROM recuperacao_senhas WHERE matricula = 'c999999'")
        cursor.execute("""
            INSERT INTO usuarios (matricula, nome, password_hash, nivel, senha_provisoria, email)
            VALUES ('c999999', 'TESTE AUTOMATIZADO', 'dummy_hash', 'Usuario', 0, 'teste.auto@cemig.com.br')
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        conn = db_manager.get_connection_config()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM usuarios WHERE matricula = 'c999999'")
        cursor.execute("DELETE FROM recuperacao_senhas WHERE matricula = 'c999999'")
        conn.commit()
        conn.close()

    def test_solicitar_codigo_usuario_inexistente(self):
        """Verifica se rejeita solicitação para matrícula que não existe."""
        ok, msg, mask = db_manager.solicitar_codigo_recuperacao('c000nonexistent')
        self.assertFalse(ok)
        self.assertIn("não encontrada", msg)
        self.assertIsNone(mask)

    def test_solicitar_codigo_usuario_sem_email_ou_desligado(self):
        """Verifica se rejeita usuário sem e-mail ou marcado como DESLIGADO."""
        conn = db_manager.get_connection_config()
        conn.execute("UPDATE usuarios SET email = 'DESLIGADO' WHERE matricula = 'c999999'")
        conn.commit()
        conn.close()

        ok, msg, mask = db_manager.solicitar_codigo_recuperacao('c999999')
        self.assertFalse(ok)
        self.assertIn("não possui e-mail cadastrado ou está inativo", msg)

    def test_validar_e_redefinir_senha_fluxo_completo(self):
        """Testa o fluxo de validação de PIN de 6 dígitos, expiração, tentativas e alteração de senha."""
        conn = db_manager.get_connection_config()
        cursor = conn.cursor()
        
        # Insere código ativo para c999999
        expira_futuro = datetime.now() + timedelta(minutes=10)
        cursor.execute("""
            INSERT INTO recuperacao_senhas (matricula, codigo, expira_em, tentativas, usado)
            VALUES ('c999999', '654321', ?, 0, 0)
        """, (expira_futuro.strftime('%Y-%m-%d %H:%M:%S'),))
        conn.commit()
        conn.close()

        # 1. Validação de senha curta (< 4 caracteres)
        ok, msg = db_manager.validar_e_redefinir_senha_recuperacao('c999999', '654321', '123')
        self.assertFalse(ok)
        self.assertIn("pelo menos 4 caracteres", msg)

        # 2. Código errado (1ª tentativa)
        ok, msg = db_manager.validar_e_redefinir_senha_recuperacao('c999999', '000000', 'NovaSenha123')
        self.assertFalse(ok)
        self.assertIn("Código incorreto", msg)

        # 3. Código correto com sucesso
        ok, msg = db_manager.validar_e_redefinir_senha_recuperacao('c999999', '654321', 'NovaSenha123')
        self.assertTrue(ok)
        self.assertIn("sucesso", msg.lower())

        # 4. Verifica se o código foi marcado como usado
        conn = db_manager.get_connection_config_read()
        cur = conn.cursor()
        cur.execute("SELECT usado FROM recuperacao_senhas WHERE matricula = 'c999999'")
        usado_status = cur.fetchone()[0]
        conn.close()
        self.assertEqual(usado_status, 1)

        # 5. Tentativa de reusar o mesmo código após já utilizado
        ok_reuso, msg_reuso = db_manager.validar_e_redefinir_senha_recuperacao('c999999', '654321', 'OutraSenha123')
        self.assertFalse(ok_reuso)
        self.assertIn("Nenhuma solicitação de recuperação ativa", msg_reuso)

    def test_codigo_expirado_bloqueado(self):
        """Verifica se códigos com mais de 10 minutos são rejeitados."""
        conn = db_manager.get_connection_config()
        cursor = conn.cursor()
        expira_passado = datetime.now() - timedelta(minutes=5)
        cursor.execute("""
            INSERT INTO recuperacao_senhas (matricula, codigo, expira_em, tentativas, usado)
            VALUES ('c999999', '999888', ?, 0, 0)
        """, (expira_passado.strftime('%Y-%m-%d %H:%M:%S'),))
        conn.commit()
        conn.close()

        ok, msg = db_manager.validar_e_redefinir_senha_recuperacao('c999999', '999888', 'NovaSenha123')
        self.assertFalse(ok)
        self.assertIn("expirou", msg.lower())

    def test_atualizar_email_usuario(self):
        """Verifica se atualizar_email_usuario altera o e-mail no banco e reflete em listar_usuarios."""
        ok = db_manager.atualizar_email_usuario('c999999', 'novo.email@cemig.com.br')
        self.assertTrue(ok)

        df_users = db_manager.listar_usuarios()
        user_row = df_users[df_users['matricula'] == 'c999999']
        self.assertFalse(user_row.empty)
        self.assertEqual(user_row.iloc[0]['email'], 'novo.email@cemig.com.br')
    def test_verificar_se_codigo_recuperacao(self):
        """Verifica se identifica corretamente quando o código de 6 dígitos é ativo e rejeita quando expirado/inválido."""
        conn = db_manager.get_connection_config()
        expira_futuro = datetime.now() + timedelta(minutes=10)
        conn.execute("""
            INSERT INTO recuperacao_senhas (matricula, codigo, expira_em, tentativas, usado)
            VALUES ('c999999', '112233', ?, 0, 0)
        """, (expira_futuro.strftime('%Y-%m-%d %H:%M:%S'),))
        conn.commit()
        conn.close()

        # Código correto e ativo
        self.assertTrue(db_manager.verificar_se_codigo_recuperacao('c999999', '112233'))
        # Código errado
        self.assertFalse(db_manager.verificar_se_codigo_recuperacao('c999999', '999999'))
        # Matrícula errada
        self.assertFalse(db_manager.verificar_se_codigo_recuperacao('c000000', '112233'))
        # Não numérico ou tamanho diferente
        self.assertFalse(db_manager.verificar_se_codigo_recuperacao('c999999', 'abc'))

if __name__ == '__main__':
    unittest.main()

