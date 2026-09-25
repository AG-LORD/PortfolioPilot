from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest
from price_fakes import make_series

from app.ml.baseline import historical_mean_forecast
from app.ml.models import make_model
from app.services.features import FEATURE_COLUMNS, LABEL_COLUMN, build_panel_from_prices
from app.services.return_providers import (
    HISTORICAL,
    MIN_PRICE_ROWS,
    ML,
    ML_MODEL,
    ML_MODEL_VERSION,
    HistoricalMeanProvider,
    MLForecastProvider,
    annualized_historical_mean,
    horizon_forecast_to_annual,
)

END = date(2025, 12, 31)
TICKERS = [f"ZZTEST_{c}" for c in "ABCDEF"]


def _prices(n_days=700, end=END, tickers=TICKERS):
    return {t: make_series(i, n_days=n_days, end=end, weekdays_only=True) for i, t in enumerate(tickers)}


# --- historical provider ---------------------------------------------------------


def test_historical_mean_is_252_times_mean_of_last_252_returns():
    points = make_series(1, n_days=400, end=END)
    closes = np.array([float(p.close) for p in points])
    returns = closes[1:] / closes[:-1] - 1
    expected = 252 * returns[-252:].mean()
    assert float(annualized_historical_mean(points)) == pytest.approx(expected, rel=1e-12)


def test_historical_provider_matches_the_evaluation_baseline_in_annual_units():
    points = make_series(2, n_days=400, end=END)
    close = pd.Series([float(p.close) for p in points])
    baseline_20d = historical_mean_forecast(close, horizon=20).iloc[-1]
    estimate = HistoricalMeanProvider().estimate({"ZZTEST_A": points})
    assert float(estimate.expected_returns["ZZTEST_A"]) == pytest.approx(horizon_forecast_to_annual(baseline_20d), rel=1e-12)
    assert estimate.sources == {"ZZTEST_A": HISTORICAL}
    assert (estimate.model_version, estimate.forecast_as_of) == (None, None)


def test_historical_mean_requires_min_price_rows():
    assert MIN_PRICE_ROWS == 253
    annualized_historical_mean(make_series(1, n_days=MIN_PRICE_ROWS, end=END))
    with pytest.raises(ValueError):
        annualized_historical_mean(make_series(1, n_days=MIN_PRICE_ROWS - 1, end=END))


def test_horizon_forecast_annualization_units():
    assert horizon_forecast_to_annual(0.02) == pytest.approx(0.252)
    assert horizon_forecast_to_annual(0.02, horizon=10) == pytest.approx(0.504)
    assert horizon_forecast_to_annual(-0.01) == pytest.approx(-0.126)


# --- ML provider -------------------------------------------------------------------


def test_ml_provider_matches_a_manual_train_and_predict():
    prices = _prices()
    estimate = MLForecastProvider().estimate(prices)

    panel = build_panel_from_prices(TICKERS, prices, errors={}).panel
    train = panel[panel[LABEL_COLUMN].notna()]
    latest = panel[panel["date"] == panel["date"].max()]
    predictions = make_model(ML_MODEL).fit(train[FEATURE_COLUMNS], train[LABEL_COLUMN]).predict(latest[FEATURE_COLUMNS])

    for ticker, forecast in zip(latest["ticker"], predictions):
        assert float(estimate.expected_returns[ticker]) == pytest.approx(forecast * 252 / 20, rel=1e-12)
    assert estimate.sources == {t: ML for t in TICKERS}
    assert estimate.forecast_as_of == max(p.date for p in prices["ZZTEST_A"])


def test_ml_provider_trains_only_on_rows_whose_label_is_known():
    prices = _prices()
    panel = build_panel_from_prices(TICKERS, prices, errors={}).panel
    labelled_dates = sorted(panel.loc[panel[LABEL_COLUMN].notna(), "date"].unique())
    all_dates = sorted(panel["date"].unique())
    # The last 20 trading days have no label and so are never training rows.
    assert labelled_dates == all_dates[:-20]


def test_ml_provider_metadata_is_deterministic():
    prices = _prices()
    first, second = MLForecastProvider().estimate(prices), MLForecastProvider().estimate(prices)
    assert first == second
    assert first.model_version == ML_MODEL_VERSION == "hist_gradient_boosting-h20-f12-v1"


def test_ml_provider_falls_back_per_ticker_without_a_latest_feature_row():
    prices = _prices()
    prices["ZZTEST_STALE"] = make_series(9, n_days=700, end=END - timedelta(days=14), weekdays_only=True)

    estimate = MLForecastProvider().estimate(prices)
    historical = HistoricalMeanProvider().estimate(prices)

    assert estimate.sources["ZZTEST_STALE"] == HISTORICAL
    assert estimate.expected_returns["ZZTEST_STALE"] == historical.expected_returns["ZZTEST_STALE"]
    assert all(estimate.sources[t] == ML for t in TICKERS)
    assert estimate.model_version == ML_MODEL_VERSION


def test_ml_provider_without_enough_training_rows_is_all_historical():
    prices = _prices(n_days=380)  # ~271 rows: no labelled feature rows
    estimate = MLForecastProvider().estimate(prices)
    assert estimate == HistoricalMeanProvider().estimate(prices)
    assert (estimate.model_version, estimate.forecast_as_of) == (None, None)


def test_ml_provider_returns_decimals():
    estimate = MLForecastProvider().estimate(_prices())
    assert all(isinstance(v, Decimal) for v in estimate.expected_returns.values())
