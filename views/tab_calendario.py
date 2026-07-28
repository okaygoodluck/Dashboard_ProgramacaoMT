import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, date, timedelta

def render_tab_calendario(df_filtered):
    """
    Renderiza a visão nativa do Calendário Mensal de Programação de Manobras.
    substituindo o arquivo estático externo HTML.
    """
    st.subheader("📅 Calendário de Programação")

    if df_filtered is None or df_filtered.empty:
        st.info("Nenhuma solicitação disponível para exibir no calendário.")
        return

    # Inicialização do estado de data ativa no calendário
    hoje = date.today()
    if "cal_ano" not in st.session_state:
        st.session_state.cal_ano = hoje.year
    if "cal_mes" not in st.session_state:
        st.session_state.cal_mes = hoje.month

    # Identificar coluna de Data de Início
    col_inicio = next((c for c in df_filtered.columns if 'início' in c.lower() or 'inicio' in c.lower()), None)
    
    df_cal = df_filtered.copy()
    if col_inicio:
        df_cal['Data_Parsed'] = pd.to_datetime(df_cal[col_inicio], dayfirst=True, errors='coerce').dt.date
    else:
        # Fallback para data atual se não encontrar coluna
        df_cal['Data_Parsed'] = hoje

    # Controles Superiores de Navegação Mensal
    c_nav1, c_nav2, c_nav3, c_nav4 = st.columns([1, 2.5, 1, 1])
    
    with c_nav1:
        if st.button("⬅️ Mês Anterior", use_container_width=True, key="cal_btn_prev"):
            if st.session_state.cal_mes == 1:
                st.session_state.cal_mes = 12
                st.session_state.cal_ano -= 1
            else:
                st.session_state.cal_mes -= 1
            st.rerun()

    with c_nav3:
        if st.button("Próximo Mês ➡️", use_container_width=True, key="cal_btn_next"):
            if st.session_state.cal_mes == 12:
                st.session_state.cal_mes = 1
                st.session_state.cal_ano += 1
            else:
                st.session_state.cal_mes += 1
            st.rerun()

    with c_nav4:
        if st.button("📅 Hoje", use_container_width=True, key="cal_btn_today"):
            st.session_state.cal_ano = hoje.year
            st.session_state.cal_mes = hoje.month
            st.rerun()

    nomes_meses = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ]
    nome_mes_atual = nomes_meses[st.session_state.cal_mes - 1]
    
    with c_nav2:
        st.markdown(
            f"<h3 style='text-align: center; margin: 0; color: var(--accent-color); font-size: 1.4rem;'>"
            f"{nome_mes_atual} / {st.session_state.cal_ano}</h3>",
            unsafe_allow_html=True
        )

    # Filtrar solicitações do mês selecionado
    ano_sel = st.session_state.cal_ano
    mes_sel = st.session_state.cal_mes

    df_mes = df_cal[
        (df_cal['Data_Parsed'].notna()) & 
        (df_cal['Data_Parsed'].apply(lambda d: d.year == ano_sel and d.month == mes_sel))
    ]

    total_mes = len(df_mes)
    aprovadas_mes = len(df_mes[df_mes['Is_Aprovada'] == True]) if 'Is_Aprovada' in df_mes.columns else 0
    elaboracao_mes = len(df_mes[df_mes['Is_Elaboracao'] == True]) if 'Is_Elaboracao' in df_mes.columns else 0
    atrasadas_mes = len(df_mes[df_mes['Status_Prazo'] == 'Atrasada']) if 'Status_Prazo' in df_mes.columns else 0

    # Cards KPI do Mês
    st.markdown("<br>", unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Total no Mês", f"{total_mes} manobras")
    with k2:
        st.metric("🟢 Aprovadas no Mês", f"{aprovadas_mes} manobras")
    with k3:
        st.metric("🔵 Em Elaboração", f"{elaboracao_mes} manobras")
    with k4:
        st.metric("🚨 Atrasadas/Prazos Críticos", f"{atrasadas_mes} manobras")

    st.markdown("<br>", unsafe_allow_html=True)

    # Cabeçalho dos Dias da Semana
    dias_semana = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    cols_header = st.columns(7)
    for idx, d_nome in enumerate(dias_semana):
        with cols_header[idx]:
            bg_hdr = "rgba(59, 130, 246, 0.2)" if idx < 5 else "rgba(148, 163, 184, 0.1)"
            st.markdown(
                f"<div style='background: {bg_hdr}; padding: 8px; border-radius: 6px; text-align: center; "
                f"font-weight: 700; font-size: 0.85rem; text-transform: uppercase; color: var(--text-primary);'>"
                f"{d_nome}</div>",
                unsafe_allow_html=True
            )

    # Matriz do Calendário Mensal
    cal = calendar.Calendar(firstweekday=0) # 0 = Segunda
    dias_matriz = cal.monthdatescalendar(ano_sel, mes_sel)

    # Dicionário de eventos por data
    eventos_por_data = {}
    if not df_mes.empty:
        for d_date, group in df_mes.groupby('Data_Parsed'):
            eventos_por_data[d_date] = group

    # Estilização e Renderização da Grade de Dias
    for semana in dias_matriz:
        st.markdown("<div style='margin-top: 6px;'></div>", unsafe_allow_html=True)
        cols_dia = st.columns(7)
        for idx, dia_dt in enumerate(semana):
            with cols_dia[idx]:
                is_current_month = (dia_dt.month == mes_sel)
                is_today = (dia_dt == hoje)
                
                # Cores e estilos do dia
                opacity = "1.0" if is_current_month else "0.35"
                border_color = "var(--accent-color)" if is_today else "var(--border-color)"
                bg_card = "rgba(30, 41, 59, 0.7)" if is_current_month else "rgba(15, 23, 42, 0.3)"
                
                if is_today:
                    bg_card = "rgba(59, 130, 246, 0.25)"

                grupo_dia = eventos_por_data.get(dia_dt, pd.DataFrame())
                qtd_dia = len(grupo_dia)

                # HTML do dia
                badge_html = ""
                if qtd_dia > 0:
                    aprov_count = len(grupo_dia[grupo_dia['Is_Aprovada'] == True]) if 'Is_Aprovada' in grupo_dia.columns else 0
                    elab_count = len(grupo_dia[grupo_dia['Is_Elaboracao'] == True]) if 'Is_Elaboracao' in grupo_dia.columns else 0
                    atraso_count = len(grupo_dia[grupo_dia['Status_Prazo'] == 'Atrasada']) if 'Status_Prazo' in grupo_dia.columns else 0
                    
                    details = []
                    if aprov_count > 0: details.append(f"<span style='color: #34d399; font-weight:700;'>✔ {aprov_count}</span>")
                    if elab_count > 0: details.append(f"<span style='color: #38bdf8; font-weight:700;'>📝 {elab_count}</span>")
                    if atraso_count > 0: details.append(f"<span style='color: #f87171; font-weight:700;'>🚨 {atraso_count}</span>")
                    
                    detail_str = " | ".join(details) if details else f"{qtd_dia} manobras"
                    badge_html = f"<div style='margin-top: 6px; font-size: 0.75rem;'>{detail_str}</div>"

                dia_num_str = f"<b>{dia_dt.day}</b>" if is_today else f"{dia_dt.day}"

                st.markdown(
                    f"""
                    <div style="
                        background: {bg_card};
                        border: 1px solid {border_color};
                        border-radius: 8px;
                        padding: 8px;
                        min-height: 90px;
                        opacity: {opacity};
                        display: flex;
                        flex-direction: column;
                        justify-content: space-between;
                    ">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 0.9rem; font-weight: 700; color: {'var(--accent-color)' if is_today else 'var(--text-primary)'};">
                                {dia_num_str}
                            </span>
                            {f"<span style='font-size: 0.7rem; background: var(--accent-color); color: white; padding: 1px 6px; border-radius: 10px; font-weight: 700;'>{qtd_dia}</span>" if qtd_dia > 0 else ""}
                        </div>
                        {badge_html}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # Se houver manobras no dia, disponibiliza visualização detalhada
                if qtd_dia > 0 and is_current_month:
                    with st.popover(f"📋 Ver ({qtd_dia})", use_container_width=True):
                        st.markdown(f"#### Manobras em **{dia_dt.strftime('%d/%m/%Y')}** ({qtd_dia})")
                        cols_show = [c for c in ['Solicitação', 'Região', 'Responsavel', 'Situação', 'Status_Prazo'] if c in grupo_dia.columns]
                        st.dataframe(grupo_dia[cols_show], use_container_width=True, hide_index=True)
