import yfinance as yf
import pandas as pd
import mysql.connector
from datetime import datetime
import requests
import os
from dotenv import load_dotenv

load_dotenv()

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

# ETFs: Ticker → ISIN
ETFS = {
    "SNAW.DE": "IE00BFNM3J75",   # World Screened
    "IUSN.DE": "IE00BF4RFH31",   # World Small Cap
    "EUNW.DE": "IE0006WW1TQ4",   # World ex USA
    "IS3N.DE": "IE00BKM4GZ66",   # EM IMI
}

# Schwellwerte – optimiert durch Parameter-Sweep (Delta +10.62% vs. Sparplan)
CONFIG = {
    # Erholung: Mindestanzahl aufeinanderfolgender grüner Tage
    "recovery_days": 2,

    # Getrennte Sperrfristen pro Logik-Gruppe (Tage)
    # L1+L2 teilen sich eine Sperrfrist (beide sind starke Dip-Signale)
    # L3 und L4 sind unabhängig, damit sie sich nicht gegenseitig blockieren
    "min_days_l1l2": 30,
    "min_days_l3":   60,
    "min_days_l4":   30,

    # VIX-Grenze für "Panik-Modus" (Sweep-Optimum)
    "vix_panic": 25,

    # Logik 1 – "Ultimate Dip"
    "l1_drawdown":  -0.10,
    "l1_rsi":        30,
    "l1_amount":    100,

    # Logik 2 – "Extremer RSI-Dip" (Sweep-Optimum: streng = 22)
    "l2_rsi":        22,
    "l2_amount":     50,

    # Logik 3 – "Trendwende (Kreuz über SMA200)"
    # Sweep-Optimum: RSI < 50 beim Kreuzungstag (nicht überhitzt kaufen)
    "l3_rsi_max":    40,
    "l3_amount":     50,

    # Logik 4 – "Moderater Dip (SMA20 + RSI)" (Sweep-Optimum: -6 %)
    "l4_dip_pct":   -0.04,
    "l4_rsi":        32,
    "l4_amount":     25,

    # Betrag-Skalierung nach Drawdown-Tiefe (nur für L1)
    "drawdown_scale_factor": 2.0,
}

# ---------------------------------------------------------------------------
# HILFSFUNKTIONEN
# ---------------------------------------------------------------------------

def send_telegram(message: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "Markdown",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"⚠️  Telegram-Fehler: {e}")


def get_vix() -> float:
    df = yf.download("^VIX", period="5d", auto_adjust=True)
    if df.empty:
        return 20.0
    return float(df["Close"].iloc[-1].item())


def calculate_rsi_wilder(series: pd.Series, period: int = 14) -> float:
    """RSI nach Wilder's Smoothing (EWM), nicht simpler Rolling-Mean."""
    delta    = series.diff()
    gain_avg = delta.where(delta > 0, 0.0).ewm(alpha=1 / period, adjust=False).mean()
    loss_avg = (-delta.where(delta < 0, 0.0)).ewm(alpha=1 / period, adjust=False).mean()
    rsi      = 100 - (100 / (1 + gain_avg / loss_avg))
    return float(rsi.iloc[-1])


def count_consecutive_green_days(series: pd.Series) -> int:
    """Zählt, wie viele aufeinanderfolgende Tage der Kurs gestiegen ist (vom Ende)."""
    count = 0
    for i in range(len(series) - 1, 0, -1):
        if series.iloc[i] > series.iloc[i - 1]:
            count += 1
        else:
            break
    return count


