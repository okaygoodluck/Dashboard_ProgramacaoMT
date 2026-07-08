import time
import subprocess
import sys
import datetime
import os


def _parse_hhmm(value, default):
    s = (value or "").strip()
    if not s:
        s = default
    parts = s.split(":")
    if len(parts) != 2:
        s = default
        parts = s.split(":")
    h = int(parts[0])
    m = int(parts[1])
    return datetime.time(hour=h, minute=m)

def _in_window(now_dt, start_t, end_t):
    t = now_dt.time()
    if start_t <= end_t:
        return start_t <= t < end_t
    return t >= start_t or t < end_t

def _seconds_until_window_start(now_dt, start_t, end_t):
    if _in_window(now_dt, start_t, end_t):
        return 0
    today_start = datetime.datetime.combine(now_dt.date(), start_t)
    if now_dt < today_start:
        return int((today_start - now_dt).total_seconds())
    tomorrow = now_dt.date() + datetime.timedelta(days=1)
    next_start = datetime.datetime.combine(tomorrow, start_t)
    return int((next_start - now_dt).total_seconds())

def job():
    print(f"\n[AGENDADOR] Iniciando execução em: {datetime.datetime.now()}")
    try:
        # Modo Exe: chama a função diretamente via import
        if getattr(sys, "frozen", False):
            import extrator_demanda
            ok = extrator_demanda.extrair_dados()
            if not ok:
                raise RuntimeError("Extração falhou")
        else:
            # Define o diretório do agendador
            current_dir = os.path.dirname(os.path.abspath(__file__))
            
            # Se estiver na pasta 'scripts', o diretório raiz é o pai
            if os.path.basename(current_dir) == "scripts":
                root_dir = os.path.dirname(current_dir)
            else:
                root_dir = current_dir
                
            # Define caminho absoluto do script extrator
            script_path = os.path.join(root_dir, "extrator_demanda.py")
            
            # Executa o extrator_demanda.py como um subprocesso na raiz
            subprocess.run(
                [sys.executable, script_path], 
                check=True,
                cwd=root_dir
            )
        print("[AGENDADOR] Execução concluída com sucesso.")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"[AGENDADOR] ERRO na execução: O script extrator encerrou com código {e.returncode}.")
        if e.stderr:
            print("Log de Erro:")
            print(e.stderr)
        return False
    except Exception as e:
        print(f"[AGENDADOR] Erro inesperado: {e}")
        return False

def main():
    print("=== Agendador Iniciado ===")
    janela_inicio = _parse_hhmm(os.environ.get("AGENDADOR_JANELA_INICIO"), "07:00")
    janela_fim = _parse_hhmm(os.environ.get("AGENDADOR_JANELA_FIM"), "20:00")
    pausa_entre_execucoes = int(os.environ.get("AGENDADOR_PAUSA_SEGUNDOS", "60"))
    pausa_fora_janela = int(os.environ.get("AGENDADOR_SLEEP_FORA_JANELA_SEGUNDOS", "30"))
    print(f"Janela: {janela_inicio.strftime('%H:%M')} - {janela_fim.strftime('%H:%M')}")
    print(f"Pausa entre execuções: {pausa_entre_execucoes}s")
    print("Pressione Ctrl+C para encerrar.")

    while True:
        try:
            agora = datetime.datetime.now()
            if _in_window(agora, janela_inicio, janela_fim):
                job()
                time.sleep(max(0, pausa_entre_execucoes))
            else:
                segundos = _seconds_until_window_start(agora, janela_inicio, janela_fim)
                if segundos > 0:
                    sleep_s = min(max(1, pausa_fora_janela), segundos)
                    time.sleep(sleep_s)
        except KeyboardInterrupt:
            print("\nAgendador encerrado pelo usuário.")
            break

if __name__ == "__main__":
    main()
