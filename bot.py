#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔═══════════════════════════════════════════════════════════════╗
║           🤖 QUANTUM BOT v4.0 - IQ OPTION AUTOMÁTICO        ║
║                                                               ║
║  ✅ Usando a nova API Sudip-T/iqoption-api                    ║
║  ✅ WebSocket para dados em tempo real                       ║
║  ✅ Comunicação detalhada no PV do Telegram                   ║
║  ✅ Status em tempo real de cada operação                     ║
║  ✅ Apuração completa (WIN/LOSS/GALES)                       ║
╚═══════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import logging
import re
import sys
import os
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from telethon import TelegramClient, events, Button

# ==================== LOG ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('quantum_bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("QuantumBot")

# ==================== CONSTANTES ====================

CONFIG_FILE = "quantum_config.json"
STATS_FILE  = "quantum_stats.json"

# ==================== INTERFACE ====================

class UI:

    @staticmethod
    def menu():
        return """
╔═══════════════════════════════════════════╗
║                                           ║
║           🤖 QUANTUM BOT v4.0            ║
║        IQ OPTION AUTOMÁTICO              ║
║                                           ║
╚═══════════════════════════════════════════╝

**MENU PRINCIPAL**

Escolha uma opção abaixo:
        """

    @staticmethod
    def configuracao_resumo(d: dict) -> str:
        sinc = "✅ Sim" if d.get('sincronizar_vela', True) else "❌ Não"
        return f"""
═══════ CONFIGURAÇÕES ═══════

📧 **Conta:** `{d.get('email','—')}`
💵 **Entrada:** R$ {d.get('valor_entrada', 0):,.2f}
🎯 **Gales:** {d.get('gales', 0)}
✖️ **Multiplicador:** {d.get('multiplicador', 2.0)}x
⏱️ **Antecipação:** {d.get('antecipacao', 5)}s
🕯️ **Sinc. vela:** {sinc}
🟢 **Stop Win:** R$ {d.get('stop_win', 0):,.2f}
🔴 **Stop Loss:** R$ {d.get('stop_loss', 0):,.2f}
🏦 **Conta:** {d.get('tipo_conta', '—').upper()}
📡 **Canal:** `{d.get('canal_id', '—')}`

═══════════════════════════
        """

    @staticmethod
    def status_sistema(conectado: bool, saldo: float, tipo: str, s: dict) -> str:
        ico = "🟢 CONECTADO" if conectado else "🔴 DESCONECTADO"
        ct  = "💰 REAL" if tipo == "real" else "🎯 TREINAMENTO"
        dt  = s.get('daily_trades', 0)
        dw  = s.get('daily_wins', 0)
        wr  = f"{dw/dt*100:.1f}%" if dt else "—"
        return f"""
📡 **STATUS DO SISTEMA**
━━━━━━━━━━━━━━━━━━━━━━━

🤖 **Bot:** {ico}
🔗 **IQ Option:** {ico}
💰 **Saldo:** R$ {saldo:,.2f}
🏦 **Conta:** {ct}

📊 **ESTATÍSTICAS DIÁRIAS**
━━━━━━━━━━━━━━━━━━━━━━━
📈 **Trades:** {dt}
🟢 **Wins:** {dw}
🔴 **Losses:** {s.get('daily_losses', 0)}
🎯 **Winrate:** {wr}
💵 **P&L:** R$ {s.get('daily_profit', 0):,.2f}

🏆 **TOTAL GERAL**
━━━━━━━━━━━━━━━━━━━━━━━
📈 **Trades:** {s.get('total_trades', 0)}
🟢 **Wins:** {s.get('total_wins', 0)}
🔴 **Losses:** {s.get('total_losses', 0)}
💵 **P&L:** R$ {s.get('total_profit', 0):,.2f}
        """

    @staticmethod
    def sinal_recebido(s: dict, antec: int = 0, sinc: bool = False) -> str:
        emoji = "🟢" if s.get('direcao', '').upper() == 'CALL' else "🔴"
        nota = ""
        if sinc:
            nota += "\n🕯️ Aguardando início da vela..."
        if antec:
            nota += f"\n⏱️ Entrada {antec}s antes"
        return f"""
═══════ 📡 NOVO SINAL ═══════

📈 **Ativo:** `{s.get('ativo', '—')}`
{emoji} **Direção:** {s.get('direcao', '—').upper()}
⏰ **Horário:** {s.get('horario', 'Imediato')}
⌛ **Expiração:** {s.get('tempo', 1)}min
{nota}

════════════════════════
        """

    @staticmethod
    def operacao_executando(valor: float, ativo: str, direcao: str, tempo: int, tentativa: int = 0) -> str:
        if tentativa == 0:
            return f"""
📈 **REALIZANDO OPERAÇÃO**

📊 **Ativo:** {ativo}
🎯 **Direção:** {direcao.upper()}
💵 **Valor:** R$ {valor:,.2f}
⏰ **Expiração:** {tempo}min

⏳ Aguarde o fechamento da vela...
            """
        else:
            return f"""
🔄 **GALE {tentativa}**

📊 **Ativo:** {ativo}
🎯 **Direção:** {direcao.upper()}
💵 **Valor:** R$ {valor:,.2f}
⏰ **Expiração:** {tempo}min

⏳ Aguarde o fechamento da vela...
            """

    @staticmethod
    def aguardando_vela(ts: str, antec: int) -> str:
        return f"""
🕯️ **AGUARDANDO VELA**

⏱️ Entrada programada: **{ts}**
⏳ Antecipação: {antec}s antes do fechamento

Aguardando momento ideal para entrada...
        """

    @staticmethod
    def resultado_operacao(r: dict, s: dict) -> str:
        win = r.get('win', False)
        titulo = "🟢 APURAÇÃO QUANTUM 🟢" if win else "🔴 APURAÇÃO QUANTUM 🔴"
        ico = "✅" if win else "⛔"
        cor = "🟩" if win else "🟥"
        
        tipo = r.get('tipo', 'SEM GALE')
        gales = r.get('gales_usados', 0)
        mult = r.get('multiplicador_usado', 1.0)
        
        ginfo = ""
        if gales > 0:
            ginfo = f"\n✖️ Multiplicador: {mult}x | Gale #{gales}"
        
        profit = r.get('profit', 0)
        daily = s.get('daily_profit', 0)
        ativo = r.get('ativo', '—')
        direcao = r.get('direcao', '—').upper()
        tempo = r.get('tempo', 1)
        valor_entrada = r.get('valor_entrada_usado', 0)
        conta = r.get('tipo_conta', '—').upper()

        return f"""
{titulo}

════ {tipo.upper()} ════

{ico} **M{tempo} {ativo} {direcao}**{ginfo}

💵 **Entrada:** R$ {valor_entrada:,.2f}
💲 **Resultado:** {'+' if win else ''}{profit:,.2f} USD

{cor} **Resultado Diário:**
**{daily:,.2f} USD**

🏦 **Conta:**
**{conta}**

════════════════════════
        """

    @staticmethod
    def aguardando_sinais() -> str:
        return """
⏳ **MONITORANDO CANAL DE SINAIS...**

📡 Aguardando nova operação...
        """

    @staticmethod
    def erro_operacao(erro: str) -> str:
        return f"""
❌ **ERRO NA OPERAÇÃO**

{erro}

════════════════════════
        """


