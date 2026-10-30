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
    def test_nivel_subgerencial(self):
        """Verifica se o perfil SubGerencial é gravado e alterado corretamente no banco."""
        ok_alt = db_manager.alterar_nivel_usuario('c999999', 'SubGerencial')
        self.assertTrue(ok_alt)

        df_users = db_manager.listar_usuarios()
        row = df_users[df_users['matricula'] == 'c999999']
        self.assertFalse(row.empty)
        self.assertEqual(row.iloc[0]['nivel'], 'SubGerencial')

        # Testar login retornando o nível SubGerencial
        user_data = db_manager.verificar_login('c999999', '12345') # dummy_hash no setup não bate com 12345, mas validar_token_sessao sim
        tok = db_manager.gerar_token_sessao('c999999')
        if tok:
            sess_data = db_manager.validar_token_sessao(tok)
            self.assertIsNotNone(sess_data)
            self.assertEqual(sess_data[2], 'SubGerencial')
            db_manager.remover_sessao(tok)

    def test_validar_desafio_cadastral_e_redefinir_senha(self):
        """Testa o fluxo de redefinicao direta por desafio cadastral para Home Office."""
        # 1. Sucesso com matricula e e-mail correspondentes
        ok, msg = db_manager.validar_desafio_cadastral_e_redefinir_senha(
            'c999999', 'teste.auto@cemig.com.br', 'SenhaNovaHome123'
        )
        self.assertTrue(ok)
        self.assertIn("sucesso", msg.lower())

        # Verifica se a nova senha funciona no login
        user_info = db_manager.verificar_login('c999999', 'SenhaNovaHome123')
        self.assertIsNotNone(user_info)

        # 2. E-mail errado
        ok, msg = db_manager.validar_desafio_cadastral_e_redefinir_senha(
            'c999999', 'email.errado@cemig.com.br', 'OutraSenha123'
        )
        self.assertFalse(ok)
        self.assertIn("não confere", msg.lower())

        # 3. Matricula inexistente
        ok, msg = db_manager.validar_desafio_cadastral_e_redefinir_senha(
            'c000nonexistent', 'qualquer@cemig.com.br', 'OutraSenha123'
        )
        self.assertFalse(ok)
        self.assertIn("não localizada", msg.lower())

        # 4. Senha curta (< 4 caracteres)
        ok, msg = db_manager.validar_desafio_cadastral_e_redefinir_senha(
            'c999999', 'teste.auto@cemig.com.br', '12'
        )
        self.assertFalse(ok)
        self.assertIn("pelo menos 4 caracteres", msg.lower())

if __name__ == '__main__':
    unittest.main()

