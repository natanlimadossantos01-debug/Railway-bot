#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import re
import time
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
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
            self.stats["sequencia"] = max(1, self.stats["sequencia"] + 1) if self.stats["sequencia"] >= 0 else 1
        elif op["status"] == "LOSS":
            self.stats["losses"] += 1
            self.stats["lucro"] -= op["valor"]
            self.stats["sequencia"] = min(-1, self.stats["sequencia"] - 1) if self.stats["sequencia"] <= 0 else -1
        elif op["status"] == "GALE":
            self.stats["gales"] += 1
        
        self.stats["melhor_seq"] = max(self.stats["melhor_seq"], self.stats["sequencia"])
        self.stats["pior_seq"] = min(self.stats["pior_seq"], self.stats["sequencia"])
    
    def get_status(self):
        s = self.stats
        taxa = (s["wins"] / s["total"] * 100) if s["total"] > 0 else 0
        
        status = f"""
📊 *ESTATÍSTICAS*
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
📋 *ÚLTIMAS 5 OPERAÇÕES*
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
            "iqoption": {
                "email": "",
                "password": "",
                "account_type": "PRACTICE",
                "valor_entrada": 5.0,
                "multiplicador_gale": 2.0,
                "max_gales": 1,
                "stop_loss": 0,
                "stop_win": 0,
                "confianca_minima": 0,
                "score_minimo": 0
            },
            "ativo": False
        }
    
    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def update(self, key, value):
        if key in self.config['iqoption']:
            self.config['iqoption'][key] = value
            self.save_config()
            return True
        return False
    
    def get_iq_config(self):
        return self.config['iqoption']
    
    def is_active(self):
        return self.config.get('ativo', False)
    
    def set_active(self, status):
        self.config['ativo'] = status
        self.save_config()

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
        self.ativo = False

    def conectar(self):
        try:
            from iqoptionapi.iqapi import IQOptionClient
            
            if not self.cfg['email'] or not self.cfg['password']:
                return False, "❌ Email ou senha não configurados!"
            
            account_type = 'demo' if self.cfg['account_type'] == 'PRACTICE' else 'real'
            
            logger.info(f"Conectando IQ Option ({account_type})...")
            
            self.api = IQOptionClient(
                self.cfg['email'],
                self.cfg['password'],
                account_type=account_type
            )
            self.api.connect()
            
            balance = self.api.get_balance()
            self.ativo = True
            return True, f"✅ Conectado! Saldo: R$ {balance:.2f}"
            
        except Exception as e:
            logger.error(f"Erro na conexão: {e}")
            return False, f"❌ Erro: {str(e)}"

    def checar_resultado(self, order_id, expiry):
        try:
            success, outcome, pnl = self.api.get_trade_outcome(order_id, expiry)
            if success:
                result = outcome.get('result', '').lower()
                if result == 'win':
                    return 'win', pnl
                elif result == 'loose':
                    return 'loose', abs(pnl)
                return 'equal', 0.0
            return 'erro', 0.0
        except Exception as e:
            logger.error(f"Erro ao checar resultado: {e}")
            return "erro", 0.0

    def operar(self, sinal, bot, chat_id):
        if not self.ativo:
            return "❌ Bot não está ativo. Use /start para configurar."
        
        cfg = self.cfg
        ativo = sinal["ativo"]
        direcao = sinal["direcao"]
        exp = sinal.get("expiracao", 1)
        valor = cfg["valor_entrada"]
        max_gales = min(sinal.get("gales", 0), cfg["max_gales"])

        # Verificar stop loss/win
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
                self.painel.adicionar({
                    "hora": datetime.now().strftime("%H:%M:%S"),
                    "ativo": ativo,
                    "direcao": direcao,
                    "status": "GALE",
                    "valor": val_atual,
                    "lucro": 0,
                    "gale": tentativa
                })

            try:
                from iqoptionapi.models import OptionsTradeParams, Direction, OptionType
                
                trade_params = OptionsTradeParams(
                    asset=ativo,
                    expiry=exp,
                    amount=val_atual,
                    direction=Direction.CALL if direcao.lower() == 'call' else Direction.PUT,
                    option_type=OptionType.BINARY_OPTION
                )

                success, order_id = self.api.execute_options_trade(trade_params)
                
                if not success:
                    return f"❌ Ordem rejeitada: {order_id}"

                bot.send_message(chat_id, f"⏳ Aguardando resultado (M{exp})...")
                time.sleep(exp * 60 + 5)
                
                status, lucro = self.checar_resultado(order_id, exp)
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
    """Inicia a configuração do bot"""
    user_id = update.effective_user.id
    config_manager = ConfigManager(user_id)
    config = config_manager.get_iq_config()
    
    if config['email'] and config['password']:
        await update.message.reply_text(
            f"🤖 *Quantum Bot - Configuração Existente*\n\n"
            f"📧 Email: {config['email']}\n"
            f"💳 Conta: {config['account_type']}\n"
            f"💰 Entrada: R$ {config['valor_entrada']:.2f}\n"
            f"🔄 Gale: {config['multiplicador_gale']}x (max {config['max_gales']})\n"
            f"🛑 Stop Loss: R$ {config['stop_loss']:.2f}\n"
            f"🏆 Stop Win: R$ {config['stop_win']:.2f}\n"
            f"🔍 Confiança: {config['confianca_minima']}%\n"
            f"🛡️ Score: {config['score_minimo']}/100\n\n"
            f"📌 *Comandos disponíveis:*\n"
            f"/start - Mostrar esta mensagem\n"
            f"/config - Reconfigurar bot\n"
            f"/status - Ver estatísticas\n"
            f"/stop - Parar bot\n"
            f"/iniciar - Iniciar bot\n\n"
            f"ℹ️ Envie mensagens com 'SINAL' para executar operações",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "🤖 *Bem-vindo ao Quantum Bot!*\n\n"
        "Vamos configurar seu bot passo a passo.\n"
        "Digite /cancel a qualquer momento para cancelar.\n\n"
        "📧 *Digite seu email da IQ Option:*",
        parse_mode='Markdown'
    )
    return EMAIL

async def config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reconfigura o bot"""
    await update.message.reply_text(
        "🔄 *Reconfiguração*\n\n"
        "Digite /start para reiniciar a configuração.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela a configuração"""
    await update.message.reply_text("❌ Configuração cancelada.")
    return ConversationHandler.END

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o email"""
    email = update.message.text.strip()
    if '@' not in email:
        await update.message.reply_text("⚠️ Email inválido. Digite um email válido:")
        return EMAIL
    
    context.user_data['email'] = email
    await update.message.reply_text(
        f"📧 Email: {email}\n\n"
        f"🔑 *Digite sua senha da IQ Option:*",
        parse_mode='Markdown'
    )
    return PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe a senha"""
    password = update.message.text.strip()
    if len(password) < 4:
        await update.message.reply_text("⚠️ Senha muito curta. Digite novamente:")
        return PASSWORD
    
    context.user_data['password'] = password
    
    await update.message.reply_text(
        f"🔑 Senha: {'*' * len(password)}\n\n"
        f"💳 *Tipo de conta:*\n"
        f"Digite '1' para DEMO ou '2' para REAL",
        parse_mode='Markdown'
    )
    return ACCOUNT_TYPE

async def get_account_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o tipo de conta"""
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
        f"💰 *Valor de entrada (mínimo R$ 1.00):*\n"
        f"Digite o valor (exemplo: 5.00)",
        parse_mode='Markdown'
    )
    return VALOR_ENTRADA

async def get_valor_entrada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o valor de entrada"""
    try:
        valor = float(update.message.text.strip())
        if valor < 1:
            await update.message.reply_text("⚠️ Valor mínimo é R$ 1.00. Digite novamente:")
            return VALOR_ENTRADA
        
        context.user_data['valor_entrada'] = valor
        
        await update.message.reply_text(
            f"💰 Entrada: R$ {valor:.2f}\n\n"
            f"🔄 *Multiplicador do Gale:*\n"
            f"Digite o multiplicador (exemplo: 2.0)",
            parse_mode='Markdown'
        )
        return MULTIPLICADOR_GALE
    except ValueError:
        await update.message.reply_text("❌ Digite um número válido. Exemplo: 5.00")
        return VALOR_ENTRADA

async def get_multiplicador_gale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o multiplicador do gale"""
    try:
        multi = float(update.message.text.strip())
        if multi < 1:
            await update.message.reply_text("⚠️ Multiplicador deve ser >= 1. Digite novamente:")
            return MULTIPLICADOR_GALE
        
        context.user_data['multiplicador_gale'] = multi
        
        await update.message.reply_text(
            f"🔄 Multiplicador: {multi}x\n\n"
            f"📊 *Número máximo de Gales:*\n"
            f"Digite o número (exemplo: 1)",
            parse_mode='Markdown'
        )
        return MAX_GALES
    except ValueError:
        await update.message.reply_text("❌ Digite um número válido. Exemplo: 2.0")
        return MULTIPLICADOR_GALE

async def get_max_gales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o número máximo de gales"""
    try:
        max_gales = int(update.message.text.strip())
        if max_gales < 0:
            await update.message.reply_text("⚠️ Digite um número >= 0. Digite novamente:")
            return MAX_GALES
        
        context.user_data['max_gales'] = max_gales
        
        await update.message.reply_text(
            f"📊 Max Gales: {max_gales}\n\n"
            f"🛑 *Stop Loss (0 para desativar):*\n"
            f"Digite o valor (exemplo: 50.00)",
            parse_mode='Markdown'
        )
        return STOP_LOSS
    except ValueError:
        await update.message.reply_text("❌ Digite um número inteiro válido.")
        return MAX_GALES

async def get_stop_loss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o stop loss"""
    try:
        stop_loss = float(update.message.text.strip())
        if stop_loss < 0:
            await update.message.reply_text("⚠️ Digite um número >= 0. Digite novamente:")
            return STOP_LOSS
        
        context.user_data['stop_loss'] = stop_loss
        
        await update.message.reply_text(
            f"🛑 Stop Loss: R$ {stop_loss:.2f}\n\n"
            f"🏆 *Stop Win (0 para desativar):*\n"
            f"Digite o valor (exemplo: 100.00)",
            parse_mode='Markdown'
        )
        return STOP_WIN
    except ValueError:
        await update.message.reply_text("❌ Digite um número válido. Exemplo: 50.00")
        return STOP_LOSS

async def get_stop_win(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o stop win"""
    try:
        stop_win = float(update.message.text.strip())
        if stop_win < 0:
            await update.message.reply_text("⚠️ Digite um número >= 0. Digite novamente:")
            return STOP_WIN
        
        context.user_data['stop_win'] = stop_win
        
        await update.message.reply_text(
            f"🏆 Stop Win: R$ {stop_win:.2f}\n\n"
            f"🔍 *Confiança mínima (0 para ignorar):*\n"
            f"Digite o valor (exemplo: 70)",
            parse_mode='Markdown'
        )
        return CONFIANCE
    except ValueError:
        await update.message.reply_text("❌ Digite um número válido. Exemplo: 100.00")
        return STOP_WIN

async def get_confiance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe a confiança mínima"""
    try:
        confiance = int(update.message.text.strip())
        if confiance < 0 or confiance > 100:
            await update.message.reply_text("⚠️ Digite um número entre 0 e 100. Digite novamente:")
            return CONFIANCE
        
        context.user_data['confianca_minima'] = confiance
        
        await update.message.reply_text(
            f"🔍 Confiança mínima: {confiance}%\n\n"
            f"🛡️ *Score mínimo (0 para ignorar):*\n"
            f"Digite o valor (exemplo: 80)",
            parse_mode='Markdown'
        )
        return SCORE
    except ValueError:
        await update.message.reply_text("❌ Digite um número inteiro válido.")
        return CONFIANCE

async def get_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o score mínimo"""
    try:
        score = int(update.message.text.strip())
        if score < 0 or score > 100:
            await update.message.reply_text("⚠️ Digite um número entre 0 e 100. Digite novamente:")
            return SCORE
        
        context.user_data['score_minimo'] = score
        
        # Salvar configuração
        user_id = update.effective_user.id
        config_manager = ConfigManager(user_id)
        
        # Atualizar configurações
        config = config_manager.get_iq_config()
        config['email'] = context.user_data.get('email', '')
        config['password'] = context.user_data.get('password', '')
        config['account_type'] = context.user_data.get('account_type', 'PRACTICE')
        config['valor_entrada'] = context.user_data.get('valor_entrada', 5.0)
        config['multiplicador_gale'] = context.user_data.get('multiplicador_gale', 2.0)
        config['max_gales'] = context.user_data.get('max_gales', 1)
        config['stop_loss'] = context.user_data.get('stop_loss', 0)
        config['stop_win'] = context.user_data.get('stop_win', 0)
        config['confianca_minima'] = context.user_data.get('confianca_minima', 0)
        config['score_minimo'] = context.user_data.get('score_minimo', 0)
        config_manager.save_config()
        
        # Mostrar resumo
        summary = f"""
✅ *CONFIGURAÇÃO CONCLUÍDA!*

📧 *Email:* {config['email']}
💳 *Conta:* {config['account_type']}
💰 *Entrada:* R$ {config['valor_entrada']:.2f}
🔄 *Gale:* {config['multiplicador_gale']}x (max {config['max_gales']})
🛑 *Stop Loss:* R$ {config['stop_loss']:.2f}
🏆 *Stop Win:* R$ {config['stop_win']:.2f}
🔍 *Confiança:* {config['confianca_minima']}%
🛡️ *Score:* {config['score_minimo']}/100

Digite /iniciar para conectar e iniciar o bot!
"""
        await update.message.reply_text(summary, parse_mode='Markdown')
        
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Digite um número inteiro válido.")
        return SCORE

async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o bot"""
    user_id = update.effective_user.id
    config_manager = ConfigManager(user_id)
    config = config_manager.get_iq_config()
    
    if not config['email'] or not config['password']:
        await update.message.reply_text("❌ Configure o bot primeiro com /start")
        return
    
    # Conectar IQ Option
    operador = IQOperador(config)
    success, msg = operador.conectar()
    
    if not success:
        await update.message.reply_text(f"❌ Erro: {msg}\nUse /start para reconfigurar.")
        return
    
    # Salvar operador no contexto
    context.user_data['operador'] = operador
    config_manager.set_active(True)
    
    await update.message.reply_text(
        f"🚀 *BOT INICIADO!*\n\n"
        f"✅ IQ Option Conectado\n"
        f"📧 {config['email']}\n"
        f"💰 Saldo: R$ {operador.api.get_balance():.2f}\n\n"
        f"📌 Envie mensagens com 'SINAL' para executar operações\n"
        f"🔧 Comandos: /status, /stop",
        parse_mode='Markdown'
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra status atual"""
    user_id = update.effective_user.id
    config_manager = ConfigManager(user_id)
    config = config_manager.get_iq_config()
    
    operador = context.user_data.get('operador')
    
    if operador and operador.ativo:
        status_text = f"""
🤖 *STATUS DO BOT*

📧 *Email:* {config['email']}
💳 *Conta:* {config['account_type']}
💰 *Entrada:* R$ {config['valor_entrada']:.2f}
🔄 *Gale:* {config['multiplicador_gale']}x
🛑 *Stop:* L: R$ {config['stop_loss']:.2f} | W: R$ {config['stop_win']:.2f}

{operador.painel.get_status()}
        """
        await update.message.reply_text(status_text, parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ Bot não está ativo. Use /iniciar para iniciar.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Para o bot"""
    user_id = update.effective_user.id
    config_manager = ConfigManager(user_id)
    config_manager.set_active(False)
    
    if 'operador' in context.user_data:
        operador = context.user_data['operador']
        operador.ativo = False
        if operador.api:
            try:
                operador.api.disconnect()
            except:
                pass
    
    await update.message.reply_text("⏹️ *Bot parado com sucesso!*", parse_mode='Markdown')
    
    # Mostrar resumo
    if 'operador' in context.user_data:
        operador = context.user_data['operador']
        if operador.operacoes > 0:
            taxa = (operador.wins / operador.operacoes * 100) if operador.operacoes > 0 else 0
            await update.message.reply_text(
                f"📊 *RESUMO FINAL*\n\n"
                f"📈 Total: {operador.operacoes}\n"
                f"✅ Wins: {operador.wins}\n"
                f"❌ Loss: {operador.losses}\n"
                f"📊 Taxa: {taxa:.1f}%\n"
                f"💰 Lucro: R$ {operador.lucro_dia:.2f}",
                parse_mode='Markdown'
            )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens do usuário"""
    user_id = update.effective_user.id
    text = update.message.text
    chat_id = update.effective_chat.id
    
    # Verificar se é sinal
    sinal = parse_sinal(text)
    if not sinal:
        await update.message.reply_text("ℹ️ Mensagem recebida. Aguardando sinais com 'SINAL'...")
        return
    
    # Processar sinal
    config_manager = ConfigManager(user_id)
    config = config_manager.get_iq_config()
    
    if not config_manager.is_active():
        await update.message.reply_text("❌ Bot está parado. Use /iniciar para iniciar.")
        return
    
    # Verificar se tem operador
    operador = context.user_data.get('operador')
    if not operador or not operador.ativo:
        await update.message.reply_text("🔄 Reconectando IQ Option...")
        operador = IQOperador(config)
        success, msg = operador.conectar()
        if not success:
            await update.message.reply_text(f"❌ {msg}")
            return
        context.user_data['operador'] = operador
    
    # Verificar filtros
    if config['confianca_minima'] > 0 and sinal.get('confianca', 100) < config['confianca_minima']:
        await update.message.reply_text(f"⚠️ Confiança {sinal.get('confianca')}% < {config['confianca_minima']}% (ignorado)")
        return
    
    if config['score_minimo'] > 0 and sinal.get('score', 100) < config['score_minimo']:
        await update.message.reply_text(f"⚠️ Score {sinal.get('score')} < {config['score_minimo']} (ignorado)")
        return
    
    # Executar operação
    await update.message.reply_text(
        f"📩 *SINAL DETECTADO!*\n\n"
        f"💰 Ativo: {sinal['ativo']}\n"
        f"📈 Direção: {sinal['direcao'].upper()}\n"
        f"⌛ Expiração: M{sinal['expiracao']}",
        parse_mode='Markdown'
    )
    
    operador.operar(sinal, update.message.bot, chat_id)

# ============ MAIN ============

def main():
    """Função principal"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN não configurado!")
        logger.info("Configure a variável de ambiente TELEGRAM_BOT_TOKEN")
        return
    
    # Criar aplicação
    application = Application.builder().token(token).build()
    
    # Conversation handler para configuração
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
    
    # Adicionar handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('config', config))
    application.add_handler(CommandHandler('iniciar', iniciar))
    application.add_handler(CommandHandler('status', status))
    application.add_handler(CommandHandler('stop', stop))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Iniciar bot
    logger.info("🚀 Bot iniciado!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
