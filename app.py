import streamlit as st
import threading
import time
import re
import os
from datetime import datetime
from iqoptionapi.stable_api import IQ_Option
from telethon import TelegramClient, events

# ──────────────────────────────────────────
# CONFIGURAÇÕES DO ADMIN (VOCÊ)
# ──────────────────────────────────────────
# Dica: No Railway, coloque essas chaves em 'Variables' para mais segurança
ADMIN_API_ID = int(os.getenv("TELEGRAM_API_ID", "22453120"))
ADMIN_API_HASH = os.getenv("TELEGRAM_API_HASH", "89826a4104518e9ed650cdb451ad8b53")
CANAL_SINAIS = int(os.getenv("CANAL_ID", "-1004375564920"))

# ──────────────────────────────────────────
# ESTILO VISUAL BOTCLOUD (CSS)
# ──────────────────────────────────────────
st.set_page_config(page_title="Quantum Cloud | Pro", layout="wide", page_icon="⚛️")

st.markdown("""
<style>
    .main { background-color: #0e1117; padding-top: 2rem; }
    .stMetric label { color: #8b949e !important; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px; }
    .stMetric div[data-testid="stMetricValue"] { color: #ffffff !important; font-weight: 700; font-size: 1.5rem; }
    .stButton button { 
        background: linear-gradient(90deg, #00d084 0%, #00a86b 100%); 
        color: white; border: none; border-radius: 6px; padding: 0.75rem 1rem; font-weight: bold; 
    }
    .stTextInput > div > div > input { background-color: #161b22; color: white; border: 1px solid #30363d; border-radius: 6px; }
    section[data-testid="stSidebar"] { background-color: #0d1117; }
    h1 { color: #ffffff; font-weight: 800; letter-spacing: -1px; }
    .status-box { padding: 1rem; border-radius: 8px; background-color: #161b22; border: 1px solid #30363d; margin-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)

st.title("⚛️ QUANTUM CLOUD SYSTEM")
st.caption(f"Admin API: {ADMIN_API_ID} | Canal Monitorado: {CANAL_SINAIS}")

# ──────────────────────────────────────────
# LÓGICA DO PARSER E OPERAÇÃO
# ──────────────────────────────────────────

def parser_sinal(texto):
    """Extrai Ativo, Direção e Horário do texto do canal."""
    t = texto.upper()
    # Tenta encontrar padrões comuns: EUR/USD, OTC, etc.
    ativo_match = re.search(r'(?:PAR|ATIVO|ASSET)[:\s]*([A-Z0-9\/\-]+(?:OTC)?)', t)
    
    direcao = None
    if "COMPRA" in t or "CALL" in t or "ACIMA" in t: direcao = "call"
    elif "VENDA" in t or "PUT" in t or "ABAIXO" in t: direcao = "put"
    
    horario_match = re.search(r'HOR[AÁ]RIO.*?(\d{1,2}:\d{2})', t)
    
    if ativo_match and direcao:
        return {
            "ativo": ativo_match.group(1).replace("/", "").replace("-", ""),
            "direcao": direcao,
            "horario": horario_match.group(1) if horario_match else None
        }
    return None

def executar_ordem(api, sinal, dados_aluno):
    """Realiza a entrada com gestão de Gale."""
    try:
        ativo = sinal['ativo']
        direcao = sinal['direcao']
        exp = dados_aluno['expiracao']
        valor_base = dados_aluno['entrada']
        mult = dados_aluno['multiplicador']
        max_gales = dados_aluno['max_gales']
        
        tentativa = 0
        while tentativa <= max_gales:
            valor_atual = round(valor_base * (mult ** tentativa), 2)
            
            # Verifica Stop Loss antes de cada entrada
            if dados_aluno['lucro_dia'] <= -dados_aluno['stop_loss']:
                dados_aluno['status'] = "🛑 Stop Loss Atingido"
                return

            check, id_op = api.buy(valor_atual, ativo, direcao, exp)
            
            if check:
                status, lucro = api.check_win_v3(id_op)
                
                if status == "win":
                    dados_aluno['lucro_dia'] += lucro
                    dados_aluno['historico'].append(f"✅ WIN | {ativo} | +R$ {lucro:.2f}")
                    return
                elif status in ["loose", "loss"]:
                    dados_aluno['lucro_dia'] -= valor_atual
                    dados_aluno['historico'].append(f"❌ LOSS | {ativo} | -R$ {valor_atual:.2f}")
                    tentativa += 1
                else:
                    dados_aluno['historico'].append(f"〰️ EQUAL | {ativo}")
                    return
            else:
                dados_aluno['status'] = "❌ Ordem Rejeitada"
                return
                
    except Exception as e:
        dados_aluno['status'] = f"⚠️ Erro na Operação: {str(e)}"

def rodar_bot_completo(dados):
    """Thread principal que conecta IQ e escuta Telegram."""
    try:
        # 1. Conexão IQ Option
        dados['status'] = "🔄 Conectando à Corretora..."
        api = IQ_Option(dados['email'], dados['senha'])
        check, reason = api.connect()
        
        if not check:
            dados['status'] = f"❌ Falha IQ: {reason}"
            return

        api.change_balance(dados['conta'])
        dados['api'] = api
        dados['saldo'] = api.get_balance()
        dados['status'] = "🟢 Online | Escutando Sinais..."

        # 2. Conexão Telegram (Listener)
        async def handler(event):
            sinal = parser_sinal(event.message.text)
            if sinal:
                dados['ultimo_sinal'] = f"📡 {sinal['ativo']} ({sinal['direcao'].upper()})"
                # Executa a ordem na thread principal
                executar_ordem(api, sinal, dados)

        client = TelegramClient("session_railway", ADMIN_API_ID, ADMIN_API_HASH)
        
        with client:
            client.on(events.NewMessage(chats=CANAL_SINAIS))(handler)
            # Mantém o listener rodando enquanto o bot estiver ativo
            while dados['ativo']:
                time.sleep(1)
                try: 
                    dados['saldo'] = api.get_balance()
                    # Verifica Stop Win
                    if dados['lucro_dia'] >= dados['stop_win']:
                        dados['status'] = "🏆 Stop Win Batido!"
                        dados['ativo'] = False
                except: pass

    except Exception as e:
        dados['status'] = f"⚠️ Erro Crítico: {str(e)}"

# ──────────────────────────────────────────
# INTERFACE DO USUÁRIO
# ──────────────────────────────────────────

if 'bot_ativo' not in st.session_state:
    st.session_state.bot_ativo = False
    st.session_state.dados = {"status": "Parado", "saldo": 0.0, "lucro_dia": 0.0, "historico": []}

d = st.session_state.dados

if not st.session_state.bot_ativo:
    with st.container(border=True):
        st.header("🔐 Configuração da Conta")
        c1, c2 = st.columns(2)
        with c1:
            email = st.text_input("E-mail IQ Option", key="email_in")
            senha = st.text_input("Senha", type="password", key="pass_in")
        with c2:
            conta = st.selectbox("Ambiente", ["PRACTICE", "REAL"], key="acc_in")
        
        st.divider()
        st.subheader("⚙️ Parâmetros de Risco")
        c3, c4, c5 = st.columns(3)
        with c3: entrada = st.number_input("Entrada (R$)", value=5.0, key="ent_in")
        with c4: mult = st.number_input("Multiplicador", value=2.0, key="mult_in")
        with c5: gales = st.number_input("Máx. Gales", value=1, key="gale_in")
        
        c6, c7 = st.columns(2)
        with c6: sw = st.number_input("Stop Win (R$)", value=50.0, key="sw_in")
        with c7: sl = st.number_input("Stop Loss (R$)", value=50.0, key="sl_in")

        if st.button("🚀 INICIAR SISTEMA AUTOMÁTICO"):
            if email and senha:
                st.session_state.dados = {
                    "email": email, "senha": senha, "conta": conta,
                    "entrada": entrada, "multiplicador": mult, "max_gales": gales,
                    "expiracao": 1, "stop_win": sw, "stop_loss": sl,
                    "status": "Iniciando...", "saldo": 0.0, "lucro_dia": 0.0, 
                    "ativo": True, "ultimo_sinal": "-", "historico": []
                }
                st.session_state.bot_ativo = True
                threading.Thread(target=rodar_bot_completo, args=(st.session_state.dados,), daemon=True).start()
                st.rerun()
else:
    # Dashboard Ativo
    m1, m2, m3 = st.columns(3)
    m1.metric("💰 Saldo Atual", f"R$ {d['saldo']:.2f}")
    m2.metric("📈 Lucro Diário", f"R$ {d['lucro_dia']:.2f}", delta=f"{d['lucro_dia']:.2f}")
    m3.metric("🎯 Status", d['status'])
    
    st.info(f"**Último Sinal Capturado:** {d.get('ultimo_sinal', 'Nenhum ainda')}")
    
    st.divider()
    st.subheader("📜 Histórico de Operações")
    for op in reversed(d['historico'][-10:]):
        st.markdown(f"`{op}`")

    if st.button("🛑 PARAR SISTEMA"):
        st.session_state.bot_ativo = False
        st.session_state.dados['ativo'] = False
        st.session_state.dados['status'] = "Parado pelo Usuário"
        st.rerun()

st.caption("© 2026 Quantum Cloud System | Powered by Railway")
