import time
import os
import json
import io
import sys
import datetime
import multiprocessing
import pandas as pd
from playwright.sync_api import sync_playwright

# --- CONFIGURAÇÕES ---
URL_SISTEMA = "http://gdis-pm/gdispm/"

SELETOR_USUARIO = "input[id='formLogin:userid']"
SELETOR_SENHA = "input[id='formLogin:password']"
SELETOR_BTN_LOGIN = "input[id='formLogin:botao']"

SELETOR_COMBO_MALHA = "select[id='formBusca:malha']"
SELETOR_COMBO_REGIAO = "select[id='formBusca:area']"
SELETOR_BTN_PESQUISAR = "input[id='formBusca:btnSalvar']"

def carregar_credenciais():
    usuario = os.environ.get("GDIS_USUARIO", "").strip()
    senha = os.environ.get("GDIS_SENHA", "").strip()
    if usuario and senha:
        return usuario, senha

    cred_path = os.path.join(os.path.expanduser("~"), ".dashboard_mt", "credenciais.json")
    try:
        with open(cred_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("usuario", "")).strip(), str(data.get("senha", "")).strip()
    except Exception:
        return "", ""

def find_frame_with_selector(page, css_selector):
    try:
        if page.locator(css_selector).count() > 0:
            return page
    except Exception:
        pass
    for fr in page.frames:
        try:
            if fr.locator(css_selector).count() > 0:
                return fr
        except Exception:
            pass
    return page

def navegar_para_programador_frames(page):
    deadline = time.time() + 15
    while time.time() < deadline:
        for fr in page.frames:
            try:
                perfil = fr.locator("text=Perfil").first
                if perfil.count() == 0:
                    continue
                try:
                    perfil.hover(timeout=1000)
                except Exception:
                    pass
                try:
                    perfil.click(timeout=2000, force=True)
                except Exception:
                    pass
                prog = fr.locator("text=Programador").first
                try:
                    prog.wait_for(timeout=2000)
                except Exception:
                    pass
                if prog.count() == 0:
                    continue
                prog.click(timeout=5000, force=True)
                return True
            except Exception:
                continue
        time.sleep(0.4)
    return False

def _max_linhas_tabela_visivel(ctx):
    try:
        return int(ctx.evaluate("""() => {
            const tabelas = Array.from(document.querySelectorAll('table'));
            let maxLinhas = 0;
            for (const tab of tabelas) {
                const visivel = (tab.offsetParent !== null) || (tab.getClientRects && tab.getClientRects().length > 0);
                if (!visivel) continue;
                if (tab.classList.contains('rich-table') || tab.querySelector('tbody[id$=":tb"]')) {
                    return tab.querySelectorAll('tr').length;
                }
                const linhas = tab.querySelectorAll('tr').length;
                if (linhas > maxLinhas) maxLinhas = linhas;
            }
            return maxLinhas;
        }"""))
    except Exception:
        return 0

def encontrar_contexto_tabela(page):
    melhor_ctx = page
    melhor = _max_linhas_tabela_visivel(page)
    for fr in page.frames:
        linhas = _max_linhas_tabela_visivel(fr)
        if linhas > melhor:
            melhor = linhas
            melhor_ctx = fr
    return melhor_ctx

def log(msg):
    print(msg, flush=True)

