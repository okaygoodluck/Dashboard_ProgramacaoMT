import os

# Força o ambiente de testes a utilizar sempre o banco de dados local isolado
os.environ["CCP_MODO_TESTE"] = "1"
os.environ["CCP_FORCAR_LOCAL"] = "1"
