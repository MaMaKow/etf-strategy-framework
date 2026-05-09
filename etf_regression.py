import yfinance as yf
import plotext as plotext
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

# -----------------------------
# Parameter
# -----------------------------
TICKER = "SAWD.L"               # iShares MSCI World ESG Screened
START_DATE = "2020-01-01"
END_DATE = datetime.today().strftime("%Y-%m-%d")

# -----------------------------
# Daten laden
# -----------------------------
df = yf.download(
    TICKER,
    start=START_DATE,
    end=END_DATE,
    auto_adjust=True,
    progress=False
)

if df.empty:
    raise RuntimeError("Keine Kursdaten geladen")

# -----------------------------
# Regression vorbereiten
# -----------------------------
df = df.reset_index()
df["t"] = np.arange(len(df))    # Zeitindex
y = df["Close"].values
x = df["t"].values

# -----------------------------
# Lineare Regression
# y = m*x + b
# -----------------------------
# Lineare Regression
# Lineare Regression
m, b = np.polyfit(x, y, 1)
m = m.item()
b = b.item()

# Gesamtveränderung
total_change = (y[-1] - y[0]).item()
df["trend"] = m * x + b

# -----------------------------
# Ergebnisse ausgeben
# -----------------------------
print("Lineare Regression seit", START_DATE)
print("----------------------------------")
print(f"Steigung (m): {m:.6f} pro Handelstag")
print(f"Achsenabschnitt (b): {b:.2f}")
print(f"Gesamtveränderung im Zeitraum: {total_change:.2f}")
print(f"Durchschnittliche Tagesänderung: {m:.4f}")

# Logarithmische Steigung (kontinuierliche Wachstumsrate)
log_y = np.log(y)
m_log, b_log = np.polyfit(x, log_y, 1)
m_log = m_log.item()

# Jahresrendite
annual_return = (np.exp(m_log * 250) - 1) * 100
print(f"Geschätzte jährliche Rendite: {annual_return:.2f}%")

# -----------------------------
# Plot
# -----------------------------
plt.figure(figsize=(10, 5))
plt.plot(df["Date"], df["Close"], label="Kurs", linewidth=2)
plt.plot(df["Date"], df["trend"], label="Lineare Regression", linestyle="--")
plt.title(f"{TICKER} – Lineare Regression seit {START_DATE}")
plt.xlabel("Datum")
plt.ylabel("Preis")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()
plt.savefig("/var/www/html/etf_plot.png") # Pfad zu deinem Web-Verzeichnis
print("Plot gespeichert unter /var/www/html/etf_plot.png")
