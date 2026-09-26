import math
import statistics
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
from fastapi import HTTPException, status

from app.ml.evaluation import BASELINE_MODEL, run_walk_forward
from app.ml.models import HIST_GRADIENT_BOOSTING, MODEL_VERSIONS
from app.schemas.backtest import (
    BacktestEquityPointRead,
    BacktestRequest,
    BacktestResultRead,
    BacktestSettingsRead,
    BacktestStrategyRead,
)
from app.services import price_history
from app.services.expected_returns import InsufficientHistoryError, ledoit_wolf_covariance
from app.services.features import DEFAULT_HORIZON, FEATURE_SET_VERSION, build_panel_from_prices
from app.services.market_calendar import ANNUALIZATION_FACTOR
from app.services.market_data import MarketDataUnavailableError
from app.services.optimization import OptimizationError, optimize_target_weights
from app.services.universe import CUSTOM_UNIVERSE, Universe, get_universe, normalize_tickers

_ZERO = Decimal("0")
_DECIMAL_PLACES = Decimal("0.000001")
_PRICE_HISTORY_LEAD_DAYS = 7 * 365
_LABEL_TAIL_CALENDAR_DAYS = 45


class BacktestError(Exception):
    pass


def _decimal(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(_DECIMAL_PLACES)


def _frequency_key(value: date, frequency: str) -> tuple[int, ...]:
    if frequency == "daily":
        return (value.toordinal(),)
    if frequency == "weekly":
        year, week, _ = value.isocalendar()
        return year, week
    return value.year, value.month


def _weights_at_signal(
    predictions: pd.DataFrame,
    price_series: dict,
    signal_date: date,
    model_column: str,
    horizon: int,
    max_position_weight: Decimal,
    target_volatility: Decimal,
) -> tuple[dict[str, Decimal], Decimal]:
    forecast_frame = predictions[pd.to_datetime(predictions["date"]).dt.date == signal_date]
    if forecast_frame.empty:
        raise BacktestError(f"No out-of-sample forecast exists for {signal_date}")
    forecast_frame = forecast_frame.sort_values("ticker")
    tickers = forecast_frame["ticker"].tolist()
    expected_returns = [
        Decimal(str(float(value)))
        * Decimal(ANNUALIZATION_FACTOR)
        / Decimal(horizon)
        for value in forecast_frame[model_column]
    ]
    historical_prices = {
        ticker: [point for point in price_series[ticker] if point.date <= signal_date]
        for ticker in tickers
    }
    if any(not points or points[-1].date > signal_date for points in historical_prices.values()):
        raise BacktestError("Forecast covariance includes prices later than its signal date")
    covariance = ledoit_wolf_covariance(tickers, historical_prices)
    allocation = optimize_target_weights(
        tickers=tickers,
        expected_returns=expected_returns,
        covariance=covariance,
        max_position_weight=max_position_weight,
        target_volatility=target_volatility,
    )
    return (
        {item.ticker: item.target_weight for item in allocation.allocations},
        allocation.cash_weight,
    )


def _selected_signal_dates(predictions: pd.DataFrame, start: date, end: date, frequency: str) -> list[date]:
    dates = sorted(
        {
            pd.Timestamp(value).date()
            for value in predictions["date"].tolist()
            if start <= pd.Timestamp(value).date() <= end
        }
    )
    selected = []
    prior_bucket = None
    for signal_date in dates:
        bucket = _frequency_key(signal_date, frequency)
        if bucket != prior_bucket:
            selected.append(signal_date)
            prior_bucket = bucket
    return selected


def _simulate_strategy(
    predictions: pd.DataFrame,
    price_series: dict,
    *,
    start: date,
    end: date,
    frequency: str,
    model_column: str,
    model_version: str,
    starting_capital: Decimal,
    max_position_weight: Decimal,
    target_volatility: Decimal,
    horizon: int = DEFAULT_HORIZON,
) -> BacktestStrategyRead:
    common_dates = None
    for points in price_series.values():
        dates = {point.date for point in points}
        common_dates = dates if common_dates is None else common_dates & dates
    common_dates = sorted(day for day in (common_dates or set()) if start <= day <= end)
    if len(common_dates) < 2:
        raise BacktestError("At least two common price dates are required in the requested period")

    all_dates = sorted(
        set.intersection(*({point.date for point in points} for points in price_series.values()))
    )
    next_session = {left: right for left, right in zip(all_dates, all_dates[1:])}
    target_by_execution_date: dict[date, tuple[dict[str, Decimal], Decimal]] = {}
    skipped_rebalances = 0
    for signal_date in _selected_signal_dates(predictions, start, end, frequency):
        execution_date = next_session.get(signal_date)
        if execution_date is None or execution_date > end:
            continue
        try:
            target_by_execution_date[execution_date] = _weights_at_signal(
                predictions,
                price_series,
                signal_date,
                model_column,
                horizon,
                max_position_weight,
                target_volatility,
            )
        except (BacktestError, InsufficientHistoryError, OptimizationError):
            skipped_rebalances += 1

    if not target_by_execution_date:
        raise BacktestError("No feasible out-of-sample rebalance was available for this period")

    close_by_ticker = {
        ticker: {point.date: point.close for point in points}
        for ticker, points in price_series.items()
    }
    holdings: dict[str, Decimal] = {}
    cash = starting_capital
    prior_value = starting_capital
    values: list[Decimal] = []
    returns: list[Decimal] = []
    turnover = _ZERO
    rebalance_count = 0

    for day_index, current_date in enumerate(common_dates):
        total_value = cash + sum(
            (quantity * close_by_ticker[ticker][current_date] for ticker, quantity in holdings.items()),
            _ZERO,
        )
        if day_index:
            returns.append(total_value / prior_value - Decimal("1"))
        values.append(total_value)

        target = target_by_execution_date.get(current_date)
        if target is not None and total_value > _ZERO:
            target_weights, target_cash_weight = target
            current_weights = {
                ticker: quantity * close_by_ticker[ticker][current_date] / total_value
                for ticker, quantity in holdings.items()
            }
            current_weights["CASH"] = cash / total_value
            union = set(current_weights) | set(target_weights) | {"CASH"}
            desired_weights = {ticker: target_weights.get(ticker, _ZERO) for ticker in union}
            desired_weights["CASH"] = target_cash_weight
            turnover += sum(
                (abs(desired_weights.get(ticker, _ZERO) - current_weights.get(ticker, _ZERO)) for ticker in union),
                _ZERO,
            ) / Decimal("2")
            holdings = {
                ticker: total_value * weight / close_by_ticker[ticker][current_date]
                for ticker, weight in target_weights.items()
                if weight > _ZERO and close_by_ticker[ticker][current_date] > _ZERO
            }
            cash = total_value * target_cash_weight
            rebalance_count += 1
        prior_value = total_value

    initial_value, final_value = values[0], values[-1]
    cumulative_return = final_value / initial_value - Decimal("1")
    annualized_return = (
        _decimal((float(final_value / initial_value)) ** (ANNUALIZATION_FACTOR / len(returns)) - 1)
        if returns and final_value > _ZERO
        else None
    )
    daily_float_returns = [float(value) for value in returns]
    annualized_volatility = (
        _decimal(statistics.stdev(daily_float_returns) * math.sqrt(ANNUALIZATION_FACTOR))
        if len(daily_float_returns) > 1
        else None
    )
    daily_std = statistics.stdev(daily_float_returns) if len(daily_float_returns) > 1 else 0
    sharpe_ratio = (
        _decimal((statistics.mean(daily_float_returns) / daily_std) * math.sqrt(ANNUALIZATION_FACTOR))
        if daily_std > 0
        else None
    )
    peak = values[0]
    maximum_drawdown = _ZERO
    for value in values:
        peak = max(peak, value)
        if peak > _ZERO:
            maximum_drawdown = min(maximum_drawdown, value / peak - Decimal("1"))

    return BacktestStrategyRead(
        model=model_column,
        model_version=model_version,
        cumulative_return=_decimal(cumulative_return),
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        max_drawdown=_decimal(maximum_drawdown),
        sharpe_ratio=sharpe_ratio,
        turnover=_decimal(turnover),
        rebalance_count=rebalance_count,
        daily_observation_count=len(returns),
        equity_curve=[
            BacktestEquityPointRead(date=day, total_value=_decimal(value))
            for day, value in zip(common_dates, values)
        ],
    )


def run_portfolio_backtest(db, request: BacktestRequest) -> BacktestResultRead:
    if request.universe is not None:
        universe = get_universe(request.universe)
    else:
        universe = Universe(CUSTOM_UNIVERSE, None, normalize_tickers(request.tickers or []))

    history_start = request.start - timedelta(days=_PRICE_HISTORY_LEAD_DAYS)
    history_end = request.end + timedelta(days=_LABEL_TAIL_CALENDAR_DAYS + 1)
    history = price_history.get_price_history(db, universe.tickers, history_start, history_end)
    price_series = {ticker: points for ticker, points in history.points.items() if points}
    price_errors = {ticker: error.reason for ticker, error in history.errors.items()}
    panel_result = build_panel_from_prices(
        list(price_series),
        price_series,
        price_errors,
        horizon=DEFAULT_HORIZON,
    )
    if panel_result.panel.empty:
        raise BacktestError("No tickers have sufficient adjusted price history for this period")
    used_tickers = sorted(panel_result.panel["ticker"].unique().tolist())
    price_series = {ticker: price_series[ticker] for ticker in used_tickers}
    walk_forward = run_walk_forward(panel_result.panel)
    model_specs = [
        (BASELINE_MODEL, MODEL_VERSIONS[BASELINE_MODEL]),
        (HIST_GRADIENT_BOOSTING, MODEL_VERSIONS[HIST_GRADIENT_BOOSTING]),
    ]
    strategies = [
        _simulate_strategy(
            walk_forward.predictions,
            price_series,
            start=request.start,
            end=request.end,
            frequency=request.rebalance_frequency,
            model_column=model,
            model_version=model_version,
            starting_capital=request.starting_capital,
            max_position_weight=request.max_position_weight,
            target_volatility=request.target_volatility,
        )
        for model, model_version in model_specs
    ]
    selected_model = (
        BASELINE_MODEL if request.return_model == "historical" else HIST_GRADIENT_BOOSTING
    )
    effective_dates = [point.date for point in strategies[0].equity_curve]
    return BacktestResultRead(
        settings=BacktestSettingsRead(
            start=request.start,
            end=request.end,
            rebalance_frequency=request.rebalance_frequency,
            starting_capital=request.starting_capital,
            return_model=request.return_model,
            max_position_weight=request.max_position_weight,
            target_volatility=request.target_volatility,
            universe=universe.name,
            universe_as_of=universe.as_of,
            universe_revision=universe.revision,
            price_source="adjusted price cache (yfinance auto_adjust=True)",
        ),
        selected_strategy=selected_model,
        feature_version=FEATURE_SET_VERSION,
        evaluation_version="purged-walk-forward-v1",
        daily_risk_free_rate_assumption=_ZERO,
        fee_assumption="No transaction fee schedule is configured; fees are excluded.",
        execution_assumption="Fractional shares at the next common-session adjusted close; forecasts use only data available through the prior signal close.",
        scored_rows=len(walk_forward.predictions),
        effective_start=min(effective_dates),
        effective_end=max(effective_dates),
        excluded=[{"ticker": item.ticker, "reason": item.reason} for item in panel_result.excluded],
        strategies=strategies,
    )