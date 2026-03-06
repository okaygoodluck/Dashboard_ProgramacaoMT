import time
import pandas as pd
from playwright.sync_api import sync_playwright

# --- CONFIGURAÇÕES ---
URL_SISTEMA = "http://gdis-pm/gdispm/"  # Ex: http://sistema.empresa.com.br
USUARIO = "c057573"
SENHA = "@K3nn3d!38124001"

# Seletores (Inspecione o elemento no navegador e copie o Seletor CSS ou XPath)
SELETOR_USUARIO = "input[id='formLogin:userid']"  # Ajuste conforme seu sistema
SELETOR_SENHA = "input[id='formLogin:password']"      # Ajuste conforme seu sistema
SELETOR_BTN_LOGIN = "input[id='formLogin:botao']" # Ajuste conforme seu sistema

# Seletores da Tela de Consulta
SELETOR_COMBO_MALHA = "select[id='formBusca:malha']"    # O * significa "contém", ajuda em IDs dinâmicos do JSF
SELETOR_COMBO_REGIAO = "select[id='formBusca:area']"
SELETOR_BTN_PESQUISAR = "input[id='formBusca:btnSalvar']" # Ou button[id*='pesquisar']

# Seletor da Tabela de Resultados
SELETOR_TABELA = "table[id='formResultTable']" # Ajuste para a tabela principal

