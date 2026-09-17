from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.risk_analytics import (
    ANNUALIZATION_FACTOR,
    SnapshotPoint,
    calculate_cumulative_return,
    calculate_daily_returns,
    calculate_max_drawdown,
    calculate_risk_analytics,
    calculate_sharpe_ratio,
    calculate_volatility,
    get_portfolio_risk_analytics,
)


def pts(*values: tuple[str, str]) -> list[SnapshotPoint]:
    return [SnapshotPoint(date=date(2026, 1, d), total_value=Decimal(v)) for d, v in values]


# --- daily returns -----------------------------------------------------


def test_simple_daily_returns():
    points = pts((1, "100"), (2, "110"), (3, "99"))
    returns = calculate_daily_returns(points)
    assert returns == [Decimal("0.1"), Decimal("-0.1")]


def test_mixed_positive_negative_returns():
    points = pts((1, "100"), (2, "105"), (3, "95"), (4, "100"))
    returns = calculate_daily_returns(points)
    assert returns[0] > 0
    assert returns[1] < 0
    assert returns[2] > 0


def test_returns_exclude_zero_previous_value():
    points = pts((1, "100"), (2, "0"), (3, "50"))
    returns = calculate_daily_returns(points)
    # (100 -> 0) is included (prev=100, valid); (0 -> 50) is excluded (prev=0).
    assert returns == [Decimal("-1")]


# --- volatility ----------------------------------------------------------


def test_volatility_normal_series():
    returns = [Decimal("0.01"), Decimal("-0.02"), Decimal("0.015")]
    vol = calculate_volatility(returns)
    assert vol is not None
    assert vol > 0


def test_volatility_uses_sample_stdev_ddof1():
    returns = [Decimal("0.01"), Decimal("0.03")]
    vol = calculate_volatility(returns)
    # sample stdev of [0.01, 0.03] with ddof=1 is 0.01414213562...
    expected = Decimal("0.01414213562373095048801688724") * Decimal(ANNUALIZATION_FACTOR).sqrt()
    assert abs(vol - expected) < Decimal("0.0000001")


def test_volatility_zero_for_identical_returns():
    returns = [Decimal("0.01"), Decimal("0.01"), Decimal("0.01")]
    assert calculate_volatility(returns) == Decimal("0")


def test_volatility_none_for_insufficient_observations():
    assert calculate_volatility([]) is None
    assert calculate_volatility([Decimal("0.01")]) is None


def test_volatility_annualization_factor_applied():
    returns = [Decimal("0.01"), Decimal("0.03")]
    vol = calculate_volatility(returns)
    daily_std_only = Decimal("0.01414213562373095048801688724")
    assert vol == daily_std_only * Decimal(ANNUALIZATION_FACTOR).sqrt()


# --- cumulative return -----------------------------------------------------


def test_cumulative_return_normal():
    points = pts((1, "100"), (2, "120"))
    result = calculate_cumulative_return(points, Decimal("100"))
    assert result == Decimal("0.2")


def test_cumulative_return_none_for_zero_initial_capital():
    points = pts((1, "100"))
    assert calculate_cumulative_return(points, Decimal("0")) is None


def test_cumulative_return_none_for_empty_points():
    assert calculate_cumulative_return([], Decimal("100")) is None


# --- max drawdown -----------------------------------------------------


def test_max_drawdown_known_fixture():
    points = pts((1, "100"), (2, "120"), (3, "90"), (4, "110"))
    dd = calculate_max_drawdown(points)
    assert dd == Decimal("-0.25")  # (90 - 120) / 120


def test_max_drawdown_monotonic_increase_is_zero():
    points = pts((1, "100"), (2, "110"), (3, "120"))
    assert calculate_max_drawdown(points) == Decimal("0")


def test_max_drawdown_single_point_is_zero():
    points = pts((1, "100"))
    assert calculate_max_drawdown(points) == Decimal("0")


def test_max_drawdown_none_for_empty_points():
    assert calculate_max_drawdown([]) is None


# --- sharpe ratio -----------------------------------------------------


