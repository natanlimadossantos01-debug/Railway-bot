#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import re
import time
import logging
import hashlib
import hmac
import random
import string
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telegram.error import NetworkError, TimedOut
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados da conversa
(EMAIL, PASSWORD, ACCOUNT_TYPE, VALOR_ENTRADA, MULTIPLICADOR_GALE, 
 MAX_GALES, STOP_LOSS, STOP_WIN, CONFIANCE, SCORE) = range(10)

# Configurações
CONFIG_DIR = "data/configs"
os.makedirs(CONFIG_DIR, exist_ok=True)

HISTORICO_MAX = 50

class PainelOperacoes:
    def __init__(self):
        self.operacoes = []
        self.stats = {
            "total": 0, "wins": 0, "losses": 0, "gales": 0,
            "lucro": 0.0, "sequencia": 0, "melhor_seq": 0, "pior_seq": 0
        }
    
    def adicionar(self, operacao):
        self.operacoes.insert(0, operacao)
        if len(self.operacoes) > HISTORICO_MAX:
            self.operacoes.pop()
        self.atualizar_stats(operacao)
    
    def atualizar_stats(self, op):
        self.stats["total"] += 1
        if op["status"] == "WIN":
            self.stats["wins"] += 1
            self.stats["lucro"] += op["lucro"]
            self.stats["sequencia"] = self.stats["sequencia"] + 1 if self.stats["sequencia"] >= 0 else 1
        elif op["status"] == "LOSS":
            self.stats["losses"] += 1
            self.stats["lucro"] -= op["valor"]
            self.stats["sequencia"] = self.stats["sequencia"] - 1 if self.stats["sequencia"] <= 0 else -1
        elif op["status"] == "GALE":
            self.stats["gales"] += 1
        
        self.stats["melhor_seq"] = max(self.stats["melhor_seq"], self.stats["sequencia"])
        self.stats["pior_seq"] = min(self.stats["pior_seq"], self.stats["sequencia"])
    
    def get_status(self):
        s = self.stats
        taxa = (s["wins"] / s["total"] * 100) if s["total"] > 0 else 0
        
        status = f"""
📊 ESTATÍSTICAS
━━━━━━━━━━━━━━━━━━
📈 Total: {s['total']}
✅ Wins: {s['wins']}
❌ Loss: {s['losses']}
🔄 Gales: {s['gales']}
📊 Taxa: {taxa:.1f}%
💰 Lucro: R$ {s['lucro']:.2f}
📈 Sequência: {self.formatar_seq(s['sequencia'])}
🏆 Melhor: {s['melhor_seq']} | ❄️ Pior: {s['pior_seq']}
━━━━━━━━━━━━━━━━━━
📋 ÚLTIMAS 5 OPERAÇÕES
"""
        for op in self.operacoes[:5]:
            status += f"\n• {op['hora']} {op['ativo']} "
            if op["status"] == "WIN":
                status += f"✅ +R$ {op['lucro']:.2f}"
            elif op["status"] == "LOSS":
                status += f"❌ -R$ {op['valor']:.2f}"
            elif op["status"] == "GALE":
                status += f"🔄 Gale {op.get('gale', 0)}"
        
        return status
    
    def formatar_seq(self, seq):
        if seq > 0: return f"🔥 +{seq}"
        elif seq < 0: return f"❄️ {seq}"
        return "⚖️ 0"

class ConfigManager:
    def __init__(self, user_id):
        self.user_id = str(user_id)
        self.config_file = os.path.join(CONFIG_DIR, f'config_{self.user_id}.json')
        self.config = self.load_config()
    
    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except:
                return self.get_default_config()
        return self.get_default_config()
    
    def get_default_config(self):
        return {
            "email": "",
            "password": "",
            "account_type": "PRACTICE",
            "valor_entrada": 5.0,
            "multiplicador_gale": 2.0,
            "max_gales": 1,
            "stop_loss": 0,
            "stop_win": 0,
            "confianca_minima": 0,
            "score_minimo": 0,
            "ativo": False
        }
    
    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def get_config(self):
        return self.config
    
    def is_active(self):
        return self.config.get('ativo', False)
    
    def set_active(self, status):
        self.config['ativo'] = status
        self.save_config()

