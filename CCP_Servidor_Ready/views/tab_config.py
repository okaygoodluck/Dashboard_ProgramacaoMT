import streamlit as st
import db_manager
import time

def render_tab_config():
    """Renderiza a aba de configurações administrativas."""
    st.header("⚙️ Configurações Administrativas")
    
    # 1. Alerta de Regiões não atribuídas
    regioes_nos_dados = db_manager.get_regioes_disponiveis_data()
    df_map_atual = db_manager.get_mapeamento_regioes()
    regioes_mapeadas = df_map_atual['sigla_regiao'].tolist()
    
    regioes_sem_dono = [r for r in regioes_nos_dados if r not in regioes_mapeadas]
    
    if regioes_sem_dono:
        st.error(f"⚠️ **Atenção:** Existem {len(regioes_sem_dono)} regiões sem responsável atribuído: **{', '.join(regioes_sem_dono)}**")
    else:
        st.success("✅ Todas as regiões presentes nos dados possuem um responsável atribuído.")

    # Layout de Colunas Modernizado [Geral | Mapeamento]
    c_adm1, c_adm2 = st.columns([1, 1.2], gap="large")
    
    with c_adm1:
        st.subheader("👥 Gestão de Usuários")
        df_users = db_manager.listar_usuarios()
        
        # Filtro de Busca Dinâmica
        search_user = st.text_input("🔍 Buscar funcionário...", placeholder="Nome ou Matrícula", label_visibility="collapsed")
        
        tab_lista, tab_novo = st.tabs(["📋 Lista Registrada", "➕ Novo Cadastro"])
        
        with tab_lista:
            if not df_users.empty:
                # Lógica de Filtro
                if search_user:
                    df_filtered = df_users[
                        df_users['nome'].str.contains(search_user, case=False, na=False) |
                        df_users['matricula'].str.contains(search_user, case=False, na=False)
                    ]
                else:
                    df_filtered = df_users

                if not df_filtered.empty:
                    # Container com Altura Fixa e Scroll para evitar esticamento da página
                    with st.container(height=550):
                        for idx, row in df_filtered.iterrows():
                            with st.container(border=True):
                                col_u1, col_u2, col_u3, col_u4 = st.columns([3, 1.5, 0.8, 0.8])
                                
                                with col_u1:
                                    st.markdown(f"**{row['nome']}**")
                                    st.caption(f"ID: {row['matricula']}")
                                
                                with col_u2:
                                    nivel_color = "#22d3ee" if row['nivel'] == "ADM" else "#f59e0b" if row['nivel'] == "Gerencial" else "#94a3b8"
                                    st.markdown(f'<div style="background:{nivel_color}15; color:{nivel_color}; border: 1px solid {nivel_color}40; padding: 1px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: 600; text-align: center; margin-top: 5px;">{row["nivel"]}</div>', unsafe_allow_html=True)
                                
                                with col_u3:
                                    if st.button("🔑", key=f"reset_{row['matricula']}", help="Resetar Senha para 12345"):
                                        if db_manager.resetar_senha(row['matricula']):
                                            st.toast(f"Senha de {row['nome']} resetada!")
                                            time.sleep(0.5)
                                            st.rerun()
                                
                                with col_u4:
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

    with c_adm2:
        st.subheader("🗺️ Mapeamento de Regiões")
        
        # Tabela de Mapeamento com Estilo Vanguard
        with st.container(border=True):
            st.markdown("##### Responsáveis por Região")
            st.dataframe(
                df_map_atual, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "sigla_regiao": st.column_config.TextColumn("Região", width="small"),
                    "responsavel": st.column_config.TextColumn("Responsável"),
                    "matricula": st.column_config.TextColumn("ID", width="small")
                }
            )
        
        with st.expander("📝 Editar Atribuições em Massa", expanded=False):
            if not df_users.empty:
                tecnico_selecionado = st.selectbox(
                    "Selecione o Responsável", 
                    options=df_users['matricula'].tolist(), 
                    format_func=lambda x: f"{df_users[df_users['matricula']==x]['nome'].iloc[0]}"
                )
                
                regioes_atuais = df_map_atual[df_map_atual['matricula'] == tecnico_selecionado]['sigla_regiao'].tolist()
                
                st.markdown(f"Atribuindo regiões para: **{df_users[df_users['matricula']==tecnico_selecionado]['nome'].iloc[0]}**")
                regioes_novas = st.multiselect(
                    "Selecione as Regiões", 
                    options=regioes_nos_dados, 
                    default=[r for r in regioes_atuais if r in regioes_nos_dados]
                )
                
                if st.button("💾 Salvar Atribuições", type="primary"):
                    if db_manager.atribuir_regioes_massa(tecnico_selecionado, regioes_novas):
                        st.success("Mapeamento atualizado com sucesso!")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
            else:
                st.error("Cadastre usuários primeiro para atribuir regiões.")
