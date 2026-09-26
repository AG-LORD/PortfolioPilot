import hashlib
import json
from decimal import Decimal, ROUND_DOWN
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Holding, Portfolio, RebalanceProposal, RecommendationSnapshot
from app.schemas.rebalance import (
    RebalanceProposalRead,
    RebalanceTradeRead,
    RebalanceWeightRead,
)
from app.services import market_data
from app.services.portfolios import get_portfolio

ZERO = Decimal("0")
FEE_ASSUMPTION = "No fee schedule is configured; estimated fees are zero."


def _fingerprint(
    portfolio: Portfolio,
    holdings: list[Holding],
    target: RecommendationSnapshot,
    prices: dict[str, Decimal],
) -> str:
    state = {
        "cash_balance": str(portfolio.cash_balance),
        "holdings": [
            [holding.ticker, str(holding.quantity), str(holding.average_cost)]
            for holding in sorted(holdings, key=lambda item: item.ticker)
        ],
        "portfolio_updated_at": portfolio.updated_at.isoformat(),
        "recommendation_id": str(target.id),
        "prices": {ticker: str(price) for ticker, price in sorted(prices.items())},
    }
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode("utf-8")).hexdigest()


def _proposal_read(proposal: RebalanceProposal) -> RebalanceProposalRead:
    return RebalanceProposalRead(
        id=proposal.id,
        portfolio_id=proposal.portfolio_id,
        recommendation_id=proposal.recommendation_id,
        created_at=proposal.created_at,
        status=proposal.status,
        portfolio_value=proposal.portfolio_value,
        cash_before=proposal.cash_before,
        projected_cash=proposal.projected_cash,
        buy_total=proposal.buy_total,
        sell_total=proposal.sell_total,
        estimated_fees=proposal.estimated_fees,
        fee_assumption=proposal.fee_assumption,
        trades=[RebalanceTradeRead.model_validate(item) for item in proposal.trades],
        resulting_weights=[RebalanceWeightRead.model_validate(item) for item in proposal.resulting_weights],
    )


