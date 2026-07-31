import streamlit as st
import asyncio
import threading
import time
from datetime import datetime
from iqoptionapi.stable_api import IQ_Option
from telethon import TelegramClient, events

# ──────────────────────────────────────────
# CONFIGURAÇÕES FIXAS DO ADMIN (VOCÊ)
# ──────────────────────────────────────────
ADMIN_API_ID = 22453120
ADMIN_API_HASH = "89826a4104518e9ed650cdb451ad8b53"
CANAL_SINAIS = -1004375564920

# ──────────────────────────────────────────
# LÓGICA DO BOT (RODA EM SEGUNDO PLANO)
# ──────────────────────────────────────────

def iniciar_bot_aluno(dados_aluno):
    """Função que conecta na IQ do aluno e escuta o seu canal."""
    try:
        # 1. Conecta na IQ Option do Aluno
        api = IQ_Option(dados_aluno['email'], dados_aluno['senha'])
        check, reason = api.connect()
        
        if not check:
            dados_aluno['status'] = f"❌ Erro IQ: {reason}"
            return

        api.change_balance(dados_aluno['conta'])
        dados_aluno['saldo'] = api.get_balance()
        dados_aluno['status'] = "✅ Bot Ativo! Aguardando sinais..."

        # 2. Conecta no Telegram com SUAS credenciais para ouvir o canal
        async def listener():
            client = TelegramClient("session_temp", ADMIN_API_ID, ADMIN_API_HASH)
            await client.start()
            
            @client.on(events.NewMessage(chats=CANAL_SINAIS))
            async def handler(event):
                texto = event.message.text or ""
                # Aqui entraria seu parser de sinal original
                if "SINAL" in texto.upper():
                    dados_aluno['ultimo_sinal'] = f"📡 Sinal detectado às {datetime.now().strftime('%H:%M')}"
                    # Simulação de operação (substitua pela sua lógica de buy/put)
                    # api.buy(...) 
            
            await client.run_until_disconnected()

        # Roda o listener em um loop de eventos separado
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(listener())

    except Exception as e:
        dados_aluno['status'] = f"⚠️ Erro: {str(e)}"

# ──────────────────────────────────────────
# INTERFACE DO USUÁRIO (STREAMLIT)
# ──────────────────────────────────────────

st.set_page_config(page_title="Quantum IQ Bot - Acesso Aluno", layout="centered")
st.title("⚛️ Quantum IQ Bot - Portal do Aluno")

if 'bot_ativo' not in st.session_state:
    st.session_state.bot_ativo = False
    st.session_state.dados = {"status": "Parado", "saldo": 0.0, "ultimo_sinal": "-"}

with st.form("login_form"):
    st.header("🔐 Suas Credenciais IQ Option")
    email = st.text_input("E-mail da Conta")
    senha = st.text_input("Senha", type="password")
    conta = st.selectbox("Tipo de Conta", ["PRACTICE", "REAL"])
    
    col1, col2 = st.columns(2)
    with col1:
        entrada = st.number_input("Valor Entrada (R$)", value=5.0)
    with col2:
        stop_win = st.number_input("Stop Win (R$)", value=50.0)

    submitted = st.form_submit_button("🚀 INICIAR BOT AUTOMÁTICO")

if submitted:
    if email and senha:
        st.session_state.dados = {
            "email": email, "senha": senha, "conta": conta,
            "entrada": entrada, "stop_win": stop_win,
            "status": "Iniciando conexão...", "saldo": 0.0, "ultimo_sinal": "-"
        }
        st.session_state.bot_ativo = True
        
        # Inicia a Thread do Bot
        t = threading.Thread(target=iniciar_bot_aluno, args=(st.session_state.dados,))
        t.daemon = True
        t.start()
        st.rerun()

# Painel de Status
if st.session_state.bot_ativo:
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Status do Bot", st.session_state.dados['status'])
        st.metric("Saldo Atual", f"R$ {st.session_state.dados['saldo']:.2f}")
    with col2:
        st.info(f"Último Evento: {st.session_state.dados['ultimo_sinal']}")
    
    if st.button("🛑 Parar Operação"):
        st.session_state.bot_ativo = False
        st.session_state.dados['status'] = "Parado pelo usuário"
        st.rerun()
else:
    st.warning("⚠️ Preencha seus dados acima para começar a operar.")

st.caption("Canal de Sinais: Quantum VIP (Admin) | Execução: Conta do Aluno")
