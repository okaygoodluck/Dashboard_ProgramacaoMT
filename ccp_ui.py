import streamlit as st

# --- BIBLIOTECA DE ÍCONES (ICONSAX LINEAR) ---
ICONS = {
    "timer": '<path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M12 7V12L15 15" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
    "flash": '<path d="M13 2L3 14H12L11 22L21 10H12L13 2Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
    "tick": '<path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M7.75 12L10.58 14.83L16.25 9.17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
    "info": '<path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M12 8V13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M11.9941 16H12.0031" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    "people": '<path d="M12 11C14.2091 11 16 9.20914 16 7C16 4.79086 14.2091 3 12 3C9.79086 3 8 4.79086 8 7C8 9.20914 9.79086 11 12 11Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 21V19C6 16.7909 7.79086 15 10 15H14C16.2091 15 18 16.7909 18 19V21" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
    "edit": '<path d="M11 4H4C3.46957 4 2.96086 4.21071 2.58579 4.58579C2.21071 4.96086 2 5.46957 2 6V20C2 20.5304 2.21071 21.0391 2.58579 21.4142C2.96086 21.7893 3.46957 22 4 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M18.5 2.5C18.8978 2.10217 19.4374 1.87868 20 1.87868C20.5626 1.87868 21.1022 2.10217 21.5 2.5C21.8978 2.89782 22.1213 3.43739 22.1213 4C22.1213 4.56261 21.8978 5.10218 21.5 5.5L12 15L8 16L9 12L18.5 2.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
}

# --- CONFIGURAÇÕES DE DESIGN SYSTEM ---
DESIGN_SYSTEM = {
    "Dark": {
        "bg": "#0e1117",
        "surface": "#1a1d23",
        "surface_hover": "#262b35",
        "card_bg": "rgba(26, 29, 35, 0.8)",
        "text": "#ffffff",
        "text_secondary": "#9fb3c8",
        "text_muted": "#64748b",
        "accent": "#22d3ee",
        "accent_glow": "rgba(34, 211, 238, 0.3)",
        "border": "rgba(255, 255, 255, 0.05)",
        "card_shadow": "0 8px 32px 0 rgba(0, 0, 0, 0.8)"
    },
    "Light": {
        "bg": "#f8fafc",
        "surface": "#ffffff",
        "surface_hover": "#f1f5f9",
        "card_bg": "#ffffff",
        "text": "#0f172a",
        "text_secondary": "#475569",
        "text_muted": "#94a3b8",
        "accent": "#2563eb",
        "accent_glow": "rgba(37, 99, 235, 0.1)",
        "border": "#e2e8f0",
        "card_shadow": "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)"
    }
}

