import imaplib
import json
import os
import sys

def testar_conexao():
    print("="*50)
    print("VANGUARD - TESTE DE CONEXÃO DE E-MAIL (PROTÓTIPO)")
    print("="*50)

    # 1. Carregar Credenciais
    cred_path = os.path.join(os.path.expanduser("~"), ".dashboard_mt", "credenciais.json")
    if not os.path.exists(cred_path):
        print(f"Erro: Arquivo de credenciais não encontrado em: {cred_path}")
        return

    try:
        with open(cred_path, "r", encoding="utf-8") as f:
            creds = json.load(f)
        
        usuario_base = creds.get("usuario", "")
        senha = creds.get("senha", "")
        
        if not usuario_base or not senha:
            print("Erro: Usuário ou senha não encontrados no arquivo json.")
            return

        # Para o Office 365, precisamos do e-mail completo
        email_principal = usuario_base if "@" in usuario_base else f"{usuario_base}@cemig.com.br"
        
        # Caixa Compartilhada
        # Formato comum no O365: usuario@dominio.com\alias-da-caixa
        caixa_compartilhada = "SHM-man-urgencia" 
        login_string = f"{email_principal}\\{caixa_compartilhada}"

        print(f"Tentando logar em: outlook.office365.com")
        print(f"Utilizando login: {login_string}")
        print("-" * 50)

        # 2. Conectar ao Servidor
        try:
            mail = imaplib.IMAP4_SSL("outlook.office365.com", 993)
            print("[OK] Conexão com o servidor estabelecida.")
        except Exception as e:
            print(f"[ERRO] Falha ao conectar ao servidor: {e}")
            return

        # 3. Autenticar
        try:
            mail.login(login_string, senha)
            print("[OK] Login realizado com sucesso!")
        except Exception as e:
            print(f"[ERRO] Falha na autenticação: {e}")
            print("\nNota: Se você tiver MFA (celular), deve usar uma 'Senha de Aplicativo'.")
            return

        # 4. Listar Pastas (Para confirmar acesso)
        print("\nExplorando pastas disponíveis na caixa compartilhada:")
        status, folders = mail.list()
        if status == 'OK':
            for f in folders:
                print(f"  - {f.decode()}")
        
        # 5. Tentar acessar a INBOX
        print("\nTentando selecionar a INBOX...")
        status, data = mail.select("INBOX")
        if status == 'OK':
            num_msgs = data[0].decode()
            print(f"[OK] INBOX acessada. Total de mensagens: {num_msgs}")
            
            # Listar os 5 assuntos mais recentes
            print("\nÚltimos 5 e-mails:")
            status, ids = mail.search(None, "ALL")
            if status == 'OK':
                id_list = ids[0].split()
                recent_ids = id_list[-5:] # Pega os 5 últimos
                
                for msg_id in reversed(recent_ids):
                    status, msg_data = mail.fetch(msg_id, '(BODY[HEADER.FIELDS (SUBJECT)])')
                    subject = msg_data[0][1].decode().replace("Subject: ", "").strip()
                    print(f"  - ID {msg_id.decode()}: {subject}")
        else:
            print(f"[ERRO] Não foi possível acessar a INBOX: {status}")

        mail.logout()
        print("\n" + "="*50)
        print("TESTE CONCLUÍDO")
        print("="*50)

    except Exception as e:
        print(f"Erro inesperado: {e}")

if __name__ == "__main__":
    testar_conexao()
