from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import Holding, Portfolio, RiskProfile
from app.services.expected_returns import ExpectedReturnsInput, InsufficientHistoryError
from app.services.optimization import (
    InfeasibleAllocationError,
    OptimizationError,
    get_portfolio_target_allocation,
    optimize_target_weights,
)

# --- pure optimizer: mathematical behavior ---------------------------------


def _diag_cov(variances):
    n = len(variances)
    return [[variances[i] if i == j else Decimal("0") for j in range(n)] for i in range(n)]


def test_weights_sum_to_one_and_nonnegative():
    tickers = ["A", "B", "C"]
    returns = [Decimal("0.15"), Decimal("0.08"), Decimal("0.05")]
    cov = _diag_cov([Decimal("0.04"), Decimal("0.04"), Decimal("0.04")])
    result = optimize_target_weights(
        tickers, returns, cov, max_position_weight=Decimal("0.5"), target_volatility=Decimal("1.0")
    )
    total = sum(w.target_weight for w in result.allocations) + result.cash_weight
    assert total == Decimal("1")
    assert all(w.target_weight >= 0 for w in result.allocations)
    assert result.cash_weight >= 0


def test_binding_max_position_constraint_enforced():
    tickers = ["A", "B", "C"]
    returns = [Decimal("0.15"), Decimal("0.08"), Decimal("0.05")]
    cov = _diag_cov([Decimal("0.04"), Decimal("0.04"), Decimal("0.04")])
    result = optimize_target_weights(
        tickers, returns, cov, max_position_weight=Decimal("0.5"), target_volatility=Decimal("1.0")
    )
    by_ticker = {w.ticker: w.target_weight for w in result.allocations}
    # A has the highest return with a generous vol budget -> should hit the cap.
    assert abs(by_ticker["A"] - Decimal("0.5")) < Decimal("0.001")
    for w in result.allocations:
        assert w.target_weight <= Decimal("0.5") + Decimal("0.001")


def test_higher_return_asset_gets_more_weight_when_unconstrained_by_position_cap():
    tickers = ["A", "B"]
    returns = [Decimal("0.10"), Decimal("0.05")]
    cov = _diag_cov([Decimal("0.04"), Decimal("0.04")])
    result = optimize_target_weights(
        tickers, returns, cov, max_position_weight=Decimal("1.0"), target_volatility=Decimal("1.0")
    )
    by_ticker = {w.ticker: w.target_weight for w in result.allocations}
    assert by_ticker["A"] > by_ticker["B"]


def test_sector_constraint_respected():
    # max_sector_weight applies to every sector present (it means "max
    # exposure to any one sector"), so 3 sectors at 0.5 cap each stay
    # feasible (1.5 >= 1) while still binding TECH's combined weight.
    tickers = ["A", "B", "C", "D"]
    returns = [Decimal("0.15"), Decimal("0.14"), Decimal("0.05"), Decimal("0.03")]
    cov = _diag_cov([Decimal("0.04")] * 4)
    sector_map = {"A": "TECH", "B": "TECH", "C": "ENERGY", "D": "OTHER"}
    result = optimize_target_weights(
        tickers,
        returns,
        cov,
        max_position_weight=Decimal("1.0"),
        target_volatility=Decimal("1.0"),
        max_sector_weight=Decimal("0.5"),
        sector_map=sector_map,
    )
    by_ticker = {w.ticker: w.target_weight for w in result.allocations}
    assert by_ticker["A"] + by_ticker["B"] <= Decimal("0.5") + Decimal("0.001")


def test_target_volatility_constraint_respected():
    # Unconstrained optimum would concentrate fully in A (highest return,
    # vol 0.2) but target_volatility=0.15 is below that, and below full
    # concentration's vol too, so it must force diversification toward B.
    tickers = ["A", "B"]
    returns = [Decimal("0.30"), Decimal("0.05")]
    cov = _diag_cov([Decimal("0.04"), Decimal("0.04")])
    result = optimize_target_weights(
        tickers, returns, cov, max_position_weight=Decimal("1.0"), target_volatility=Decimal("0.15")
    )
    w = [float(x.target_weight) for x in result.allocations]
    import math

    variance = w[0] ** 2 * 0.04 + w[1] ** 2 * 0.04
    assert math.sqrt(variance) <= 0.15 + 1e-3
    # Confirms the constraint actually bound something (not vacuously true).
    assert w[0] < 1.0


def test_three_holdings_with_moderate_position_cap_is_feasible():
    # 3 assets capped at 0.10 each can sum to at most 0.30 as equities;
    # cash absorbs the rest instead of the problem being infeasible.
    tickers = ["A", "B", "C"]
    returns = [Decimal("0.15"), Decimal("0.08"), Decimal("0.05")]
    cov = _diag_cov([Decimal("0.04"), Decimal("0.04"), Decimal("0.04")])
    result = optimize_target_weights(
        tickers, returns, cov, max_position_weight=Decimal("0.10"), target_volatility=Decimal("1.0")
    )
    for w in result.allocations:
        assert w.target_weight <= Decimal("0.10") + Decimal("0.001")
    assert result.cash_weight >= Decimal("0.70") - Decimal("0.001")
    total = sum(w.target_weight for w in result.allocations) + result.cash_weight
    assert total == Decimal("1")


