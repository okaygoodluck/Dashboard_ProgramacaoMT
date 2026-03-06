import schedule
import time
import subprocess
import sys
import datetime
import os

def job():
    print(f"\n[AGENDADOR] Iniciando execução em: {datetime.datetime.now()}")
    try:
        # Define caminho absoluto do script extrator
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extrator_demanda.py")
        
        # Executa o extrator_demanda.py como um subprocesso
        # O extrator já está configurado para salvar no SQLite e gerar backup Excel
        # REMOVIDO capture_output=True para mostrar o log em tempo real no console
        resultado = subprocess.run(
            [sys.executable, script_path], 
            check=True
        )
        print("[AGENDADOR] Execução concluída com sucesso.")
        
    except subprocess.CalledProcessError as e:
        print(f"[AGENDADOR] ERRO na execução: {e}")
        print("Log de Erro:")
        print(e.stderr)
    except Exception as e:
        print(f"[AGENDADOR] Erro inesperado: {e}")

# Configura o agendamento para cada 10 minutos
schedule.every(10).minutes.do(job)

print("=== Agendador Iniciado ===")
print("O script extrator_demanda.py será executado a cada 10 minutos.")
print("Pressione Ctrl+C para encerrar.")

# Executa uma vez imediatamente ao iniciar, para não esperar 10 min pelo primeiro
job()

while True:
    try:
        schedule.run_pending()
        time.sleep(1)
    except KeyboardInterrupt:
        print("\nAgendador encerrado pelo usuário.")
        break
