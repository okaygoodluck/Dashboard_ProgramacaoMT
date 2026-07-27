import time
import os
import datetime
import json
import sys
import asyncio
import pandas as pd
from playwright.async_api import async_playwright

# --- CONFIGURAÇÕES ---
URL_SISTEMA = "http://gdis-pm/gdispm/"
NUM_WORKERS = 4  # Número de abas concorrentes em paralelo

# Seletores da Tela de Login
SELETOR_USUARIO = "input[id='formLogin:userid']"
SELETOR_SENHA = "input[id='formLogin:password']"
SELETOR_BTN_LOGIN = "input[id='formLogin:botao']"

# Seletores da Tela de Consulta
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

async def find_frame_with_selector(page, css_selector):
    try:
        if await page.locator(css_selector).count() > 0:
            return page
    except Exception:
        pass
    for fr in page.frames:
        try:
            if await fr.locator(css_selector).count() > 0:
                return fr
        except Exception:
            pass
    return page

async def navegar_para_programador_frames(page):
    deadline = time.time() + 15
    while time.time() < deadline:
        for fr in page.frames:
            try:
                perfil = fr.locator("text=Perfil").first
                if await perfil.count() == 0:
                    continue
                try:
                    await perfil.hover(timeout=1000)
                except Exception:
                    pass
                try:
                    await perfil.click(timeout=2000, force=True)
                except Exception:
                    pass
                prog = fr.locator("text=Programador").first
                try:
                    await prog.wait_for(timeout=2000)
                except Exception:
                    pass
                if await prog.count() == 0:
                    continue
                await prog.click(timeout=5000, force=True)
                return True
            except Exception:
                continue
        await asyncio.sleep(0.4)
    return False