def create_rebalance_proposal(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID,
    recommendation_id: UUID | None = None,
) -> RebalanceProposalRead:
    portfolio = get_portfolio(db, user_id, portfolio_id)
    if recommendation_id is None:
        target = db.scalars(
            select(RecommendationSnapshot)
            .where(RecommendationSnapshot.portfolio_id == portfolio_id)
            .order_by(RecommendationSnapshot.created_at.desc())
            .limit(1)
        ).first()
    else:
        target = db.get(RecommendationSnapshot, recommendation_id)
        if target is not None and target.portfolio_id != portfolio_id:
            target = None
    if target is None:
        raise ValueError("A saved recommendation is required before proposing rebalancing")
    if portfolio.updated_at > target.created_at:
        raise ValueError("The saved target is stale; generate a new recommendation first")

    holdings = db.scalars(
        select(Holding).where(Holding.portfolio_id == portfolio_id)
    ).all()
    target_weights = {
        item["ticker"]: Decimal(str(item["target_weight"]))
        for item in target.allocations
    }
    tickers = sorted({holding.ticker for holding in holdings} | set(target_weights))
    prices = {ticker: market_data.get_current_price(ticker) for ticker in tickers}
    holding_by_ticker = {holding.ticker: holding for holding in holdings}
    total_value = portfolio.cash_balance + sum(
        (holding.quantity * prices[holding.ticker] for holding in holdings), ZERO
    )
    if total_value <= ZERO:
        raise ValueError("A rebalance proposal requires a positive portfolio value")

    sell_candidates: list[tuple[str, int]] = []
    buy_candidates: list[tuple[Decimal, str, int]] = []
    current_values: dict[str, Decimal] = {}
    for ticker in tickers:
        holding = holding_by_ticker.get(ticker)
        current_quantity = holding.quantity if holding else ZERO
        current_value = current_quantity * prices[ticker]
        current_values[ticker] = current_value
        target_value = total_value * target_weights.get(ticker, ZERO)
        target_quantity = int((target_value / prices[ticker]).to_integral_value(rounding=ROUND_DOWN))
        current_whole_quantity = int(current_quantity.to_integral_value(rounding=ROUND_DOWN))
        if current_whole_quantity > target_quantity:
            sell_candidates.append((ticker, current_whole_quantity - target_quantity))
        elif target_quantity > current_whole_quantity:
            buy_candidates.append((target_value - current_value, ticker, target_quantity - current_whole_quantity))

    trades: list[dict] = []
    sell_total = ZERO
    for ticker, quantity in sorted(sell_candidates):
        price = prices[ticker]
        gross = Decimal(quantity) * price
        sell_total += gross
        holding = holding_by_ticker.get(ticker)
        resulting_quantity = (holding.quantity if holding else ZERO) - Decimal(quantity)
        trades.append(
            {
                "ticker": ticker,
                "side": "SELL",
                "quantity": quantity,
                "estimated_price": price,
                "estimated_gross_amount": gross,
                "estimated_fee": ZERO,
                "estimated_net_amount": gross,
                "current_weight": current_values[ticker] / total_value,
                "target_weight": target_weights.get(ticker, ZERO),
                "resulting_weight": resulting_quantity * price / total_value,
            }
        )

    cash_after_sells = portfolio.cash_balance + sell_total
    buy_total = ZERO
    for _deficit, ticker, requested_quantity in sorted(
        buy_candidates,
        key=lambda item: (-item[0], item[1]),
    ):
        price = prices[ticker]
        affordable_quantity = int((cash_after_sells / price).to_integral_value(rounding=ROUND_DOWN))
        quantity = min(requested_quantity, affordable_quantity)
        if quantity <= 0:
            continue
        gross = Decimal(quantity) * price
        cash_after_sells -= gross
        buy_total += gross
        holding = holding_by_ticker.get(ticker)
        current_quantity = holding.quantity if holding else ZERO
        trades.append(
            {
                "ticker": ticker,
                "side": "BUY",
                "quantity": quantity,
                "estimated_price": price,
                "estimated_gross_amount": gross,
                "estimated_fee": ZERO,
                "estimated_net_amount": gross,
                "current_weight": current_values[ticker] / total_value,
                "target_weight": target_weights.get(ticker, ZERO),
                "resulting_weight": (current_quantity + Decimal(quantity)) * price / total_value,
            }
        )

    trade_by_ticker = {trade["ticker"]: trade for trade in trades}
    resulting_weights = []
    for ticker in [*tickers, "CASH"]:
        if ticker == "CASH":
            current_value = portfolio.cash_balance
            target_weight = target.cash_weight
            resulting_value = cash_after_sells
            current_weight = current_value / total_value
            resulting_weight = resulting_value / total_value
        else:
            current_value = current_values[ticker]
            target_weight = target_weights.get(ticker, ZERO)
            trade = trade_by_ticker.get(ticker)
            quantity_delta = Decimal(trade["quantity"]) * (Decimal("1") if trade["side"] == "BUY" else Decimal("-1")) if trade else ZERO
            resulting_value = (holding_by_ticker[ticker].quantity if ticker in holding_by_ticker else ZERO) + quantity_delta
            resulting_value *= prices[ticker]
            current_weight = current_value / total_value
            resulting_weight = resulting_value / total_value
        resulting_weights.append(
            {
                "ticker": ticker,
                "current_weight": current_weight,
                "target_weight": target_weight,
                "resulting_weight": resulting_weight,
            }
        )

    proposal = RebalanceProposal(
        portfolio_id=portfolio_id,
        recommendation_id=target.id,
        state_fingerprint=_fingerprint(portfolio, holdings, target, prices),
        portfolio_value=total_value,
        cash_before=portfolio.cash_balance,
        projected_cash=cash_after_sells,
        buy_total=buy_total,
        sell_total=sell_total,
        estimated_fees=ZERO,
        fee_assumption=FEE_ASSUMPTION,
        trades=[
            RebalanceTradeRead.model_validate(item).model_dump(mode="json")
            for item in trades
        ],
        resulting_weights=[
            RebalanceWeightRead.model_validate(item).model_dump(mode="json")
            for item in resulting_weights
        ],
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return _proposal_read(proposal)


def get_rebalance_proposal(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID,
    proposal_id: UUID,
) -> RebalanceProposalRead:
    get_portfolio(db, user_id, portfolio_id)
    proposal = db.get(RebalanceProposal, proposal_id)
    if proposal is None or proposal.portfolio_id != portfolio_id:
        raise ValueError("Rebalance proposal not found")
    return _proposal_read(proposal)