import sqlite3
import pandas as pd
import hashlib

DB_PATH = r'i:\IT\ODCO\PUBLICA\Kennedy\Projetos\analise_demanda\demanda.db'
EXCEL_PATH = r'i:\IT\ODCO\PUBLICA\Kennedy\Projetos\analise_demanda\Lista de funcionarios.xlsx'

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def setup():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("--- Criando tabelas ---")
    # Tabela de Usuários
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        matricula TEXT PRIMARY KEY,
        nome TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        nivel TEXT NOT NULL,
        senha_provisoria INTEGER DEFAULT 1
    )
    ''')

    # Tabela de Regiões x Responsáveis
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS regioes_responsaveis (
        sigla_regiao TEXT PRIMARY KEY,
        matricula_responsavel TEXT,
        FOREIGN KEY (matricula_responsavel) REFERENCES usuarios(matricula)
    )
    ''')
    conn.commit()

    print("--- Importando funcionários do Excel ---")
    df_func = pd.read_excel(EXCEL_PATH)
    senha_padrao_hash = hash_password("12345")

    for _, row in df_func.iterrows():
        matricula = str(row['MATRICULA']).strip()
        nome = str(row['NOME']).upper().strip()
        nivel = str(row['NIVEL']).strip()
        
        # Insere ou atualiza usuário
        cursor.execute('''
        INSERT INTO usuarios (matricula, nome, password_hash, nivel, senha_provisoria)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(matricula) DO UPDATE SET
            nome=excluded.nome,
            nivel=excluded.nivel
        ''', (matricula, nome, senha_padrao_hash, nivel))
    
    conn.commit()
    print(f"Total de {len(df_func)} funcionários processados.")

    print("--- Mapeando regiões iniciais ---")
    # Mapeamento extraído do dashboard.py
    MAPA_INICIAL = {
        'SL': 'LAURA', 'AR': 'LAURA',
        'BT': 'GABRIEL R', 'SG': 'GABRIEL R',
        'BH': 'POLIANE', 'NL': 'POLIANE',
        'CL': 'ANDERSON',
        'CR': 'ANDERSON', 'RA': 'ANDERSON',
        'TO': 'ANA P', 'AL': 'ANA P', 'IR': 'ANA P',
        'GV': 'NATÁLIA', 'IP': 'NATÁLIA',
        'MO': 'VICTOR', 'UN': 'VICTOR',
        'PT': 'KENNEDY', 'SI': 'KENNEDY',
        'JN': 'FLÁVIO','JB': 'FLÁVIO',
        'PI': 'FLÁVIO', 
        'IJ': 'GUSTAVO', 
        'DV': 'EMANUELLE', 'PR': 'EMANUELLE', 
        'TC': 'KENNEDY',
        'FM': 'AMANDA A', 'PS': 'AMANDA A',
        'VR': 'BRENO', 'PA': 'BRENO', 
        'AF': 'AMANDA P',
        'JF': 'KASSIUS', 'SJ': 'KASSIUS', 'JM': 'KASSIUS',
        'LF': 'PABLO', 'PN': 'PABLO', 'OP': 'PABLO',
        'LV': 'PABLIANE', 'BC': 'PABLIANE', 'IA': 'PABLIANE',
        'PM': 'EDUARDO', 'FR': 'EDUARDO',
        'UR': 'DEBORA', 'TB': 'DEBORA',
        'PO': 'JOÃO', 'BD': 'JOÃO',
        'UL': 'ANA C', 'AX': 'ANA C', 'AG': 'ANA C'
    }

    # Busca matrículas baseadas no primeiro nome ou substring
    cursor.execute("SELECT matricula, nome FROM usuarios")
    users = cursor.fetchall()

    for sigla, nome_curto in MAPA_INICIAL.items():
        matricula_encontrada = None
        for m, n in users:
            # Match se o primeiro nome bater ou se o nome curto estiver contido no nome completo
            # Ex: 'AMANDA A' -> 'AMANDA ANDRADE ABREU'
            partes_curtas = nome_curto.split()
            primeiro_nome_curto = partes_curtas[0]
            
            if n.startswith(primeiro_nome_curto):
                # Se tiver sobrenome abreviado (ex: AMANDA A), tenta bater a primeira letra do segundo nome
                if len(partes_curtas) > 1:
                    letra_sobrenome = partes_curtas[1][0]
                    palavras_nome_completo = n.split()
                    if len(palavras_nome_completo) > 1 and palavras_nome_completo[1].startswith(letra_sobrenome):
                        matricula_encontrada = m
                        break
                else:
                    matricula_encontrada = m
                    break
        
        if matricula_encontrada:
            cursor.execute('''
            INSERT INTO regioes_responsaveis (sigla_regiao, matricula_responsavel)
            VALUES (?, ?)
            ON CONFLICT(sigla_regiao) DO UPDATE SET matricula_responsavel=excluded.matricula_responsavel
            ''', (sigla, matricula_encontrada))
        else:
            print(f"Aviso: Não foi possível encontrar usuário para region {sigla} ({nome_curto})")

    conn.commit()
    conn.close()
    print("--- Setup concluído com sucesso! ---")

if __name__ == "__main__":
    setup()
