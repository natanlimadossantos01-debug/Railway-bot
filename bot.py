#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔═══════════════════════════════════════════════════════════════╗
║           🤖 ROBIN BOT v4.0 - MULTI-USUÁRIO                 ║
║                                                               ║
║  ✅ Cada usuário tem suas próprias configurações              ║
║  ✅ Cada usuário tem suas próprias estatísticas               ║
║  ✅ Cada usuário pode ter seu próprio canal de sinais         ║
║  ✅ Admin pode desativar/ativar usuários                     ║
╚═══════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import logging
import re
import sys
import os
import sqlite3
import traceback
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from telethon import TelegramClient, events, Button

# ==================== LOG ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler('robin_bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("RobinBot")

# ==================== BANCO DE DADOS MULTI-USUÁRIO ====================

class Database:
    def __init__(self):
        self.db_path = "robin_users.db"
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                email TEXT DEFAULT '',
                senha TEXT DEFAULT '',
                valor_entrada REAL DEFAULT 2.0,
                gales INTEGER DEFAULT 2,
                multiplicador REAL DEFAULT 2.0,
                antecipacao INTEGER DEFAULT 5,
                sincronizar_vela INTEGER DEFAULT 1,
                stop_win REAL DEFAULT 100.0,
                stop_loss REAL DEFAULT 50.0,
                tipo_conta TEXT DEFAULT 'real',
                canal_id INTEGER DEFAULT 0,
                configurado INTEGER DEFAULT 0,
                bot_ligado INTEGER DEFAULT 0,
                conectado INTEGER DEFAULT 0,
                ativo INTEGER DEFAULT 1,
                cadastro TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS stats (
                user_id INTEGER PRIMARY KEY,
                daily_profit REAL DEFAULT 0.0,
                daily_trades INTEGER DEFAULT 0,
                daily_wins INTEGER DEFAULT 0,
                daily_losses INTEGER DEFAULT 0,
                total_profit REAL DEFAULT 0.0,
                total_trades INTEGER DEFAULT 0,
                total_wins INTEGER DEFAULT 0,
                total_losses INTEGER DEFAULT 0,
                ultimo_reset TEXT DEFAULT CURRENT_DATE
            );
            
            CREATE TABLE IF NOT EXISTS admin (
                user_id INTEGER PRIMARY KEY,
                is_admin INTEGER DEFAULT 0
            );
        """)
        
        # Admin padrão (configure via env)
        admin_id = int(os.getenv("ADMIN_ID", "0"))
        if admin_id:
            conn.execute("INSERT OR IGNORE INTO admin (user_id, is_admin) VALUES (?, 1)", (admin_id,))
        
        conn.commit()
        conn.close()
        logger.info("✅ Banco de dados inicializado")

    # ========== USERS ==========
    
    def get_user(self, user_id: int) -> Optional[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def create_user(self, user_id: int, username: str = "", first_name: str = ""):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR IGNORE INTO users (user_id, username, first_name, ativo) 
            VALUES (?, ?, ?, 1)
        """, (user_id, username, first_name))
        conn.execute("INSERT OR IGNORE INTO stats (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
        logger.info(f"✅ Usuário criado: {user_id} ({first_name})")

    def update_user(self, user_id: int, **kwargs):
        if not kwargs:
            return
        conn = sqlite3.connect(self.db_path)
        sets = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [user_id]
        conn.execute(f"UPDATE users SET {sets} WHERE user_id=?", vals)
        conn.commit()
        conn.close()

    def get_config(self, user_id: int) -> dict:
        user = self.get_user(user_id)
        if not user:
            return {}
        return {
            "email": user.get("email"),
            "senha": user.get("senha"),
            "valor_entrada": user.get("valor_entrada", 2.0),
            "gales": user.get("gales", 2),
            "multiplicador": user.get("multiplicador", 2.0),
            "antecipacao": user.get("antecipacao", 5),
            "sincronizar_vela": bool(user.get("sincronizar_vela", 1)),
            "stop_win": user.get("stop_win", 100.0),
            "stop_loss": user.get("stop_loss", 50.0),
            "tipo_conta": user.get("tipo_conta", "real"),
            "canal_id": user.get("canal_id"),
            "configurado": bool(user.get("configurado", 0)),
            "bot_ligado": bool(user.get("bot_ligado", 0)),
            "ativo": bool(user.get("ativo", 1))
        }

    def save_config(self, user_id: int, config: dict):
        self.update_user(user_id,
            email=config.get("email"),
            senha=config.get("senha"),
            valor_entrada=config.get("valor_entrada", 2.0),
            gales=config.get("gales", 2),
            multiplicador=config.get("multiplicador", 2.0),
            antecipacao=config.get("antecipacao", 5),
            sincronizar_vela=1 if config.get("sincronizar_vela", True) else 0,
            stop_win=config.get("stop_win", 100.0),
            stop_loss=config.get("stop_loss", 50.0),
            tipo_conta=config.get("tipo_conta", "real"),
            canal_id=config.get("canal_id"),
            configurado=1
        )

    def set_bot_status(self, user_id: int, ligado: bool):
        self.update_user(user_id, bot_ligado=1 if ligado else 0)

    def set_active(self, user_id: int, ativo: bool):
        self.update_user(user_id, ativo=1 if ativo else 0)

    def get_all_users(self) -> list:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT u.user_id, u.username, u.first_name, u.bot_ligado, u.ativo, u.email
            FROM users u
            ORDER BY u.cadastro DESC
        """)
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def is_admin(self, user_id: int) -> bool:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT is_admin FROM admin WHERE user_id=?", (user_id,))
        row = c.fetchone()
        conn.close()
        return bool(row and row[0])

    # ========== STATS ==========

    def get_stats(self, user_id: int) -> dict:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Reseta diário se necessário
        hoje = datetime.now().strftime("%Y-%m-%d")
        c.execute("SELECT ultimo_reset FROM stats WHERE user_id=?", (user_id,))
        row = c.fetchone()
        if row and row[0] != hoje:
            c.execute("""
                UPDATE stats SET 
                    daily_profit=0, daily_trades=0, daily_wins=0, daily_losses=0,
                    ultimo_reset=?
                WHERE user_id=?
            """, (hoje, user_id))
            conn.commit()
        
        c.execute("SELECT * FROM stats WHERE user_id=?", (user_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else {}

    def update_stats(self, user_id: int, win: bool, profit: float):
        conn = sqlite3.connect(self.db_path)
        hoje = datetime.now().strftime("%Y-%m-%d")
        
        # Reseta diário
        conn.execute("""
            UPDATE stats SET 
                daily_profit=0, daily_trades=0, daily_wins=0, daily_losses=0,
                ultimo_reset=?
            WHERE user_id=? AND ultimo_reset != ?
        """, (hoje, user_id, hoje))
        
        # Atualiza
        conn.execute("""
            UPDATE stats SET 
                daily_trades = daily_trades + 1,
                total_trades = total_trades + 1,
                daily_profit = daily_profit + ?,
                total_profit = total_profit + ?,
                daily_wins = daily_wins + ?,
                total_wins = total_wins + ?,
                daily_losses = daily_losses + ?,
                total_losses = total_losses + ?
            WHERE user_id = ?
        """, (profit, profit, 
              1 if win else 0, 1 if win else 0,
              0 if win else 1, 0 if win else 1,
              user_id))
        conn.commit()
        conn.close()

    def reset_stats(self, user_id: int):
        conn = sqlite3.connect(self.db_path)
        hoje = datetime.now().strftime("%Y-%m-%d")
        conn.execute("""
            UPDATE stats SET 
                daily_profit=0, daily_trades=0, daily_wins=0, daily_losses=0,
                total_profit=0, total_trades=0, total_wins=0, total_losses=0,
                ultimo_reset=?
            WHERE user_id=?
        """, (hoje, user_id))
        conn.commit()
        conn.close()


# ==================== INTERFACE ====================

class UI:
    @staticmethod
    def menu():
        return """
╔═══════════════════════════════════════════╗
║                                           ║
║           🤖 ROBIN BOT v4.0              ║
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
        ct = "💰 REAL" if tipo == "real" else "🎯 TREINAMENTO"
        dt = s.get('daily_trades', 0)
        dw = s.get('daily_wins', 0)
        wr = f"{dw/dt*100:.1f}%" if dt else "—"
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
        titulo = "🟢 APURAÇÃO ROBIN 🟢" if win else "🔴 APURAÇÃO ROBIN 🔴"
        ico = "✅" if win else "⛔"
        
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

💵 **Resultado Diário:**
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


# ==================== IQ TRADER ====================

class IQTrader:
    def __init__(self, db: Database, user_id: int):
        self.db = db
        self.user_id = user_id
        self.api = None
        self.conectado = False
        self.saldo = 0.0
        self.tipo_conta = "real"
        self._ultima_conexao = 0

    async def conectar(self) -> bool:
        try:
            config = self.db.get_config(self.user_id)
            email = config.get("email")
            senha = config.get("senha")
            tipo = config.get("tipo_conta", "real")

            if not email or not senha:
                return False

            try:
                from iqoptionapi.stable_api import IQ_Option
            except ImportError:
                logger.error("iqoptionapi não instalada")
                return False

            self.api = IQ_Option(email, senha)
            ok = self.api.connect()

            if ok and self.api.check_connect():
                self.conectado = True
                self._ultima_conexao = time.time()
                self.saldo = self.api.get_balance()
                self.tipo_conta = tipo
                logger.info(f"✅ Usuário {self.user_id} conectado à IQ Option")
                return True
            else:
                logger.error(f"❌ Falha conexão user {self.user_id}")
                return False

        except Exception as e:
            logger.error(f"Erro conexão user {self.user_id}: {e}")
            return False

    async def executar(self, ativo: str, direcao: str, tempo: int, msg_fn, skip_sinc: bool = False) -> dict:
        if not self.conectado or not self.api:
            return {"sucesso": False, "erro": "Não conectado"}

        config = self.db.get_config(self.user_id)
        stats = self.db.get_stats(self.user_id)
        
        stop_loss = config.get("stop_loss", 50.0)
        stop_win = config.get("stop_win", 100.0)
        daily = stats.get('daily_profit', 0)

        if daily <= -stop_loss:
            await msg_fn(f"🛑 Stop Loss atingido: R$ {stop_loss:,.2f}")
            return {"sucesso": False, "erro": "Stop Loss"}

        if daily >= stop_win:
            await msg_fn(f"🎯 Stop Win atingido: R$ {stop_win:,.2f}")
            return {"sucesso": False, "erro": "Stop Win"}

        ativo_iq, modo = AtivoMapper.mapear(ativo)
        if not ativo_iq:
            return {"sucesso": False, "erro": f"Ativo '{ativo}' não mapeado"}

        dir_api = "put" if direcao.upper() == "PUT" else "call"
        valor_base = config.get("valor_entrada", 2.0)
        gales = config.get("gales", 2)
        multiplicador = config.get("multiplicador", 2.0)
        antecipacao = config.get("antecipacao", 5)
        sinc_vela = config.get("sincronizar_vela", True)

        if sinc_vela and not skip_sinc:
            await VelaSync.aguardar(tempo, antecipacao, msg_fn)

        valor_atual = valor_base
        gales_usados = 0
        tipo_res = "SEM GALE"
        perda_acumulada = 0.0

        for tentativa in range(gales + 1):
            if tentativa > 0:
                valor_atual = valor_base * (multiplicador ** tentativa)
                gales_usados = tentativa
                tipo_res = f"WIN G{tentativa}"
                await msg_fn(f"🔄 **GALE {tentativa}**\n✖️ {multiplicador}x → R$ {valor_atual:.2f}")

            try:
                saldo_antes = self.api.get_balance()
                agora_buy = datetime.now()
                candle_start = VelaSync.proximo_inicio(tempo, agora_buy)
                candle_close = candle_start + timedelta(minutes=tempo)

                await msg_fn(UI.operacao_executando(valor_atual, ativo, direcao, tempo, tentativa))

                buy_result = self.api.buy(valor_atual, ativo_iq, dir_api, tempo)
                
                if isinstance(buy_result, tuple):
                    ok, order_id = buy_result
                else:
                    ok = buy_result
                    order_id = None

                if not ok:
                    await msg_fn("❌ Falha na execução da ordem")
                    return {"sucesso": False, "erro": "Falha ao comprar"}

                espera = (candle_close - datetime.now()).total_seconds() - 1
                if espera > 0:
                    await asyncio.sleep(espera)

                profit = None
                if order_id:
                    for _ in range(40):
                        try:
                            profit = self.api.check_win_v3(order_id)
                            if profit is not None:
                                break
                        except:
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

                if delta > 0:
                    profit_final = delta - perda_acumulada
                    self.db.update_stats(self.user_id, True, profit_final)
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
                    await msg_fn(UI.resultado_operacao(r, self.db.get_stats(self.user_id)))
                    return r

                elif delta < 0:
                    perda_acumulada += abs(delta)
                    if tentativa < gales:
                        await msg_fn(f"🔴 Loss na tentativa {tentativa+1} — ativando próximo gale...")
                        continue
                    else:
                        self.db.update_stats(self.user_id, False, -perda_acumulada)
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
                        await msg_fn(UI.resultado_operacao(r, self.db.get_stats(self.user_id)))
                        return r

                else:
                    await msg_fn("⚠️ Saldo inalterado")
                    return {"sucesso": False, "erro": "Saldo inalterado"}

            except Exception as e:
                logger.error(f"Erro ordem user {self.user_id}: {e}")
                await msg_fn(f"❌ Erro: {e}")
                return {"sucesso": False, "erro": str(e)}

        return {"sucesso": False, "erro": "Loop finalizado"}


# ==================== BOT PRINCIPAL ====================

class RobinBot:
    def __init__(self):
        self.db = Database()
        self.parser = SignalParser()
        self.client: Optional[TelegramClient] = None
        self.traders: Dict[int, IQTrader] = {}
        self.processando: Dict[int, bool] = {}

        self.api_id = int(os.getenv("TG_API_ID", "22453120"))
        self.api_hash = os.getenv("TG_API_HASH", "89826a4104518e9ed650cdb451ad8b53")
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "8233598336:AAHUtMg14-2hcOFObRhrBGsO4JIEyyA7gtI")

        self._states: Dict[int, str] = {}
        self._data: Dict[int, dict] = {}

    async def msg(self, user_id: int, texto: str):
        try:
            await self.client.send_message(user_id, texto)
            logger.info(f"📤 Msg para {user_id}: {texto[:50]}...")
        except Exception as e:
            logger.error(f"msg(): {e}")

    async def msg_btn(self, user_id: int, texto: str, botoes: list):
        try:
            await self.client.send_message(user_id, texto, buttons=botoes)
        except Exception as e:
            logger.error(f"msg_btn(): {e}")

    async def run(self):
        self.client = TelegramClient("robin_bot", self.api_id, self.api_hash)
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
        c.add_event_handler(self._h_admin, events.NewMessage(pattern='/admin'))
        c.add_event_handler(self._h_desativar, events.NewMessage(pattern='/desativar'))
        c.add_event_handler(self._h_ativar, events.NewMessage(pattern='/ativar'))
        c.add_event_handler(self._h_text, events.NewMessage)
        c.add_event_handler(self._h_callback, events.CallbackQuery)
        c.add_event_handler(self._h_sinal, events.NewMessage)

        await c.run_until_disconnected()

    # ==================== HANDLERS ====================

    async def _h_start(self, event):
        user_id = event.sender_id
        username = event.sender.username or ""
        first_name = event.sender.first_name or f"User{user_id}"
        
        self.db.create_user(user_id, username, first_name)
        
        await event.reply(f"""
👋 Olá, *{first_name}*!

✅ **Acesso liberado!**

📚 **COMANDOS:**
/config - Configurar IQ Option
/startauto - Ligar robô
/stopauto - Desligar robô
/status - Ver status
/stats - Estatísticas
/menu - Menu principal
        """)

    async def _h_menu(self, event):
        user_id = event.sender_id
        await self._menu(user_id, event, reply=True)

    async def _h_config(self, event):
        user_id = event.sender_id
        config = self.db.get_config(user_id)
        if not config.get("configurado"):
            await self._config_iniciar(event)
        else:
            await self._config_mostrar(event, reply=True)

    async def _h_status(self, event):
        user_id = event.sender_id
        await self._status(user_id, event, reply=True)

    async def _h_stats(self, event):
        user_id = event.sender_id
        await self._stats(user_id, event, reply=True)

    async def _h_startauto(self, event):
        user_id = event.sender_id
        config = self.db.get_config(user_id)
        
        if not config.get("configurado"):
            await event.reply("⚠️ Configure primeiro: /config")
            return
        
        # Conecta à IQ
        trader = IQTrader(self.db, user_id)
        ok = await trader.conectar()
        
        if ok:
            self.traders[user_id] = trader
            self.db.set_bot_status(user_id, True)
            self.processando[user_id] = False
            await event.reply(f"""
✅ **Robô ATIVADO!**

📡 Monitorando canal: `{config.get('canal_id', 'Não configurado')}`
💰 Entrada: R$ {config.get('valor_entrada', 2):.2f}
🎯 Gales: {config.get('gales', 2)}
            """)
        else:
            await event.reply("❌ Falha na conexão com IQ Option!\nVerifique email/senha em /config")

    async def _h_stopauto(self, event):
        user_id = event.sender_id
        self.db.set_bot_status(user_id, False)
        if user_id in self.traders:
            self.traders[user_id].conectado = False
            del self.traders[user_id]
        await event.reply("🛑 **Robô DESATIVADO!**")

    async def _h_reset(self, event):
        user_id = event.sender_id
        self.db.reset_stats(user_id)
        await event.reply("✅ Estatísticas resetadas!")

    async def _h_help(self, event):
        await event.reply("""
📚 **COMANDOS**

/start — Iniciar
/config — Configurar IQ Option
/startauto — Ativar robô
/stopauto — Desativar robô
/status — Status do sistema
/stats — Estatísticas
/resetstats — Resetar stats
/help — Ajuda

👑 **Admin:**
/admin — Listar usuários
/desativar ID — Desativar usuário
/ativar ID — Ativar usuário
        """)

    async def _h_admin(self, event):
        user_id = event.sender_id
        if not self.db.is_admin(user_id):
            await event.reply("⛔ Acesso negado!")
            return
        
        users = self.db.get_all_users()
        msg = "👑 **USUÁRIOS**\n\n"
        for u in users:
            status = "🟢" if u['ativo'] else "🔴"
            bot = "🤖" if u['bot_ligado'] else "💤"
            msg += f"{status}{bot} `{u['user_id']}` - {u.get('first_name', '?')}\n"
            if u.get('email'):
                msg += f"   📧 {u['email']}\n"
        msg += "\n/desativar ID | /ativar ID"
        await event.reply(msg)

    async def _h_desativar(self, event):
        user_id = event.sender_id
        if not self.db.is_admin(user_id):
            await event.reply("⛔ Acesso negado!")
            return
        
        parts = event.message.raw_text.split()
        if len(parts) < 2:
            await event.reply("❌ /desativar <user_id>")
            return
        
        try:
            target = int(parts[1])
            self.db.set_active(target, False)
            # Para o bot do usuário
            if target in self.traders:
                self.traders[target].conectado = False
                del self.traders[target]
            await event.reply(f"✅ Usuário `{target}` desativado!")
        except:
            await event.reply("❌ ID inválido")

    async def _h_ativar(self, event):
        user_id = event.sender_id
        if not self.db.is_admin(user_id):
            await event.reply("⛔ Acesso negado!")
            return
        
        parts = event.message.raw_text.split()
        if len(parts) < 2:
            await event.reply("❌ /ativar <user_id>")
            return
        
        try:
            target = int(parts[1])
            self.db.set_active(target, True)
            await event.reply(f"✅ Usuário `{target}` ativado!")
        except:
            await event.reply("❌ ID inválido")

    # ==================== TEXT E CALLBACK ====================

    async def _h_text(self, event):
        try:
            if event.message.out or not event.is_private:
                return
            texto = (event.message.raw_text or "").strip()
            if not texto or texto.startswith('/'):
                return

            user_id = event.sender_id
            estado = self._states.get(user_id)
            data = self._data.get(user_id, {})

            if estado is None:
                return

            if estado == "email":
                data["email"] = texto
                self._states[user_id] = "senha"
                await event.reply("📌 Digite sua **SENHA** da IQ Option:")

            elif estado == "senha":
                data["senha"] = texto
                self._states[user_id] = "valor"
                await event.reply("📌 **VALOR BASE** de entrada (R$):\n_(ex: 2.00)_")

            elif estado == "valor":
                try:
                    v = float(texto.replace(',', '.'))
                    if v < 0.5:
                        await event.reply("⚠️ Mínimo R$ 0,50")
                        return
                    data["valor"] = v
                    self._states[user_id] = "gales"
                    await event.reply("📌 Quantos **GALES**? (0–5)")
                except:
                    await event.reply("❌ Número inválido")

            elif estado == "gales":
                try:
                    g = int(texto)
                    if not (0 <= g <= 5):
                        await event.reply("❌ Entre 0 e 5")
                        return
                    data["gales"] = g
                    self._states[user_id] = "multiplicador"
                    await event.reply("📌 **MULTIPLICADOR** (ex: 2.0):")
                except:
                    await event.reply("❌ Número inválido")

            elif estado == "multiplicador":
                try:
                    m = float(texto.replace(',', '.'))
                    if not (1.1 <= m <= 5.0):
                        await event.reply("❌ Entre 1.1 e 5.0")
                        return
                    data["multiplicador"] = m
                    self._states[user_id] = "antecipacao"
                    await event.reply("📌 **ANTECIPAÇÃO** (segundos, 0-60):")
                except:
                    await event.reply("❌ Número inválido")

            elif estado == "antecipacao":
                try:
                    a = int(texto)
                    if not (0 <= a <= 60):
                        await event.reply("❌ Entre 0 e 60")
                        return
                    data["antecipacao"] = a
                    self._states[user_id] = "stop_win"
                    await event.reply("📌 **STOP WIN** (R$):\n_(ex: 100.00)_")
                except:
                    await event.reply("❌ Número inválido")

            elif estado == "stop_win":
                try:
                    sw = float(texto.replace(',', '.'))
                    if sw < 10:
                        await event.reply("⚠️ Mínimo R$ 10")
                        return
                    data["stop_win"] = sw
                    self._states[user_id] = "stop_loss"
                    await event.reply("📌 **STOP LOSS** (R$):\n_(ex: 50.00)_")
                except:
                    await event.reply("❌ Número inválido")

            elif estado == "stop_loss":
                try:
                    sl = float(texto.replace(',', '.'))
                    if sl < 5:
                        await event.reply("⚠️ Mínimo R$ 5")
                        return
                    data["stop_loss"] = sl
                    self._states[user_id] = "canal"
                    await event.reply("📡 **ID do canal de sinais**:\n_(ex: -100123456789)_")
                except:
                    await event.reply("❌ Número inválido")

            elif estado == "canal":
                try:
                    canal_id = int(texto)
                    data["canal_id"] = canal_id
                    await self._config_finalizar(user_id, event)
                except:
                    await event.reply("❌ ID inválido")

            # Edições
            elif estado.startswith("edit_"):
                campo = estado[5:]
                await self._processar_edicao(user_id, campo, texto, event)

            self._data[user_id] = data

        except Exception as e:
            logger.error(f"_h_text: {e}")

    async def _h_callback(self, event):
        try:
            user_id = event.sender_id
            data = event.data.decode('utf-8')

            if data == "menu":
                await self._menu(user_id, event, reply=False)
            elif data == "status":
                await self._status(user_id, event, reply=False)
            elif data == "config":
                await self._config_mostrar(event, reply=False)
            elif data == "startauto":
                await event.edit("▶️ Use /startauto no chat")
            elif data == "stopauto":
                await event.edit("⏹️ Use /stopauto no chat")
            elif data == "stats":
                await self._stats(user_id, event, reply=False)
            elif data == "resetstats":
                self.db.reset_stats(user_id)
                await event.edit("✅ Stats resetadas!", buttons=self._bts_voltar())
            elif data == "help":
                await event.edit("📚 Use /help", buttons=self._bts_voltar())
            elif data == "cancelar":
                self._limpar_estado(user_id)
                await event.edit("❌ Cancelado.", buttons=self._bts_voltar())
            elif data == "conectar":
                await self._cb_conectar(user_id, event)
            elif data == "sinc_sim":
                self._data[user_id]["sincronizar"] = True
                self._states[user_id] = "stop_win"
                await event.edit("✅ Sincronização ativada!\n\n📌 **STOP WIN** (R$):")
            elif data == "sinc_nao":
                self._data[user_id]["sincronizar"] = False
                self._states[user_id] = "stop_win"
                await event.edit("ℹ️ Sincronização desativada.\n\n📌 **STOP WIN** (R$):")
            elif data == "conta_real":
                self._data[user_id]["tipo_conta"] = "real"
                self._states[user_id] = "canal"
                await event.edit("💰 Conta REAL selecionada!\n\n📡 **ID do canal:**")
            elif data == "conta_demo":
                self._data[user_id]["tipo_conta"] = "treinamento"
                self._states[user_id] = "canal"
                await event.edit("🎯 Conta TREINAMENTO selecionada!\n\n📡 **ID do canal:**")
            elif data.startswith("edit_"):
                campo = data[5:]
                self._states[user_id] = f"edit_{campo}"
                if campo == "sincronizar":
                    await event.edit("🕯️ **Sincronizar?**", buttons=[
                        [Button.inline("✅ Sim", b"edt_sinc_sim"),
                         Button.inline("❌ Não", b"edt_sinc_nao")]
                    ])
                elif campo == "tipo_conta":
                    await event.edit("🏦 **Tipo de conta:**", buttons=[
                        [Button.inline("💰 REAL", b"edt_conta_real"),
                         Button.inline("🎯 DEMO", b"edt_conta_demo")]
                    ])
                else:
                    await event.edit(f"✏️ Digite o novo valor para **{campo}**:", 
                                     buttons=[[Button.inline("❌ Cancelar", b"cancelar")]])
            elif data.startswith("edt_"):
                await self._processar_edit_callback(user_id, data, event)

            try:
                await event.answer()
            except:
                pass

        except Exception as e:
            logger.error(f"_h_callback: {e}")

    # ==================== SINAIS ====================

    async def _h_sinal(self, event):
        try:
            if event.message.out:
                return
            
            texto = (event.message.raw_text or "").strip()
            if not texto:
                return

            # Verifica todos os usuários ativos
            users = self.db.get_all_users()
            for user in users:
                user_id = user['user_id']
                if not user['ativo'] or not user['bot_ligado']:
                    continue
                
                config = self.db.get_config(user_id)
                canal_id = config.get('canal_id')
                if not canal_id or event.chat_id != canal_id:
                    continue
                
                if self.processando.get(user_id, False):
                    continue

                dados = self.parser.parse(texto)
                if not dados['valido']:
                    continue

                # Executa sinal para este usuário
                asyncio.create_task(self._executar_sinal(user_id, dados))

        except Exception as e:
            logger.error(f"_h_sinal: {e}")

    async def _executar_sinal(self, user_id: int, dados: dict):
        self.processando[user_id] = True
        config = self.db.get_config(user_id)
        antec = config.get("antecipacao", 5)
        sinc = config.get("sincronizar_vela", True)

        try:
            await self.msg(user_id, UI.sinal_recebido(dados, antec, sinc))

            if user_id not in self.traders or not self.traders[user_id].conectado:
                trader = IQTrader(self.db, user_id)
                ok = await trader.conectar()
                if ok:
                    self.traders[user_id] = trader
                else:
                    await self.msg(user_id, "❌ Falha na conexão com IQ Option!")
                    self.processando[user_id] = False
                    return

            trader = self.traders[user_id]
            
            # Executa operação
            resultado = await trader.executar(
                dados['ativo'], dados['direcao'], dados['tempo'],
                lambda msg: self.msg(user_id, msg),
                skip_sinc=False
            )

            if not resultado.get('sucesso') and resultado.get('erro'):
                await self.msg(user_id, UI.erro_operacao(resultado['erro']))

        except Exception as e:
            logger.error(f"_executar_sinal user {user_id}: {e}")
            await self.msg(user_id, f"❌ Erro: {e}")
        finally:
            self.processando[user_id] = False
            await self.msg(user_id, UI.aguardando_sinais())

    # ==================== MÉTODOS AUXILIARES ====================

    def _limpar_estado(self, user_id: int):
        self._states.pop(user_id, None)
        self._data.pop(user_id, None)

    def _bts_menu(self):
        return [
            [Button.inline("📊 Status", b"status")],
            [Button.inline("⚙️ Config", b"config")],
            [Button.inline("📈 Stats", b"stats"), Button.inline("🔄 Reset", b"resetstats")],
            [Button.inline("🔗 Conectar", b"conectar")],
            [Button.inline("📋 Menu", b"menu")]
        ]

    def _bts_voltar(self):
        return [[Button.inline("📋 Menu", b"menu")]]

    def _bts_config(self):
        return [
            [Button.inline("✏️ Email", b"edit_email"), Button.inline("✏️ Senha", b"edit_senha")],
            [Button.inline("💵 Entrada", b"edit_valor"), Button.inline("🎯 Gales", b"edit_gales")],
            [Button.inline("✖️ Multiplicador", b"edit_multiplicador"), Button.inline("⏱️ Antecipação", b"edit_antecipacao")],
            [Button.inline("🕯️ Sinc. Vela", b"edit_sincronizar"), Button.inline("🏦 Conta", b"edit_tipo_conta")],
            [Button.inline("🟢 Stop Win", b"edit_stop_win"), Button.inline("🔴 Stop Loss", b"edit_stop_loss")],
            [Button.inline("📡 Canal", b"edit_canal")],
            [Button.inline("📋 Menu", b"menu")]
        ]

    async def _menu(self, user_id: int, event, reply: bool):
        if reply:
            await event.reply(UI.menu(), buttons=self._bts_menu())
        else:
            await event.edit(UI.menu(), buttons=self._bts_menu())

    async def _status(self, user_id: int, event, reply: bool):
        config = self.db.get_config(user_id)
        stats = self.db.get_stats(user_id)
        trader = self.traders.get(user_id)
        
        conectado = trader and trader.conectado
        saldo = trader.saldo if trader else 0
        tipo = config.get("tipo_conta", "real")
        
        msg = UI.status_sistema(conectado, saldo, tipo, stats)
        bts = [[Button.inline("🔄 Atualizar", b"status"), Button.inline("📋 Menu", b"menu")]]
        if reply:
            await event.reply(msg, buttons=bts)
        else:
            await event.edit(msg, buttons=bts)

    async def _stats(self, user_id: int, event, reply: bool):
        stats = self.db.get_stats(user_id)
        msg = f"""
📊 **ESTATÍSTICAS**
━━━━━━━━━━━━━━━━━━━━━━━

📅 **HOJE**
📈 {stats.get('daily_trades', 0)} trades
🟢 {stats.get('daily_wins', 0)} wins | 🔴 {stats.get('daily_losses', 0)} losses
💵 R$ {stats.get('daily_profit', 0):,.2f}

🏆 **TOTAL**
📈 {stats.get('total_trades', 0)} trades
🟢 {stats.get('total_wins', 0)} wins | 🔴 {stats.get('total_losses', 0)} losses
💵 R$ {stats.get('total_profit', 0):,.2f}
        """
        bts = [[Button.inline("🔄 Atualizar", b"stats"), Button.inline("📋 Menu", b"menu")]]
        if reply:
            await event.reply(msg, buttons=bts)
        else:
            await event.edit(msg, buttons=bts)

    async def _config_mostrar(self, event, reply: bool):
        user_id = event.sender_id
        config = self.db.get_config(user_id)
        msg = UI.configuracao_resumo(config)
        if reply:
            await event.reply(msg, buttons=self._bts_config())
        else:
            await event.edit(msg, buttons=self._bts_config())

    async def _config_iniciar(self, event):
        user_id = event.sender_id
        self._data[user_id] = {}
        self._states[user_id] = "email"
        await event.reply(
            "🔐 **CONFIGURAÇÃO**\n\n"
            "📌 **PASSO 1/9 — Email IQ Option**\n\n"
            "Digite seu email:"
        )

    async def _config_finalizar(self, user_id: int, event):
        data = self._data.get(user_id, {})
        
        config = {
            "email": data.get("email"),
            "senha": data.get("senha"),
            "valor_entrada": data.get("valor", 2.0),
            "gales": data.get("gales", 2),
            "multiplicador": data.get("multiplicador", 2.0),
            "antecipacao": data.get("antecipacao", 5),
            "sincronizar_vela": data.get("sincronizar", True),
            "stop_win": data.get("stop_win", 100.0),
            "stop_loss": data.get("stop_loss", 50.0),
            "tipo_conta": data.get("tipo_conta", "real"),
            "canal_id": data.get("canal_id"),
            "configurado": True
        }
        
        self.db.save_config(user_id, config)
        self._limpar_estado(user_id)
        
        # Tenta conectar
        trader = IQTrader(self.db, user_id)
        ok = await trader.conectar()
        
        if ok:
            self.traders[user_id] = trader
            await event.reply(f"""
✅ **CONFIGURAÇÃO COMPLETA!**

{UI.configuracao_resumo(config)}

🚀 Use /startauto para ativar o robô!
            """)
        else:
            await event.reply("⚠️ Configurado, mas falha na conexão com IQ Option.\nVerifique email/senha.")

    async def _cb_conectar(self, user_id: int, event):
        config = self.db.get_config(user_id)
        if not config.get("configurado"):
            await event.edit("⚠️ Configure primeiro: /config", buttons=self._bts_voltar())
            return
        
        if user_id in self.traders and self.traders[user_id].conectado:
            await event.edit("✅ Já está conectado!", buttons=self._bts_voltar())
            return
        
        await event.edit("🔄 Conectando...")
        trader = IQTrader(self.db, user_id)
        ok = await trader.conectar()
        
        if ok:
            self.traders[user_id] = trader
            await event.edit("✅ Conectado com sucesso!", buttons=self._bts_voltar())
        else:
            await event.edit("❌ Falha na conexão!", buttons=self._bts_voltar())

    async def _processar_edicao(self, user_id: int, campo: str, valor: str, event):
        try:
            if campo == "email":
                self.db.update_user(user_id, email=valor)
                await event.reply(f"✅ Email atualizado: `{valor}`")
            elif campo == "senha":
                self.db.update_user(user_id, senha=valor)
                await event.reply("✅ Senha atualizada!")
            elif campo == "valor":
                v = float(valor.replace(',', '.'))
                self.db.update_user(user_id, valor_entrada=v)
                await event.reply(f"✅ Valor atualizado: R$ {v:,.2f}")
            elif campo == "gales":
                g = int(valor)
                self.db.update_user(user_id, gales=g)
                await event.reply(f"✅ Gales atualizado: {g}")
            elif campo == "multiplicador":
                m = float(valor.replace(',', '.'))
                self.db.update_user(user_id, multiplicador=m)
                await event.reply(f"✅ Multiplicador: {m}x")
            elif campo == "antecipacao":
                a = int(valor)
                self.db.update_user(user_id, antecipacao=a)
                await event.reply(f"✅ Antecipação: {a}s")
            elif campo == "stop_win":
                sw = float(valor.replace(',', '.'))
                self.db.update_user(user_id, stop_win=sw)
                await event.reply(f"✅ Stop Win: R$ {sw:,.2f}")
            elif campo == "stop_loss":
                sl = float(valor.replace(',', '.'))
                self.db.update_user(user_id, stop_loss=sl)
                await event.reply(f"✅ Stop Loss: R$ {sl:,.2f}")
            elif campo == "canal":
                cid = int(valor)
                self.db.update_user(user_id, canal_id=cid)
                await event.reply(f"✅ Canal: `{cid}`")
            elif campo == "tipo_conta":
                # Tratado via callback
                pass
            elif campo == "sincronizar":
                # Tratado via callback
                pass
            
            self._limpar_estado(user_id)
            await self._config_mostrar(event, reply=True)
        except Exception as e:
            await event.reply(f"❌ Erro: {e}")

    async def _processar_edit_callback(self, user_id: int, data: str, event):
        if data == "edt_sinc_sim":
            self.db.update_user(user_id, sincronizar_vela=1)
            await event.edit("✅ Sincronização ativada!")
            await self._config_mostrar(event, reply=False)
        elif data == "edt_sinc_nao":
            self.db.update_user(user_id, sincronizar_vela=0)
            await event.edit("ℹ️ Sincronização desativada!")
            await self._config_mostrar(event, reply=False)
        elif data == "edt_conta_real":
            self.db.update_user(user_id, tipo_conta="real")
            await event.edit("💰 Conta REAL selecionada!")
            await self._config_mostrar(event, reply=False)
        elif data == "edt_conta_demo":
            self.db.update_user(user_id, tipo_conta="treinamento")
            await event.edit("🎯 Conta TREINAMENTO selecionada!")
            await self._config_mostrar(event, reply=False)
        
        self._limpar_estado(user_id)


# ==================== MAIN ====================

async def main():
    bot = RobinBot()
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
