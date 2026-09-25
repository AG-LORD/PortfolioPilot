"""Target-allocation optimization. Pure math only below the orchestration line.

Recommendation only: nothing here writes to Holding/Transaction/
Portfolio.cash_balance. Weights are converted to float for scipy/numpy
(required by the solver) and back to Decimal at the boundary.

Cash is an explicit (n+1)th decision variable (zero expected return,
zero variance, zero covariance with every asset) rather than requiring
100% equity investment — otherwise a tight max_position_weight with few
holdings (e.g. 3 holdings capped at 10% each) would be falsely infeasible.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import numpy as np
from scipy.optimize import minimize
from sqlalchemy.orm import Session

from app.models import RiskProfile
from app.services.expected_returns import ExpectedReturnsInput, get_expected_returns_and_covariance
from app.services.portfolios import get_portfolio, list_holdings


class OptimizationError(Exception):
    pass


class InfeasibleAllocationError(OptimizationError):
    pass


@dataclass
class TargetWeight:
    ticker: str
    target_weight: Decimal
    expected_return: Decimal


@dataclass
class TargetAllocationResult:
    allocations: list[TargetWeight]
    cash_weight: Decimal

    def __iter__(self):
        return iter(self.allocations)


def optimize_target_weights(
    tickers: list[str],
    expected_returns: list[Decimal],
    covariance: list[list[Decimal]],
    max_position_weight: Decimal,
    target_volatility: Decimal,
    max_sector_weight: Decimal | None = None,
    sector_map: dict[str, str] | None = None,
) -> TargetAllocationResult:
    n = len(tickers)
    if n == 0:
        raise OptimizationError("No tickers to optimize.")
    if target_volatility < 0:
        raise InfeasibleAllocationError("target_volatility cannot be negative.")
    if max_position_weight <= 0:
        raise InfeasibleAllocationError("max_position_weight must be strictly positive.")

    mu = np.array([float(r) for r in expected_returns])
    sigma = np.array([[float(v) for v in row] for row in covariance])
    max_pos = float(max_position_weight)
    target_vol = float(target_volatility)

    # Variables: n asset weights followed by 1 cash weight.
    bounds = [(0.0, max_pos) for _ in range(n)] + [(0.0, 1.0)]

    constraints = [
        {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        {"type": "ineq", "fun": lambda w: target_vol - np.sqrt(max(w[:n] @ sigma @ w[:n], 0.0))},
    ]

    # Sector constraint only applied where sector data is actually
    # available — no sector data source exists yet in this codebase, so
    # sector_map is None by default and this is skipped, not invented.
    if sector_map and max_sector_weight is not None:
        max_sector = float(max_sector_weight)
        sectors = sorted({sector_map[t] for t in tickers if t in sector_map})
        for sector in sectors:
            idx = [i for i, t in enumerate(tickers) if sector_map.get(t) == sector]

            def sector_constraint(w, idx=idx):
                return max_sector - sum(w[i] for i in idx)

            constraints.append({"type": "ineq", "fun": sector_constraint})

    init_asset_weight = min(max_pos, 1.0 / (n + 1))
    init_cash = max(1.0 - n * init_asset_weight, 0.0)
    x0 = np.array([init_asset_weight] * n + [init_cash])

    result = minimize(
        lambda w: -np.dot(w[:n], mu),
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 200, "ftol": 1e-9},
    )

    weights = result.x
    asset_weights = weights[:n]
    cash_val = weights[n]
    tol = 1e-4
    portfolio_vol = np.sqrt(max(asset_weights @ sigma @ asset_weights, 0.0))
    feasible = (
        result.success
        and abs(np.sum(weights) - 1.0) < tol
        and np.all(asset_weights >= -tol)
        and cash_val >= -tol
        and np.all(asset_weights <= max_pos + tol)
        and portfolio_vol <= target_vol + tol
    )
    if not feasible:
        raise InfeasibleAllocationError(
            "No feasible target allocation satisfies the risk-profile constraints "
            "(max position weight, max sector weight, target volatility)."
        )

    return _finalize_weights(tickers, asset_weights, mu)


def _finalize_weights(tickers: list[str], asset_weights, mu) -> TargetAllocationResult:
    allocations = [
        TargetWeight(
            ticker=ticker,
            target_weight=Decimal(str(round(max(weight, 0.0), 6))),
            expected_return=Decimal(str(round(mu[i], 6))),
        )
        for i, (ticker, weight) in enumerate(zip(tickers, asset_weights))
    ]
    # Rounding each weight to 6 dp can push a fully invested total just above
    # 1; take the excess (at most a few 1e-6) off the largest weight so cash
    # is never negative.
    allocated = sum((w.target_weight for w in allocations), Decimal("0"))
    if allocated > 1:
        largest = max(allocations, key=lambda w: w.target_weight)
        largest.target_weight -= allocated - 1
        allocated = Decimal("1")
    # cash_weight is the exact complement of the rounded allocations, not an
    # independently-rounded solver output — guarantees allocations+cash==1.
    cash_weight = Decimal("1") - allocated

    return TargetAllocationResult(allocations=allocations, cash_weight=cash_weight)


def get_portfolio_target_allocation(
    db: Session, user_id: UUID, portfolio_id: UUID
) -> TargetAllocationResult:
    portfolio = get_portfolio(db, user_id, portfolio_id)
    holdings = list_holdings(db, user_id, portfolio_id)

    if not holdings:
        raise OptimizationError("Portfolio has no holdings to optimize.")

    risk_profile = db.get(RiskProfile, portfolio.risk_profile_id)
    if risk_profile is None:
        raise OptimizationError("Portfolio has no associated risk profile.")

    tickers = [h.ticker for h in holdings]
    inputs: ExpectedReturnsInput = get_expected_returns_and_covariance(db, tickers)

    return optimize_target_weights(
        tickers=inputs.tickers,
        expected_returns=inputs.expected_returns,
        covariance=inputs.covariance,
        max_position_weight=risk_profile.max_position_weight,
        target_volatility=risk_profile.target_volatility,
        max_sector_weight=risk_profile.max_sector_weight,
        sector_map=None,
    )
