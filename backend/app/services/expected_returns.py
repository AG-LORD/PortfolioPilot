"""Expected-return/covariance inputs for portfolio optimization.

Prices come from market_data's canonical adjusted history, read through the
price_history cache.

- Expected returns come from an ExpectedReturnProvider (return_providers.py).
  All providers use the annualized arithmetic convention (mean daily
  return x 252). The default is the historical mean over each ticker's last
  252 daily returns, the same definition as the evaluation baseline.
- Covariance: Ledoit-Wolf shrinkage on daily returns over the dates common to
  all tickers, restricted to the same trailing 252-return window, annualized
  x 252. It is the same for every provider.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
from sklearn.covariance import LedoitWolf
from sqlalchemy.orm import Session

from app.ml.baseline import BASELINE_LOOKBACK
from app.services import market_data, price_history
from app.services.market_calendar import ANNUALIZATION_FACTOR
from app.services.return_providers import (
    MIN_PRICE_ROWS,
    Driver,
    ExpectedReturnProvider,
    HistoricalMeanProvider,
)
from app.services.universe import ExcludedTicker

# Minimum overlapping daily returns across all tickers for the covariance.
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
    sources: dict[str, str] = field(default_factory=dict)
    model_version: str | None = None
    forecast_as_of: date | None = None
    clipped: dict[str, bool] = field(default_factory=dict)
    drivers: dict[str, list[Driver]] = field(default_factory=dict)
    typical_estimates: dict[str, Decimal] = field(default_factory=dict)
    forecast_source: str | None = None


def _history_window(calendar_days: int) -> tuple[date, date]:
    end = date.today()
    return end - timedelta(days=calendar_days), end


def _short_history_reason(rows: int) -> str:
    return f"only {rows} trading day(s) of history; at least {MIN_PRICE_ROWS} are needed"


def ledoit_wolf_covariance(
    tickers: list[str], price_series: dict[str, list[market_data.PricePoint]]
) -> list[list[Decimal]]:
    # Align on dates common to every ticker so the return/covariance matrix
    # is well-defined (simplest safe approach; no forward-fill/interpolation).
    common_dates = None
    for ticker in tickers:
        dates = {p.date for p in price_series[ticker]}
        common_dates = dates if common_dates is None else common_dates & dates
    common_dates = sorted(common_dates) if common_dates else []

    if len(common_dates) < MIN_HISTORY_OBSERVATIONS + 1:
        raise InsufficientHistoryError(
            f"Only {len(common_dates)} overlapping trading day(s) of history available "
            f"across {len(tickers)} ticker(s); at least {MIN_HISTORY_OBSERVATIONS + 1} "
            "are needed."
        )

    closes_by_ticker = {ticker: {p.date: p.close for p in price_series[ticker]} for ticker in tickers}

    returns_matrix = []
    for i in range(1, len(common_dates)):
        prev_date, curr_date = common_dates[i - 1], common_dates[i]
        row = []
        for ticker in tickers:
            prev_close = closes_by_ticker[ticker][prev_date]
            curr_close = closes_by_ticker[ticker][curr_date]
            row.append(0.0 if prev_close == 0 else float((curr_close - prev_close) / prev_close))
        returns_matrix.append(row)

    returns_array = np.array(returns_matrix)[-BASELINE_LOOKBACK:]  # (n_obs, n_tickers)
    shrunk = LedoitWolf().fit(returns_array)
    annualized_cov = shrunk.covariance_ * ANNUALIZATION_FACTOR
    return [[Decimal(str(v)) for v in row] for row in annualized_cov]


def _estimate_from_price_series(
    tickers: list[str], price_series: dict[str, list[market_data.PricePoint]]
) -> ExpectedReturnsInput:
    """Historical-mean expected returns plus covariance; every ticker must
    have at least MIN_PRICE_ROWS prices."""
    for ticker in tickers:
        rows = len(price_series[ticker])
        if rows < MIN_PRICE_ROWS:
            raise InsufficientHistoryError(f"{ticker} has {_short_history_reason(rows)}.")

    estimates = HistoricalMeanProvider().estimate({t: price_series[t] for t in tickers})
    return ExpectedReturnsInput(
        tickers=tickers,
        expected_returns=[estimates.expected_returns[t] for t in tickers],
        covariance=ledoit_wolf_covariance(tickers, price_series),
    )


def get_expected_returns_and_covariance(db: Session, tickers: list[str]) -> ExpectedReturnsInput:
    if not tickers:
        raise InsufficientHistoryError("No tickers provided for optimization.")

    start, end = _history_window(HistoricalMeanProvider.history_calendar_days)
    history = price_history.get_price_history(db, tickers, start, end)

    # A ticker with no data fails the whole request (same fail-entirely
    # policy as valuation's price fetch).
    for ticker in tickers:
        if ticker in history.errors:
            raise history.errors[ticker]

    price_series = {ticker: history.points[ticker] for ticker in tickers}
    return _estimate_from_price_series(tickers, price_series)


def get_expected_returns_for_universe(
    db: Session, tickers: list[str], provider: ExpectedReturnProvider | None = None
) -> UniverseReturnsInput:
    """Like get_expected_returns_and_covariance, but excludes (with a reason)
    tickers with no data or too little history instead of failing outright.
    Expected returns come from `provider` (historical mean by default)."""
    if not tickers:
        raise InsufficientHistoryError("No tickers provided for recommendation.")
    provider = provider or HistoricalMeanProvider()

    start, end = _history_window(provider.history_calendar_days)
    history = price_history.get_price_history(db, tickers, start, end)
    price_series: dict[str, list[market_data.PricePoint]] = {}
    excluded: list[ExcludedTicker] = []

    for ticker in tickers:
        if ticker in history.errors:
            excluded.append(ExcludedTicker(ticker=ticker, reason=history.errors[ticker].reason))
            continue
        points = history.points[ticker]
        if len(points) < MIN_PRICE_ROWS:
            excluded.append(ExcludedTicker(ticker=ticker, reason=_short_history_reason(len(points))))
            continue
        price_series[ticker] = points

    if not price_series:
        raise InsufficientHistoryError(
            f"None of the {len(tickers)} requested ticker(s) have sufficient price history."
        )

    eligible = list(price_series)
    estimates = provider.estimate(price_series)
    return UniverseReturnsInput(
        inputs=ExpectedReturnsInput(
            tickers=eligible,
            expected_returns=[estimates.expected_returns[t] for t in eligible],
            covariance=ledoit_wolf_covariance(eligible, price_series),
        ),
        excluded=excluded,
        sources=estimates.sources,
        model_version=estimates.model_version,
        forecast_as_of=estimates.forecast_as_of,
        clipped=estimates.clipped,
        drivers=estimates.drivers,
        typical_estimates=estimates.typical_estimates,
        forecast_source=estimates.forecast_source,
    )
