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

    col_titulo, col_btn = st.columns([4.8, 1.4])
    with col_titulo:
        st.subheader("📋 Base de Dados Detalhada")
    with col_btn:
        st.markdown("<div style='padding-top: 4px;'>", unsafe_allow_html=True)
        btn_sync = st.button("🔄 Sincronizar E-mails", key="btn_sync_emails", use_container_width=True, help="Consulta no Outlook as caixas DECP (CHI ≥ 1500) e Urgência (Fora do Prazo)")
        st.markdown("</div>", unsafe_allow_html=True)

    # Disparo da Sincronização Manual sob Demanda (DECP + Urgência)
    if btn_sync:
        col_solic_busca = next((c for c in df_filtered.columns if 'solicita' in c.lower() and 'status' not in c.lower()), None)
        col_chi_busca = next((c for c in df_filtered.columns if c.strip().upper() == 'CHI' or c.startswith('CHI')), None)
        col_urg_busca = next((c for c in df_filtered.columns if 'urg' in c.lower()), None)

        def is_urg_busca_fn(val):
            if pd.isna(val): return False
            s = str(val).strip().upper()
            if s in ['SEM', 'NÃO', 'NAO', 'N', 'FALSE', '0', '']: return False
            return s in ['SIM', 'S', 'TRUE', '1'] or 'SIM' in s or s.startswith('S')

        solics_decp = []
        if col_solic_busca and col_chi_busca:
            mask_decp = pd.to_numeric(df_filtered[col_chi_busca], errors='coerce').fillna(0) >= 1500
            solics_decp = df_filtered[mask_decp][col_solic_busca].dropna().unique().tolist()

        solics_urg = []
        if col_solic_busca and col_urg_busca:
            mask_urg = df_filtered[col_urg_busca].apply(is_urg_busca_fn)
            solics_urg = df_filtered[mask_urg][col_solic_busca].dropna().unique().tolist()

        if not solics_decp and not solics_urg:
            st.info("Nenhuma solicitação com CHI ≥ 1500 ou Urgência encontrada para sincronizar.")
        else:
            path_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "sync_emails.ps1")
            mensagens_sucesso = []
            with st.spinner("Consultando caixas de e-mail no Outlook..."):
                # 1. Sincronização DECP (CHI >= 1500)
                if solics_decp:
                    ids_str_decp = ",".join([str(s) for s in solics_decp])
                    cmd_decp = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", path_script, ids_str_decp, "SHM-gestaodecp@cemig.com.br"]
                    try:
                        res_decp = subprocess.run(cmd_decp, capture_output=True, text=True, encoding='utf-8', timeout=60)
                        if res_decp.returncode == 0:
                            map_res_decp = json.loads(res_decp.stdout)
                            if 'map_email_decp' not in st.session_state:
                                st.session_state.map_email_decp = {}
                            st.session_state.map_email_decp.update(map_res_decp)
                            try:
                                db_manager.atualizar_email_decp_bd(map_res_decp)
                            except Exception as e_db:
                                print(f"[DB] Aviso ao persistir sync DECP: {e_db}")
                            conf_decp = sum(1 for v in map_res_decp.values() if v)
                            mensagens_sucesso.append(f"DECP: {conf_decp}/{len(map_res_decp)}")
                    except Exception as e:
                        print(f"[Outlook DECP] Erro: {e}")

                # 2. Sincronização Urgência (Fora do Prazo)
                if solics_urg:
                    ids_str_urg = ",".join([str(s) for s in solics_urg])
                    cmd_urg = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", path_script, ids_str_urg, "SHM-man-urgencia@cemig.com.br"]
                    try:
                        res_urg = subprocess.run(cmd_urg, capture_output=True, text=True, encoding='utf-8', timeout=60)
                        if res_urg.returncode == 0:
                            map_res_urg = json.loads(res_urg.stdout)
                            if 'map_email_urgencia' not in st.session_state:
                                st.session_state.map_email_urgencia = {}
                            st.session_state.map_email_urgencia.update(map_res_urg)
                            try:
                                db_manager.atualizar_email_urgencia_bd(map_res_urg)
                            except Exception as e_db:
                                print(f"[DB] Aviso ao persistir sync Urgência: {e_db}")
                            conf_urg = sum(1 for v in map_res_urg.values() if v)
                            mensagens_sucesso.append(f"Urgência: {conf_urg}/{len(map_res_urg)}")
                    except Exception as e:
                        print(f"[Outlook Urgência] Erro: {e}")

                try:
                    db_manager.carregar_dados_recentes.clear()
                except Exception:
                    pass

                if mensagens_sucesso:
                    st.success(f"Sincronização concluída! ({' | '.join(mensagens_sucesso)} e-mails confirmados).")
                    st.rerun()
                else:
                    st.warning("Falha ao comunicar com o Outlook. Verifique se o aplicativo está aberto e com acesso às caixas.")

    # Legenda visual para as solicitações CHI >= 1500 e Urgência
    st.markdown("""
    <div style="display: flex; gap: 20px; align-items: center; margin: 4px 0 10px 0; font-size: 0.8rem; flex-wrap: wrap;">
        <span style="display: flex; align-items: center; gap: 6px;">
            <span style="display: inline-block; width: 14px; height: 14px; background: rgba(239, 68, 68, 0.25); border: 1px solid rgba(239, 68, 68, 0.6); border-radius: 3px;"></span>
            <span><strong>CHI ≥ 1500 ou Urgência (Aguardando E-mail)</strong></span>
        </span>
        <span style="display: flex; align-items: center; gap: 6px;">
            <span style="display: inline-block; width: 14px; height: 14px; background: rgba(16, 185, 129, 0.22); border: 1px solid rgba(16, 185, 129, 0.6); border-radius: 3px;"></span>
            <span><strong>CHI ≥ 1500 ou Urgência (E-mail Confirmado)</strong></span>
        </span>
        <span style="color: #64748b; font-size: 0.75rem;">
            *(Consulte a coluna <strong>E-mail Autorização</strong> para verificar qual e-mail foi recebido)*
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
                
    # Mapeamento dos status de e-mail DECP e Urgência antes de ocultar colunas
    col_solic = next((c for c in df_detalhe_view.columns if 'solicita' in c.lower() and 'status' not in c.lower()), None)
    col_urg_view = next((c for c in df_detalhe_view.columns if 'urg' in c.lower()), None)
    col_chi_view = next((c for c in df_detalhe_view.columns if c.strip().upper() == 'CHI' or c.startswith('CHI')), 'CHI')

    email_decp_map = {}
    email_urg_map = {}
    if col_solic:
        if 'Tem_Email_DECP' in df_detalhe_view.columns:
            for k, v in zip(df_detalhe_view[col_solic].astype(str), df_detalhe_view['Tem_Email_DECP']):
                k_clean = str(k).strip()
                val = bool(v)
                email_decp_map[k_clean] = val
                email_decp_map[k_clean.lstrip('0')] = val
        if 'Tem_Email' in df_detalhe_view.columns:
            for k, v in zip(df_detalhe_view[col_solic].astype(str), df_detalhe_view['Tem_Email']):
                k_clean = str(k).strip()
                val = bool(v)
                email_urg_map[k_clean] = val
                email_urg_map[k_clean.lstrip('0')] = val

    if 'map_email_decp' in st.session_state and isinstance(st.session_state.map_email_decp, dict):
        for k, v in st.session_state.map_email_decp.items():
            k_clean = str(k).strip()
            val = bool(v)
            email_decp_map[k_clean] = val
            email_decp_map[k_clean.lstrip('0')] = val

    if 'map_email_urgencia' in st.session_state and isinstance(st.session_state.map_email_urgencia, dict):
        for k, v in st.session_state.map_email_urgencia.items():
            k_clean = str(k).strip()
            val = bool(v)
            email_urg_map[k_clean] = val
            email_urg_map[k_clean.lstrip('0')] = val

    def is_urgente_val(val):
        if pd.isna(val): return False
        s = str(val).strip().upper()
        if s in ['SEM', 'NÃO', 'NAO', 'N', 'FALSE', '0', '']: return False
        return s in ['SIM', 'S', 'TRUE', '1'] or 'SIM' in s or s.startswith('S')

    def get_email_autorizacao(row):
        chi_val = pd.to_numeric(row.get(col_chi_view, 0), errors='coerce')
        is_chi = pd.notna(chi_val) and chi_val >= 1500
        urg_val = row.get(col_urg_view, None) if col_urg_view else None
        is_urg = is_urgente_val(urg_val)

        if not is_chi and not is_urg:
            return "—"

        solic_raw = str(row.get(col_solic, '')).strip()
        solic_trim = solic_raw.lstrip('0')
        tem_decp = email_decp_map.get(solic_raw, False) or email_decp_map.get(solic_trim, False)
        tem_urg = email_urg_map.get(solic_raw, False) or email_urg_map.get(solic_trim, False)

        if tem_decp and tem_urg:
            return "DECP + Urgência"
        elif tem_decp:
            return "DECP"
        elif tem_urg:
            return "Urgência"
        else:
            return "Pendente"

    df_detalhe_view['E-mail Autorização'] = df_detalhe_view.apply(get_email_autorizacao, axis=1)

    # Inserção de E-mail Autorização nas colunas visíveis logo após CHI ou Situação
    if 'E-mail Autorização' in cols:
        cols.remove('E-mail Autorização')
    if 'CHI' in cols:
        cols.insert(cols.index('CHI') + 1, 'E-mail Autorização')
    elif col_situacao in cols:
        cols.insert(cols.index(col_situacao) + 1, 'E-mail Autorização')
    elif 'Situação' in cols:
        cols.insert(cols.index('Situação') + 1, 'E-mail Autorização')
    else:
        cols.append('E-mail Autorização')

    # Remover colunas solicitadas pelo usuário (Limpeza Visual + Is_Aprovada)
    cols_to_hide = [
        'Sol. Vinc.', 'Ações', 'Tem_Email', 'Tem_Email_DECP', 'Data_Extracao', 
        'Status_Prazo', 'Is_Elaboracao', 'Is_Aprovada', 'Resp. Manobra'
    ]
    cols = [c for c in cols if c not in cols_to_hide]

    df_detalhe_view = df_detalhe_view[cols]
    
    col_config = {}
    col_config['E-mail Autorização'] = st.column_config.TextColumn(
        "E-mail Autorização",
        help="Identificação do e-mail recebido (DECP, Urgência, DECP + Urgência) ou Pendente",
        width="medium"
    )
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

    # Função de estilização para destacar a linha inteira quando CHI >= 1500 ou Urgência == 'SIM'
    def aplicar_destaque_autorizacao(row):
        status_aut = str(row.get('E-mail Autorização', '—')).strip()
        if status_aut in ['DECP', 'Urgência', 'DECP + Urgência']:
            # Fundo verde para solicitação com e-mail confirmado (ao menos um recebido) com texto branco contrastante
            return ['background-color: rgba(16, 185, 129, 0.40); font-weight: 700; color: #ffffff;'] * len(row)
        elif status_aut == 'Pendente':
            # Fundo avermelhado/alerta para solicitação aguardando e-mail com texto branco brilhante legível
            return ['background-color: rgba(220, 38, 38, 0.45); font-weight: 700; color: #ffffff;'] * len(row)
        return [''] * len(row)

    st.markdown('<div class="animate-target">', unsafe_allow_html=True)
    st.dataframe(
        df_detalhe_view.style.format(format_styler).apply(aplicar_destaque_autorizacao, axis=1),
        use_container_width=True,
        hide_index=True,
        height=500,
        column_config=col_config
    )
    st.markdown('</div>', unsafe_allow_html=True)

