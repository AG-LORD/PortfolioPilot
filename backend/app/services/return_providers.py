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

  Signal control: each raw 20-day forecast is clipped to the
  [CLIP_LOWER_Q, CLIP_UPPER_Q] quantiles of the training labels of that fit
  (training rows only, so point-in-time) before annualizing; `clipped`
  records which tickers were capped.

  Explanations: for every ML-forecast ticker, `drivers` holds a local
  ablation attribution per feature: the (unclipped) prediction with the
  actual features minus the prediction with that one feature replaced by its
  training-set median, annualized like expected_return. `typical_estimates`
  is the annualized prediction with every feature at its training median.
  These are approximate (interactions mean they need not sum to the
  estimate) and explain the model, not the market.

  Nightly precomputed forecasts (scripts/nightly_jobs.py, stored in
  ml_forecasts) come from the same fit_and_forecast() on the pooled NIFTY50
  panel; callers can pass them in as `stored` to skip training.

This module does not touch the database: callers pass price histories and
any stored forecasts.
"""

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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

# Where the ML forecasts came from. "on_request" if any ticker needed a fit
# on the requested prices, "precomputed" if all came from the nightly store.
FORECAST_PRECOMPUTED = "precomputed"
FORECAST_ON_REQUEST = "on_request"

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

# Forecasts are clipped to these quantiles of the fit's training labels.
CLIP_LOWER_Q = 0.01
CLIP_UPPER_Q = 0.99

# Decimal places kept for driver values and contributions.
DRIVER_DECIMALS = 6


@dataclass
class Driver:
    feature: str
    value: Decimal  # the ticker's actual feature value
    contribution: Decimal  # annualized, same unit as expected_return


@dataclass
class ReturnEstimates:
    expected_returns: dict[str, Decimal]  # annualized, per ticker
    sources: dict[str, str]  # HISTORICAL or ML, per ticker
    model_version: str | None = None
    forecast_as_of: date | None = None
    # Only filled for ML-forecast tickers; absent tickers mean "not clipped",
    # "no drivers" and "no typical estimate".
    clipped: dict[str, bool] = field(default_factory=dict)
    drivers: dict[str, list[Driver]] = field(default_factory=dict)
    typical_estimates: dict[str, Decimal] = field(default_factory=dict)
    clip_bounds: tuple[float, float] | None = None  # raw horizon-return bounds of the fit
    forecast_source: str | None = None  # FORECAST_PRECOMPUTED / FORECAST_ON_REQUEST; None if historical only


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


def label_clip_bounds(train_labels: pd.Series) -> tuple[float, float]:
    """[CLIP_LOWER_Q, CLIP_UPPER_Q] quantiles of the training labels only."""
    lower, upper = np.quantile(train_labels.to_numpy(dtype=float), [CLIP_LOWER_Q, CLIP_UPPER_Q])
    return float(lower), float(upper)


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(round(float(value), DRIVER_DECIMALS)))


def ablation_drivers(
    model, latest_features: pd.DataFrame, train_medians: pd.Series, horizon: int = DEFAULT_HORIZON
) -> tuple[list[list[Driver]], float]:
    """Per row of latest_features: one Driver per feature (sorted by
    |contribution| desc) and the annualized "typical" prediction with every
    feature at its training median. `model` only needs predict()."""
    columns = list(latest_features.columns)
    base = np.asarray(model.predict(latest_features), dtype=float)

    typical_row = pd.DataFrame([train_medians[columns].to_numpy(dtype=float)], columns=columns)
    typical = horizon_forecast_to_annual(float(model.predict(typical_row)[0]), horizon)

    contributions = np.empty((len(latest_features), len(columns)))
    for j, column in enumerate(columns):
        ablated = latest_features.copy()
        ablated[column] = float(train_medians[column])
        contributions[:, j] = base - np.asarray(model.predict(ablated), dtype=float)
    contributions = contributions * ANNUALIZATION_FACTOR / horizon

    values = latest_features.to_numpy(dtype=float)
    drivers = []
    for i in range(len(latest_features)):
        row = [
            Driver(feature=column, value=_to_decimal(values[i, j]), contribution=_to_decimal(contributions[i, j]))
            for j, column in enumerate(columns)
        ]
        row.sort(key=lambda d: abs(d.contribution), reverse=True)
        drivers.append(row)
    return drivers, typical


class HistoricalMeanProvider(ExpectedReturnProvider):
    name = HISTORICAL
    history_calendar_days = HISTORICAL_HISTORY_DAYS

    def estimate(self, prices: dict[str, list[PricePoint]]) -> ReturnEstimates:
        return ReturnEstimates(
            expected_returns={t: annualized_historical_mean(points) for t, points in prices.items()},
            sources={t: HISTORICAL for t in prices},
        )


@dataclass
class TickerForecast:
    ticker: str
    raw_forecast: float  # horizon return from the model, before clipping
    annual_forecast: Decimal  # clipped, then annualized
    clipped: bool
    drivers: list[Driver]
    typical_estimate: Decimal | None


@dataclass
class PanelForecast:
    """One model fit on a price panel and its forecasts for the latest feature date."""

    as_of: date
    horizon: int
    model_version: str
    forecasts: dict[str, TickerForecast]  # finite forecasts only
    clip_bounds: tuple[float, float]
    training_start: date
    training_end: date
    training_rows: int


def fit_and_forecast(
    prices: dict[str, list[PricePoint]], model_name: str = ML_MODEL, horizon: int = DEFAULT_HORIZON
) -> PanelForecast | None:
    """Train on every labelled, finite panel row and forecast each ticker's
    latest feature row (clipped, annualized, with ablation drivers).
    None when there are fewer than MIN_TRAINING_ROWS training rows. Used by
    MLForecastProvider on request and by the nightly job on the full universe."""
    tickers = list(prices)
    panel = build_panel_from_prices(tickers, prices, errors={}, horizon=horizon).panel
    finite_features = np.isfinite(panel[FEATURE_COLUMNS].to_numpy(dtype=float)).all(axis=1)
    panel = panel[finite_features]

    train = panel[panel[LABEL_COLUMN].notna() & np.isfinite(panel[LABEL_COLUMN].to_numpy(dtype=float))]
    if len(train) < MIN_TRAINING_ROWS:
        return None

    forecast_as_of = panel["date"].max()
    latest = panel[panel["date"] == forecast_as_of]
    model = make_model(model_name).fit(train[FEATURE_COLUMNS], train[LABEL_COLUMN])
    latest_features = latest[FEATURE_COLUMNS].reset_index(drop=True)
    predictions = model.predict(latest_features)
    lower, upper = label_clip_bounds(train[LABEL_COLUMN])
    drivers_by_row, typical = ablation_drivers(model, latest_features, train[FEATURE_COLUMNS].median(), horizon)

    forecasts: dict[str, TickerForecast] = {}
    for i, (ticker, forecast) in enumerate(zip(latest["ticker"], predictions)):
        if math.isfinite(forecast):
            bounded = min(max(float(forecast), lower), upper)
            forecasts[ticker] = TickerForecast(
                ticker=ticker,
                raw_forecast=float(forecast),
                annual_forecast=Decimal(str(horizon_forecast_to_annual(bounded, horizon))),
                clipped=bounded != float(forecast),
                drivers=drivers_by_row[i],
                typical_estimate=_to_decimal(typical),
            )

    return PanelForecast(
        as_of=pd.Timestamp(forecast_as_of).date(),
        horizon=horizon,
        model_version=ML_MODEL_VERSION,
        forecasts=forecasts,
        clip_bounds=(lower, upper),
        training_start=pd.Timestamp(train["date"].min()).date(),
        training_end=pd.Timestamp(train["date"].max()).date(),
        training_rows=len(train),
    )


class MLForecastProvider(ExpectedReturnProvider):
    """`stored`: precomputed forecasts (nightly run) for the latest completed
    trading day and the current model version, keyed by ticker. Requested
    tickers found there are used without training; if every requested ticker
    is covered, no model is fitted. The rest go through fit_and_forecast on
    the requested prices, then fall back to historical as before."""

    name = ML
    history_calendar_days = ML_HISTORY_DAYS

    def __init__(
        self,
        model_name: str = ML_MODEL,
        horizon: int = DEFAULT_HORIZON,
        stored: dict[str, TickerForecast] | None = None,
        stored_as_of: date | None = None,
    ):
        self.model_name = model_name
        self.horizon = horizon
        self.stored = stored or {}
        self.stored_as_of = stored_as_of

    def estimate(self, prices: dict[str, list[PricePoint]]) -> ReturnEstimates:
        historical = HistoricalMeanProvider().estimate(prices)
        precomputed = {t: f for t, f in self.stored.items() if t in prices}

        fitted: PanelForecast | None = None
        if len(precomputed) < len(prices):
            fitted = fit_and_forecast(prices, self.model_name, self.horizon)
        on_request = {
            t: f for t, f in (fitted.forecasts.items() if fitted else ()) if t not in precomputed
        }

        chosen = {**on_request, **precomputed}
        if not chosen:
            return historical

        expected = dict(historical.expected_returns)
        sources = dict(historical.sources)
        for ticker, forecast in chosen.items():
            expected[ticker] = forecast.annual_forecast
            sources[ticker] = ML

        return ReturnEstimates(
            expected_returns=expected,
            sources=sources,
            model_version=ML_MODEL_VERSION,
            forecast_as_of=fitted.as_of if on_request else self.stored_as_of,
            clipped={t: f.clipped for t, f in chosen.items()},
            drivers={t: f.drivers for t, f in chosen.items()},
            typical_estimates={t: f.typical_estimate for t, f in chosen.items() if f.typical_estimate is not None},
            clip_bounds=fitted.clip_bounds if fitted else None,
            forecast_source=FORECAST_ON_REQUEST if on_request else FORECAST_PRECOMPUTED,
        )
