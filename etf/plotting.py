from io import BytesIO
from datetime import datetime, timedelta
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yfinance as yf
import pandas as pd


def create_price_plot(ticker: str, weeks: int = 12) -> BytesIO | None:
    """Lädt Kursdaten der letzten `weeks` Wochen (inkl. SMA) und gibt ein PNG-BytesIO zurück.

    Rückgabe: BytesIO (PNG) oder None, wenn keine Daten vorhanden sind.
    """
    try:
        sma_window = 200
        display_days = max(7, weeks * 7)
        # Zusätzlichen Vorlauf laden, damit der SMA schon am ersten Anzeigetag
        # einen validen Wert hat (Handelstage ≈ Kalendertage * 5/7, plus Puffer)
        lookback_days = display_days + int(sma_window * 7 / 5) + 15
        df = yf.download(ticker, period=f"{lookback_days}d", auto_adjust=True)
        if df.empty:
            return None

        close = df["Close"].squeeze()
        sma200 = close.rolling(sma_window).mean()
        sma50 = close.rolling(50).mean()

        # Erst jetzt auf den gewünschten Anzeigezeitraum zuschneiden
        cutoff = pd.Timestamp.now(tz=close.index.tz) - pd.Timedelta(days=display_days)
        close = close[close.index >= cutoff]
        sma200 = sma200[sma200.index >= cutoff]
        sma50 = sma50[sma50.index >= cutoff]

        if close.empty:
            return None

        dates = pd.to_datetime(close.index)
        prices = close.values

        price_min = min(prices.min(), sma200.min(), sma50.min())
        price_max = max(prices.max(), sma200.max(), sma50.max())
        margin = (price_max - price_min) * 0.05 or price_max * 0.01

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(dates, prices, color="#1f77b4", linewidth=2, label="Kurs")
        ax.plot(sma50.index, sma50.values, color="#6fd7ff", linewidth=1.2, linestyle="--", label=f"SMA50")
        ax.plot(sma200.index, sma200.values, color="#3fa7e4", linewidth=0.8, linestyle=":", label=f"SMA{sma_window}")
        # Fläche nur bis knapp unter das Minimum füllen, nicht bis 0
        ax.fill_between(dates, prices, price_min - margin, color="#1f77b4", alpha=0.07)
        ax.set_ylim(price_min - margin, price_max + margin)
        ax.set_title(f"{ticker} — Kurs der letzten {weeks} Wochen")
        ax.set_ylabel("Preis")
        ax.grid(alpha=0.25)
        ax.legend(loc="upper left", frameon=False, fontsize=8)
        fig.autofmt_xdate()

        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception as exc:
        print(f"⚠️ Fehler beim Erstellen des Charts für {ticker}: {exc}")
        return None