from decimal import Decimal
from uuid import uuid4

from app.models import Holding, Portfolio
from app.services.valuation import calculate_valuation


def make_portfolio(cash_balance: Decimal) -> Portfolio:
    return Portfolio(
        id=uuid4(),
        user_id=uuid4(),
        risk_profile_id=uuid4(),
        name="Test",
        purpose=None,
        base_currency="INR",
        initial_capital=Decimal("100000"),
        cash_balance=cash_balance,
    )


def make_holding(ticker: str, quantity: Decimal, average_cost: Decimal) -> Holding:
    return Holding(
        id=uuid4(),
        portfolio_id=uuid4(),
        ticker=ticker,
        quantity=quantity,
        average_cost=average_cost,
    )


def test_valuation_with_multiple_holdings():
    portfolio = make_portfolio(Decimal("10000"))
    holdings = [
        make_holding("RELIANCE", Decimal("10"), Decimal("2500")),
        make_holding("TCS", Decimal("5"), Decimal("3000")),
    ]
    prices = {"RELIANCE": Decimal("2600"), "TCS": Decimal("2900")}

    result = calculate_valuation(portfolio, holdings, prices)

    assert result.invested_value == Decimal("40000")
    market_value = Decimal("10") * Decimal("2600") + Decimal("5") * Decimal("2900")
    assert result.total_value == Decimal("10000") + market_value
    assert result.unrealized_pnl == market_value - Decimal("40000")


def test_valuation_cash_only_empty_holdings():
    portfolio = make_portfolio(Decimal("50000"))

    result = calculate_valuation(portfolio, [], {})

    assert result.invested_value == Decimal("0")
    assert result.total_value == Decimal("50000")
    assert result.unrealized_pnl == Decimal("0")
    assert result.holdings == []


def test_valuation_gain_case():
    portfolio = make_portfolio(Decimal("0"))
    holdings = [make_holding("INFY", Decimal("10"), Decimal("1000"))]
    prices = {"INFY": Decimal("1200")}

    result = calculate_valuation(portfolio, holdings, prices)

    assert result.holdings[0].unrealized_pnl == Decimal("2000")


def test_valuation_loss_case():
    portfolio = make_portfolio(Decimal("0"))
    holdings = [make_holding("INFY", Decimal("10"), Decimal("1000"))]
    prices = {"INFY": Decimal("800")}

    result = calculate_valuation(portfolio, holdings, prices)

    assert result.holdings[0].unrealized_pnl == Decimal("-2000")
