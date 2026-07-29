#!/usr/bin/env python3
"""
🤖 QUANTUM IA V2 - Bot Telegram Multi-Usuário
⚡ Versão Assíncrona Otimizada para Cloud
📦 Usa iqoption-async (mais estável)
"""

import asyncio
import logging
import os
import sqlite3
import time
import json
import numpy as np
from datetime import datetime, timedelta, timezone
from collections import deque
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)

# ═══════════════════════════════════════════
# CONFIGURAÇÕES
# ═══════════════════════════════════════════
FUSO_BR = timezone(timedelta(hours=-3))
os.environ['TZ'] = 'America/Sao_Paulo'
time.tzset()

BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))
DB_PATH = "quantum_users.db"

if not BOT_TOKEN:
    print("❌ Configure BOT_TOKEN no Railway!")
    exit(1)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# BANCO DE DADOS
# ═══════════════════════════════════════════
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            iq_email TEXT DEFAULT '',
            iq_senha TEXT DEFAULT '',
            iq_conta TEXT DEFAULT 'PRACTICE',
            valor_entrada REAL DEFAULT 2.0,
            multiplicador REAL DEFAULT 2.0,
            max_gales INTEGER DEFAULT 1,
            stop_loss REAL DEFAULT 0,
            stop_win REAL DEFAULT 0,
            bot_ligado INTEGER DEFAULT 0,
            conectado INTEGER DEFAULT 0,
            saldo REAL DEFAULT 0,
            ativo INTEGER DEFAULT 1,
            cadastro TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            data TEXT,
            ativo TEXT,
            direcao TEXT,
            valor REAL,
            resultado TEXT,
            lucro REAL
        );
    """)
    conn.execute("INSERT OR IGNORE INTO users (user_id, first_name, ativo, cadastro) VALUES (?, 'Admin', 1, datetime('now','localtime'))", (ADMIN_ID,))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    cols = [d[0] for d in c.description] if c.description else []
    conn.close()
    return dict(zip(cols, row)) if row else None

def criar_usuario(user_id, username, first_name):
    now_str = datetime.now(FUSO_BR).strftime("%Y-%m-%d %H:%M:%S")
    if not first_name: first_name = f"User{user_id}"
    if not username: username = f"user_{user_id}"
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO users (user_id, username, first_name, ativo, cadastro) VALUES (?,?,?,1,?)",
                 (user_id, username, first_name, now_str))
    conn.commit()
    conn.close()
    logger.info(f"✅ Usuário criado: {user_id} ({first_name})")

def atualizar_user(user_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [user_id]
    conn.execute(f"UPDATE users SET {sets} WHERE user_id=?", vals)
    conn.commit()
    conn.close()

def desativar_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET ativo=0, bot_ligado=0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def user_ativo(user_id):
    u = get_user(user_id)
    return bool(u and u.get('ativo', 1))

def listar_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, username, first_name, ativo, bot_ligado, saldo, iq_email FROM users ORDER BY cadastro DESC")
    rows = []
    for r in c.fetchall():
        rows.append({"id": r[0], "user": r[1] or "", "nome": r[2] or f"User{r[0]}", "ativo": r[3], "bot": r[4], "saldo": r[5] or 0, "email": r[6] or ""})
    conn.close()
    return rows

def salvar_trade(user_id, ativo, direcao, valor, resultado, lucro):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO trades (user_id, data, ativo, direcao, valor, resultado, lucro) VALUES (?,?,?,?,?,?,?)",
                 (user_id, datetime.now(FUSO_BR).strftime("%Y-%m-%d %H:%M:%S"), ativo, direcao, valor, resultado, lucro))
    conn.commit()
    conn.close()

def resultado_dia(user_id):
    hoje = datetime.now(FUSO_BR).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT COUNT(*), SUM(CASE WHEN resultado='win' THEN 1 ELSE 0 END), 
                        SUM(CASE WHEN resultado='loss' THEN 1 ELSE 0 END), SUM(lucro) 
                 FROM trades WHERE user_id=? AND data LIKE ?""", (user_id, f"{hoje}%"))
    t, w, l, lc = c.fetchone()
    conn.close()
    return {"total": t or 0, "wins": w or 0, "losses": l or 0, "lucro": lc or 0.0}

