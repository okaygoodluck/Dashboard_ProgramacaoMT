import time
import subprocess
import sys

print("===================================================")
print("     AGENDADOR DE TESTES (EXTRAÇÃO REAL CONTÍNUA)")
print("===================================================")
print("Este script roda o extrator_demanda.py periodicamente.")
print("Ele buscará as informações REAIS do GDIS e as salvará")
print("nos bancos de TESTE, gerando os eventos de produtividade")
print("reais conforme a equipe trabalha no sistema oficial.")
print("===================================================\n")

contador = 1
while True:
    print(f"\n[{time.strftime('%H:%M:%S')}] --- Rodada de Extração (Teste) #{contador} ---")
    try:
        # Roda o extrator real (que abrirá o navegador e fará a raspagem)
        subprocess.run([sys.executable, "extrator_demanda.py"], check=True)
    except Exception as e:
        print(f"Erro ao rodar extrator: {e}")
        
    print("\nAguardando 2 minutos para a próxima extração...")
    time.sleep(120)  # 2 minutos de espera para não sobrecarregar
    contador += 1