def calculate_indicators(ticker: str) -> dict | None:
    raw = yf.download(ticker, period="2y", auto_adjust=True)
    if len(raw) < 200:
        print(f"  ⚠️  Nicht genügend Daten für {ticker}")
        return None

    close = raw["Close"].squeeze()   # 1-D Series

    sma200_series    = close.rolling(window=200).mean()
    current_price    = float(close.iloc[-1])
    prev_price       = float(close.iloc[-2])
    current_sma200   = float(sma200_series.iloc[-1])
    prev_sma200      = float(sma200_series.iloc[-2])
    current_sma20    = float(close.rolling(window=20).mean().iloc[-1])
    dip_from_sma20   = (current_price - current_sma20) / current_sma20
    current_rsi      = calculate_rsi_wilder(close)
    high_52w         = float(close.rolling(window=252, min_periods=1).max().iloc[-1])
    drawdown         = (current_price - high_52w) / high_52w
    recovery_candles = count_consecutive_green_days(close)

    return {
        "price":          current_price,
        "prev_price":     prev_price,
        "sma200":         current_sma200,
        "prev_sma200":    prev_sma200,
        "sma20":          current_sma20,
        "dip_from_sma20": dip_from_sma20,
        "rsi":            current_rsi,
        "drawdown":       drawdown,
        "recovery_days":  recovery_candles,
    }


def scale_amount(base_amount: float, drawdown: float) -> int:
    """Erhöht den Kaufbetrag proportional zur Drawdown-Tiefe."""
    factor  = 1.0 + abs(drawdown) * CONFIG["drawdown_scale_factor"]
    scaled  = round(base_amount * factor / 25) * 25   # auf 25 € runden
    return int(scaled)


# ---------------------------------------------------------------------------
# HAUPTLOGIK
# ---------------------------------------------------------------------------

def days_since_last(cursor, isin: str, reasons: list) -> int:
    """Tage seit dem letzten Kauf einer bestimmten Logik-Gruppe aus signal_log."""
    placeholders = ",".join(["%s"] * len(reasons))
    cursor.execute(
        f"SELECT MAX(signal_date) AS last FROM signal_log "
        f"WHERE isin = %s AND reason IN ({placeholders})",
        (isin, *reasons),
    )
    row = cursor.fetchone()
    last = row["last"] if row else None
    return (datetime.now().date() - last).days if last else 999