# ═══════════════════════════════════════════
# 5 ESTRATÉGIAS (OTIMIZADAS)
# ═══════════════════════════════════════════
class Mortalha:
    def sma(self, d, p):
        try:
            if len(d)>=p: return sum(d[-p:])/p
            return sum(d)/len(d) if d else 0
        except: return 0
    def wma(self, d, p):
        try:
            if len(d)<p: return sum(d)/len(d) if d else 0
            w=np.arange(1, p+1); return np.sum(np.array(d[-p:])*w)/np.sum(w)
        except: return 0
    def analisar(self, v):
        try:
            if len(v)<30: return None, 0
            c=np.array([x['close'] for x in v]); b1=np.zeros(len(c))
            for i in range(len(c)):
                if i>=33: b1[i]=self.sma(c[:i+1], 1)-self.sma(c[:i+1], 34)
            b2=np.zeros(len(b1))
            for i in range(len(b1)):
                if i>=3: b2[i]=self.wma(b1[:i+1], 4)
            if b1[-1]>b2[-1] and b1[-2]<=b2[-2]: return'CALL', min(45+abs(b1[-1]-b2[-1])*10000, 90)
            if b1[-1]<b2[-1] and b1[-2]>=b2[-2]: return'PUT', min(45+abs(b1[-1]-b2[-1])*10000, 90)
            return None, 0
        except: return None, 0

class Formiga:
    def ema(self, p, pe):
        try:
            if len(p)<pe: return sum(p)/len(p) if p else 0
            return np.mean(p[-pe:])
        except: return 0
    def analisar(self, v):
        try:
            if len(v)<15: return None, 0
            precos=np.array([x['close'] for x in v])
            ema5=self.ema(precos, 5); ema10=self.ema(precos, 10)
            dif=((ema5-ema10)/ema10)*100 if ema10>0 else 0
            sc=sp=0
            if dif>0.02: sc+=3
            elif dif>0.005: sc+=1
            elif dif<-0.02: sp+=3
            elif dif<-0.005: sp+=1
            if sc>=2 and sc>sp: return'CALL', min(50+sc*4, 85)
            if sp>=2 and sp>sc: return'PUT', min(50+sp*4, 85)
            return None, 0
        except: return None, 0

class Fortaleza:
    def rsi(self, p, pe=7):
        try:
            if len(p)<pe+1: return 50
            d=np.diff(list(p[-pe-1:])); g=np.where(d>0, d, 0); l=np.where(d<0, -d, 0)
            mg=np.mean(g) if len(g)>0 else 0; mp=np.mean(l) if len(l)>0 else 0
            if mp==0: return 100
            return 100-(100/(1+mg/mp))
        except: return 50
    def analisar(self, v):
        try:
            if len(v)<18: return None, 0
            precos=np.array([x['close'] for x in v])
            rsi_val=self.rsi(precos)
            m=np.mean(precos[-10:]) if len(precos)>=10 else np.mean(precos)
            s=np.std(precos[-10:]) if len(precos)>=10 else 0
            bs=m+2*s; bi=m-2*s
            sc=sp=0
            if rsi_val<30: sc+=3
            elif rsi_val<40: sc+=2
            if rsi_val>70: sp+=3
            elif rsi_val>60: sp+=2
            if precos[-1]<=bi*1.0004: sc+=3
            if precos[-1]>=bs*0.9996: sp+=3
            if sc>=4 and sc>sp: return'CALL', min(60+sc*3, 90)
            if sp>=4 and sp>sc: return'PUT', min(60+sp*3, 90)
            return None, 0
        except: return None, 0

