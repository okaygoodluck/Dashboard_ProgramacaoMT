import streamlit as st
import calendar
from datetime import date, datetime, timedelta

# --- BANCO DE FERIADOS (BH / CEMIG) ---
HOLIDAYS_BH_2025 = [
    (1, 1, "Confraternização Universal"),
    (3, 3, "Carnaval"),
    (3, 4, "Carnaval (facultativo)"),
    (3, 5, "Quarta-feira de Cinzas"),
    (4, 18, "Paixão de Cristo"),
    (4, 21, "Tiradentes"),
    (5, 1, "Dia do Trabalhador"),
    (5, 2, "Dia do Trabalhador (emenda)"),
    (6, 19, "Corpus Christi"),
    (6, 20, "Corpus Christi (emenda)"),
    (8, 15, "Assunção de N. Sra."),
    (9, 7, "Independência do Brasil"),
    (10, 12, "N. Sra. Aparecida"),
    (11, 2, "Finados"),
    (11, 15, "Proclamação da República"),
    (11, 20, "Consciência Negra"),
    (11, 21, "Consciência Negra (emenda)"),
    (11, 25, "Feriado Municipal BH"),
    (12, 24, "Véspera de Natal"),
    (12, 25, "Natal"),
    (12, 26, "Natal (emenda)"),
    (12, 31, "Véspera de Ano Novo")
]

HOLIDAYS_BH_2026 = [
    (1, 1, "Confraternização Universal"),
    (1, 2, "Confraternização Universal (emenda)"),
    (2, 16, "Segunda de Carnaval"),
    (2, 17, "Terça de Carnaval"),
    (2, 18, "Quarta de Cinzas"),
    (4, 3, "Paixão de Cristo"),
    (4, 20, "Emenda Tiradentes"),
    (4, 21, "Tiradentes"),
    (5, 1, "Dia do Trabalhador"),
    (6, 4, "Corpus Christi"),
    (6, 5, "Emenda Corpus Christi"),
    (8, 15, "Assunção de N. Sra."),
    (9, 7, "Independência do Brasil"),
    (10, 12, "N. Sra. Aparecida"),
    (11, 2, "Finados"),
    (11, 15, "Proclamação da República"),
    (11, 20, "Consciência Negra"),
    (12, 25, "Natal"),
    (12, 31, "Véspera de Ano Novo")
]

def get_holiday_info(d: date):
    """Retorna o nome do feriado caso a data seja um feriado cadastrado."""
    h_list = HOLIDAYS_BH_2025 if d.year == 2025 else (HOLIDAYS_BH_2026 if d.year == 2026 else [])
    for month, day, name in h_list:
        if d.month == month and d.day == day:
            return name
    return None

def is_holiday(d: date):
    return get_holiday_info(d) is not None

def is_business_day(d: date):
    """Verifica se a data é um dia útil (não é fim de semana nem feriado)."""
    return d.weekday() < 5 and not is_holiday(d)

def calculate_business_days(start_date: date, end_date: date):
    """Calcula o número de dias úteis entre duas datas (inclusive)."""
    if start_date > end_date:
        return -1
    count = 0
    curr = start_date
    while curr <= end_date:
        if is_business_day(curr):
            count += 1
        curr += timedelta(days=1)
    return count

def add_business_days(start_date: date, days_to_add: int):
    """Soma N dias úteis a uma data inicial."""
    if days_to_add <= 0:
        return start_date
    curr = start_date
    count = 0
    while count < days_to_add:
        curr += timedelta(days=1)
        if is_business_day(curr):
            count += 1
    return curr

def get_consecutive_non_business_days(start_date: date):
    """Retorna lista de dias não úteis consecutivos imediatamente após uma data."""
    res = []
    curr = start_date + timedelta(days=1)
    while not is_business_day(curr):
        res.append(curr)
        curr += timedelta(days=1)
    return res

