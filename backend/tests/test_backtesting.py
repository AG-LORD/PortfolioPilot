from datetime import date, timedelta
from decimal import Decimal

import pandas as pd

from app.ml.baseline import BASELINE_COLUMN
from app.ml.models import HIST_GRADIENT_BOOSTING
from app.services import backtesting
from app.services.market_data import PricePoint
from app.services.optimization import TargetAllocationResult, TargetWeight
from app.services.features import LABEL_COLUMN


def _price_series(count=70):
    dates = pd.bdate_range("2024-01-02", periods=count)
    result = {"AAA": [], "BBB": []}
    for index, timestamp in enumerate(dates):
        day = timestamp.date()
        for ticker, start, slope in (("AAA", 100, 0.8), ("BBB", 80, -0.1)):
            close = Decimal(str(start + slope * index))
            result[ticker].append(
                PricePoint(
                    date=day,
                    open=close - Decimal("0.2"),
                    high=close + Decimal("1"),
                    low=close - Decimal("1"),
                    close=close,
                    volume=1000,
                )
            )
    return result


def _prediction_frame(price_series):
    rows = []
    for point in price_series["AAA"]:
        for ticker, historical, ml in (("AAA", 0.02, 0.03), ("BBB", 0.01, 0.015)):
            rows.append(
                {
                    "date": pd.Timestamp(point.date),
                    "ticker": ticker,
                    BASELINE_COLUMN: historical,
                    HIST_GRADIENT_BOOSTING: ml,
                    LABEL_COLUMN: 0.01,
                }
            )
    return pd.DataFrame(rows)


def _fixed_allocation(*_args, **_kwargs):
    return TargetAllocationResult(
        allocations=[
            TargetWeight("AAA", Decimal("0.6"), Decimal("0.1")),
            TargetWeight("BBB", Decimal("0.2"), Decimal("0.1")),
        ],
        cash_weight=Decimal("0.2"),
    )


def test_covariance_inputs_never_include_prices_after_signal(monkeypatch):
    prices = _price_series(50)
    signal_date = prices["AAA"][35].date
    observed = []

    def capture_covariance(tickers, history):
        observed.extend(point.date for series in history.values() for point in series)
        return [[Decimal("0.001"), Decimal("0")], [Decimal("0"), Decimal("0.001")]]

    monkeypatch.setattr(backtesting, "ledoit_wolf_covariance", capture_covariance)
    monkeypatch.setattr(backtesting, "optimize_target_weights", _fixed_allocation)
    predictions = _prediction_frame(prices)

    weights_before, cash_before = backtesting._weights_at_signal(
        predictions,
        prices,
        signal_date,
        HIST_GRADIENT_BOOSTING,
        20,
        Decimal("0.6"),
        Decimal("0.2"),
    )
    altered_future = {ticker: list(points) for ticker, points in prices.items()}
    for ticker in altered_future:
        point = altered_future[ticker][-1]
        altered_future[ticker][-1] = PricePoint(
            date=point.date,
            open=point.open * 100,
            high=point.high * 100,
            low=point.low * 100,
            close=point.close * 100,
            volume=point.volume,
        )

    weights_after, cash_after = backtesting._weights_at_signal(
        predictions,
        altered_future,
        signal_date,
        HIST_GRADIENT_BOOSTING,
        20,
        Decimal("0.6"),
        Decimal("0.2"),
    )

    assert observed and max(observed) <= signal_date
    assert weights_before == weights_after
    assert cash_before == cash_after


def test_backtest_reports_frequency_metrics_and_historical_equity_curve(monkeypatch):
    prices = _price_series()
    predictions = _prediction_frame(prices)
    monkeypatch.setattr(
        backtesting,
        "ledoit_wolf_covariance",
        lambda tickers, history: [[Decimal("0.001"), Decimal("0")], [Decimal("0"), Decimal("0.001")]],
    )
    monkeypatch.setattr(backtesting, "optimize_target_weights", _fixed_allocation)
    start = prices["AAA"][0].date
    end = prices["AAA"][-1].date

    monthly = backtesting._simulate_strategy(
        predictions,
        prices,
        start=start,
        end=end,
        frequency="monthly",
        model_column=BASELINE_COLUMN,
        model_version="historical-test-v1",
        starting_capital=Decimal("10000"),
        max_position_weight=Decimal("0.6"),
        target_volatility=Decimal("0.2"),
    )
    daily = backtesting._simulate_strategy(
        predictions,
        prices,
        start=start,
        end=end,
        frequency="daily",
        model_column=BASELINE_COLUMN,
        model_version="historical-test-v1",
        starting_capital=Decimal("10000"),
        max_position_weight=Decimal("0.6"),
        target_volatility=Decimal("0.2"),
    )

    assert monthly.rebalance_count < daily.rebalance_count
    assert monthly.daily_observation_count == len(prices["AAA"]) - 1
    assert monthly.cumulative_return > Decimal("0")
    assert monthly.annualized_volatility is not None
    assert monthly.max_drawdown <= Decimal("0")
    assert monthly.equity_curve[0].total_value == Decimal("10000.000000")
    assert monthly.equity_curve[-1].date == end