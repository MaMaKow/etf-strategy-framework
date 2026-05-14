import os
import json
import yaml
import mysql.connector
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

import yfinance as yf
import pandas as pd
import requests
from dotenv import load_dotenv

from .config import SDAConfig
from .strategies.sda import SDAStrategy
from .models import MarketState, State, Order

load_dotenv()

def load_bot_config(config_path: str = "bot_config.yaml") -> Dict[str, Any]:
    """Lädt die Bot-Konfiguration aus einer YAML-Datei."""
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        print(f"✅ Konfiguration geladen aus {config_path}")
        return config
    else:
        print(f"⚠️ Konfigurationsdatei {config_path} nicht gefunden, verwende Standardkonfiguration")
        return BOT_CONFIG.copy()

# ---------------------------------------------------------------------------
# KONFIGURATION
# ---------------------------------------------------------------------------

DB_CONFIG = {
    'host':     'localhost',
    'user':     os.getenv("MARIADB_USER"),
    'password': os.getenv("MARIADB_PASSPHRASE"),
    'database': 'etf_bot'
}

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Bot-Konfiguration (kann später in YAML/JSON ausgelagert werden)
BOT_CONFIG = {
    "etf_ticker": "EUNL.DE",
    "vix_ticker": "^VIX",
    "monthly_contribution": 300.0,
    "monthly_savings": 150.0,
    "ocf_target": 100.0,
    "min_order_eur": 100.0,
    "slippage": 0.0005,
    "vix_threshold": 15.0,
    "dip_tiers": [
        (-0.05, 0.20, "T1"),
        (-0.10, 0.30, "T2"),
        (-0.20, 0.40, "T3"),
        (-0.30, 0.50, "T4"),
        (-0.40, 0.60, "T5")
    ],
    "cooldown_min": 5,
    "ocf_low_pct": 0.30,
    "ocf_mid_pct": 1.00,
    "t1_requires_above_sma200": True,
}

# ---------------------------------------------------------------------------
# DATENBANK-SCHEMA
# ---------------------------------------------------------------------------

CREATE_TABLES_SQL = """
-- Portfolio-State pro ETF
CREATE TABLE IF NOT EXISTS bot_state (
    etf_ticker VARCHAR(20) PRIMARY KEY,
    cash_ocf DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    units DECIMAL(12,6) NOT NULL DEFAULT 0.00,
    portfolio_value DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    cooldowns JSON NOT NULL DEFAULT ('{}'),
    total_contributions DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    total_cashflow DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    last_monthly_date DATE,
    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Alle ausgeführten Trades
CREATE TABLE IF NOT EXISTS trade_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    etf_ticker VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    tier VARCHAR(50),
    amount_eur DECIMAL(10,2) NOT NULL,
    price DECIMAL(10,6) NOT NULL,
    units DECIMAL(12,6) NOT NULL,
    drawdown DECIMAL(8,6),
    vix DECIMAL(6,2),
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_etf_date (etf_ticker, date)
);

-- Alle täglichen Empfehlungen (inkl. "kein Handel")
CREATE TABLE IF NOT EXISTS signal_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    etf_ticker VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    recommendation VARCHAR(20) NOT NULL,  -- 'BUY' or 'HOLD'
    tier VARCHAR(50),  -- nur bei BUY
    amount_eur DECIMAL(10,2),  -- nur bei BUY
    price DECIMAL(10,6),
    units DECIMAL(12,6),  -- nur bei BUY
    reason TEXT,  -- Erklärung
    market_data JSON NOT NULL,  -- alle Indikatoren
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_etf_date (etf_ticker, date),
    INDEX idx_etf_date (etf_ticker, date)
);
"""

# ---------------------------------------------------------------------------
# HILFSKLASSEN
# ---------------------------------------------------------------------------

@dataclass
class BotState:
    etf_ticker: str
    cash_ocf: float = 0.0
    units: float = 0.0
    portfolio_value: float = 0.0
    cooldowns: Dict[str, int] = None
    total_contributions: float = 0.0
    total_cashflow: float = 0.0
    last_monthly_date: Optional[date] = None

    def __post_init__(self):
        if self.cooldowns is None:
            self.cooldowns = {}

    def to_state(self) -> State:
        return State(
            cash_ocf=self.cash_ocf,
            units=self.units,
            portfolio_value=self.portfolio_value,
            cooldowns=self.cooldowns,
            total_contributions=self.total_contributions,
            total_cashflow=self.total_cashflow,
        )

    @classmethod
    def from_row(cls, row) -> 'BotState':
        return cls(
            etf_ticker=row['etf_ticker'],
            cash_ocf=float(row['cash_ocf']),
            units=float(row['units']),
            portfolio_value=float(row['portfolio_value']),
            cooldowns=json.loads(row['cooldowns']) if row['cooldowns'] else {},
            total_contributions=float(row['total_contributions']),
            total_cashflow=float(row['total_cashflow']),
            last_monthly_date=row['last_monthly_date'],
        )

