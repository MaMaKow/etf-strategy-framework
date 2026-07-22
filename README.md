# ETF Backtest Framework

A modular, quantitative backtesting framework for ETF strategies, featuring the Systematic Drawdown Accumulator (SDA) approach.

## Features

- **Modular Architecture**: Clean separation of data loading, strategy logic, portfolio management, analytics, and backtesting engine.
- **SDA Strategy**: Path-dependent cashflow state machine with dip-buy tiers and opportunity cost reserves.
- **Parameter Sweeps**: Automated grid search over strategy parameters.
- **Comprehensive Analytics**: CAGR, Sharpe ratio, drawdown analysis, and equity curve plotting.
- **CLI Interface**: Easy command-line execution with optional parameter sweeps.

## Installation

```bash
pip install -e .
```

## Usage

### Basic Backtest

```bash
python -m etf.cli.main
```

### With Parameter Sweep

```bash
python -m etf.cli.main --sweep
```

### Strategie-Auswahl per CLI

```bash
python -m etf.cli.main run --strategy sda --ticker EUNL.DE --start 2014-01-01 --end 2024-12-31
python -m etf.cli.main run --strategy adaptive_dca --ticker EUNL.DE --monthly 300 --adca-reserve-pct 0.1
python -m etf.cli.main compare --strategies sda,adaptive_dca,dca --ticker EUNL.DE --start 2014-01-01 --end 2024-12-31
```

Weitere Details: `docs/adaptive_dca_strategy.md`.

## Server Deployment

### 1) System vorbereiten

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

### 2) Repository klonen

```bash
git clone <REPO_URL>
cd etf-strategy-framework
```

### 3) Virtuelle Umgebung einrichten

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -e .
```

### 4) Zusätzliche Bot-Abhängigkeiten installieren

```bash
pip install mysql-connector-python python-dotenv PyYAML requests
```

### 5) Datenbank konfigurieren

Erstelle die MariaDB-Datenbank und stelle sicher, dass der Benutzer Zugriff hat. Beispiel:

```bash
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS etf_bot;"
```

### 6) Umgebungsvariablen setzen

Erstelle eine `.env`-Datei im Projektverzeichnis mit mindestens diesen Einträgen:

```env
MARIADB_USER=dein_db_user
MARIADB_PASSPHRASE=dein_db_passwort
TELEGRAM_BOT_TOKEN=dein_telegram_token
TELEGRAM_CHAT_ID=deine_chat_id
```

### 7) Bot-Konfiguration anlegen

Erstelle `bot_config.yaml` mit globalen Einstellungen und mehreren ETFs. Beispiel:

```yaml
global:
  vix_ticker: "^VIX"
  slippage: 0.0005
  vix_threshold: 15.0
  min_order_eur: 100.0
  ocf_target: 100.0
  cooldown_min: 5
  ocf_low_pct: 0.30
  ocf_mid_pct: 1.00
  t1_requires_above_sma200: true
  dip_tiers:
    - [ -0.05, 0.20, "T1" ]
    - [ -0.10, 0.30, "T2" ]
    - [ -0.20, 0.40, "T3" ]
    - [ -0.30, 0.50, "T4" ]
    - [ -0.40, 0.60, "T5" ]

etfs:
  EUNL.DE:
    monthly_contribution: 300.0
    monthly_savings: 150.0
  SNAW.DE:
    monthly_contribution: 200.0
    monthly_savings: 100.0
```

### 8) Datenbanktabellen initialisieren

```bash
./venv/bin/python -m etf.cli.main bot-init
```

### 9) Bot ausführen

Einzelnen ETF ausführen:

```bash
./venv/bin/python -m etf.cli.main bot-run --ticker EUNL.DE
```

Alle konfigurierten ETFs ausführen:

```bash
./venv/bin/python -m etf.cli.main bot-run
```

### 10) Automatisierung mit Cron

Füge einen Cronjob hinzu, um den Bot täglich auszuführen:

```bash
crontab -e
```

```cron
0 18 * * * cd /pfad/zum/etf-strategy-framework && /pfad/zum/venv/bin/python -m etf.cli.main bot-run >> /pfad/zum/etf-strategy-framework/bot.log 2>&1
```

## Configuration

Edit `etf/config.py` or pass configuration via CLI.

### Value Averaging Parameters

- `--va-mode`: `linear` or `exponential` (default: `linear`)
- `--va-base`: starting target amount for VA; if not set, defaults to `monthly_contribution`
- `--va-rate`: growth rate for exponential VA (default: `0.0`)
- `--va-allow-negative`: allow negative adjustments / de-risking actions (default: buy-only)

## Architecture

- `data/`: Data loading and indicator computation
- `strategies/`: Trading strategy implementations
- `portfolio/`: Portfolio state and order execution
- `analytics/`: Performance metrics and reporting
- `backtest/`: Simulation engine and parameter sweeps
- `cli/`: Command-line interface

## Extending

Implement new strategies by inheriting from `etf.strategies.base.Strategy` and overriding `on_day()`.

## License

MIT