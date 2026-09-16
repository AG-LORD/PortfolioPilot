from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.market_data import (
    MarketDataUnavailableError,
    _to_yfinance_symbol,
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