# ============ API IQ OPTION SIMPLIFICADA ============

class SimpleIQOption:
    """API simplificada para IQ Option usando apenas requests"""
    
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.ssid = None
        self.logged_in = False
        self.balance = 0
        self.user_id = None
        self.token = None
        
        # Headers padrão
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'Origin': 'https://iqoption.com',
            'Referer': 'https://iqoption.com/pt/',
        })
    
    def login(self):
        """Faz login na IQ Option"""
        try:
            # Primeiro, pegar o SSID
            login_url = "https://auth.iqoption.com/api/v1/login"
            
            payload = {
                "email": self.email,
                "password": self.password
            }
            
            response = self.session.post(login_url, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    self.logged_in = True
                    self.user_id = data.get('data', {}).get('user_id')
                    self.token = data.get('data', {}).get('token')
                    
                    # Atualizar headers com token
                    self.session.headers.update({
                        'Authorization': f'Bearer {self.token}'
                    })
                    
                    # Buscar saldo
                    self._update_balance()
                    
                    return True, "✅ Login realizado com sucesso!"
                else:
                    return False, f"❌ Erro no login: {data.get('msg', 'Erro desconhecido')}"
            else:
                return False, f"❌ Erro HTTP: {response.status_code}"
                
        except Exception as e:
            logger.error(f"Erro no login: {e}")
            return False, f"❌ Erro: {str(e)}"
    
    def _update_balance(self):
        """Atualiza o saldo"""
        try:
            response = self.session.get(
                "https://iqoption.com/api/getbalance",
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                self.balance = data.get('data', {}).get('balance', 0)
            return self.balance
        except:
            return self.balance
    
    def get_balance(self):
        """Retorna o saldo atual"""
        self._update_balance()
        return self.balance
    
    def get_asset_id(self, asset_name):
        """Converte nome do ativo para ID"""
        assets = {
            'EURUSD': 1, 'EURUSD-OTC': 1,
            'GBPUSD': 2, 'GBPUSD-OTC': 2,
            'USDJPY': 3, 'USDJPY-OTC': 3,
            'AUDUSD': 4, 'AUDUSD-OTC': 4,
            'USDCAD': 5, 'USDCAD-OTC': 5,
            'USDCHF': 6, 'USDCHF-OTC': 6,
            'NZDUSD': 7, 'NZDUSD-OTC': 7,
            'BTCUSD': 8, 'BTCUSD-OTC': 8,
            'ETHUSD': 9, 'ETHUSD-OTC': 9,
            'LTCUSD': 10, 'LTCUSD-OTC': 10,
            'XRPUSD': 11, 'XRPUSD-OTC': 11,
        }
        return assets.get(asset_name.upper(), 1)
    
    def buy(self, amount, asset, direction, expiry):
        """Executa uma operação"""
        if not self.logged_in:
            return False, "Não conectado"
        
        try:
            asset_id = self.get_asset_id(asset)
            direction_value = 1 if direction.lower() == 'call' else 2
            expiry_seconds = expiry * 60
            
            payload = {
                "asset_id": asset_id,
                "amount": float(amount),
                "direction": direction_value,
                "expiry": expiry_seconds,
                "type": 1  # 1 = binária
            }
            
            response = self.session.post(
                "https://iqoption.com/api/buy",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    order_id = data.get('data', {}).get('order_id')
                    return True, order_id
                else:
                    return False, data.get('msg', 'Erro na operação')
            else:
                return False, f"Erro HTTP: {response.status_code}"
                
        except Exception as e:
            logger.error(f"Erro ao comprar: {e}")
            return False, str(e)
    
    def check_win(self, order_id):
        """Verifica resultado de uma operação"""
        try:
            response = self.session.get(
                f"https://iqoption.com/api/get-result/{order_id}",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    result_data = data.get('data', {})
                    profit = result_data.get('profit', 0)
                    status = result_data.get('status', '')
                    
                    if profit > 0:
                        return 'win', profit
                    elif profit < 0:
                        return 'loose', abs(profit)
                    else:
                        return 'equal', 0
                else:
                    return 'erro', 0
            return 'erro', 0
        except Exception as e:
            logger.error(f"Erro ao verificar: {e}")
            return 'erro', 0

class IQOperador:
    def __init__(self, config):
        self.cfg = config
        self.api = None
        self.painel = PainelOperacoes()
        self.lucro_dia = 0.0
        self.operacoes = 0
        self.wins = 0
        self.losses = 0
        self.gales_usados = 0
        self.conectado = False

    def conectar(self):
        try:
            if not self.cfg['email'] or not self.cfg['password']:
                return False, "❌ Email ou senha não configurados!"
            
            logger.info(f"🔄 Conectando IQ Option...")
            
            self.api = SimpleIQOption(self.cfg['email'], self.cfg['password'])
            success, msg = self.api.login()
            
            if not success:
                return False, msg
            
            self.conectado = True
            balance = self.api.get_balance()
            logger.info(f"✅ Conectado! Saldo: R$ {balance:.2f}")
            return True, f"✅ Conectado! Saldo: R$ {balance:.2f}"
            
        except Exception as e:
            logger.error(f"❌ Erro na conexão: {e}")
            self.conectado = False
            return False, f"❌ Erro: {str(e)}"

    def operar(self, sinal, bot, chat_id):
        if not self.conectado:
            return "❌ Bot não conectado. Use /iniciar para reconectar."
        
        cfg = self.cfg
        ativo = sinal["ativo"]
        direcao = sinal["direcao"]
        exp = sinal.get("expiracao", 1)
        valor = cfg["valor_entrada"]
        max_gales = min(sinal.get("gales", 0), cfg["max_gales"])

        if cfg["stop_loss"] > 0 and self.lucro_dia <= -cfg["stop_loss"]:
            return f"🛑 Stop Loss atingido! Lucro: R$ {self.lucro_dia:.2f}"
        
        if cfg["stop_win"] > 0 and self.lucro_dia >= cfg["stop_win"]:
            return f"🏆 Stop Win atingido! Lucro: R$ {self.lucro_dia:.2f}"

        bot.send_message(chat_id, f"🎯 {ativo} | {direcao.upper()} | M{exp} | R$ {valor:.2f}")

        tentativa = 0
        resultado_final = ""
        
        while tentativa <= max_gales:
            val_atual = round(valor * (cfg["multiplicador_gale"] ** tentativa), 2)

            if tentativa > 0:
                self.gales_usados += 1
                bot.send_message(chat_id, f"🔄 Gale {tentativa} → R$ {val_atual:.2f}")

            try:
                success, order_id = self.api.buy(val_atual, ativo, direcao, exp)
                
                if not success:
                    return f"❌ Ordem rejeitada: {order_id}"

                bot.send_message(chat_id, f"⏳ Aguardando resultado (M{exp})...")
                time.sleep(exp * 60 + 5)
                
                status, lucro = self.api.check_win(order_id)
                self.operacoes += 1

                if status == "win":
                    self.wins += 1
                    self.lucro_dia += lucro
                    resultado_final = f"✅ WIN! +R$ {lucro:.2f}"
                    
                    self.painel.adicionar({
                        "hora": datetime.now().strftime("%H:%M:%S"),
                        "ativo": ativo,
                        "direcao": direcao,
                        "status": "WIN",
                        "valor": val_atual,
                        "lucro": lucro,
                        "gale": tentativa
                    })
                    
                    bot.send_message(chat_id, resultado_final)
                    break
                    
                elif status in ("loose", "loss"):
                    self.losses += 1
                    self.lucro_dia -= val_atual
                    resultado_final = f"❌ LOSS! -R$ {val_atual:.2f}"
                    
                    self.painel.adicionar({
                        "hora": datetime.now().strftime("%H:%M:%S"),
                        "ativo": ativo,
                        "direcao": direcao,
                        "status": "LOSS",
                        "valor": val_atual,
                        "lucro": -val_atual,
                        "gale": tentativa
                    })
                    
                    bot.send_message(chat_id, resultado_final)
                    
                    tentativa += 1
                    if tentativa > max_gales:
                        bot.send_message(chat_id, "🚫 Sem mais gales.")
                        
                elif status == "equal":
                    bot.send_message(chat_id, "〰️ EMPATE (doji)")
                    break
                else:
                    bot.send_message(chat_id, f"Status: {status}")
                    break

            except Exception as e:
                error_msg = f"❌ Erro: {str(e)}"
                logger.error(error_msg)
                bot.send_message(chat_id, error_msg)
                break

        if self.operacoes > 0:
            taxa = (self.wins / self.operacoes * 100) if self.operacoes > 0 else 0
            summary = f"📊 {self.operacoes} ops | {self.wins}W/{self.losses}L | {taxa:.0f}% | R$ {self.lucro_dia:.2f}"
            bot.send_message(chat_id, summary)
        
        return resultado_final

def parse_sinal(texto):
    if "SINAL" not in texto.upper():
        return None

    sinal = {}

    m = re.search(r'Hor[aá]rio[:\s]+(\d{1,2}:\d{2})', texto)
    if m:
        sinal["horario"] = m.group(1)

    m = re.search(r'Ativo[:\s]+([\w\-\/]+)', texto)
    if m:
        sinal["ativo"] = m.group(1).strip()

    if "CALL" in texto.upper():
        sinal["direcao"] = "call"
    elif "PUT" in texto.upper():
        sinal["direcao"] = "put"

    m = re.search(r'Expira[çc][aã]o[:\s]+M(\d+)', texto, re.IGNORECASE)
    sinal["expiracao"] = int(m.group(1)) if m else 1

    m = re.search(r'Confian[çc]a[:\s]+(\d+)%', texto, re.IGNORECASE)
    if m:
        sinal["confianca"] = int(m.group(1))

    m = re.search(r'Score\s+IA[:\s]+(\d+)/100', texto, re.IGNORECASE)
    if m:
        sinal["score"] = int(m.group(1))

    m = re.search(r'(\d+)\s+recupera[çc][aã]o', texto, re.IGNORECASE)
    sinal["gales"] = int(m.group(1)) if m else 0

    if "ativo" in sinal and "direcao" in sinal:
        return sinal
    return None

# ============ HANDLERS DO TELEGRAM ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    config_manager = ConfigManager(user_id)
    config = config_manager.get_config()
    
    if config['email'] and config['password']:
        msg = (
            f"🤖 Quantum Bot - Configuração Existente\n\n"
            f"📧 Email: {config['email']}\n"
            f"💳 Conta: {config['account_type']}\n"
            f"💰 Entrada: R$ {config['valor_entrada']:.2f}\n"
            f"🔄 Gale: {config['multiplicador_gale']}x (max {config['max_gales']})\n"
            f"🛑 Stop Loss: R$ {config['stop_loss']:.2f}\n"
            f"🏆 Stop Win: R$ {config['stop_win']:.2f}\n"
            f"🔍 Confiança: {config['confianca_minima']}%\n"
            f"🛡️ Score: {config['score_minimo']}/100\n\n"
            f"📌 Comandos:\n"
            f"/start - Menu\n"
            f"/config - Reconfigurar\n"
            f"/status - Estatísticas\n"
            f"/stop - Parar bot\n"
            f"/iniciar - Iniciar bot\n\n"
            f"ℹ️ Envie 'SINAL' para operar"
        )
        await update.message.reply_text(msg)
        return ConversationHandler.END
    
    await update.message.reply_text(
        "🤖 Bem-vindo ao Quantum Bot!\n\n"
        "Vamos configurar seu bot passo a passo.\n"
        "Digite /cancel para cancelar.\n\n"
        "📧 Digite seu email da IQ Option:"
    )
    return EMAIL

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Configuração cancelada.")
    return ConversationHandler.END

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    if '@' not in email:
        await update.message.reply_text("⚠️ Email inválido. Digite novamente:")
        return EMAIL
    
    context.user_data['email'] = email
    await update.message.reply_text(f"📧 Email: {email}\n\n🔑 Digite sua senha:")
    return PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    if len(password) < 4:
        await update.message.reply_text("⚠️ Senha muito curta. Digite novamente:")
        return PASSWORD
    
    context.user_data['password'] = password
    await update.message.reply_text(
        f"🔑 Senha: {'*' * len(password)}\n\n"
        f"💳 Tipo de conta:\n"
        f"Digite '1' para DEMO ou '2' para REAL"
    )
    return ACCOUNT_TYPE

async def get_account_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip()
    
    if choice == '1':
        account_type = 'PRACTICE'
    elif choice == '2':
        account_type = 'REAL'
    else:
        await update.message.reply_text("⚠️ Digite '1' para DEMO ou '2' para REAL:")
        return ACCOUNT_TYPE
    
    context.user_data['account_type'] = account_type
    await update.message.reply_text(
        f"💳 Conta: {account_type}\n\n"
        f"💰 Valor de entrada (mínimo R$ 1.00):"
    )
    return VALOR_ENTRADA

async def get_valor_entrada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        valor = float(update.message.text.strip())
        if valor < 1:
            await update.message.reply_text("⚠️ Valor mínimo é R$ 1.00. Digite novamente:")
            return VALOR_ENTRADA
        
        context.user_data['valor_entrada'] = valor
        await update.message.reply_text(
            f"💰 Entrada: R$ {valor:.2f}\n\n"
            f"🔄 Multiplicador do Gale (ex: 2.0):"
        )
        return MULTIPLICADOR_GALE
    except ValueError:
        await update.message.reply_text("❌ Digite um número válido.")
        return VALOR_ENTRADA

async def get_multiplicador_gale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        multi = float(update.message.text.strip())
        if multi < 1:
            await update.message.reply_text("⚠️ Multiplicador deve ser >= 1:")
            return MULTIPLICADOR_GALE
        
        context.user_data['multiplicador_gale'] = multi
        await update.message.reply_text(
            f"🔄 Multiplicador: {multi}x\n\n"
            f"📊 Número máximo de Gales:"
        )
        return MAX_GALES
    except ValueError:
        await update.message.reply_text("❌ Digite um número válido.")
        return MULTIPLICADOR_GALE

async def get_max_gales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        max_gales = int(update.message.text.strip())
        if max_gales < 0:
            await update.message.reply_text("⚠️ Digite um número >= 0:")
            return MAX_GALES
        
        context.user_data['max_gales'] = max_gales
        await update.message.reply_text(
            f"📊 Max Gales: {max_gales}\n\n"
            f"🛑 Stop Loss (0 para desativar):"
        )
        return STOP_LOSS
    except ValueError:
        await update.message.reply_text("❌ Digite um número inteiro.")
        return MAX_GALES

async def get_stop_loss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        stop_loss = float(update.message.text.strip())
        if stop_loss < 0:
            await update.message.reply_text("⚠️ Digite um número >= 0:")
            return STOP_LOSS
        
        context.user_data['stop_loss'] = stop_loss
        await update.message.reply_text(
            f"🛑 Stop Loss: R$ {stop_loss:.2f}\n\n"
            f"🏆 Stop Win (0 para desativar):"
        )
        return STOP_WIN
    except ValueError:
        await update.message.reply_text("❌ Digite um número válido.")
        return STOP_LOSS

async def get_stop_win(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        stop_win = float(update.message.text.strip())
        if stop_win < 0:
            await update.message.reply_text("⚠️ Digite um número >= 0:")
            return STOP_WIN
        
        context.user_data['stop_win'] = stop_win
        await update.message.reply_text(
            f"🏆 Stop Win: R$ {stop_win:.2f}\n\n"
            f"🔍 Confiança mínima (0 para ignorar):"
        )
        return CONFIANCE
    except ValueError:
        await update.message.reply_text("❌ Digite um número válido.")
        return STOP_WIN

async def get_confiance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        confiance = int(update.message.text.strip())
        if confiance < 0 or confiance > 100:
            await update.message.reply_text("⚠️ Digite entre 0 e 100:")
            return CONFIANCE
        
        context.user_data['confianca_minima'] = confiance
        await update.message.reply_text(
            f"🔍 Confiança: {confiance}%\n\n"
            f"🛡️ Score mínimo (0 para ignorar):"
        )
        return SCORE
    except ValueError:
        await update.message.reply_text("❌ Digite um número inteiro.")
        return CONFIANCE

async def get_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        score = int(update.message.text.strip())
        if score < 0 or score > 100:
            await update.message.reply_text("⚠️ Digite entre 0 e 100:")
            return SCORE
        
        context.user_data['score_minimo'] = score
        
        user_id = update.effective_user.id
        config_manager = ConfigManager(user_id)
        config = config_manager.get_config()
        
        for key in ['email', 'password', 'account_type', 'valor_entrada', 
                   'multiplicador_gale', 'max_gales', 'stop_loss', 'stop_win',
                   'confianca_minima', 'score_minimo']:
            if key in context.user_data:
                config[key] = context.user_data[key]
        
        config_manager.save_config()
        
        summary = (
            f"✅ CONFIGURAÇÃO CONCLUÍDA!\n\n"
            f"📧 Email: {config['email']}\n"
            f"💳 Conta: {config['account_type']}\n"
            f"💰 Entrada: R$ {config['valor_entrada']:.2f}\n"
            f"🔄 Gale: {config['multiplicador_gale']}x\n"
            f"📊 Max Gales: {config['max_gales']}\n"
            f"🛑 Stop Loss: R$ {config['stop_loss']:.2f}\n"
            f"🏆 Stop Win: R$ {config['stop_win']:.2f}\n"
            f"🔍 Confiança: {config['confianca_minima']}%\n"
            f"🛡️ Score: {config['score_minimo']}/100\n\n"
            f"Digite /iniciar para conectar!"
        )
        await update.message.reply_text(summary)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Digite um número inteiro.")
        return SCORE

async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    config_manager = ConfigManager(user_id)
    config = config_manager.get_config()
    
    if not config['email'] or not config['password']:
        await update.message.reply_text("❌ Configure o bot primeiro com /start")
        return
    
    operador = IQOperador(config)
    success, msg = operador.conectar()
    
    if not success:
        await update.message.reply_text(f"❌ {msg}\nUse /start para reconfigurar.")
        return
    
    context.user_data['operador'] = operador
    config_manager.set_active(True)
    
    await update.message.reply_text(
        f"🚀 BOT INICIADO!\n\n"
        f"✅ IQ Option Conectado\n"
        f"📧 {config['email']}\n"
        f"💰 Saldo: R$ {operador.api.get_balance():.2f}\n\n"
        f"📌 Envie 'SINAL' para operar\n"
        f"🔧 Comandos: /status, /stop"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    config_manager = ConfigManager(user_id)
    config = config_manager.get_config()
    operador = context.user_data.get('operador')
    
    if operador and operador.conectado:
        status_text = (
            f"🤖 STATUS DO BOT\n\n"
            f"📧 Email: {config['email']}\n"
            f"💳 Conta: {config['account_type']}\n"
            f"💰 Entrada: R$ {config['valor_entrada']:.2f}\n"
            f"🔄 Gale: {config['multiplicador_gale']}x\n"
            f"🛑 Stop: L: R$ {config['stop_loss']:.2f} | W: R$ {config['stop_win']:.2f}\n"
            f"🔍 Confiança: {config['confianca_minima']}%\n"
            f"🛡️ Score: {config['score_minimo']}/100\n\n"
            f"{operador.painel.get_status()}"
        )
        await update.message.reply_text(status_text)
    else:
        await update.message.reply_text("❌ Bot não está ativo. Use /iniciar.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    config_manager = ConfigManager(user_id)
    config_manager.set_active(False)
    
    if 'operador' in context.user_data:
        operador = context.user_data['operador']
        operador.conectado = False
    
    await update.message.reply_text("⏹️ Bot parado com sucesso!")
    
    if 'operador' in context.user_data:
        operador = context.user_data['operador']
        if operador.operacoes > 0:
            taxa = (operador.wins / operador.operacoes * 100) if operador.operacoes > 0 else 0
            await update.message.reply_text(
                f"📊 RESUMO FINAL\n\n"
                f"📈 Total: {operador.operacoes}\n"
                f"✅ Wins: {operador.wins}\n"
                f"❌ Loss: {operador.losses}\n"
                f"📊 Taxa: {taxa:.1f}%\n"
                f"💰 Lucro: R$ {operador.lucro_dia:.2f}"
            )

async def config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Use /start para reconfigurar completamente.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    chat_id = update.effective_chat.id
    
    sinal = parse_sinal(text)
    if not sinal:
        await update.message.reply_text("ℹ️ Envie 'SINAL' para operar.")
        return
    
    config_manager = ConfigManager(user_id)
    config = config_manager.get_config()
    
    if not config_manager.is_active():
        await update.message.reply_text("❌ Bot está parado. Use /iniciar.")
        return
    
    operador = context.user_data.get('operador')
    if not operador or not operador.conectado:
        await update.message.reply_text("🔄 Reconectando...")
        operador = IQOperador(config)
        success, msg = operador.conectar()
        if not success:
            await update.message.reply_text(f"❌ {msg}")
            return
        context.user_data['operador'] = operador
    
    if config['confianca_minima'] > 0 and sinal.get('confianca', 100) < config['confianca_minima']:
        await update.message.reply_text(f"⚠️ Confiança {sinal.get('confianca')}% < {config['confianca_minima']}%")
        return
    
    if config['score_minimo'] > 0 and sinal.get('score', 100) < config['score_minimo']:
        await update.message.reply_text(f"⚠️ Score {sinal.get('score')} < {config['score_minimo']}")
        return
    
    await update.message.reply_text(
        f"📩 SINAL DETECTADO!\n\n"
        f"💰 Ativo: {sinal['ativo']}\n"
        f"📈 Direção: {sinal['direcao'].upper()}\n"
        f"⌛ Expiração: M{sinal['expiracao']}"
    )
    
    operador.operar(sinal, update.message.bot, chat_id)

# ============ MAIN ============

def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN não configurado!")
        return
    
    application = Application.builder().token(token).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
            ACCOUNT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_account_type)],
            VALOR_ENTRADA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_valor_entrada)],
            MULTIPLICADOR_GALE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_multiplicador_gale)],
            MAX_GALES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_max_gales)],
            STOP_LOSS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_stop_loss)],
            STOP_WIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_stop_win)],
            CONFIANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_confiance)],
            SCORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_score)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('config', config))
    application.add_handler(CommandHandler('iniciar', iniciar))
    application.add_handler(CommandHandler('status', status))
    application.add_handler(CommandHandler('stop', stop))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Bot iniciado!")
    
    while True:
        try:
            application.run_polling(allowed_updates=Update.ALL_TYPES)
        except (NetworkError, TimedOut) as e:
            logger.error(f"Erro de rede: {e}. Reconectando em 10s...")
            time.sleep(10)
        except KeyboardInterrupt:
            logger.info("🛑 Bot interrompido")
            break
        except Exception as e:
            logger.error(f"Erro: {e}. Reiniciando em 30s...")
            time.sleep(30)

if __name__ == "__main__":
    main()
