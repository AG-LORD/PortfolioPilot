"""The portfolio's plan: the recommendation drift and rebalancing aim at.

The plan is the ADOPTED recommendation when the user has adopted one, else the
latest saved recommendation. Adopting changes no holdings or cash; it only
records which snapshot to follow.

Staleness: a latest-recommendation target is stale once the portfolio changed
after it was saved (its capital no longer matches). An adopted plan is never
stale: its weights apply to whatever the portfolio is worth now, so recording
the plan's own orders does not invalidate it.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Portfolio, RecommendationSnapshot
from app.services.portfolios import get_portfolio


def latest_recommendation(db: Session, portfolio_id: UUID) -> RecommendationSnapshot | None:
    return db.scalars(
        select(RecommendationSnapshot)
        .where(RecommendationSnapshot.portfolio_id == portfolio_id)
        .order_by(RecommendationSnapshot.created_at.desc())
        .limit(1)
    ).first()


def plan_target(db: Session, portfolio: Portfolio) -> tuple[RecommendationSnapshot | None, bool]:
    """(target snapshot or None, whether it is the adopted plan)."""
    if portfolio.adopted_recommendation_id is not None:
        adopted = db.get(RecommendationSnapshot, portfolio.adopted_recommendation_id)
        if adopted is not None and adopted.portfolio_id == portfolio.id:
            return adopted, True
    return latest_recommendation(db, portfolio.id), False


def is_target_stale(portfolio: Portfolio, target: RecommendationSnapshot, adopted: bool) -> bool:
    return not adopted and portfolio.updated_at > target.created_at


def adopt_recommendation(db: Session, user_id: UUID, portfolio_id: UUID, recommendation_id: UUID) -> Portfolio:
    portfolio = get_portfolio(db, user_id, portfolio_id)
    snapshot = db.get(RecommendationSnapshot, recommendation_id)
    if snapshot is None or snapshot.portfolio_id != portfolio_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")

    # Core UPDATE that keeps updated_at as is: adopting is not a change to cash
    # or holdings, so it must not make the latest recommendation look stale.
    db.execute(
        update(Portfolio)
        .where(Portfolio.id == portfolio_id)
        .values(
            adopted_recommendation_id=recommendation_id,
            adopted_at=datetime.now(timezone.utc),
            updated_at=Portfolio.updated_at,
        )
    )
    db.commit()
    db.refresh(portfolio)
    return portfolio