async def _max_linhas_tabela_visivel(ctx):
    try:
        return int(await ctx.evaluate("""() => {
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

async def encontrar_contexto_tabela(page):
    melhor_ctx = page
    melhor = await _max_linhas_tabela_visivel(page)
    for fr in page.frames:
        linhas = await _max_linhas_tabela_visivel(fr)
        if linhas > melhor:
            melhor = linhas
            melhor_ctx = fr
    return melhor_ctx

async def worker_extração(worker_id, context, queue, resultados_lock, dados_consolidados, regioes_vazias):
    """Worker paralelo que consome tarefas da fila de regiões."""
    page = await context.new_page()
    try:
        await page.goto(URL_SISTEMA)
        await navegar_para_programador_frames(page)
        ctx = await find_frame_with_selector(page, SELETOR_COMBO_MALHA)
        
        while not queue.empty():
            try:
                task = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
                
            malha, regiao_text, regiao_valor = task
            print(f"[Worker {worker_id}] ⚡ Processando: Malha '{malha}' -> Região '{regiao_text}'...")
            
            try:
                # Troca Malha na aba do Worker
                await ctx.select_option(SELETOR_COMBO_MALHA, label=malha)
                await asyncio.sleep(0.3)
                
                # Troca Região na aba do Worker
                await ctx.select_option(SELETOR_COMBO_REGIAO, value=regiao_valor)
                await asyncio.sleep(0.2)
                
                ctx_tabela = await encontrar_contexto_tabela(page)
                
                # Marcador de Pesquisa AJAX
                try:
                    await ctx_tabela.evaluate("() => { document.querySelectorAll('table').forEach(t => t.setAttribute('data-extrator', 'pesquisando')); }")
                except Exception:
                    pass
                    
                await ctx.click(SELETOR_BTN_PESQUISAR, no_wait_after=True)
                
                # Aguarda AJAX
                deadline = time.time() + 30
                while time.time() < deadline:
                    try:
                        pesquisando = await ctx_tabela.evaluate("() => document.querySelectorAll('table[data-extrator=\"pesquisando\"]').length > 0")
                    except Exception:
                        pesquisando = False
                    if not pesquisando:
                        break
                    await asyncio.sleep(0.2)
                    
                await asyncio.sleep(0.8)
                ctx_tabela = await encontrar_contexto_tabela(page)
                
                tem_dados = await ctx_tabela.evaluate("() => { const tb = document.querySelector('tbody[id$=\":tb\"]'); return tb && tb.querySelectorAll('tr').length > 0; }")
                
                if tem_dados:
                    # Extrai dados da tabela
                    tabela_html = await ctx_tabela.evaluate("""() => {
                        const tab = document.querySelector('table.rich-table') || document.querySelector('tbody[id$=":tb"]')?.closest('table');
                        return tab ? tab.outerHTML : '';
                    }""")
                    
                    if tabela_html:
                        dfs = pd.read_html(tabela_html)
                        if dfs:
                            df_reg = dfs[0]
                            df_reg['Ref_Malha'] = malha
                            df_reg['Ref_Regiao'] = regiao_text
                            async with resultados_lock:
                                dados_consolidados.append(df_reg)
                            print(f"[Worker {worker_id}] ✅ Sucesso: {len(df_reg)} solicitações extraídas em '{regiao_text}'.")
                else:
                    async with resultados_lock:
                        regioes_vazias.append(regiao_text)
                    print(f"[Worker {worker_id}] ℹ️ Vazio: Região '{regiao_text}' sem registros.")
                    
            except Exception as e:
                print(f"[Worker {worker_id}] ❌ Erro ao extrair '{regiao_text}': {e}")
            finally:
                queue.task_done()
    finally:
        await page.close()

async def main():
    print("=" * 60)
    print("🚀 INICIANDO EXTRATOR DE TESTES (POOL PARALELO DE ABAS)")
    print(f"⚙️ Configuração: {NUM_WORKERS} Workers Concorrentes")
    print("=" * 60)
    
    usuario, senha = carregar_credenciais()
    if not usuario or not senha:
        print("❌ ERRO: Credenciais não encontradas em ~/.dashboard_mt/credenciais.json")
        return

    start_time = time.time()
    
    caminhos_navegador = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    ]
    executavel = next((c for c in caminhos_navegador if os.path.exists(c)), None)
    
    async with async_playwright() as p:
        print("🌐 Abrindo Navegador Mestre...")
        browser = await p.chromium.launch(executable_path=executavel, headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        print("🔑 Realizando Login Único...")
        await page.goto(URL_SISTEMA)
        if await page.locator(SELETOR_USUARIO).count() > 0:
            await page.fill(SELETOR_USUARIO, usuario)
            await page.fill(SELETOR_SENHA, senha)
            await page.click(SELETOR_BTN_LOGIN)
            await page.wait_for_load_state('networkidle')
            
        print("📍 Navegando para o menu de consulta...")
        await navegar_para_programador_frames(page)
        ctx = await find_frame_with_selector(page, SELETOR_COMBO_MALHA)
        
        # Mapear Malhas
        lista_malhas = await ctx.evaluate(f"""() => {{
            const options = Array.from(document.querySelectorAll("{SELETOR_COMBO_MALHA} option"));
            return options.map(o => o.innerText.trim()).filter(t => t && !t.includes('Selecione'));
        }}""")
        
        print(f"📋 Malhas Mapeadas ({len(lista_malhas)}): {lista_malhas}")
        
        # Fila de tarefas para os workers paralelos
        queue = asyncio.Queue()
        total_regioes_mapeadas = 0
        
        for malha in lista_malhas:
            await ctx.select_option(SELETOR_COMBO_MALHA, label=malha)
            await asyncio.sleep(0.5)
            regioes_objs = await ctx.evaluate(f"""() => {{
                const options = Array.from(document.querySelectorAll("{SELETOR_COMBO_REGIAO} option"));
                return options.map(o => ({{ text: o.innerText.trim(), value: o.value }})).filter(o => o.text && !o.text.includes('Selecione') && o.value);
            }}""")
            for r in regioes_objs:
                queue.put_nowait((malha, r['text'], r['value']))
                total_regioes_mapeadas += 1
                
        print(f"\n🎯 Total de Regiões Mapeadas para Extração Paralela: {total_regioes_mapeadas}")
        print("-" * 60)
        
        dados_consolidados = []
        regioes_vazias = []
        resultados_lock = asyncio.Lock()
        
        # Inicia o Pool de Workers em Paralelo
        workers = [
            asyncio.create_task(worker_extração(i + 1, context, queue, resultados_lock, dados_consolidados, regioes_vazias))
            for i in range(NUM_WORKERS)
        ]
        
        await queue.join()
        for w in workers:
            w.cancel()
            
        await browser.close()
        
        tempo_total = time.time() - start_time
        print("=" * 60)
        print("🏁 EXTRAÇÃO PARALELA CONCLUÍDA COM SUCESSO!")
        print(f"⏱️ Tempo Total Gasto: {tempo_total:.2f} segundos ({tempo_total/60:.2f} minutos)")
        print(f"📊 Regiões Processadas: {total_regioes_mapeadas}")
        print(f"📦 Total de Tabelas Coletadas: {len(dados_consolidados)}")
        print(f"🔴 Regiões Vazias: {len(regioes_vazias)}")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