def extrair_dados():
    start_time = time.time() # Início da medição de tempo
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
        import os
        for caminho in caminhos_navegador:
            if os.path.exists(caminho):
                navegador_executavel = caminho
                print(f"Navegador encontrado: {caminho}")
                break
        
        if not navegador_executavel:
            print("ERRO: Não encontrei Edge ou Chrome instalado nos locais padrão.")
            print("Instale o Playwright manualmente ou verifique o caminho do seu navegador.")
            return

        # headless=True roda em "modo invisível" (sem janela)
        # channel="msedge" ou "chrome" força o uso do navegador instalado
        print("Iniciando navegador em modo invisível (aguarde)...")
        browser = p.chromium.launch(executable_path=navegador_executavel, headless=True) 
        context = browser.new_context()
        page = context.new_page()
        
        print(f"Acessando {URL_SISTEMA}...")
        try:
            page.goto(URL_SISTEMA)
        except Exception as e:
            print(f"Erro ao acessar URL: {e}")
            return

        # 1. LOGIN
        print("Realizando Login...")
        try:
            # Preenche apenas se os campos existirem
            if page.locator(SELETOR_USUARIO).count() > 0:
                page.fill(SELETOR_USUARIO, USUARIO)
                page.fill(SELETOR_SENHA, SENHA)
                page.click(SELETOR_BTN_LOGIN)
                page.wait_for_load_state('networkidle')
            else:
                print("Campos de login não encontrados ou já logado. Prosseguindo...")
        except Exception as e:
            print(f"Erro no login (pode ser necessário ajuste manual): {e}")

        #2. NAVEGAÇÃO ATÉ A TELA (Se necessário)
        #Se precisar clicar em menus, adicione aqui:
        try:
            page.click("text=Perfil", timeout=5000)
            page.click("text=Programador", timeout=5000)
        except:
            print("Menu não encontrado ou já na tela correta.")
        
        # Espera o combo de Malha aparecer
        try:
            page.wait_for_selector(SELETOR_COMBO_MALHA, timeout=10000)
        except:
            print("Não encontrou o combo de Malha. Verifique se está na tela correta.")
            # Pause para você navegar manualmente se precisar
            # page.pause() 

        # 3. IDENTIFICAR OPÇÕES DE MALHA
        print("Mapeando Malhas...")
        try:
            # Espera o combo de Malha estar carregado e acessível
            page.wait_for_selector(SELETOR_COMBO_MALHA, state="visible", timeout=15000)
        except:
            print("Não encontrou o combo de Malha. Verifique se está na tela correta.")
            # page.pause()
            return

        # Pega todas as opções de Malha (VIA JAVASCRIPT - Mais rápido)
        lista_malhas = page.evaluate(f"""() => {{
            const options = Array.from(document.querySelectorAll("{SELETOR_COMBO_MALHA} option"));
            return options.map(o => {{
                return {{ text: o.innerText.trim(), value: o.value }};
            }}).filter(o => o.text && !o.text.includes('Selecione') && o.value).map(o => o.text);
        }}""")
        
        print(f"Malhas encontradas: {len(lista_malhas)}")
        print(lista_malhas)

        dados_consolidados = []

        # 4. LOOP DUPLO: MALHAS -> REGIÕES
        for malha in lista_malhas:
            print(f"\n>>> Processando Malha: {malha} <<<")
            
            # Seleciona a Malha
            # Ao selecionar Malha, o JSF dispara um evento para carregar as Regiões.
            # Precisamos garantir que isso terminou antes de ler as regiões.
            
            # Estratégia: Pegar o conteúdo atual do combo de região antes da troca para comparar depois
            try:
                conteudo_antigo_regiao = page.evaluate(f"document.querySelector('{SELETOR_COMBO_REGIAO}').innerText")
            except:
                conteudo_antigo_regiao = ""
            
            print(f"  Trocando para Malha: {malha}...")
            page.select_option(SELETOR_COMBO_MALHA, label=malha)
            
            # Espera ativa pela mudança do conteúdo do combo de região
            # O sistema usa AJAX, então o combo deve mudar.
            print("  Aguardando atualização das regiões...")
            try:
                # Espera até que o texto do select seja diferente do antigo E tenha mais que apenas "Selecione"
                page.wait_for_function(
                    f"""() => {{
                        const el = document.querySelector('{SELETOR_COMBO_REGIAO}');
                        return el && el.innerText !== {repr(conteudo_antigo_regiao)} && el.options.length > 1;
                    }}""",
                    timeout=10000
                )
            except:
                print("  [Aviso] Timeout esperando atualização do combo de regiões. Pode ser que as regiões sejam iguais ou o sistema está lento.")
                time.sleep(2) # Fallback final
            
            # Garante rede ociosa
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except:
                pass

            # Ler as Regiões desta Malha (VIA JAVASCRIPT)
            # Retorna lista de objetos para usar o VALUE no select (mais seguro)
            lista_regioes_objs = page.evaluate(f"""() => {{
                const options = Array.from(document.querySelectorAll("{SELETOR_COMBO_REGIAO} option"));
                return options.map(o => {{
                    return {{ text: o.innerText.trim(), value: o.value }};
                }}).filter(o => o.text && !o.text.includes('Selecione') && o.value);
            }}""")
            
            print(f"  Regiões na Malha {malha}: {len(lista_regioes_objs)}")

            # Loop das Regiões
            for regiao_obj in lista_regioes_objs:
                regiao = regiao_obj['text'] # Mantém compatibilidade com o resto do código
                regiao_valor = regiao_obj['value']
                
                print(f"  --- Extraindo Região: {regiao} ---")
                
                # Seleciona a região pelo VALOR
                try:
                    page.select_option(SELETOR_COMBO_REGIAO, value=regiao_valor)
                except Exception as e:
                    print(f"    [ERRO CRÍTICO] Falha ao selecionar região {regiao}: {e}")
                    continue
                
                # Garante que a seleção pegou
                try:
                     page.wait_for_load_state("networkidle", timeout=2000)
                except:
                     pass
                
                # Clica em Pesquisar
                # print("  Pesquisando...")
                page.click(SELETOR_BTN_PESQUISAR)
                
                # OTIMIZAÇÃO: Espera tabela aparecer ou rede ociosa
                try:
                    page.wait_for_load_state("networkidle", timeout=3000)
                    # Espera pelo menos uma tabela aparecer
                    page.wait_for_selector("table", timeout=3000)
                except:
                    time.sleep(2) # Fallback 
                
                # LÓGICA DE PAGINAÇÃO
                # Loop para clicar no botão "Próximo" (») até desabilitar
                pagina_atual = 1
                count_extraidos = 0 # Inicializa contador da região
                
                while True:
                    print(f"    [Página {pagina_atual}] Extraindo dados...")
                    
                    # ---------------------------------------------------------
                    # OTIMIZAÇÃO: EXTRAÇÃO VIA JAVASCRIPT (MUITO MAIS RÁPIDO)
                    # ---------------------------------------------------------
                    
                    dados_pagina = page.evaluate("""() => {
                        const tabelas = Array.from(document.querySelectorAll('table'));
                        let melhorTabela = null;
                        let maxLinhas = 0;
                        
                        // Encontra a maior tabela visível
                        for (const tab of tabelas) {
                            if (tab.offsetParent !== null) { // is visible
                                const linhas = tab.querySelectorAll('tr').length;
                                if (linhas > maxLinhas) {
                                    maxLinhas = linhas;
                                    melhorTabela = tab;
                                }
                            }
                        }
                        
                        if (!melhorTabela || maxLinhas <= 1) return null;
                        
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
                            item['Ref_Regiao'] = regiao
                            dados_consolidados.append(item)
                        
                        qtd_pagina = len(dados_pagina)
                        count_extraidos += qtd_pagina
                        print(f"    -> {qtd_pagina} registros na página {pagina_atual}.")
                    else:
                        print("    [Aviso] Tabela não encontrada nesta página.")
                    
                    # ---------------------------------------------------------
                    # LÓGICA DE NAVEGAÇÃO (PRÓXIMA PÁGINA)
                    # ---------------------------------------------------------
                    # Procura o botão "Próximo" (»)
                    
                    # OTIMIZAÇÃO: Usar evaluate para verificar botão também é mais rápido
                    proximo_btn_existe = page.evaluate("""() => {
                        const tds = Array.from(document.querySelectorAll('td.rich-datascr-button'));
                        const btn = tds.find(td => td.innerText.includes('»') && !td.innerText.includes('»»'));
                        if (btn && !btn.className.includes('rich-datascr-button-dsbld')) {
                            btn.click(); // Clica via JS direto
                            return true;
                        }
                        return false;
                    }""")
                    
                    if proximo_btn_existe:
                        print("    -> Navegando para a próxima página...")
                        # Espera carregar (RichFaces usa AJAX)
                        # OTIMIZAÇÃO: Reduzido de 4s fixo para espera dinâmica
                        try:
                            # Espera que o spinner de carregamento suma OU espera rede ociosa
                            # Se não tiver spinner, usamos um sleep menor
                            page.wait_for_load_state("networkidle", timeout=3000)
                            time.sleep(1.5) # Reduzido de 4s para 1.5s
                        except:
                            time.sleep(2) # Fallback seguro
                            
                        pagina_atual += 1
                    else:
                        print("    -> Fim da paginação.")
                        break

                print(f"    -> Total extraído nesta região: {count_extraidos} registros.")
                
                if count_extraidos == 0:
                     print("    -> Sem dados extraídos nesta região.")
                     # Tira um print para debug se falhar
                     # page.screenshot(path=f"debug_erro_{regiao}.png")

        # 5. SALVAR ARQUIVO (E BANCO DE DADOS)
        if dados_consolidados:
            df = pd.DataFrame(dados_consolidados)
            
            # --- 1. SALVAR NO BANCO DE DADOS (SQLite) ---
            try:
                import db_manager
                print("\n[DB] Salvando dados no banco local...")
                db_manager.salvar_dados(df)
            except Exception as e:
                print(f"[ERRO DB] Falha ao salvar no banco de dados: {e}")

            # --- 2. SALVAR EXCEL (BACKUP / RELATÓRIO) ---
            # Mantemos o Excel como um artefato visível para o usuário, 
            # mas agora o sistema principal (Dashboard) pode ler do banco.
            
            # --- GERENCIAMENTO DE ARQUIVOS ---
            pasta_destino = "relatorios"
            import os
            # Cria a pasta se não existir
            if not os.path.exists(pasta_destino):
                os.makedirs(pasta_destino)

            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            # Define o caminho completo
            arquivo_saida = os.path.join(pasta_destino, f"relatorio_demanda_{timestamp}.xlsx")
            
            try:
                df.to_excel(arquivo_saida, index=False)
                print(f"\n[SUCESSO] Relatório salvo em: {arquivo_saida}")

                # --- ROTAÇÃO DE ARQUIVOS (LIMPEZA AUTOMÁTICA) ---
                # Mantém apenas os 5 arquivos mais recentes para não lotar o disco
                import glob
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

        browser.close()
        
        # MÉTRICA DE TEMPO
        end_time = time.time()
        duration_seconds = int(end_time - start_time)
        import datetime
        tempo_formatado = str(datetime.timedelta(seconds=duration_seconds))
        print(f"\n" + "="*50)
        print(f"RESUMO DA EXECUÇÃO")
        print(f"Tempo total: {tempo_formatado}")
        if dados_consolidados:
            print(f"Registros extraídos: {len(dados_consolidados)}")
        print("="*50 + "\n")

if __name__ == "__main__":
    extrair_dados()
