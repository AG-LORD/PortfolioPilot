"""Target-allocation optimization. Pure math only below the orchestration line.

Recommendation only: nothing here writes to Holding/Transaction/
Portfolio.cash_balance. Weights are converted to float for scipy/numpy
(required by the solver) and back to Decimal at the boundary.

Cash is an explicit (n+1)th decision variable (zero expected return,
zero variance, zero covariance with every asset) rather than requiring
100% equity investment — otherwise a tight max_position_weight with few
holdings (e.g. 3 holdings capped at 10% each) would be falsely infeasible.
All cash is always feasible, so a solution always exists for valid limits.

Objective (docs/ML_METHODOLOGY.md, "Optimizer"):
- "mean_variance" (default): maximize mu_s'w - (lambda/2) w'Sigma w, where
  lambda is the profile's risk aversion (RISK_AVERSION) and mu_s the shrunk
  estimates (shrink_expected_returns).
- "max_return": maximize mu_s'w (the previous behaviour, kept for comparison).
Both are subject to: weights + cash = 1, 0 <= w_i <= max_position_weight,
portfolio volatility <= target_volatility, cash >= 0 and, when a sector map
is given, the weight of every sector <= max_sector_weight. A ticker whose
UNshrunk estimate is <= 0 is never bought (upper bound 0): shrinkage pulls
estimates toward the mean and must not turn "expected to fall" into a buy.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal
from uuid import UUID

import numpy as np
from scipy.optimize import minimize
from sqlalchemy.orm import Session

from app.models import RiskProfile
from app.services.expected_returns import ExpectedReturnsInput, get_expected_returns_and_covariance
from app.services.portfolios import get_portfolio, list_holdings
from app.services.sectors import get_sector

Objective = Literal["mean_variance", "max_return"]
MEAN_VARIANCE: Objective = "mean_variance"
MAX_RETURN: Objective = "max_return"

# Risk aversion (lambda) per risk-profile category: a higher value trades
# more expected return away for lower variance.
RISK_AVERSION: dict[str, float] = {"conservative": 8.0, "moderate": 4.0, "aggressive": 2.0}
DEFAULT_RISK_AVERSION = RISK_AVERSION["moderate"]

# Weight on each ticker's own estimate; the rest goes to the cross-sectional
# mean. Damps noisy forecasts without changing their ranking.
SHRINKAGE_ALPHA = 0.5

# Solver tolerance for feasibility checks and for calling a limit binding.
FEASIBILITY_TOLERANCE = 1e-4
BINDING_TOLERANCE = 1e-4


class OptimizationError(Exception):
    pass


class InfeasibleAllocationError(OptimizationError):
    pass


@dataclass
class TargetWeight:
    ticker: str
    target_weight: Decimal
    expected_return: Decimal  # the model's estimate, before shrinkage
    expected_return_used: Decimal | None = None  # after shrinkage: what the optimizer used
    sector_group: str | None = None  # the sector the constraint grouped it in; None without a sector map


@dataclass
class TargetAllocationResult:
    allocations: list[TargetWeight]
    cash_weight: Decimal
    # Sector groups whose max_sector_weight cap is binding in the solution.
    binding_sectors: set[str] = field(default_factory=set)
    objective: Objective = MEAN_VARIANCE
    risk_aversion: float | None = None

    def __iter__(self):
        return iter(self.allocations)


def risk_aversion_for(category: str | None) -> float:
    return RISK_AVERSION.get((category or "").lower(), DEFAULT_RISK_AVERSION)


def shrink_expected_returns(mu: np.ndarray, alpha: float = SHRINKAGE_ALPHA) -> np.ndarray:
    """mu_s = alpha * mu + (1 - alpha) * mean(mu). A positive alpha keeps the ranking."""
    if mu.size == 0:
        return mu
    return alpha * mu + (1.0 - alpha) * float(np.mean(mu))


def sector_groups(tickers: list[str], sector_map: dict[str, str]) -> list[str]:
    """Constraint group per ticker; tickers without a sector form their own group."""
    return [sector_map.get(t) or f"{t} (no sector)" for t in tickers]


def sector_map_for(tickers: list[str]) -> dict[str, str]:
    """Sectors from app/data/sectors.json for the tickers that have one."""
    return {t: s for t in tickers if (s := get_sector(t))}


def optimize_target_weights(
    tickers: list[str],
    expected_returns: list[Decimal],
    covariance: list[list[Decimal]],
    max_position_weight: Decimal,
    target_volatility: Decimal,
    max_sector_weight: Decimal | None = None,
    sector_map: dict[str, str] | None = None,
    *,
    objective: Objective = MEAN_VARIANCE,
    risk_aversion: float = DEFAULT_RISK_AVERSION,
    shrinkage_alpha: float = SHRINKAGE_ALPHA,
) -> TargetAllocationResult:
    n = len(tickers)
    if n == 0:
        raise OptimizationError("No tickers to optimize.")
    if target_volatility < 0:
        raise InfeasibleAllocationError("target_volatility cannot be negative.")
    if max_position_weight <= 0:
        raise InfeasibleAllocationError("max_position_weight must be strictly positive.")
    if objective not in (MEAN_VARIANCE, MAX_RETURN):
        raise OptimizationError(f"Unknown objective: {objective}")

    mu_raw = np.array([float(r) for r in expected_returns])
    mu = shrink_expected_returns(mu_raw, shrinkage_alpha)
    sigma = np.array([[float(v) for v in row] for row in covariance])
    max_pos = float(max_position_weight)
    target_vol = float(target_volatility)
    lam = float(risk_aversion)

    # Variables: n asset weights followed by 1 cash weight. Never buy a stock
    # the model expects to fall, whatever shrinkage did to its estimate.
    bounds = [(0.0, max_pos if mu_raw[i] > 0 else 0.0) for i in range(n)] + [(0.0, 1.0)]

    # Volatility as a variance constraint: smooth at w = 0, unlike the square root.
    constraints = [
        {"type": "eq", "fun": lambda w: np.sum(w) - 1.0, "jac": lambda w: np.ones(n + 1)},
        {
            "type": "ineq",
            "fun": lambda w: target_vol**2 - w[:n] @ sigma @ w[:n],
            "jac": lambda w: np.concatenate([-2.0 * (sigma @ w[:n]), [0.0]]),
        },
    ]

    groups = sector_groups(tickers, sector_map) if sector_map is not None else None
    group_members: dict[str, list[int]] = {}
    if groups is not None and max_sector_weight is not None:
        max_sector = float(max_sector_weight)
        for i, group in enumerate(groups):
            group_members.setdefault(group, []).append(i)
        for idx in group_members.values():
            row = np.zeros(n + 1)
            row[idx] = 1.0
            constraints.append(
                {"type": "ineq", "fun": lambda w, row=row: max_sector - row @ w, "jac": lambda w, row=row: -row}
            )

    def negative_utility(w):
        assets = w[:n]
        value = mu @ assets
        if objective == MEAN_VARIANCE:
            value -= 0.5 * lam * (assets @ sigma @ assets)
        return -value

    def negative_utility_grad(w):
        grad = mu.copy()
        if objective == MEAN_VARIANCE:
            grad = grad - lam * (sigma @ w[:n])
        return np.concatenate([-grad, [0.0]])

    init_asset_weight = min(max_pos, 1.0 / (n + 1))
    x0 = np.array([init_asset_weight if upper > 0 else 0.0 for _, upper in bounds[:n]] + [0.0])
    x0[n] = 1.0 - x0[:n].sum()

    result = minimize(
        negative_utility,
        x0,
        jac=negative_utility_grad,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 500, "ftol": 1e-12},
    )

    weights = result.x
    asset_weights = np.clip(weights[:n], 0.0, None)
    cash_val = weights[n]
    tol = FEASIBILITY_TOLERANCE
    portfolio_vol = np.sqrt(max(asset_weights @ sigma @ asset_weights, 0.0))
    sector_ok = all(
        asset_weights[idx].sum() <= float(max_sector_weight) + tol for idx in group_members.values()
    )
    feasible = (
        result.success
        and abs(np.sum(weights) - 1.0) < tol
        and np.all(weights[:n] >= -tol)
        and cash_val >= -tol
        and np.all(asset_weights <= max_pos + tol)
        and portfolio_vol <= target_vol + tol
        and sector_ok
    )
    if not feasible:
        raise InfeasibleAllocationError(
            "No feasible target allocation satisfies the risk-profile constraints "
            "(max position weight, max sector weight, target volatility)."
        )

    binding = {
        group
        for group, idx in group_members.items()
        if asset_weights[idx].sum() >= float(max_sector_weight) - BINDING_TOLERANCE
    }
    result_weights = _finalize_weights(tickers, asset_weights, mu_raw, mu_used=mu, groups=groups)
    result_weights.binding_sectors = binding
    result_weights.objective = objective
    result_weights.risk_aversion = lam if objective == MEAN_VARIANCE else None
    return result_weights


def _finalize_weights(tickers: list[str], asset_weights, mu, mu_used=None, groups=None) -> TargetAllocationResult:
    allocations = [
        TargetWeight(
            ticker=ticker,
            target_weight=Decimal(str(round(max(weight, 0.0), 6))),
            expected_return=Decimal(str(round(mu[i], 6))),
            expected_return_used=None if mu_used is None else Decimal(str(round(float(mu_used[i]), 6))),
            sector_group=None if groups is None else groups[i],
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
        sector_map=sector_map_for(inputs.tickers),
        risk_aversion=risk_aversion_for(risk_profile.category),
    )
