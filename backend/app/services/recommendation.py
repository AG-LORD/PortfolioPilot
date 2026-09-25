"""Capital-allocation recommendation over a candidate universe.

Recommendation only: nothing here writes to Holding/Transaction/Portfolio.
optimize_target_weights() is used unchanged; rupee amounts and
portfolio-level metrics are derived here, outside the optimizer.

Capital is cash_balance rounded DOWN to 0.01 (cash_balance is stored with 4
decimals; the sub-paisa remainder, < 0.01, is left unallocated and not
reported). Amounts are rounded DOWN to 0.01 so their sum never exceeds
capital; cash_amount is the exact remainder, so amounts + cash_amount ==
capital, all with 2 decimals.
"""

import math
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, Decimal
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session

from app.models import RiskProfile
from app.services.expected_returns import ExcludedTicker, get_expected_returns_for_universe
from app.services.optimization import (
    OptimizationError,
    TargetAllocationResult,
    optimize_target_weights,
)
from app.services.portfolios import get_portfolio
from app.services.return_providers import (
    HISTORICAL,
    ML,
    ExpectedReturnProvider,
    HistoricalMeanProvider,
    MLForecastProvider,
)
from app.services.universe import CUSTOM_UNIVERSE, get_universe, normalize_tickers

AMOUNT_QUANTUM = Decimal("0.01")
METRIC_DECIMALS = 6
# Matches the optimizer's feasibility tolerance.
POSITION_LIMIT_TOLERANCE = Decimal("0.0001")


@dataclass
class RecommendedAllocation:
    ticker: str
    expected_return: Decimal
    target_weight: Decimal
    amount: Decimal
    at_position_limit: bool
    source: str = HISTORICAL  # which provider produced expected_return


@dataclass
class SizedAllocation:
    capital: Decimal
    allocations: list[RecommendedAllocation]
    cash_weight: Decimal
    cash_amount: Decimal
    expected_portfolio_return: Decimal
    expected_portfolio_volatility: Decimal


@dataclass
class RecommendationConstraints:
    max_position_weight: Decimal
    target_volatility: Decimal


@dataclass
class Recommendation:
    universe: str
    universe_as_of: date | None
    return_model: str
    capital: Decimal
    allocations: list[RecommendedAllocation]
    cash_weight: Decimal
    cash_amount: Decimal
    expected_portfolio_return: Decimal
    expected_portfolio_volatility: Decimal
    constraints: RecommendationConstraints
    excluded: list[ExcludedTicker]
    model_version: str | None = None
    forecast_as_of: date | None = None


def size_allocation(
    target: TargetAllocationResult,
    expected_returns: list[Decimal],
    covariance: list[list[Decimal]],
    capital: Decimal,
    max_position_weight: Decimal,
    sources: dict[str, str] | None = None,
) -> SizedAllocation:
    """Zero-weight tickers are omitted from the returned allocations.
    `sources` maps a ticker to the provider of its expected return
    (default: historical)."""
    sources = sources or {}
    capital = capital.quantize(AMOUNT_QUANTUM, rounding=ROUND_DOWN)
    w = np.array([float(a.target_weight) for a in target.allocations])
    mu = np.array([float(r) for r in expected_returns])
    sigma = np.array([[float(v) for v in row] for row in covariance])

    portfolio_return = float(w @ mu)
    portfolio_vol = math.sqrt(max(float(w @ sigma @ w), 0.0))

    allocations = [
        RecommendedAllocation(
            ticker=a.ticker,
            expected_return=a.expected_return,
            target_weight=a.target_weight,
            amount=(a.target_weight * capital).quantize(AMOUNT_QUANTUM, rounding=ROUND_DOWN),
            at_position_limit=abs(a.target_weight - max_position_weight) <= POSITION_LIMIT_TOLERANCE,
            source=sources.get(a.ticker, HISTORICAL),
        )
        for a in target.allocations
        if a.target_weight != 0
    ]
    cash_amount = capital - sum((a.amount for a in allocations), Decimal("0"))

    return SizedAllocation(
        capital=capital,
        allocations=allocations,
        cash_weight=target.cash_weight,
        cash_amount=cash_amount,
        expected_portfolio_return=Decimal(str(round(portfolio_return, METRIC_DECIMALS))),
        expected_portfolio_volatility=Decimal(str(round(portfolio_vol, METRIC_DECIMALS))),
    )


# --- orchestration (DB + market data) --------------------------------------


def get_portfolio_recommendation(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID,
    *,
    universe: str | None = None,
    tickers: list[str] | None = None,
    return_model: str = HISTORICAL,
) -> Recommendation:
    """return_model picks the expected-return provider. The response reports
    the model actually used: "ml" if at least one ticker got an ML forecast,
    otherwise "historical" (every ticker fell back)."""
    portfolio = get_portfolio(db, user_id, portfolio_id)
    risk_profile = db.get(RiskProfile, portfolio.risk_profile_id)
    if risk_profile is None:
        raise OptimizationError("Portfolio has no associated risk profile.")

    if universe is not None:
        universe_name, as_of, candidates = get_universe(universe)
    else:
        universe_name, as_of, candidates = CUSTOM_UNIVERSE, None, normalize_tickers(tickers or [])

    provider: ExpectedReturnProvider = MLForecastProvider() if return_model == ML else HistoricalMeanProvider()
    data = get_expected_returns_for_universe(db, candidates, provider)
    target = optimize_target_weights(
        tickers=data.inputs.tickers,
        expected_returns=data.inputs.expected_returns,
        covariance=data.inputs.covariance,
        max_position_weight=risk_profile.max_position_weight,
        target_volatility=risk_profile.target_volatility,
    )

    sized = size_allocation(
        target,
        data.inputs.expected_returns,
        data.inputs.covariance,
        portfolio.cash_balance,
        risk_profile.max_position_weight,
        sources=data.sources,
    )
    used_ml = ML in data.sources.values()

    return Recommendation(
        universe=universe_name,
        universe_as_of=as_of,
        return_model=ML if used_ml else HISTORICAL,
        model_version=data.model_version if used_ml else None,
        forecast_as_of=data.forecast_as_of if used_ml else None,
        capital=sized.capital,
        allocations=sized.allocations,
        cash_weight=sized.cash_weight,
        cash_amount=sized.cash_amount,
        expected_portfolio_return=sized.expected_portfolio_return,
        expected_portfolio_volatility=sized.expected_portfolio_volatility,
        constraints=RecommendationConstraints(
            max_position_weight=risk_profile.max_position_weight,
            target_volatility=risk_profile.target_volatility,
        ),
        excluded=data.excluded,
    )