@dataclass
class SignalLog:
    etf_ticker: str
    date: date
    recommendation: str  # 'BUY' or 'HOLD'
    tier: Optional[str] = None
    amount_eur: Optional[float] = None
    price: Optional[float] = None
    units: Optional[float] = None
    reason: str = ""
    market_data: Dict[str, Any] = None

    def __post_init__(self):
        if self.market_data is None:
            self.market_data = {}

# ---------------------------------------------------------------------------
# DATENBANK-FUNKTIONEN
# ---------------------------------------------------------------------------

def init_database() -> None:
    """Erstellt die notwendigen Tabellen in der Datenbank."""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    try:
        for statement in CREATE_TABLES_SQL.strip().split(';'):
            if statement.strip():
                cursor.execute(statement)
        conn.commit()
        print("✅ Datenbank-Tabellen erstellt.")
    finally:
        cursor.close()
        conn.close()

def load_bot_state(etf_ticker: str) -> BotState:
    """Lädt den aktuellen Bot-State aus der DB."""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM bot_state WHERE etf_ticker = %s", (etf_ticker,))
        row = cursor.fetchone()
        if row:
            return BotState.from_row(row)
        else:
            # Neuer State
            state = BotState(etf_ticker=etf_ticker)
            save_bot_state(state)
            return state
    finally:
        cursor.close()
        conn.close()

def save_bot_state(state: BotState) -> None:
    """Speichert den Bot-State in der DB."""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO bot_state
                (etf_ticker, cash_ocf, units, portfolio_value, cooldowns,
                 total_contributions, total_cashflow, last_monthly_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                cash_ocf = VALUES(cash_ocf),
                units = VALUES(units),
                portfolio_value = VALUES(portfolio_value),
                cooldowns = VALUES(cooldowns),
                total_contributions = VALUES(total_contributions),
                total_cashflow = VALUES(total_cashflow),
                last_monthly_date = VALUES(last_monthly_date)
        """, (
            state.etf_ticker,
            state.cash_ocf,
            state.units,
            state.portfolio_value,
            json.dumps(state.cooldowns),
            state.total_contributions,
            state.total_cashflow,
            state.last_monthly_date,
        ))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def log_signal(signal: SignalLog) -> None:
    """Speichert eine Signal-Empfehlung in der DB."""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO signal_log
                (etf_ticker, date, recommendation, tier, amount_eur, price, units, reason, market_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                recommendation = VALUES(recommendation),
                tier = VALUES(tier),
                amount_eur = VALUES(amount_eur),
                price = VALUES(price),
                units = VALUES(units),
                reason = VALUES(reason),
                market_data = VALUES(market_data)
        """, (
            signal.etf_ticker,
            signal.date,
            signal.recommendation,
            signal.tier,
            signal.amount_eur,
            signal.price,
            signal.units,
            signal.reason,
            json.dumps(signal.market_data),
        ))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def log_trade(order: Order, etf_ticker: str) -> None:
    """Speichert einen ausgeführten Trade in der DB."""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO trade_log
                (etf_ticker, date, tier, amount_eur, price, units, drawdown, vix)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            etf_ticker,
            order.date,
            order.tier,
            order.amount_eur,
            order.price,
            order.units,
            order.drawdown,
            order.vix,
        ))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

# ---------------------------------------------------------------------------
# SDA-BOT-KLASSE
# ---------------------------------------------------------------------------

