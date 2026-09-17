"""Historical expected-return/covariance inputs for portfolio optimization.

Uses market_data's canonical adjusted-price history. Annualized with the
same ANNUALIZATION_FACTOR (252) convention used elsewhere in risk analytics.
Ledoit-Wolf shrinkage (sklearn) is used for the covariance estimate, a
standard, more stable alternative to a raw sample covariance on limited
history.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
from sklearn.covariance import LedoitWolf

from app.services import market_data
from app.services.risk_analytics import ANNUALIZATION_FACTOR

LOOKBACK_DAYS = 365
MIN_HISTORY_OBSERVATIONS = 30


class InsufficientHistoryError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass
class ExpectedReturnsInput:
    tickers: list[str]
    expected_returns: list[Decimal]
    covariance: list[list[Decimal]]


def get_expected_returns_and_covariance(tickers: list[str]) -> ExpectedReturnsInput:
    if not tickers:
        raise InsufficientHistoryError("No tickers provided for optimization.")

    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)

    # market_data raises MarketDataUnavailableError per-ticker if a symbol
    # has no data — let it propagate (same fail-entirely policy as
    # valuation's price fetch).
    price_series = {
        ticker: market_data.get_historical_prices(ticker, start, end) for ticker in tickers
    }

    # Align on dates common to every ticker so the return/covariance matrix
    # is well-defined (simplest safe approach; no forward-fill/interpolation).
    common_dates = None
    for points in price_series.values():
        dates = {p.date for p in points}
        common_dates = dates if common_dates is None else common_dates & dates
    common_dates = sorted(common_dates) if common_dates else []

    if len(common_dates) < MIN_HISTORY_OBSERVATIONS + 1:
        raise InsufficientHistoryError(
            f"Only {len(common_dates)} overlapping trading day(s) of history available "
            f"across {len(tickers)} ticker(s); at least {MIN_HISTORY_OBSERVATIONS + 1} "
            "are needed."
        )

    closes_by_ticker = {
        ticker: {p.date: p.close for p in points} for ticker, points in price_series.items()
    }

    returns_matrix = []
    for i in range(1, len(common_dates)):
        prev_date, curr_date = common_dates[i - 1], common_dates[i]
        row = []
        for ticker in tickers:
            prev_close = closes_by_ticker[ticker][prev_date]
            curr_close = closes_by_ticker[ticker][curr_date]
            row.append(0.0 if prev_close == 0 else float((curr_close - prev_close) / prev_close))
        returns_matrix.append(row)

    returns_array = np.array(returns_matrix)  # (n_obs, n_tickers)

    mean_daily = returns_array.mean(axis=0)
    expected_returns = [Decimal(str(m * ANNUALIZATION_FACTOR)) for m in mean_daily]

    shrunk = LedoitWolf().fit(returns_array)
    annualized_cov = shrunk.covariance_ * ANNUALIZATION_FACTOR
    covariance = [[Decimal(str(v)) for v in row] for row in annualized_cov]

    return ExpectedReturnsInput(tickers=tickers, expected_returns=expected_returns, covariance=covariance)
