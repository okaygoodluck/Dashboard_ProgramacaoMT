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
    print(f"\n[AGENDADOR] Iniciando extração rápida em: {datetime.datetime.now()}")
    try:
        # Modo Exe: chama a função diretamente via import
        if getattr(sys, "frozen", False):
            import extrator_demanda
            ok = extrator_demanda.extrair_dados()
            if not ok:
                raise RuntimeError("Extração falhou")
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            root_dir = os.path.dirname(current_dir) if os.path.basename(current_dir) == "scripts" else current_dir
            script_path = os.path.join(root_dir, "extrator_demanda.py")
            subprocess.run(
                [sys.executable, script_path], 
                check=True,
                cwd=root_dir
            )
        print("[AGENDADOR] Extração rápida concluída com sucesso.")
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


def job_auditor():
    """
    Executa a conciliação remota de status no GDIS-PM de forma sequencial,
    garantindo que o extrator de fila ativa já tenha liberado o navegador e o banco.
    """
    print(f"\n[AGENDADOR] Verificando demandas pendentes de auditoria em: {datetime.datetime.now()}")
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(current_dir) if os.path.basename(current_dir) == "scripts" else current_dir
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)

        import db_manager
        pendentes = db_manager.get_solicitacoes_pendentes_conciliacao(limite=1)
        if not pendentes:
            print("[AGENDADOR] Nenhuma solicitação pendente na fila de conciliação. Ciclo dispensado.")
            return True

        print(f"[AGENDADOR] Demandas pendentes detectadas. Iniciando auditor_status.py...")
        if getattr(sys, "frozen", False):
            import auditor_status
            auditor_status.executar_auditoria()
        else:
            script_path = os.path.join(root_dir, "auditor_status.py")
            subprocess.run(
                [sys.executable, script_path],
                check=True,
                cwd=root_dir
            )
        print("[AGENDADOR] Ciclo de auditoria concluído com sucesso.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[AGENDADOR] Aviso no auditor: Encerrou com código {e.returncode}.")
        return False
    except Exception as e:
        print(f"[AGENDADOR] Erro inesperado no ciclo de auditoria: {e}")
        return False


def main():
    print("=== Agendador Integrado CCP Iniciado ===")
    janela_inicio = _parse_hhmm(os.environ.get("AGENDADOR_JANELA_INICIO"), "06:00")
    janela_fim = _parse_hhmm(os.environ.get("AGENDADOR_JANELA_FIM"), "20:00")
    pausa_entre_execucoes = int(os.environ.get("AGENDADOR_PAUSA_SEGUNDOS", "15"))
    pausa_fora_janela = int(os.environ.get("AGENDADOR_SLEEP_FORA_JANELA_SEGUNDOS", "30"))
    intervalo_auditoria_segundos = int(os.environ.get("AGENDADOR_INTERVALO_AUDITORIA_SEGUNDOS", "7200")) # 2 horas padrão
    
    print(f"Janela Operacional: {janela_inicio.strftime('%H:%M')} - {janela_fim.strftime('%H:%M')}")
    print(f"Pausa entre extrações rápidas: {pausa_entre_execucoes}s")
    print(f"Intervalo de auditoria remota: {intervalo_auditoria_segundos // 60} minutos")
    print("Pressione Ctrl+C para encerrar.\n")

    ultima_auditoria = None

    while True:
        try:
            agora = datetime.datetime.now()
            if _in_window(agora, janela_inicio, janela_fim):
                # 1. Ciclo Rápido de Estoque (extrator_demanda.py)
                job()
                
                # 2. Ciclo Periódico de Reconciliação (auditor_status.py sequencial)
                deve_auditar = (ultima_auditoria is None) or ((agora - ultima_auditoria).total_seconds() >= intervalo_auditoria_segundos)
                if deve_auditar:
                    time.sleep(3) # Pausa de garantia para liberação completa do Chromium
                    job_auditor()
                    ultima_auditoria = datetime.datetime.now()

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