class SDABot:
    def __init__(self, config: Optional[Dict[str, Any]] = None, config_path: str = "bot_config.yaml"):
        if config is None:
            config = load_bot_config(config_path)
        self.config = config
        self.sda_config = SDAConfig(**self.config)
        self.strategy = SDAStrategy(self.sda_config)

    def send_telegram(self, message: str) -> None:
        """Sendet eine Nachricht via Telegram."""
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            print("⚠️ Telegram-Konfiguration fehlt.")
            return

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": self.config.get("telegram_chat_id", TELEGRAM_CHAT_ID),
            "text": message,
            "parse_mode": "Markdown",
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"⚠️ Telegram-Fehler: {e}")

    def log_and_notify(self, etf_ticker: str, date: date, recommendation: str, reason: str = "", market_data: Dict[str, Any] = None) -> None:
        """Loggt eine Signal-Empfehlung und sendet eine Benachrichtigung."""
        if market_data is None:
            market_data = {}

        signal = SignalLog(
            etf_ticker=etf_ticker,
            date=date,
            recommendation=recommendation,
            reason=reason,
            market_data=market_data,
        )
        log_signal(signal)

        message = f"*SDA-Bot für {etf_ticker}*\n\n{reason}"
        self.send_telegram(message)

    def get_market_state(self, etf_ticker: str, current_date: date) -> Optional[MarketState]:
        """Holt Marktdaten und erstellt MarketState."""
        try:
            # Daten für die letzten 2 Jahre + etwas Puffer
            df = yf.download(etf_ticker, period="2y", auto_adjust=True)

            if df.empty or len(df) < 200:
                return None

            close = df["Close"].squeeze()  # Konvertiert zu Series falls nötig

            # Aktuelle Werte
            current_price = float(close.iloc[-1])
            prev_price = float(close.iloc[-2]) if len(close) > 1 else current_price

            # SMA200
            sma200_series = close.rolling(window=200).mean()
            current_sma200 = float(sma200_series.iloc[-1]) if not pd.isna(sma200_series.iloc[-1]) else current_price
            prev_sma200 = float(sma200_series.iloc[-2]) if len(sma200_series) > 1 and not pd.isna(sma200_series.iloc[-2]) else current_sma200

            # SMA20
            sma20_series = close.rolling(window=20).mean()
            sma20 = float(sma20_series.iloc[-1]) if not pd.isna(sma20_series.iloc[-1]) else current_price

            # RSI (Wilder's Smoothing)
            def calculate_rsi(series: pd.Series, period: int = 14) -> float:
                delta = series.diff()
                gain = delta.where(delta > 0, 0.0)
                loss = -delta.where(delta < 0, 0.0)
                avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
                avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
                rs = avg_gain / avg_loss.replace(0, 1e-9)
                rsi = 100 - (100 / (1 + rs))
                return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

            rsi = calculate_rsi(close)

            # Drawdown (gegen 252-Tage Hoch)
            high_252_series = close.rolling(window=252, min_periods=1).max()
            high_252 = float(high_252_series.iloc[-1]) if not pd.isna(high_252_series.iloc[-1]) else current_price
            drawdown = (current_price - high_252) / high_252 if high_252 != 0 else 0.0

            # Recovery Days
            def count_consecutive_green_days(series: pd.Series) -> int:
                count = 0
                for i in range(len(series) - 1, 0, -1):
                    if series.iloc[i] > series.iloc[i - 1]:
                        count += 1
                    else:
                        break
                return count

            recovery_days = count_consecutive_green_days(close)

            # VIX
            vix_data = yf.download(self.config["vix_ticker"], period="5d", auto_adjust=True)
            vix = float(vix_data["Close"].squeeze().iloc[-1]) if not vix_data.empty else 20.0

            # Monatsstart prüfen
            is_month_start = current_date.day == 1

            return MarketState(
                date=current_date,
                close=current_price,
                prev_price=prev_price,
                sma200=current_sma200,
                prev_sma200=prev_sma200,
                sma20=sma20,
                rsi=rsi,
                drawdown=drawdown,
                recovery_days=recovery_days,
                vix=vix,
                is_month_start=is_month_start,
            )
        except Exception as e:
            print(f"⚠️ Fehler beim Laden der Marktdaten: {e}")
            return None

    def evaluate_day(self, etf_ticker: str, current_date: date = None) -> str:
        """Bewertet einen Tag und gibt eine Empfehlung zurück."""
        if current_date is None:
            current_date = date.today()

        # State laden
        bot_state = load_bot_state(etf_ticker)

        # Marktdaten holen
        market_state = self.get_market_state(etf_ticker, current_date)
        if not market_state:
            reason = "Nicht genügend Marktdaten verfügbar."
            self.log_and_notify(etf_ticker, current_date, "HOLD", reason=reason, market_data={})
            return reason

        # SDA-Logik ausführen
        portfolio_state = bot_state.to_state()
        orders = self.strategy.on_day(market_state, portfolio_state)

        # State aktualisieren
        if orders:
            # Monatliche Orders verarbeiten
            monthly_orders = [o for o in orders if o.tier == "MONTHLY-ETF"]
            dip_orders = [o for o in orders if o.tier != "MONTHLY-ETF"]

            # Cashflow für monatliche Orders
            if monthly_orders and market_state.is_month_start:
                monthly_amount = sum(o.amount_eur for o in monthly_orders)
                bot_state.cash_ocf += self.config["monthly_contribution"]
                bot_state.total_contributions += self.config["monthly_contribution"]
                bot_state.total_cashflow += self.config["monthly_contribution"]
                bot_state.last_monthly_date = current_date

            # Portfolio aktualisieren
            for order in orders:
                if order.amount_eur <= bot_state.cash_ocf:
                    bot_state.cash_ocf -= order.amount_eur
                    bot_state.units += order.units
                    log_trade(order, etf_ticker)

                    # Cooldown setzen
                    if order.cooldown_days:
                        bot_state.cooldowns[order.tier] = order.cooldown_days

            # Portfolio-Wert aktualisieren
            bot_state.portfolio_value = bot_state.units * market_state.close

        # Cooldowns dekrementieren
        bot_state.cooldowns = {k: v-1 for k, v in bot_state.cooldowns.items() if v > 1}

        # State speichern
        save_bot_state(bot_state)

        # Empfehlung erstellen
        if orders and any(o.tier != "MONTHLY-ETF" for o in orders):
            dip_order = next((o for o in orders if o.tier != "MONTHLY-ETF"), None)
            if dip_order:
                recommendation = "BUY"
                tier = dip_order.tier
                amount_eur = dip_order.amount_eur
                units = dip_order.units
                reason = f"Dip-Buy empfohlen: {tier}, Betrag {amount_eur:.2f} €, Preis {dip_order.price:.4f} €, Einheiten {units:.4f}"
            else:
                recommendation = "HOLD"
                reason = "Monatlicher Sparplan ausgeführt, aber kein Dip-Buy."
        else:
            recommendation = "HOLD"
            reason_parts = []
            if market_state.vix <= self.config["vix_threshold"]:
                reason_parts.append(f"VIX zu niedrig ({market_state.vix:.1f} ≤ {self.config['vix_threshold']})")
            if market_state.drawdown > min(t[0] for t in self.config["dip_tiers"]):
                reason_parts.append(f"Drawdown zu gering ({market_state.drawdown:.1%})")
            if any(c > 0 for c in bot_state.cooldowns.values()):
                active_cooldowns = [f"{k}: {v}d" for k, v in bot_state.cooldowns.items() if v > 0]
                reason_parts.append(f"Aktive Sperrfristen: {', '.join(active_cooldowns)}")
            if bot_state.cash_ocf < self.config["ocf_target"] * self.config["ocf_low_pct"]:
                reason_parts.append(f"OCF-Reserve zu niedrig ({bot_state.cash_ocf:.2f} €)")
            if not reason_parts:
                reason_parts.append("Alle Bedingungen erfüllt, aber kein Signal ausgelöst")
            reason = f"Kein Handel: {', '.join(reason_parts)}"

        # Loggen und benachrichtigen
        market_data = {
            "close": market_state.close,
            "sma200": market_state.sma200,
            "sma20": market_state.sma20,
            "rsi": market_state.rsi,
            "drawdown": market_state.drawdown,
            "vix": market_state.vix,
            "recovery_days": market_state.recovery_days,
        }

        signal = SignalLog(
            etf_ticker=etf_ticker,
            date=current_date,
            recommendation=recommendation,
            tier=tier if recommendation == "BUY" else None,
            amount_eur=amount_eur if recommendation == "BUY" else None,
            price=market_state.close,
            units=units if recommendation == "BUY" else None,
            reason=reason,
            market_data=market_data,
        )
        log_signal(signal)

        # Nachricht erstellen
        message = f"*SDA-Bot für {etf_ticker}*\n\n{reason}\n\n"
        message += f"Marktdaten:\n"
        message += f"• Preis: {market_state.close:.2f} €\n"
        message += f"• Drawdown: {market_state.drawdown:.1%}\n"
        message += f"• RSI: {market_state.rsi:.1f}\n"
        message += f"• VIX: {market_state.vix:.1f}\n"
        message += f"• Erholungstage: {market_state.recovery_days}\n\n"
        message += f"Portfolio:\n"
        message += f"• Cash OCF: {bot_state.cash_ocf:.2f} €\n"
        message += f"• Einheiten: {bot_state.units:.4f}\n"
        message += f"• Portfolio-Wert: {bot_state.portfolio_value:.2f} €"

        self.send_telegram(message)

        return reason

# ---------------------------------------------------------------------------
# HAUPTFUNKTIONEN
# ---------------------------------------------------------------------------

def init_bot() -> None:
    """Initialisiert die Datenbank und den Bot."""
    init_database()
    print("✅ SDA-Bot initialisiert.")

def run_daily(etf_ticker: str = "EUNL.DE") -> None:
    """Führt die tägliche Bewertung für einen ETF durch."""
    bot = SDABot()
    try:
        result = bot.evaluate_day(etf_ticker)
        print(f"✅ Bewertung abgeschlossen: {result}")
    except Exception as e:
        error_msg = f"⚠️ Bot-Fehler für {etf_ticker}: {str(e)}"
        print(error_msg)
        bot.send_telegram(error_msg)
        raise

if __name__ == "__main__":
    # Beispiel-Nutzung
    init_bot()
    run_daily("EUNL.DE")