def worker_processo(process_id, malhas_atribuidas, pasta_temp):
    """Executa em um processo Python totalmente separado (Sessao/JSESSIONID exclusiva)."""
    log(f"[Processo {process_id}] [INICIO] Atribuido as Malhas: {malhas_atribuidas}")
    
    usuario, senha = carregar_credenciais()
    if not usuario or not senha:
        log(f"[Processo {process_id}] [ERRO] Credenciais nao encontradas!")
        return

    caminhos_navegador = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    ]
    executavel = next((c for c in caminhos_navegador if os.path.exists(c)), None)
    
    dados_processo = []
    regioes_vazias = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executavel, headless=True)
        context = browser.new_context()  # JSESSIONID EXCLUSIVA DESTE PROCESSO!
        page = context.new_page()
        
        try:
            log(f"[Processo {process_id}] Realizando login exclusivo no GDIS...")
            page.goto(URL_SISTEMA)
            if page.locator(SELETOR_USUARIO).count() > 0:
                page.fill(SELETOR_USUARIO, usuario)
                page.fill(SELETOR_SENHA, senha)
                page.click(SELETOR_BTN_LOGIN)
                try:
                    page.wait_for_load_state('networkidle', timeout=15000)
                except Exception:
                    pass
                    
            cookies = context.cookies()
            jsession = next((c['value'] for c in cookies if c['name'] == 'JSESSIONID'), 'Desconhecida')
            log(f"[Processo {process_id}] Sessao JSESSIONID exclusiva: {jsession}")
            
            log(f"[Processo {process_id}] Navegando para o menu Programador...")
            navegar_para_programador_frames(page)
            
            # Aguarda a tela carregar
            deadline_malha = time.time() + 30
            ctx = page
            while time.time() < deadline_malha:
                ctx = find_frame_with_selector(page, SELETOR_COMBO_MALHA)
                try:
                    if ctx.locator(SELETOR_COMBO_MALHA).count() > 0:
                        ctx.wait_for_selector(SELETOR_COMBO_MALHA, state="visible", timeout=5000)
                        break
                except Exception:
                    pass
                time.sleep(0.5)
                
            for malha in malhas_atribuidas:
                log(f"\n[Processo {process_id}] >>> Processando Malha: '{malha}' <<<")
                
                try:
                    html_antigo = ctx.evaluate(f"() => document.querySelector('{SELETOR_COMBO_REGIAO}')?.innerHTML || ''")
                except Exception:
                    html_antigo = ""
                    
                ctx.select_option(SELETOR_COMBO_MALHA, label=malha)
                
                deadline_m = time.time() + 15
                while time.time() < deadline_m:
                    try:
                        html_novo = ctx.evaluate(f"() => document.querySelector('{SELETOR_COMBO_REGIAO}')?.innerHTML || ''")
                        if html_novo != html_antigo:
                            break
                    except Exception:
                        pass
                    time.sleep(0.3)
                time.sleep(0.5)
                
                regioes_objs = ctx.evaluate(f"""() => {{
                    const options = Array.from(document.querySelectorAll("{SELETOR_COMBO_REGIAO} option"));
                    return options.map(o => ({{ text: o.innerText.trim(), value: o.value }})).filter(o => o.text && !o.text.includes('Selecione') && o.value);
                }}""")
                
                log(f"[Processo {process_id}] Regioes encontradas em '{malha}': {len(regioes_objs)}")
                
                for r_obj in regioes_objs:
                    regiao_text = r_obj['text']
                    regiao_valor = r_obj['value']
                    
                    t0 = time.time()
                    log(f"[Processo {process_id}] [RUN] Extraindo: Regiao '{regiao_text}'...")
                    
                    try:
                        try:
                            ctx.wait_for_selector(f"{SELETOR_COMBO_REGIAO} option[value='{regiao_valor}']", timeout=10000)
                        except Exception:
                            pass
                            
                        ctx.select_option(SELETOR_COMBO_REGIAO, value=regiao_valor)
                        time.sleep(0.2)
                        
                        ctx_tabela = encontrar_contexto_tabela(page)
                        
                        try:
                            ctx_tabela.evaluate("() => { document.querySelectorAll('table').forEach(t => t.setAttribute('data-extrator', 'pesquisando')); }")
                        except Exception:
                            pass
                            
                        ctx.click(SELETOR_BTN_PESQUISAR, no_wait_after=True)
                        
                        deadline_ajax = time.time() + 30
                        while time.time() < deadline_ajax:
                            try:
                                pesquisando = ctx_tabela.evaluate("() => document.querySelectorAll('table[data-extrator=\"pesquisando\"]').length > 0")
                            except Exception:
                                pesquisando = False
                            if not pesquisando:
                                break
                            time.sleep(0.2)
                            
                        time.sleep(0.8)
                        ctx_tabela = encontrar_contexto_tabela(page)
                        
                        tem_dados = ctx_tabela.evaluate("() => { const tb = document.querySelector('tbody[id$=\":tb\"]'); return tb && tb.querySelectorAll('tr').length > 0; }")
                        
                        if tem_dados:
                            tabela_html = ctx_tabela.evaluate("""() => {
                                const tab = document.querySelector('table.rich-table') || document.querySelector('tbody[id$=":tb"]')?.closest('table');
                                return tab ? tab.outerHTML : '';
                            }""")
                            if tabela_html:
                                try:
                                    dfs = pd.read_html(io.StringIO(tabela_html))
                                except Exception:
                                    dfs = []
                                if dfs:
                                    df_reg = dfs[0]
                                    df_reg['Ref_Malha'] = malha
                                    df_reg['Ref_Regiao'] = regiao_text
                                    dados_processo.append(df_reg)
                                    dt = time.time() - t0
                                    log(f"[Processo {process_id}] [OK] {len(df_reg)} solicitacoes extraidas em '{regiao_text}' ({dt:.1f}s).")
                        else:
                            regioes_vazias += 1
                            dt = time.time() - t0
                            log(f"[Processo {process_id}] [VAZIO] Regiao '{regiao_text}' sem registros ({dt:.1f}s).")
                            
                    except Exception as e:
                        log(f"[Processo {process_id}] [ERRO] Falha ao extrair '{regiao_text}': {e}")
                        
        finally:
            browser.close()
            
    # Salva dados do processo em arquivo temporario
    os.makedirs(pasta_temp, exist_ok=True)
    out_file = os.path.join(pasta_temp, f"proc_{process_id}_dados.parquet")
    meta_file = os.path.join(pasta_temp, f"proc_{process_id}_meta.json")
    
    if dados_processo:
        df_concat = pd.concat(dados_processo, ignore_index=True)
        df_concat.to_parquet(out_file, index=False)
        
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump({"vazias": regioes_vazias, "tabelas": len(dados_processo)}, f)
        
    log(f"[Processo {process_id}] Finalizado! Dados salvos em '{out_file}'.")

