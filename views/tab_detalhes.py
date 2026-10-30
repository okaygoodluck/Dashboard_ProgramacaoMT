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
        btn_sync = st.button("🔄 Sincronizar E-mails", key="btn_sync_emails", use_container_width=True, help="Consulta no Outlook as caixas Gestão DECP (toda a base) e Urgência (Fora do Prazo)")
        st.markdown("</div>", unsafe_allow_html=True)

    if 'msg_sync_sucesso' in st.session_state:
        st.success(f"✅ {st.session_state.pop('msg_sync_sucesso')}")

    # Disparo da Sincronização Manual sob Demanda (DECP 100% via Inbox Harvesting + Urgência)
    if btn_sync:
        col_solic_busca = next((c for c in df_filtered.columns if 'solicita' in c.lower() and 'status' not in c.lower()), None)
        col_urg_busca = next((c for c in df_filtered.columns if 'urg' in c.lower()), None)

        def is_urg_busca_fn(val):
            if pd.isna(val): return False
            s = str(val).strip().upper()
            if s in ['SEM', 'NÃO', 'NAO', 'N', 'FALSE', '0', '']: return False
            return s in ['SIM', 'S', 'TRUE', '1'] or 'SIM' in s or s.startswith('S')

        solics_urg = []
        if col_solic_busca and col_urg_busca:
            mask_urg = df_filtered[col_urg_busca].apply(is_urg_busca_fn)
            solics_urg = df_filtered[mask_urg][col_solic_busca].dropna().unique().tolist()

        path_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "sync_emails.ps1")
        mensagens_sucesso = []
        with st.spinner("Consultando caixas de e-mail no Outlook..."):
            # 1. Sincronização DECP (100% da base via ALL)
            cmd_decp = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", path_script, "ALL", "SHM-gestaodecp@cemig.com.br"]
            try:
                res_decp = subprocess.run(cmd_decp, capture_output=True, text=True, encoding='utf-8', timeout=60)
                if res_decp.returncode == 0 and res_decp.stdout.strip():
                    map_res_decp = json.loads(res_decp.stdout)
                    if 'map_email_decp' not in st.session_state:
                        st.session_state.map_email_decp = {}
                    st.session_state.map_email_decp.update(map_res_decp)
                    try:
                        db_manager.atualizar_email_decp_bd(map_res_decp)
                    except Exception as e_db:
                        print(f"[DB] Aviso ao persistir sync DECP: {e_db}")
                    conf_decp = sum(1 for v in map_res_decp.values() if v)
                    mensagens_sucesso.append(f"DECP: {conf_decp} e-mails na caixa")
            except Exception as e:
                print(f"[Outlook DECP] Erro: {e}")

            # 2. Sincronização Urgência (Fora do Prazo)
            if solics_urg:
                ids_str_urg = ",".join([str(s) for s in solics_urg])
                cmd_urg = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", path_script, ids_str_urg, "SHM-man-urgencia@cemig.com.br"]
                try:
                    res_urg = subprocess.run(cmd_urg, capture_output=True, text=True, encoding='utf-8', timeout=60)
                    if res_urg.returncode == 0 and res_urg.stdout.strip():
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
            st.session_state['msg_sync_sucesso'] = f"Sincronização concluída! ({' | '.join(mensagens_sucesso)})"
            st.rerun()
        else:
            st.warning("Falha ao comunicar com o Outlook. Verifique se o aplicativo está aberto e com acesso às caixas compartilhadas.")

    df_detalhe_view = df_filtered.copy()

    col_f1, col_f2, col_f3 = st.columns([1.5, 2.5, 3.0])
    
    with col_f1:
        opcoes_sit = ['Aprovada', 'Em Elaboração']
        filtro_sit = st.multiselect(
            "Situação:",
            options=opcoes_sit,
            default=opcoes_sit,
            key="filtro_detalhes_sit"
        )
        
    with col_f2:
        opcoes_prazo = ['No Prazo', 'Alerta de Prazo', 'Atrasada', 'Urgência']
        filtro_prazo = st.multiselect(
            "Status do Prazo:",
            options=opcoes_prazo,
            default=opcoes_prazo,
            key="filtro_detalhes_prazo"
        )
        
    with col_f3:
        termo_busca = st.text_input("🔍 Buscar na tabela (digite qualquer informação):", "", key="busca_detalhes_txt")

    # 1. Filtro por Situação (Aprovada vs Em Elaboração)
    if filtro_sit is not None:
        mask_sit = pd.Series(False, index=df_detalhe_view.index)
        if 'Aprovada' in filtro_sit:
            mask_sit = mask_sit | df_detalhe_view.get('Is_Aprovada', pd.Series(False, index=df_detalhe_view.index))
        if 'Em Elaboração' in filtro_sit:
            mask_sit = mask_sit | df_detalhe_view.get('Is_Elaboracao', pd.Series(False, index=df_detalhe_view.index))
        df_detalhe_view = df_detalhe_view[mask_sit]

    # 2. Filtro por Status do Prazo
    if filtro_prazo is not None:
        mask_prazo = df_detalhe_view['Status_Prazo'].isin(filtro_prazo)
        df_detalhe_view = df_detalhe_view[mask_prazo]

    # 3. Busca Global (segura contra caracteres especiais regex)
    if termo_busca:
        mask_busca = df_detalhe_view.astype(str).apply(
            lambda x: x.str.contains(termo_busca, case=False, na=False, regex=False)
        ).any(axis=1)
        df_detalhe_view = df_detalhe_view[mask_busca]

    st.markdown('<div class="animate-target">', unsafe_allow_html=True)
    renderizar_tabela_detalhada_estilizada(df_detalhe_view, col_situacao=col_situacao, height=500)
    st.markdown('</div>', unsafe_allow_html=True)


