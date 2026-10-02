# scripts/simular_dados_teste.py
# Gerador de Dados Simulados para Teste Local do CCP (Isolado da Rede)
import os
import sys
import datetime
import pandas as pd

# Força o modo de teste para não copiar para a rede
os.environ["CCP_MODO_TESTE"] = "1"
os.environ["CCP_NAO_COPIAR_REDE"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db_manager

def gerar_dados_teste():
    print("=" * 60)
    print("  SIMULAÇÃO DE DADOS DE DEMANDA (AMBIENTE LOCAL DE TESTE)")
    print("=" * 60)

    agora = datetime.datetime.now()
    data_extracao = agora.strftime("%Y-%m-%d %H:%M:%S")
    amanha = agora + datetime.timedelta(days=1)
    depois = agora + datetime.timedelta(days=2)

    registros = [
        {
            "Solicitação": "990001",
            "Região": "PM - Pouso Alegre",
            "Ref_Regiao": "PM - Pouso Alegre",
            "Malha": "Sul",
            "Situação": "APROVADA",
            "Data Início Manobra": amanha.strftime("%d/%m/%Y 08:00"),
            "Data Término Manobra": amanha.strftime("%d/%m/%Y 12:00"),
            "Urgência": "NÃO",
            "Responsável": "Carlos Silva",
            "Finalidade": "Manutenção Preventiva",
            "CHI": 1850.5,           # CHI >= 1500 sem e-mail -> DEVE DESTACAR EM VERMELHO/ALERTA
            "Clientes": 420,
            "Peso": "3",
            "OBRA GD": "",
            "Tem_Email": False,
            "Tem_Email_DECP": False, # Sem e-mail DECP
            "Data_Extracao": data_extracao
        },
        {
            "Solicitação": "990002",
            "Região": "PM - Varginha",
            "Ref_Regiao": "PM - Varginha",
            "Malha": "Sul",
            "Situação": "APROVADA",
            "Data Início Manobra": amanha.strftime("%d/%m/%Y 09:00"),
            "Data Término Manobra": amanha.strftime("%d/%m/%Y 13:00"),
            "Urgência": "NÃO",
            "Responsável": "Mariana Santos",
            "Finalidade": "Obra de Expansão",
            "CHI": 2400.0,           # CHI >= 1500 com e-mail -> DEVE DESTACAR EM VERDE SUAVE
            "Clientes": 890,
            "Peso": "4",
            "OBRA GD": "GD-7781",
            "Tem_Email": False,
            "Tem_Email_DECP": True,  # Com e-mail DECP confirmado!
            "Data_Extracao": data_extracao
        },
        {
            "Solicitação": "990003",
            "Região": "BH - Belo Horizonte",
            "Ref_Regiao": "BH - Belo Horizonte",
            "Malha": "Centro",
            "Situação": "APROVADA",
            "Data Início Manobra": depois.strftime("%d/%m/%Y 07:30"),
            "Data Término Manobra": depois.strftime("%d/%m/%Y 11:30"),
            "Urgência": "NÃO",
            "Responsável": "Roberto Almeida",
            "Finalidade": "Atendimento Emergencial",
            "CHI": 450.0,            # CHI normal (< 1500) -> Linha padrão sem cor especial
            "Clientes": 110,
            "Peso": "1",
            "OBRA GD": "",
            "Tem_Email": False,
            "Tem_Email_DECP": False,
            "Data_Extracao": data_extracao
        },
        {
            "Solicitação": "990004",
            "Região": "SL - Sete Lagoas",
            "Ref_Regiao": "SL - Sete Lagoas",
            "Malha": "Centro",
            "Situação": "APROVADA",
            "Data Início Manobra": amanha.strftime("%d/%m/%Y 14:00"),
            "Data Término Manobra": amanha.strftime("%d/%m/%Y 17:00"),
            "Urgência": "SIM",
            "Responsável": "Ana Paula Lima",
            "Finalidade": "Correção de Defeito Crítico",
            "CHI": 1620.0,           # Urgente + CHI >= 1500 (Aguardando e-mail DECP)
            "Clientes": 650,
            "Peso": "4",
            "OBRA GD": "",
            "Tem_Email": True,       # Tem e-mail de urgência
            "Tem_Email_DECP": False, # Falta e-mail DECP
            "Data_Extracao": data_extracao
        },
        {
            "Solicitação": "990005",
            "Região": "UD - Uberlândia",
            "Ref_Regiao": "UD - Uberlândia",
            "Malha": "Triângulo",
            "Situação": "APROVADA",
            "Data Início Manobra": depois.strftime("%d/%m/%Y 10:00"),
            "Data Término Manobra": depois.strftime("%d/%m/%Y 14:00"),
            "Urgência": "SIM",
            "Responsável": "Fernando Costa",
            "Finalidade": "Troca de Transformador",
            "CHI": 210.0,            # Urgente comum (CHI < 1500)
            "Clientes": 85,
            "Peso": "2",
            "OBRA GD": "",
            "Tem_Email": False,      # Falta e-mail de urgência
            "Tem_Email_DECP": False,
            "Data_Extracao": data_extracao
        }
    ]

    df_teste = pd.DataFrame(registros)

    print(f"[*] Gerando {len(df_teste)} registros de teste...")
    print(f"    - Solicitação 990001: CHI=1850 (Sem e-mail DECP -> Alerta Vermelho)")
    print(f"    - Solicitação 990002: CHI=2400 (Com e-mail DECP -> Verde Suave)")
    print(f"    - Solicitação 990003: CHI=450  (Padrão, CHI < 1500)")
    print(f"    - Solicitação 990004: CHI=1620 (Urgente + Falta DECP)")
    print(f"    - Solicitação 990005: CHI=210  (Urgente comum)")

    print("\n[DB] Gravando dados simulados localmente...")
    db_manager.salvar_dados(df_teste)
    db_manager.publicar_db_rede()

    try:
        db_manager.carregar_dados_recentes.clear()
    except Exception:
        pass

    print("\n[SUCESSO] Dados de teste carregados com sucesso no banco local!")
    print("Inicie o dashboard via 'Iniciar_Dashboard_Teste.bat' para visualizar os resultados.")
    print("=" * 60)

if __name__ == "__main__":
    gerar_dados_teste()
