"""Target-allocation optimization. Pure math only below the orchestration line.

Recommendation only: nothing here writes to Holding/Transaction/
Portfolio.cash_balance. Weights are converted to float for scipy/numpy
(required by the solver) and back to Decimal at the boundary.
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


def optimize_target_weights(
    tickers: list[str],
    expected_returns: list[Decimal],
    covariance: list[list[Decimal]],
    max_position_weight: Decimal,
    target_volatility: Decimal,
    max_sector_weight: Decimal | None = None,
    sector_map: dict[str, str] | None = None,
) -> list[TargetWeight]:
    n = len(tickers)
    if n == 0:
        raise OptimizationError("No tickers to optimize.")

    mu = np.array([float(r) for r in expected_returns])
    sigma = np.array([[float(v) for v in row] for row in covariance])
    max_pos = float(max_position_weight)
    target_vol = float(target_volatility)

    bounds = [(0.0, max_pos) for _ in range(n)]

    constraints = [
        {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        {"type": "ineq", "fun": lambda w: target_vol - np.sqrt(w @ sigma @ w)},
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

    x0 = np.full(n, 1.0 / n)

    result = minimize(
        lambda w: -np.dot(w, mu),
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 200, "ftol": 1e-9},
    )

    weights = result.x
    tol = 1e-4
    feasible = (
        result.success
        and abs(np.sum(weights) - 1.0) < 1e-4
        and np.all(weights >= -tol)
        and np.all(weights <= max_pos + tol)
        and np.sqrt(max(weights @ sigma @ weights, 0.0)) <= target_vol + tol
    )
    if not feasible:
        raise InfeasibleAllocationError(
            "No feasible target allocation satisfies the risk-profile constraints "
            "(max position weight, max sector weight, target volatility)."
        )

    return [
        TargetWeight(
            ticker=ticker,
            target_weight=Decimal(str(round(max(weight, 0.0), 6))),
            expected_return=Decimal(str(round(mu[i], 6))),
        )
        for i, (ticker, weight) in enumerate(zip(tickers, weights))
    ]


def get_portfolio_target_allocation(
    db: Session, user_id: UUID, portfolio_id: UUID
) -> list[TargetWeight]:
    portfolio = get_portfolio(db, user_id, portfolio_id)
    holdings = list_holdings(db, user_id, portfolio_id)

    if not holdings:
        raise OptimizationError("Portfolio has no holdings to optimize.")

    risk_profile = db.get(RiskProfile, portfolio.risk_profile_id)
    if risk_profile is None:
        raise OptimizationError("Portfolio has no associated risk profile.")

    tickers = [h.ticker for h in holdings]
    inputs: ExpectedReturnsInput = get_expected_returns_and_covariance(tickers)

    return optimize_target_weights(
        tickers=inputs.tickers,
        expected_returns=inputs.expected_returns,
        covariance=inputs.covariance,
        max_position_weight=risk_profile.max_position_weight,
        target_volatility=risk_profile.target_volatility,
        max_sector_weight=risk_profile.max_sector_weight,
        sector_map=None,
    )
