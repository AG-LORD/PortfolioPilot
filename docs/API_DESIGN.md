# API Design

All endpoints require a Supabase bearer token. A portfolio that does not exist
or belongs to another user returns `404 Portfolio not found`.

## POST /portfolios/{portfolio_id}/recommendation

Recommends how to allocate the portfolio's available cash (`cash_balance`)
across a candidate universe. Recommendation only: it does not write holdings,
transactions, cash balance or any other table, and nothing is persisted.
Works for portfolios with no holdings.

**Request**: exactly one of `universe` or `tickers`.

```json
{ "universe": "NIFTY50", "return_model": "historical" }
```
```json
{ "tickers": ["RELIANCE", "TCS", "INFY"], "return_model": "historical" }
```

- `universe`: a named universe (currently only `NIFTY50`).
- `tickers`: bare NSE symbols (no `.NS`). They are uppercased, trimmed and de-duplicated. At most 100.
- `return_model`: only `"historical"` for now (optional, default).

**Method**
- About 365 days of adjusted daily closes per ticker. Tickers with no data or fewer than 31 trading days of history are excluded and listed in `excluded` with a reason.
- Remaining tickers are aligned on common dates (at least 31 overlapping days required).
- Expected returns are historical mean daily return × 252. Covariance is Ledoit-Wolf, annualized × 252.
- Weights come from the existing cash-aware optimizer using the risk profile's `max_position_weight` and `target_volatility`.
- `capital` is `cash_balance` rounded down to 0.01. `cash_balance` is stored with 4 decimals, so any sub-paisa remainder (less than ₹0.01) is left unallocated and not reported.
- `amount = target_weight × capital`, rounded down to 0.01. `cash_amount` is the exact remainder, so amounts + `cash_amount` = `capital`, all with 2 decimals.
- Prices are read through the daily price cache (`daily_prices`), and only missing dates are fetched from yfinance.
- Tickers with a zero target weight are omitted from `allocations`.

**Response 200**

```json
{
  "portfolio_id": "3f2a1c9e-0000-4000-8000-000000000001",
  "universe": "custom",
  "universe_as_of": null,
  "return_model": "historical",
  "capital": "100000.00",
  "allocations": [
    { "ticker": "RELIANCE", "expected_return": "0.197665", "target_weight": "0.1", "amount": "10000.00" },
    { "ticker": "INFY", "expected_return": "0.144422", "target_weight": "0.1", "amount": "10000.00" },
    { "ticker": "HDFCBANK", "expected_return": "0.22987", "target_weight": "0.1", "amount": "10000.00" }
  ],
  "cash_weight": "0.7",
  "cash_amount": "70000.00",
  "expected_portfolio_return": "0.057196",
  "expected_portfolio_volatility": "0.040847",
  "constraints": { "max_position_weight": "0.10", "target_volatility": "0.15" },
  "excluded": [
    { "ticker": "NEWIPO", "reason": "only 12 trading day(s) of history; at least 31 are needed" },
    { "ticker": "DELISTED", "reason": "no historical data returned" }
  ]
}
```

`universe` is the universe name, or `"custom"` for an explicit ticker list. `universe_as_of` is the date of the constituent list, or `null` for a custom list.

**Errors**
- `404`: portfolio not found or not owned by the caller.
- `422`: invalid body (both or neither of `universe`/`tickers`, unsupported `return_model`), unknown or unconfigured universe, no eligible tickers, too few overlapping trading days, or infeasible risk-profile constraints.
