from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Holding, Portfolio
from app.schemas.valuation import HoldingValuation, PortfolioValuation
from app.services import market_data
from app.services.portfolios import get_portfolio, list_holdings


def calculate_valuation(
    portfolio: Portfolio,
    holdings: list[Holding],
    prices: dict[str, Decimal],
) -> PortfolioValuation:
    holding_valuations = []
    invested_value = Decimal("0")
    total_market_value = Decimal("0")

    for holding in holdings:
        current_price = prices[holding.ticker]
        market_value = holding.quantity * current_price
        cost_basis = holding.quantity * holding.average_cost
        unrealized_pnl = market_value - cost_basis

        invested_value += cost_basis
        total_market_value += market_value

        holding_valuations.append(
            HoldingValuation(
                ticker=holding.ticker,
                quantity=holding.quantity,
                average_cost=holding.average_cost,
                current_price=current_price,
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
            )
        )

    return PortfolioValuation(
        portfolio_id=portfolio.id,
        cash_balance=portfolio.cash_balance,
        invested_value=invested_value,
        total_value=portfolio.cash_balance + total_market_value,
        unrealized_pnl=total_market_value - invested_value,
        holdings=holding_valuations,
    )


def get_portfolio_valuation(db: Session, user_id: UUID, portfolio_id: UUID) -> PortfolioValuation:
    portfolio = get_portfolio(db, user_id, portfolio_id)
    holdings = list_holdings(db, user_id, portfolio_id)

    # Fetch every ticker's price before computing anything: if any one
    # fails, this raises immediately and no partial valuation is built.
    prices = {holding.ticker: market_data.get_current_price(holding.ticker) for holding in holdings}

    return calculate_valuation(portfolio, holdings, prices)
