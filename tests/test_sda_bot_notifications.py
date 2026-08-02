from datetime import date

from etf.sda_bot import SDABot


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
