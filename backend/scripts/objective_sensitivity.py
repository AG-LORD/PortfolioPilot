"""Compares the optimizer objectives on today's inputs. Makes no database writes.

Run from backend/:
    python -m scripts.objective_sensitivity

For the NIFTY50 universe and the ML expected returns (today's stored nightly
forecasts; tickers without one are forecast on request, as in a live
recommendation) it prints, per risk profile and for both objectives
(max_return, mean_variance): number of holdings, max weight, min non-zero
weight, cash %, ex-ante return (weights x the model's own estimates),
ex-ante volatility and the number of sectors held. Then a lambda grid
(1, 2, 4, 8, 16) for the Moderate profile.

Everything runs inside one database transaction that is rolled back at the
end, so price-cache refreshes triggered while loading inputs are not kept.
"""

from dataclasses import dataclass
from decimal import Decimal

import numpy as np
from sqlalchemy.orm import Session

from app.database import engine
from app.services.expected_returns import get_expected_returns_for_universe
from app.services.optimization import (
    MAX_RETURN,
    MEAN_VARIANCE,
    RISK_AVERSION,
    TargetAllocationResult,
    optimize_target_weights,
    sector_groups,
    sector_map_for,
)
from app.services.recommendation import _ml_provider
from app.services.universe import get_universe

UNIVERSE = "NIFTY50"
LAMBDA_GRID = (1.0, 2.0, 4.0, 8.0, 16.0)


@dataclass(frozen=True)
class Profile:
    name: str
    max_position_weight: Decimal
    max_sector_weight: Decimal
    target_volatility: Decimal


# Mirrors CATEGORY_RISK_PROFILES in frontend/src/lib/riskMapping.ts.
PROFILES = [
    Profile("conservative", Decimal("0.05"), Decimal("0.15"), Decimal("0.08")),
    Profile("moderate", Decimal("0.10"), Decimal("0.25"), Decimal("0.15")),
    Profile("aggressive", Decimal("0.20"), Decimal("0.40"), Decimal("0.25")),
]

HEADER = f"{'profile':<13}{'objective':<17}{'holdings':>9}{'max w':>8}{'min w':>8}{'cash':>8}{'return':>9}{'vol':>8}{'sectors':>9}"


def _row(label: str, objective: str, result: TargetAllocationResult, mu: np.ndarray, sigma: np.ndarray, groups: list[str]) -> str:
    w = np.array([float(a.target_weight) for a in result.allocations])
    held = w > 0
    ret = float(w @ mu)
    vol = float(np.sqrt(max(w @ sigma @ w, 0.0)))
    sectors = len({groups[i] for i in np.flatnonzero(held)})
    max_w = w[held].max() if held.any() else 0.0
    min_w = w[held].min() if held.any() else 0.0
    return (
        f"{label:<13}{objective:<17}{int(held.sum()):>9}{max_w:>8.1%}{min_w:>8.1%}"
        f"{float(result.cash_weight):>8.1%}{ret:>9.2%}{vol:>8.2%}{sectors:>9}"
    )


def main() -> None:
    connection = engine.connect()
    outer = connection.begin()
    # Session commits only release savepoints; the outer rollback discards everything.
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        _, as_of, candidates = get_universe(UNIVERSE)
        data = get_expected_returns_for_universe(db, candidates, _ml_provider(db, candidates))
    finally:
        db.close()
        outer.rollback()
        connection.close()

    tickers = data.inputs.tickers
    mu = np.array([float(r) for r in data.inputs.expected_returns])
    sigma = np.array([[float(v) for v in row] for row in data.inputs.covariance])
    sectors = sector_map_for(tickers)
    groups = sector_groups(tickers, sectors)
    ml_count = sum(1 for source in data.sources.values() if source == "ml")

    print(f"Universe {UNIVERSE} (list as of {as_of}): {len(tickers)} eligible, {len(data.excluded)} excluded")
    print(
        f"Expected returns: {ml_count} ML ({data.forecast_source or 'n/a'}, forecast date {data.forecast_as_of}), "
        f"{len(tickers) - ml_count} historical fallback; {int((mu > 0).sum())} positive"
    )
    print("Return = weights x the model's own (unshrunk) estimates; both objectives use shrunk estimates and the sector cap.")
    print()
    print(HEADER)
    for profile in PROFILES:
        for objective in (MAX_RETURN, MEAN_VARIANCE):
            result = optimize_target_weights(
                tickers,
                data.inputs.expected_returns,
                data.inputs.covariance,
                profile.max_position_weight,
                profile.target_volatility,
                max_sector_weight=profile.max_sector_weight,
                sector_map=sectors,
                objective=objective,
                risk_aversion=RISK_AVERSION[profile.name],
            )
            label = profile.name if objective == MAX_RETURN else ""
            print(_row(label, objective, result, mu, sigma, groups))

    moderate = next(p for p in PROFILES if p.name == "moderate")
    print()
    print("Lambda grid, moderate profile (mean_variance):")
    print(HEADER.replace("profile      ", "lambda       "))
    for lam in LAMBDA_GRID:
        result = optimize_target_weights(
            tickers,
            data.inputs.expected_returns,
            data.inputs.covariance,
            moderate.max_position_weight,
            moderate.target_volatility,
            max_sector_weight=moderate.max_sector_weight,
            sector_map=sectors,
            objective=MEAN_VARIANCE,
            risk_aversion=lam,
        )
        print(_row(f"{lam:g}", MEAN_VARIANCE, result, mu, sigma, groups))


if __name__ == "__main__":
    main()
