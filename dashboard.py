import streamlit as st
import pandas as pd
import sys
import altair as alt
import glob
import os
import numpy as np
from datetime import datetime, date, timedelta
from streamlit_autorefresh import st_autorefresh
import db_manager
import importlib
importlib.reload(db_manager)
import extra_streamlit_components as stx

# --- IMPORTAÇÃO DOS MÓDULOS CCP (Centro de Controle da Programação) ---
from ccp_ui import (
    DESIGN_SYSTEM, 
    inject_ui_assets, 
    inject_ui_css,
    login_screen,
    change_password_screen,
    ICONS
)
from components.vanguard_cards import (
    premium_metric_card, 
    circular_progress_ring
)
from components.vanguard_charts import (
    render_volume_by_responsible,
    render_delays_by_responsible,
    render_volume_by_mesh,
    render_delays_by_mesh,
    render_qty_x_weight_chart
)
from views.tab_detalhes import render_tab_detalhes
from views.tab_config import render_tab_config

# Inicializa banco de dados de sessões no startup

# Configuração da página (Deve ser a primeira linha de comando Streamlit)
st.set_page_config(
    page_title="Centro de Controle da Programação",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

# --- CONFIGURAÇÃO DA PÁGINA ---

# 0. Instancia o Gerenciador de Cookies Nativos
cookie_manager = stx.CookieManager()

# --- SISTEMA DE AUTENTICAÇÃO E PERSISTÊNCIA CCP ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if st.session_state.get('force_logout'):
    cookie_manager.delete("control_token")
    st.session_state.pop('force_logout')

# Limpeza de URL segura após renderização do cookie
if st.session_state.get('clear_token_soon'):
    st.query_params.clear()
    st.session_state['clear_token_soon'] = False

# 1. Tenta reconectar se não estiver logado
if not st.session_state.logged_in:
    # Ordem de prioridade: Session State (Novo Login) -> Cookie Manager -> Query Param
    token_auth = st.session_state.get('login_token_ready') or cookie_manager.get("control_token") or st.query_params.get("ctoken")
    
    if token_auth:
        user_data = db_manager.validar_token_sessao(token_auth)
        if user_data:
            st.session_state.logged_in = True
            st.session_state.user_matricula = user_data[0]
            st.session_state.user_nome = user_data[1]
            st.session_state.user_nivel = user_data[2]
            st.session_state.senha_provisoria = bool(user_data[3])
            
            # Se o token for novo (veio da tela de login ou da URL), assamos ele no Cookie Manager
            if st.session_state.get('login_token_ready') or st.query_params.get("ctoken"):
                cookie_manager.set("control_token", token_auth, max_age=2592000)
                # Marcar para limpar a URL e o state no próximo clique, garantindo que o cookie tenha tempo de renderizar
                st.session_state['clear_token_soon'] = True
                
                if 'login_token_ready' in st.session_state:
                    st.session_state.pop('login_token_ready')
        else:
            # Token inválido: limpa rastros
            cookie_manager.delete("control_token")
            if st.query_params.get("ctoken"):
                st.query_params.clear()
            if 'login_token_ready' in st.session_state:
                st.session_state.pop('login_token_ready')

# 2. Bloqueio de Acesso Global
if not st.session_state.logged_in:
    login_screen(cookie_manager)
    st.stop()

# 3. Verificação de Senha Provisória
if st.session_state.get('senha_provisoria'):
    change_password_screen()
    st.stop()



# --- CONFIGURAÇÃO DE TEMA ---
# O tema agora é gerenciado nativamente pelo menu do Streamlit (Settings > Theme)
# para garantir que as tabelas mudem de cor corretamente.

# --- INJEÇÃO DE ESTILOS E ASSETS ---
inject_ui_css()
inject_ui_assets()




# --- CONFIGURAÇÃO DE FERIADOS (Sincronizado com Calendário HTML) ---
FERIADOS_BASE = [
    # 2024
    '2024-01-01', '2024-02-12', '2024-02-13', '2024-03-29', '2024-04-21', 
    '2024-05-01', '2024-05-30', '2024-09-07', '2024-10-12', '2024-11-02', 
    '2024-11-15', '2024-11-20', '2024-12-25',
    # 2025
    '2025-01-01', '2025-03-03', '2025-03-04', '2025-03-05', '2025-04-18', 
    '2025-04-21', '2025-05-01', '2025-05-02', '2025-06-19', '2025-06-20', 
    '2025-08-15', '2025-09-07', '2025-10-12', '2025-11-02', '2025-11-15', 
    '2025-11-20', '2025-11-21', '2025-12-24', '2025-12-25', '2025-12-26', 
    '2025-12-31',
    # 2026
    '2026-01-01', '2026-01-02', '2026-02-16', '2026-02-17', '2026-02-18',
    '2026-04-03', '2026-04-20', '2026-04-21', '2026-05-01', '2026-06-04', 
    '2026-08-15', '2026-09-07', '2026-10-12', '2026-11-02', '2026-11-15',
    '2026-11-20', '2026-12-25', '2026-12-31'
]

# Função para calcular dias úteis RESTANTES (Data Inicio - Hoje)
def calcular_dias_uteis_restantes(data_inicio):
    if pd.isnull(data_inicio):
        return None
    
    # Converte para datetime se não for
    if not isinstance(data_inicio, datetime):
        try:
            # Tenta formatos comuns PT-BR
            data_inicio = pd.to_datetime(data_inicio, dayfirst=True)
        except Exception:
            return None
            
    hoje = pd.Timestamp.now().normalize() # Data de hoje sem hora
    data_inicio = pd.Timestamp(data_inicio).normalize()

    # Usa a lista global consolidada
    feriados = FERIADOS_BASE

    # ---------------------------------------------------------
    # CORREÇÃO: Força a conversão para Data nativa do Numpy. Isso 
    # evita que a função falhe ocultamente e marque tudo como "Atrasada".
    # ---------------------------------------------------------
    feriados_np = np.array(feriados, dtype='datetime64[D]')
    
    try:
        # Congelamento do "Relógio de Hoje"
        hoje_util = np.busday_offset(hoje.date(), 0, roll='backward', weekmask='1111100', holidays=feriados_np)
        
        # Congelamento da "Data de Início" da Solicitação
        data_inicio_util = np.busday_offset(data_inicio.date(), 0, roll='backward', weekmask='1111100', holidays=feriados_np)
        
        return int(np.busday_count(hoje_util, data_inicio_util, weekmask='1111100', holidays=feriados_np))
    except Exception as e:
        print(f"Erro no cálculo de dias úteis: {e}")
        return None

# Função para calcular status de atraso
def verificar_status_atraso(row):
    # Situações que indicam conclusão ou cancelamento (ignora atraso)
    # ATUALIZAÇÃO: O usuário pediu para considerar atraso APENAS se estiver "APROVADA"
    situacao = str(row.get('Situação', '')).upper()
    
    # Se NÃO contiver "APROVADA", consideramos neutro/concluído para fins de KPI de atraso
    if "APROVADA" not in situacao:
        return "Concluída/Outros"
    
    dias_restantes = row.get('Dias_Uteis_Restantes')
    
    if pd.isna(dias_restantes):
        return "Sem Data"
        
    urgencia = str(row.get('Urgência', '')).upper()
    
    # Se a data já passou (negativo), é Atrasada
    if dias_restantes < 0:
        return "Atrasada"

    # REGRA: PRAZO PADRÃO (8 DIAS ÚTEIS DE ANTECEDÊNCIA - CONFORME CALENDÁRIO "AVISOS")
    limite_prazo = 8

    # REGRA 1: URGÊNCIA (Prioridade Alta)
    # Se for Urgente e tiver menos de X dias (ou seja, recente/sem antecedência), já entra como "Urgência"
    if 'SIM' in urgencia:
         if dias_restantes < limite_prazo:
             return "Urgência"
         else:
             return "No Prazo"

    # REGRA 2: PRAZO NORMAL (X DIAS DE ANTECEDÊNCIA)
    # Se dias > limite: No Prazo (Tem antecedência suficiente)
    if dias_restantes > limite_prazo:
        return "No Prazo"
    
    # Se dias == limite: Alerta de Prazo (Limite mínimo)
    if dias_restantes == limite_prazo:
        return "Alerta de Prazo"

    # Se dias < limite: Atrasada (Não cumpriu antecedência mínima)
    return "Atrasada"


def tratar_snapshot_diario(total, atrasadas, alertas, urgencias, no_prazo):
    """Verifica se já existe snapshot hoje e salva se necessário."""
    # Se chegarmos aqui sem dados, ignora
    if total == 0:
        return
        
    df_hist = db_manager.get_historico_kpis(dias=1)
    hoje = date.today().isoformat()
    
    # Se o banco estiver vazio ou o último registro não for hoje
    needs_update = True
    if not df_hist.empty:
        if df_hist.iloc[0]['data_ref'] == hoje:
            needs_update = False
            
    if needs_update:
        kpis = {
            'total': total,
            'atrasadas': atrasadas,
            'alertas': alertas,
            'urgencias': urgencias,
            'no_prazo': no_prazo
        }
        db_manager.salvar_kpi_diario(kpis)

def render_tab_calendario():
    """Renderiza o arquivo calendario_programacao.html sincronizado com o tema do sistema."""
    try:
        with open('calendario_programacao.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Sincronização de Tema: Injeta script para forçar o modo escuro se necessário
        is_dark = True  # TODO: Detectar tema nativo do Streamlit
        theme_script = """
        <script>
            window.onload = function() {
                const isDark = %s;
                if (isDark) {
                    document.body.classList.add('dark-mode');
                    document.getElementById('themeSwitcher').textContent = '🌙';
                } else {
                    document.body.classList.remove('dark-mode');
                    document.getElementById('themeSwitcher').textContent = '☀️';
                }
            }
        </script>
        """ % ('true' if is_dark else 'false')
        
        final_html = html_content + theme_script
        
        st.components.v1.html(final_html, height=800, scrolling=True)
    except Exception as e:
        st.error(f"Erro ao carregar o calendário: {e}")

# Função para carregar o arquivo mais recente (AGORA VIA BANCO DE DADOS)
@st.cache_data(ttl=60)  # Cache de 1 minuto para não reler banco toda hora
def load_latest_data():
    # 1. Tenta carregar do Banco de Dados
    df = db_manager.carregar_dados_recentes()
    
    if df is not None and not df.empty:
        pass
    else:
        # 2. Fallback: Procura arquivos Excel se o banco estiver vazio (primeira execução)
        pasta_relatorios = "relatorios"
        if os.path.exists(pasta_relatorios):
            arquivos = glob.glob(os.path.join(pasta_relatorios, "relatorio_demanda_*.xlsx"))
        else:
            arquivos = []

        if not arquivos:
            arquivos = glob.glob("relatorio_demanda_*.xlsx")
        
        if arquivos:
            arquivo_mais_recente = max(arquivos, key=os.path.getctime)
            try:
                df = pd.read_excel(arquivo_mais_recente)
            except Exception:
                return None, None, None, None, None, None, None
        else:
            return None, None, None, None, None, None, None

    # PROCESSAMENTO DE DATAS E STATUS
    try:
        # Tenta achar coluna de Data de Início
        col_data = next((c for c in df.columns if 'início' in c.lower() or 'inicio' in c.lower()), None)
        
        if col_data:
            # Converte coluna para datetime
            df[col_data] = pd.to_datetime(df[col_data], dayfirst=True, errors='coerce')
            
            # Calcula dias úteis RESTANTES para cada linha
            df['Dias_Uteis_Restantes'] = df[col_data].apply(calcular_dias_uteis_restantes)
            
            # Identifica outras colunas
            cols = df.columns.tolist()
            col_malha = 'Ref_Malha' if 'Ref_Malha' in cols else cols[0]
            col_regiao = 'Ref_Regiao' if 'Ref_Regiao' in cols else cols[1]
            col_situacao = next((c for c in cols if 'situa' in c.lower()), None)
            col_urgencia = next((c for c in cols if 'urg' in c.lower()), None)
            col_finalidade = next((c for c in cols if 'finalidade' in c.lower()), None)
            
            # Garante que colunas essenciais existam com os nomes esperados para a função
            if col_finalidade:
                df['Finalidade'] = df[col_finalidade]
            else:
                df['Finalidade'] = ''
                
            if col_situacao:
                df['Situação'] = df[col_situacao]
            else:
                df['Situação'] = ''
                
            if col_urgencia:
                df['Urgência'] = df[col_urgencia]
            else:
                df['Urgência'] = ''

            # Aplica regra de status
            df['Status_Prazo'] = df.apply(verificar_status_atraso, axis=1)
            
            # Tenta obter a data de extração
            data_extracao = None
            if 'Data_Extracao' in df.columns:
                # Se veio do banco, pega da primeira linha (assume que todas são iguais do snapshot)
                try:
                    data_extracao = pd.to_datetime(df['Data_Extracao'].iloc[0])
                except Exception:
                    data_extracao = datetime.now()
            elif 'arquivo_mais_recente' in locals():
                # Se veio do Excel
                try:
                    timestamp = os.path.getmtime(arquivo_mais_recente)
                    data_extracao = datetime.fromtimestamp(timestamp)
                except Exception:
                    data_extracao = datetime.now()
            else:
                 # Fallback
                 data_extracao = datetime.now()

            # --- INTEGRAÇÃO MESÃO DIÁRIO ---
            try:
                try:
                    from dotenv import load_dotenv
                    load_dotenv()
                except ImportError:
                    pass
                hoje = datetime.now()
                pasta_mesao = os.environ.get("CCP_MESAO_DIARIO_PATH", r"I:\IT\ODCO\PROGRAMACAO_MT\Mesao_Diario")
                data_str_hj = hoje.strftime("%d_%m_%y")
                arquivo_mesao_hj = os.path.join(pasta_mesao, f"Mesao_{data_str_hj}.xlsx")
                
                arquivo_alvo = None
                if os.path.exists(arquivo_mesao_hj):
                    arquivo_alvo = arquivo_mesao_hj
                else:
                    arquivos_mesao = glob.glob(os.path.join(pasta_mesao, "Mesao_*.xlsx"))
                    if arquivos_mesao:
                        arquivo_alvo = max(arquivos_mesao, key=os.path.getmtime)
                
                if arquivo_alvo:
                    df_mesao = pd.read_excel(arquivo_alvo)
                    
                    if 'Solicit' in str(df_mesao.columns.tolist()): 
                        # Identifica as colunas de união dinamicamente (devido a encoding/acentos)
                        # No Mesão, evita-se pegar a coluna "Status Solicitação" para o merge
                        col_sol_db = next((c for c in df.columns if 'Solicit' in c and 'Status' not in c), df.columns[0])
                        col_sol_ms = next((c for c in df_mesao.columns if 'Solicit' in c and 'Status' not in c), df_mesao.columns[0])
                        
                        if col_sol_ms in df_mesao.columns and col_sol_db in df.columns:
                            # Limpa os dados pra evitar erros no merge
                            df['Solicitação_Merge'] = df[col_sol_db].astype(str).str.strip().str.lstrip('0')
                            df_mesao['Solicitação_Merge'] = df_mesao[col_sol_ms].astype(str).str.strip().str.lstrip('0')
                            
                            colunas_mesao = ['Solicitação_Merge']
                            if 'Peso' in df_mesao.columns: colunas_mesao.append('Peso')
                            if 'Clientes' in df_mesao.columns: colunas_mesao.append('Clientes')
                            elif 'Cliente' in df_mesao.columns:
                                df_mesao.rename(columns={'Cliente': 'Clientes'}, inplace=True)
                                colunas_mesao.append('Clientes')
                                
                            if 'CHI' in df_mesao.columns: colunas_mesao.append('CHI')
                            if 'PLE' in df_mesao.columns: colunas_mesao.append('PLE')
                            
                            # Padroniza variações de 'OBRA GD'
                            for var_gd in ['Obra GD', 'OBRA GD', 'OBRA_GD', 'GD']:
                                if var_gd in df_mesao.columns:
                                    df_mesao.rename(columns={var_gd: 'OBRA GD'}, inplace=True)
                                    colunas_mesao.append('OBRA GD')
                                    break
                            
                            df_mesao_sub = df_mesao[colunas_mesao].drop_duplicates(subset=['Solicitação_Merge'])
                            df = pd.merge(df, df_mesao_sub, on='Solicitação_Merge', how='left')
                            df.drop(columns=['Solicitação_Merge'], inplace=True)
                        
                        # Preenche valores Vazios com 0 nas colunas numéricas / vazio para texto
                        if 'Peso' in df.columns:
                            # Garante a formatação inicial numérica para tratamento de vazios
                            peso_num = pd.to_numeric(df['Peso'], errors='coerce').fillna(0)
                            df['Peso'] = peso_num.astype(int).astype(str)
                            
                            if 'PLE' in df.columns:
                                mask_ple_preenchido = df['PLE'].notna() & (df['PLE'].astype(str).str.strip() != '') & (df['PLE'].astype(str).str.strip().str.upper() != 'NAN')
                                mask_peso_vazio = df['Peso'] == '0'
                                df.loc[mask_peso_vazio & mask_ple_preenchido, 'Peso'] = df.loc[mask_peso_vazio & mask_ple_preenchido, 'PLE'].astype(str).str.strip()
                                df.drop(columns=['PLE'], inplace=True)
                                
                        if 'Clientes' in df.columns: df['Clientes'] = pd.to_numeric(df['Clientes'], errors='coerce').fillna(0)
                        if 'CHI' in df.columns: df['CHI'] = pd.to_numeric(df['CHI'], errors='coerce').fillna(0)
                        if 'OBRA GD' in df.columns: df['OBRA GD'] = df['OBRA GD'].fillna('')
            except Exception as e:
                import streamlit as st
                st.sidebar.warning(f"Erro ao carregar Mesão Diário: {e}")
            # --------------------------------

            return df, col_malha, col_regiao, col_situacao, col_urgencia, col_data, data_extracao
        else:
            return None, None, None, None, None, None, None
    except Exception as e:
        st.error(f"Erro ao processar dados: {e}")
        return None, None, None, None, None, None, None

# --- CARREGAMENTO DOS DADOS ---
df, col_malha, col_regiao, col_situacao, col_urgencia, col_data, data_extracao = load_latest_data()

if df is not None:
    # Prepara colunas Em Elaboração e Aprovadas para as contagens nas tabelas
    if col_situacao and col_situacao in df.columns:
        df['Is_Elaboracao'] = df[col_situacao].astype(str).str.upper().str.contains('ELABORAÇÃO|ELABORACAO')
        df['Is_Aprovada'] = df[col_situacao].astype(str).str.upper().str.contains('APROVADA|APROVADO')
    else:
        df['Is_Elaboracao'] = False
        df['Is_Aprovada'] = False

    # --- MAPEAMENTO GLOBAL DO RESPONSÁVEL (Real-time via Banco + Travas) ---
    df['temp_sigla'] = df[col_regiao].astype(str).str.strip().str[:2].str.upper()
    df_map = db_manager.get_mapeamento_regioes()
    
    # 1. Mapeamento por Região (Padrão)
    if not df_map.empty:
        df = df.merge(df_map[['sigla_regiao', 'responsavel', 'matricula']], left_on='temp_sigla', right_on='sigla_regiao', how='left')
        df['Responsavel_Regiao'] = df['responsavel'].fillna("Não Atribuído")
        df['Matricula_Regiao'] = df['matricula']
        df = df.drop(columns=['temp_sigla', 'sigla_regiao', 'responsavel', 'matricula'])
    else:
        df['Responsavel_Regiao'] = "Não Atribuído"
        df['Matricula_Regiao'] = None
        df = df.drop(columns=['temp_sigla'])

    col_sol = next((c for c in df.columns if 'Solicit' in c and 'Status' not in c), df.columns[0])

    # 2. Verifica se há travas no banco para solicitações em elaboração
    df_travadas = db_manager.get_solicitacoes_travadas()
    if not df_travadas.empty:
        df['Solicitacao_str'] = df[col_sol].astype(str).str.strip()
        df = df.merge(df_travadas, left_on='Solicitacao_str', right_on='solicitacao', how='left')
        
        # 3. Define quem é o Responsável Final (Trava prevalece sobre Regiao)
        df['Responsavel'] = df['responsavel_travado'].fillna(df['Responsavel_Regiao'])
        df['Matricula'] = df['matricula_travada'].fillna(df['Matricula_Regiao'])
        
        df = df.drop(columns=['Solicitacao_str', 'solicitacao', 'responsavel_travado', 'matricula_travada'])
    else:
        df['Responsavel'] = df['Responsavel_Regiao']
        df['Matricula'] = df['Matricula_Regiao']

    # 4. Grava novas travas no banco para solicitações "Em elaboração" que não estavam travadas
    # Se 'Is_Elaboracao' é True e ainda não estava na tabela de travas, ele salva a trava agora.
    solicitacoes_ja_travadas = df_travadas['solicitacao'].tolist() if not df_travadas.empty else []
    novas_para_travar = df[(df['Is_Elaboracao'] == True) & (df['Matricula'].notna()) & (~df[col_sol].astype(str).str.strip().isin(solicitacoes_ja_travadas))]
    
    if not novas_para_travar.empty:
        db_manager.travar_solicitacoes(novas_para_travar[[col_sol, 'Matricula']].rename(columns={col_sol: 'Solicitação'}))

    # 5. Atualiza o snapshot de pendentes do dia com os dados atuais mapeados
    db_manager.registrar_snapshot_pendentes(df)

    # --- DEFINIÇÃO DE ESCOPO DE KPIs (Regra de Acesso) ---
    if st.session_state.user_nivel == "Usuario":
        # Usuário comum vê apenas seus próprios dados no topo
        df_top = df[df['Responsavel'] == st.session_state.user_nome]
        prefix_kpi = "Minha "
    else:
        # Gerencial e ADM veem o panorama geral
        df_top = df
        prefix_kpi = "Geral: " if st.session_state.user_nivel in ["Gerencial", "ADM"] else ""

    # 1. KPIs GERAIS (Recálculo Dinâmico ocorrerá após os filtros)
    # Definimos variáveis iniciais caso o processamento falhe
    total_solicitacoes = 0
    qtd_atrasadas = 0
    qtd_urgencia = 0
    qtd_alerta = 0

    # --- 2. FILTROS (No Sidebar - Redesign UI/UX Pro Max) ---
    # Sincroniza preset de data selecionado pelos botões de atalho no sidebar
    if "date_period_preset" in st.session_state:
        st.session_state["v_filter_date"] = st.session_state.pop("date_period_preset")

    def set_date_preset(start_d, end_d):
        st.session_state["date_period_preset"] = (start_d, end_d)

    # 1. CARD DE PERFIL DO USUÁRIO NO TOPO DO SIDEBAR
    user_nome = getattr(st.session_state, "user_nome", "Usuário")
    user_nivel = getattr(st.session_state, "user_nivel", "Usuario")
    
    partes_nome = user_nome.split()
    iniciais = (partes_nome[0][0] + (partes_nome[-1][0] if len(partes_nome) > 1 else "")).upper()
    
    if user_nivel == "ADM":
        badge_style = "background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff;"
        badge_label = "👑 ADM"
    elif user_nivel == "Gerencial":
        badge_style = "background: linear-gradient(135deg, #3b82f6, #1d4ed8); color: #fff;"
        badge_label = "📊 GERENCIAL"
    else:
        badge_style = "background: linear-gradient(135deg, #10b981, #047857); color: #fff;"
        badge_label = "👤 OPERACIONAL"

    st.sidebar.markdown(f"""
        <div style="background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255,255,255,0.08); padding: 12px; border-radius: 12px; margin-bottom: 12px; display: flex; align-items: center; gap: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
            <div style="width: 40px; height: 40px; border-radius: 50%; background: linear-gradient(135deg, #06b6d4, #3b82f6); display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 0.95rem; color: #fff; box-shadow: 0 0 10px rgba(6,182,212,0.4); flex-shrink: 0;">
                {iniciais}
            </div>
            <div style="flex: 1; min-width: 0;">
                <div style="font-weight: 700; font-size: 0.85rem; color: #f8fafc; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                    {user_nome}
                </div>
                <span style="display: inline-block; margin-top: 2px; padding: 2px 8px; border-radius: 6px; font-size: 0.6rem; font-weight: 800; letter-spacing: 0.5px; {badge_style}">
                    {badge_label}
                </span>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # 2. BLOCO PERÍODO & ATALHOS
    st.sidebar.markdown("<div style='font-size:0.75rem; font-weight:800; color:#38bdf8; letter-spacing:0.5px; margin-bottom:4px;'>📅 PERÍODO DE ANÁLISE</div>", unsafe_allow_html=True)
    
    col_filtro_data = next((c for c in df.columns if 'inicio' in c.lower() or 'início' in c.lower()), col_data)
    if col_filtro_data != col_data:
         df[col_filtro_data] = pd.to_datetime(df[col_filtro_data], dayfirst=True, errors='coerce')

    min_date = df[col_filtro_data].min()
    max_date = df[col_filtro_data].max()
    min_date = min_date.date() if not pd.isna(min_date) else datetime.now().date()
    max_date = max_date.date() if not pd.isna(max_date) else datetime.now().date()
    if min_date > max_date: min_date = max_date

    # Data Padrão: Hoje até Hoje + 11 dias úteis
    hoje_date = pd.Timestamp.now().normalize().date()
    feriados_np_filtro = np.array(FERIADOS_BASE, dtype='datetime64[D]')

    def ajustar_fim_periodo(d_end):
        """Se o dia final for seguido de final de semana ou feriado, estende o período até a véspera do próximo dia útil."""
        try:
            prox_du = pd.to_datetime(
                np.busday_offset(d_end, 1, roll='forward', weekmask='1111100', holidays=feriados_np_filtro)
            ).date()
            return prox_du - timedelta(days=1)
        except Exception:
            return d_end

    try:
        decimo_primeiro_dia_util = np.busday_offset(hoje_date, 11, roll='forward', weekmask='1111100', holidays=feriados_np_filtro)
        default_max = ajustar_fim_periodo(pd.to_datetime(decimo_primeiro_dia_util).date())
    except Exception: 
        default_max = hoje_date + pd.Timedelta(days=15)
        
    min_value_picker = min(min_date, hoje_date)
    max_value_picker = max(max_date, default_max)
    
    # Se o sinal de Reset Global foi acionado
    if "reset_all_signal" in st.session_state:
        st.session_state.pop("reset_all_signal")
        st.session_state["v_filter_date"] = (hoje_date, default_max)
        if "v_filter_resp" in st.session_state: st.session_state.pop("v_filter_resp")
        if "v_filter_malha" in st.session_state: st.session_state.pop("v_filter_malha")
        if "v_filter_regiao" in st.session_state: st.session_state.pop("v_filter_regiao")

    filtro_data = st.sidebar.date_input(
        "Filtrar por Período", 
        value=(hoje_date, default_max), 
        min_value=min_value_picker, 
        max_value=max_value_picker, 
        format="DD/MM/YYYY",
        label_visibility="collapsed",
        key="v_filter_date"
    )

    try:
        get_du_date = lambda offset: ajustar_fim_periodo(
            pd.to_datetime(
                np.busday_offset(hoje_date, offset, roll='forward', weekmask='1111100', holidays=feriados_np_filtro)
            ).date()
        )
        date_du8 = get_du_date(8)
        date_du9 = get_du_date(9)
        date_du10 = get_du_date(10)
        date_du11 = get_du_date(11)
    except Exception:
        date_du8 = ajustar_fim_periodo(hoje_date + timedelta(days=10))
        date_du9 = ajustar_fim_periodo(hoje_date + timedelta(days=11))
        date_du10 = ajustar_fim_periodo(hoje_date + timedelta(days=12))
        date_du11 = ajustar_fim_periodo(hoje_date + timedelta(days=13))

    # Botões de atalho rápido de período (Grade 2 Colunas)
    st.sidebar.markdown("""
        <style>
        div[data-testid="stSidebar"] div[data-testid="stButton"] button {
            padding: 4px 6px !important;
            font-size: 0.78rem !important;
            font-weight: 700 !important;
            min-height: 32px !important;
            height: 32px !important;
            border-radius: 6px !important;
            white-space: nowrap !important;
        }
        </style>
        <div style='margin-top: 4px; margin-bottom: 6px;'>
            <strong style='font-size: 0.72rem; color: var(--text-secondary);'>⚡ Atalhos de Período:</strong>
        </div>
    """, unsafe_allow_html=True)
    
    r1_c1, r1_c2 = st.sidebar.columns(2)
    r1_c1.button("8-11D", key="btn_sb_8_11", use_container_width=True, on_click=set_date_preset, args=(date_du8, date_du11), help="Do 8º ao 11º Dia Útil")
    r1_c2.button("Reset", key="btn_sb_reset", use_container_width=True, on_click=set_date_preset, args=(hoje_date, default_max), help="Resetar Período Padrão")

    r2_c1, r2_c2 = st.sidebar.columns(2)
    r2_c1.button("H➔8D", key="btn_sb_h8", use_container_width=True, on_click=set_date_preset, args=(hoje_date, date_du8), help="Hoje até o 8º Dia Útil")
    r2_c2.button("H➔9D", key="btn_sb_h9", use_container_width=True, on_click=set_date_preset, args=(hoje_date, date_du9), help="Hoje até o 9º Dia Útil")

    r3_c1, r3_c2 = st.sidebar.columns(2)
    r3_c1.button("H➔10D", key="btn_sb_h10", use_container_width=True, on_click=set_date_preset, args=(hoje_date, date_du10), help="Hoje até o 10º Dia Útil")
    r3_c2.button("H➔11D", key="btn_sb_h11", use_container_width=True, on_click=set_date_preset, args=(hoje_date, date_du11), help="Hoje até o 11º Dia Útil")

    st.sidebar.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 12px 0;' />", unsafe_allow_html=True)
    
    # 3. BLOCO FOCO OPERACIONAL
    st.sidebar.markdown("<div style='font-size:0.75rem; font-weight:800; color:#38bdf8; letter-spacing:0.5px; margin-bottom:6px;'>🎯 FOCO OPERACIONAL</div>", unsafe_allow_html=True)
    
    lista_responsaveis = sorted(df_top['Responsavel'].unique())
    if st.session_state.user_nivel == "Usuario":
        if st.session_state.user_nome in lista_responsaveis:
            filtro_responsavel = st.sidebar.multiselect("👩‍💻 Responsável (Travado)", options=lista_responsaveis, default=[st.session_state.user_nome], key="v_filter_resp", disabled=True)
        else:
            st.sidebar.error(f"Seu nome ({st.session_state.user_nome}) não foi encontrado como responsável.")
            filtro_responsavel = st.sidebar.multiselect("👩‍💻 Responsável", options=lista_responsaveis, default=lista_responsaveis, key="v_filter_resp")
    else:
        filtro_responsaveis_all = sorted(df['Responsavel'].unique())
        filtro_responsavel = st.sidebar.multiselect("👩‍💻 Responsável", options=filtro_responsaveis_all, default=filtro_responsaveis_all, key="v_filter_resp")
        
    df_filtered_resp = df[df['Responsavel'].isin(filtro_responsavel)]

    lista_regioes_total = sorted(df_top[col_regiao].unique())
    default_regioes = sorted(df_filtered_resp[col_regiao].unique()) if not df_filtered_resp.empty else []
    filtro_regiao = st.sidebar.multiselect("🗺️ Região", options=lista_regioes_total, default=default_regioes, key="v_filter_regiao")

    # Malha padrão (sem filtro no sidebar)
    filtro_malha = sorted(df_top[col_malha].unique())

    # 4. BOTÃO DE RESET GLOBAL E SAIR
    def trigger_reset_all():
        st.session_state["reset_all_signal"] = True

    st.sidebar.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
    st.sidebar.button("🔄 Resetar Todos os Filtros", key="btn_global_reset", use_container_width=True, on_click=trigger_reset_all, help="Restaura datas, responsáveis e regiões ao estado padrão")

    if st.sidebar.button("🚪 Sair do Sistema", key="btn_logout_sidebar", use_container_width=True, help="Encerrar sessão de usuário"):
        st.session_state.authenticated = False
        st.session_state.user_nome = ""
        st.session_state.user_nivel = ""
        st.rerun()

    # Aplica filtros finais para gerar o df_filtered
    df_filtered = df[df['Responsavel'].isin(filtro_responsavel)]
    df_filtered = df_filtered[df_filtered[col_malha].isin(filtro_malha)]
    df_filtered = df_filtered[df_filtered[col_regiao].isin(filtro_regiao)]
    
    if isinstance(filtro_data, tuple) and len(filtro_data) >= 1:
        start_date = filtro_data[0]
        end_date = filtro_data[1] if len(filtro_data) == 2 else filtro_data[0]
        mask_date = (df_filtered[col_filtro_data].dt.date >= start_date) & (df_filtered[col_filtro_data].dt.date <= end_date)
        df_filtered = df_filtered.loc[mask_date]

    # RECALCULA VARIÁVEIS DE KPI BASEADAS NO FILTRO ATUAL
    total_solicitacoes = len(df_filtered)
    qtd_atrasadas = len(df_filtered[df_filtered['Status_Prazo'] == 'Atrasada'])
    qtd_urgencia = len(df_filtered[df_filtered['Status_Prazo'] == 'Urgência'])
    qtd_alerta = len(df_filtered[df_filtered['Status_Prazo'] == 'Alerta de Prazo'])
    qtd_aprovadas = len(df_filtered[df_filtered['Is_Aprovada'] == True]) if 'Is_Aprovada' in df_filtered.columns else 0
    qtd_elaboracao = len(df_filtered[df_filtered['Is_Elaboracao'] == True]) if 'Is_Elaboracao' in df_filtered.columns else 0
    
    # --- CABEÇALHO DE CONTROLE ---
    st.markdown(f"""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-xs);" class="animate-target">
        <div>
            <h1 style="margin: 0; font-size: 2.2rem; color: var(--accent-color); line-height: 1.1;">CENTRO DE CONTROLE DA PROGRAMAÇÃO</h1>            
        </div>
        <div style="display: flex; align-items: center; gap: var(--space-md);">
            <div style="text-align: right; border-right: 1px solid var(--border-color); padding-right: var(--space-md);">
                <div style="color: var(--text-secondary); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 1px;">Última Atualização</div>
                <div style="display: flex; align-items: center; gap: 6px; color: #34d399; font-weight: 700; font-size: 0.85rem;">
                    <div style="width: 6px; height: 6px; background: #34d399; border-radius: 50%; box-shadow: 0 0 8px #34d399; animation: pulse 2s infinite;"></div>
                    {data_extracao.strftime('%d/%m/%Y %H:%M') if data_extracao else 'N/A'}
                </div>
            </div>
            <div style="background: var(--surface-color); padding: 8px 16px; border-radius: 8px; border: 1px solid var(--border-color); box-shadow: inset 0 0 10px rgba(0,0,0,0.2);">
                <span id="digital-clock" style="font-family: 'Space Grotesk', sans-serif; font-size: 1.1rem; font-weight: 700; color: var(--primary-color); letter-spacing: 1px;">{datetime.now().strftime('%H:%M:%S')}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <style>
        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(52, 211, 153, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(52, 211, 153, 0); }
        }
        /* pulse-red definido em ccp_ui.py */
        @keyframes glow-green {
            0% { box-shadow: 0 0 5px rgba(16, 185, 129, 0.1); }
            50% { box-shadow: 0 0 15px rgba(16, 185, 129, 0.3); }
            100% { box-shadow: 0 0 5px rgba(16, 185, 129, 0.1); }
        }
        .vanguard-alert-card {
            background: var(--card-bg);
            padding: 0;
            border-radius: 12px;
            margin-bottom: var(--space-xs);
            border: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            height: 100%;
            overflow: hidden;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: var(--card-shadow);
        }
        .vanguard-alert-card:hover {
            transform: translateY(-2px);
            border-color: var(--accent-color);
        }
        .vanguard-card-pending {
            border: 2px solid #ef4444;
            animation: pulse-red 2s infinite;
        }
        .vanguard-card-confirmed {
            border: 2px solid #10b981;
            animation: glow-green 3s infinite;
        }
        .card-header-pending {
            background: #ef4444;
            color: white;
            padding: 6px 10px;
            font-size: 0.65rem;
            font-weight: 800;
            text-transform: uppercase;
            text-align: center;
            letter-spacing: 0.5px;
        }
        .card-header-confirmed {
            background: #10b981;
            color: white;
            padding: 6px 10px;
            font-size: 0.65rem;
            font-weight: 800;
            text-transform: uppercase;
            text-align: center;
            letter-spacing: 0.5px;
        }
        .card-body {
            padding: 14px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
    </style>
    """, unsafe_allow_html=True)



    # --- MOTOR DE ATIVAÇÃO ---

    # --- SISTEMA DE ALERTAS (Notificações Persistentes) ---
    if 'control_dismissed' not in st.session_state:
        st.session_state.control_dismissed = set()

    # Detecta urgências ativas no escopo df_filtered que ainda não foram descartadas
    # Regra: Só emitir alerta se a urgência for SIM e a Situação contiver "APROVADA"
    urgencias_ativas = df_filtered[
        df_filtered[col_urgencia].astype(str).str.upper().str.contains('SIM|S') &
        df_filtered[col_situacao].astype(str).str.upper().str.contains('APROVADA')
    ].copy()
    
    # Filtra as que o usuário ainda não confirmou leitura e remove duplicações para evitar erro de chaves iguais
    alertas_pendentes = urgencias_ativas[~urgencias_ativas[col_sol].astype(str).isin(st.session_state.control_dismissed)]
    alertas_pendentes = alertas_pendentes.drop_duplicates(subset=[col_sol])

    if not alertas_pendentes.empty:
        st.markdown(f'<h3 style="color: #ef4444; font-size: 0.8rem; margin-bottom: var(--space-sm); font-weight: 700; display: flex; align-items: center; gap: 8px;"><span style="background: #ef4444; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.6rem;">!</span> Solicitações Fora do Prazo ({len(alertas_pendentes)})</h3>', unsafe_allow_html=True)
        
        # Guarda contra ausência da coluna Tem_Email (só existe se o extrator rodou com Outlook)
        if 'Tem_Email' not in alertas_pendentes.columns:
            alertas_pendentes['Tem_Email'] = False
        
        # 4. Separar com email vs sem email (comparação explícita para evitar KeyError)
        alertas_com_email = alertas_pendentes[alertas_pendentes['Tem_Email'] == True].copy()
        alertas_sem_email = alertas_pendentes[alertas_pendentes['Tem_Email'] != True].copy()
        
        # 3. Ordenar de forma crescente considerando a data
        # Tenta usar a coluna de data (col_data) se existir, senão usa os Dias Úteis (mais atrasados primeiro)
        if col_data in alertas_pendentes.columns:
            alertas_com_email.sort_values(col_data, ascending=True, inplace=True)
            alertas_sem_email.sort_values(col_data, ascending=True, inplace=True)
        else:
            alertas_com_email.sort_values('Dias_Uteis_Restantes', ascending=True, inplace=True)
            alertas_sem_email.sort_values('Dias_Uteis_Restantes', ascending=True, inplace=True)

        def renderizar_grid_alertas(df_alertas, header_label, header_class, card_class, n_cols=2):
            num_alertas = len(df_alertas)
            for i in range(0, num_alertas, n_cols):
                cols = st.columns(n_cols)
                batch = df_alertas.iloc[i : i + n_cols]
                
                for j, (idx, row) in enumerate(batch.iterrows()):
                    solicit_id = str(row[col_sol])
                    # Tenta capturar o nome do responsável caso o nome da coluna varie
                    responsavel = str(row.get('Responsável', row.get('Técnico Responsável', row.get('Responsavel', 'Não Atribuído'))))
                    
                    with cols[j]:
                        # Estilos inline para compactar ainda mais e adicionar o responsável
                        st.markdown(f"""
                        <div class="vanguard-alert-card {card_class}">
                            <div class="{header_class}">{header_label}</div>
                            <div class="card-body" style="padding: 6px; gap: 2px;">
                                <div style="color: var(--text-primary); font-size: 0.9rem; font-weight: 700; line-height: 1.1;">Sol. {solicit_id}</div>
                                <div style="color: var(--text-secondary); font-size: 0.7rem; font-weight: 500;">📍 {row[col_regiao]}</div>
                                <div style="color: var(--text-secondary); font-size: 0.7rem; font-weight: 500;">🎯 {str(row.get('Finalidade', 'N/A'))}</div>
                                <div style="color: var(--text-secondary); font-size: 0.7rem; font-weight: 500;">👤 {responsavel}</div>
                                <div style="color: var(--text-secondary); font-size: 0.7rem; font-weight: 500;">⏳ {row.get('Dias_Uteis_Restantes')} dias úteis</div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
        # 1. Área dividida ao meio, usando sistema de paginação em vez de scroll
        col_esq, col_dir = st.columns(2)
        
        ITEMS_PER_PAGE = 4
        
        # Paginação Esquerda (Sem E-mail)
        if 'page_sem_email' not in st.session_state:
            st.session_state.page_sem_email = 0
            
        total_pages_sem = max(1, int(np.ceil(len(alertas_sem_email) / ITEMS_PER_PAGE)))
        if st.session_state.page_sem_email >= total_pages_sem:
            st.session_state.page_sem_email = max(0, total_pages_sem - 1)
            
        start_idx_sem = st.session_state.page_sem_email * ITEMS_PER_PAGE
        batch_sem = alertas_sem_email.iloc[start_idx_sem : start_idx_sem + ITEMS_PER_PAGE]
        
        with col_esq:
            # Cabeçalho com paginação embutida e botões menores
            hc1, hc2, hc3, hc4, hc5, hc6 = st.columns([3.5, 0.6, 0.6, 1.2, 0.6, 0.6])
            with hc1:
                st.markdown("<div style='margin-top: 8px;'><strong style='color: #ef4444; font-size: 0.85rem;'>⚠️ AGUARDANDO E-MAIL</strong></div>", unsafe_allow_html=True)
            if total_pages_sem > 1:
                with hc2:
                    if st.button("⏮", key="first_sem", disabled=(st.session_state.page_sem_email == 0), use_container_width=True):
                        st.session_state.page_sem_email = 0
                        st.rerun()
                with hc3:
                    if st.button("◄", key="prev_sem", disabled=(st.session_state.page_sem_email == 0), use_container_width=True):
                        st.session_state.page_sem_email -= 1
                        st.rerun()
                with hc4:
                    st.markdown(f"<div style='text-align: center; font-size: 0.70rem; color: var(--text-secondary); margin-top: 12px; font-weight: bold;'>{st.session_state.page_sem_email + 1} / {total_pages_sem}</div>", unsafe_allow_html=True)
                with hc5:
                    if st.button("►", key="next_sem", disabled=(st.session_state.page_sem_email == total_pages_sem - 1), use_container_width=True):
                        st.session_state.page_sem_email += 1
                        st.rerun()
                with hc6:
                    if st.button("⏭", key="last_sem", disabled=(st.session_state.page_sem_email == total_pages_sem - 1), use_container_width=True):
                        st.session_state.page_sem_email = total_pages_sem - 1
                        st.rerun()

            with st.container(border=True):
                if not alertas_sem_email.empty:
                    renderizar_grid_alertas(batch_sem, "⚠️ SEM E-MAIL", "card-header-pending", "vanguard-card-pending", n_cols=2)
                else:
                    st.info("Nenhuma solicitação sem e-mail.")

        # Paginação Direita (Com E-mail)
        if 'page_com_email' not in st.session_state:
            st.session_state.page_com_email = 0
            
        total_pages_com = max(1, int(np.ceil(len(alertas_com_email) / ITEMS_PER_PAGE)))
        if st.session_state.page_com_email >= total_pages_com:
            st.session_state.page_com_email = max(0, total_pages_com - 1)
            
        start_idx_com = st.session_state.page_com_email * ITEMS_PER_PAGE
        batch_com = alertas_com_email.iloc[start_idx_com : start_idx_com + ITEMS_PER_PAGE]

        with col_dir:
            # Cabeçalho com paginação embutida e botões menores
            hc1, hc2, hc3, hc4, hc5, hc6 = st.columns([3.5, 0.6, 0.6, 1.2, 0.6, 0.6])
            with hc1:
                st.markdown("<div style='margin-top: 8px;'><strong style='color: #10b981; font-size: 0.85rem;'>📧 E-MAIL RECEBIDO</strong></div>", unsafe_allow_html=True)
            if total_pages_com > 1:
                with hc2:
                    if st.button("⏮", key="first_com", disabled=(st.session_state.page_com_email == 0), use_container_width=True):
                        st.session_state.page_com_email = 0
                        st.rerun()
                with hc3:
                    if st.button("◄", key="prev_com", disabled=(st.session_state.page_com_email == 0), use_container_width=True):
                        st.session_state.page_com_email -= 1
                        st.rerun()
                with hc4:
                    st.markdown(f"<div style='text-align: center; font-size: 0.70rem; color: var(--text-secondary); margin-top: 12px; font-weight: bold;'>{st.session_state.page_com_email + 1} / {total_pages_com}</div>", unsafe_allow_html=True)
                with hc5:
                    if st.button("►", key="next_com", disabled=(st.session_state.page_com_email == total_pages_com - 1), use_container_width=True):
                        st.session_state.page_com_email += 1
                        st.rerun()
                with hc6:
                    if st.button("⏭", key="last_com", disabled=(st.session_state.page_com_email == total_pages_com - 1), use_container_width=True):
                        st.session_state.page_com_email = total_pages_com - 1
                        st.rerun()

            with st.container(border=True):
                if not alertas_com_email.empty:
                    renderizar_grid_alertas(batch_com, "📧 COM E-MAIL", "card-header-confirmed", "vanguard-card-confirmed", n_cols=2)
                else:
                    st.info("Nenhuma solicitação com e-mail.")




    # --- LAYOUT SIMÉTRICO VANGUARD (KPIs GERAIS) ---
    @st.dialog("📋 Detalhamento de Solicitações", width="large")
    def show_kpi_dialog(kpi_name, df_kpi):
        st.markdown(f"#### Mostrando: **{kpi_name}** ({len(df_kpi)} itens)")
        if df_kpi.empty:
            st.info("Nenhuma solicitação encontrada para este filtro.")
        else:
            # Exibir colunas mais relevantes primeiro
            cols_prioridade = [col_sol, 'Responsavel', col_regiao, col_malha, 'Status_Prazo', 'Dias_Uteis_Restantes']
            cols_exibicao = [c for c in cols_prioridade if c in df_kpi.columns]
            cols_restantes = [c for c in df_kpi.columns if c not in cols_exibicao]
            st.dataframe(df_kpi[cols_exibicao + cols_restantes], use_container_width=True, hide_index=True)

    # Âncora única para o CSS targeting
    st.markdown('<div id="kpi-columns-anchor"></div>', unsafe_allow_html=True)
    st.markdown("""
    <style>
    /* Transforma a coluna que vem logo após a âncora no referencial relativo */
    div[data-testid="element-container"]:has(#kpi-columns-anchor) + div[data-testid="element-container"] div[data-testid="column"] {
        position: relative !important;
    }
    /* Estica os botões contidos nas colunas para o tamanho da coluna toda e zera opacidade */
    div[data-testid="element-container"]:has(#kpi-columns-anchor) + div[data-testid="element-container"] div[data-testid="column"] div[data-testid="stButton"] {
        position: absolute !important;
        top: 0 !important; left: 0 !important; width: 100% !important; height: 100% !important;
        opacity: 0 !important; z-index: 999 !important;
    }
    div[data-testid="element-container"]:has(#kpi-columns-anchor) + div[data-testid="element-container"] div[data-testid="column"] div[data-testid="stButton"] button {
        width: 100% !important; height: 100% !important; cursor: pointer !important;
    }
    </style>
    """, unsafe_allow_html=True)

    kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5, kpi_col6 = st.columns(6)
    
    with kpi_col1:
        premium_metric_card("Total Geral", total_solicitacoes, icon_name="people", color="#3b82f6", is_vanguard=True)
        if st.button("Total Geral", key="kpi_btn_fila", use_container_width=True):
            show_kpi_dialog("Total Geral", df_filtered)
    
    with kpi_col2:
        premium_metric_card("Solicitações Atrasadas", qtd_atrasadas, icon_name="timer", color="#f87171")
        if st.button("Atrasadas", key="kpi_btn_atrasados", use_container_width=True):
            show_kpi_dialog("Solicitações Atrasadas", df_filtered[df_filtered['Status_Prazo'] == 'Atrasada'])

    with kpi_col3:
        premium_metric_card("Foras do Prazo (Caixa)", qtd_urgencia, icon_name="flash", color="#fbbf24")
        if st.button("Fora do Prazo", key="kpi_btn_urgentes", use_container_width=True):
            show_kpi_dialog("Foras do Prazo (Caixa)", df_filtered[df_filtered['Status_Prazo'] == 'Urgência'])
        
    with kpi_col4:
        premium_metric_card("8 dias - Prazo p/ Enviar Aviso", qtd_alerta, icon_name="info", color="#818cf8")
        if st.button("Aviso (8 dias)", key="kpi_btn_alertas", use_container_width=True):
            show_kpi_dialog("8 dias - Prazo p/ Enviar Aviso", df_filtered[df_filtered['Status_Prazo'] == 'Alerta de Prazo'])
        
    with kpi_col5:
        premium_metric_card("Total Em elaboração", qtd_elaboracao, icon_name="edit", color="#38bdf8")
        if st.button("Em elaboração", key="kpi_btn_elaboracao", use_container_width=True):
            show_kpi_dialog("Total Em elaboração", df_filtered[df_filtered['Is_Elaboracao'] == True])
        
    with kpi_col6:
        premium_metric_card("Total de Aprovadas", qtd_aprovadas, icon_name="tick", color="#34d399")
        if st.button("Aprovadas", key="kpi_btn_aprovadas", use_container_width=True):
            show_kpi_dialog("Total de Aprovadas", df_filtered[df_filtered['Is_Aprovada'] == True])

    # Automação de Snapshot Diário (Pós-processamento dos KPIs)
    tratar_snapshot_diario(total_solicitacoes, qtd_atrasadas, qtd_alerta, qtd_urgencia, (total_solicitacoes - qtd_atrasadas))

    # 3. ABAS DE VISUALIZAÇÃO (Symmetry Mode - Responsivo)
    if st.session_state.user_nivel in ["Gerencial", "ADM"]:
        abas = ["📅 Calendário", "👥 Responsáveis", "🏙️ Visão por Malha", "🗺️ Visão por Região", "📋 Dados Detalhados", "📊 Relatórios"]
    else:
        abas = ["📅 Calendário", "🗺️ Visão por Região", "📋 Dados Detalhados"]
    
    # Nível ADM vê Configurações
    if st.session_state.user_nivel == "ADM":
        abas.append("⚙️ Configurações")
        
    # Recupera a aba ativa ou usa a primeira
    default_tab = st.session_state.get("active_tab_nav", abas[0])
    if default_tab not in abas:
        default_tab = abas[0]
        
    # CSS para transformar o st.segmented_control num clone visual do st.tabs escuro com cyan
    st.markdown("""
    <style>
    /* Remove o fundo cinza contínuo do segmented control e cria o espaçamento entre as abas */
    div[data-testid="stSegmentedControl"] {
        background-color: transparent !important;
        padding: 0 !important;
        gap: 8px !important;
        margin-bottom: 25px !important;
    }
    
    /* Remove a pílula de animação padrão do BaseWeb que desliza atrás dos botões */
    div[data-testid="stSegmentedControl"] > div > div:first-child {
        display: none !important;
    }
    
    /* Estilo de cada "Aba" INATIVA (separadas umas das outras) */
    div[data-testid="stSegmentedControl"] label {
        background-color: var(--secondary-background-color) !important;
        border: 1px solid rgba(128, 128, 128, 0.2) !important;
        border-radius: 8px !important;
        min-height: 55px !important;
        height: 55px !important;
        padding: 0px 20px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        border-bottom: 3px solid rgba(128, 128, 128, 0.2) !important;
        margin-right: 5px !important;
    }
    
    /* Fonte das abas */
    div[data-testid="stSegmentedControl"] p,
    div[data-testid="stSegmentedControl"] span {
        font-size: 15px !important;
        font-weight: 600 !important;
        color: var(--text-color) !important;
        opacity: 0.8 !important;
    }
    
    /* Estilo da aba ATIVA usando as cores primárias do Streamlit */
    div[data-testid="stSegmentedControl"] label[data-checked="true"],
    div[data-testid="stSegmentedControl"] label:has(input:checked) {
        border: 1px solid var(--primary-color) !important;
        border-bottom: 3px solid var(--primary-color) !important;
    }
    
    div[data-testid="stSegmentedControl"] label[data-checked="true"] p,
    div[data-testid="stSegmentedControl"] label:has(input:checked) p,
    div[data-testid="stSegmentedControl"] label[data-checked="true"] span,
    div[data-testid="stSegmentedControl"] label:has(input:checked) span {
        color: var(--primary-color) !important;
        opacity: 1 !important;
    }
    
    /* Aumenta a margem abaixo da linha divisória (---) para afastar os cards ainda mais */
    hr {
        margin-top: 10px !important;
        margin-bottom: 35px !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    chosen_tab = st.segmented_control("Navegação", abas, default=default_tab, key="active_tab_nav", label_visibility="collapsed", width="stretch")
    
    # Se o usuário não selecionar nada (desmarcar), forçamos para a aba padrão para evitar tela em branco
    if not chosen_tab:
        chosen_tab = default_tab
        
    st.markdown("---")

    # --- RENDERIZAÇÃO DAS ABAS ---
    
    # ABA: CALENDÁRIO
    if chosen_tab == "📅 Calendário":
        with st.container():
            render_tab_calendario()

    # --- ABA 0: EQUIPE (DIVISÃO DE TRABALHO) ---
    if chosen_tab == "👥 Responsáveis":
        with st.container():
            st.subheader("Análise por Responsável (Divisão de Trabalho)")
            
            # Agrupamento por Responsável
            df_equipe_agg = df_filtered.copy()
            # Encurtamento de nomes local para exibição
            def short_name(name):
                if not isinstance(name, str) or not name: return name
                parts = name.split()
                return f"{parts[0]} {parts[1][0]}." if len(parts) >= 2 else name
    
            df_equipe_agg['Responsavel'] = df_equipe_agg['Responsavel'].apply(short_name)
            df_equipe_agg = df_equipe_agg.groupby('Responsavel').agg(
                Total=('Status_Prazo', 'count'),
                Em_Elaboracao=('Is_Elaboracao', 'sum'),
                Atrasadas=('Status_Prazo', lambda x: x.isin(['Atrasada']).sum()),
                Urgencia=('Status_Prazo', lambda x: x.isin(['Urgência']).sum()),
                Alertas=('Status_Prazo', lambda x: (x == 'Alerta de Prazo').sum())
            ).reset_index()
    
            # Garante que as colunas sejam numéricas para evitar erros de cálculo
            for col in ['Total', 'Em_Elaboracao', 'Atrasadas', 'Urgencia', 'Alertas']:
                df_equipe_agg[col] = pd.to_numeric(df_equipe_agg[col], errors='coerce').fillna(0)
            df_equipe_agg['Total Critico'] = df_equipe_agg['Atrasadas'] + df_equipe_agg['Urgencia'] + df_equipe_agg['Alertas']
            df_equipe_agg = df_equipe_agg.sort_values('Total', ascending=False)
    
            if not df_equipe_agg.empty:
                col_e1, col_e2 = st.columns(2)
                with col_e1: render_volume_by_responsible(df_equipe_agg)
                with col_e2: render_delays_by_responsible(df_equipe_agg)
    
            st.markdown("##### Detalhamento por Equipe")
            st.dataframe(df_equipe_agg, use_container_width=True, hide_index=True)

    # --- ABA 1: MALHAS ---
    if chosen_tab == "🏙️ Visão por Malha":
        with st.container():
            st.subheader("Análise Consolidada por Malha")
            df_malha_agg = df_filtered.groupby(col_malha).agg(
                Total=('Status_Prazo', 'count'),
                Atrasadas=('Status_Prazo', lambda x: x.isin(['Atrasada']).sum())
            ).reset_index()
            
            # Garante que as colunas sejam numéricas (evita erro: str / int)
            df_malha_agg['Total'] = pd.to_numeric(df_malha_agg['Total'], errors='coerce').fillna(0)
            df_malha_agg['Atrasadas'] = pd.to_numeric(df_malha_agg['Atrasadas'], errors='coerce').fillna(0)
    
            df_malha_agg['% Atraso'] = (df_malha_agg['Atrasadas'] / df_malha_agg['Total'] * 100).round(1)
            df_malha_agg = df_malha_agg.sort_values('Total', ascending=False)
            
            if not df_malha_agg.empty:
                col_m1, col_m2 = st.columns(2)
                with col_m1: render_volume_by_mesh(df_malha_agg, col_malha)
                with col_m2: render_delays_by_mesh(df_malha_agg, col_malha)
    
            st.dataframe(df_malha_agg, use_container_width=True, hide_index=True)

    # --- ABA 2: REGIÕES ---
    if chosen_tab == "🗺️ Visão por Região":
        with st.container():
            st.subheader("Análise Consolidada por Região")
            df_regiao_agg = df_filtered.groupby(col_regiao).agg(
                Total=('Status_Prazo', 'count'),
                Atrasadas=('Status_Prazo', lambda x: x.isin(['Atrasada']).sum()),
                Urgencia=('Status_Prazo', lambda x: (x == 'Urgência').sum()),
                Alertas=('Status_Prazo', lambda x: (x == 'Alerta de Prazo').sum())
            ).reset_index()
    
            # Garante que as colunas sejam numéricas
            for col in ['Total', 'Atrasadas', 'Urgencia', 'Alertas']:
                df_regiao_agg[col] = pd.to_numeric(df_regiao_agg[col], errors='coerce').fillna(0)
    
            df_regiao_agg['Total Critico'] = df_regiao_agg['Atrasadas'] + df_regiao_agg['Urgencia'] + df_regiao_agg['Alertas']
            df_regiao_agg = df_regiao_agg.sort_values('Total', ascending=False)
            
            # Filtro de peso se disponível
            if 'Peso' in df_filtered.columns:
                regioes_selecionadas = st.multiselect("Regiões para Qtde x Peso", options=df_regiao_agg[col_regiao].tolist(), default=df_regiao_agg[col_regiao].tolist()[:5])
                if regioes_selecionadas:
                    df_peso_base = df_filtered[df_filtered[col_regiao].isin(regioes_selecionadas)].copy()
                    df_peso_agg = df_peso_base.groupby([col_regiao, 'Peso']).size().reset_index(name='Quantidade')
                    if not df_peso_agg.empty:
                        render_qty_x_weight_chart(df_peso_agg, col_regiao)
    
            st.dataframe(df_regiao_agg, use_container_width=True, hide_index=True)

    # --- ABA 3: DETALHES (Modularizado) ---
    if chosen_tab == "📋 Dados Detalhados":
        with st.container():
            render_tab_detalhes(df_filtered, col_situacao)

    # --- ABA 4: RELATÓRIOS & GESTÃO ---
    if chosen_tab == "📊 Relatórios":
        with st.container():
            try:
                conn_app = db_manager.get_connection_config(read_only=True)
                hoje_str = db_manager.get_agora_br().strftime('%Y-%m-%d')
                
                # Juntar com usuários para ter o nome (trazendo todo o histórico)
                query_eventos = f"""
                    SELECT e.*, COALESCE(u.nome, 'Não Atribuído') as nome_responsavel 
                    FROM eventos_diarios e 
                    LEFT JOIN usuarios u ON e.matricula_responsavel = u.matricula 
                """
                df_eventos_all = pd.read_sql(query_eventos, conn_app)
                
                if not df_eventos_all.empty:
                    # Extrair apenas a data (YYYY-MM-DD)
                    df_eventos_all['data'] = pd.to_datetime(df_eventos_all['data_evento']).dt.strftime('%Y-%m-%d')
                    
                    # --- GRÁFICO: Solicitações Tratadas (Equipe) ---
                    st.subheader("Solicitações Tratadas (Equipe)")
                    
                    import plotly.express as px
                    
                    df_tratadas = df_eventos_all[df_eventos_all['tipo_evento'] == 'TRATADA'].copy()
                    
                    datas_unicas = sorted(df_eventos_all['data'].dropna().unique().tolist())
                    if datas_unicas:
                        data_min = pd.to_datetime(datas_unicas[0]).date()
                        data_max = pd.to_datetime(datas_unicas[-1]).date()
                    else:
                        data_min = data_max = date.today()
                        
                    limite = date(2026, 7, 7)
                    data_min = max(data_min, limite)
                    
                    col_p1, _ = st.columns([1, 4])
                    with col_p1:
                        datas_selecionadas = st.date_input(
                            "Período de Análise:", 
                            value=(max(data_min, data_max - timedelta(days=15)), data_max), 
                            min_value=limite, 
                            max_value=data_max,
                            key="hist_data_usr"
                        )
                    
                    if isinstance(datas_selecionadas, tuple):
                        d_inicio = datas_selecionadas[0]
                        d_fim = datas_selecionadas[1] if len(datas_selecionadas) > 1 else datas_selecionadas[0]
                    else:
                        d_inicio = d_fim = datas_selecionadas
                        
                    d_inicio_str = d_inicio.strftime('%Y-%m-%d')
                    d_fim_str = d_fim.strftime('%Y-%m-%d')
                    
                    df_usr_filtered = df_tratadas[
                        (df_tratadas['data'] >= d_inicio_str) &
                        (df_tratadas['data'] <= d_fim_str)
                    ] if not df_tratadas.empty else pd.DataFrame()
                    
                    if not df_usr_filtered.empty:
                        df_user_grouped = df_usr_filtered.groupby(['data', 'nome_responsavel']).size().reset_index(name='Tratadas')
                        df_user_grouped['data_exibicao'] = pd.to_datetime(df_user_grouped['data']).dt.strftime('%d/%m/%Y')
                        
                        df_user_grouped['primeiro_nome'] = df_user_grouped['nome_responsavel'].apply(
                            lambda x: str(x).split()[0] if str(x).split() else ""
                        )
                        
                        ordem_usuarios = df_user_grouped.groupby('nome_responsavel')['Tratadas'].sum().sort_values(ascending=False).index.tolist()
                        
                        fig_user = px.bar(
                            df_user_grouped, 
                            x='data_exibicao', 
                            y='Tratadas', 
                            color='nome_responsavel',
                            barmode='group',
                            text='primeiro_nome',
                            title=f"Solicitações Tratadas (Equipe): {d_inicio.strftime('%d/%m/%Y')} a {d_fim.strftime('%d/%m/%Y')}",
                            category_orders={"nome_responsavel": ordem_usuarios}
                        )
                        fig_user.update_traces(textposition='outside')
                        fig_user.update_layout(
                            xaxis_title="Data", 
                            yaxis_title="Quantidade Tratada", 
                            yaxis_tickformat="d",
                            margin=dict(l=10, r=10, t=35, b=10),
                            showlegend=False
                        )
                        fig_user.update_xaxes(type='category')
                        st.plotly_chart(fig_user, use_container_width=True)
                    else:
                        st.info("Nenhuma solicitação tratada encontrada no período selecionado.")
                            
                    # --- Gráfico 3: Performance por Técnico ---
                    st.markdown("---")
                    st.subheader("Performance por Técnico")
                    
                    todos_usuarios_d1 = sorted(df_eventos_all['nome_responsavel'].dropna().unique().tolist())
                    hoje = date.today()
                    limite_inferior = date(2026, 7, 7)
                    data_inicio_padrao = max(limite_inferior, hoje - timedelta(days=15))
                    
                    # Estilo CSS global para garantir alinhamento vertical perfeito dos seletores
                    st.markdown("""
                        <style>
                        div[data-testid="stDateInput"], div[data-testid="stDateInput"] > div {
                            max-width: 270px !important;
                        }
                        </style>
                    """, unsafe_allow_html=True)

                    # Disposição dos seletores de Responsável e Período alinhados lado a lado
                    col_resp, col_perio, _ = st.columns([2.2, 1.3, 3.5])
                    
                    with col_resp:
                        resp_d1 = st.selectbox("Selecione o Responsável:", options=todos_usuarios_d1, key="d1_responsavel")
                        
                    with col_perio:
                        datas_d1 = st.date_input(
                            "Período de Análise:",
                            value=(data_inicio_padrao, hoje),
                            min_value=limite_inferior,
                            max_value=hoje,
                            key="d1_periodo"
                        )
                        
                    if resp_d1 and len(datas_d1) == 2:
                        d1_inicio, d1_fim = datas_d1
                        df_perf = db_manager.get_performance_d1(resp_d1, data_inicio=d1_inicio.strftime('%Y-%m-%d'), data_fim=d1_fim.strftime('%Y-%m-%d'))
                        
                        if not df_perf.empty:
                            df_perf['Data_Exibicao'] = pd.to_datetime(df_perf['Data']).dt.strftime('%d/%m/%Y')
                            
                            import plotly.graph_objects as go
                            fig_d1 = go.Figure()
                            
                            fig_d1.add_trace(go.Bar(
                                x=df_perf['Data_Exibicao'], 
                                y=df_perf['Novas'], 
                                name='Novas (Entrada)',
                                marker_color='#3b82f6',
                                text=df_perf['Novas'],
                                textposition='outside'
                            ))
                            fig_d1.add_trace(go.Bar(
                                x=df_perf['Data_Exibicao'], 
                                y=df_perf['Tratadas'], 
                                name='Tratadas (Saída)',
                                marker_color='#10b981',
                                text=df_perf['Tratadas'],
                                textposition='outside'
                            ))
                            fig_d1.add_trace(go.Bar(
                                x=df_perf['Data_Exibicao'], 
                                y=df_perf['Pendentes_Iniciadas'], 
                                name='Pendências (Em Elaboração)',
                                marker_color='#f59e0b',
                                text=df_perf['Pendentes_Iniciadas'],
                                textposition='outside'
                            ))
                                                        
                            fig_d1.update_layout(
                                title=f"Desempenho Individual: {resp_d1} ({d1_inicio.strftime('%d/%m/%Y')} a {d1_fim.strftime('%d/%m/%Y')})",
                                xaxis_title="Data",
                                yaxis_title="Quantidade",
                                barmode='group',
                                hovermode='x unified',
                                margin=dict(l=10, r=10, t=50, b=10),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                            )
                            fig_d1.update_xaxes(type='category')
                            st.plotly_chart(fig_d1, use_container_width=True)
                        else:
                            st.warning(f"Não há dados consolidados para {resp_d1} no período selecionado.")
                        
                    # --- Gráfico 4: Fluxo Diário de Demandas (Novas x Tratadas) ---
                    st.markdown("---")
                    # --- Seção: Análise de Demanda ---
                    st.markdown("---")
                    st.subheader("Análise de Demanda")

                    regioes_opcoes = ["Todas (Visão Global)"] + db_manager.get_lista_regioes_eventos()
                    todos_responsaveis_opcoes = ["Todos (Visão Global)"] + sorted(df_eventos_all['nome_responsavel'].dropna().unique().tolist())

                    hoje_fluxo = date.today()
                    limite_fluxo = date(2026, 7, 7)
                    data_inicio_fluxo_padrao = max(limite_fluxo, hoje_fluxo - timedelta(days=15))

                    # 1. Filtros posicionados lado a lado: [FILTRO REGIÃO] [FILTRO RESPONSÁVEL] [PERÍODO DE ANÁLISE]
                    col_f1, col_f2, col_f3 = st.columns([1.8, 2.2, 1.5])
                    with col_f1:
                        regiao_sel = st.selectbox("Selecione a Região:", options=regioes_opcoes, key="fluxo_regiao")
                    with col_f2:
                        resp_sel = st.selectbox("Selecione o Responsável:", options=todos_responsaveis_opcoes, key="fluxo_responsavel")
                    with col_f3:
                        datas_fluxo = st.date_input(
                            "Período de Análise:",
                            value=(data_inicio_fluxo_padrao, hoje_fluxo),
                            min_value=limite_fluxo,
                            max_value=hoje_fluxo,
                            key="fluxo_periodo"
                        )

                    if len(datas_fluxo) == 2:
                        flx_inicio, flx_fim = datas_fluxo
                        df_fluxo = db_manager.get_fluxo_diario_novas_tratadas(
                            data_inicio=flx_inicio.strftime('%Y-%m-%d'),
                            data_fim=flx_fim.strftime('%Y-%m-%d'),
                            regiao=regiao_sel,
                            responsavel=resp_sel
                        )
                        
                        if not df_fluxo.empty:
                            df_fluxo['Data_Exibicao'] = pd.to_datetime(df_fluxo['Data']).dt.strftime('%d/%m/%Y')
                            
                            tot_novas = int(df_fluxo['Novas'].sum())
                            tot_tratadas = int(df_fluxo['Tratadas'].sum())
                            saldo = tot_novas - tot_tratadas
                            
                            # 2. CARDS KPI no formato Totais Gerais + Neon para Saldo do Período
                            st.markdown("<br>", unsafe_allow_html=True)
                            kpi1, kpi2, kpi3 = st.columns(3)
                            with kpi1:
                                premium_metric_card("Novas no Período", f"{tot_novas:,}".replace(",", "."), icon_name="people", color="#3b82f6")
                            with kpi2:
                                premium_metric_card("Tratadas no Período", f"{tot_tratadas:,}".replace(",", "."), icon_name="tick", color="#34d399")
                            with kpi3:
                                # Card Saldo com Borda Neon utilizando a mesma estrutura padronizada dos demais cards
                                neon_color = "#ef4444" if saldo > 0 else "#10b981"
                                sign_str = f"+{saldo:,}".replace(",", ".") if saldo > 0 else f"{saldo:,}".replace(",", ".")
                                premium_metric_card("Saldo do Período", sign_str, icon_name="flash", neon_glow=True, neon_color=neon_color)
                            
                            # 3. Gráfico de Barras Agrupadas
                            st.markdown("<br>", unsafe_allow_html=True)
                            df_melted = df_fluxo.melt(
                                id_vars=['Data_Exibicao'],
                                value_vars=['Novas', 'Tratadas'],
                                var_name='Tipo',
                                value_name='Quantidade'
                            )
                            
                            fig_fluxo = px.bar(
                                df_melted,
                                x='Data_Exibicao',
                                y='Quantidade',
                                color='Tipo',
                                barmode='group',
                                text='Quantidade',
                                color_discrete_map={'Novas': '#3b82f6', 'Tratadas': '#10b981'},
                                title=f"Fluxo de Manobras ({regiao_sel} | {resp_sel})"
                            )
                            fig_fluxo.update_traces(textposition='outside')
                            fig_fluxo.update_layout(
                                xaxis_title="Data",
                                yaxis_title="Quantidade de Manobras",
                                yaxis_tickformat="d",
                                legend_title_text="Tipo de Demanda",
                                hovermode='x unified',
                                margin=dict(l=10, r=10, t=40, b=10),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                            )
                            fig_fluxo.update_xaxes(type='category')
                            st.plotly_chart(fig_fluxo, use_container_width=True)

                            # 4. Gráficos de RANK (Rank das Demandas Elevadas & Rank das Demandas Controladas)
                            df_rank_saldo = db_manager.get_rank_saldo_regioes(
                                data_inicio=flx_inicio.strftime('%Y-%m-%d'),
                                data_fim=flx_fim.strftime('%Y-%m-%d'),
                                responsavel=resp_sel
                            )
                            
                            if not df_rank_saldo.empty:
                                # RANK 1: Rank das Demandas Elevadas (Saldo > 0)
                                df_rank_piores = df_rank_saldo[df_rank_saldo['Saldo'] > 0].sort_values(by=['Saldo', 'Novas'], ascending=[False, False]).copy()
                                
                                st.markdown("<br>", unsafe_allow_html=True)
                                st.markdown("#### 🚨 Rank das Demandas Elevadas")
                                st.caption("Regiões com acúmulo positivo de passivo no período (onde entraram mais demandas do que foram tratadas).")
                                
                                if not df_rank_piores.empty:
                                    df_rank_piores['Texto_Barra'] = df_rank_piores['Saldo'].apply(lambda x: f"+{x}")
                                    fig_rank_p = px.bar(
                                        df_rank_piores,
                                        x='Regiao',
                                        y='Saldo',
                                        text='Texto_Barra',
                                        color='Saldo',
                                        color_continuous_scale=['#f59e0b', '#ef4444'],
                                        title=f"Rank das Demandas Elevadas ({flx_inicio.strftime('%d/%m/%Y')} a {flx_fim.strftime('%d/%m/%Y')})"
                                    )
                                    fig_rank_p.update_traces(textposition='outside')
                                    fig_rank_p.update_layout(
                                        xaxis_title="Região",
                                        yaxis_title="Saldo de Manobras (Novas - Tratadas)",
                                        yaxis_tickformat="d",
                                        showlegend=False,
                                        coloraxis_showscale=False,
                                        margin=dict(l=10, r=10, t=40, b=10)
                                    )
                                    fig_rank_p.update_xaxes(type='category')
                                    st.plotly_chart(fig_rank_p, use_container_width=True)
                                else:
                                    st.info("Nenhuma região com demandas elevadas (saldo positivo) no período selecionado.")

                                # RANK 2: Rank das Demandas Controladas (Saldo <= 0)
                                df_rank_melhores = df_rank_saldo[df_rank_saldo['Saldo'] <= 0].sort_values(by=['Saldo', 'Novas'], ascending=[True, True]).copy()
                                
                                st.markdown("<br>", unsafe_allow_html=True)
                                st.markdown("#### 🏆 Rank das Demandas Controladas")
                                st.caption("Regiões com saldo neutro ou negativo no período (onde a capacidade de tratamento igualou ou superou as novas demandas).")
                                
                                if not df_rank_melhores.empty:
                                    df_rank_melhores['Texto_Barra'] = df_rank_melhores['Saldo'].astype(str)
                                    fig_rank_m = px.bar(
                                        df_rank_melhores,
                                        x='Regiao',
                                        y='Saldo',
                                        text='Texto_Barra',
                                        color='Saldo',
                                        color_continuous_scale=['#10b981', '#38bdf8', '#94a3b8'],
                                        title=f"Rank das Demandas Controladas ({flx_inicio.strftime('%d/%m/%Y')} a {flx_fim.strftime('%d/%m/%Y')})"
                                    )
                                    fig_rank_m.update_traces(textposition='outside')
                                    fig_rank_m.update_layout(
                                        xaxis_title="Região",
                                        yaxis_title="Saldo de Manobras (Novas - Tratadas)",
                                        yaxis_tickformat="d",
                                        showlegend=False,
                                        coloraxis_showscale=False,
                                        margin=dict(l=10, r=10, t=40, b=10)
                                    )
                                    fig_rank_m.update_xaxes(type='category')
                                    st.plotly_chart(fig_rank_m, use_container_width=True)
                                else:
                                    st.info("Nenhuma região com demandas controladas (saldo neutro ou negativo) no período selecionado.")
                            else:
                                st.info("Nenhum dado de saldo por região para os filtros selecionados.")
                        else:
                            st.info("Nenhum dado de fluxo encontrado para os filtros selecionados.")

                    # --- Seção 5: Retrato de Transição de Regiões (Handover Snapshot) ---
                    st.markdown("---")
                    st.subheader("📸 Retrato de Transição de Regiões (Handover Snapshot)")
                    st.caption("Consulte o retrato congelado do passivo de uma região no momento exato da troca de responsabilidade entre técnicos.")

                    df_trans = db_manager.get_historico_transicoes()
                    
                    if not df_trans.empty:
                        col_t_filter, col_t_content = st.columns([1, 7])
                        
                        with col_t_filter:
                            st.markdown("#### Filtros Handover")
                            regioes_trans = ["Todas (Visão Global)"] + sorted(df_trans['sigla_regiao'].unique().tolist())
                            reg_handover_sel = st.selectbox("Selecione a Região:", options=regioes_trans, key="handover_regiao")
                            
                            df_trans_filtered = df_trans.copy()
                            if reg_handover_sel != "Todas (Visão Global)":
                                df_trans_filtered = df_trans_filtered[df_trans_filtered['sigla_regiao'] == reg_handover_sel]

                        with col_t_content:
                            st.markdown(f"##### Registros de Transição Encontrados: **{len(df_trans_filtered)}**")
                            
                            # Tabela de Histórico de Transições com Detalhamento de Herdadas
                            df_trans_display = df_trans_filtered.copy()
                            df_trans_display['Data / Hora da Troca'] = pd.to_datetime(df_trans_display['data_transicao']).dt.strftime('%d/%m/%Y %H:%M')
                            
                            # Garante existência das novas colunas de detecção de herdadas
                            for col_def in ['aprovadas_herdadas', 'atrasadas_herdadas', 'du8_herdadas', 'du9_herdadas', 'du10_herdadas', 'du11_herdadas']:
                                if col_def not in df_trans_display.columns:
                                    df_trans_display[col_def] = 0
                                else:
                                    df_trans_display[col_def] = df_trans_display[col_def].fillna(0).astype(int)
                                    
                            st.dataframe(
                                df_trans_display[['Data / Hora da Troca', 'sigla_regiao', 'nome_anterior', 'nome_novo', 'aprovadas_herdadas', 'atrasadas_herdadas', 'du8_herdadas', 'du9_herdadas', 'du10_herdadas', 'du11_herdadas', 'em_elaboracao', 'total_pendentes']],
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    "sigla_regiao": st.column_config.TextColumn("Região"),
                                    "nome_anterior": st.column_config.TextColumn("Técnico Anterior"),
                                    "nome_novo": st.column_config.TextColumn("Novo Técnico"),
                                    "aprovadas_herdadas": st.column_config.NumberColumn("Aprovadas Herdadas"),
                                    "atrasadas_herdadas": st.column_config.NumberColumn("Atrasadas Herdadas"),
                                    "du8_herdadas": st.column_config.NumberColumn("8 Dias Úteis"),
                                    "du9_herdadas": st.column_config.NumberColumn("9 Dias Úteis"),
                                    "du10_herdadas": st.column_config.NumberColumn("10 Dias Úteis"),
                                    "du11_herdadas": st.column_config.NumberColumn("11 Dias Úteis"),
                                    "em_elaboracao": st.column_config.NumberColumn("Em Elaboração (Fica c/ Antigo)"),
                                    "total_pendentes": st.column_config.NumberColumn("Total Geral Região")
                                }
                            )

                            # Comparativo com o Estado Atual da Região no Live Dataset
                            if len(df_trans_filtered) > 0:
                                ultima_troca = df_trans_filtered.iloc[0]
                                sigla_u = ultima_troca['sigla_regiao']
                                
                                # Busca estado atual no live dataset
                                df_reg_atual = df[df[col_regiao].astype(str).str.strip().str[:2].str.upper() == sigla_u] if df is not None else pd.DataFrame()
                                total_atual = len(df_reg_atual)
                                
                                st.markdown(f"#### 📊 Comparativo da Última Transição (Região **{sigla_u}**)")
                                st.caption(f"Troca realizada em {pd.to_datetime(ultima_troca['data_transicao']).strftime('%d/%m/%Y %H:%M')}: De **{ultima_troca['nome_anterior']}** ➔ **{ultima_troca['nome_novo']}**")
                                st.caption("🔒 *Nota de Trava:* Solicitações 'Em Elaboração' permanecem travadas com o técnico de origem. O novo técnico herda as manobras **Aprovadas** da região.")
                                
                                k1, k2, k3, k4 = st.columns(4)
                                with k1:
                                    st.metric("📦 Aprovadas Herdadas", f"{ultima_troca.get('aprovadas_herdadas', 0)} manobras")
                                with k2:
                                    st.metric("🚨 Atrasadas Herdadas", f"{ultima_troca.get('atrasadas_herdadas', 0)} manobras")
                                with k3:
                                    st.metric("📅 Prazos (8D / 9D / 10D / 11D)", f"{ultima_troca.get('du8_herdadas',0)} | {ultima_troca.get('du9_herdadas',0)} | {ultima_troca.get('du10_herdadas',0)} | {ultima_troca.get('du11_herdadas',0)}")
                                with k4:
                                    st.metric("🔒 Em Elaboração (Técnico Antigo)", f"{ultima_troca.get('em_elaboracao', 0)} manobras")
                            
                            # Opção de exclusão para administradores caso ocorra algum registro indevido
                            if st.session_state.get("user_nivel") == "ADM":
                                with st.expander("🛠️ Gerenciar / Excluir Registro de Transição (ADM)"):
                                    opcoes_excluir = {
                                        f"ID {r['id']} - Região {r['sigla_regiao']} ({r['nome_anterior']} ➔ {r['nome_novo']} em {pd.to_datetime(r['data_transicao']).strftime('%d/%m/%Y %H:%M')})": r['id']
                                        for _, r in df_trans_filtered.iterrows()
                                    }
                                    if opcoes_excluir:
                                        trans_sel_label = st.selectbox("Selecione o registro para remover:", options=list(opcoes_excluir.keys()), key="sb_delete_handover")
                                        if st.button("🗑️ Confirmar Exclusão do Registro", key="btn_confirm_del_handover", type="primary"):
                                            id_del = opcoes_excluir[trans_sel_label]
                                            if db_manager.deletar_transicao_regiao(id_del):
                                                st.success("Registro de transição excluído com sucesso!")
                                                st.rerun()
                    else:
                        st.info("Nenhuma transição de região foi registrada ainda. As trocas efetuadas no painel de configurações gravarão automaticamente o retrato da transição.")
                        
                else:
                    st.info("Nenhum evento de produtividade registrado no histórico.")
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                print(f"ERRO CRÍTICO EM CARREGAR EVENTOS:\n{error_trace}")
                st.error(f"Não foi possível carregar eventos: {e}\n\nDetalhes no console.")
            finally:
                if 'conn_app' in locals() and conn_app:
                    try:
                        conn_app.close()
                    except Exception:
                        pass



    # --- ABA 4: CONFIGURAÇÕES (Modularizado) ---
    if chosen_tab == "⚙️ Configurações":
        with st.container():
            render_tab_config()



else:
    st.warning("⚠️ Nenhum arquivo de dados encontrado. Execute o `agendador.py` primeiro para gerar o relatório.")
    st.info("Aguardando geração do primeiro relatório...")
    
    # Botão para tentar forçar execução (opcional, avançado)
    if st.button("Tentar executar extrator agora"):
        import subprocess
        import sys
        try:
            with st.spinner('Executando extrator... (Isso pode levar alguns minutos)'):
                subprocess.run([sys.executable, "extrator_demanda.py"], check=True)
            st.success("Execução finalizada! Recarregue a página.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao executar: {e}")

# --- AUTO REFRESH SILENCIOSO (Sincronização Periódica de Dados) ---
# Aumentado para 10 minutos para evitar que a aba do usuário seja resetada constantemente
st_autorefresh(interval=600000, key="datarefresh")
