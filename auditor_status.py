"""
Módulo Desacoplado de Auditoria Remota de Status (GDIS-PM)
Consulta o status real de solicitações que saíram da grade de Programador
acessando a tela 'Consultas -> Solicitação' a cada 2 a 3 horas.
"""

import os
import sys
import time
import argparse
from playwright.sync_api import sync_playwright

import db_manager
import extrator_demanda


def modo_debug_visual():
    return ("--debug" in sys.argv) or (os.environ.get("AUDITOR_DEBUG_UI", "").strip() == "1")


def encontrar_seletor_solicitacao(ctx):
    """
    Localiza o campo de input para 'Nº da Solicitação' na tela Pesquisar Solicitação de Manobra.
    """
    seletores = [
        "input[id*='solicitacao']",
        "input[id*='Solicitacao']",
        "input[id*='numSolicitacao']",
        "input[id*='txtSolicitacao']",
        "input[name*='solicitacao']",
        "input[name*='Solicitacao']",
    ]
    for sel in seletores:
        try:
            loc = ctx.locator(sel)
            if loc.count() > 0:
                return sel
        except Exception:
            continue
            
    # Fallback via Javascript seletor baseado em label ou posição
    try:
        seletor_js = ctx.evaluate("""() => {
            const inputs = Array.from(document.querySelectorAll("input[type='text'], input:not([type])"));
            for (const inp of inputs) {
                // Checa label próximo
                const parentText = inp.parentElement ? inp.parentElement.innerText : '';
                if (parentText.toLowerCase().includes('solicita')) {
                    return inp.id ? '#' + inp.id : null;
                }
            }
            return inputs.length > 0 && inputs[0].id ? '#' + inputs[0].id : null;
        }""")
        if seletor_js:
            return seletor_js
    except Exception:
        pass
        
    return "input[type='text']"


def encontrar_botao_pesquisar(ctx):
    """
    Localiza o botão Pesquisar no formulário de Consulta.
    """
    seletores = [
        "input[value*='Pesquisar']",
        "button:has-text('Pesquisar')",
        "input[id*='btnPesquisar']",
        "input[id*='btnSalvar']",
        "input[id*='pesquisar']"
    ]
    for sel in seletores:
        try:
            loc = ctx.locator(sel)
            if loc.count() > 0:
                return sel
        except Exception:
            continue
    return "input[value='Pesquisar']"


def navegar_para_consulta_solicitacao(page, debug_ui=False):
    """
    Navega no menu do GDIS-PM: Consultas -> Solicitação.
    """
    deadline = time.time() + 20
    while time.time() < deadline:
        for fr in page.frames:
            try:
                # 1. Localiza o menu 'Consultas'
                consultas_menu = fr.locator("text=Consultas").first
                if consultas_menu.count() == 0:
                    continue
                    
                try:
                    consultas_menu.hover(timeout=1500)
                except Exception:
                    pass
                try:
                    consultas_menu.click(timeout=1500, force=True)
                except Exception:
                    pass
                    
                time.sleep(0.3)
                
                # 2. Localiza o submenu 'Solicitação'
                sol_submenu = fr.locator("text=Solicitação").first
                try:
                    sol_submenu.wait_for(timeout=2000)
                except Exception:
                    pass
                    
                if sol_submenu.count() == 0:
                    continue
                    
                sol_submenu.click(timeout=4000, force=True)
                time.sleep(1.0)
                
                # Aguarda carregamento da tela de pesquisa
                for _ in range(15):
                    ctx_busca, _ = extrator_demanda.encontrar_contexto_tabela(page)
                    tem_pesq = ctx_busca.locator("text=Pesquisar").count() > 0
                    if tem_pesq:
                        if debug_ui:
                            print("[AUDITOR DEBUG] Tela 'Pesquisar Solicitação de Manobra' carregada com sucesso.")
                        return True, ctx_busca
                    time.sleep(0.5)
                    
            except Exception:
                continue
        time.sleep(0.5)
        
    return False, page


def extrair_resultado_consulta(ctx_tabela):
    """
    Raspa a primeira linha do resultado da pesquisa por solicitação.
    Retorna dicionário {'situacao': ..., 'manobra': ..., 'usu_elaboracao': ...} ou None.
    """
    try:
        resultado = ctx_tabela.evaluate("""() => {
            const tabelas = Array.from(document.querySelectorAll('table'));
            let melhorTabela = null;
            for (const tab of tabelas) {
                if (tab.offsetParent !== null && (tab.classList.contains('rich-table') || tab.querySelector('tbody[id$=":tb"]'))) {
                    melhorTabela = tab;
                    break;
                }
            }
            if (!melhorTabela) {
                for (const tab of tabelas) {
                    if (tab.offsetParent !== null && tab.querySelectorAll('tr').length > 1) {
                        melhorTabela = tab;
                        break;
                    }
                }
            }
            if (!melhorTabela) return null;

            // Identifica cabeçalhos
            let headers = [];
            const headerRow = melhorTabela.querySelector('thead tr') || melhorTabela.querySelector('tr');
            if (headerRow) {
                headers = Array.from(headerRow.querySelectorAll('th, td')).map(c => c.innerText.trim().toLowerCase());
            }

            // Pega primeira linha de dados
            const tbody = melhorTabela.querySelector('tbody');
            const dataRows = tbody ? Array.from(tbody.querySelectorAll('tr')) : Array.from(melhorTabela.querySelectorAll('tr')).slice(1);
            if (dataRows.length === 0) return null;

            const firstRow = dataRows[0];
            const cols = Array.from(firstRow.querySelectorAll('td')).map(c => c.innerText.trim());
            if (cols.length === 0) return null;

            let situacao = '';
            let manobra = '';
            let usu_elab = '';

            for (let i = 0; i < headers.length; i++) {
                const h = headers[i];
                const val = cols[i] || '';
                if (h.includes('situa')) situacao = val;
                else if (h.includes('manobra') && !h.includes('condis')) manobra = val;
                else if (h.includes('usu') && h.includes('elab')) usu_elab = val;
            }

            // Fallback posicional se cabeçalho não bater exatamente
            if (!situacao) {
                for (const val of cols) {
                    const vUpper = val.toUpperCase();
                    if (vUpper.includes('ELABORADA') || vUpper.includes('APROVADA') || vUpper.includes('CONDIS') || vUpper.includes('REPROVADA') || vUpper.includes('CANCELADA')) {
                        situacao = val;
                        break;
                    }
                }
            }

            return {
                situacao: situacao,
                manobra: manobra,
                usu_elaboracao: usu_elab
            };
        }""")
        return resultado
    except Exception as e:
        print(f"[AUDITOR] Erro ao raspar tabela de resultado: {e}")
        return None


