from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.market_data import (
    MarketDataUnavailableError,
    _to_yfinance_symbol,
    download_history_batch,
    get_current_price,
    get_historical_prices,
)


def test_to_yfinance_symbol_appends_ns():
    assert _to_yfinance_symbol("RELIANCE") == "RELIANCE.NS"


def test_to_yfinance_symbol_uppercases():
    assert _to_yfinance_symbol("reliance") == "RELIANCE.NS"


@patch("app.services.market_data.yf.Ticker")
def test_get_current_price_uses_fast_info(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.fast_info.last_price = 1234.5
    mock_ticker_cls.return_value = mock_ticker

    assert get_current_price("RELIANCE") == Decimal("1234.5")


@patch("app.services.market_data.yf.Ticker")
def test_get_current_price_falls_back_to_history(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.fast_info.last_price = None
    mock_ticker.history.return_value = pd.DataFrame({"Close": [100.0, 105.0]})
    mock_ticker_cls.return_value = mock_ticker

    assert get_current_price("RELIANCE") == Decimal("105.0")


@patch("app.services.market_data.yf.Ticker")
def test_get_current_price_raises_when_both_sources_fail(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.fast_info.last_price = None
    mock_ticker.history.return_value = pd.DataFrame()
    mock_ticker_cls.return_value = mock_ticker

    with pytest.raises(MarketDataUnavailableError):
        get_current_price("FAKETICKER")


@patch("app.services.market_data.yf.Ticker")
def test_get_historical_prices_raises_on_empty(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()
    mock_ticker_cls.return_value = mock_ticker

    with pytest.raises(MarketDataUnavailableError):
        get_historical_prices("FAKETICKER", date(2026, 1, 1), date(2026, 1, 31))


@patch("app.services.market_data.yf.Ticker")
def test_get_historical_prices_parses_rows(mock_ticker_cls):
    idx = pd.to_datetime(["2026-01-02", "2026-01-03"])
    df = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Volume": [1000, 1500],
        },
        index=idx,
    )
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = df
    mock_ticker_cls.return_value = mock_ticker

    points = get_historical_prices("RELIANCE", date(2026, 1, 1), date(2026, 1, 31))

    assert len(points) == 2
    assert points[0].close == Decimal("101.0")
    assert points[1].volume == 1500


def _batch_frame():
    # Shape returned by yf.download(..., group_by="ticker"): (ticker, field)
    # columns over the union of all tickers' dates; missing bars are NaN.
    idx = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
    fields = ["Open", "High", "Low", "Close", "Volume"]
    columns = pd.MultiIndex.from_product([["RELIANCE.NS", "TCS.NS"], fields])
    nan = float("nan")
    data = [
        [100.0, 102.0, 99.0, 101.0, 1000, 3000.0, 3010.0, 2990.0, 3005.0, 500],
        [101.0, 103.0, 100.0, 102.0, 1500, nan, nan, nan, nan, nan],
        [102.0, 104.0, 101.0, 103.0, 1200, 3005.0, 3020.0, 3000.0, 3015.0, 700],
    ]
    return pd.DataFrame(data, index=idx, columns=columns)


@patch("app.services.market_data.yf.download")
def test_download_history_batch_parses_grouped_frame(mock_download):
    mock_download.return_value = _batch_frame()

    result = download_history_batch(["RELIANCE", "TCS", "NODATA"], date(2026, 1, 1), date(2026, 1, 7))

    kwargs = mock_download.call_args.kwargs
    assert mock_download.call_args.args[0] == ["RELIANCE.NS", "TCS.NS", "NODATA.NS"]
    assert kwargs["auto_adjust"] is True
    assert kwargs["group_by"] == "ticker"
    assert (kwargs["start"], kwargs["end"]) == (date(2026, 1, 1), date(2026, 1, 7))

    assert [p.date for p in result["RELIANCE"]] == [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6)]
    assert result["RELIANCE"][1].close == Decimal("102.0")
    # NaN row for TCS on 2026-01-05 is dropped, not stored as data.
    assert [p.date for p in result["TCS"]] == [date(2026, 1, 2), date(2026, 1, 6)]
    assert result["TCS"][1].volume == 700
    assert result["NODATA"] == []


@patch("app.services.market_data.yf.download")
def test_download_history_batch_matches_single_ticker_parsing(mock_download):
    frame = _batch_frame()
    mock_download.return_value = frame
    batched = download_history_batch(["RELIANCE"], date(2026, 1, 1), date(2026, 1, 7))

    with patch("app.services.market_data.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.history.return_value = frame["RELIANCE.NS"]
        single = get_historical_prices("RELIANCE", date(2026, 1, 1), date(2026, 1, 7))

    assert batched["RELIANCE"] == single


@patch("app.services.market_data.yf.download")
def test_download_history_batch_raises_when_request_fails(mock_download):
    mock_download.side_effect = RuntimeError("network down")
    with pytest.raises(MarketDataUnavailableError) as exc_info:
        download_history_batch(["RELIANCE"], date(2026, 1, 1), date(2026, 1, 7))
    assert exc_info.value.reason.startswith("history request failed")
