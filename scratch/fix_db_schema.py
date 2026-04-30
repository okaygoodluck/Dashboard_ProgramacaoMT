import sqlite3
import os
import shutil

DB_PATH = 'demanda.db'
NETWORK_PATH = r'I:\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programação\Dashboard MT\demanda_publica.db'

def fix_db(path):
    if not os.path.exists(path):
        print(f"Path not found: {path}")
        return
    
    print(f"Fixing DB: {path}")
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    
    # Check tables
    for table in ['demanda_atual', 'demanda_historico']:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [col[1] for col in cursor.fetchall()]
        if 'Tem_Email' not in cols:
            print(f"Adding Tem_Email to {table}")
            cursor.execute(f'ALTER TABLE "{table}" ADD COLUMN "Tem_Email" TEXT')
    
    conn.commit()
    conn.close()
    print(f"Done fixing {path}")

# Fix local
fix_db(DB_PATH)

# Fix network
fix_db(NETWORK_PATH)

# Copy local to network just in case
try:
    shutil.copy2(DB_PATH, NETWORK_PATH)
    print("Copied local to network.")
except Exception as e:
    print(f"Copy failed: {e}")