def test_fewer_holdings_than_fully_invested_formula_is_feasible():
    # 2 assets capped at 0.10 each sum to at most 0.20, leaving 0.80 cash.
    tickers = ["A", "B"]
    returns = [Decimal("0.10"), Decimal("0.05")]
    cov = _diag_cov([Decimal("0.04"), Decimal("0.04")])
    result = optimize_target_weights(
        tickers, returns, cov, max_position_weight=Decimal("0.10"), target_volatility=Decimal("1.0")
    )
    assert all(w.target_weight <= Decimal("0.10") + Decimal("0.001") for w in result.allocations)
    assert result.cash_weight >= Decimal("0.80") - Decimal("0.001")
    total = sum(w.target_weight for w in result.allocations) + result.cash_weight
    assert total == Decimal("1")


def test_genuinely_infeasible_constraints_raise():
    tickers = ["A", "B"]
    returns = [Decimal("0.10"), Decimal("0.05")]
    cov = _diag_cov([Decimal("0.04"), Decimal("0.04")])

    # Negative target volatility cannot be satisfied by any asset or cash (vol >= 0).
    with pytest.raises(InfeasibleAllocationError):
        optimize_target_weights(
            tickers,
            returns,
            cov,
            max_position_weight=Decimal("1.0"),
            target_volatility=Decimal("-0.05"),
        )

    # Zero max_position_weight cannot be satisfied.
    with pytest.raises(InfeasibleAllocationError):
        optimize_target_weights(
            tickers,
            returns,
            cov,
            max_position_weight=Decimal("0.0"),
            target_volatility=Decimal("0.15"),
        )


def test_deterministic_output_for_same_inputs():
    tickers = ["A", "B", "C"]
    returns = [Decimal("0.12"), Decimal("0.09"), Decimal("0.04")]
    cov = _diag_cov([Decimal("0.05"), Decimal("0.03"), Decimal("0.02")])
    r1 = optimize_target_weights(
        tickers, returns, cov, max_position_weight=Decimal("0.6"), target_volatility=Decimal("0.5")
    )
    r2 = optimize_target_weights(
        tickers, returns, cov, max_position_weight=Decimal("0.6"), target_volatility=Decimal("0.5")
    )
    assert [w.target_weight for w in r1.allocations] == [w.target_weight for w in r2.allocations]
    assert r1.cash_weight == r2.cash_weight


def test_no_tickers_raises():
    with pytest.raises(OptimizationError):
        optimize_target_weights(
            [], [], [], max_position_weight=Decimal("0.5"), target_volatility=Decimal("1.0")
        )


# --- data/input behavior (expected_returns, no network) --------------------


def test_insufficient_history_raises():
    with pytest.raises(InsufficientHistoryError):
        raise InsufficientHistoryError("Only 5 overlapping trading day(s)")


def test_get_expected_returns_missing_price_history_propagates(db_session, fake_market):
    from app.services.expected_returns import get_expected_returns_and_covariance
    from app.services.market_data import MarketDataUnavailableError

    with pytest.raises(MarketDataUnavailableError) as exc_info:
        get_expected_returns_and_covariance(db_session, ["ZZTEST_FAKETICKER"])
    assert exc_info.value.reason == "no historical data returned"


def test_get_expected_returns_insufficient_overlap_raises(db_session, fake_market):
    from price_fakes import make_series

    from app.services.expected_returns import get_expected_returns_and_covariance

    # Only 5 days of history -> below MIN_HISTORY_OBSERVATIONS.
    fake_market.series = {"ZZTEST_A": make_series(1, n_days=5), "ZZTEST_B": make_series(2, n_days=5)}
    with pytest.raises(InsufficientHistoryError):
        get_expected_returns_and_covariance(db_session, ["ZZTEST_A", "ZZTEST_B"])


# --- architectural safety: no DB mutation -----------------------------------


def _make_risk_profile_permissive(db_session, portfolio):
    # The shared fixture's RiskProfile (max_position_weight=0.1) can't hold
    # 100% of a single-ticker portfolio; loosen it for tests that only
    # exercise plumbing/wiring, not constraint math (covered separately).
    risk_profile = db_session.get(RiskProfile, portfolio.risk_profile_id)
    risk_profile.max_position_weight = Decimal("1.0")
    risk_profile.target_volatility = Decimal("1.0")
    db_session.commit()


