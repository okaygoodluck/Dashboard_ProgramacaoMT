import streamlit as st
import pandas as pd
import altair as alt
import glob
import os
import numpy as np
from datetime import datetime, date
from streamlit_autorefresh import st_autorefresh
import db_manager

# --- IMPORTAÇÃO DOS MÓDULOS CCP (Centro de Controle da Programação) ---
from ccp_ui import (
    DESIGN_SYSTEM, 
    inject_ui_assets, 
    ui_bridge, 
    inject_ui_css,
    login_screen,
    change_password_screen
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
# Inicializa banco de dados de sessões no startup

# Configuração da página (Deve ser a primeira linha de comando Streamlit)
st.set_page_config(
    page_title="Centro de Controle da Programação",
    page_icon="📊",
    layout="wide"
)

# --- CONFIGURAÇÃO DA PÁGINA ---

# --- SISTEMA DE AUTENTICAÇÃO E PERSISTÊNCIA CCP ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# 1. Tenta reconectar se não estiver logado
if not st.session_state.logged_in:
    # Ordem de prioridade: Cookie (Nativo) -> Query Param (Ponte JS)
    token_auth = st.context.cookies.get("control_token") or st.query_params.get("ctoken")
    
    if token_auth:
        user_data = db_manager.validar_token_sessao(token_auth)
        if user_data:
            st.session_state.logged_in = True
            st.session_state.user_matricula = user_data[0]
            st.session_state.user_nome = user_data[1]
            st.session_state.user_nivel = user_data[2]
            st.session_state.senha_provisoria = False # Sessão persistente não pede senha provisória
            
            # Atualiza LocalStorage e limpa URL se necessário
            if st.query_params.get("ctoken"):
                st.query_params.clear()
                st.rerun()
        else:
            # Token inválido: limpa rastros
            ui_bridge(delete=True)
            if st.query_params.get("ctoken"):
                st.query_params.clear()
                st.rerun()
    else:
        # Modo Descoberta: Oculto para evitar blocos fantasmas no login
        pass

# 2. Bloqueio de Acesso Global
if not st.session_state.logged_in:
    login_screen()
    st.stop()

# 3. Verificação de Senha Provisória
if st.session_state.get('senha_provisoria'):
    change_password_screen()
    st.stop()

# 4. Sincronização de Manutenção (Oculto)
if st.session_state.logged_in:
    pass

# --- CONFIGURAÇÃO DE TEMA ---
with st.sidebar:
    theme_choice = st.selectbox(
        "🌓 TEMA DO SISTEMA", 
        options=["Dark Mode", "Light Mode"], 
        index=0 if st.session_state.get('control_theme', 'Dark') == "Dark" else 1
    )
    st.session_state.control_theme = "Dark" if theme_choice == "Dark Mode" else "Light"
    ds = DESIGN_SYSTEM[st.session_state.control_theme]

# --- INJEÇÃO DE ESTILOS E ASSETS ---
inject_ui_css(st.session_state.control_theme)
inject_ui_assets()


# --- SIDEBAR INFO ---
if st.session_state.user_nivel == "Usuario":
    st.sidebar.markdown(f"**👤 Usuário:** {st.session_state.user_nome}")
else:
    st.sidebar.markdown(f"**🎖️ Administrador:** {st.session_state.user_nome}")

if st.sidebar.button("🚪 Sair", use_container_width=True):
    # Invalida sessão no DB e no Cookie
    token_cookie = st.context.cookies.get("control_token")
    if token_cookie:
        db_manager.remover_sessao(token_cookie)
        ui_bridge(delete=True)
    
    st.session_state.logged_in = False
    st.rerun()

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
        return 0
    
    # Converte para datetime se não for
    if not isinstance(data_inicio, datetime):
        try:
            # Tenta formatos comuns PT-BR
            data_inicio = pd.to_datetime(data_inicio, dayfirst=True)
        except:
            return 0
            
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
        return 0

# Função para calcular status de atraso
def verificar_status_atraso(row):
    # Situações que indicam conclusão ou cancelamento (ignora atraso)
    # ATUALIZAÇÃO: O usuário pediu para considerar atraso APENAS se estiver "APROVADA"
    situacao = str(row.get('Situação', '')).upper()
    
    # Se NÃO contiver "APROVADA", consideramos neutro/concluído para fins de KPI de atraso
    if "APROVADA" not in situacao:
        return "Concluída/Outros"
    
    dias_restantes = row.get('Dias_Uteis_Restantes', 0)
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
        is_dark = st.session_state.get('control_theme', 'Dark') == 'Dark'
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
    # Quebra de cache: forçando o Streamlit a ler a nova função de datas atualizada
    import db_manager
    
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
            except:
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
            
            # Garante que a coluna Finalidade exista para a função (renomeia se achar)
            if col_finalidade:
                df['Finalidade'] = df[col_finalidade]
            else:
                df['Finalidade'] = ''

            # Aplica regra de status
            df['Status_Prazo'] = df.apply(verificar_status_atraso, axis=1)
            
            # Tenta obter a data de extração
            data_extracao = None
            if 'Data_Extracao' in df.columns:
                # Se veio do banco, pega da primeira linha (assume que todas são iguais do snapshot)
                try:
                    data_extracao = pd.to_datetime(df['Data_Extracao'].iloc[0])
                except:
                    data_extracao = datetime.now()
            elif 'arquivo_mais_recente' in locals():
                # Se veio do Excel
                try:
                    timestamp = os.path.getmtime(arquivo_mais_recente)
                    data_extracao = datetime.fromtimestamp(timestamp)
                except:
                    data_extracao = datetime.now()
            else:
                 # Fallback
                 data_extracao = datetime.now()

            # --- INTEGRAÇÃO MESÃO DIÁRIO ---
            try:
                hoje = datetime.now()
                pasta_mesao = r"I:\IT\ODCO\PROGRAMACAO_MT\Mesao_Diario"
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
                        col_sol_db = next((c for c in df.columns if 'Solicit' in c and 'Status' not in c), 'Solicitação')
                        col_sol_ms = next((c for c in df_mesao.columns if 'Solicit' in c and 'Status' not in c), 'Solicitação')
                        
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
    # Prepara coluna Em Elaboração para as contagens nas tabelas
    if col_situacao and col_situacao in df.columns:
        df['Is_Elaboracao'] = df[col_situacao].astype(str).str.upper().str.contains('ELABORAÇÃO|ELABORACAO')
    else:
        df['Is_Elaboracao'] = False

    # --- MAPEAMENTO GLOBAL DO RESPONSÁVEL (Real-time via Banco) ---
    df['temp_sigla'] = df[col_regiao].astype(str).str.strip().str[:2].str.upper()
    df_map = db_manager.get_mapeamento_regioes()
    
    if not df_map.empty:
        df = df.merge(df_map[['sigla_regiao', 'responsavel']], left_on='temp_sigla', right_on='sigla_regiao', how='left')
        df['Responsavel'] = df['responsavel'].fillna("Não Atribuído")
        df = df.drop(columns=['temp_sigla', 'sigla_regiao', 'responsavel'])
    else:
        df['Responsavel'] = "Não Atribuído"
        df = df.drop(columns=['temp_sigla'])

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

    # --- 2. FILTROS (Movidos para o topo para garantir reatividade dos KPIs) ---
    st.markdown('<div class="animate-target" style="margin-top: var(--space-xs); margin-bottom: var(--space-xs);">', unsafe_allow_html=True)
    with st.expander("🔍 FILTROS DE COMANDO • PROTOCOLO VANGUARD", expanded=False):
        c_filtro0, c_filtro1, c_filtro2, c_filtro3 = st.columns(4)
        
        # 1. Filtro de Responsável (Foco Operacional)
        lista_responsaveis = sorted(df_top['Responsavel'].unique())
        
        if st.session_state.user_nivel == "Usuario":
            if st.session_state.user_nome in lista_responsaveis:
                filtro_responsavel = c_filtro0.multiselect("👩‍💻 Responsável (Travado)", options=lista_responsaveis, default=[st.session_state.user_nome], key="v_filter_resp", disabled=True)
            else:
                st.sidebar.error(f"Seu nome ({st.session_state.user_nome}) não foi encontrado como responsável.")
                filtro_responsavel = c_filtro0.multiselect("👩‍💻 Filtrar por Responsável", options=lista_responsaveis, default=lista_responsaveis, key="v_filter_resp")
        else:
            filtro_responsaveis_all = sorted(df['Responsavel'].unique())
            filtro_responsavel = c_filtro0.multiselect("👩‍💻 Filtrar por Responsável", options=filtro_responsaveis_all, default=filtro_responsaveis_all, key="v_filter_resp")
            
        df_filtered_resp = df[df['Responsavel'].isin(filtro_responsavel)]

        # 2. Filtro de Malha (Opções sempre visíveis)
        lista_malhas_total = sorted(df_top[col_malha].unique())
        default_malhas = sorted(df_filtered_resp[col_malha].unique()) if not df_filtered_resp.empty else []
        filtro_malha = c_filtro1.multiselect("Filtrar por Malha", options=lista_malhas_total, default=default_malhas, key="v_filter_malha")
        
        # 3. Filtro de Região (Opções sempre visíveis)
        lista_regioes_total = sorted(df_top[col_regiao].unique())
        df_filtered_temp = df_filtered_resp[df_filtered_resp[col_malha].isin(filtro_malha)] if not df_filtered_resp.empty else pd.DataFrame()
        default_regioes = sorted(df_filtered_temp[col_regiao].unique()) if not df_filtered_temp.empty else []
        filtro_regiao = c_filtro2.multiselect("Filtrar por Região", options=lista_regioes_total, default=default_regioes, key="v_filter_regiao")

        # 4. Filtro de Data
        cols_data_possiveis = [c for c in df.columns if 'data' in c.lower() or 'inicio' in c.lower() or 'criacao' in c.lower()]
        if not cols_data_possiveis: cols_data_possiveis = [col_data]
        col_filtro_data = c_filtro3.selectbox("Coluna de Data", options=cols_data_possiveis, index=0, key="v_filter_col_data")

        if col_filtro_data != col_data:
             df[col_filtro_data] = pd.to_datetime(df[col_filtro_data], dayfirst=True, errors='coerce')

        min_date = df[col_filtro_data].min()
        max_date = df[col_filtro_data].max()
        min_date = min_date.date() if not pd.isna(min_date) else datetime.now().date()
        max_date = max_date.date() if not pd.isna(max_date) else datetime.now().date()
        if min_date > max_date: min_date = max_date

        # Data Padrão: 8 dias úteis
        hoje_date = pd.Timestamp.now().normalize().date()
        feriados_np_filtro = np.array(FERIADOS_BASE, dtype='datetime64[D]')
        try:
            oitavo_dia_util = np.busday_offset(hoje_date, 8, roll='forward', weekmask='1111100', holidays=feriados_np_filtro)
            default_max = pd.to_datetime(oitavo_dia_util).date()
        except: default_max = hoje_date + pd.Timedelta(days=12)
            
        max_value_picker = max(max_date, default_max)
        
        # Filtro de Data com PERSISTÊNCIA (Session State key)
        filtro_data = c_filtro3.date_input(
            "Filtrar por Período", 
            value=(min(min_date, default_max), default_max), 
            min_value=min_date, 
            max_value=max_value_picker, 
            format="DD/MM/YYYY",
            key="v_filter_date"
        )
    st.markdown('</div>', unsafe_allow_html=True)

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
                <span id="digital-clock" style="font-family: 'Space Grotesk', sans-serif; font-size: 1.1rem; font-weight: 700; color: var(--text-primary); letter-spacing: 1px;">{datetime.now().strftime('%H:%M:%S')}</span>
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
        @keyframes pulse-red {
            0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
            70% { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
            100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
        }
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
        #digital-clock {
            background: linear-gradient(135deg, var(--accent-color), #3b82f6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
    </style>
    """, unsafe_allow_html=True)

    # --- MOTOR DE ATIVAÇÃO ---
    inject_ui_assets()

    # --- SISTEMA DE ALERTAS (Notificações Persistentes) ---
    if 'control_dismissed' not in st.session_state:
        st.session_state.control_dismissed = set()

    # Detecta urgências ativas no escopo df_filtered que ainda não foram descartadas
    # Regra: Só emitir alerta se a urgência for SIM e a Situação contiver "APROVADA"
    urgencias_ativas = df_filtered[
        df_filtered[col_urgencia].astype(str).str.upper().str.contains('SIM|S') &
        df_filtered[col_situacao].astype(str).str.upper().str.contains('APROVADA')
    ].copy()
    
    # Filtra as que o usuário ainda não confirmou leitura
    alertas_pendentes = urgencias_ativas[~urgencias_ativas['Solicitação'].astype(str).isin(st.session_state.control_dismissed)]

    if not alertas_pendentes.empty:
        head_c1, head_c2 = st.columns([3, 1])
        with head_c1:
            st.markdown(f'<h3 style="color: #ef4444; font-size: 0.8rem; margin-bottom: var(--space-sm); font-weight: 700; display: flex; align-items: center; gap: 8px;"><span style="background: #ef4444; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.6rem;">!</span> PROTOCOLOS CRÍTICOS DETECTADOS ({len(alertas_pendentes)})</h3>', unsafe_allow_html=True)
        with head_c2:
            if st.button("✓ Confirmar Tudo", key="btn_confirm_all", help="Marcar todos os alertas atuais como lidos", use_container_width=True):
                for solicit in alertas_pendentes['Solicitação'].astype(str):
                    st.session_state.control_dismissed.add(solicit)
                st.rerun()
        
        # Grid de Alertas: 4 colunas por linha
        n_cols = 4
        num_alertas = len(alertas_pendentes)
        
        for i in range(0, num_alertas, n_cols):
            cols = st.columns(n_cols)
            batch = alertas_pendentes.iloc[i : i + n_cols]
            
            for j, (idx, row) in enumerate(batch.iterrows()):
                solicit_id = str(row['Solicitação'])
                tem_email = row.get('Tem_Email', False)
                
                # Define as classes e labels baseadas no status do e-mail
                card_class = "vanguard-card-confirmed" if tem_email else "vanguard-card-pending"
                header_class = "card-header-confirmed" if tem_email else "card-header-pending"
                header_label = "📧 E-MAIL RECEBIDO" if tem_email else "⚠️ AGUARDANDO E-MAIL"
                
                with cols[j]:
                    st.markdown(f"""
                    <div class="vanguard-alert-card {card_class}">
                        <div class="{header_class}">{header_label}</div>
                        <div class="card-body">
                            <div style="color: var(--text-primary); font-size: 1.05rem; font-weight: 700; line-height: 1.2;">Solicitação {solicit_id}</div>
                            <div style="color: var(--text-secondary); font-size: 0.85rem; font-weight: 500;">📍 {row[col_regiao]}</div>
                            <div style="color: var(--text-secondary); font-size: 0.85rem; font-weight: 500;">⏳ {row['Dias_Uteis_Restantes']} dias úteis restantes</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    label_btn = "✓ Marcar como visto"
                    if st.button(label_btn, key=f"btn_alert_{solicit_id}", use_container_width=True):
                        st.session_state.control_dismissed.add(solicit_id)
                        st.rerun()
        
        # Espaçamento compactado

    # --- LAYOUT SIMÉTRICO VANGUARD (KPIs GERAIS) ---
    kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5 = st.columns(5)
    
    with kpi_col1:
        premium_metric_card(f"{prefix_kpi}Fila de Processamento", total_solicitacoes, icon_name="people", color="#3b82f6", is_vanguard=True)
    
    with kpi_col2:
        premium_metric_card(f"{prefix_kpi}Atrasados", qtd_atrasadas, icon_name="timer", color="#f87171")
        
    with kpi_col3:
        # KPI de Saúde do Sistema (No Prazo / Total) centralizado
        percent_prazo = round((total_solicitacoes - qtd_atrasadas) / total_solicitacoes * 100, 1) if total_solicitacoes > 0 else 100
        circular_progress_ring("Saúde Operacional", percent_prazo, color="#34d399")
        
    with kpi_col4:
        premium_metric_card(f"{prefix_kpi}Urgentes", qtd_urgencia, icon_name="flash", color="#fbbf24")
        
    with kpi_col5:
        premium_metric_card(f"{prefix_kpi}Alertas", qtd_alerta, icon_name="info", color="#818cf8")

    # Automação de Snapshot Diário (Pós-processamento dos KPIs)
    tratar_snapshot_diario(total_solicitacoes, qtd_atrasadas, qtd_alerta, qtd_urgencia, (total_solicitacoes - qtd_atrasadas))


    # 3. ABAS DE VISUALIZAÇÃO (Symmetry Mode - Responsivo)
    abas = ["📅 Calendário", "👥 Responsáveis", "🏙️ Visão por Malha", "🗺️ Visão por Região", "📋 Dados Detalhados"]
    
    # Nível Gerencial ou ADM vê Histórico
    if st.session_state.user_nivel in ["Gerencial", "ADM"]:
        abas.append("📊 Histórico")
    
    # Nível ADM vê Configurações
    if st.session_state.user_nivel == "ADM":
        abas.append("⚙️ Configurações")
        
    abas_principais = st.tabs(abas)
    
    # Desestruturação Dinâmica baseada nos itens da lista 'abas'
    tabs_map = {}
    for i, nome_aba in enumerate(abas):
        tabs_map[nome_aba] = abas_principais[i]
    
    # Extração das abas para uso posterior
    tab_calendario = tabs_map.get("📅 Calendário")
    tab_equipe = tabs_map.get("👥 Responsáveis")
    tab_malha = tabs_map.get("🏙️ Visão por Malha")
    tab_regiao = tabs_map.get("🗺️ Visão por Região")
    tab_dados = tabs_map.get("📋 Dados Detalhados")
    tab_historico = tabs_map.get("📊 Histórico") 
    tab_config = tabs_map.get("⚙️ Configurações")

    # --- RENDERIZAÇÃO DAS ABAS ---
    
    # ABA: CALENDÁRIO
    if tab_calendario:
        with tab_calendario:
            render_tab_calendario()

    # --- ABA 0: EQUIPE (DIVISÃO DE TRABALHO) ---
    with tab_equipe:
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
            current_theme = st.session_state.get('control_theme', 'Dark')
            with col_e1: render_volume_by_responsible(df_equipe_agg, theme=current_theme)
            with col_e2: render_delays_by_responsible(df_equipe_agg, theme=current_theme)

        st.markdown("##### Detalhamento por Equipe")
        st.dataframe(df_equipe_agg, use_container_width=True, hide_index=True)

    # --- ABA 1: MALHAS ---
    with tab_malha:
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
            current_theme = st.session_state.get('control_theme', 'Dark')
            with col_m1: render_volume_by_mesh(df_malha_agg, col_malha, theme=current_theme)
            with col_m2: render_delays_by_mesh(df_malha_agg, col_malha, theme=current_theme)

        st.dataframe(df_malha_agg, use_container_width=True, hide_index=True)
    # --- ABA 2: REGIÕES ---
    with tab_regiao:
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
                    current_theme = st.session_state.get('control_theme', 'Dark')
                    render_qty_x_weight_chart(df_peso_agg, col_regiao, theme=current_theme)

        st.dataframe(df_regiao_agg, use_container_width=True, hide_index=True)

    # --- ABA 3: DETALHES (Modularizado) ---
    with tab_dados:
        render_tab_detalhes(df_filtered, col_situacao)

    # --- ABA 4: HISTÓRICO & GESTÃO ---
    if tab_historico:
        with tab_historico:
            st.subheader("Histórico de Indicadores (Evolução Diária)")
            df_kpi_hist = db_manager.get_historico_kpis(dias=60)
            
            if not df_kpi_hist.empty:
                # Gráfico de Tendência
                import altair as alt
                
                # Melt para formato longo
                df_melted = df_kpi_hist.melt(id_vars=['data_ref'], value_vars=['atrasadas', 'alertas', 'urgencias'], 
                                            var_name='Indicador', value_name='Quantidade')
                
                chart = alt.Chart(df_melted).mark_line(point=True).encode(
                    x=alt.X('data_ref:T', title='Data'),
                    y=alt.Y('Quantidade:Q', title='Quantidade de Ocorrências', axis=alt.Axis(format='d')),
                    color=alt.Color('Indicador:N', scale=alt.Scale(domain=['atrasadas', 'alertas', 'urgencias'], range=['#f87171', '#818cf8', '#fbbf24'])),
                    tooltip=['data_ref', 'Indicador', 'Quantidade']
                ).properties(height=350).interactive()
                
                st.altair_chart(chart, use_container_width=True)
                
                st.markdown("##### Tabela Consolidada de Snapshots")
                st.dataframe(df_kpi_hist.sort_values('data_ref', ascending=False), use_container_width=True, hide_index=True)
                
                # Exportação
                csv_hist = df_kpi_hist.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Exportar Histórico Completo (CSV)",
                    data=csv_hist,
                    file_name=f'historico_kpis_{date.today()}.csv',
                    mime='text/csv',
                    key='btn_export_hist'
                )
            else:
                st.info("📊 O histórico de indicadores começará a ser construído a partir de hoje.")
                st.image("https://img.freepik.com/free-vector/data-analysis-concept-illustration_114360-1511.jpg", width=300)

    # --- ABA 4: CONFIGURAÇÕES (Modularizado) ---
    if tab_config:
        with tab_config:
            render_tab_config()

    st.markdown("---")
    # Botão de Download
    csv = df_filtered.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Baixar Dados Filtrados (CSV)",
        data=csv,
        file_name='demanda_filtrada.csv',
        mime='text/csv',
    )

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
st_autorefresh(interval=30000, key="datarefresh")
