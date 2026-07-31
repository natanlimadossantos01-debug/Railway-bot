import streamlit as st
import threading
import time
import re
from datetime import datetime
from iqoptionapi.stable_api import IQ_Option
from telethon import TelegramClient, events

# ──────────────────────────────────────────
# CONFIGURAÇÕES FIXAS DO ADMIN (VOCÊ)
# ──────────────────────────────────────────
ADMIN_API_ID = 22453120
ADMIN_API_HASH = "89826a4104518e9ed650cdb451ad8b53"
CANAL_SINAIS = -1004375564920

# CSS para Visual BotCloud
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stMetric label { color: #808495 !important; }
    .stButton button { background-color: #00d084; color: white; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="Quantum Cloud", layout="wide")
st.title("⚛️ QUANTUM CLOUD SYSTEM")

if 'bot_ativo' not in st.session_state:
    st.session_state.bot_ativo = False
    st.session_state.dados = {"status": "Parado", "saldo": 0.0, "lucro_dia": 0.0}

def parser_sinal(texto):
    """Extrai dados do sinal baseado no padrão da sua sala."""
    t = texto.upper()
    ativo = re.search(r'PAR[:\s]+([A-Z0-9\/\-]+)', t)
    direcao = "call" if "COMPRA" in t or "CALL" in t else "put" if "VENDA" in t or "PUT" in t else None
    horario = re.search(r'HOR[AÁ]RIO.*?(\d{1,2}:\d{2})', t)
    
    if ativo and direcao:
        return {
            "ativo": ativo.group(1).replace("/", "").replace("-", ""),
            "direcao": direcao,
            "horario": horario.group(1) if horario else None
        }
    return None

def rodar_sistema(dados):
    try:
        dados['status'] = "🔄 Conectando à IQ Option..."
        api = IQ_Option(dados['email'], dados['senha'])
        
        # Tenta conectar com timeout
        check, reason = api.connect()
        if not check:
            dados['status'] = f"❌ Erro IQ: {reason}"
            return

        api.change_balance(dados['conta'])
        dados['saldo'] = api.get_balance()
        dados['api'] = api
        dados['status'] = "🟢 Online | Escutando Canal..."

        # Inicia o Listener do Telegram em uma Thread separada
        def listener_telegram():
            client = TelegramClient("session_cloud", ADMIN_API_ID, ADMIN_API_HASH)
            async def handler(event):
                sinal = parser_sinal(event.message.text)
                if sinal:
                    dados['ultimo_sinal'] = f"📡 {sinal['ativo']} {sinal['direcao'].upper()}"
                    # Aqui entraria a chamada api.buy() quando o horário chegar
            
            with client:
                client.on(events.NewMessage(chats=CANAL_SINAIS))(handler)
                client.run_until_disconnected()

        t_tel = threading.Thread(target=listener_telegram)
        t_tel.daemon = True
        t_tel.start()

        while dados['ativo']:
            time.sleep(2)
            try: dados['saldo'] = api.get_balance()
            except: pass

    except Exception as e:
        dados['status'] = f"⚠️ Erro: {str(e)}"

# Interface
if not st.session_state.bot_ativo:
    with st.container(border=True):
        email = st.text_input("E-mail IQ Option")
        senha = st.text_input("Senha", type="password")
        conta = st.selectbox("Conta", ["PRACTICE", "REAL"])
        if st.button("🚀 INICIAR SISTEMA"):
            if email and senha:
                st.session_state.dados = {"email": email, "senha": senha, "conta": conta, 
                                          "status": "Iniciando...", "saldo": 0.0, "ativo": True, "ultimo_sinal": "-"}
                st.session_state.bot_ativo = True
                threading.Thread(target=rodar_sistema, args=(st.session_state.dados,), daemon=True).start()
                st.rerun()
else:
    d = st.session_state.dados
    m1, m2, m3 = st.columns(3)
    m1.metric("💰 Saldo", f"R$ {d['saldo']:.2f}")
    m2.metric("🎯 Status", d['status'])
    m3.metric("⚡ Último Sinal", d.get('ultimo_sinal', '-'))
    
    if st.button("🛑 PARAR"):
        st.session_state.bot_ativo = False
        st.session_state.dados['ativo'] = False
        st.rerun()
