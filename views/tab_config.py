import streamlit as st
import pandas as pd
import db_manager
import time

@st.dialog("Alterar Nível de Acesso")
def mudar_nivel_dialog(matricula, nome, nivel_atual):
    st.write(f"Usuário: **{nome}** ({matricula})")
    novo_nivel = st.selectbox("Novo Nível", options=["Usuario", "Gerencial", "ADM"], index=["Usuario", "Gerencial", "ADM"].index(nivel_atual))
    if st.button("Salvar Alteração"):
        if db_manager.alterar_nivel_usuario(matricula, novo_nivel):
            st.success(f"Nível de {nome} alterado para {novo_nivel}!")
            time.sleep(1)
            st.rerun()
        else:
            st.error("Erro ao alterar nível.")

def formatar_nome_exibicao(df_usuarios):
    """Gera nomes resumidos e elegantes, diferenciando homônimos (ex: GABRIEL R*, AMANDA P*)."""
    contagem_primeiro = {}
    for _, r in df_usuarios.iterrows():
        partes = str(r['nome']).strip().split()
        if partes:
            pri = partes[0].upper()
            contagem_primeiro[pri] = contagem_primeiro.get(pri, 0) + 1
            
    nomes = {}
    for _, r in df_usuarios.iterrows():
        mat = str(r['matricula']).strip()
        partes = str(r['nome']).strip().split()
        if not partes:
            nomes[mat] = mat
            continue
        pri = partes[0].upper()
        if contagem_primeiro.get(pri, 0) > 1 and len(partes) > 1:
            segunda_inicial = partes[1][0].upper()
            nomes[mat] = f"{pri} {segunda_inicial}*"
        else:
            nomes[mat] = pri
    return nomes