def main():
    log("=" * 60)
    log("[INICIO] EXTRATOR MULTIPROCESSADO (2 SESSÕES GDIS SEPARADAS)")
    log("=" * 60)
    
    usuario, senha = carregar_credenciais()
    if not usuario or not senha:
        log("[ERRO] Credenciais nao encontradas em ~/.dashboard_mt/credenciais.json")
        return

    start_time = time.time()
    pasta_temp = os.path.join(os.path.dirname(__file__), ".temp_multiprocess")
    
    grupo1 = ['CN - CENTRO', 'LE - LESTE', 'MQ - MANTIQUEIRA']
    grupo2 = ['NT - NORTE', 'SU - SUL', 'TA - TRIANGULO']
    
    p1 = multiprocessing.Process(target=worker_processo, args=(1, grupo1, pasta_temp))
    p2 = multiprocessing.Process(target=worker_processo, args=(2, grupo2, pasta_temp))
    
    log("[RUN] Disparando Processos Filhos em Paralelo...")
    p1.start()
    p2.start()
    
    p1.join()
    p2.join()
    
    total_tabelas = 0
    total_vazias = 0
    
    for proc_id in (1, 2):
        meta_file = os.path.join(pasta_temp, f"proc_{proc_id}_meta.json")
        if os.path.exists(meta_file):
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
                total_tabelas += meta.get("tabelas", 0)
                total_vazias += meta.get("vazias", 0)
                
    tempo_total = time.time() - start_time
    
    log("=" * 60)
    log("[FIM] EXTRACAO MULTIPROCESSADA CONCLUIDA COM SUCESSO!")
    log(f"[TEMPO] Tempo Total Gasto: {tempo_total:.2f} segundos ({tempo_total/60:.2f} minutos)")
    log(f"[DATA] Total de Tabelas Coletadas: {total_tabelas}")
    log(f"[VAZIO] Regioes Vazias: {total_vazias}")
    log("=" * 60)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
