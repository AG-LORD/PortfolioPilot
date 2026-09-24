import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from price_fakes import make_series

from app.ml.baseline import BASELINE_COLUMN, BASELINE_LOOKBACK
from app.services.features import (
    DEFAULT_HORIZON,
    FEATURE_COLUMNS,
    LABEL_COLUMN,
    MIN_HISTORY_ROWS,
    WARMUP_ROWS,
    atr,
    build_feature_panel,
    compute_features,
    forward_return,
    macd,
    realized_volatility,
    rsi,
)


def _frame(close, high=None, low=None):
    close = np.asarray(close, dtype=float)
    index = pd.Index(pd.bdate_range("2025-01-01", periods=len(close)).date, name="date")
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01 if high is None else np.asarray(high, dtype=float),
            "low": close * 0.99 if low is None else np.asarray(low, dtype=float),
            "close": close,
            "volume": 1000,
        },
        index=index,
    )


def _random_prices(n=300, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0.0005, 0.02, n))
    open_ = close * (1 + rng.normal(0, 0.005, n))
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.02, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.02, n))
    frame = _frame(close, high, low)
    frame["open"] = open_
    return frame


# --- known values ---------------------------------------------------------------


def test_sma_ratios_and_momentum_known_values():
    close = np.arange(1, 101)  # close_i = i + 1
    row = compute_features(_frame(close)).iloc[70 - WARMUP_ROWS]  # close = 71
    sma20, sma50 = 71 - 9.5, 71 - 24.5
    assert row["close_to_sma_20"] == pytest.approx(71 / sma20 - 1, rel=1e-12)
    assert row["close_to_sma_50"] == pytest.approx(71 / sma50 - 1, rel=1e-12)
    assert row["sma_20_to_sma_50"] == pytest.approx(sma20 / sma50 - 1, rel=1e-12)
    assert row["momentum_5"] == pytest.approx(71 / 66 - 1, rel=1e-12)
    assert row["momentum_20"] == pytest.approx(71 / 51 - 1, rel=1e-12)
    assert row["momentum_60"] == pytest.approx(71 / 11 - 1, rel=1e-12)


def test_rsi_wilder_known_values():
    # deltas: +1, -1, +2, +1. Seed (window 3): gain 1, loss 1/3 -> RSI 75.
    # Next: gain (1*2+1)/3 = 1, loss (1/3*2+0)/3 = 2/9 -> RSI 100*1/(1+2/9).
    result = rsi(pd.Series([10.0, 11, 10, 12, 13]), window=3)
    assert result.iloc[:3].isna().all()
    assert result.iloc[3] == pytest.approx(75.0)
    assert result.iloc[4] == pytest.approx(100 / (1 + 2 / 9))


def test_rsi_edge_cases():
    assert (rsi(pd.Series(np.arange(1.0, 30)), window=3).dropna() == 100).all()
    assert (rsi(pd.Series([5.0] * 10), window=3).dropna() == 50).all()


