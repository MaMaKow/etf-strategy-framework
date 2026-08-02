import pandas as pd
import numpy as np

from etf.plotting import create_price_plot, prepare_plot_data


def build_close_frame(days: int = 1600) -> pd.DataFrame:
    index = pd.date_range("2019-01-01", periods=days, freq="B")
    close = pd.Series(np.linspace(100, 140, days), index=index)
    return pd.DataFrame({"Close": close})


def test_create_price_plot_uses_six_year_window(monkeypatch):
    captured = {}

    def fake_download(ticker, period=None, auto_adjust=True):
        captured["period"] = period
        return build_close_frame(1600)

    monkeypatch.setattr("etf.plotting.yf.download", fake_download)

    buf = create_price_plot("TEST.DE", weeks=4)

    assert buf is not None
    assert captured["period"] == "6y"


def test_prepare_plot_data_slices_and_calculates_indicators():
    df = build_close_frame(1600)

    df_5y, df_30d = prepare_plot_data(df)

    assert len(df_5y) == 1260
    assert len(df_30d) == 30
    assert df_5y["SMA200"].notna().all()
    assert df_30d["SMA50"].notna().all()
