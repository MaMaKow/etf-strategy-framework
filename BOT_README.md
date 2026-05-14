# SDA Trading Bot

Ein automatischer Trading-Bot, der die SDA (Systematic Dip Accumulation) Strategie täglich ausführt und Kaufempfehlungen via Telegram versendet.

## Übersicht

Der Bot wertet jeden Tag die Marktbedingungen aus und trifft Kaufentscheidungen basierend auf:
- Drawdown vom 52-Wochen-Hoch
- RSI-Indikator
- VIX-Volatilität
- Erholungstage (Recovery Days)
- Opportunity Cost Reserve (OCF)

## Installation

### Voraussetzungen
- Python 3.8+
- MariaDB/MySQL Datenbank
- Telegram Bot Token (von @BotFather)

### Setup

1. **Datenbank erstellen:**
   ```bash
   mysql -u root -p
   CREATE DATABASE etf_bot;
   ```

2. **Umgebungsvariablen setzen (.env):**
   ```bash
   MARIADB_USER=your_db_user
   MARIADB_PASSPHRASE=your_db_password
   TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
   TELEGRAM_CHAT_ID=your_chat_id
   ```

3. **Bot initialisieren:**
   ```bash
   ./venv/bin/python -m etf.cli.main bot-init
   ```

4. **Konfiguration anpassen (bot_config.yaml):**
   ```yaml
   etf_ticker: "EUNL.DE"
   monthly_contribution: 300.0
   monthly_savings: 150.0
   # ... weitere Parameter
   ```

## Verwendung

### Einzelne Bewertung
```bash
./venv/bin/python -m etf.cli.main bot-run --ticker EUNL.DE
```

### Automatische Ausführung
Füge dies zu deinem Cron-Job hinzu (werktags 9:00 Uhr):
```bash
0 9 * * 1-5 /path/to/venv/bin/python -m etf.cli.main bot-run --ticker EUNL.DE
```

## Datenbank-Schema

### bot_state
Speichert den aktuellen Portfolio-Zustand pro ETF:
- `cash_ocf`: Verfügbare Cash-Reserve
- `units`: Anzahl gehaltener ETF-Einheiten
- `portfolio_value`: Aktueller Portfolio-Wert
- `cooldowns`: Aktive Sperrfristen als JSON
- `total_contributions`: Kumulierte Einzahlungen
- `total_cashflow`: Kumulierter Cashflow
- `last_monthly_date`: Datum der letzten monatlichen Einzahlung

### trade_log
Alle ausgeführten Trades:
- `date`: Handelsdatum
- `tier`: SDA-Tier (T1, T2, etc.)
- `amount_eur`: Handelsbetrag
- `price`: Ausführungspreis
- `units`: Gekaufte Einheiten
- `drawdown`: Drawdown zum Zeitpunkt des Kaufs
- `vix`: VIX-Wert zum Zeitpunkt des Kaufs

### signal_log
Alle täglichen Empfehlungen:
- `recommendation`: 'BUY' oder 'HOLD'
- `reason`: Erklärung der Entscheidung
- `market_data`: Marktdaten als JSON

## Konfiguration

### Strategie-Parameter

| Parameter | Beschreibung | Standard |
|-----------|-------------|----------|
| `monthly_contribution` | Monatlicher Gesamtbetrag | 300.0 |
| `monthly_savings` | Monatlicher ETF-Sparplan | 150.0 |
| `ocf_target` | Ziel-OCF-Reserve | 100.0 |
| `min_order_eur` | Mindestordergröße | 100.0 |
| `vix_threshold` | VIX-Grenzwert für Panik-Modus | 15.0 |

### Dip-Buy Tiers

Die SDA-Strategie verwendet mehrere Dip-Buy-Stufen:

| Tier | Drawdown | OCF-Anteil | Beschreibung |
|------|----------|------------|-------------|
| T1 | -5% | 20% | Leichter Dip |
| T2 | -10% | 30% | Mittlerer Dip |
| T3 | -20% | 40% | Starker Dip |
| T4 | -30% | 50% | Sehr starker Dip |
| T5 | -40% | 60% | Extrem starker Dip |

## Telegram-Benachrichtigungen

Der Bot sendet täglich eine Nachricht mit:
- **Bei Handel:** Konkrete Kaufempfehlung mit Betrag und Preis
- **Bei keinem Handel:** Berechnete Parameter und Gründe

Beispiel-Nachricht:
```
*SDA-Bot für EUNL.DE*

Kein Handel: Drawdown zu gering (-0.5%), OCF-Reserve zu niedrig (50.00 €)

Marktdaten:
• Preis: 120.50 €
• Drawdown: -0.5%
• RSI: 55.2
• VIX: 14.2
• Erholungstage: 3

Portfolio:
• Cash OCF: 50.00 €
• Einheiten: 25.5
• Portfolio-Wert: 3075.00 €
```

## Sicherheit

- **Testen:** Führe Backtests durch bevor du reale Trades ausführst
- **Limits:** Setze tägliche/maximale Handelslimits
- **Überwachung:** Überwache die Bot-Aktivitäten regelmäßig
- **Backup:** Sichere die Datenbank regelmäßig

## Troubleshooting

### Bot startet nicht
- Prüfe `.env` Datei auf korrekte Umgebungsvariablen
- Stelle sicher, dass die Datenbank erreichbar ist
- Überprüfe `bot_config.yaml` auf Syntaxfehler

### Keine Telegram-Nachrichten
- Verifiziere Bot-Token und Chat-ID
- Prüfe ob der Bot bei Telegram registriert ist

### Falsche Signale
- Vergleiche mit Backtest-Ergebnissen
- Prüfe Marktdaten-Quelle (Yahoo Finance)
- Überprüfe Konfigurationsparameter