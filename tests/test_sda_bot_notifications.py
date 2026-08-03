from datetime import date
from pathlib import Path

import yaml

from etf.sda_bot import SDABot, load_bot_config


def test_log_and_notify_sends_single_photo_message(monkeypatch):
    calls = []

    def fake_create_price_plot(ticker, weeks=4):
        calls.append(("create", ticker, weeks))
        return object()

    def fake_send_telegram_photo(self, photo_buf, caption=None):
        calls.append(("photo", caption))

    monkeypatch.setattr("etf.sda_bot.create_price_plot", fake_create_price_plot)
    monkeypatch.setattr(SDABot, "send_telegram_photo", fake_send_telegram_photo)

    bot = SDABot({})
    bot.log_and_notify("TEST.DE", date(2024, 1, 2), "HOLD", reason="Test", market_data={})

    assert calls[0][0] == "create"
    assert calls[1][0] == "photo"
    assert calls[1][1].startswith("*SDA-Bot für TEST.DE*")


def test_load_bot_config_enriches_missing_etf_metadata(tmp_path, monkeypatch):
    config_path = tmp_path / "bot_config.yaml"
    config_path.write_text(
        "etfs:\n  TEST.DE:\n    monthly_contribution: 10.0\n",
        encoding="utf-8",
    )

    def fake_lookup_etf_metadata(ticker):
        assert ticker == "TEST.DE"
        return {
            "full_name": "Example ETF",
            "isin": "DE0001234567",
            "info_url": "https://example.com/etf",
        }

    monkeypatch.setattr("etf.sda_bot.lookup_etf_metadata", fake_lookup_etf_metadata)

    config = load_bot_config(str(config_path))

    assert config["etfs"]["TEST.DE"]["full_name"] == "Example ETF"
    assert config["etfs"]["TEST.DE"]["isin"] == "DE0001234567"
    assert config["etfs"]["TEST.DE"]["info_url"] == "https://example.com/etf"

    written_config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    assert written_config["etfs"]["TEST.DE"]["full_name"] == "Example ETF"
