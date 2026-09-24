"""Historical expected-return/covariance inputs for portfolio optimization.

Uses market_data's canonical adjusted-price history, read through the
price_history cache. Annualized with the
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
from sqlalchemy.orm import Session

from app.services import market_data, price_history
from app.services.risk_analytics import ANNUALIZATION_FACTOR
from app.services.universe import ExcludedTicker

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


@dataclass
class UniverseReturnsInput:
    inputs: ExpectedReturnsInput
    excluded: list[ExcludedTicker]


def _history_window() -> tuple[date, date]:
    end = date.today()
    return end - timedelta(days=LOOKBACK_DAYS), end


def _estimate_from_price_series(
    tickers: list[str], price_series: dict[str, list[market_data.PricePoint]]
) -> ExpectedReturnsInput:
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


def get_expected_returns_and_covariance(db: Session, tickers: list[str]) -> ExpectedReturnsInput:
    if not tickers:
        raise InsufficientHistoryError("No tickers provided for optimization.")

    start, end = _history_window()
    history = price_history.get_price_history(db, tickers, start, end)

    # A ticker with no data fails the whole request (same fail-entirely
    # policy as valuation's price fetch).
    for ticker in tickers:
        if ticker in history.errors:
            raise history.errors[ticker]

    price_series = {ticker: history.points[ticker] for ticker in tickers}
    return _estimate_from_price_series(tickers, price_series)


def get_expected_returns_for_universe(db: Session, tickers: list[str]) -> UniverseReturnsInput:
    """Like get_expected_returns_and_covariance, but excludes (with a reason)
    tickers with no data or too little history instead of failing outright."""
    if not tickers:
        raise InsufficientHistoryError("No tickers provided for recommendation.")

    start, end = _history_window()
    history = price_history.get_price_history(db, tickers, start, end)
    price_series: dict[str, list[market_data.PricePoint]] = {}
    excluded: list[ExcludedTicker] = []

    for ticker in tickers:
        if ticker in history.errors:
            excluded.append(ExcludedTicker(ticker=ticker, reason=history.errors[ticker].reason))
            continue
        points = history.points[ticker]
        if len(points) < MIN_HISTORY_OBSERVATIONS + 1:
            excluded.append(
                ExcludedTicker(
                    ticker=ticker,
                    reason=(
                        f"only {len(points)} trading day(s) of history; at least "
                        f"{MIN_HISTORY_OBSERVATIONS + 1} are needed"
                    ),
                )
            )
            continue
        price_series[ticker] = points

    if not price_series:
        raise InsufficientHistoryError(
            f"None of the {len(tickers)} requested ticker(s) have sufficient price history."
        )

    eligible = list(price_series)
    return UniverseReturnsInput(
        inputs=_estimate_from_price_series(eligible, price_series),
        excluded=excluded,
    )