def render_tab_config():
    """Renderiza a aba de configurações administrativas e escala de regiões."""
    st.header("⚙️ Configurações Administrativas")
    
    # Injeção de CSS para estilizar os cartões e os slots compactos
    st.markdown("""
    <style>
    /* Ajuste de padding dos containers nativos (tiras finas) */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        padding: 2px 4px !important;
        margin-bottom: 3px !important;
        border-radius: 5px !important;
    }
    
    /* Compactação limpa e centralização dos seletores de slot */
    div[data-testid="stSelectbox"] {
        margin-top: 0px !important;
        margin-bottom: 0px !important;
    }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] {
        min-height: 28px !important;
        border-radius: 6px !important;
        padding: 0 !important;
    }
    /* Ocultar a seta de dropdown nos seletores de slot para liberar 100% da largura útil */
    div[data-testid="stSelectbox"] div[data-baseweb="select"] svg {
        display: none !important;
    }
    form div[data-testid="stSelectbox"] div[data-baseweb="select"] svg {
        display: inline-block !important;
    }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        min-height: 28px !important;
        padding-left: 2px !important;
        padding-right: 2px !important;
        padding-top: 0px !important;
        padding-bottom: 0px !important;
        background-color: #1e293b !important;
        border: 1px solid #475569 !important;
        border-radius: 6px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    /* Zerar paddings verticais em todos os containers intermediários do BaseWeb */
    div[data-testid="stSelectbox"] div[data-baseweb="select"] div {
        padding-top: 0px !important;
        padding-bottom: 0px !important;
    }
    /* Forçar texto nítido, centralizado, branco brilhante sem truncamento (nunca virar ponto) */
    div[data-testid="stSelectbox"] div[data-baseweb="select"] * {
        color: #ffffff !important;
        font-weight: 800 !important;
        font-size: 0.85rem !important;
        text-align: center !important;
        justify-content: center !important;
        overflow: visible !important;
        white-space: nowrap !important;
    }
    </style>
    """, unsafe_allow_html=True)

    todas_regioes = db_manager.get_regioes_disponiveis_data()
    df_map_atual = db_manager.get_mapeamento_regioes()
    df_users = db_manager.listar_usuarios()
    
    # Filtra técnicos ativos (remove os marcados como desligados)
    if not df_users.empty:
        df_ativos = df_users[~df_users['nome'].str.contains('desligado', case=False, na=False)].copy()
        df_ativos['primeiro_nome'] = df_ativos['nome'].str.strip().str.split().str[0].str.upper()
        
        # Mapeia quantidade de regiões atribuídas no banco para priorizar quem tem região no topo
        map_qtd_reg = df_map_atual.groupby('matricula')['sigla_regiao'].count().to_dict()
        df_ativos['qtd_reg'] = df_ativos['matricula'].astype(str).str.strip().map(lambda m: map_qtd_reg.get(m, 0))
        df_ativos['tem_reg'] = df_ativos['qtd_reg'] > 0
        
        # Ordenação inteligente: Primeiro técnicos COM região, depois alfabético por primeiro nome
        df_ativos = df_ativos.sort_values(by=['tem_reg', 'primeiro_nome', 'nome'], ascending=[False, True, True]).reset_index(drop=True)
    else:
        df_ativos = pd.DataFrame(columns=['matricula', 'nome', 'nivel'])

    map_display_names = formatar_nome_exibicao(df_ativos)

    # Inicialização do estado de slots
    if 'map_slots' not in st.session_state:
        st.session_state.map_slots = {}
        for _, u in df_ativos.iterrows():
            mat = str(u['matricula']).strip()
            regs_u = df_map_atual[df_map_atual['matricula'] == mat]['sigla_regiao'].tolist()
            slots = [r for r in regs_u][:4]
            while len(slots) < 4:
                slots.append("—")
            st.session_state.map_slots[mat] = slots

    # Assegura que novos usuários ativos adicionados na sessão estejam presentes em map_slots
    for _, u in df_ativos.iterrows():
        mat = str(u['matricula']).strip()
        if mat not in st.session_state.map_slots:
            regs_u = df_map_atual[df_map_atual['matricula'] == mat]['sigla_regiao'].tolist()
            slots = [r for r in regs_u][:4]
            while len(slots) < 4:
                slots.append("—")
            st.session_state.map_slots[mat] = slots

    # Cálculo das regiões ocupadas e livres
    regioes_ocupadas = set()
    for mat_k, slots in st.session_state.map_slots.items():
        for s in slots:
            if s and s != "—":
                regioes_ocupadas.add(s)

    regioes_livres = sorted([r for r in todas_regioes if r not in regioes_ocupadas])

    # Unificação lado a lado: Esquerda (Gestão de Usuários) | Direita (Escala de Regiões)
    col_esq, col_dir = st.columns([1, 1], gap="medium")

    # =========================================================================
    # COLUNA ESQUERDA: GESTÃO DE USUÁRIOS E ACESSOS
    # =========================================================================
    with col_esq:
        st.subheader("👥 Gestão de Usuários")
        
        search_user = st.text_input("🔍 Buscar funcionário...", placeholder="Nome ou Matrícula", label_visibility="collapsed", key="search_user_tab")
        
        tab_lista, tab_novo = st.tabs(["📋 Lista Registrada", "➕ Novo Cadastro"])
        
        with tab_lista:
            if not df_users.empty:
                if search_user:
                    df_filtered = df_users[
                        df_users['nome'].str.contains(search_user, case=False, na=False) |
                        df_users['matricula'].str.contains(search_user, case=False, na=False)
                    ]
                else:
                    df_filtered = df_users

                if not df_filtered.empty:
                    with st.container(height=580):
                        for idx, row in df_filtered.iterrows():
                            with st.container(border=True):
                                col_u1, col_u2, col_u3, col_u4, col_u5 = st.columns([2.5, 1.5, 0.6, 0.6, 0.6], vertical_alignment="center")
                                
                                with col_u1:
                                    st.markdown(f"**{row['nome']}**")
                                    st.caption(f"ID: {row['matricula']}")
                                
                                with col_u2:
                                    nivel_color = "#22d3ee" if row['nivel'] == "ADM" else "#f59e0b" if row['nivel'] == "Gerencial" else "#94a3b8"
                                    st.markdown(f'<div style="background:{nivel_color}15; color:{nivel_color}; border: 1px solid {nivel_color}40; padding: 4px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: 600; text-align: center;">{row["nivel"]}</div>', unsafe_allow_html=True)
                                
                                with col_u3:
                                    if st.session_state.user_nivel == "ADM" and row['matricula'] != st.session_state.user_matricula:
                                        if st.button("✏️", key=f"edit_{row['matricula']}", help="Alterar Nível"):
                                            mudar_nivel_dialog(row['matricula'], row['nome'], row['nivel'])
                                
                                with col_u4:
                                    if st.button("🔑", key=f"reset_{row['matricula']}", help="Resetar Senha para 12345"):
                                        if db_manager.resetar_senha(row['matricula']):
                                            st.toast(f"Senha de {row['nome']} resetada!")
                                            time.sleep(0.5)
                                            st.rerun()
                                
                                with col_u5:
                                    if row['matricula'] != st.session_state.user_matricula:
                                        if st.button("🗑️", key=f"del_{row['matricula']}", help="Remover Usuário"):
                                            if db_manager.deletar_usuario(row['matricula']):
                                                st.toast(f"Usuário {row['nome']} removido!")
                                                time.sleep(0.5)
                                                st.rerun()
                else:
                    st.warning("Nenhum usuário encontrado.")
            else:
                st.info("Nenhum usuário cadastrado.")

        with tab_novo:
            with st.container(border=True):
                with st.form("form_novo_usuario", clear_on_submit=True):
                    st.markdown("#### Detalhes do Novo Acesso")
                    fn_mat = st.text_input("Matrícula (ex: c000000)").strip()
                    fn_nom = st.text_input("Nome Completo").strip()
                    fn_niv = st.selectbox("Nível de Acesso", options=["Usuario", "Gerencial", "ADM"])
                    
                    if st.form_submit_button("✨ Criar Usuário Vanguard"):
                        if fn_mat and fn_nom:
                            if db_manager.criar_usuario(fn_mat, fn_nom, fn_niv):
                                st.success("Sucesso! Senha inicial: 12345")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("Erro ao criar. Verifique se a matrícula já existe.")
                        else:
                            st.warning("Preencha Nome e Matrícula.")

    # =========================================================================
    # COLUNA DIREITA: ESCALA DE REGIÕES DOS TÉCNICOS (4 SLOTS)
    # =========================================================================
    with col_dir:
        st.subheader("🗺️ Escala de Regiões (4 Slots)")

        # Barra de Ações Compacta da Escala
        c_salvar, c_reset, c_busca = st.columns([1.5, 1.2, 2.0], vertical_alignment="center")
        with c_salvar:
            btn_salvar = st.button("💾 Salvar", type="primary", use_container_width=True, help="Grava no banco de dados todas as regiões atribuídas aos 4 slots")
        with c_reset:
            btn_reset = st.button("🔄 Recarregar", use_container_width=True, help="Restaura as atribuições salvas atualmente no banco")
        with c_busca:
            busca_tec = st.text_input("🔍 Filtrar técnico...", placeholder="Filtrar técnico...", label_visibility="collapsed")

        # Status inline com alerta de regiões livres
        alerta_html = f"<span style='color: #ef4444; font-weight: 700;'>⚠️ {len(regioes_livres)} Livres ({', '.join(regioes_livres[:4])}{'...' if len(regioes_livres)>4 else ''})</span>" if regioes_livres else "<span style='color: #10b981; font-weight: 700;'>✅ 100% Atribuídas</span>"
        st.markdown(f"<div style='font-size: 0.82rem; margin-top: 3px; margin-bottom: 6px;'><b>Total:</b> {len(todas_regioes)} &nbsp;|&nbsp; <b>Atribuídas:</b> {len(regioes_ocupadas)} &nbsp;|&nbsp; {alerta_html}</div>", unsafe_allow_html=True)

        # Ações de Salvamento e Reset
        if btn_salvar:
            with st.spinner("Salvando escala de regiões no banco de dados..."):
                sucesso = True
                for mat_tec, slots_tec in st.session_state.map_slots.items():
                    siglas_escolhidas = [s for s in slots_tec if s and s != "—"]
                    if not db_manager.atribuir_regioes_massa(mat_tec, siglas_escolhidas):
                        sucesso = False
                
                db_manager.get_mapeamento_regioes.clear()
                if sucesso:
                    st.toast("✅ Escala de regiões salva com sucesso!", icon="💾")
                    st.success("Escala de regiões salva com sucesso!")
                    time.sleep(0.8)
                    st.session_state.pop('map_slots', None)
                    for k in list(st.session_state.keys()):
                        if isinstance(k, str) and k.startswith('sel_slot_'):
                            st.session_state.pop(k, None)
                    st.rerun()
                else:
                    st.error("Ocorreu um erro ao salvar algumas regiões. Verifique os logs.")

        if btn_reset:
            st.session_state.pop('map_slots', None)
            for k in list(st.session_state.keys()):
                if isinstance(k, str) and k.startswith('sel_slot_'):
                    st.session_state.pop(k, None)
            st.rerun()

        # Filtro de busca na listagem dos técnicos
        if busca_tec:
            df_exibicao = df_ativos[
                df_ativos['nome'].str.contains(busca_tec, case=False, na=False) |
                df_ativos['matricula'].str.contains(busca_tec, case=False, na=False)
            ]
        else:
            df_exibicao = df_ativos

        # Callback para atualizar slot com Opção A (filtro dinâmico)
        def on_slot_change(matricula, slot_idx):
            key = f"sel_slot_{matricula}_{slot_idx}"
            novo_val = st.session_state.get(key, "—")
            st.session_state.map_slots[matricula][slot_idx] = novo_val

        # Renderização do cartão de um técnico (Tira Fina com 4 slots)
        def render_cartao_tecnico(row_tec):
            mat = str(row_tec['matricula']).strip()
            nome_disp = map_display_names.get(mat, row_tec['nome'])
            nome_completo = str(row_tec['nome']).strip()
            
            with st.container(border=True):
                c_nom, c1, c2, c3, c4 = st.columns([1.3, 0.8, 0.8, 0.8, 0.8], gap="small", vertical_alignment="center")
                
                with c_nom:
                    st.markdown(
                        f"<div style='font-size: 0.78rem; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 26px;' title='{nome_completo} ({mat})'>{nome_disp}</div>", 
                        unsafe_allow_html=True
                    )
                
                slots_cols = [c1, c2, c3, c4]
                for i_slot, col_slot in enumerate(slots_cols):
                    with col_slot:
                        val_atual = st.session_state.map_slots[mat][i_slot]
                        
                        # Opções disponíveis (Opção A):
                        opcoes_slot = ["—"]
                        if val_atual != "—":
                            opcoes_slot.append(val_atual)
                        for r in sorted(todas_regioes):
                            if r not in regioes_ocupadas and r != val_atual:
                                opcoes_slot.append(r)
                                
                        idx_sel = opcoes_slot.index(val_atual) if val_atual in opcoes_slot else 0
                        key_w = f"sel_slot_{mat}_{i_slot}"
                        
                        # Prevenção contra exceção de Streamlit caso opção mude
                        if key_w in st.session_state and st.session_state[key_w] not in opcoes_slot:
                            st.session_state[key_w] = val_atual if val_atual in opcoes_slot else "—"

                        st.selectbox(
                            f"Slot {i_slot+1} de {mat}",
                            options=opcoes_slot,
                            index=idx_sel,
                            key=key_w,
                            on_change=on_slot_change,
                            args=(mat, i_slot),
                            label_visibility="collapsed"
                        )

        # Divisão em 2 Colunas dentro da metade direita (2 técnicos por linha)
        if not df_exibicao.empty:
            num_cols = 2
            cols_painel = st.columns(num_cols, gap="small")
            
            tamanho_bloco = (len(df_exibicao) + num_cols - 1) // num_cols
            for i_col, col_target in enumerate(cols_painel):
                inicio = i_col * tamanho_bloco
                fim = min(inicio + tamanho_bloco, len(df_exibicao))
                if inicio < len(df_exibicao):
                    df_fatia = df_exibicao.iloc[inicio:fim]
                    with col_target:
                        for _, row in df_fatia.iterrows():
                            render_cartao_tecnico(row)
        else:
            st.info("Nenhum técnico encontrado para o filtro digitado.")

