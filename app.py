import streamlit as st
import asyncio
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

# ──────────────────────────────────────────
# LÓGICA DO BOT COM GESTÃO DE RISCO
# ──────────────────────────────────────────

def executar_entrada(api, ativo, direcao, expiracao, valor_base, multiplicador, max_gales):
    """Realiza a entrada com lógica de Gale."""
    tentativa = 0
    while tentativa <= max_gales:
        valor_atual = round(valor_base * (multiplicador ** tentativa), 2)
        
        # Tenta enviar a ordem
        check, id_op = api.buy(valor_atual, ativo, direcao, expiracao)
        
        if not check:
            return False, "Ordem rejeitada", 0
        
        # Aguarda o resultado (check_win_v3 é bloqueante, mas necessário aqui)
        status, lucro = api.check_win_v3(id_op)
        
        if status == "win":
            return True, "WIN", lucro
        elif status in ["loose", "loss"]:
            tentativa += 1
            if tentativa > max_gales:
                return False, "LOSS (Sem mais gales)", -valor_atual
        else:
            return False, "EQUAL/ERRO", 0
            
    return False, "FALHA", 0

def rodar_bot_aluno(dados_aluno):
    """Thread principal que conecta e opera."""
    try:
        dados_aluno['status'] = "Conectando à IQ Option..."
        api = IQ_Option(dados_aluno['email'], dados_aluno['senha'])
        check, reason = api.connect()
        
        if not check:
            dados_aluno['status'] = f"❌ Erro IQ: {reason}"
            return

        api.change_balance(dados_aluno['conta'])
        saldo_inicial = api.get_balance()
        dados_aluno['saldo'] = saldo_inicial
        dados_aluno['lucro_dia'] = 0.0
        dados_aluno['status'] = "✅ Bot Ativo! Monitorando canal..."

        # Loop principal de monitoramento (Simulado para não travar o WebSocket)
        while dados_aluno['ativo']:
            # Verifica Stops Globais
            if dados_aluno['lucro_dia'] >= dados_aluno['stop_win']:
                dados_aluno['status'] = "🏆 Stop Win Atingido!"
                dados_aluno['ativo'] = False
                break
            
            if dados_aluno['lucro_dia'] <= -dados_aluno['stop_loss']:
                dados_aluno['status'] = "🛑 Stop Loss Atingido!"
                dados_aluno['ativo'] = False
                break

            # Simulação de detecção de sinal (Substitua pela sua lógica de Telegram real)
            # Aqui estamos apenas mantendo a conexão viva e atualizando o saldo
            time.sleep(10)
            dados_aluno['saldo'] = api.get_balance()
            
    except Exception as e:
        dados_aluno['status'] = f"⚠️ Erro Crítico: {str(e)}"

# ──────────────────────────────────────────
# INTERFACE DO USUÁRIO (STREAMLIT)
# ──────────────────────────────────────────

st.set_page_config(page_title="Quantum IQ Bot - Gestão de Risco", layout="centered")
st.title("⚛️ Quantum IQ Bot - Portal do Aluno")

if 'bot_ativo' not in st.session_state:
    st.session_state.bot_ativo = False
    st.session_state.dados = {"status": "Parado", "saldo": 0.0, "lucro_dia": 0.0}

with st.form("config_form"):
    st.header("🔐 Configurações da Conta")
    col1, col2 = st.columns(2)
    with col1:
        email = st.text_input("E-mail IQ Option")
        senha = st.text_input("Senha", type="password")
    with col2:
        conta = st.selectbox("Tipo de Conta", ["PRACTICE", "REAL"])
    
    st.header("⚙️ Gestão de Risco e Estratégia")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        entrada = st.number_input("Entrada (R$)", value=5.0)
    with c2:
        multiplicador = st.number_input("Multiplicador Gale", value=2.0)
    with c3:
        max_gales = st.number_input("Máx. Gales", value=1, min_value=0, max_value=5)
    with c4:
        expiracao = st.number_input("Expiração (Min)", value=1)

    c5, c6 = st.columns(2)
    with c5:
        stop_win = st.number_input("Stop Win (R$)", value=50.0)
    with c6:
        stop_loss = st.number_input("Stop Loss (R$)", value=50.0)

    submitted = st.form_submit_button("🚀 INICIAR BOT AUTOMÁTICO")

if submitted:
    if email and senha:
        st.session_state.dados = {
            "email": email, "senha": senha, "conta": conta,
            "entrada": entrada, "multiplicador": multiplicador, 
            "max_gales": max_gales, "expiracao": expiracao,
            "stop_win": stop_win, "stop_loss": stop_loss,
            "status": "Iniciando...", "saldo": 0.0, "lucro_dia": 0.0,
            "ativo": True
        }
        st.session_state.bot_ativo = True
        
        t = threading.Thread(target=rodar_bot_aluno, args=(st.session_state.dados,))
        t.daemon = True
        t.start()
        st.rerun()

# Painel de Status em Tempo Real
if st.session_state.bot_ativo:
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Status", st.session_state.dados['status'])
    with col2:
        st.metric("Saldo Atual", f"R$ {st.session_state.dados['saldo']:.2f}")
    with col3:
        st.metric("Lucro do Dia", f"R$ {st.session_state.dados['lucro_dia']:.2f}")
    
    if st.button("🛑 Parar Operação"):
        st.session_state.bot_ativo = False
        st.session_state.dados['ativo'] = False
        st.session_state.dados['status'] = "Parado pelo usuário"
        st.rerun()
else:
    st.warning("⚠️ Configure seus dados e gestão de risco acima para começar.")

st.caption(f"Canal Admin: {CANAL_SINAIS} | API ID: {ADMIN_API_ID}")
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
