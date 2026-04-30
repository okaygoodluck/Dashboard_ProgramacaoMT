import streamlit as st
from ccp_ui import ICONS

def circular_progress_ring(label, value, color="#22d3ee"):
    """Gera um anel de progresso circular dinâmico."""
    try:
        val = float(value.replace('%', '')) if isinstance(value, str) else float(value)
    except:
        val = 0
    
    radius = 35
    circumference = 2 * 3.14159 * radius
    offset = circumference - (val / 100) * circumference
    
    html = f"""
    <div class="premium-card animate-target" style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%;">
        <div style="position: relative; width: 100px; height: 100px;">
            <svg width="100" height="100" viewBox="0 0 100 100" style="transform: rotate(-90deg);">
                <circle cx="50" cy="50" r="{radius}" stroke="var(--border-color)" stroke-width="8" fill="none" style="opacity: 0.5;"/>
                <circle cx="50" cy="50" r="{radius}" stroke="{color}" stroke-width="8" fill="none" 
                    stroke-dasharray="{circumference}" stroke-dashoffset="{offset}" 
                    style="transition: stroke-dashoffset 2s ease-out; filter: drop-shadow(0 0 5px {color}); shadow-linecap: round;"/>
            </svg>
            <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-family: 'Space Grotesk', sans-serif; font-size: 1.2rem; font-weight: 700; color: var(--text-primary);">
                {int(val)}%
            </div>
        </div>
        <div style="margin-top: var(--space-xs); color: var(--text-secondary); font-size: 0.8rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1px;">{label}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def premium_metric_card(title, value, delta=None, icon_name="info", color=None, is_vanguard=False):
    """Gera um card de métrica premium com Iconsax e animação."""
    icon_svg = ICONS.get(icon_name, ICONS["info"])
    accent = color if color else "var(--accent-color)"
    vanguard_class = "vanguard-card" if is_vanguard else ""
    
    delta_html = ""
    if delta is not None:
        d_color = "#34d399" if delta >= 0 else "#f87171"
        d_icon = "↑" if delta >= 0 else "↓"
        delta_html = f'<div style="color: {d_color}; font-size: 0.85rem; font-weight: 600; margin-top: 4px;">{d_icon} {abs(delta)}% em relação a ontem</div>'

    html = f"""
    <div class="premium-card {vanguard_class} animate-target" style="border-left: 4px solid {accent}; display: flex; flex-direction: column; justify-content: space-between; height: 100%;">
        <div style="display: flex; align-items: center; gap: var(--space-sm); margin-bottom: var(--space-xs); position: relative; z-index: 2;">
            <div style="color: {accent}; display: flex; align-items: center;">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    {icon_svg}
                </svg>
            </div>
            <span style="color: var(--text-muted); font-size: 0.8rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">{title}</span>
        </div>
        <div style="font-family: 'Space Grotesk', sans-serif; font-size: 2rem; font-weight: 700; color: var(--text-primary); line-height: 1; position: relative; z-index: 2;">
            {value}
        </div>
        {delta_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def alert_hub_card(protocolo, tecnico, data, status_email):
    """Gera um card específico para o Alert Hub (Urgências)."""
    is_confirmed = (status_email == "E-MAIL RECEBIDO")
    card_class = "alert-card-green" if is_confirmed else "alert-card-red"
    status_color = "#10b981" if is_confirmed else "#ef4444"
    icon = "📧" if is_confirmed else "⏳"
    
    html = f"""
    <div class="premium-card {card_class} animate-target" style="margin-bottom: 10px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div>
                <div style="font-size: 0.7rem; color: var(--text-secondary); text-transform: uppercase; font-weight: 700;">Protocolo</div>
                <div style="font-family: 'Space Grotesk', sans-serif; font-size: 1.1rem; font-weight: 700; color: {status_color};">{protocolo}</div>
            </div>
            <div style="font-size: 1.2rem;">{icon}</div>
        </div>
        <div style="margin-top: 10px;">
            <div style="font-size: 0.85rem; font-weight: 600; color: var(--text-primary);">{tecnico}</div>
            <div style="font-size: 0.75rem; color: var(--text-secondary);">Início: {data}</div>
        </div>
        <div style="margin-top: 10px; border-top: 1px solid var(--border-color); padding-top: 5px;">
             <div style="font-size: 0.7rem; font-weight: 800; color: {status_color}; text-transform: uppercase;">
                {status_email}
             </div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def render_luminous_alert_hub(df_filtered):
    """Renderiza o Hub de Alertas de Urgência com estilização Luminous."""
    # Filtra apenas urgências
    df_urgencia = df_filtered[df_filtered['Status_Prazo'] == 'Urgência'].copy()
    
    if not df_urgencia.empty:
        st.markdown("---")
        st.subheader("🚨 PROTOCOLO DE URGÊNCIA (ALERT HUB)")
        
        # Grid de cards (Máximo 4 por linha)
        cols = st.columns(4)
        for idx, (_, row) in enumerate(df_urgencia.iterrows()):
            col_idx = idx % 4
            with cols[col_idx]:
                # Status do E-mail para feedback visual
                status_email = "E-MAIL RECEBIDO" if row.get('Tem_Email') else "AGUARDANDO E-MAIL"
                
                alert_hub_card(
                    protocolo=row.get('Protocolo', 'N/A'),
                    tecnico=row.get('Responsavel', 'Não Atribuído'),
                    data=row.get('Data Inicio', 'S/D'),
                    status_email=status_email
                )
        st.markdown("---")