def evaluate_signals() -> None:
    conn   = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    vix    = get_vix()

    print(f"VIX: {vix:.1f}")

    for ticker, isin in ETFS.items():
        print(f"\nPrüfe {ticker} …")
        data = calculate_indicators(ticker)
        if data is None:
            continue

        print(
            f"  Preis: {data['price']:.2f} | SMA200: {data['sma200']:.2f} | "
            f"SMA20: {data['sma20']:.2f} | Dip vs SMA20: {data['dip_from_sma20']:.2%} | "
            f"RSI: {data['rsi']:.1f} | Drawdown: {data['drawdown']:.2%} | "
            f"Erholungstage: {data['recovery_days']}"
        )

        recovering = data["recovery_days"] >= CONFIG["recovery_days"]

        # Getrennte Sperrfristen pro Logik-Gruppe
        days_l1l2 = days_since_last(cursor, isin, ["L1_ULTIMATE_DIP", "L2_RSI_EXTREME"])
        days_l3   = days_since_last(cursor, isin, ["L3_TREND_CROSS"])
        days_l4   = days_since_last(cursor, isin, ["L4_MODERATE_DIP"])

        signal = False
        amount = 0
        reason = ""
        logic  = ""

        # -- Logik 1: "Ultimate Dip" ----------------------------------------
        if (
            days_l1l2 >= CONFIG["min_days_l1l2"]
            and data["drawdown"] <= CONFIG["l1_drawdown"]
            and data["rsi"]      <  CONFIG["l1_rsi"]
            and vix              >  CONFIG["vix_panic"]
            and recovering
        ):
            signal = True
            logic  = "L1_ULTIMATE_DIP"
            amount = scale_amount(CONFIG["l1_amount"], data["drawdown"])
            reason = (
                f"🚨 STARKER DIP: {ticker} liegt {data['drawdown']:.1%} unter 52W-Hoch. "
                f"RSI: {data['rsi']:.1f}, VIX: {vix:.1f}, "
                f"{data['recovery_days']} Erholungstage."
            )

        # -- Logik 2: "Extremer RSI-Dip" ------------------------------------
        elif (
            days_l1l2 >= CONFIG["min_days_l1l2"]
            and data["rsi"] < CONFIG["l2_rsi"]
            and recovering
        ):
            signal = True
            logic  = "L2_RSI_EXTREME"
            amount = CONFIG["l2_amount"]
            reason = (
                f"📉 RSI-DIP: {ticker} RSI bei {data['rsi']:.1f}. "
                f"{data['recovery_days']} Erholungstage sichtbar."
            )

        # -- Logik 3: "Trendwende – Kreuz über SMA200 + RSI nicht überhitzt" -
        elif (
            days_l3 >= CONFIG["min_days_l3"]
            and data["price"]      >  data["sma200"]
            and data["prev_price"] <= data["prev_sma200"]
            and data["rsi"]        <  CONFIG["l3_rsi_max"]
        ):
            signal = True
            logic  = "L3_TREND_CROSS"
            amount = CONFIG["l3_amount"]
            reason = (
                f"📈 TRENDWENDE: {ticker} hat die 200-Tage-Linie durchbrochen "
                f"(RSI: {data['rsi']:.1f})."
            )

        # -- Logik 4: "Moderater Dip (SMA20 + RSI)" ------------------------
        elif (
            days_l4 >= CONFIG["min_days_l4"]
            and data["dip_from_sma20"] <= CONFIG["l4_dip_pct"]
            and data["rsi"]            <  CONFIG["l4_rsi"]
            and recovering
        ):
            signal = True
            logic  = "L4_MODERATE_DIP"
            amount = CONFIG["l4_amount"]
            reason = (
                f"📊 MODERATER DIP: {ticker} ist {data['dip_from_sma20']:.1%} unter SMA20, "
                f"RSI {data['rsi']:.1f}, {data['recovery_days']} Erholungstage."
            )

        # -- Signal versenden & DB speichern --------------------------------
        if signal:
            msg = (
                f"*KAUFEMPFEHLUNG*\n"
                f"ETF: `{ticker}` ({isin})\n"
                f"Betrag: *{amount} €*\n"
                f"Logik: {logic}\n"
                f"Grund: {reason}"
            )
            send_telegram(msg)
            print(f"  ✅ [{logic}] {reason}")

            cursor.execute(
                """
                INSERT INTO signals (isin, last_purchase_date)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE last_purchase_date = VALUES(last_purchase_date)
                """,
                (isin, datetime.now().date()),
            )
            cursor.execute(
                """
                INSERT IGNORE INTO signal_log
                    (isin, ticker, signal_date, amount, reason,
                     price, sma200, sma20, rsi, drawdown, vix)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    isin, ticker, datetime.now().date(), amount, logic,
                    round(data["price"],    4),
                    round(data["sma200"],   4),
                    round(data["sma20"],    4),
                    round(data["rsi"],      2),
                    round(data["drawdown"], 4),
                    round(vix, 2),
                ),
            )
            conn.commit()
        else:
            skipped = []
            if days_l1l2 < CONFIG["min_days_l1l2"]:
                skipped.append(f"L1/L2 gesperrt noch {CONFIG['min_days_l1l2'] - days_l1l2}d")
            if days_l3 < CONFIG["min_days_l3"]:
                skipped.append(f"L3 gesperrt noch {CONFIG['min_days_l3'] - days_l3}d")
            if days_l4 < CONFIG["min_days_l4"]:
                skipped.append(f"L4 gesperrt noch {CONFIG['min_days_l4'] - days_l4}d")
            hint = f" ({', '.join(skipped)})" if skipped else ""
            print(f"  — Kein Signal.{hint}")

    cursor.close()
    conn.close()


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Umgebungsvariablen fehlen – prüfe die .env Datei!")
    try:
        evaluate_signals()
    except Exception as e:
        send_telegram(f"⚠️ Bot-Fehler: {str(e)}")
        raise