# ==================== CONFIG ====================

class ConfigManager:
    DEFAULTS = {
        "email": None, "senha": None,
        "valor_entrada": 5.0, "gales": 2,
        "multiplicador": 2.0,
        "antecipacao": 5,
        "sincronizar_vela": True,
        "stop_win": 100.0, "stop_loss": 50.0,
        "tipo_conta": "real", "canal_id": None,
        "modo_automatico": False, "configurado": False,
    }

    def __init__(self):
        self.config = self._load()

    def _load(self) -> dict:
        if Path(CONFIG_FILE).exists():
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for k, v in self.DEFAULTS.items():
                data.setdefault(k, v)
            return data
        return dict(self.DEFAULTS)

    def _save(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self._save()

    @property
    def configurado(self) -> bool:
        return bool(self.config.get("configurado"))


# ==================== STATS ====================

class StatsManager:
    def __init__(self):
        self.stats = self._load()
        self._reset_diario()

    def _load(self) -> dict:
        if Path(STATS_FILE).exists():
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "daily_profit": 0.0, "daily_trades": 0, "daily_wins": 0, "daily_losses": 0,
            "total_profit": 0.0, "total_trades": 0, "total_wins": 0, "total_losses": 0,
            "ultimo_reset": datetime.now().strftime("%Y-%m-%d")
        }

    def _save(self):
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.stats, f, indent=4, ensure_ascii=False)

    def _reset_diario(self):
        hoje = datetime.now().strftime("%Y-%m-%d")
        if self.stats["ultimo_reset"] != hoje:
            self.stats.update(daily_profit=0.0, daily_trades=0,
                              daily_wins=0, daily_losses=0, ultimo_reset=hoje)
            self._save()

    def add(self, win: bool, profit: float):
        self._reset_diario()
        self.stats["daily_trades"] += 1
        self.stats["total_trades"] += 1
        self.stats["daily_profit"] += profit
        self.stats["total_profit"] += profit
        if win:
            self.stats["daily_wins"] += 1
            self.stats["total_wins"] += 1
        else:
            self.stats["daily_losses"] += 1
            self.stats["total_losses"] += 1
        self._save()

    def get_stats(self) -> dict:
        self._reset_diario()
        return self.stats


# ==================== PARSER DE SINAIS ====================

class SignalParser:
    @staticmethod
    def parse(texto: str) -> Dict[str, Any]:
        r = {'ativo': None, 'direcao': None, 'tempo': 1, 'horario': None, 'valido': False}

        if any(kw in texto.upper() for kw in ["WIN", "LOSS", "✅", "⛔"]):
            return r

        for pat in [r"Ativo:\s*([^\n]+)", r"💰\s*Ativo:\s*([^\n]+)", r"Par:\s*([^\n]+)"]:
            m = re.search(pat, texto, re.IGNORECASE)
            if m:
                r['ativo'] = re.sub(r'[^\w\s/.-]', '', m.group(1)).strip()
                break

        if "CALL" in texto.upper() or "COMPRA" in texto.upper():
            r['direcao'] = 'CALL'
        elif "PUT" in texto.upper() or "VENDA" in texto.upper():
            r['direcao'] = 'PUT'
        elif "🟢" in texto:
            r['direcao'] = 'CALL'
        elif "🔴" in texto:
            r['direcao'] = 'PUT'

        for pat in [r"Expiração:\s*([^\n]+)", r"⌛️?\s*Expiração:\s*([^\n]+)"]:
            m = re.search(pat, texto, re.IGNORECASE)
            if m:
                t = m.group(1).strip().upper()
                if 'M5' in t or '5MIN' in t:
                    r['tempo'] = 5
                elif 'M3' in t or '3MIN' in t:
                    r['tempo'] = 3
                elif 'M2' in t or '2MIN' in t:
                    r['tempo'] = 2
                else:
                    r['tempo'] = 1
                break

        for pat in [r"Horário:\s*([^\n]+)", r"⏰\s*Horário:\s*([^\n]+)"]:
            m = re.search(pat, texto, re.IGNORECASE)
            if m:
                r['horario'] = m.group(1).strip()
                break

        r['valido'] = bool(r['ativo'] and r['direcao'])
        return r


# ==================== MAPEAMENTO ATIVOS ====================