class RaioNegro:
    def analisar(self, v):
        try:
            if len(v)<12: return None, 0
            precos=np.array([x['close'] for x in v])
            ema5=np.mean(precos[-5:]) if len(precos)>=5 else precos[-1]
            ema13=np.mean(precos[-13:]) if len(precos)>=13 else ema5
            macd=ema5-ema13; sinal=macd*0.5
            mom=precos[-1]-precos[-3] if len(precos)>=3 else 0
            sc=sp=0
            if macd>sinal and macd>0: sc+=3
            elif macd>sinal: sc+=1
            elif macd<sinal and macd<0: sp+=3
            elif macd<sinal: sp+=1
            if mom>0.00003: sc+=3
            elif mom>0: sc+=1
            elif mom<-0.00003: sp+=3
            elif mom<0: sp+=1
            if sc>=2 and sc>sp: return'CALL', min(48+sc*4, 85)
            if sp>=2 and sp>sc: return'PUT', min(48+sp*4, 85)
            return None, 0
        except: return None, 0

class Tsunami:
    def analisar(self, v):
        try:
            if len(v)<12: return None, 0
            precos=np.array([x['close'] for x in v])
            altas=sum(1 for i in range(-min(5, len(v)-1), 0) if precos[i]>precos[i-1])
            sc=sp=0
            if altas>=3: sc+=3
            elif altas<=2: sp+=3
            if sc>=2 and sc>sp: return'CALL', min(50+sc*3, 85)
            if sp>=2 and sp>sc: return'PUT', min(50+sp*3, 85)
            return None, 0
        except: return None, 0

class QuantumIA:
    def __init__(self):
        self.mortalha=Mortalha(); self.formiga=Formiga(); self.fortaleza=Fortaleza()
        self.raio_negro=RaioNegro(); self.tsunami=Tsunami(); self.min_estrategias=3
    def analisar_completo(self, v):
        try:
            if len(v)<30: return None, 0, 0
            resultados=[]; votos={'CALL':0, 'PUT':0}; confiancas={'CALL':[], 'PUT':[]}
            for est in [self.mortalha, self.formiga, self.fortaleza, self.raio_negro, self.tsunami]:
                try:
                    d, c=est.analisar(v)
                    if d: resultados.append(d); votos[d]+=1; confiancas[d].append(c)
                except: pass
            total=len(resultados)
            if total<self.min_estrategias: return None, 0, total
            if votos['CALL']>=self.min_estrategias and votos['CALL']>votos['PUT']:
                conf=np.mean(confiancas['CALL']); return'CALL', min(conf+(total-3)*4, 95), total
            if votos['PUT']>=self.min_estrategias and votos['PUT']>votos['CALL']:
                conf=np.mean(confiancas['PUT']); return'PUT', min(conf+(total-3)*4, 95), total
            return None, 0, total
        except: return None, 0, 0
    def melhor_par(self, velas_dict, bloqueados):
        melhor=None; melhor_score=0
        for nome, velas in velas_dict.items():
            if nome in bloqueados: continue
            if len(velas)>=30:
                d, cf, num=self.analisar_completo(velas)
                if d:
                    score=cf+(num*5)
                    if score>melhor_score: melhor_score=score; melhor={'ativo': nome, 'direcao': d, 'confianca': cf, 'estrategias': num}
        return melhor

