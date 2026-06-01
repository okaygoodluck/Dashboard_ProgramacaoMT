import time
import os
import datetime
import json
import sys
import subprocess

import pandas as pd
from playwright.sync_api import sync_playwright

# --- CONFIGURAÇÕES ---
URL_SISTEMA = "http://gdis-pm/gdispm/"  # Ex: http://sistema.empresa.com.br

def modo_debug_visual():
    return ("--debug" in sys.argv) or (os.environ.get("EXTRATOR_DEBUG_UI", "").strip() == "1")

def carregar_credenciais():
    usuario = os.environ.get("GDIS_USUARIO", "").strip()
    senha = os.environ.get("GDIS_SENHA", "").strip()
    if usuario and senha:
        return usuario, senha

    cred_path = os.path.join(os.path.expanduser("~"), ".dashboard_mt", "credenciais.json")
    try:
        with open(cred_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        usuario = str(data.get("usuario", "")).strip()
        senha = str(data.get("senha", "")).strip()
        return usuario, senha
    except Exception:
        return "", ""

def salvar_debug(page, prefixo):
    try:
        pasta = "Erros"
        os.makedirs(pasta, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in str(prefixo))[:80]
        png_path = os.path.join(pasta, f"debug_erro_{safe}_{ts}.png")
        html_path = os.path.join(pasta, f"debug_erro_{safe}_{ts}.html")
        try:
            page.screenshot(path=png_path, full_page=True)
        except Exception:
            pass
        try:
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page.content())
        except Exception:
            pass
    except Exception:
        pass

def fechar_browser(browser):
    try:
        browser.close()
    except Exception:
        pass

# A publicação agora é gerenciada centralizadamente pelo db_manager.py

# Seletores (Inspecione o elemento no navegador e copie o Seletor CSS ou XPath)
SELETOR_USUARIO = "input[id='formLogin:userid']"  # Ajuste conforme seu sistema
SELETOR_SENHA = "input[id='formLogin:password']"      # Ajuste conforme seu sistema
SELETOR_BTN_LOGIN = "input[id='formLogin:botao']" # Ajuste conforme seu sistema

# Seletores da Tela de Consulta
SELETOR_COMBO_MALHA = "select[id='formBusca:malha']"    # O * significa "contém", ajuda em IDs dinâmicos do JSF
SELETOR_COMBO_REGIAO = "select[id='formBusca:area']"
SELETOR_BTN_PESQUISAR = "input[id='formBusca:btnSalvar']" # Ou button[id*='pesquisar']

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

def navegar_para_programador_frames(page, debug_ui):
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

    if debug_ui:
        try:
            print("DEBUG_UI: frames detectados:")
            for fr in page.frames:
                name = getattr(fr, "name", "") or ""
                url = getattr(fr, "url", "") or ""
                print(f" - {name} | {url}")
        except Exception:
            pass
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
    return melhor_ctx, melhor

