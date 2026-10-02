import streamlit as st
import pandas as pd
import os
import subprocess
import json
import db_manager

def render_tab_detalhes(df_filtered, col_situacao):
    """Renderiza a aba de dados detalhados com filtros, sincronização DECP e tabelas customizadas."""
    # Normalização preventiva de colunas (caso ainda existam sufixos _x/_y)
    for base_c in ['CHI', 'Peso', 'Clientes', 'OBRA GD']:
        if base_c not in df_filtered.columns:
            for sfx in ['_y', '_x']:
                col_cand = f"{base_c}{sfx}"
                if col_cand in df_filtered.columns:
                    df_filtered[base_c] = df_filtered[col_cand]
                    break

    col_titulo, col_btn = st.columns([3, 1.2])
    with col_titulo:
        st.subheader("📋 Base de Dados Detalhada")
    with col_btn:
        btn_sync = st.button("🔄 Sincronizar DECP", key="btn_sync_decp", use_container_width=True, help="Consulta no Outlook a caixa SHM-gestaodecp@cemig.com.br para solicitações com CHI ≥ 1500")

    # Disparo da Sincronização Manual sob Demanda
    if btn_sync:
        col_solic_busca = next((c for c in df_filtered.columns if 'solicita' in c.lower() and 'status' not in c.lower()), None)
        col_chi_busca = next((c for c in df_filtered.columns if c.strip().upper() == 'CHI' or c.startswith('CHI')), None)
        if col_solic_busca and col_chi_busca:
            mask_decp = pd.to_numeric(df_filtered[col_chi_busca], errors='coerce').fillna(0) >= 1500
            solics_decp = df_filtered[mask_decp][col_solic_busca].dropna().unique().tolist()
            if solics_decp:
                with st.spinner(f"Consultando caixa SHM-gestaodecp@cemig.com.br no Outlook para {len(solics_decp)} solicitações..."):
                    ids_str = ",".join([str(s) for s in solics_decp])
                    path_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "sync_emails.ps1")
                    cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", path_script, ids_str, "SHM-gestaodecp@cemig.com.br"]
                    try:
                        res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=60)
                        if res.returncode == 0:
                            map_res = json.loads(res.stdout)
                            if 'map_email_decp' not in st.session_state:
                                st.session_state.map_email_decp = {}
                            st.session_state.map_email_decp.update(map_res)
                            try:
                                db_manager.atualizar_email_decp_bd(map_res)
                                db_manager.carregar_dados_recentes.clear()
                            except Exception as e_db:
                                print(f"[DB] Aviso ao persistir sync DECP: {e_db}")
                            total_conf = sum(1 for v in map_res.values() if v)
                            st.success(f"Sincronização concluída! {total_conf} de {len(map_res)} e-mails confirmados na caixa DECP.")
                            st.rerun()
                        else:
                            st.error("Falha ao comunicar com o Outlook. Verifique se o aplicativo está aberto e com acesso à caixa compartilhada.")
                    except subprocess.TimeoutExpired:
                        st.error("Tempo limite excedido ao consultar o Outlook (60s).")
                    except Exception as e:
                        st.error(f"Erro na sincronização: {e}")
            else:
                st.info("Nenhuma solicitação com CHI ≥ 1500 encontrada para sincronizar.")
        else:
            st.warning("Colunas de Solicitação ou CHI não disponíveis.")

    # Legenda visual para as solicitações CHI >= 1500
    st.markdown("""
    <div style="display: flex; gap: 20px; align-items: center; margin: 4px 0 10px 0; font-size: 0.8rem;">
        <span style="display: flex; align-items: center; gap: 6px;">
            <span style="display: inline-block; width: 14px; height: 14px; background: rgba(239, 68, 68, 0.25); border: 1px solid rgba(239, 68, 68, 0.6); border-radius: 3px;"></span>
            <span><strong>CHI ≥ 1500 (Aguardando E-mail DECP)</strong></span>
        </span>
        <span style="display: flex; align-items: center; gap: 6px;">
            <span style="display: inline-block; width: 14px; height: 14px; background: rgba(16, 185, 129, 0.22); border: 1px solid rgba(16, 185, 129, 0.6); border-radius: 3px;"></span>
            <span><strong>CHI ≥ 1500 (E-mail DECP Confirmado)</strong></span>
        </span>
    </div>
    """, unsafe_allow_html=True)
    
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

    # 2. Status 'Sem Data' e 'Concluída/Outros' removidos conforme solicitado
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
        matching_cols = [c for c in cols if c == col_name or c.startswith(f"{col_name}_")]
        for c_match in matching_cols:
            cols.remove(c_match)
            idx = -1
            if col_situacao in cols:
                idx = cols.index(col_situacao) + 1
            elif 'Situação' in cols:
                idx = cols.index('Situação') + 1
            
            if idx > 0:
                cols.insert(idx, c_match)
            else:
                cols.append(c_match)
                
    # Mapeamento do status de e-mail DECP antes de ocultar colunas
    col_solic = next((c for c in df_detalhe_view.columns if 'solicita' in c.lower() and 'status' not in c.lower()), None)
    email_decp_map = {}
    if col_solic and 'Tem_Email_DECP' in df_detalhe_view.columns:
        for k, v in zip(df_detalhe_view[col_solic].astype(str), df_detalhe_view['Tem_Email_DECP']):
            k_clean = str(k).strip()
            k_num = k_clean.lstrip('0')
            val = bool(v)
            email_decp_map[k_clean] = val
            email_decp_map[k_num] = val

    # Remover colunas solicitadas pelo usuário (Limpeza Visual)
    cols_to_hide = [
        'Sol. Vinc.', 'Ações', 'Tem_Email', 'Tem_Email_DECP', 'Data_Extracao', 
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
            except Exception:
                pass

    # Garante que colunas de valores numéricos sejam estritamente números inteiros (sem frações/decimais)
    for col_int in ['CHI', 'Clientes']:
        if col_int in df_detalhe_view.columns:
            df_detalhe_view[col_int] = pd.to_numeric(df_detalhe_view[col_int], errors='coerce').fillna(0).round().astype(int)
            col_config[col_int] = st.column_config.NumberColumn(format="%d")

    # Tratamento de Peso para evitar frações como '1.0', mantendo textos como 'PLE'
    if 'Peso' in df_detalhe_view.columns:
        def limpar_peso_inteiro(v):
            if pd.isna(v) or str(v).strip() == '' or str(v).strip().lower() == 'nan':
                return '0'
            try:
                val_float = float(v)
                return str(int(round(val_float)))
            except (ValueError, TypeError):
                return str(v).strip()
        df_detalhe_view['Peso'] = df_detalhe_view['Peso'].apply(limpar_peso_inteiro)

    # Converte qualquer outra coluna com tipo float remanescente para número inteiro
    for c in df_detalhe_view.select_dtypes(include=['float', 'float64']).columns:
        df_detalhe_view[c] = df_detalhe_view[c].fillna(0).round().astype(int)
        col_config[c] = st.column_config.NumberColumn(format="%d")

    # 4. Ordenar por padrão pela data início em ordem crescente
    col_inicio = next((c for c in df_detalhe_view.columns if 'início' in c.lower() or 'inicio' in c.lower()), None)
    if col_inicio:
        df_detalhe_view = df_detalhe_view.sort_values(by=col_inicio, ascending=True)

    # Identifica dinamicamente a coluna de CHI na visão
    col_chi_view = next((c for c in df_detalhe_view.columns if c.strip().upper() == 'CHI' or c.startswith('CHI')), 'CHI')

    # Dicionário de formatação de exibição do Styler para garantir números sem decimais
    format_styler = {}
    for col_int in ['CHI', 'Clientes']:
        if col_int in df_detalhe_view.columns:
            format_styler[col_int] = '{:.0f}'

    # Função de estilização para destacar a linha inteira quando CHI >= 1500
    def aplicar_destaque_chi_decp(row):
        chi_val = pd.to_numeric(row.get(col_chi_view, 0), errors='coerce')
        if pd.notna(chi_val) and chi_val >= 1500:
            solic_raw = str(row.get(col_solic, '')).strip()
            tem_email = email_decp_map.get(solic_raw, False) or email_decp_map.get(solic_raw.lstrip('0'), False)
            if not tem_email:
                # Fundo avermelhado/alerta de alto contraste para CHI >= 1500 sem e-mail DECP
                return ['background-color: rgba(239, 68, 68, 0.38); font-weight: 700; color: inherit;'] * len(row)
            else:
                # Fundo verde para CHI >= 1500 com e-mail confirmado
                return ['background-color: rgba(16, 185, 129, 0.30); font-weight: 600; color: inherit;'] * len(row)
        return [''] * len(row)

    st.markdown('<div class="animate-target">', unsafe_allow_html=True)
    st.dataframe(
        df_detalhe_view.style.format(format_styler).apply(aplicar_destaque_chi_decp, axis=1),
        use_container_width=True,
        hide_index=True,
        height=500,
        column_config=col_config
    )
    st.markdown('</div>', unsafe_allow_html=True)