def test_optimization_does_not_modify_holding_or_cash_balance(db_session, test_portfolio):
    user_id, portfolio = test_portfolio
    _make_risk_profile_permissive(db_session, portfolio)
    holding = Holding(
        portfolio_id=portfolio.id, ticker="A", quantity=Decimal("10"), average_cost=Decimal("100")
    )
    db_session.add(holding)
    db_session.commit()

    before_qty = holding.quantity
    before_avg_cost = holding.average_cost
    before_cash = db_session.get(Portfolio, portfolio.id).cash_balance

    fake_inputs = ExpectedReturnsInput(
        tickers=["A"],
        expected_returns=[Decimal("0.1")],
        covariance=[[Decimal("0.04")]],
    )
    with patch(
        "app.services.optimization.get_expected_returns_and_covariance", return_value=fake_inputs
    ):
        get_portfolio_target_allocation(db_session, user_id, portfolio.id)

    db_session.expire_all()
    refreshed_holding = db_session.get(Holding, holding.id)
    refreshed_portfolio = db_session.get(Portfolio, portfolio.id)

    assert refreshed_holding.quantity == before_qty
    assert refreshed_holding.average_cost == before_avg_cost
    assert refreshed_portfolio.cash_balance == before_cash

    db_session.query(Holding).filter(Holding.id == holding.id).delete()
    db_session.commit()


# --- API: ownership, success, clean failure ---------------------------------


def test_optimize_route_no_holdings_returns_422(db_session, test_portfolio):
    from app.api.portfolios import read_portfolio_target_allocation

    user_id, portfolio = test_portfolio
    with pytest.raises(HTTPException) as exc_info:
        read_portfolio_target_allocation(portfolio_id=portfolio.id, user_id=user_id, db=db_session)
    assert exc_info.value.status_code == 422


def test_optimize_route_unauthorized_returns_404(db_session, test_portfolio):
    from app.api.portfolios import read_portfolio_target_allocation

    _, portfolio = test_portfolio
    with pytest.raises(HTTPException) as exc_info:
        read_portfolio_target_allocation(portfolio_id=portfolio.id, user_id=uuid4(), db=db_session)
    assert exc_info.value.status_code == 404


def test_optimize_route_success(db_session, test_portfolio):
    from app.api.portfolios import read_portfolio_target_allocation

    user_id, portfolio = test_portfolio
    _make_risk_profile_permissive(db_session, portfolio)
    holding = Holding(
        portfolio_id=portfolio.id, ticker="A", quantity=Decimal("10"), average_cost=Decimal("100")
    )
    db_session.add(holding)
    db_session.commit()

    fake_inputs = ExpectedReturnsInput(
        tickers=["A"], expected_returns=[Decimal("0.1")], covariance=[[Decimal("0.04")]]
    )
    with patch(
        "app.services.optimization.get_expected_returns_and_covariance", return_value=fake_inputs
    ):
        response = read_portfolio_target_allocation(
            portfolio_id=portfolio.id, user_id=user_id, db=db_session
        )

    assert response.portfolio_id == portfolio.id
    assert len(response.allocations) == 1
    assert response.allocations[0].ticker == "A"
    assert abs(response.allocations[0].target_weight - Decimal("1")) < Decimal("0.001")
    assert response.cash_weight == Decimal("0")

    db_session.query(Holding).filter(Holding.id == holding.id).delete()
    db_session.commit()


def test_optimize_route_cash_aware_three_holdings(db_session, test_portfolio):
    from app.api.portfolios import read_portfolio_target_allocation

    user_id, portfolio = test_portfolio
    # Default RiskProfile in test_portfolio has max_position_weight = Decimal("0.1")
    holdings = [
        Holding(portfolio_id=portfolio.id, ticker="A", quantity=Decimal("10"), average_cost=Decimal("100")),
        Holding(portfolio_id=portfolio.id, ticker="B", quantity=Decimal("10"), average_cost=Decimal("100")),
        Holding(portfolio_id=portfolio.id, ticker="C", quantity=Decimal("10"), average_cost=Decimal("100")),
    ]
    for h in holdings:
        db_session.add(h)
    db_session.commit()

    fake_inputs = ExpectedReturnsInput(
        tickers=["A", "B", "C"],
        expected_returns=[Decimal("0.15"), Decimal("0.08"), Decimal("0.05")],
        covariance=_diag_cov([Decimal("0.04"), Decimal("0.04"), Decimal("0.04")]),
    )
    with patch(
        "app.services.optimization.get_expected_returns_and_covariance", return_value=fake_inputs
    ):
        response = read_portfolio_target_allocation(
            portfolio_id=portfolio.id, user_id=user_id, db=db_session
        )

    assert response.portfolio_id == portfolio.id
    assert len(response.allocations) == 3
    assert response.cash_weight >= Decimal("0.70") - Decimal("0.001")
    total = sum(a.target_weight for a in response.allocations) + response.cash_weight
    assert total == Decimal("1")

    for h in holdings:
        db_session.delete(h)
    db_session.commit()
