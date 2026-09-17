from datetime import date, datetime
from datetime import time as time_of_day
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from app.models import PortfolioSnapshot
from app.services.risk_analytics import (
    ANNUALIZATION_FACTOR,
    DEFAULT_VAR_CONFIDENCE,
    MIN_VAR_RETURN_OBSERVATIONS,
    SnapshotPoint,
    calculate_cumulative_return,
    calculate_daily_returns,
    calculate_historical_cvar,
    calculate_historical_var,
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
    # 3 usable returns is enough for volatility/Sharpe (>=2) but not for
    # VaR/CVaR (needs 20) — the message should now explain that gap rather
    # than being None, since VaR/CVaR are None here.
    assert result.historical_var is None
    assert result.historical_cvar is None
    assert result.message is not None
    assert "VaR" in result.message


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


# --- Historical VaR and CVaR -----------------------------------------------


def test_var_returns_none_with_fewer_than_20_observations():
    assert calculate_historical_var([]) is None
    assert calculate_historical_var([Decimal("0.01")]) is None
    returns_19 = [Decimal("0.01")] * 19
    assert calculate_historical_var(returns_19) is None


def test_cvar_returns_none_with_fewer_than_20_observations():
    assert calculate_historical_cvar([]) is None
    assert calculate_historical_cvar([Decimal("0.01")]) is None
    returns_19 = [Decimal("0.01")] * 19
    assert calculate_historical_cvar(returns_19) is None


def test_var_uses_loss_distribution_correctly():
    # 20 returns: -0.01, -0.02, ..., -0.20
    # Losses = -return: 0.01, 0.02, ..., 0.20
    # Sorted losses: 0.01, 0.02, ..., 0.20
    # Percentile position at 95%: 0.95 * 19 = 18.05
    # losses[18] = 0.19, losses[19] = 0.20
    # VaR = 0.19 + 0.05 * (0.20 - 0.19) = 0.1905
    returns = [Decimal("-0.01") * i for i in range(1, 21)]
    var = calculate_historical_var(returns, Decimal("0.95"))
    assert var == Decimal("0.1905")


def test_cvar_greater_than_or_equal_to_var_for_loss_tail():
    # For returns = -1% to -20%:
    # VaR(0.95) = 0.1905.
    # Losses >= 0.1905: [0.20]
    # CVaR = 0.20 >= 0.1905
    returns = [Decimal("-0.01") * i for i in range(1, 21)]
    var_95 = calculate_historical_var(returns, Decimal("0.95"))
    cvar_95 = calculate_historical_cvar(returns, Decimal("0.95"))
    assert var_95 is not None and cvar_95 is not None
    assert cvar_95 >= var_95
    assert cvar_95 == Decimal("0.20")

    # For confidence 0.80:
    # position = 0.80 * 19 = 15.2
    # VaR = losses[15] + 0.2 * (losses[16] - losses[15]) = 0.16 + 0.002 = 0.162
    # Losses >= 0.162: [0.17, 0.18, 0.19, 0.20]
    # CVaR = (0.17 + 0.18 + 0.19 + 0.20) / 4 = 0.185
    var_80 = calculate_historical_var(returns, Decimal("0.80"))
    cvar_80 = calculate_historical_cvar(returns, Decimal("0.80"))
    assert var_80 == Decimal("0.162")
    assert cvar_80 == Decimal("0.185")
    assert cvar_80 >= var_80


def test_different_confidence_levels_produce_non_decreasing_var():
    returns = [Decimal("-0.01") * i for i in range(1, 21)]
    var_90 = calculate_historical_var(returns, Decimal("0.90"))
    var_95 = calculate_historical_var(returns, Decimal("0.95"))
    var_99 = calculate_historical_var(returns, Decimal("0.99"))
    assert var_90 is not None and var_95 is not None and var_99 is not None
    assert var_90 < var_95 < var_99


def test_invalid_confidence_values_rejected():
    returns = [Decimal("0.01")] * 20
    for invalid in [Decimal("0"), Decimal("1"), Decimal("-0.1"), Decimal("1.5")]:
        with pytest.raises(ValueError):
            calculate_historical_var(returns, invalid)
        with pytest.raises(ValueError):
            calculate_historical_cvar(returns, invalid)
        with pytest.raises(ValueError):
            calculate_risk_analytics([], Decimal("100000"), var_confidence=invalid)


def test_risk_analytics_orchestration_var_none_for_insufficient_observations():
    points = [SnapshotPoint(date=date(2026, 1, i), total_value=Decimal("100") + Decimal(i)) for i in range(1, 16)]
    result = calculate_risk_analytics(points, Decimal("100"))
    assert result.observation_count == 14
    assert result.annualized_volatility is not None
    assert result.historical_var is None
    assert result.historical_cvar is None
    assert result.var_confidence == DEFAULT_VAR_CONFIDENCE


def test_risk_analytics_orchestration_exposes_var_cvar_with_enough_observations():
    # 21 snapshots yield 20 returns
    points = [SnapshotPoint(date=date(2026, 1, 1), total_value=Decimal("1000"))]
    for i in range(2, 22):
        points.append(SnapshotPoint(date=date(2026, 1, i), total_value=points[-1].total_value - Decimal("10")))
    result = calculate_risk_analytics(points, Decimal("1000"), var_confidence=Decimal("0.95"))
    assert result.observation_count == 20
    assert result.historical_var is not None
    assert result.historical_cvar is not None
    assert result.historical_cvar >= result.historical_var
    assert result.var_confidence == Decimal("0.95")


def test_risk_analytics_zero_snapshots_has_none_var_cvar():
    result = calculate_risk_analytics([], Decimal("100000"), var_confidence=Decimal("0.90"))
    assert result.observation_count == 0
    assert result.historical_var is None
    assert result.historical_cvar is None
    assert result.var_confidence == Decimal("0.90")
    assert result.message == "No snapshot history exists for this portfolio yet."


def test_get_portfolio_risk_analytics_passes_through_var_confidence(db_session, test_portfolio):
    user_id, portfolio = test_portfolio
    result = get_portfolio_risk_analytics(
        db_session,
        user_id,
        portfolio.id,
        var_confidence=Decimal("0.99"),
    )
    assert result.var_confidence == Decimal("0.99")
    assert result.historical_var is None
    assert result.historical_cvar is None


def test_get_portfolio_risk_analytics_propagates_confidence_through_real_history(
    db_session, test_portfolio
):
    # Insert 21 real snapshots -> 20 usable returns, meeting
    # MIN_VAR_RETURN_OBSERVATIONS, through the actual DB-backed orchestration
    # path (not the pure function directly), to prove var_confidence reaches
    # the calculation end-to-end, not just that the response echoes it.
    user_id, portfolio = test_portfolio
    ist = ZoneInfo("Asia/Kolkata")

    value = Decimal("1000")
    for i in range(21):
        snapshot_date = datetime.combine(date(2026, 2, 1 + i), time_of_day.min, tzinfo=ist)
        db_session.add(
            PortfolioSnapshot(
                portfolio_id=portfolio.id,
                snapshot_date=snapshot_date,
                total_value=value,
                cash_balance=value,
                invested_value=Decimal("0"),
                daily_return=None,
                cumulative_return=None,
            )
        )
        value += Decimal("5") if i % 2 == 0 else Decimal("-8")
    db_session.commit()

    result_90 = get_portfolio_risk_analytics(
        db_session, user_id, portfolio.id, var_confidence=Decimal("0.90")
    )
    result_95 = get_portfolio_risk_analytics(
        db_session, user_id, portfolio.id, var_confidence=Decimal("0.95")
    )

    assert result_90.observation_count == 20
    assert result_90.var_confidence == Decimal("0.90")
    assert result_95.var_confidence == Decimal("0.95")
    assert result_90.historical_var is not None
    assert result_95.historical_var is not None
    # Different confidence levels over a non-constant loss distribution must
    # produce different VaR values — this is what actually proves
    # var_confidence reaches calculate_historical_var, not just that it's
    # echoed back unchanged in the response.
    assert result_90.historical_var != result_95.historical_var


def test_read_portfolio_risk_route_with_custom_confidence(db_session, test_portfolio):
    from app.api.portfolios import read_portfolio_risk
    user_id, portfolio = test_portfolio
    response = read_portfolio_risk(
        portfolio_id=portfolio.id,
        var_confidence=Decimal("0.90"),
        user_id=user_id,
        db=db_session,
    )
    assert response.var_confidence == Decimal("0.90")
    assert response.historical_var is None
    assert response.historical_cvar is None


def test_read_portfolio_risk_route_rejects_invalid_confidence(db_session, test_portfolio):
    from app.api.portfolios import read_portfolio_risk
    user_id, portfolio = test_portfolio
    for invalid in [Decimal("0"), Decimal("1"), Decimal("-0.5"), Decimal("1.2")]:
        with pytest.raises(HTTPException) as exc_info:
            read_portfolio_risk(
                portfolio_id=portfolio.id,
                var_confidence=invalid,
                user_id=user_id,
                db=db_session,
            )
        assert exc_info.value.status_code == 422