def encurtar_nome_responsavel(name):
    """Encurta o nome do responsável com diferenciação de Gabriel Leandro e Gabriel Leonardo."""
    if not isinstance(name, str) or not name: return name
    parts = name.strip().split()
    if len(parts) >= 2:
        first = parts[0].upper()
        second = parts[1].upper()
        if first == 'GABRIEL':
            if 'LEANDRO' in second:
                return "Gabriel Leandro"
            elif 'LEONARDO' in second:
                return "Gabriel Leonardo"
        return f"{parts[0]} {parts[1][0]}."
    return name


def calcular_largura_coluna(col_name, series):
    """Calcula a largura em pixels ajustada estritamente ao tamanho real do conteúdo e do cabeçalho."""
    c_str = str(col_name).strip()
    if any(p in c_str.lower() for p in ['data', 'início', 'inicio', 'término', 'termino']):
        return 145
    len_header = len(c_str)
    len_content = 0
    if series is not None and not series.empty:
        s_clean = series.dropna().astype(str)
        if not s_clean.empty:
            len_content = int(s_clean.str.len().quantile(0.98))
    chars = max(len_header, len_content)
    if c_str in ['CHI', 'Peso']:
        return max(65, chars * 9 + 20)
    elif c_str in ['Clientes']:
        return max(75, chars * 9 + 20)
    elif c_str in ['OBRA GD', 'Urgência']:
        return 80
    elif c_str in ['Dias uteis']:
        return 95
    elif c_str in ['Matrícula R.', 'Matrícula A.']:
        return 110
    elif c_str in ['Malha']:
        return 85
    elif c_str in ['Região']:
        return max(90, chars * 8 + 25)
    elif c_str in ['E-mail', 'Conjunto']:
        return 120
    elif c_str in ['Solicitação']:
        return 110
    elif c_str in ['Situação']:
        return 125
    elif c_str in ['Responsável', 'Assumiu']:
        return max(130, chars * 8 + 25)
    elif c_str in ['Alimentador', 'Manobra']:
        return max(115, chars * 8 + 25)
    elif c_str in ['Finalidade']:
        return max(220, min(380, chars * 7 + 30))
    return max(70, min(350, int(chars * 8.5 + 25)))