# ═══════════════════════════════════════════
# IQ OPTION API ASSÍNCRONA (NOVA)
# ═══════════════════════════════════════════
class IQAPIAsync:
    def __init__(self, email, senha, conta='PRACTICE'):
        self.email = email
        self.senha = senha
        self.conta = conta
        self.client = None
        self.velas = {nome: deque(maxlen=100) for nome in ["EURUSD","GBPUSD","EURGBP"]}
        self.ok = False
        self.saldo = 0
        self.ativo_map = {"EURUSD": "EURUSD-OTC", "GBPUSD": "GBPUSD-OTC", "EURGBP": "EURGBP-OTC"}
        
    async def conectar(self):
        """Conecta usando iqoption-async"""
        try:
            # Importa a biblioteca assíncrona
            from iqoption_async import IQOptionClient
            
            self.client = IQOptionClient(self.email, self.senha)
            await self.client.connect()
            
            # Verifica conexão
            if self.client.is_connected:
                # Seta conta (PRACTICE ou REAL)
                if self.conta == "PRACTICE":
                    await self.client.change_account("practice")
                else:
                    await self.client.change_account("real")
                
                self.ok = True
                self.saldo = await self.client.get_balance()
                logger.info(f"✅ Conectado IQ: {self.email} | Saldo: ${self.saldo}")
                return True, self.saldo
            
            return False, 0
            
        except Exception as e:
            logger.error(f"❌ Erro conexão IQ: {e}")
            return False, 0

    async def atualizar_velas(self):
        """Atualiza velas de forma assíncrona"""
        if not self.ok or not self.client:
            return
            
        for nome, ativo_id in self.ativo_map.items():
            try:
                # Busca velas de 1 minuto
                velas = await self.client.get_candles(ativo_id, 60, 80)
                
                if velas and len(velas) > 0:
                    self.velas[nome].clear()
                    for x in velas[-80:]:
                        if isinstance(x, dict) or hasattr(x, '__dict__'):
                            # Converte objeto para dict se necessário
                            if hasattr(x, '__dict__'):
                                x = x.__dict__
                            self.velas[nome].append({
                                'time': datetime.fromtimestamp(x.get('from', 0), FUSO_BR),
                                'open': float(x.get('open', 0)),
                                'high': float(x.get('max', 0)),
                                'low': float(x.get('min', 0)),
                                'close': float(x.get('close', 0)),
                                'volume': int(x.get('volume', 0))
                            })
            except Exception as e:
                logger.debug(f"Erro velas {nome}: {e}")
                continue

    async def get_saldo(self):
        """Retorna saldo atualizado"""
        if not self.ok or not self.client:
            return 0
        try:
            self.saldo = await self.client.get_balance()
            return self.saldo
        except:
            return self.saldo

    async def comprar(self, ativo, direcao, exp, valor):
        """Executa compra assíncrona"""
        if not self.ok or not self.client:
            return False, None
            
        ativo_id = self.ativo_map.get(ativo, ativo)
        try:
            # Converte direção para 'call' ou 'put'
            dir_lower = direcao.lower()
            
            # Compra binária com 1 minuto de expiração
            result = await self.client.binary.buy(
                price=valor,
                asset=ativo_id,
                direction=dir_lower,
                duration=exp
            )
            
            if result and result.get('isSuccessful', False):
                order_id = result.get('id')
                logger.info(f"✅ Compra executada: {ativo} {direcao} ${valor}")
                return True, order_id
            else:
                logger.error(f"❌ Falha compra: {result}")
                return False, None
                
        except Exception as e:
            logger.error(f"❌ Erro compra: {e}")
            return False, None

    async def fechar(self):
        """Fecha conexão"""
        if self.client:
            try:
                await self.client.close()
            except:
                pass
            self.ok = False

# ═══════════════════════════════════════════
# MOTOR DE TRADING (VERSÃO ASSÍNCRONA)
# ═══════════════════════════════════════════
user_bots = {}

