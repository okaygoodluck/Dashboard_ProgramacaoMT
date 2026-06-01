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

