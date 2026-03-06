import streamlit as st
import pandas as pd
import altair as alt
import glob
import os
import time
import numpy as np
from datetime import datetime, date
from streamlit_autorefresh import st_autorefresh

# Configuração da página
st.set_page_config(
    page_title="Análise de Demanda de Serviço",
    page_icon="📊",
    layout="wide"
)

# --- AUTO REFRESH SILENCIOSO ---
# Atualiza a cada 60 segundos (60000ms) sem recarregar a página inteira (se possível)
# Isso evita que a tela pisque ou escureça
st_autorefresh(interval=60000, key="datarefresh")

# --- CSS PERSONALIZADO ---
# Esconde o spinner de "Running" e ajusta layout para não escurecer
st.markdown("""
<style>
    /* Esconde o spinner superior direito */
    .stApp > header {visibility: hidden;}
    .stSpinner {visibility: hidden;}
    
    /* Melhora visual dos cards */
    .metric-card {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

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
    
    # Gera array de datas úteis (busday)
    # weekmask='1111100' significa Seg-Sex são dias úteis.
    
    # Se Data Inicio for no futuro (ex: 18/03), busday_count(hoje, inicio) retorna positivo.
    # Se Data Inicio for no passado (ex: 01/03), busday_count(hoje, inicio) retorna negativo (erro no numpy antigo? Testar).
    # O numpy.busday_count conta dias entre d1 e d2. Se d1 > d2, retorna negativo.
    # Vamos garantir: busday_count(hoje, data_inicio)
    
    try:
        return np.busday_count(hoje.date(), data_inicio.date(), weekmask='1111100')
    except:
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
    finalidade = str(row.get('Finalidade', '')).upper()
    
    # Se a data já passou (negativo), é Atrasada
    if dias_restantes < 0:
        return "Atrasada"

    # REGRA ESPECIAL: TERCEIROS OU NOVOS CONSUMIDORES (Prazo de 5 dias)
    # Se a finalidade for uma dessas, a regra dos 8 dias é substituída por 5
    if "TERCEIROS" in finalidade or "NOVOS CONSUMIDORES" in finalidade:
        limite_prazo = 5
    else:
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


# Função para carregar o arquivo mais recente (AGORA VIA BANCO DE DADOS)
@st.cache_data(ttl=60)  # Cache de 1 minuto para não reler banco toda hora
def load_latest_data():
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

            return df, col_malha, col_regiao, col_situacao, col_urgencia, col_data, data_extracao
        else:
            return None, None, None, None, None, None, None
    except Exception as e:
        st.error(f"Erro ao processar dados: {e}")
        return None, None, None, None, None, None, None

# --- CARREGAMENTO DOS DADOS ---
df, col_malha, col_regiao, col_situacao, col_urgencia, col_data, data_extracao = load_latest_data()

if df is not None:
    # 1. KPIs GERAIS
    total_solicitacoes = len(df)
    qtd_atrasadas = len(df[df['Status_Prazo'] == 'Atrasada'])
    qtd_urgencia = len(df[df['Status_Prazo'] == 'Urgência'])
    qtd_alerta = len(df[df['Status_Prazo'] == 'Alerta de Prazo'])
    qtd_regioes = df[col_regiao].nunique()
    
    st.title("Dashboard de Análise de Demanda")
    
    # Exibe data de atualização real dos dados
    if data_extracao:
        st.caption(f"Última atualização (Extração): {data_extracao.strftime('%d/%m/%Y %H:%M:%S')}")
    else:
        st.caption(f"Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Solicitações", total_solicitacoes)
    c2.metric("⚠️ Atrasadas", qtd_atrasadas, delta=f"{qtd_atrasadas}", delta_color="inverse")
    c3.metric("🚨 Urgência", qtd_urgencia, delta=f"{qtd_urgencia}", delta_color="inverse")
    c4.metric("🔔 Alerta (Limite)", qtd_alerta, delta=f"{qtd_alerta}", delta_color="off")
    c5.metric("Regiões Ativas", qtd_regioes)

    st.markdown("---")

    # 2. FILTROS
    with st.expander("🔍 Filtros Avançados", expanded=True):
        c_filtro1, c_filtro2 = st.columns(2)
        filtro_malha = c_filtro1.multiselect("Filtrar por Malha", options=sorted(df[col_malha].unique()), default=df[col_malha].unique())
        
        # Filtra DF pela Malha para atualizar opções de região
        df_filtered_temp = df[df[col_malha].isin(filtro_malha)]
        
        filtro_regiao = c_filtro2.multiselect("Filtrar por Região", options=sorted(df_filtered_temp[col_regiao].unique()), default=df_filtered_temp[col_regiao].unique())

    # Aplica filtros finais
    df_filtered = df[df[col_malha].isin(filtro_malha)]
    df_filtered = df_filtered[df_filtered[col_regiao].isin(filtro_regiao)]
    
    # Recalcula KPIs filtrados
    total_filtrado = len(df_filtered)
    qtd_atrasadas = len(df_filtered[df_filtered['Status_Prazo'].isin(['Atrasada'])])
    qtd_urgencia = len(df_filtered[df_filtered['Status_Prazo'].isin(['Urgência'])])
    qtd_alerta = len(df_filtered[df_filtered['Status_Prazo'] == 'Alerta de Prazo'])
    qtd_no_prazo = len(df_filtered[df_filtered['Status_Prazo'] == 'No Prazo'])

    st.markdown("---")

    # 3. ABAS DE VISUALIZAÇÃO
    tab_malha, tab_regiao, tab_detalhes = st.tabs(["🏙️ Visão por Malha", "🗺️ Visão por Região", "📋 Dados Detalhados"])

    # --- ABA 1: MALHAS ---
    with tab_malha:
        st.subheader("Análise Consolidada por Malha")
        
        # Agrupamento por Malha
        df_malha_agg = df_filtered.groupby(col_malha).agg(
            Total=('Status_Prazo', 'count'),
            Atrasadas=('Status_Prazo', lambda x: x.isin(['Atrasada']).sum()),
            Urgencia=('Status_Prazo', lambda x: x.isin(['Urgência']).sum()),
            Alertas=('Status_Prazo', lambda x: (x == 'Alerta de Prazo').sum()),
            No_Prazo=('Status_Prazo', lambda x: (x == 'No Prazo').sum())
        ).reset_index()
        
        df_malha_agg['% Atraso'] = (df_malha_agg['Atrasadas'] / df_malha_agg['Total'] * 100).round(1)
        df_malha_agg = df_malha_agg.sort_values('Total', ascending=False)
        
        # Top 10 Malhas (Volume) - Padronização
        top_malhas = df_malha_agg.head(10)

        col_m1, col_m2 = st.columns(2)
        
        with col_m1:
            st.markdown("##### Top 10 Malhas (Volume)")
            # Gráfico Altair estático e ordenado
            chart_m_vol = alt.Chart(top_malhas).mark_bar().encode(
                x=alt.X(col_malha, sort='-y', axis=alt.Axis(labelLimit=200, title=None)),
                y=alt.Y('Total', title='Volume'),
                tooltip=[col_malha, 'Total', '% Atraso']
            )
            st.altair_chart(chart_m_vol, use_container_width=True)
            
        with col_m2:
            st.markdown("##### Top Malhas com Atraso")
            # Ordena por atraso para este gráfico
            df_malha_atraso = df_malha_agg.sort_values('Atrasadas', ascending=False).head(10)
            # Gráfico Altair estático e ordenado
            chart_m_atr = alt.Chart(df_malha_atraso).mark_bar(color='#ff4b4b').encode(
                x=alt.X(col_malha, sort='-y', axis=alt.Axis(labelLimit=200, title=None)),
                y=alt.Y('Atrasadas', title='Qtd Atrasos'),
                tooltip=[col_malha, 'Atrasadas', 'Total']
            )
            st.altair_chart(chart_m_atr, use_container_width=True)

        st.markdown("##### Detalhamento por Malha")
        st.dataframe(
            df_malha_agg,
            use_container_width=True,
            column_config={
                col_malha: "Malha",
                "Total": st.column_config.NumberColumn("Total", format="%d"),
                "Atrasadas": st.column_config.ProgressColumn("Atrasadas", format="%d", min_value=0, max_value=int(df_malha_agg['Total'].max()), help="Total de Atrasos"),
                "Urgencia": st.column_config.NumberColumn("Urgência 🚨", format="%d"),
                "Alertas": st.column_config.NumberColumn("Alertas 🔔", format="%d"),
                "% Atraso": st.column_config.NumberColumn("% Crítico", format="%.1f%%")
            },
            hide_index=True
        )

    # --- ABA 2: REGIÕES ---
        with tab_regiao:
            st.subheader("Análise Consolidada por Região")
            
            # Agrupamento por Região
            df_regiao_agg = df_filtered.groupby(col_regiao).agg(
                Total=('Status_Prazo', 'count'),
                Atrasadas=('Status_Prazo', lambda x: x.isin(['Atrasada']).sum()),
                Alertas=('Status_Prazo', lambda x: (x == 'Alerta de Prazo').sum()),
                Urgencia=('Status_Prazo', lambda x: (x == 'Urgência').sum())
            ).reset_index()
            
            # Cálculo de % Atraso (Adicionado para consistência)
            df_regiao_agg['% Atraso'] = (df_regiao_agg['Atrasadas'] / df_regiao_agg['Total'] * 100).round(1)
            
            # Ordenação do maior para o menor Volume
            df_regiao_agg = df_regiao_agg.sort_values('Total', ascending=False)
            
            # ATUALIZAÇÃO: Reduzido de Top 20 para Top 10 conforme solicitado
            top_regioes = df_regiao_agg.head(10)

            col_r1, col_r2 = st.columns(2)
            
            with col_r1:
                st.markdown("##### Top 10 Regiões (Volume)")
                # Gráfico Altair ordenado explicitamente pelo eixo Y descendente (Estático)
                chart_vol = alt.Chart(top_regioes).mark_bar().encode(
                    x=alt.X(col_regiao, sort='-y', axis=alt.Axis(labelLimit=200, title=None)),
                    y=alt.Y('Total', title='Volume'),
                    tooltip=[col_regiao, 'Total', '% Atraso']
                )
                st.altair_chart(chart_vol, use_container_width=True)
                
            with col_r2:
                st.markdown("##### Top 10 Regiões (Atrasos)")
                # Ordena também por Atrasadas para o gráfico de atraso fazer sentido visualmente
                df_regiao_atraso = df_regiao_agg.sort_values('Atrasadas', ascending=False).head(10)
                # Gráfico Altair ordenado explicitamente pelo eixo Y descendente (Estático)
                chart_atr = alt.Chart(df_regiao_atraso).mark_bar(color='#ff4b4b').encode(
                    x=alt.X(col_regiao, sort='-y', axis=alt.Axis(labelLimit=200, title=None)),
                    y=alt.Y('Atrasadas', title='Qtd Atrasos'),
                    tooltip=[col_regiao, 'Atrasadas', 'Total']
                )
                st.altair_chart(chart_atr, use_container_width=True)

            st.markdown("##### Detalhamento por Região")
            st.dataframe(
                df_regiao_agg,
                use_container_width=True,
                column_config={
                    col_regiao: "Região",
                    "Total": st.column_config.ProgressColumn("Volume", format="%d", min_value=0, max_value=int(df_regiao_agg['Total'].max())),
                    "Atrasadas": st.column_config.NumberColumn("Atrasadas ⚠️", format="%d"),
                    "Urgencia": st.column_config.NumberColumn("Urgência 🚨", format="%d"),
                    "Alertas": st.column_config.NumberColumn("Alertas 🔔", format="%d"),
                    "% Atraso": st.column_config.NumberColumn("% Crítico", format="%.1f%%")
                },
                hide_index=True
            )

    # --- ABA 3: DETALHES ---
    with tab_detalhes:
        st.subheader("Base de Dados Completa")
        
        # Opção de filtro rápido por status
        filtro_status = st.multiselect(
            "Filtrar por Status de Prazo:",
            options=['No Prazo', 'Alerta de Prazo', 'Atrasada', 'Urgência', 'Concluída/Outros'],
            default=['Atrasada', 'Urgência', 'Alerta de Prazo']
        )
        
        if filtro_status:
            df_detalhe_view = df_filtered[df_filtered['Status_Prazo'].isin(filtro_status)]
        else:
            df_detalhe_view = df_filtered

        st.dataframe(
            df_detalhe_view,
            use_container_width=True,
            hide_index=True,
            height=500
        )


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