def executar_auditoria(limite=50):
    """
    Executa a conciliação das solicitações pendentes no GDIS-PM.
    """
    debug_ui = modo_debug_visual()
    pendentes = db_manager.get_solicitacoes_pendentes_conciliacao(limite=limite)
    if not pendentes:
        print("[AUDITOR] Nenhuma solicitação pendente de conciliação. Finalizando.")
        return 0

    print(f"[AUDITOR] Iniciando auditoria para {len(pendentes)} solicitações pendentes de status...")

    usuario, senha = extrator_demanda.carregar_credenciais()
    if not usuario or not senha:
        print("[AUDITOR ERRO] Credenciais do GDIS-PM não configuradas.")
        return 0

    # Busca executável do navegador
    caminhos_navegador = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    ]
    navegador_executavel = next((c for c in caminhos_navegador if os.path.exists(c)), None)

    apuradas_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=navegador_executavel,
            headless=not debug_ui,
            args=["--start-maximized"] if debug_ui else []
        )
        context = browser.new_context(no_viewport=True if debug_ui else False)
        page = context.new_page()

        try:
            print("[AUDITOR] Conectando ao GDIS-PM...")
            page.goto(extrator_demanda.URL_SISTEMA, timeout=40000)

            # Login
            fr_login = extrator_demanda.find_frame_with_selector(page, extrator_demanda.SELETOR_USUARIO)
            fr_login.fill(extrator_demanda.SELETOR_USUARIO, usuario)
            fr_login.fill(extrator_demanda.SELETOR_SENHA, senha)
            fr_login.click(extrator_demanda.SELETOR_BTN_LOGIN)
            time.sleep(2.0)

            # Navega para Consultas -> Solicitação
            print("[AUDITOR] Navegando para Consultas -> Solicitação...")
            sucesso_nav, ctx_busca = navegar_para_consulta_solicitacao(page, debug_ui=debug_ui)
            if not sucesso_nav:
                print("[AUDITOR ERRO] Falha ao abrir a tela de Consulta de Solicitações.")
                return 0

            seletor_input_sol = encontrar_seletor_solicitacao(ctx_busca)
            seletor_btn_pesq = encontrar_botao_pesquisar(ctx_busca)

            for idx, item in enumerate(pendentes, 1):
                sol_id = str(item['solicitacao']).strip().lstrip('0')
                print(f"  [{idx}/{len(pendentes)}] Auditando Solicitação {sol_id}...")

                try:
                    # Limpa e preenche o número da solicitação
                    ctx_busca.fill(seletor_input_sol, sol_id)
                    time.sleep(0.3)

                    # Clica em Pesquisar
                    ctx_busca.click(seletor_btn_pesq, no_wait_after=True)
                    time.sleep(1.5)

                    ctx_tabela, _ = extrator_demanda.encontrar_contexto_tabela(page)
                    res = extrair_resultado_consulta(ctx_tabela)

                    if res and res.get('situacao'):
                        sit_real = res['situacao'].strip().upper()
                        manobra = res.get('manobra') or None
                        usu_elab = res.get('usu_elaboracao') or None

                        db_manager.atualizar_status_conciliado(
                            solicitacao=sol_id,
                            status_apurado=sit_real,
                            manobra=manobra,
                            usu_elaboracao=usu_elab
                        )
                        print(f"    -> Status Apurado: {sit_real} | Manobra: {manobra or '-'} | Técnico: {usu_elab or '-'}")
                        apuradas_count += 1
                    else:
                        print(f"    -> Solicitação {sol_id} sem retorno de dados na tabela de consulta.")

                except Exception as e_item:
                    print(f"    [AVISO] Falha ao consultar {sol_id}: {e_item}")
                    continue

        except Exception as e_global:
            print(f"[AUDITOR ERRO] Exceção durante ciclo de auditoria: {e_global}")
            extrator_demanda.salvar_debug(page, "auditor_erro_geral")
        finally:
            extrator_demanda.fechar_browser(browser)

    print(f"[AUDITOR] Ciclo concluído: {apuradas_count}/{len(pendentes)} solicitações conciliadas com sucesso.")
    return apuradas_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auditor Desacoplado de Status de Solicitações (GDIS-PM)")
    parser.add_argument("--limite", type=int, default=50, help="Quantidade máxima de solicitações a auditar por ciclo")
    parser.add_argument("--debug", action="store_true", help="Executa o navegador com interface gráfica visível")
    args = parser.parse_args()

    executar_auditoria(limite=args.limite)