def _ema_reference(values, span):
    alpha = 2 / (span + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(out[-1] + alpha * (v - out[-1]))
    return np.array(out)


def test_macd_known_values():
    close = np.array([1.0, 2, 3, 2, 5])
    line = _ema_reference(close, 2) - _ema_reference(close, 3)
    signal = _ema_reference(line, 2)
    got_line, got_signal, got_hist = macd(pd.Series(close), fast=2, slow=3, signal=2)
    np.testing.assert_allclose(got_line, line / close, rtol=1e-12)
    np.testing.assert_allclose(got_signal, signal / close, rtol=1e-12)
    np.testing.assert_allclose(got_hist, (line - signal) / close, rtol=1e-12)
    # By hand for row 1: fast EMA 1 + 2/3 = 5/3, slow EMA 1.5 -> line 1/6, over close 2.
    assert got_line.iloc[1] == pytest.approx(1 / 12)


def test_macd_is_zero_for_constant_prices():
    for series in macd(pd.Series([50.0] * 40)):
        assert (series == 0).all()


def test_atr_wilder_known_values():
    high = pd.Series([11.0, 12, 13, 12, 15])
    low = pd.Series([9.0, 10, 11, 9, 11])
    close = pd.Series([10.0, 11, 12, 10, 14])
    # True ranges from row 1: 2, 2, 3, 5. Seed = 7/3; next = (7/3*2 + 5)/3 = 29/9.
    result = atr(high, low, close, window=3)
    assert result.iloc[:3].isna().all()
    assert result.iloc[3] == pytest.approx((7 / 3) / 10)
    assert result.iloc[4] == pytest.approx((29 / 9) / 14)


def test_realized_volatility_known_value():
    returns = [0.01 if i % 2 == 0 else -0.01 for i in range(20)]
    close = pd.Series(100 * np.cumprod([1.0, *[1 + r for r in returns]]))
    result = realized_volatility(close, window=20)
    expected = math.sqrt(20 * 0.01**2 / 19) * math.sqrt(252)
    assert result.iloc[20] == pytest.approx(expected, rel=1e-9)
    assert result.iloc[:20].isna().all()


def test_forward_return_label_and_nan_tail():
    close = pd.Series(np.arange(1.0, 51))
    label = forward_return(close, horizon=DEFAULT_HORIZON)
    assert label.iloc[0] == pytest.approx(21 / 1 - 1)
    assert label.iloc[29] == pytest.approx(50 / 30 - 1)
    assert label.iloc[-DEFAULT_HORIZON:].isna().all()
    assert label.iloc[:-DEFAULT_HORIZON].notna().all()


# --- structure: warm-up and NaN ----------------------------------------------------


def test_warm_up_rows_dropped_and_no_nan_after():
    prices = _random_prices(200)
    features = compute_features(prices)
    assert list(features.columns) == FEATURE_COLUMNS
    assert len(features) == 200 - WARMUP_ROWS
    assert features.index[0] == prices.index[WARMUP_ROWS]
    assert not features.isna().any().any()


def test_too_short_series_gives_no_rows():
    assert compute_features(_random_prices(WARMUP_ROWS)).empty
    assert len(compute_features(_random_prices(MIN_HISTORY_ROWS))) == 1


# --- point-in-time: truncation invariance ------------------------------------------


@pytest.mark.parametrize("feature", FEATURE_COLUMNS)
@pytest.mark.parametrize("cutoff", [WARMUP_ROWS + 1, 150, 250])
def test_truncation_invariance(feature, cutoff):
    prices = _random_prices(300)
    full = compute_features(prices)[feature]
    truncated = compute_features(prices.iloc[:cutoff])[feature]
    pd.testing.assert_series_equal(full.loc[truncated.index], truncated, check_exact=True)


@pytest.mark.parametrize("feature", FEATURE_COLUMNS)
def test_future_prices_do_not_change_past_features(feature):
    prices = _random_prices(300)
    shocked = prices.copy()
    shocked.iloc[200:, :4] *= 3.0  # a large move after the cutoff
    pd.testing.assert_series_equal(
        compute_features(prices)[feature].iloc[: 200 - WARMUP_ROWS],
        compute_features(shocked)[feature].iloc[: 200 - WARMUP_ROWS],
        check_exact=True,
    )


# --- scale invariance ------------------------------------------------------------


@pytest.mark.parametrize("feature", FEATURE_COLUMNS)
def test_scale_invariance(feature):
    prices = _random_prices(300)
    base = compute_features(prices)[feature]

    exact = prices.copy()
    exact[["open", "high", "low", "close"]] *= 4.0  # power of two: bit-exact in floats
    pd.testing.assert_series_equal(compute_features(exact)[feature], base, check_exact=True)

    scaled = prices.copy()
    scaled[["open", "high", "low", "close"]] *= 3.7
    np.testing.assert_allclose(compute_features(scaled)[feature], base, rtol=1e-10, atol=1e-14)


# --- panel (DB) ----------------------------------------------------------------------


@pytest.mark.db
def test_build_feature_panel_excludes_short_history_and_aligns_label(db_session, fake_market):
    n = 300
    fake_market.series = {
        "ZZTEST_LONG": make_series(1, n_days=n),
        "ZZTEST_SHORT": make_series(2, n_days=40),
    }
    start, end = date.today() - timedelta(days=400), date.today()

    result = build_feature_panel(db_session, ["ZZTEST_LONG", "ZZTEST_SHORT", "ZZTEST_MISSING"], start, end)

    reasons = {e.ticker: e.reason for e in result.excluded}
    assert reasons == {
        "ZZTEST_SHORT": f"only 40 trading day(s) of history; at least {MIN_HISTORY_ROWS} are needed",
        "ZZTEST_MISSING": "no historical data returned",
    }
    panel = result.panel
    assert list(panel.columns) == ["date", "ticker", *FEATURE_COLUMNS, LABEL_COLUMN, BASELINE_COLUMN]
    assert set(panel["ticker"]) == {"ZZTEST_LONG"}
    assert len(panel) == n - WARMUP_ROWS
    assert panel[LABEL_COLUMN].isna().sum() == DEFAULT_HORIZON
    assert panel[BASELINE_COLUMN].notna().sum() == n - BASELINE_LOOKBACK
    assert not panel[FEATURE_COLUMNS].isna().any().any()
