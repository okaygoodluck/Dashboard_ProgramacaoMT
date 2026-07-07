import streamlit as st
import pandas as pd

def render_tab_detalhes(df_filtered, col_situacao):
    """Renderiza a aba de dados detalhados com filtros e tabelas customizadas."""
    st.subheader("📋 Base de Dados Detalhada")
    
    df_detalhe_view = df_filtered.copy()
    
    # Função para encurtar nomes
    def short_name(name):
        if not isinstance(name, str) or not name: return name
        parts = name.split()
        if len(parts) >= 2:
            return f"{parts[0]} {parts[1][0]}."
        return name

    # Aplica encurtamento na coluna Responsavel
    if 'Responsavel' in df_detalhe_view.columns:
        df_detalhe_view['Responsavel'] = df_detalhe_view['Responsavel'].apply(short_name)

    # 1. Campo de busca global
    termo_busca = st.text_input("🔍 Buscar na tabela (digite qualquer informação):", "")

    # 2. Status 'Concluída/Outros' removido e 3. Por padrão ativado todos.
    opcoes_status = ['No Prazo', 'Alerta de Prazo', 'Atrasada', 'Urgência', 'Em Elaboração']
    filtro_status = st.multiselect(
        "Filtrar por Status/Situação:",
        options=opcoes_status,
        default=opcoes_status
    )
    
    if filtro_status:
        mask = pd.Series(False, index=df_detalhe_view.index)
        if 'Em Elaboração' in filtro_status:
            mask = mask | df_detalhe_view['Is_Elaboracao']
        
        status_normais = [s for s in filtro_status if s != 'Em Elaboração']
        if status_normais:
            mask = mask | df_detalhe_view['Status_Prazo'].isin(status_normais)
            
        df_detalhe_view = df_detalhe_view[mask]

    # Aplica a busca global
    if termo_busca:
        mask_busca = df_detalhe_view.astype(str).apply(lambda x: x.str.contains(termo_busca, case=False, na=False)).any(axis=1)
        df_detalhe_view = df_detalhe_view[mask_busca]

    # Reordenação de colunas
    cols = list(df_detalhe_view.columns)
    for col_name in ['CHI', 'Clientes', 'Peso', 'OBRA GD']:
        if col_name in cols:
            cols.remove(col_name)
            idx = -1
            if col_situacao in cols:
                idx = cols.index(col_situacao) + 1
            elif 'Situação' in cols:
                idx = cols.index('Situação') + 1
            
            if idx > 0:
                cols.insert(idx, col_name)
            else:
                cols.append(col_name)
                
    # Remover colunas solicitadas pelo usuário (Limpeza Visual)
    cols_to_hide = [
        'Sol. Vinc.', 'Ações', 'Tem_Email', 'Data_Extracao', 
        'Status_Prazo', 'Is_Elaboracao', 'Resp. Manobra'
    ]
    cols = [c for c in cols if c not in cols_to_hide]

    df_detalhe_view = df_detalhe_view[cols]
    
    col_config = {}
    for c in df_detalhe_view.columns:
        if any(palavra in c.lower() for palavra in ['data', 'início', 'inicio', 'término', 'termino']):
            try:
                df_detalhe_view[c] = pd.to_datetime(df_detalhe_view[c], dayfirst=True)
                col_config[c] = st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")
            except:
                pass

    # 4. Ordenar por padrão pela data início em ordem crescente
    col_inicio = next((c for c in df_detalhe_view.columns if 'início' in c.lower() or 'inicio' in c.lower()), None)
    if col_inicio:
        df_detalhe_view = df_detalhe_view.sort_values(by=col_inicio, ascending=True)

    st.markdown('<div class="animate-target">', unsafe_allow_html=True)
    st.dataframe(
        df_detalhe_view,
        use_container_width=True,
        hide_index=True,
        height=500,
        column_config=col_config
    )
    st.markdown('</div>', unsafe_allow_html=True)