def inject_ui_css(theme="Dark"):
    """Injeta o CSS principal mapeando para as variáveis nativas do Streamlit."""
    
    st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Oswald:wght@500;700&family=Space+Grotesk:wght@500;700&display=swap');

        :root {{
            --bg-color: var(--background-color);
            --surface-color: var(--secondary-background-color);
            --surface-hover: rgba(128, 128, 128, 0.1);
            --card-bg: var(--secondary-background-color);
            --text-primary: var(--text-color);
            --text-secondary: var(--text-color);
            --text-muted: var(--text-color);
            --accent-color: var(--primary-color);
            --accent-glow: rgba(128, 128, 128, 0.1);
            --border-color: rgba(128, 128, 128, 0.2);
            --card-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            
            --space-xs: 0.25rem;
            --space-sm: 0.5rem;
            --space-md: 0.75rem;
            --space-lg: 1.25rem;
        }}

        /* --- OCULTAR BOTÃO DE DEPLOY --- */
        .stAppDeployButton {{
            display: none !important;
        }}
        .stDeployButton {{
            display: none !important;
        }}
        [data-testid="stAppDeployButton"] {{
            display: none !important;
        }}

        /* --- PREVENÇÃO DE ESCURECIMENTO (LOADING) --- */
        [data-testid="stAppViewContainer"] > div:first-child {{
            transition: none !important;
        }}
        [data-testid="stApp"] {{
            opacity: 1 !important;
            transition: none !important;
        }}
        [data-testid="stAppViewBlockContainer"] {{
            transition: none !important;
        }}

        /* Global Reset */
        .stApp {{
            background-color: var(--bg-color);
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
        }}

        /* Anti-Dimming & Anti-Blur Total (Impede 100% o escurecimento e desfoque da tela no Streamlit) */
        .stApp[data-test-script-state="running"],
        .stApp[data-test-script-state="running"] *,
        [data-testid="stAppViewContainer"][data-test-script-state="running"],
        [data-testid="stAppViewContainer"][data-test-script-state="running"] *,
        [data-testid="stMainBlockContainer"],
        [data-testid="stMainBlockContainer"] *,
        [data-testid="stAppViewBlockContainer"],
        [data-testid="stAppViewBlockContainer"] *,
        [data-testid="stMain"],
        [data-testid="stMain"] *,
        .stElementContainer,
        .stElementContainer * {{
            opacity: 1 !important;
            filter: none !important;
            backdrop-filter: none !important;
            transition: none !important;
        }}
        [data-testid="stStatusWidget"],
        div[data-testid="stStatusWidget"],
        .stSpinner {{
            display: none !important;
            visibility: hidden !important;
        }}
        
        [data-testid="stWidgetLabel"] p, .stMarkdown p {{ color: var(--text-primary) !important; }}
        
        /* Selectbox e Inputs */
        div[data-baseweb="select"] > div {{
            background-color: var(--surface-color) !important;
            border-color: var(--border-color) !important;
        }}
        div[data-baseweb="select"] * {{ color: var(--text-primary) !important; }}
        
        /* Popovers / Listboxes */
        [data-baseweb="popover"] div[role="listbox"], [data-baseweb="popover"] ul {{
            background-color: var(--bg-color) !important;
        }}
        [data-baseweb="popover"] li {{
            color: var(--text-primary) !important;
            background-color: var(--surface-color) !important;
        }}

        /* Sistema de Cards de Controle */
        .premium-card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: var(--space-md);
            box-shadow: var(--card-shadow);
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            position: relative;
            overflow: hidden;
            backdrop-filter: blur(10px);
            z-index: 1;
        }}

        .premium-card:hover {{
            border-color: var(--accent-color);
            box-shadow: 0 10px 40px var(--accent-glow);
            transform: translateY(-5px) scale(1.02);
        }}

        /* Classes para preenchimento total dos cards de saldo */
        .card-saldo-red {{
            background-color: #dc2626 !important;
            background-image: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%) !important;
            border: 2px solid #fca5a5 !important;
            border-left: 6px solid #ffffff !important;
            box-shadow: 0 4px 20px rgba(239, 68, 68, 0.6) !important;
            backdrop-filter: none !important;
        }}

        .card-saldo-green {{
            background-color: #059669 !important;
            background-image: linear-gradient(135deg, #10b981 0%, #047857 100%) !important;
            border: 2px solid #6ee7b7 !important;
            border-left: 6px solid #ffffff !important;
            box-shadow: 0 4px 20px rgba(16, 185, 129, 0.6) !important;
            backdrop-filter: none !important;
        }}

        /* Typography */
        h1, h2, h3 {{
            font-family: 'Space Grotesk', sans-serif !important;
            text-transform: uppercase;
            letter-spacing: 2px;
            font-weight: 700 !important;
            color: var(--text-primary) !important;
        }}

        /* Alertas do Centro de Controle */
        .alert-card-green {{ border-left: 5px solid #10b981 !important; box-shadow: 0 0 15px rgba(16, 185, 129, 0.2); }}
        .alert-card-red {{ border-left: 5px solid #ef4444 !important; box-shadow: 0 0 15px rgba(239, 68, 68, 0.2); animation: pulse-red 2s infinite; }}
        
        @keyframes pulse-red {{
            0% {{ box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }}
            70% {{ box-shadow: 0 0 0 15px rgba(239, 68, 68, 0); }}
            100% {{ box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }}
        }}

        /* Scrollbar */
        ::-webkit-scrollbar-thumb:hover {{ background: var(--accent-color); }}

        /* Sidebar Dinâmica */
        [data-testid="stSidebar"] {{
            background-color: var(--surface-color) !important;
            border-right: 1px solid var(--border-color) !important;
        }}
        [data-testid="stSidebar"] * {{
            color: var(--text-primary) !important;
        }}
        [data-testid="stSidebarNav"] {{
            background-color: transparent !important;
        }}

        /* Normalização de Botões Streamlit (Alta Especificidade) */
        button[kind="secondary"], button[kind="primary"], .stButton > button, .stDownloadButton > button {{
            background-color: var(--surface-color) !important;
            color: var(--text-primary) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 8px !important;
            font-family: 'Space Grotesk', sans-serif !important;
            font-weight: 600 !important;
            transition: all 0.3s ease !important;
            padding: 0.5rem 1rem !important;
        }}

        button[kind="secondary"]:hover, button[kind="primary"]:hover, .stButton > button:hover {{
            border-color: var(--accent-color) !important;
            color: var(--accent-color) !important;
            background-color: var(--surface-hover) !important;
            box-shadow: 0 4px 12px var(--accent-glow) !important;
        }}

        /* Widgets: Datas e Multiselect (Alta Especificidade) */
        .stDateInput div[data-baseweb="input"], 
        .stMultiSelect div[data-baseweb="select"],
        div[data-testid="stDateInput"] div[data-baseweb="input"] {{
            background-color: var(--surface-color) !important;
            border-color: var(--border-color) !important;
        }}
        
        .stDateInput input, div[data-testid="stDateInput"] input {{
            color: var(--text-primary) !important;
            background-color: transparent !important;
        }}
        
        /* Chips (Tags do Multiselect) - Reset Completo */
        [data-baseweb="tag"] {{
            background-color: var(--accent-glow) !important;
            border: 1px solid var(--accent-color) !important;
            color: var(--text-primary) !important;
            border-radius: 6px !important;
        }}
        [data-baseweb="tag"] * {{
            color: var(--text-primary) !important;
        }}

        /* Expander Headers (Reset Completo) */
        .stExpander, [data-testid="stExpander"] {{
            background-color: var(--card-bg) !important;
            border: 1px solid var(--border-color) !important;
        }}
        .stExpander summary, [data-testid="stExpander"] summary {{
            background-color: var(--surface-hover) !important;
            color: var(--text-primary) !important;
        }}
        
        /* Ajuste de Botões Streamlit em Containers Específicos */
        div.stButton > button, div.stDownloadButton > button, 
        .st-emotion-cache-1... button {{
            background-color: var(--surface-color) !important;
            color: var(--text-primary) !important;
            border: 1px solid var(--border-color) !important;
        }}
        
        /* Sidebar Icons e Textos */
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{
            color: var(--text-primary) !important;
        }}

        /* Anti-Ghost: Oculta componentes técnicos invisíveis */
        iframe[height="0"], iframe[width="0"], .stAutorefresh, div[data-testid="stHtml"][style*="height: 0"] {{
            display: none !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }}

    </style>
    """, unsafe_allow_html=True)

def inject_ui_assets():
    """Injeta animações, Splash Screen e o motor do Relógio Digital."""
    js_clock = """
    <script>
    function updateClock() {
        const doc = window.parent.document;
        const clockEl = doc.querySelector('#digital-clock');
        if (clockEl) {
            const now = new Date();
            const h = String(now.getHours()).padStart(2, '0');
            const m = String(now.getMinutes()).padStart(2, '0');
            const s = String(now.getSeconds()).padStart(2, '0');
            clockEl.textContent = `${h}:${m}:${s}`;
        }
    }
    // Atualiza a cada segundo
    if (!window.ccpClockSet) {
        setInterval(updateClock, 1000);
        window.ccpClockSet = true;
    }
    </script>
    """
    st.components.v1.html(js_clock, height=0)



def login_screen(cookie_manager=None):
    """Renderiza a interface de login premium."""
    import db_manager
    # CSS agressivo para Square Mode 4.0 (Formulário DENTRO do Card)
    st.markdown("""
        <style>
        /* Oculta infra técnica */
        iframe[height="0"], iframe[width="0"], .stAutorefresh, 
        div[data-testid="stHtml"], div[data-testid="stComponent"] {
            display: none !important;
        }

        /* Aplica o estilo do CARD diretamente na coluna central do Streamlit */
        [data-testid="column"]:nth-of-type(2) [data-testid="stVerticalBlock"] {
            background: rgba(26, 29, 35, 0.95) !important;
            backdrop-filter: blur(30px) !important;
            padding: 45px 35px !important;
            border-radius: 24px !important;
            border: 1px solid rgba(255,255,255,0.1) !important;
            box-shadow: 0 50px 100px rgba(0,0,0,0.9) !important;
            text-align: center !important;
            margin-top: 10px !important;
        }
        
        /* Ajuste de Título */
        [data-testid="column"]:nth-of-type(2) h3 {
            margin-top: 0 !important;
            color: white !important;
            font-size: 1.7rem !important;
            font-weight: 800 !important;
            letter-spacing: -0.5px !important;
        }

        /* Estilização de Inputs e Botão */
        .stButton>button {
            width: 100% !important;
            background: linear-gradient(135deg, #22d3ee, #0ea5e9) !important;
            color: white !important;
            font-weight: 700 !important;
            border: none !important;
            padding: 15px !important;
            border-radius: 12px !important;
            margin-top: 20px !important;
            text-transform: uppercase;
            letter-spacing: 1.5px;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Grid de Centralização (O container da coluna 2 será o nosso CARD)
    _, center_col, _ = st.columns([1.1, 1, 1.1])
    
    with center_col:
        st.markdown('### 🧊 CENTRO DE CONTROLE')
        st.markdown('<p style="color: #9fb3c8; font-size: 0.8rem; margin-bottom: 30px; letter-spacing: 1.5px; opacity: 0.7;">AUTENTICAÇÃO EXCLUSIVA</p>', unsafe_allow_html=True)
        
        user = st.text_input("Matrícula", placeholder="C000000", key="login_user")
        pwd = st.text_input("Senha", type="password", placeholder="••••••••", key="login_pwd")
        
        if st.button("ACESSAR SISTEMA"):
            if not user or not pwd:
                st.warning("Preencha todos os campos.")
            else:
                user_data = db_manager.verificar_login(user, pwd)
                if user_data:
                    matricula, nome, nivel, is_provisional = user_data
                    
                    # Gera um TOKEN REAL de persistência no Banco de Dados
                    session_token = db_manager.gerar_token_sessao(matricula)
                    if session_token:
                        # Passamos o token instantaneamente para o dashboard.py via session_state (100% seguro contra reruns)
                        st.session_state['login_token_ready'] = session_token
                        st.rerun()
                else:
                    st.error("Credenciais inválidas.")
        
        st.markdown('<p style="font-size: 0.6rem; color: #4b5563; margin-top: 40px; letter-spacing: 4px; opacity: 0.5;">PROGRAMAÇÃO MT • v1.5</p>', unsafe_allow_html=True)



def change_password_screen():
    """Tela para troca de senha obrigatória (primeiro acesso) ou manual."""
    import db_manager
    st.markdown("### 🔑 Atualização de Segurança")
    st.info("Detectamos que este é seu primeiro acesso ou sua senha foi resetada. Por favor, defina uma nova senha.")
    
    with st.form("change_pwd_form"):
        new_pwd = st.text_input("Nova Senha", type="password")
        conf_pwd = st.text_input("Confirme a Nova Senha", type="password")
        submit = st.form_submit_button("SALVAR NOVA SENHA")
        
        if submit:
            if len(new_pwd) < 4:
                st.error("A senha deve ter pelo menos 4 caracteres.")
            elif new_pwd != conf_pwd:
                st.error("As senhas não coincidem.")
            else:
                result = db_manager.atualizar_senha(st.session_state.user_matricula, new_pwd)
                if result:
                    st.success("Senha atualizada com sucesso!")
                    st.session_state.senha_provisoria = False
                    st.rerun()
                else:
                    st.error("Erro ao atualizar senha no banco de dados.")