def preparar_dataframe_detalhes(df_input, col_situacao=None):
    """
    Prepara e formata o DataFrame com exatamente as mesmas colunas, ordenações,
    tipos de dados e funções de destaque condicional de cores da visualização detalhada.
    """
    df_view = df_input.copy()

    # Normalização preventiva de colunas (caso ainda existam sufixos _x/_y)
    for base_c in ['CHI', 'Peso', 'Clientes', 'OBRA GD']:
        if base_c not in df_view.columns:
            for sfx in ['_y', '_x']:
                col_cand = f"{base_c}{sfx}"
                if col_cand in df_view.columns:
                    df_view[base_c] = df_view[col_cand]
                    break

    # Aplica encurtamento nas colunas de responsáveis
    if 'Responsavel' in df_view.columns:
        df_view['Responsavel'] = df_view['Responsavel'].apply(encurtar_nome_responsavel)
    if 'Responsavel_Regiao' in df_view.columns:
        df_view['Responsavel_Regiao'] = df_view['Responsavel_Regiao'].apply(encurtar_nome_responsavel)

    if not col_situacao:
        col_situacao = next((c for c in df_view.columns if 'situa' in c.lower()), 'Situação')

    # Ordem de colunas será definida globalmente após todas as inserções e renomeações

    col_solic = next((c for c in df_view.columns if 'solicita' in c.lower() and 'status' not in c.lower()), None)
    col_urg_view = next((c for c in df_view.columns if 'urg' in c.lower()), None)
    col_chi_view = next((c for c in df_view.columns if c.strip().upper() == 'CHI' or c.startswith('CHI')), 'CHI')
    col_alim_view = next((c for c in df_view.columns if 'alim' in c.lower()), None)
    col_reg_view = next((c for c in df_view.columns if 'regi' in c.lower()), None)

    # Carrega mapeamento de conjuntos restritos via db_manager
    map_alim_to_sigla, set_conj_restritos, _ = db_manager.carregar_conjuntos_restritos()

    email_decp_map = {}
    email_urg_map = {}
    if col_solic:
        if 'Tem_Email_DECP' in df_view.columns:
            for k, v in zip(df_view[col_solic].astype(str), df_view['Tem_Email_DECP']):
                k_clean = str(k).strip()
                val = bool(v)
                email_decp_map[k_clean] = val
                email_decp_map[k_clean.lstrip('0')] = val
        if 'Tem_Email' in df_view.columns:
            for k, v in zip(df_view[col_solic].astype(str), df_view['Tem_Email']):
                k_clean = str(k).strip()
                val = bool(v)
                email_urg_map[k_clean] = val
                email_urg_map[k_clean.lstrip('0')] = val

    if hasattr(st, 'session_state'):
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

    # Identificação de Conjuntos Restritos (avaliado previamente para subsidiar autorização)
    def get_status_conjunto(row):
        if 'Conjunto' in row and str(row['Conjunto']).strip().upper() == 'RESTRITO':
            return 'RESTRITO'
        if not col_alim_view:
            return "—"
        alim_val = row.get(col_alim_view, '')
        reg_val = row.get(col_reg_view, '') if col_reg_view else None
        if db_manager.is_alimentador_restrito(alim_val, reg_val):
            return "RESTRITO"
        return "—"
    df_view['Conjunto'] = df_view.apply(get_status_conjunto, axis=1)

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
        is_restrito = str(row.get('Conjunto', '—')).strip() == 'RESTRITO'
        is_exige_decp = is_chi or (is_restrito and pd.notna(chi_val) and chi_val >= 500)

        solic_raw = str(row.get(col_solic, '')).strip()
        solic_trim = solic_raw.lstrip('0')
        tem_decp = bool(email_decp_map.get(solic_raw, False) or email_decp_map.get(solic_trim, False))
        tem_urg = bool(email_urg_map.get(solic_raw, False) or email_urg_map.get(solic_trim, False))

        if tem_decp and tem_urg:
            return "DECP + Urgência"
        elif tem_decp:
            return "DECP"
        elif tem_urg:
            return "Urgência"
        elif is_exige_decp or is_urg:
            return "Pendente"
        else:
            return "—"

    df_view['E-mail'] = df_view.apply(get_email_autorizacao, axis=1)

    # Remover colunas ocultadas (Limpeza Visual + Flags Internas)
    cols_to_hide = [
        'Sol. Vinc.', 'Ações', 'Tem_Email', 'Tem_Email_DECP', 'Data_Extracao', 
        'Status_Prazo', 'Is_Elaboracao', 'Is_Aprovada', 'Resp. Manobra'
    ]

    # Renomeação específica para exibição na visualização detalhada (Pedidos Gilberto)
    mapa_renomear = {
        'Ref_Malha': 'Malha',
        'Ref_Regiao': 'Região',
        'Dias_Uteis_Restantes': 'Dias uteis',
        'Responsavel_Regiao': 'Responsável',
        'Matricula_Regiao': 'Matrícula R.',
        'Responsavel': 'Assumiu',
        'Matricula': 'Matrícula A.',
        'Data de início': 'Data de Início',
        'Data de inicio': 'Data de Início',
        'Data de Término': 'Data de Fim',
        'Data de Termino': 'Data de Fim',
        'Data de término': 'Data de Fim',
        'Data de termino': 'Data de Fim',
    }
    df_view = df_view.rename(columns=mapa_renomear)

    # Ordenação mestre de colunas solicitada pela equipe
    ordem_prioritaria = [
        'Solicitação', 'Situação', 'OBRA GD', 'Peso', 'Clientes', 'CHI',
        'Dias uteis', 'Data de Início', 'Data de Fim', 'E-mail',
        'Conjunto', 'Urgência', 'Finalidade'
    ]
    cols_ordenadas = [c for c in ordem_prioritaria if c in df_view.columns]
    cols_restantes = [c for c in df_view.columns if c not in cols_ordenadas and c not in cols_to_hide]
    df_view = df_view[cols_ordenadas + cols_restantes]
    
    col_config = {}
    col_config['E-mail'] = st.column_config.TextColumn(
        "E-mail",
        help="Identificação do e-mail recebido (DECP, Urgência, DECP + Urgência) ou Pendente",
        width=calcular_largura_coluna('E-mail', df_view['E-mail'])
    )
    col_config['Conjunto'] = st.column_config.TextColumn(
        "Conjunto",
        help="Indica RESTRITO caso o alimentador pertença a um conjunto com restrição de DEC para CHI ≥ 500",
        width=calcular_largura_coluna('Conjunto', df_view['Conjunto'])
    )
    for c in df_view.columns:
        if any(palavra in c.lower() for palavra in ['data', 'início', 'inicio', 'término', 'termino']):
            try:
                df_view[c] = pd.to_datetime(df_view[c], dayfirst=True)
                col_config[c] = st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm", width=calcular_largura_coluna(c, df_view[c]))
            except Exception:
                pass

    # Sanitização de matrículas para texto limpo (evita .0 ou conversão de nulos para 0)
    for col_mat in ['Matrícula R.', 'Matrícula A.']:
        if col_mat in df_view.columns:
            df_view[col_mat] = df_view[col_mat].fillna('—').astype(str).str.replace(r'\.0$', '', regex=True)
            col_config[col_mat] = st.column_config.TextColumn(col_mat, width=calcular_largura_coluna(col_mat, df_view[col_mat]))

    # Garante que colunas de valores numéricos sejam estritamente números inteiros (sem frações/decimais)
    for col_int in ['CHI', 'Clientes', 'Dias uteis']:
        if col_int in df_view.columns:
            df_view[col_int] = pd.to_numeric(df_view[col_int], errors='coerce').fillna(0).round().astype(int)
            col_config[col_int] = st.column_config.NumberColumn(col_int, format="%d", width=calcular_largura_coluna(col_int, df_view[col_int]))

    # Tratamento de Peso para evitar frações como '1.0', mantendo textos como 'PLE'
    if 'Peso' in df_view.columns:
        def limpar_peso_inteiro(v):
            if pd.isna(v) or str(v).strip() == '' or str(v).strip().lower() == 'nan':
                return '0'
            try:
                val_float = float(v)
                return str(round(val_float))
            except (ValueError, TypeError):
                return str(v).strip()
        df_view['Peso'] = df_view['Peso'].apply(limpar_peso_inteiro)
        col_config['Peso'] = st.column_config.TextColumn('Peso', width=calcular_largura_coluna('Peso', df_view['Peso']))

    # Converte qualquer outra coluna com tipo float remanescente para número inteiro
    for c in df_view.select_dtypes(include=['float', 'float64']).columns:
        df_view[c] = df_view[c].fillna(0).round().astype(int)
        col_config[c] = st.column_config.NumberColumn(format="%d", width=calcular_largura_coluna(c, df_view[c]))

    # Configuração de largura calculada em pixels para as demais colunas textuais
    for c in df_view.columns:
        if c not in col_config:
            col_config[c] = st.column_config.TextColumn(c, width=calcular_largura_coluna(c, df_view[c]))

    # Ordenar por padrão pela data início em ordem crescente
    col_inicio = next((c for c in df_view.columns if 'início' in c.lower() or 'inicio' in c.lower()), None)
    if col_inicio and col_inicio in df_view.columns:
        df_view = df_view.sort_values(by=col_inicio, ascending=True)

    # Dicionário de formatação de exibição do Styler para garantir números sem decimais
    format_styler = {}
    for col_int in ['CHI', 'Clientes', 'Dias uteis']:
        if col_int in df_view.columns:
            format_styler[col_int] = '{:.0f}'

    # Função de estilização para destacar a linha inteira quando CHI >= 1500, Urgência == 'SIM' ou Conjunto == 'RESTRITO'
    def aplicar_destaque_autorizacao(row):
        status_conj = str(row.get('Conjunto', '—')).strip()
        status_aut = str(row.get('E-mail', '—')).strip()
        tem_email = status_aut in ['DECP', 'Urgência', 'DECP + Urgência']

        estilo_vermelho = 'background-color: rgba(220, 38, 38, 0.45); font-weight: 700; color: #ffffff;'
        estilo_verde = 'background-color: rgba(16, 185, 129, 0.40); font-weight: 700; color: #ffffff;'
        estilo_neutro = ''

        cols = row.index if hasattr(row, 'index') else list(row.keys())

        if status_conj == 'RESTRITO':
            if tem_email:
                # Linha inteira verde quando possui e-mail, mantendo apenas a célula 'Conjunto' em vermelho
                return [
                    estilo_vermelho if col in ['Conjunto', 'Restrito'] else estilo_verde
                    for col in cols
                ]
            else:
                # Fundo avermelhado para conjunto restrito sem confirmação
                return [estilo_vermelho] * len(cols)

        if tem_email:
            # Fundo verde para solicitação com e-mail confirmado (ao menos um recebido) com texto branco contrastante
            return [estilo_verde] * len(cols)
        elif status_aut == 'Pendente':
            # Fundo avermelhado/alerta para solicitação aguardando e-mail com texto branco brilhante legível
            return [estilo_vermelho] * len(cols)
        return [estilo_neutro] * len(cols)

    return df_view, col_config, format_styler, aplicar_destaque_autorizacao


def renderizar_tabela_detalhada_estilizada(df_input, col_situacao=None, height=500):
    """
    Renderiza a tabela utilizando exatamente as colunas e formatações de Dados Detalhados,
    com a estilização condicional de cores por linha (Pendente/Restrito em vermelho, Confirmado em verde).
    """
    df_view, col_config, format_styler, func_destaque = preparar_dataframe_detalhes(df_input, col_situacao)
    
    st.dataframe(
        df_view.style.format(format_styler).apply(func_destaque, axis=1),
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config=col_config
    )