def render_month_calendar_html(year: int, month: int, today_date: date):
    """Gera o HTML/CSS de um único mês com estilos fiéis ao calendario_programacao.html."""
    month_names = ["", "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", 
                   "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
    
    month_name = f"{month_names[month]} {year}"
    
    # Limites operacionais calculados a partir de hoje
    condis_limit = add_business_days(today_date, 2)
    avisos_limit = add_business_days(today_date, 8)
    approval_limit = add_business_days(today_date, 11)
    
    condis_ext = [condis_limit] + get_consecutive_non_business_days(condis_limit)
    avisos_ext = [avisos_limit] + get_consecutive_non_business_days(avisos_limit)
    approval_ext = [approval_limit] + get_consecutive_non_business_days(approval_limit)
    
    days_html_list = []
    
    # Matriz real por semanas (Domingo a Sábado)
    first_day_weekday = calendar.monthrange(year, month)[0] # 0=Seg, 6=Dom
    # Offset para domingo (Se Seg(0) => offset 1, Dom(6) => offset 0)
    start_offset = (first_day_weekday + 1) % 7
    total_days = calendar.monthrange(year, month)[1]
    
    # Preencher dias vazios iniciais
    for _ in range(start_offset):
        days_html_list.append('<div class="cal-day empty"></div>')
        
    for day_num in range(1, total_days + 1):
        curr_date = date(year, month, day_num)
        is_today = (curr_date == today_date)
        holiday_name = get_holiday_info(curr_date)
        
        # Classes e cores
        classes = ["cal-day"]
        applied_colors = []
        legends = []
        
        if is_today:
            classes.append("today")
            
        if holiday_name:
            classes.append("holiday")
            applied_colors.append("#ac63e3") # Roxo
            legends.append(holiday_name)
            
        # Prazos Limites Operacionais
        if any(curr_date == d for d in approval_ext):
            classes.append("limit-aprovacao")
            applied_colors.append("#d64a38") # Vermelho Escuro
            legends.append("Aprovação")
            
        if any(curr_date == d for d in avisos_ext):
            classes.append("limit-avisos")
            applied_colors.append("#f7913d") # Laranja
            legends.append("Avisos")
            
        if any(curr_date == d for d in condis_ext):
            classes.append("limit-condis")
            applied_colors.append("#3f9be6") # Azul
            legends.append("Condis")
            
        # Regra de coloração base de dias úteis futuros/passados
        if curr_date >= today_date:
            b_days = calculate_business_days(today_date, curr_date)
            if 0 <= b_days <= 11:
                if not holiday_name and not any(curr_date == d for d in (approval_ext + avisos_ext + condis_ext)):
                    classes.append("red-day") # Vermelho Claro / Janela Crítica
            elif b_days > 11:
                if not holiday_name and not any(curr_date == d for d in (approval_ext + avisos_ext + condis_ext)):
                    classes.append("green-day") # Verde / Janela Segura

        # Estilo de Fundo (Gradiente se houver múltiplos status)
        style_inline = ""
        if len(applied_colors) > 1:
            step = 100.0 / len(applied_colors)
            stops = []
            for idx, c in enumerate(applied_colors):
                s = idx * step
                e = (idx + 1) * step
                stops.append(f"{c} {s:.1f}%")
                stops.append(f"{c} {e:.1f}%")
            style_inline = f'background: linear-gradient(135deg, {", ".join(stops)}) !important; color: white !important;'
        elif len(applied_colors) == 1:
            style_inline = f'background-color: {applied_colors[0]} !important; color: white !important;'

        legend_text = " / ".join(dict.fromkeys(legends)) # Para tooltip no hover
        title_attr = f'title="{legend_text}"' if legend_text else ""
        class_str = " ".join(classes)
        
        day_card = f'<div class="{class_str}" style="{style_inline}" {title_attr}><span class="cal-number">{day_num}</span></div>'
        days_html_list.append(day_card)
        
    return month_name, "".join(days_html_list)

def render_tab_calendario(df_filtered=None, *args, **kwargs):
    """Renderiza a aba Calendário nativamente em Python/Streamlit."""
    
    # Inicializa estado da navegação de meses
    if 'cal_month_offset' not in st.session_state:
        st.session_state['cal_month_offset'] = 0
        
    hoje = date.today()
    
    # Controle de Navegação dos Meses
    c_nav1, c_nav2, c_nav3 = st.columns([1.5, 4, 1.5])
    with c_nav1:
        if st.button("❮ Mês Anterior", use_container_width=True, key="btn_cal_prev"):
            st.session_state['cal_month_offset'] -= 1
            st.rerun()
            
    with c_nav3:
        if st.button("Próximo Mês ❯", use_container_width=True, key="btn_cal_next"):
            st.session_state['cal_month_offset'] += 1
            st.rerun()
            
    with c_nav2:
        if st.session_state['cal_month_offset'] != 0:
            if st.button("📅 Voltar para Mês Atual", use_container_width=True, key="btn_cal_reset"):
                st.session_state['cal_month_offset'] = 0
                st.rerun()

    # Cálculo dos dois meses a serem exibidos
    offset = st.session_state['cal_month_offset']
    
    # Mês 1
    m1_month = (hoje.month - 1 + offset) % 12 + 1
    m1_year = hoje.year + (hoje.month - 1 + offset) // 12
    
    # Mês 2 (Próximo Mês)
    m2_month = (m1_month) % 12 + 1
    m2_year = m1_year + (1 if m1_month == 12 else 0)
    
    title_m1, html_days_m1 = render_month_calendar_html(m1_year, m1_month, hoje)
    title_m2, html_days_m2 = render_month_calendar_html(m2_year, m2_month, hoje)

    # Injeção de CSS nativo padronizado com o Design System
    st.markdown("""
    <style>
    .cal-month-card {
        background: var(--surface-color, #1e293b);
        border: 1px solid var(--border-color, #334155);
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    }
    .cal-month-title {
        text-align: center;
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--text-primary, #f8fafc);
        margin-bottom: 16px;
        letter-spacing: 1px;
    }
    .cal-weekdays {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        text-align: center;
        font-weight: 700;
        font-size: 0.9rem;
        color: #94a3b8;
        margin-bottom: 12px;
    }
    .cal-grid {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 8px;
    }
    .cal-day {
        min-height: 75px;
        border-radius: 10px;
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 6px 2px;
        transition: all 0.2s ease;
        position: relative;
        overflow: hidden;
    }
    .cal-day:not(.empty):hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    .cal-day.empty {
        background: transparent !important;
        border: none !important;
    }
    .cal-number {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.25rem;
        font-weight: 700;
        line-height: 1;
        margin-bottom: 4px;
    }
    .cal-legend {
        font-size: 0.65rem;
        font-weight: 700;
        text-transform: uppercase;
        text-align: center;
        line-height: 1.1;
        padding: 2px 4px;
        border-radius: 4px;
        word-break: break-word;
        max-width: 95%;
    }
    
    /* Cores de Status */
    .cal-day.green-day { background-color: #059669; color: white; }
    .cal-day.red-day { background-color: #dc2626; color: white; }
    .cal-day.holiday { background-color: #8b5cf6; color: white; }
    .cal-day.limit-aprovacao { background-color: #b91c1c; color: white; }
    .cal-day.limit-avisos { background-color: #d97706; color: white; }
    .cal-day.limit-condis { background-color: #0284c7; color: white; }
    
    /* Dia Atual (Today) */
    .cal-day.today {
        border: 3px solid #38bdf8 !important;
        box-shadow: 0 0 16px rgba(56, 189, 248, 0.6) !important;
        transform: scale(1.03);
    }
    
    /* Barra Informativa de Legenda */
    .cal-info-bar {
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
        justify-content: center;
        background: rgba(30, 41, 59, 0.6);
        padding: 12px;
        border-radius: 12px;
        margin-top: 20px;
        border: 1px solid rgba(255,255,255,0.08);
    }
    .cal-info-item {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 0.8rem;
        font-weight: 600;
        color: #cbd5e1;
    }
    .cal-info-dot {
        width: 12px;
        height: 12px;
        border-radius: 4px;
    }
    </style>
    """, unsafe_allow_html=True)

    # Exibição dos 2 meses lado a lado
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f'<div class="cal-month-card"><div class="cal-month-title">{title_m1}</div><div class="cal-weekdays"><span>DOM</span><span>SEG</span><span>TER</span><span>QUA</span><span>QUI</span><span>SEX</span><span>SÁB</span></div><div class="cal-grid">{html_days_m1}</div></div>', unsafe_allow_html=True)

    with col2:
        st.markdown(f'<div class="cal-month-card"><div class="cal-month-title">{title_m2}</div><div class="cal-weekdays"><span>DOM</span><span>SEG</span><span>TER</span><span>QUA</span><span>QUI</span><span>SEX</span><span>SÁB</span></div><div class="cal-grid">{html_days_m2}</div></div>', unsafe_allow_html=True)

    # Barra Informativa de Legenda
    st.markdown("""
    <div class="cal-info-bar">
        <div class="cal-info-item"><div class="cal-info-dot" style="background:#dc2626;"></div> 🔴 Janela Crítica (Até 11 D.U.)</div>
        <div class="cal-info-item"><div class="cal-info-dot" style="background:#059669;"></div> 🟢 Janela Segura (> 11 D.U.)</div>
        <div class="cal-info-item"><div class="cal-info-dot" style="background:#b91c1c;"></div> 🚨 Limite Aprovação (11 D.U.)</div>
        <div class="cal-info-item"><div class="cal-info-dot" style="background:#d97706;"></div> 🟠 Limite Avisos (8 D.U.)</div>
        <div class="cal-info-item"><div class="cal-info-dot" style="background:#0284c7;"></div> 🔵 Limite Condis (2 D.U.)</div>
        <div class="cal-info-item"><div class="cal-info-dot" style="background:#8b5cf6;"></div> 🟣 Feriado (BH)</div>
        <div class="cal-info-item"><div class="cal-info-dot" style="border: 2px solid #38bdf8; background: transparent;"></div> 🔷 Hoje</div>
    </div>
    """, unsafe_allow_html=True)