def extrair_dados():
    start_time = time.time() # Início da medição de tempo
    debug_ui = modo_debug_visual()
    usuario, senha = carregar_credenciais()
    if not usuario or not senha:
        print("ERRO: Credenciais não configuradas. Use Configurar_Credenciais.bat ou GDIS_USUARIO/GDIS_SENHA.")
        return False
    with sync_playwright() as p:
        # Tenta encontrar o Edge ou Chrome instalado na máquina
        # Caminhos comuns em Windows corporativo
        caminhos_navegador = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        ]
        
        navegador_executavel = None
        for caminho in caminhos_navegador:
            if os.path.exists(caminho):
                navegador_executavel = caminho
                print(f"Navegador encontrado: {caminho}")
                break
        
        if not navegador_executavel:
            print("ERRO: Não encontrei Edge ou Chrome instalado nos locais padrão.")
            print("Instale o Playwright manualmente ou verifique o caminho do seu navegador.")
            return False

        if debug_ui:
            print("DEBUG_UI ATIVO: navegador visível.")
        print("Iniciando navegador do sistema (aguarde)...")
        browser = p.chromium.launch(executable_path=navegador_executavel, headless=(not debug_ui), slow_mo=(250 if debug_ui else 0))
        context = browser.new_context()
        page = context.new_page()
        
        print(f"Acessando {URL_SISTEMA}...")
        try:
            page.goto(URL_SISTEMA)
        except Exception as e:
            print(f"Erro ao acessar URL: {e}")
            fechar_browser(browser)
            return False

        # 1. LOGIN
        print("Realizando Login...")
        try:
            # Preenche apenas se os campos existirem
            if page.locator(SELETOR_USUARIO).count() > 0:
                page.fill(SELETOR_USUARIO, usuario)
                page.fill(SELETOR_SENHA, senha)
                page.click(SELETOR_BTN_LOGIN)
                page.wait_for_load_state('networkidle')
            else:
                print("Campos de login não encontrados ou já logado. Prosseguindo...")
        except Exception as e:
            print(f"Erro no login (pode ser necessário ajuste manual): {e}")
            salvar_debug(page, "login")
            if debug_ui:
                try:
                    page.wait_for_timeout(180000)
                except Exception:
                    pass
            fechar_browser(browser)
            return False

        if page.locator(SELETOR_COMBO_MALHA).count() == 0:
            ok_menu = navegar_para_programador_frames(page, debug_ui)
            if not ok_menu:
                print("Menu não encontrado ou não clicável.")
        
        # Espera o combo de Malha aparecer
        ctx = find_frame_with_selector(page, SELETOR_COMBO_MALHA)
        try:
            ctx.wait_for_selector(SELETOR_COMBO_MALHA, timeout=30000)
        except:
            print("Não encontrou o combo de Malha. Verifique se está na tela correta.")
            salvar_debug(page, "combo_malha_nao_encontrado")
            if debug_ui:
                try:
                    page.wait_for_timeout(180000)
                except Exception:
                    pass
            fechar_browser(browser)
            return False

        # 3. IDENTIFICAR OPÇÕES DE MALHA
        print("Mapeando Malhas...")
        try:
            # Espera o combo de Malha estar carregado e acessível
            ctx.wait_for_selector(SELETOR_COMBO_MALHA, state="visible", timeout=30000)
        except:
            print("Não encontrou o combo de Malha. Verifique se está na tela correta.")
            salvar_debug(page, "combo_malha_invisivel")
            fechar_browser(browser)
            return False

        # Pega todas as opções de Malha (VIA JAVASCRIPT - Mais rápido)
        lista_malhas = ctx.evaluate(f"""() => {{
            const options = Array.from(document.querySelectorAll("{SELETOR_COMBO_MALHA} option"));
            return options.map(o => {{
                return {{ text: o.innerText.trim(), value: o.value }};
            }}).filter(o => o.text && !o.text.includes('Selecione') && o.value).map(o => o.text);
        }}""")
        
        print(f"Malhas encontradas: {len(lista_malhas)}")
        print(lista_malhas)
        if not lista_malhas:
            salvar_debug(page, "malhas_vazias")
            fechar_browser(browser)
            return False

        dados_consolidados = []

        # 4. LOOP DUPLO: MALHAS -> REGIÕES
        for malha in lista_malhas:
            print(f"\n>>> Processando Malha: {malha} <<<")
            
            # Seleciona a Malha
            # Ao selecionar Malha, o JSF dispara um evento para carregar as Regiões.
            # Precisamos garantir que isso terminou antes de ler as regiões.
            
            # Estratégia: Pegar o conteúdo atual do combo de região antes da troca para comparar depois
            try:
                conteudo_antigo_regiao = ctx.evaluate(f"document.querySelector('{SELETOR_COMBO_REGIAO}').innerHTML")
            except:
                conteudo_antigo_regiao = ""
            
            print(f"  Trocando para Malha: {malha}...")
            ctx.select_option(SELETOR_COMBO_MALHA, label=malha)
            
            print("  Aguardando atualização das regiões...")
            deadline_regioes = time.time() + 15
            while time.time() < deadline_regioes:
                try:
                    conteudo_novo = ctx.evaluate(f"document.querySelector('{SELETOR_COMBO_REGIAO}').innerHTML")
                    if conteudo_novo != conteudo_antigo_regiao:
                        break
                except:
                    pass
                time.sleep(0.2)
            time.sleep(0.5)
            
            # Garante rede ociosa
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except:
                pass

            # -------------------------------------------------------------
            # LER AS REGIÕES DESTA MALHA E VOLTAR A ITERAR POR REGIÃO
            # -------------------------------------------------------------
            lista_regioes_objs = ctx.evaluate(f"""() => {{
                const options = Array.from(document.querySelectorAll("{SELETOR_COMBO_REGIAO} option"));
                return options.map(o => {{
                    return {{ text: o.innerText.trim(), value: o.value }};
                }}).filter(o => o.text && !o.text.includes('Selecione') && o.value);
            }}""")
            
            print(f"  Regiões na Malha {malha}: {len(lista_regioes_objs)}")
            count_extraidos_malha = 0

            for regiao_obj in lista_regioes_objs:
                regiao = regiao_obj['text']
                regiao_valor = regiao_obj['value']
                
                print(f"  --- Extraindo Região: {regiao} ---")
                
                # Seleciona a região pelo VALOR
                try:
                    ctx.select_option(SELETOR_COMBO_REGIAO, value=regiao_valor)
                except Exception as e:
                    print(f"    [ERRO CRÍTICO] Falha ao selecionar região {regiao}: {e}")
                    continue
                
                time.sleep(0.2) # OTIMIZAÇÃO: Pausa rápida ao invés de aguardar rede

                ctx_tabela, _ = encontrar_contexto_tabela(page)
                
                # TÉCNICA DE MARCADOR DOM: Injeta um atributo falso na tabela. 
                # Quando o AJAX recarregar a tabela (mesmo que vazia), o atributo some na mesma hora!
                try:
                    ctx_tabela.evaluate("""() => { 
                        document.querySelectorAll('table').forEach(t => t.setAttribute('data-extrator', 'pesquisando'));
                    }""")
                except:
                    pass

                print("    -> Pesquisando...")
                ctx.click(SELETOR_BTN_PESQUISAR, no_wait_after=True)
                
                # Aguarda a resposta do AJAX
                deadline_pesquisa = time.time() + 60
                while time.time() < deadline_pesquisa:
                    try:
                        ainda_pesquisando = ctx_tabela.evaluate("""() => { 
                            return document.querySelectorAll('table[data-extrator=\"pesquisando\"]').length > 0;
                        }""")
                    except:
                        ainda_pesquisando = False
                        
                    if not ainda_pesquisando:
                        break # O AJAX terminou e reconstruiu a tabela!
                    time.sleep(0.2) # OTIMIZAÇÃO: Fast polling (0.2s) ao invés de 1.0s

                time.sleep(1.0) # GARANTE que o navegador renderizou a nova tabela
                ctx_tabela, _ = encontrar_contexto_tabela(page)
                
                # OTIMIZAÇÃO: Verifica explicitamente se há linhas de dados no corpo da tabela (tbody)
                tem_dados = ctx_tabela.evaluate("""() => {
                    const tbody = document.querySelector('tbody[id$=":tb"]');
                    return tbody && tbody.querySelectorAll('tr').length > 0;
                }""")
                
                if not tem_dados:
                    print("    -> Sem registros nesta região.")
                    continue

                # --- CORREÇÃO DO BUG DE PAGINAÇÃO DO SISTEMA (FORÇAR PÁGINA 1) ---
                try:
                    precisa_voltar = ctx_tabela.evaluate("""() => {
                        // Verifica se já estamos na página 1 (célula ativa)
                        const activePage = document.querySelector('td.rich-datascr-act');
                        if (activePage && activePage.innerText.trim() === '1') {
                            return false; 
                        }

                        const tds = Array.from(document.querySelectorAll('td.rich-datascr-button, td.rich-datascr-inact'));
                        
                        // 1. Tenta achar o botão «« (Primeira Página)
                        let btn = tds.find(td => td.innerText.includes('««') && !td.className.includes('dsbld'));
                        
                        // 2. Se não achar, tenta clicar direto no número '1' (página inativa)
                        if (!btn) {
                            btn = tds.find(td => td.innerText.trim() === '1');
                        }
                        
                        if (btn) {
                            // Clica no link interno, se houver (o JSF as vezes põe o evento no <a>)
                            const link = btn.querySelector('a');
                            if (link) { link.click(); }
                            else { btn.click(); }
                            return true;
                        }
                        return false;
                    }""")
                except:
                    precisa_voltar = False

                if precisa_voltar:
                    print("    [Aviso] O sistema não voltou para a primeira página. Forçando retorno para a Página 1...")
                    try:
                        ctx_tabela.wait_for_function("""() => { 
                            const active = document.querySelector('td.rich-datascr-act');
                            return active && active.innerText.trim() === '1';
                        }""", timeout=15000)
                    except:
                        time.sleep(2.0) # Fallback em caso de erro
                    time.sleep(0.5) # Aguarda renderização da nova página 1
                # -----------------------------------------------------------------
                
                # LÓGICA DE PAGINAÇÃO
                pagina_atual = 1
                count_extraidos_regiao = 0
                
                while True:
                    print(f"    [Página {pagina_atual}] Extraindo dados...")
                    
                    # ---------------------------------------------------------
                    # OTIMIZAÇÃO: EXTRAÇÃO VIA JAVASCRIPT (MUITO MAIS RÁPIDO)
                    # ---------------------------------------------------------
                    
                    dados_pagina = ctx_tabela.evaluate("""() => {
                        const tabelas = Array.from(document.querySelectorAll('table'));
                        let melhorTabela = null;
                        
                        // Encontra a tabela principal de resultados
                        for (const tab of tabelas) {
                            if (tab.offsetParent !== null) { // is visible
                                if (tab.classList.contains('rich-table') || tab.querySelector('tbody[id$=":tb"]')) {
                                    melhorTabela = tab;
                                    break;
                                }
                            }
                        }
                        
                        if (!melhorTabela) {
                            let maxLinhas = 0;
                            for (const tab of tabelas) {
                                if (tab.offsetParent !== null) { 
                                    const linhas = tab.querySelectorAll('tr').length;
                                    if (linhas > maxLinhas) { maxLinhas = linhas; melhorTabela = tab; }
                                }
                            }
                        }
                        
                        if (!melhorTabela) return null;
                        
                        const linhas = Array.from(melhorTabela.querySelectorAll('tr'));
                        
                        // Tenta achar cabeçalho
                        let cabecalhos = [];
                        let headerRow = melhorTabela.querySelector('thead tr');
                        if (!headerRow) headerRow = linhas[0];
                        
                        if (headerRow) {
                            const cells = Array.from(headerRow.querySelectorAll('th, td'));
                            cabecalhos = cells.map((c, i) => {
                                let txt = c.innerText.trim();
                                if (!txt) txt = c.getAttribute('title') || '';
                                return txt || `col_${i}`;
                            });
                        }
                        
                        // Tenta achar corpo
                        let bodyRows = [];
                        const tbody = melhorTabela.querySelector('tbody');
                        if (tbody) {
                            bodyRows = Array.from(tbody.querySelectorAll('tr'));
                        } else {
                            bodyRows = linhas.slice(1);
                        }
                        
                        const resultados = [];
                        
                        for (const row of bodyRows) {
                            // Ignora paginação
                            if (row.innerText.includes('«') || row.innerText.includes('»')) continue;
                            
                            const cols = Array.from(row.querySelectorAll('td'));
                            if (cols.length === 0) continue;
                            
                            const dadosLinha = cols.map(col => {
                                let txt = col.innerText.trim();
                                if (!txt) {
                                    const input = col.querySelector('input');
                                    if (input) txt = input.value || '';
                                }
                                if (!txt) {
                                    const a = col.querySelector('a');
                                    if (a) txt = a.innerText.trim();
                                }
                                return txt.replace(/\\n/g, ' ').replace(/\\r/g, '');
                            });
                            
                            // Ignora linhas vazias (sem dados úteis)
                            const temDados = dadosLinha.some(d => d.trim() !== '');
                            if (!temDados) continue;
                            
                            // Ajusta tamanho
                            while (dadosLinha.length < cabecalhos.length) dadosLinha.push('');
                            if (dadosLinha.length > cabecalhos.length) dadosLinha.length = cabecalhos.length;
                            
                            // Cria objeto
                            const obj = {};
                            cabecalhos.forEach((key, i) => obj[key] = dadosLinha[i]);
                            resultados.push(obj);
                        }
                        
                        return resultados;
                    }""")
                    
                    if dados_pagina:
                        for item in dados_pagina:
                            item['Ref_Malha'] = malha
                            # GARANTE O NOME DA REGIÃO CORRETA SELECIONADA NO COMBOBOX
                            item['Ref_Regiao'] = regiao 
                            dados_consolidados.append(item)
                        
                        qtd_pagina = len(dados_pagina)
                        count_extraidos_regiao += qtd_pagina
                        print(f"    -> {qtd_pagina} registros na página {pagina_atual}.")
                    else:
                        tentativas = 0
                        while tentativas < 3 and not dados_pagina:
                            time.sleep(1)
                            ctx_tabela, _ = encontrar_contexto_tabela(page)
                            dados_pagina = ctx_tabela.evaluate("""() => {
                                const tabelas = Array.from(document.querySelectorAll('table'));
                                let melhorTabela = null;
                                for (const tab of tabelas) {
                                    const visivel = (tab.offsetParent !== null) || (tab.getClientRects && tab.getClientRects().length > 0);
                                    if (visivel && (tab.classList.contains('rich-table') || tab.querySelector('tbody[id$=":tb"]'))) {
                                        melhorTabela = tab;
                                        break;
                                    }
                                }
                                if (!melhorTabela) {
                                    let maxLinhas = 0;
                                    for (const tab of tabelas) {
                                        const visivel = (tab.offsetParent !== null) || (tab.getClientRects && tab.getClientRects().length > 0);
                                        if (!visivel) continue;
                                        const linhas = tab.querySelectorAll('tr').length;
                                        if (linhas > maxLinhas) { maxLinhas = linhas; melhorTabela = tab; }
                                    }
                                }
                                if (!melhorTabela) return null;
                                const linhas = Array.from(melhorTabela.querySelectorAll('tr'));
                                let cabecalhos = [];
                                let headerRow = melhorTabela.querySelector('thead tr');
                                if (!headerRow) headerRow = linhas[0];
                                if (headerRow) {
                                    const cells = Array.from(headerRow.querySelectorAll('th, td'));
                                    cabecalhos = cells.map((c, i) => {
                                        let txt = c.innerText.trim();
                                        if (!txt) txt = c.getAttribute('title') || '';
                                        return txt || `col_${i}`;
                                    });
                                }
                                let bodyRows = [];
                                const tbody = melhorTabela.querySelector('tbody');
                                if (tbody) bodyRows = Array.from(tbody.querySelectorAll('tr'));
                                else bodyRows = linhas.slice(1);
                                const resultados = [];
                                for (const row of bodyRows) {
                                    if (row.innerText.includes('«') || row.innerText.includes('»')) continue;
                                    const cols = Array.from(row.querySelectorAll('td'));
                                    if (cols.length === 0) continue;
                                    const dadosLinha = cols.map(col => {
                                        let txt = col.innerText.trim();
                                        if (!txt) {
                                            const input = col.querySelector('input');
                                            if (input) txt = input.value || '';
                                        }
                                        if (!txt) {
                                            const a = col.querySelector('a');
                                            if (a) txt = a.innerText.trim();
                                        }
                                        return txt.replace(/\\n/g, ' ').replace(/\\r/g, '');
                                    });
                                    const temDados = dadosLinha.some(d => d.trim() !== '');
                                    if (!temDados) continue;
                                    while (dadosLinha.length < cabecalhos.length) dadosLinha.push('');
                                    if (dadosLinha.length > cabecalhos.length) dadosLinha.length = cabecalhos.length;
                                    const obj = {};
                                    cabecalhos.forEach((key, i) => obj[key] = dadosLinha[i]);
                                    resultados.push(obj);
                                }
                                return resultados;
                            }""")
                            tentativas += 1
                        if dados_pagina:
                            for item in dados_pagina:
                                item['Ref_Malha'] = malha
                                item['Ref_Regiao'] = regiao
                                dados_consolidados.append(item)
                            qtd_pagina = len(dados_pagina)
                            count_extraidos_regiao += qtd_pagina
                            print(f"    -> {qtd_pagina} registros na página {pagina_atual}.")
                        else:
                            print("    [Aviso] Tabela não encontrada ou vazia nesta página.")
                    
                    # ---------------------------------------------------------
                    # LÓGICA DE NAVEGAÇÃO (PRÓXIMA PÁGINA)
                    # ---------------------------------------------------------
                        
                    proximo_btn_existe = ctx_tabela.evaluate("""() => {
                        const tds = Array.from(document.querySelectorAll('td.rich-datascr-button'));
                        const btn = tds.find(td => td.innerText.includes('»') && !td.innerText.includes('»»'));
                        if (btn && !btn.className.includes('rich-datascr-button-dsbld')) {
                            const link = btn.querySelector('a');
                            if (link) { link.click(); } else { btn.click(); }
                            return true;
                        }
                        return false;
                    }""")
                    
                    if proximo_btn_existe:
                        print(f"    -> Navegando para a página {pagina_atual + 1} (aguardando carregamento)...")
                        try:
                            # Espera nativa do Playwright pelo número da página no componente JSF
                            ctx_tabela.wait_for_function("""(prox) => { 
                                const active = document.querySelector('td.rich-datascr-act');
                                return active && active.innerText.trim() === String(prox);
                            }""", arg=(pagina_atual + 1), timeout=15000)
                        except:
                            time.sleep(2.0) # Fallback seguro
                        time.sleep(0.4) # Garante que os dados da nova página foram pintados
                            
                        pagina_atual += 1
                    else:
                        print("    -> Fim da paginação da região.")
                        break

                print(f"  -> Total extraído na Região {regiao}: {count_extraidos_regiao} registros.")
                count_extraidos_malha += count_extraidos_regiao

            print(f"-> Total extraído na Malha {malha}: {count_extraidos_malha} registros.")
            
            if count_extraidos_malha == 0:
                 print(f"-> Sem dados extraídos na Malha {malha}.")

        # 5. SALVAR ARQUIVO (E BANCO DE DADOS)
        if dados_consolidados:
            df = pd.DataFrame(dados_consolidados)
            
            # --- FILTRAR DUPLICATAS POR REGIÃO PRINCIPAL (USANDO MESÃO) ---
            try:
                import glob
                pasta_mesao = r"I:\IT\ODCO\PROGRAMACAO_MT\Mesao_Diario"
                arquivos_mesao = glob.glob(os.path.join(pasta_mesao, "Mesao_*.xlsx"))
                if arquivos_mesao:
                    arquivo_alvo = max(arquivos_mesao, key=os.path.getmtime)
                    print(f"\n[DEDUPLICAÇÃO] Importando Mesão para definir região principal: {os.path.basename(arquivo_alvo)}")
                    df_mesao = pd.read_excel(arquivo_alvo)
                    
                    # Nome das colunas podem sofrer de problemas de encoding
                    col_solic_mesao = next((c for c in df_mesao.columns if 'solicita' in c.lower() and 'status' not in c.lower()), None)
                    col_regiao_mesao = next((c for c in df_mesao.columns if 'regi' in c.lower()), None)
                    
                    col_solic_df = next((c for c in df.columns if 'solicita' in c.lower()), None)
                    
                    if col_solic_mesao and col_regiao_mesao and col_solic_df:
                        # Padroniza Solicitações para facilitar o Merge
                        df['_solic_key'] = df[col_solic_df].astype(str).str.strip().str.lstrip('0')
                        df_mesao['_solic_key'] = df_mesao[col_solic_mesao].astype(str).str.strip().str.lstrip('0')
                        
                        # Extrai a sigla da região no Mesão (Ex: "PM")
                        df_mesao['Regiao_Sigla'] = df_mesao[col_regiao_mesao].astype(str).str[:2].str.upper().str.strip()
                        mapa_regioes = df_mesao.set_index('_solic_key')['Regiao_Sigla'].to_dict()
                        
                        df_antes_count = len(df)
                        
                        # Função de filtragem
                        def manter_linha(row):
                            solic = row['_solic_key']
                            if solic in mapa_regioes:
                                ref_reg = str(row.get('Ref_Regiao', '')).strip().upper()
                                # Só mantém se for a Região principal
                                return ref_reg.startswith(mapa_regioes[solic])
                            # Se não estive mapeada no mesão, matemos (para que ela não suma totalmente)
                            return True
                            
                        # Filtra e dropa colunas temporárias
                        df['manter'] = df.apply(manter_linha, axis=1)
                        df = df[df['manter']].drop(columns=['manter', '_solic_key'])
                        
                        # Se ainda houver duplicatas da MESMA solicitação por outro motivo (garante unicidade)
                        df = df.drop_duplicates(subset=[col_solic_df], keep='first')
                        
                        print(f"    -> Deduplicação Concluída: {df_antes_count} registros -> {len(df)} registros.")
                    else:
                        print("    -> [AVISO] Colunas necessárias no Mesão não encontradas. Deduplicação ignorada.")
            except Exception as e:
                print(f"    -> [ERRO] Falha ao processar Mesão para deduplicação: {e}")
                if '_solic_key' in df.columns:
                    df = df.drop(columns=['_solic_key'])
                if 'manter' in df.columns:
                    df = df.drop(columns=['manter'])

            # --- 6. SINCRONIA DE E-MAIL (VANGUARD) ---
            try:
                # Identificar protocolos urgentes
                # Regra: Urgência = SIM/S e Situação = APROVADA (conforme dashboard)
                col_urg = next((c for c in df.columns if 'urg' in c.lower()), None)
                col_solic = next((c for c in df.columns if 'solicita' in c.lower()), None)
                
                if col_urg and col_solic:
                    # Filtra apenas quem é Urgente
                    mask_urg = df[col_urg].astype(str).str.upper().str.contains('SIM|S')
                    ids_urgentes = df[mask_urg][col_solic].unique().tolist()
                    
                    if ids_urgentes:
                        print(f"\n[EMAIL] Sincronizando e-mails para {len(ids_urgentes)} protocolos urgentes...")
                        ids_str = ",".join([str(i) for i in ids_urgentes])
                        path_script = os.path.join(os.path.dirname(__file__), "scripts", "sync_emails.ps1")
                        
                        # Chama o PowerShell silenciosamente
                        cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", path_script, ids_str]
                        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
                        
                        if result.returncode == 0:
                            try:
                                map_email = json.loads(result.stdout)
                                # Adiciona a coluna Tem_Email baseada no retorno do JSON
                                df['Tem_Email'] = df[col_solic].astype(str).map(lambda x: map_email.get(x, False))
                                print(f"    -> Sincronização concluída. {df['Tem_Email'].sum()} e-mails confirmados.")
                            except Exception as e_json:
                                print(f"    -> [ERRO] Falha ao processar JSON do e-mail: {e_json}")
                                df['Tem_Email'] = False
                        else:
                            print("    -> [AVISO] Falha no motor de e-mail (Outlook pode estar fechado).")
                            df['Tem_Email'] = False
                    else:
                        print("\n[EMAIL] Nenhuma urgência detectada para sincronização.")
                        df['Tem_Email'] = False
                else:
                    df['Tem_Email'] = False
            except Exception as e_email:
                print(f"\n[AVISO] Erro na sincronia de e-mails: {e_email}")
                df['Tem_Email'] = False

            # --- 1. SALVAR NO BANCO DE DADOS (SQLite) ---
            try:
                import db_manager
                print("\n[DB] Salvando dados no banco local...")
                db_manager.salvar_dados(df)
            except Exception as e:
                print(f"[ERRO DB] Falha ao salvar no banco de dados: {e}")
                salvar_debug(page, "db_salvar_falhou")
                fechar_browser(browser)
                return False

            db_manager.publicar_db_rede()

            # --- 2. SALVAR EXCEL (BACKUP / RELATÓRIO) ---
            # Mantemos o Excel como um artefato visível para o usuário, 
            # mas agora o sistema principal (Dashboard) pode ler do banco.
            
            # --- GERENCIAMENTO DE ARQUIVOS ---
            pasta_destino = "relatorios"
            # Cria a pasta se não existir
            if not os.path.exists(pasta_destino):
                os.makedirs(pasta_destino)

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            # Define o caminho completo
            arquivo_saida = os.path.join(pasta_destino, f"relatorio_demanda_{timestamp}.xlsx")
            
            try:
                df.to_excel(arquivo_saida, index=False)
                print(f"\n[SUCESSO] Relatório salvo em: {arquivo_saida}")

                # --- ROTAÇÃO DE ARQUIVOS (LIMPEZA AUTOMÁTICA) ---
                # Mantém apenas os 5 arquivos mais recentes para não lotar o disco
                # Lista todos os relatórios na pasta
                arquivos_existentes = sorted(glob.glob(os.path.join(pasta_destino, "relatorio_demanda_*.xlsx")), key=os.path.getmtime, reverse=True)
                
                QTD_MANTER = 5
                if len(arquivos_existentes) > QTD_MANTER:
                    print(f"\n[MANUTENÇÃO] Limpando relatórios antigos (Mantendo os {QTD_MANTER} mais recentes)...")
                    for arquivo_velho in arquivos_existentes[QTD_MANTER:]:
                        try:
                            os.remove(arquivo_velho)
                            print(f"    -> Removido: {arquivo_velho}")
                        except Exception as e:
                            print(f"    -> Erro ao remover {arquivo_velho}: {e}")

            except Exception as e:
                print(f"\n[ERRO] Não foi possível salvar o arquivo Excel: {e}")
                print("Tentando salvar como CSV de backup...")
                # Backup CSV também na pasta relatorios
                arquivo_csv = os.path.join(pasta_destino, f"relatorio_demanda_{timestamp}.csv")
                df.to_csv(arquivo_csv, index=False, sep=";")
                print(f"Backup salvo em: {arquivo_csv}")

            if 'arquivo_saida' in locals():
                print(f"\nSucesso! Arquivo gerado: {arquivo_saida}")
            print(df.head())
        else:
            print("\nNenhum dado foi coletado. Verifique os seletores.")
            salvar_debug(page, "nenhum_dado_coletado")
            fechar_browser(browser)
            return False

        fechar_browser(browser)
        
        # MÉTRICA DE TEMPO
        end_time = time.time()
        duration_seconds = int(end_time - start_time)
        tempo_formatado = str(datetime.timedelta(seconds=duration_seconds))
        print("\n" + "="*50)
        print("RESUMO DA EXECUÇÃO")
        print(f"Tempo total: {tempo_formatado}")
        if dados_consolidados:
            print(f"Registros extraídos: {len(dados_consolidados)}")
        print("="*50 + "\n")
        return True

if __name__ == "__main__":
    sys.exit(0 if extrair_dados() else 1)
 