class AtivoMapper:
    MAPA = {
        "PYTH": "PYTH", "NEAR": "NEAR", "SAND": "SAND", "SEI": "SEI",
        "ICP": "ICP", "INJ": "INJ", "APT": "APT", "SUI": "SUI",
        "ARB": "ARB", "OP": "OP", "EOS": "EOS", "STX": "STX",
        "IOTA": "IOTA", "TIA": "TIA", "DOT": "DOT", "LINK": "LINK",
        "UNI": "UNI", "AVAX": "AVAX", "ATOM": "ATOM", "MATIC": "MATIC",
        "SOL": "SOL", "FLOKI": "FLOKI", "BONK": "BONK", "SHIB": "SHIB",
        "PEPE": "PEPE", "DOGE": "DOGE", "LTC": "LTC", "TRX": "TRX",
        "ADA": "ADA", "BNB": "BNB", "BTC": "BTC", "ETH": "ETH", "XRP": "XRP",
        "AAPL": "AAPL-OTC", "APPLE": "AAPL-OTC", "TSLA": "TSLA-OTC",
        "TESLA": "TSLA-OTC", "AMZN": "AMZN-OTC", "AMAZON": "AMZN-OTC",
        "GOOGL": "GOOGL-OTC", "GOOGLE": "GOOGL-OTC", "MSFT": "MSFT-OTC",
        "MICROSOFT": "MSFT-OTC", "META": "META-OTC", "FACEBOOK": "META-OTC",
        "NVDA": "NVDA-OTC", "NVIDIA": "NVDA-OTC",
        "US30": "US30-OTC", "DOW": "US30-OTC",
        "NASDAQ": "NAS100-OTC", "NAS100": "NAS100-OTC",
        "SP500": "SPX500-OTC", "SPX": "SPX500-OTC",
        "DAX": "DAX-OTC", "GERMANY30": "DAX-OTC",
        "FTSE": "FTSE-OTC", "UK100": "FTSE-OTC",
        "NIKKEI": "NIKKEI-OTC", "JAPAN225": "NIKKEI-OTC",
        "CAC": "CAC-OTC", "FRANCE40": "CAC-OTC",
        "XAUUSD": "XAUUSD-OTC", "GOLD": "XAUUSD-OTC",
        "XAGUSD": "XAGUSD-OTC", "SILVER": "XAGUSD-OTC",
        "WTI": "WTI-OTC", "USOUSD": "WTI-OTC",
        "BRENT": "BRENT-OTC", "UKOUSD": "BRENT-OTC",
        "USDCAD-OTC": "USDCAD-OTC", "EURUSD-OTC": "EURUSD-OTC",
        "GBPUSD-OTC": "GBPUSD-OTC", "USDJPY-OTC": "USDJPY-OTC",
        "USDCHF-OTC": "USDCHF-OTC", "AUDUSD-OTC": "AUDUSD-OTC",
        "NZDUSD-OTC": "NZDUSD-OTC", "EURGBP-OTC": "EURGBP-OTC",
        "EURJPY-OTC": "EURJPY-OTC", "GBPJPY-OTC": "GBPJPY-OTC",
        "AUDCAD-OTC": "AUDCAD-OTC",
        "EURUSD": "EURUSD", "GBPUSD": "GBPUSD",
        "USDJPY": "USDJPY", "AUDUSD": "AUDUSD",
        "USDCAD": "USDCAD", "USDCHF": "USDCHF",
        "NZDUSD": "NZDUSD", "EURGBP": "EURGBP",
        "EURJPY": "EURJPY", "GBPJPY": "GBPJPY",
        "AUDCAD": "AUDCAD",
    }

    @classmethod
    def mapear(cls, ativo: str) -> Tuple[Optional[str], str]:
        if not ativo:
            return None, "DIGITAL"
        up = ativo.upper()
        mapped = cls.MAPA.get(up)
        if not mapped:
            for k, v in cls.MAPA.items():
                if k in up or up in k:
                    mapped = v
                    break
        if not mapped:
            mapped = ativo.replace("/", "")
        modo = "OTC" if "-OTC" in mapped else "DIGITAL"
        logger.info(f"Mapeamento: {ativo} → {mapped} ({modo})")
        return mapped, modo


# ==================== SYNC DE VELA ====================

class VelaSync:
    @staticmethod
    def proximo_inicio(tempo_min: int, agora: datetime = None) -> datetime:
        if agora is None:
            agora = datetime.now()
        seg_total = agora.minute * 60 + agora.second + agora.microsecond / 1e6
        bloco_seg = tempo_min * 60
        ja_passou = seg_total % bloco_seg
        faltam = bloco_seg - ja_passou
        return agora + timedelta(seconds=faltam)

    @staticmethod
    async def aguardar(tempo_min: int, antecipacao_s: int, msg_fn):
        agora = datetime.now()
        proximo = VelaSync.proximo_inicio(tempo_min, agora)
        momento_entrar = proximo - timedelta(seconds=antecipacao_s)
        espera = (momento_entrar - agora).total_seconds()

        if espera <= 0:
            proximo = proximo + timedelta(minutes=tempo_min)
            momento_entrar = proximo - timedelta(seconds=antecipacao_s)
            espera = (momento_entrar - agora).total_seconds()

        if espera > 300:
            logger.warning(f"Espera de vela longa ({espera:.0f}s) — entrada imediata")
            return

        if espera > 2:
            ts = momento_entrar.strftime("%H:%M:%S")
            await msg_fn(UI.aguardando_vela(ts, antecipacao_s))
            await asyncio.sleep(espera)

        logger.info(f"Momento de entrada: {datetime.now().strftime('%H:%M:%S.%f')}")


# ==================== IQ TRADER COM NOVA API ====================

