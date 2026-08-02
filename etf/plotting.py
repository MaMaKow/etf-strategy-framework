from io import BytesIO
from typing import Optional, Tuple
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import yfinance as yf
import pandas as pd


def prepare_plot_data(df: pd.DataFrame) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Bereitet die Daten für ein 5-Jahres-Hauptchart und ein 30-Tage-Inset vor."""
    if df is None or df.empty:
        return None, None

    close = df["Close"].squeeze()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    close = pd.Series(close, index=df.index).astype(float).sort_index().dropna()
    if close.empty:
        return None, None

    sma50 = close.rolling(50, min_periods=50).mean()
    sma200 = close.rolling(200, min_periods=200).mean()

    full_df = pd.DataFrame({"Close": close, "SMA50": sma50, "SMA200": sma200})
    df_5y = full_df.tail(1260)
    df_30d = full_df.tail(30)

    return df_5y, df_30d


def create_price_plot(ticker: str, weeks: int = 12) -> BytesIO | None:
    """Erstellt ein kombiniertes Inset-Chart-Bild mit 5-Jahres-Trend und 30-Tage-Fokus."""
    try:
        df = yf.download(ticker, period="6y", auto_adjust=True)
        if df.empty:
            return None

        plot_frames = prepare_plot_data(df)
        if plot_frames[0] is None or plot_frames[1] is None:
            return None

        df_5y, df_30d = plot_frames
        if df_5y.empty or df_30d.empty:
            return None

        fig = plt.figure(figsize=(12, 6))
        main_ax = fig.add_subplot(111)
        main_ax.plot(df_5y.index, df_5y["Close"], color="#1f77b4", linewidth=2, label="Close")
        main_ax.plot(df_5y.index, df_5y["SMA50"], color="#e74c3c", linewidth=1.3, linestyle="--", label="SMA50")
        main_ax.plot(df_5y.index, df_5y["SMA200"], color="#3fa7e4", linewidth=1.2, linestyle=":", label="SMA200")
        main_ax.set_title(f"{ticker} — Langfristiger Trend (60 Monate)", fontsize=13)
        main_ax.set_ylabel("Preis", fontsize=10)
        main_ax.grid(alpha=0.25)
        main_ax.legend(loc="upper left", frameon=False, fontsize=8)
        main_ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        main_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        plt.setp(main_ax.get_xticklabels(), rotation=45, ha="right")

        inset_ax = fig.add_axes([0.17, 0.56, 0.30, 0.24])
        inset_ax.plot(df_30d.index, df_30d["Close"], color="#1f77b4", linewidth=1.8)
        inset_ax.plot(df_30d.index, df_30d["SMA50"], color="#e74c3c", linewidth=1.1, linestyle="--", label="SMA50")
        inset_ax.set_title("Fokus: Letzte 30 Tage", fontsize=9)
        inset_ax.grid(alpha=0.25)
        inset_ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        plt.setp(inset_ax.get_xticklabels(), rotation=45, ha="right")

        fig.subplots_adjust(left=0.08, right=0.98, top=0.90, bottom=0.16)

        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception as exc:
        print(f"⚠️ Fehler beim Erstellen des Charts für {ticker}: {exc}")
        return None