def test_sharpe_with_zero_risk_free_rate():
    returns = [Decimal("0.01"), Decimal("0.02"), Decimal("-0.005")]
    sharpe = calculate_sharpe_ratio(returns, Decimal("0"))
    assert sharpe is not None


def test_sharpe_with_explicit_nonzero_risk_free_rate():
    returns = [Decimal("0.01"), Decimal("0.02"), Decimal("-0.005")]
    sharpe_zero_rf = calculate_sharpe_ratio(returns, Decimal("0"))
    sharpe_with_rf = calculate_sharpe_ratio(returns, Decimal("0.065"))
    assert sharpe_with_rf != sharpe_zero_rf


def test_sharpe_none_for_zero_volatility():
    returns = [Decimal("0.01"), Decimal("0.01"), Decimal("0.01")]
    assert calculate_sharpe_ratio(returns, Decimal("0")) is None


def test_sharpe_none_for_insufficient_observations():
    assert calculate_sharpe_ratio([Decimal("0.01")], Decimal("0")) is None
    assert calculate_sharpe_ratio([], Decimal("0")) is None


# --- orchestrating pure function: calculate_risk_analytics -----------------


def test_risk_analytics_zero_snapshots():
    result = calculate_risk_analytics([], Decimal("100000"))
    assert result.observation_count == 0
    assert result.cumulative_return is None
    assert result.max_drawdown is None
    assert result.annualized_volatility is None
    assert result.sharpe_ratio is None
    assert result.message is not None


def test_risk_analytics_one_snapshot():
    points = pts((1, "110"))
    result = calculate_risk_analytics(points, Decimal("100"))
    assert result.cumulative_return == Decimal("0.1")
    assert result.max_drawdown == Decimal("0")
    assert result.annualized_volatility is None
    assert result.sharpe_ratio is None


def test_risk_analytics_two_snapshots():
    points = pts((1, "100"), (2, "110"))
    result = calculate_risk_analytics(points, Decimal("100"))
    assert result.observation_count == 1
    assert result.cumulative_return == Decimal("0.1")
    assert result.max_drawdown == Decimal("0")
    assert result.annualized_volatility is None
    assert result.sharpe_ratio is None


def test_risk_analytics_three_plus_snapshots_enables_volatility_and_sharpe():
    points = pts((1, "100"), (2, "105"), (3, "95"), (4, "102"))
    result = calculate_risk_analytics(points, Decimal("100"))
    assert result.observation_count == 3
    assert result.annualized_volatility is not None
    assert result.sharpe_ratio is not None
    assert result.message is None


def test_risk_analytics_irregular_snapshot_dates_still_produces_result():
    # Gaps of several days between snapshots; treated as single observations
    # (documented approximation), not rejected or specially weighted.
    points = [
        SnapshotPoint(date=date(2026, 1, 1), total_value=Decimal("100")),
        SnapshotPoint(date=date(2026, 1, 10), total_value=Decimal("105")),
        SnapshotPoint(date=date(2026, 1, 25), total_value=Decimal("95")),
    ]
    result = calculate_risk_analytics(points, Decimal("100"))
    assert result.observation_count == 2
    assert result.first_snapshot_date == date(2026, 1, 1)
    assert result.last_snapshot_date == date(2026, 1, 25)


def test_risk_analytics_excludes_zero_previous_value_from_observation_count():
    points = pts((1, "100"), (2, "0"), (3, "50"), (4, "60"))
    result = calculate_risk_analytics(points, Decimal("100"))
    # returns: (100->0) valid, (0->50) excluded, (50->60) valid => 2 usable
    assert result.observation_count == 2


# --- ownership (integration, reuses test_portfolio fixture from conftest) --


def test_risk_analytics_unauthorized_access_raises_404(db_session, test_portfolio):
    _, portfolio = test_portfolio
    with pytest.raises(HTTPException) as exc_info:
        get_portfolio_risk_analytics(db_session, uuid4(), portfolio.id)
    assert exc_info.value.status_code == 404