class IQTrader:
    def __init__(self, config: ConfigManager, stats: StatsManager, bot):
        self.config = config
        self.stats = stats
        self.bot = bot
        self.api = None
        self.conectado = False
        self.saldo = 0.0
        self.tipo_conta = "real"

    async def conectar(self, email: str, senha: str, tipo: str = "real") -> bool:
        try:
            await self.bot.msg("🔄 Conectando na IQ Option com nova API...")
            try:
                from iqoptionapi.iqapi import IQOptionClient
                from iqoptionapi.models import OptionsTradeParams, Direction, OptionType
            except ImportError:
                await self.bot.msg("❌ iqoptionapi não instalada!\n📦 pip install iqoptionapi")
                return False

            # Criar cliente
            account_type = 'demo' if tipo == "treinamento" else 'real'
            self.api = IQOptionClient(email, senha, account_type=account_type)
            
            # Conectar
            self.api.connect()
            
            # Verificar conexão
            balance = self.api.get_balance()
            self.conectado = True
            self.saldo = balance
            self.tipo_conta = tipo
            
            self.config.set("email", email)
            self.config.set("tipo_conta", tipo)
            
            await self.bot.msg(
                f"✅ Conectado com sucesso!\n\n"
                f"💰 Saldo: R$ {balance:,.2f}\n"
                f"🏦 Conta: {tipo.upper()}"
            )
            return True
            
        except Exception as e:
            await self.bot.msg(f"❌ Erro ao conectar: {e}")
            logger.error(f"Erro conexão: {e}")
            return False

    async def executar(self, ativo: str, direcao: str, tempo: int, skip_sinc: bool = False) -> dict:
        if not self.conectado or not self.api:
            return {"sucesso": False, "erro": "Não conectado"}

        s = self.stats.get_stats()
        stop_loss = self.config.get("stop_loss", 50.0)
        stop_win = self.config.get("stop_win", 100.0)
        daily = s['daily_profit']

        if daily <= -stop_loss:
            msg = f"🛑 Stop Loss atingido: R$ {stop_loss:,.2f}"
            await self.bot.msg(msg)
            return {"sucesso": False, "erro": "Stop Loss atingido"}

        if daily >= stop_win:
            msg = f"🎯 Stop Win atingido: R$ {stop_win:,.2f}"
            await self.bot.msg(msg)
            return {"sucesso": False, "erro": "Stop Win atingido"}

        ativo_iq, modo = AtivoMapper.mapear(ativo)
        if not ativo_iq:
            return {"sucesso": False, "erro": f"Ativo '{ativo}' não mapeado"}

        # Direção para a nova API
        direction = Direction.CALL if direcao.upper() == "CALL" else Direction.PUT
        
        valor_base = self.config.get("valor_entrada", 5.0)
        gales = self.config.get("gales", 2)
        multiplicador = self.config.get("multiplicador", 2.0)
        antecipacao = self.config.get("antecipacao", 5)
        sinc_vela = self.config.get("sincronizar_vela", True)

        if sinc_vela and not skip_sinc:
            await VelaSync.aguardar(tempo, antecipacao, self.bot.msg)

        valor_atual = valor_base
        gales_usados = 0
        tipo_res = "SEM GALE"
        perda_acumulada = 0.0

        for tentativa in range(gales + 1):

            if tentativa > 0:
                valor_atual = valor_base * (multiplicador ** tentativa)
                gales_usados = tentativa
                tipo_res = f"WIN G{tentativa}"
                ts_agora = datetime.now().strftime("%H:%M:%S")
                await self.bot.msg(
                    f"🔴 Loss na tentativa anterior!\n\n"
                    f"🔄 **GALE {tentativa}**\n"
                    f"✖️ {multiplicador}x → R$ {valor_atual:.2f}\n"
                    f"⚡ Entrada: **{ts_agora}**"
                )

            try:
                saldo_antes = self.api.get_balance()
                agora_buy = datetime.now()

                candle_start = VelaSync.proximo_inicio(tempo, agora_buy)
                candle_close = candle_start + timedelta(minutes=tempo)

                logger.info(
                    f"[T{tentativa}] Comprando R${valor_atual:.2f} "
                    f"em {ativo_iq} ({direction}) {tempo}min | "
                    f"vela fecha {candle_close.strftime('%H:%M:%S')}"
                )

                # Envia mensagem de operação
                await self.bot.msg(UI.operacao_executando(
                    valor_atual, ativo, direcao, tempo, tentativa
                ))

                # Usar a nova API para executar trade
                from iqoptionapi.models import OptionsTradeParams, OptionType
                
                trade_params = OptionsTradeParams(
                    asset=ativo_iq,
                    expiry=tempo,
                    amount=valor_atual,
                    direction=direction,
                    option_type=OptionType.BINARY_OPTION
                )

                success, order_id = self.api.execute_options_trade(trade_params)

                if not success:
                    await self.bot.msg(f"❌ Falha na execução: {order_id}")
                    return {"sucesso": False, "erro": f"Falha ao comprar: {order_id}"}

                ts_close = candle_close.strftime("%H:%M:%S")
                await self.bot.msg(
                    f"⏳ Aguardando fechamento da vela: **{ts_close}**"
                )

                espera = (candle_close - datetime.now()).total_seconds() - 1
                if espera > 0:
                    await asyncio.sleep(espera)

                # Verificar resultado usando a nova API
                profit = None
                if order_id:
                    for _ in range(40):
                        try:
                            success, outcome, pnl = self.api.get_trade_outcome(order_id, tempo)
                            if success:
                                profit = pnl
                                break
                        except Exception:
                            pass
                        await asyncio.sleep(0.2)

                if profit is None:
                    await asyncio.sleep(2)
                    saldo_atual = self.api.get_balance()
                    profit = saldo_atual - saldo_antes
                else:
                    saldo_atual = self.api.get_balance()

                self.saldo = saldo_atual
                delta = profit

                logger.info(f"[T{tentativa}] Resultado: {delta:+.2f} | saldo {saldo_atual:.2f}")

                if delta > 0:
                    # WIN
                    profit_final = delta - perda_acumulada
                    self.stats.add(True, profit_final)
                    r = {
                        "sucesso": True, "win": True,
                        "profit": profit_final,
                        "ativo": ativo, "direcao": direcao,
                        "tempo": tempo,
                        "tipo": tipo_res if gales_usados else "SEM GALE",
                        "gales_usados": gales_usados,
                        "multiplicador_usado": multiplicador,
                        "valor_entrada_usado": valor_atual,
                        "saldo": self.saldo,
                        "tipo_conta": self.tipo_conta
                    }
                    await self.bot.msg(UI.resultado_operacao(r, self.stats.get_stats()))
                    return r

                elif delta < 0:
                    perda_acumulada += abs(delta)
                    if tentativa < gales:
                        await self.bot.msg(f"🔴 Loss na tentativa {tentativa+1} — ativando próximo gale...")
                        continue
                    else:
                        self.stats.add(False, -perda_acumulada)
                        r = {
                            "sucesso": False, "win": False,
                            "profit": -perda_acumulada,
                            "ativo": ativo, "direcao": direcao,
                            "tempo": tempo,
                            "tipo": "LOSS",
                            "gales_usados": gales_usados,
                            "multiplicador_usado": multiplicador,
                            "valor_entrada_usado": valor_atual,
                            "saldo": self.saldo,
                            "tipo_conta": self.tipo_conta
                        }
                        await self.bot.msg(UI.resultado_operacao(r, self.stats.get_stats()))
                        return r

                else:
                    await self.bot.msg("⚠️ Saldo inalterado — verifique a plataforma.")
                    return {"sucesso": False, "erro": "Saldo inalterado"}

            except Exception as e:
                logger.error(f"Erro na ordem T{tentativa}: {e}")
                await self.bot.msg(f"❌ Erro: {e}")
                return {"sucesso": False, "erro": str(e)}

        return {"sucesso": False, "erro": "Loop de gales finalizado"}


# ==================== BOT PRINCIPAL ====================

