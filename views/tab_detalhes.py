import streamlit as st
import pandas as pd
import os
import subprocess
import json
import db_manager

def render_tab_detalhes(df_filtered, col_situacao):
    """Renderiza a aba de dados detalhados com filtros, sincronização DECP e tabelas customizadas."""
    col_titulo, col_btn = st.columns([3, 1.2])
    with col_titulo:
        st.subheader("📋 Base de Dados Detalhada")
    with col_btn:
        btn_sync = st.button("🔄 Sincronizar DECP", key="btn_sync_decp", use_container_width=True, help="Consulta no Outlook a caixa SHM-gestaodecp@cemig.com.br para solicitações com CHI ≥ 1500")

    # Disparo da Sincronização Manual sob Demanda
    if btn_sync:
        col_solic_busca = next((c for c in df_filtered.columns if 'solicita' in c.lower() and 'status' not in c.lower()), None)
        if col_solic_busca and 'CHI' in df_filtered.columns:
            mask_decp = pd.to_numeric(df_filtered['CHI'], errors='coerce').fillna(0) >= 1500
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
                
    # Mapeamento do status de e-mail DECP antes de ocultar colunas
    col_solic = next((c for c in df_detalhe_view.columns if 'solicita' in c.lower() and 'status' not in c.lower()), None)
    email_decp_map = {}
    if col_solic and 'Tem_Email_DECP' in df_detalhe_view.columns:
        email_decp_map = {str(k): bool(v) for k, v in zip(df_detalhe_view[col_solic].astype(str), df_detalhe_view['Tem_Email_DECP'])}

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

    # 4. Ordenar por padrão pela data início em ordem crescente
    col_inicio = next((c for c in df_detalhe_view.columns if 'início' in c.lower() or 'inicio' in c.lower()), None)
    if col_inicio:
        df_detalhe_view = df_detalhe_view.sort_values(by=col_inicio, ascending=True)

    # Função de estilização para destacar a linha inteira quando CHI >= 1500
    def aplicar_destaque_chi_decp(row):
        chi_val = pd.to_numeric(row.get('CHI', 0), errors='coerce')
        if pd.notna(chi_val) and chi_val >= 1500:
            solic_val = str(row.get(col_solic, ''))
            tem_email = email_decp_map.get(solic_val, False)
            if not tem_email:
                # Fundo avermelhado/alerta para CHI >= 1500 sem e-mail DECP
                return ['background-color: rgba(239, 68, 68, 0.22); font-weight: 600;'] * len(row)
            else:
                # Fundo verde suave para CHI >= 1500 com e-mail confirmado
                return ['background-color: rgba(16, 185, 129, 0.18); font-weight: 500;'] * len(row)
        return [''] * len(row)

    st.markdown('<div class="animate-target">', unsafe_allow_html=True)
    st.dataframe(
        df_detalhe_view.style.apply(aplicar_destaque_chi_decp, axis=1),
        use_container_width=True,
        hide_index=True,
        height=500,
        column_config=col_config
    )
    st.markdown('</div>', unsafe_allow_html=True)