async def trading_loop(user_id, app):
    """Loop principal de trading - Versão Otimizada"""
    logger.info(f"🔄 Trading loop iniciado para user {user_id}")
    
    # Instância do IQ
    iq = None
    reconectar_count = 0
    sem_sinal_count = 0
    
    while True:
        try:
            # Verifica se usuário ainda está ativo
            user = get_user(user_id)
            if not user:
                break
                
            if not user.get('bot_ligado') or not user.get('ativo', 1):
                logger.info(f"⏹️ Trading loop encerrado para user {user_id}")
                if user_id in user_bots:
                    await user_bots[user_id].fechar()
                    del user_bots[user_id]
                break
            
            # Reconecta se necessário
            if not iq or not iq.ok:
                if reconectar_count > 5:
                    logger.error(f"❌ User {user_id}: falha reconexão, desligando")
                    atualizar_user(user_id, bot_ligado=0)
                    break
                    
                iq = IQAPIAsync(
                    user.get('iq_email', ''), 
                    user.get('iq_senha', ''), 
                    user.get('iq_conta', 'PRACTICE')
                )
                ok, info = await iq.conectar()
                
                if ok:
                    user_bots[user_id] = iq
                    atualizar_user(user_id, conectado=1, saldo=info)
                    reconectar_count = 0
                else:
                    reconectar_count += 1
                    await asyncio.sleep(15)
                    continue
            
            # Atualiza velas
            await iq.atualizar_velas()
            
            # Checa stop loss/win
            res = resultado_dia(user_id)
            sl = user.get('stop_loss', 0)
            sw = user.get('stop_win', 0)
            
            if sl > 0 and res['lucro'] <= -sl:
                await app.bot.send_message(
                    user_id, 
                    f"🛑 *Stop Loss!* R$ {res['lucro']:.2f}", 
                    parse_mode="Markdown"
                )
                atualizar_user(user_id, bot_ligado=0)
                break
            
            if sw > 0 and res['lucro'] >= sw:
                await app.bot.send_message(
                    user_id, 
                    f"🏆 *Stop Win!* R$ {res['lucro']:.2f}", 
                    parse_mode="Markdown"
                )
                atualizar_user(user_id, bot_ligado=0)
                break
            
            # Gera sinal
            qia = QuantumIA()
            sinal = qia.melhor_par(iq.velas, [])
            
            if sinal:
                sem_sinal_count = 0
                logger.info(f"📡 User {user_id}: {sinal['ativo']} {sinal['direcao']} {sinal['confianca']:.0f}%")
                
                await app.bot.send_message(
                    user_id,
                    f"⚛️ *SINAL V2*\n"
                    f"💰 {sinal['ativo']}\n"
                    f"📈 {sinal['direcao']}\n"
                    f"📊 {sinal['confianca']:.0f}%\n"
                    f"🧠 {sinal['estrategias']}/5\n"
                    f"🕐 {datetime.now(FUSO_BR).strftime('%H:%M:%S')}",
                    parse_mode="Markdown"
                )
                
                # Executa trade
                valor = user.get('valor_entrada', 2.0)
                max_gales = user.get('max_gales', 1)
                multiplicador = user.get('multiplicador', 2.0)
                
                for tentativa in range(max_gales + 1):
                    val = round(valor * (multiplicador ** tentativa), 2)
                    
                    # Verifica saldo antes
                    saldo_antes = await iq.get_saldo()
                    
                    if saldo_antes < val:
                        await app.bot.send_message(
                            user_id, 
                            f"⚠️ Saldo insuficiente! R$ {saldo_antes:.2f}",
                            parse_mode="Markdown"
                        )
                        break
                    
                    # Executa compra
                    ok, order_id = await iq.comprar(
                        sinal['ativo'], 
                        sinal['direcao'], 
                        1,  # 1 minuto
                        val
                    )
                    
                    if not ok:
                        logger.error(f"❌ Falha compra user {user_id}")
                        continue
                    
                    # Aguarda resultado (1 minuto + buffer)
                    await asyncio.sleep(65)
                    
                    # Verifica resultado
                    saldo_depois = await iq.get_saldo()
                    lucro = saldo_depois - saldo_antes
                    
                    if lucro > 0:
                        salvar_trade(user_id, sinal['ativo'], sinal['direcao'], val, "win", abs(lucro))
                        atualizar_user(user_id, saldo=saldo_depois)
                        gale_text = f" (Gale {tentativa})" if tentativa > 0 else ""
                        await app.bot.send_message(
                            user_id, 
                            f"✅ *WIN{gale_text}!* +R$ {abs(lucro):.2f}\n💰 Saldo: R$ {saldo_depois:.2f}",
                            parse_mode="Markdown"
                        )
                        break
                    elif lucro < 0:
                        if tentativa < max_gales:
                            await app.bot.send_message(
                                user_id,
                                f"🔄 *Gale {tentativa+1}* - Prejuízo R$ {abs(lucro):.2f}",
                                parse_mode="Markdown"
                            )
                            continue
                        else:
                            salvar_trade(user_id, sinal['ativo'], sinal['direcao'], val, "loss", -val)
                            atualizar_user(user_id, saldo=saldo_depois)
                            await app.bot.send_message(
                                user_id, 
                                f"❌ *LOSS* -R$ {val:.2f}\n💰 Saldo: R$ {saldo_depois:.2f}",
                                parse_mode="Markdown"
                            )
                    break
            else:
                sem_sinal_count += 1
                if sem_sinal_count % 10 == 0:
                    await app.bot.send_message(
                        user_id,
                        "⏳ Aguardando sinal...\n"
                        f"🎯 {len(iq.velas.get('EURUSD', []))} velas carregadas",
                        parse_mode="Markdown"
                    )
            
            # Aguarda próximo ciclo (menos agressivo)
            await asyncio.sleep(45)
            
        except asyncio.CancelledError:
            logger.info(f"⏹️ Loop cancelado para user {user_id}")
            break
        except Exception as e:
            logger.error(f"❌ Erro trading user {user_id}: {e}")
            await asyncio.sleep(30)
            continue