class QuantumBot:
    def __init__(self):
        self.config = ConfigManager()
        self.stats = StatsManager()
        self.trader = IQTrader(self.config, self.stats, self)
        self.parser = SignalParser()
        self.client: Optional[TelegramClient] = None
        self.user_id = None
        self.processando = False

        # Credenciais do Telegram (use variáveis de ambiente)
        self.api_id = int(os.getenv("TG_API_ID", "22453120"))
        self.api_hash = os.getenv("TG_API_HASH", "89826a4104518e9ed650cdb451ad8b53")
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")

        self._states: Dict[int, str] = {}
        self._data: Dict[int, dict] = {}

    async def msg(self, texto: str):
        if self.user_id:
            try:
                await self.client.send_message(self.user_id, texto)
                logger.info(f"📤 Mensagem enviada: {texto[:50]}...")
            except Exception as e:
                logger.error(f"msg(): {e}")

    async def msg_btn(self, texto: str, botoes: list):
        if self.user_id:
            try:
                await self.client.send_message(self.user_id, texto, buttons=botoes)
                logger.info(f"📤 Mensagem com botões enviada: {texto[:50]}...")
            except Exception as e:
                logger.error(f"msg_btn(): {e}")

    async def run(self):
        if not self.token:
            logger.error("❌ TELEGRAM_BOT_TOKEN não configurado!")
            return

        self.client = TelegramClient("quantum_bot", self.api_id, self.api_hash)
        await self.client.start(bot_token=self.token)
        logger.info("✅ Bot conectado")

        c = self.client
        c.add_event_handler(self._h_start, events.NewMessage(pattern='/start'))
        c.add_event_handler(self._h_menu, events.NewMessage(pattern='/menu'))
        c.add_event_handler(self._h_config, events.NewMessage(pattern='/config'))
        c.add_event_handler(self._h_status, events.NewMessage(pattern='/status'))
        c.add_event_handler(self._h_stats, events.NewMessage(pattern='/stats'))
        c.add_event_handler(self._h_startauto, events.NewMessage(pattern='/startauto'))
        c.add_event_handler(self._h_stopauto, events.NewMessage(pattern='/stopauto'))
        c.add_event_handler(self._h_reset, events.NewMessage(pattern='/resetstats'))
        c.add_event_handler(self._h_help, events.NewMessage(pattern='/help'))
        c.add_event_handler(self._h_text, events.NewMessage)
        c.add_event_handler(self._h_callback, events.CallbackQuery)
        c.add_event_handler(self._h_sinal, events.NewMessage)

        await self.msg("🤖 **QUANTUM BOT v4.0** iniciado!\n\nDigite /menu para começar.")

        await c.run_until_disconnected()

    # ==================== HANDLERS ====================

    async def _h_start(self, event):
        self.user_id = event.sender_id
        if not self.config.configurado:
            await self._config_iniciar(event)
        else:
            await self._menu(event, reply=True)

    async def _h_menu(self, event):
        await self._menu(event, reply=True)

    async def _h_config(self, event):
        if not self.config.configurado:
            await self._config_iniciar(event)
        else:
            await self._config_mostrar(event, reply=True)

    async def _h_status(self, event):
        await self._status(event, reply=True)

    async def _h_stats(self, event):
        await self._stats(event, reply=True)

    async def _h_startauto(self, event):
        if not self.trader.conectado:
            await event.reply("⚠️ Conecte à IQ Option primeiro.\nUse /config e depois 🔗 Conectar IQ.")
            return
        self.config.set("modo_automatico", True)
        await event.reply("✅ Modo automático **ATIVADO**!\n📡 Aguardando sinais do canal...")

    async def _h_stopauto(self, event):
        self.config.set("modo_automatico", False)
        await event.reply("🛑 Modo automático **DESATIVADO**.")

    async def _h_reset(self, event):
        self.stats = StatsManager()
        await event.reply("✅ Estatísticas resetadas!")

    async def _h_help(self, event):
        await self._help(event, reply=True)

    # ==================== TEXTO E CALLBACK ====================

    async def _h_text(self, event):
        try:
            if event.message.out or not event.is_private:
                return
            texto = (event.message.raw_text or "").strip()
            if not texto or texto.startswith('/'):
                return

            uid = event.sender_id
            estado = self._states.get(uid)

            if estado is None:
                return

            # Configuração inicial (igual ao Robin Bot)
            if estado == "email":
                self._data[uid]["email"] = texto
                self._states[uid] = "senha"
                await event.reply("📌 **PASSO 2/9** — Digite sua **SENHA** da IQ Option:")

            elif estado == "senha":
                self._data[uid]["senha"] = texto
                self._states[uid] = "valor"
                await event.reply(
                    "📌 **PASSO 3/9** — **VALOR BASE** de entrada (R$):\n_(ex: 5.00)_"
                )

            elif estado == "valor":
                try:
                    v = float(texto.replace(',', '.'))
                    if v < 0.5:
                        await event.reply("⚠️ Mínimo R$ 0,50. Tente novamente:")
                        return
                    self._data[uid]["valor"] = v
                    self._states[uid] = "gales"
                    await event.reply("📌 **PASSO 4/9** — Quantos **GALES**? (0–5)\n_(0 = sem gale)_")
                except ValueError:
                    await event.reply("❌ Número inválido. Ex: `5.00`")

            elif estado == "gales":
                try:
                    g = int(texto)
                    if not (0 <= g <= 5):
                        await event.reply("❌ Digite entre 0 e 5.")
                        return
                    self._data[uid]["gales"] = g
                    self._states[uid] = "multiplicador"
                    await event.reply(
                        "📌 **PASSO 5/9** — **MULTIPLICADOR DE GALE**:\n\n"
                        "`2.0` → dobra (R$2 → R$4 → R$8)\n"
                        "`2.5` → 2.5x (R$2 → R$5 → R$12.50)\n"
                        "`1.5` → suave (R$2 → R$3 → R$4.50)\n\n"
                        "Digite o valor:"
                    )
                except ValueError:
                    await event.reply("❌ Digite um número inteiro. Ex: `2`")

            elif estado == "multiplicador":
                try:
                    m = float(texto.replace(',', '.'))
                    if not (1.1 <= m <= 5.0):
                        await event.reply("❌ Valor entre 1.1 e 5.0. Ex: `2.0`")
                        return
                    self._data[uid]["multiplicador"] = m
                    self._states[uid] = "antecipacao"
                    await event.reply(
                        "📌 **PASSO 6/9** — **ANTECIPAÇÃO** (segundos):\n"
                        "`5` = entra 5s antes | `0` = sem antecipação\n"
                        "_(Recomendado: 3 a 10s)_"
                    )
                except ValueError:
                    await event.reply("❌ Número inválido. Ex: `2.0`")

            elif estado == "antecipacao":
                try:
                    a = int(texto)
                    if not (0 <= a <= 60):
                        await event.reply("❌ Entre 0 e 60 segundos.")
                        return
                    self._data[uid]["antecipacao"] = a
                    self._states[uid] = "sincronizar"
                    await event.reply(
                        "📌 **PASSO 7/9** — **SINCRONIZAR COM VELA?**\n\n"
                        "🕯️ Aguarda o início exato da próxima vela.",
                        buttons=[[
                            Button.inline("✅ Sim (recomendado)", b"cfg_sinc_sim"),
                            Button.inline("❌ Não", b"cfg_sinc_nao")
                        ]]
                    )
                except ValueError:
                    await event.reply("❌ Número inteiro. Ex: `5`")

            elif estado == "sincronizar":
                await event.reply("⬆️ Clique em um dos botões acima.")

            elif estado == "stop_win":
                try:
                    sw = float(texto.replace(',', '.'))
                    if sw < 10:
                        await event.reply("⚠️ Mínimo R$ 10,00")
                        return
                    self._data[uid]["stop_win"] = sw
                    self._states[uid] = "stop_loss"
                    await event.reply("📌 **PASSO 8/9** — **STOP LOSS** (R$):\n_(ex: 50.00)_")
                except ValueError:
                    await event.reply("❌ Número inválido. Ex: `100.00`")

            elif estado == "stop_loss":
                try:
                    sl = float(texto.replace(',', '.'))
                    if sl < 5:
                        await event.reply("⚠️ Mínimo R$ 5,00")
                        return
                    self._data[uid]["stop_loss"] = sl
                    self._states[uid] = "tipo_conta"
                    await event.reply(
                        "🏦 **Tipo de conta IQ Option:**",
                        buttons=[[
                            Button.inline("💰 REAL", b"cfg_conta_real"),
                            Button.inline("🎯 TREINAMENTO", b"cfg_conta_demo")
                        ]]
                    )
                except ValueError:
                    await event.reply("❌ Número inválido. Ex: `50.00`")

            elif estado == "tipo_conta":
                await event.reply("⬆️ Clique em um dos botões acima.")

            elif estado == "canal":
                try:
                    canal_id = int(texto)
                    self._data[uid]["canal_id"] = canal_id
                    self._states[uid] = None
                    await self._config_finalizar(event, uid, reply=True)
                except ValueError:
                    await event.reply("❌ ID inválido. Ex: `-100123456789`")

            # Edições (simplificadas)
            elif estado.startswith("edit_"):
                campo = estado[5:]
                if campo == "email":
                    self.config.set("email", texto)
                elif campo == "senha":
                    self.config.set("senha", texto)
                elif campo == "valor":
                    try:
                        self.config.set("valor_entrada", float(texto.replace(',', '.')))
                    except:
                        await event.reply("❌ Número inválido")
                        return
                elif campo == "gales":
                    try:
                        self.config.set("gales", int(texto))
                    except:
                        await event.reply("❌ Número inválido")
                        return
                elif campo == "multiplicador":
                    try:
                        self.config.set("multiplicador", float(texto.replace(',', '.')))
                    except:
                        await event.reply("❌ Número inválido")
                        return
                elif campo == "antecipacao":
                    try:
                        self.config.set("antecipacao", int(texto))
                    except:
                        await event.reply("❌ Número inválido")
                        return
                elif campo == "stop_win":
                    try:
                        self.config.set("stop_win", float(texto.replace(',', '.')))
                    except:
                        await event.reply("❌ Número inválido")
                        return
                elif campo == "stop_loss":
                    try:
                        self.config.set("stop_loss", float(texto.replace(',', '.')))
                    except:
                        await event.reply("❌ Número inválido")
                        return
                elif campo == "canal":
                    try:
                        self.config.set("canal_id", int(texto))
                    except:
                        await event.reply("❌ ID inválido")
                        return
                
                self._limpar_estado(uid)
                await event.reply(f"✅ {campo} atualizado!")
                await self._config_mostrar(event, reply=True)

        except Exception as e:
            logger.error(f"_h_text: {e}")

    async def _h_callback(self, event):
        try:
            uid = event.sender_id
            data = event.data.decode('utf-8')

            if data == "menu":
                await self._menu(event, reply=False)
            elif data == "status":
                await self._status(event, reply=False)
            elif data == "config":
                if not self.config.configurado:
                    await self._config_iniciar_cb(event)
                else:
                    await self._config_mostrar(event, reply=False)
            elif data == "startauto":
                if not self.trader.conectado:
                    await event.edit("⚠️ Conecte à IQ Option primeiro!", buttons=self._bts_voltar())
                else:
                    self.config.set("modo_automatico", True)
                    await event.edit("✅ Modo automático **ATIVADO**!\n📡 Aguardando sinais...", buttons=self._bts_voltar())
            elif data == "stopauto":
                self.config.set("modo_automatico", False)
                await event.edit("🛑 Modo automático **DESATIVADO**.", buttons=self._bts_voltar())
            elif data == "stats":
                await self._stats(event, reply=False)
            elif data == "resetstats":
                self.stats = StatsManager()
                await event.edit("✅ Estatísticas resetadas!", buttons=self._bts_voltar())
            elif data == "conectar":
                await self._cb_conectar(event)
            elif data == "help":
                await self._help(event, reply=False)
            elif data == "cancelar":
                await self._cb_cancelar(event, uid)

            # Configuração
            elif data == "cfg_sinc_sim":
                self._data[uid]["sincronizar"] = True
                self._states[uid] = "stop_win"
                await event.edit("✅ Sincronização **ATIVADA**!\n\n📌 **PASSO 8/9** — **STOP WIN** (R$):")
            elif data == "cfg_sinc_nao":
                self._data[uid]["sincronizar"] = False
                self._states[uid] = "stop_win"
                await event.edit("ℹ️ Sincronização **desativada**.\n\n📌 **PASSO 8/9** — **STOP WIN** (R$):")
            elif data == "cfg_conta_real":
                self._data[uid]["tipo_conta"] = "real"
                self._states[uid] = "canal"
                await event.edit("💰 Conta **REAL** selecionada!\n\n📡 **ID do canal de sinais**:\nDigite abaixo:")
            elif data == "cfg_conta_demo":
                self._data[uid]["tipo_conta"] = "treinamento"
                self._states[uid] = "canal"
                await event.edit("🎯 Conta **TREINAMENTO** selecionada!\n\n📡 **ID do canal de sinais**:\nDigite abaixo:")

            # Edições
            elif data.startswith("edit_"):
                campo = data[5:]
                self._states[uid] = f"edit_{campo}"
                self._data[uid] = {}

                if campo == "sincronizar":
                    await event.edit(
                        "🕯️ **Sincronizar com início de vela?**",
                        buttons=[[
                            Button.inline("✅ Sim", b"edt_sinc_sim"),
                            Button.inline("❌ Não", b"edt_sinc_nao")
                        ]]
                    )
                elif campo == "tipo_conta":
                    await event.edit(
                        "🏦 **Tipo de conta:**",
                        buttons=[[
                            Button.inline("💰 REAL", b"edt_conta_real"),
                            Button.inline("🎯 TREINAMENTO", b"edt_conta_demo")
                        ]]
                    )
                else:
                    label = {
                        "email": "📧 Digite o NOVO EMAIL:",
                        "senha": "🔐 Digite a NOVA SENHA:",
                        "valor": "💵 Digite o NOVO VALOR (R$):",
                        "gales": "🎯 Quantos GALES? (0–5):",
                        "multiplicador": "✖️ Novo MULTIPLICADOR:",
                        "antecipacao": "⏱️ Nova ANTECIPAÇÃO (s):",
                        "stop_win": "🟢 Novo STOP WIN (R$):",
                        "stop_loss": "🔴 Novo STOP LOSS (R$):",
                        "canal": "📡 Novo ID do canal:"
                    }.get(campo, "Digite o novo valor:")
                    await event.edit(label, buttons=[[Button.inline("❌ Cancelar", b"cancelar")]])

            elif data == "edt_sinc_sim":
                self.config.set("sincronizar_vela", True)
                self._limpar_estado(uid)
                await event.edit("✅ Sincronização **ATIVADA**!")
                await self._config_mostrar_msg(uid)
            elif data == "edt_sinc_nao":
                self.config.set("sincronizar_vela", False)
                self._limpar_estado(uid)
                await event.edit("ℹ️ Sincronização **desativada**.")
                await self._config_mostrar_msg(uid)
            elif data == "edt_conta_real":
                self.config.set("tipo_conta", "real")
                self._limpar_estado(uid)
                await event.edit("💰 Conta **REAL** atualizada!")
                await self._config_mostrar_msg(uid)
            elif data == "edt_conta_demo":
                self.config.set("tipo_conta", "treinamento")
                self._limpar_estado(uid)
                await event.edit("🎯 Conta **TREINAMENTO** atualizada!")
                await self._config_mostrar_msg(uid)

            try:
                await event.answer()
            except Exception:
                pass

        except Exception as e:
            logger.error(f"_h_callback: {e}")
            try:
                await event.answer("❌ Erro interno", alert=True)
            except Exception:
                pass

    # ==================== SINAIS ====================

    async def _h_sinal(self, event):
        try:
            if event.message.out:
                return
            texto = (event.message.raw_text or "").strip()
            if not texto:
                return

            canal_id = self.config.get("canal_id")
            if not canal_id or event.chat_id != canal_id:
                return
            if not self.config.get("modo_automatico", False):
                return
            if self.processando:
                return

            dados = self.parser.parse(texto)
            if not dados['valido']:
                return

            await self._executar_sinal(dados)

        except Exception as e:
            logger.error(f"_h_sinal: {e}")

    async def _executar_sinal(self, dados: dict):
        self.processando = True
        antec = self.config.get("antecipacao", 5)
        sinc = self.config.get("sincronizar_vela", True)

        try:
            await self.msg(UI.sinal_recebido(dados, antec, sinc))

            horario_sincronizado = False
            if dados['horario']:
                try:
                    nums = re.findall(r'\d+', dados['horario'])
                    if len(nums) >= 2:
                        hora, minuto = int(nums[0]), int(nums[1])
                        agora = datetime.now()
                        alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
                        if alvo <= agora:
                            alvo += timedelta(days=1)

                        momento_entrar = alvo - timedelta(seconds=antec)
                        espera = (momento_entrar - agora).total_seconds()

                        if espera > 0:
                            ts = momento_entrar.strftime("%H:%M:%S")
                            await self.msg(
                                f"⏰ Sinal para: **{dados['horario']}**\n"
                                f"⏱️ Entrada: **{ts}** ({antec}s antes)\n"
                                f"⏳ Aguardando **{espera:.0f}s**..."
                            )
                            await asyncio.sleep(espera)
                        else:
                            await self.msg(f"⚡ Entrada imediata")
                        horario_sincronizado = True
                except Exception as ex:
                    logger.warning(f"Erro ao calcular horário: {ex}")

            resultado = await self.trader.executar(
                dados['ativo'], dados['direcao'], dados['tempo'],
                skip_sinc=horario_sincronizado
            )

            if not resultado.get('sucesso') and resultado.get('erro'):
                await self.msg(UI.erro_operacao(resultado['erro']))

        except Exception as e:
            logger.error(f"_executar_sinal: {e}")
            await self.msg(f"❌ Erro ao executar sinal: {e}")
        finally:
            self.processando = False
            await self.msg(UI.aguardando_sinais())

    # ==================== MÉTODOS AUXILIARES ====================

    async def _cb_conectar(self, event):
        try:
            if self.trader.conectado:
                await event.edit("✅ Já está conectado!", buttons=self._bts_voltar())
                return

            email = self.config.get("email")
            senha = self.config.get("senha")
            tipo = self.config.get("tipo_conta", "real")

            if not email or not senha:
                await event.edit("⚠️ Credenciais não configuradas!\nUse /config.", buttons=self._bts_voltar())
                return

            await event.edit("🔄 Conectando à IQ Option...")
            sucesso = await self.trader.conectar(email, senha, tipo)

            if sucesso:
                await event.edit("✅ Conectado com sucesso!", buttons=self._bts_voltar())
            else:
                await event.edit("❌ Falha na conexão!", buttons=self._bts_voltar())
        except Exception as e:
            logger.error(f"_cb_conectar: {e}")
            await event.edit(f"❌ Erro: {e}", buttons=self._bts_voltar())

    async def _cb_cancelar(self, event, uid: int):
        self._limpar_estado(uid)
        await event.edit("❌ Operação cancelada.", buttons=self._bts_voltar())

    def _limpar_estado(self, uid: int):
        self._states.pop(uid, None)
        self._data.pop(uid, None)

    def _bts_menu(self):
        return [
            [Button.inline("📊 Status", b"status")],
            [Button.inline("⚙️ Configurações", b"config")],
            [Button.inline("▶️ Iniciar Auto", b"startauto"), Button.inline("⏹️ Parar Auto", b"stopauto")],
            [Button.inline("📈 Estatísticas", b"stats"), Button.inline("🔄 Reset Stats", b"resetstats")],
            [Button.inline("🔗 Conectar IQ", b"conectar"), Button.inline("❓ Ajuda", b"help")],
        ]

    def _bts_voltar(self):
        return [[Button.inline("📋 Menu", b"menu")]]

    def _bts_config(self):
        return [
            [Button.inline("✏️ Email", b"edit_email")],
            [Button.inline("✏️ Senha", b"edit_senha")],
            [Button.inline("💵 Entrada", b"edit_valor")],
            [Button.inline("🎯 Gales", b"edit_gales")],
            [Button.inline("✖️ Multiplicador", b"edit_multiplicador")],
            [Button.inline("⏱️ Antecipação", b"edit_antecipacao")],
            [Button.inline("🕯️ Sinc. Vela", b"edit_sincronizar")],
            [Button.inline("🟢 Stop Win", b"edit_stop_win")],
            [Button.inline("🔴 Stop Loss", b"edit_stop_loss")],
            [Button.inline("🏦 Tipo Conta", b"edit_tipo_conta")],
            [Button.inline("📡 Canal", b"edit_canal")],
            [Button.inline("📋 Menu", b"menu")],
        ]

    async def _menu(self, event, reply: bool):
        if reply:
            await event.reply(UI.menu(), buttons=self._bts_menu())
        else:
            await event.edit(UI.menu(), buttons=self._bts_menu())

    async def _status(self, event, reply: bool):
        s = self.stats.get_stats()
        msg = UI.status_sistema(self.trader.conectado, self.trader.saldo, self.trader.tipo_conta, s)
        bts = [[Button.inline("🔄 Atualizar", b"status"), Button.inline("📋 Menu", b"menu")]]
        if reply:
            await event.reply(msg, buttons=bts)
        else:
            await event.edit(msg, buttons=bts)

    async def _stats(self, event, reply: bool):
        s = self.stats.get_stats()
        td = s.get('total_trades', 0)
        tw = s.get('total_wins', 0)
        dd = s.get('daily_trades', 0)
        dw = s.get('daily_wins', 0)
        parte_dia = f"📅 **HOJE**\n📈 {dd} trades | 🟢 {dw} | 🔴 {s.get('daily_losses',0)}"
        if dd:
            parte_dia += f" | 🎯 {dw/dd*100:.1f}%\n💵 R$ {s.get('daily_profit',0):,.2f}"
        else:
            parte_dia += "\n💵 R$ 0,00"

        parte_total = f"🏆 **TOTAL**\n📈 {td} trades | 🟢 {tw} | 🔴 {s.get('total_losses',0)}"
        if td:
            parte_total += f" | 🎯 {tw/td*100:.1f}%\n💵 R$ {s.get('total_profit',0):,.2f}"
        else:
            parte_total += "\n💵 R$ 0,00"

        msg = f"📊 **ESTATÍSTICAS**\n━━━━━━━━━━━━━━━━━━━━━━━\n\n{parte_dia}\n\n{parte_total}"
        bts = [[Button.inline("🔄 Atualizar", b"stats"), Button.inline("📋 Menu", b"menu")]]
        if reply:
            await event.reply(msg, buttons=bts)
        else:
            await event.edit(msg, buttons=bts)

    async def _help(self, event, reply: bool):
        msg = """
📚 **COMANDOS**
━━━━━━━━━━━━━━━━━━━━━━━

/start — Iniciar / configurar
/config — Ver/alterar configurações
/menu — Menu principal
/status — Status do sistema
/stats — Estatísticas
/startauto — Ativar robô
/stopauto — Desativar robô
/resetstats — Resetar stats
/help — Esta mensagem

🆕 **v4.0 — NOVIDADES:**
✅ Nova API Sudip-T/iqoption-api
✅ WebSocket para dados em tempo real
✅ Comunicação detalhada no PV
📊 Resultados formatados com emojis
🔄 Status em tempo real
✅ Apuração completa de cada operação
        """
        bts = self._bts_voltar()
        if reply:
            await event.reply(msg, buttons=bts)
        else:
            await event.edit(msg, buttons=bts)

    async def _config_mostrar(self, event, reply: bool):
        dados = {k: self.config.get(k) for k in self.config.DEFAULTS}
        msg = UI.configuracao_resumo(dados)
        if reply:
            await event.reply(msg, buttons=self._bts_config())
        else:
            await event.edit(msg, buttons=self._bts_config())

    async def _config_mostrar_msg(self, uid: int):
        dados = {k: self.config.get(k) for k in self.config.DEFAULTS}
        await self.client.send_message(uid, UI.configuracao_resumo(dados), buttons=self._bts_config())

    async def _config_iniciar(self, event):
        uid = event.sender_id
        self._data[uid] = {}
        self._states[uid] = "email"
        await event.reply(
            "🔐 **CONFIGURAÇÃO DO QUANTUM BOT v4.0**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📌 **PASSO 1/9 — Email**\n\n"
            "Digite seu **EMAIL** da IQ Option:"
        )

    async def _config_iniciar_cb(self, event):
        uid = event.sender_id
        self._data[uid] = {}
        self._states[uid] = "email"
        await event.edit(
            "🔐 **CONFIGURAÇÃO DO QUANTUM BOT v4.0**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📌 **PASSO 1/9 — Email**\n\n"
            "Digite seu **EMAIL** da IQ Option:",
            buttons=[[Button.inline("❌ Cancelar", b"cancelar")]]
        )

    async def _config_finalizar(self, event, uid: int, reply: bool):
        d = self._data.get(uid, {})

        self.config.set("email", d.get("email"))
        self.config.set("senha", d.get("senha"))
        self.config.set("valor_entrada", d.get("valor", 5.0))
        self.config.set("gales", d.get("gales", 2))
        self.config.set("multiplicador", d.get("multiplicador", 2.0))
        self.config.set("antecipacao", d.get("antecipacao", 5))
        self.config.set("sincronizar_vela", d.get("sincronizar", True))
        self.config.set("stop_win", d.get("stop_win", 100.0))
        self.config.set("stop_loss", d.get("stop_loss", 50.0))
        self.config.set("tipo_conta", d.get("tipo_conta", "real"))
        self.config.set("canal_id", d.get("canal_id"))
        self.config.set("configurado", True)

        self._limpar_estado(uid)

        if reply:
            await event.reply("🔄 Conectando à IQ Option...")
        else:
            await event.edit("🔄 Conectando à IQ Option...")

        ok = await self.trader.conectar(d.get("email"), d.get("senha"), d.get("tipo_conta", "real"))

        if ok:
            await self.client.send_message(
                uid,
                f"✅ **CONFIGURAÇÃO COMPLETA!**\n\n"
                f"{UI.configuracao_resumo({k: self.config.get(k) for k in self.config.DEFAULTS})}\n\n"
                "🚀 Use `/startauto` para ativar o robô!\n"
                "📡 Aguardando sinais do canal configurado..."
            )
        else:
            await self.client.send_message(
                uid,
                "❌ Falha na conexão com a IQ Option.\n"
                "Verifique email/senha e tente novamente."
            )


# ==================== MAIN ====================

async def main():
    bot = QuantumBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        print("\n🛑 Bot interrompido")
        logger.info("Bot interrompido")
    except Exception as e:
        logger.error(f"Erro fatal: {e}\n{traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
