import streamlit as st
import threading
import time
from datetime import datetime
from iqoptionapi.stable_api import IQ_Option

# ──────────────────────────────────────────
# CONFIGURAÇÕES FIXAS DO ADMIN (VOCÊ)
# ──────────────────────────────────────────
ADMIN_API_ID = 22453120
ADMIN_API_HASH = "89826a4104518e9ed650cdb451ad8b53"
CANAL_SINAIS = -1004375564920

# Configuração Visual do Streamlit (Tema Dark Automático)
st.set_page_config(
    page_title="Quantum Cloud | Portal do Aluno", 
    page_icon="⚛️", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS Personalizado para ficar igual BotCloud/Dashboard
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stMetric label { color: #808495 !important; font-size: 0.9rem; }
    .stMetric div { color: #fafafa !important; font-weight: bold; }
    section[data-testid="stSidebar"] { background-color: #161b22; }
    h1, h2, h3 { color: #ffffff; }
    .stButton button { background-color: #00d084; color: white; border-radius: 8px; }
    .stTextInput > div > div > input { background-color: #21262d; color: white; border: 1px solid #30363d; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────
# LÓGICA DE CONEXÃO (IQ OPTION)
# ──────────────────────────────────────────

def conectar_aluno(dados):
    try:
        dados['status'] = "🔄 Conectando ao servidor..."
        api = IQ_Option(dados['email'], dados['senha'])
        check, reason = api.connect()
        
        if not check:
            dados['status'] = f"❌ Falha: {reason}"
            return

        api.change_balance(dados['conta'])
        dados['api'] = api
        dados['saldo'] = api.get_balance()
        dados['status'] = "🟢 Online | Aguardando Sinais"
        
        while dados['ativo']:
            time.sleep(5)
            try: dados['saldo'] = api.get_balance()
            except: pass
            
    except Exception as e:
        dados['status'] = f"⚠️ Erro: {str(e)}"

# ──────────────────────────────────────────
# INTERFACE PRINCIPAL
# ──────────────────────────────────────────

if 'bot_ativo' not in st.session_state:
    st.session_state.bot_ativo = False
    st.session_state.dados = {"status": "Desconectado", "saldo": 0.0, "lucro_dia": 0.0}

# Cabeçalho
col_logo, col_status = st.columns([1, 4])
with col_logo:
    st.title("⚛️ QUANTUM CLOUD")
with col_status:
    st.markdown(f"**Canal:** `{CANAL_SINAIS}` | **Admin API:** `{ADMIN_API_ID}`")

if not st.session_state.bot_ativo:
    with st.container(border=True):
        st.header("🔐 Acesso à Conta")
        c1, c2 = st.columns(2)
        with c1:
            email = st.text_input("E-mail IQ Option", placeholder="seu@email.com")
            senha = st.text_input("Senha", type="password", placeholder="••••••••")
        with c2:
            conta = st.selectbox("Ambiente", ["PRACTICE", "REAL"])
            
        st.divider()
        st.subheader("⚙️ Parâmetros de Operação")
        c3, c4, c5, c6 = st.columns(4)
        with c3: entrada = st.number_input("Entrada (R$)", value=5.0)
        with c4: mult = st.number_input("Multiplicador", value=2.0)
        with c5: gales = st.number_input("Máx. Gales", value=1)
        with c6: exp = st.number_input("Expiração (min)", value=1)
        
        c7, c8 = st.columns(2)
        with c7: sw = st.number_input("Stop Win (R$)", value=50.0)
        with c8: sl = st.number_input("Stop Loss (R$)", value=50.0)

        if st.button("🚀 INICIAR SISTEMA", use_container_width=True):
            if email and senha:
                st.session_state.dados = {
                    "email": email, "senha": senha, "conta": conta,
                    "entrada": entrada, "multiplicador": mult, "max_gales": gales,
                    "expiracao": exp, "stop_win": sw, "stop_loss": sl,
                    "status": "Iniciando...", "saldo": 0.0, "lucro_dia": 0.0, "ativo": True
                }
                st.session_state.bot_ativo = True
                t = threading.Thread(target=conectar_aluno, args=(st.session_state.dados,))
                t.daemon = True
                t.start()
                st.rerun()
else:
    # Dashboard Ativo
    d = st.session_state.dados
    
    # Métricas Principais
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💰 Saldo Atual", f"R$ {d['saldo']:.2f}")
    m2.metric("📈 Lucro Hoje", f"R$ {d['lucro_dia']:.2f}", delta=f"{d['lucro_dia']:.2f}")
    m3.metric("🎯 Status", d['status'])
    m4.metric("⚡ Sinal Atual", "Aguardando...")

    # Área de Logs/Histórico
    st.divider()
    st.subheader("📜 Histórico de Operações")
    
    # Tabela simulada de operações
    st.dataframe({
        "Horário": ["--:--", "--:--", "--:--"],
        "Ativo": ["EUR/USD", "GBP/JPY", "USD/CAD"],
        "Direção": ["CALL", "PUT", "CALL"],
        "Resultado": ["WIN", "LOSS", "WIN"],
        "Lucro": ["+R$ 4.55", "-R$ 5.00", "+R$ 4.55"]
    }, hide_index=True, use_container_width=True)

    if st.button("🛑 PARAR SISTEMA", use_container_width=True, type="primary"):
        st.session_state.bot_ativo = False
        st.session_state.dados['ativo'] = False
        st.rerun()

st.caption("© 2026 Quantum Cloud System | Powered by Admin API")
