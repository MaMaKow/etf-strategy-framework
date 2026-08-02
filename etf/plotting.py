from io import BytesIO
from datetime import datetime, timedelta
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yfinance as yf
import pandas as pd
from matplotlib.dates import DateFormatter


def create_price_plot(ticker: str, weeks: int = 12) -> BytesIO | None:
    """Erzeugt ein kombiniertes Chart (Haupt + Inset) und gibt ein PNG-BytesIO zurück.

    Details:
    - Lädt 6 Jahre (period="6y") Kursdaten und berechnet SMA50 und SMA200 über
      den kompletten 6-Jahres-DataFrame.
    - Schneidet anschließend für die Darstellungen:
      * df_5y: letzte 5 Jahre (ab now - 5 Jahre)
      * df_30d: letzte 30 Handelstage
    - Hauptchart: 5-Jahres-Verlauf + SMA200 (X-Format YYYY-MM, Titel: "{ticker} — Langfristiger Trend (60 Monate)")
    - Inset (oben links): 30-Tage-Verlauf + SMA50 (X-Format DD.MM., Titel: "Fokus: Letzte 30 Tage")
    - Speichert mit bbox_inches='tight' und gibt BytesIO zurück.
    """
    try:
        # 1) Daten laden: 6 Jahre, damit SMA200 über die vollen 5 Jahre valide ist
        df = yf.download(ticker, period="6y", auto_adjust=True, progress=False)
        if df.empty:
            return None

        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        # Sicherstellen, dass 'Close' existiert
        if "Close" not in df.columns:
            return None

        # 2) Indikatoren über den kompletten 6-Jahres-DF berechnen
        df["SMA50"] = df["Close"].rolling(window=50, min_periods=1).mean()
        df["SMA200"] = df["Close"].rolling(window=200, min_periods=1).mean()

        # 3) Slices für Plots
        last_date = df.index.max()
        start_5y = last_date - pd.DateOffset(years=5)
        df_5y = df.loc[df.index >= start_5y].copy()
        df_30d = df.tail(30).copy()

        if df_5y.empty or df_30d.empty:
            # Wenn eines der Segmente leer ist, trotzdem versuchen zurückzugeben
            # (evtl. nur Text-Nachricht senden). Hier None signalisiert den Aufrufer.
            return None

        # 4) Plotting
        plt.style.use('seaborn-whitegrid')
        fig, ax = plt.subplots(figsize=(10, 6))

        # Hauptchart: 5 Jahre Close + SMA200
        ax.plot(df_5y.index, df_5y['Close'], label='Close', color='tab:blue', linewidth=1.5)
        ax.plot(df_5y.index, df_5y['SMA200'], label='SMA200', color='tab:orange', linewidth=1.2)
        ax.set_title(f"{ticker} — Langfristiger Trend (60 Monate)", fontsize=14, weight='semibold')
        ax.set_ylabel("Preis", fontsize=11)
        ax.legend(loc='upper left', fontsize=10)
        ax.grid(True, linestyle='--', alpha=0.4)
        ax.xaxis.set_major_formatter(DateFormatter('%Y-%m'))
        fig.autofmt_xdate(rotation=30)

        # Inset (oben links) — Lupe für letzte 30 Tage
        inset_pos = [0.18, 0.52, 0.32, 0.32]
        ax_ins = fig.add_axes(inset_pos)
        ax_ins.plot(df_30d.index, df_30d['Close'], label='Close', color='tab:blue', linewidth=1.2)
        ax_ins.plot(df_30d.index, df_30d['SMA50'], label='SMA50', color='tab:green', linewidth=1.0)
        ax_ins.set_title("Fokus: Letzte 30 Tage", fontsize=10)
        ax_ins.grid(True, linestyle='--', alpha=0.35)
        ax_ins.xaxis.set_major_formatter(DateFormatter('%d.%m.'))

        # kleinere tick-labels im inset
        for tick in list(ax_ins.get_xticklabels()) + list(ax_ins.get_yticklabels()):
            tick.set_fontsize(8)

        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return buf

    except Exception as exc:
        print(f"⚠️ Fehler beim Erstellen des Inset-Charts für {ticker}: {exc}")
        return None
