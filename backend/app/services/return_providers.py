"""Expected-return providers for the optimizer.

Every provider returns ANNUALIZED ARITHMETIC expected returns, the unit the
optimizer uses: mean daily return x ANNUALIZATION_FACTOR (252).

- HistoricalMeanProvider: 252 x the mean of each ticker's last BASELINE_LOOKBACK
  (252) daily returns. This is exactly the walk-forward evaluation baseline
  (app.ml.baseline.historical_mean_forecast), annualized instead of scaled to
  the 20-day horizon.
- MLForecastProvider: trains the fixed-hyperparameter model on the
  point-in-time feature panel, using every labelled row (labels end on or
  before the latest price date, so nothing unknown is used), predicts each
  ticker's latest feature row, and converts the 20-trading-day forecast to
  the annual unit arithmetically: r20 x 252 / 20. Tickers without a usable
  ML forecast fall back to the historical estimate, and `sources` records
  which one each ticker got.

This module does not touch the database: callers pass price histories.
"""

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from app.ml.baseline import BASELINE_LOOKBACK, historical_mean_forecast
from app.ml.models import HIST_GRADIENT_BOOSTING, make_model
from app.services.features import (
    DEFAULT_HORIZON,
    FEATURE_COLUMNS,
    LABEL_COLUMN,
    build_panel_from_prices,
)
from app.services.market_calendar import ANNUALIZATION_FACTOR
from app.services.market_data import PricePoint

HISTORICAL = "historical"
ML = "ml"

# BASELINE_LOOKBACK daily returns need one more price than that.
MIN_PRICE_ROWS = BASELINE_LOOKBACK + 1

# Calendar days of price history each provider needs loaded. 420 calendar
# days reliably covers 253 NSE trading days; the ML window leaves about five
# years of labelled training rows after the 252-day feature history.
HISTORICAL_HISTORY_DAYS = 420
ML_HISTORY_DAYS = 6 * 365

# Chosen from the NIFTY50 walk-forward evaluation (results/evaluation_2026-09-25.json):
# highest mean IC of the models evaluated. That is a selection made on the
# evaluation period, so its IC there is not an independent out-of-sample result.
ML_MODEL = HIST_GRADIENT_BOOSTING
ML_MODEL_VERSION = f"{ML_MODEL}-h{DEFAULT_HORIZON}-f{len(FEATURE_COLUMNS)}-v1"
MIN_TRAINING_ROWS = 500


@dataclass
class ReturnEstimates:
    expected_returns: dict[str, Decimal]  # annualized, per ticker
    sources: dict[str, str]  # HISTORICAL or ML, per ticker
    model_version: str | None = None
    forecast_as_of: date | None = None


class ExpectedReturnProvider(ABC):
    name: str
    history_calendar_days: int

    @abstractmethod
    def estimate(self, prices: dict[str, list[PricePoint]]) -> ReturnEstimates:
        """prices: date-sorted history per ticker, each with at least MIN_PRICE_ROWS rows."""


def annualized_historical_mean(points: list[PricePoint]) -> Decimal:
    close = pd.Series([float(p.close) for p in points])
    value = historical_mean_forecast(close, horizon=ANNUALIZATION_FACTOR).iloc[-1]
    if pd.isna(value):
        raise ValueError(f"needs at least {MIN_PRICE_ROWS} prices, got {len(points)}")
    return Decimal(str(value))


def horizon_forecast_to_annual(forecast: float, horizon: int = DEFAULT_HORIZON) -> float:
    """Arithmetic conversion, matching mean-daily-return x 252: r_h x 252 / h."""
    return forecast * ANNUALIZATION_FACTOR / horizon


class HistoricalMeanProvider(ExpectedReturnProvider):
    name = HISTORICAL
    history_calendar_days = HISTORICAL_HISTORY_DAYS

    def estimate(self, prices: dict[str, list[PricePoint]]) -> ReturnEstimates:
        return ReturnEstimates(
            expected_returns={t: annualized_historical_mean(points) for t, points in prices.items()},
            sources={t: HISTORICAL for t in prices},
        )


class MLForecastProvider(ExpectedReturnProvider):
    name = ML
    history_calendar_days = ML_HISTORY_DAYS

    def __init__(self, model_name: str = ML_MODEL, horizon: int = DEFAULT_HORIZON):
        self.model_name = model_name
        self.horizon = horizon

    def estimate(self, prices: dict[str, list[PricePoint]]) -> ReturnEstimates:
        historical = HistoricalMeanProvider().estimate(prices)
        tickers = list(prices)
        panel = build_panel_from_prices(tickers, prices, errors={}, horizon=self.horizon).panel
        finite_features = np.isfinite(panel[FEATURE_COLUMNS].to_numpy(dtype=float)).all(axis=1)
        panel = panel[finite_features]

        train = panel[panel[LABEL_COLUMN].notna() & np.isfinite(panel[LABEL_COLUMN].to_numpy(dtype=float))]
        if len(train) < MIN_TRAINING_ROWS:
            return historical

        forecast_as_of = panel["date"].max()
        latest = panel[panel["date"] == forecast_as_of]
        model = make_model(self.model_name).fit(train[FEATURE_COLUMNS], train[LABEL_COLUMN])
        predictions = model.predict(latest[FEATURE_COLUMNS])

        expected = dict(historical.expected_returns)
        sources = dict(historical.sources)
        for ticker, forecast in zip(latest["ticker"], predictions):
            if math.isfinite(forecast):
                expected[ticker] = Decimal(str(horizon_forecast_to_annual(float(forecast), self.horizon)))
                sources[ticker] = ML

        if ML not in sources.values():
            return historical
        return ReturnEstimates(
            expected_returns=expected,
            sources=sources,
            model_version=ML_MODEL_VERSION,
            forecast_as_of=pd.Timestamp(forecast_as_of).date(),
        )