# ═══════════════════════════════════════════
# [RESTANTE DO CÓDIGO: HANDLERS E MAIN]
# ═══════════════════════════════════════════

# ESTADOS DA CONFIGURAÇÃO
(CONF_EMAIL, CONF_SENHA, CONF_CONTA, CONF_VALOR, 
 CONF_MULTI, CONF_GALES, CONF_SL, CONF_SW) = range(8)

# ... (mantenha seus handlers existentes)
# cmd_start, cmd_status, cmd_ligar, cmd_parar, cmd_ajuda
# cmd_configurar (conversation handler)
# cmd_admin, cmd_desativar, cmd_listar
# (todos idênticos aos que você já tem)

# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation Handler para configurar
    conv = ConversationHandler(
        entry_points=[CommandHandler("configurar", cmd_configurar)],
        states={
            CONF_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, conf_email)],
            CONF_SENHA: [MessageHandler(filters.TEXT & ~filters.COMMAND, conf_senha)],
            CONF_CONTA: [CallbackQueryHandler(conf_conta, pattern="^conta_")],
            CONF_VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, conf_valor)],
            CONF_MULTI: [MessageHandler(filters.TEXT & ~filters.COMMAND, conf_multi)],
            CONF_GALES: [MessageHandler(filters.TEXT & ~filters.COMMAND, conf_gales)],
            CONF_SL: [MessageHandler(filters.TEXT & ~filters.COMMAND, conf_sl)],
            CONF_SW: [MessageHandler(filters.TEXT & ~filters.COMMAND, conf_sw)],
        },
        fallbacks=[CommandHandler("cancelar", conf_cancelar)],
    )
    
    # Registra handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("ligar", cmd_ligar))
    app.add_handler(CommandHandler("parar", cmd_parar))
    app.add_handler(CommandHandler("ajuda", cmd_ajuda))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("desativar", cmd_desativar))
    app.add_handler(CommandHandler("listar", cmd_listar))
    app.add_handler(conv)
    
    print(f"\n🤖 Quantum IA V2 - Bot Telegram")
    print(f"👑 Admin ID: {ADMIN_ID}")
    print(f"📦 Usando iqoption-async")
    print(f"🚀 Pronto para Railway!\n")
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
