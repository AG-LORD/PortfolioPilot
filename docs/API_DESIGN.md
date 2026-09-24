# API Design

All endpoints except `GET /health` require a Supabase bearer token
(`Authorization: Bearer <access_token>`). A portfolio that does not exist or
belongs to another user returns `404 Portfolio not found`.

Decimals are returned as JSON strings (e.g. `"0.1"`), dates as `YYYY-MM-DD`,
timestamps as ISO 8601. The live schema is at `/openapi.json` (interactive:
`/docs`). Example payloads for the frontend live in `frontend/src/lib/mocks/`
and are validated against these schemas by `backend/tests/test_frontend_mocks.py`.

## Endpoints

| Method | Path | Response |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` (no auth) |
| GET | `/users/me` | profile `{id, full_name, created_at}` |
| POST | `/users/me/risk-profile` | `RiskProfileRead` |
| GET | `/portfolios` | `PortfolioRead[]` |
| POST | `/portfolios` | `PortfolioRead` |
| GET | `/portfolios/overview` | `PortfolioOverviewRead` (see below) |
| GET | `/portfolios/{portfolio_id}` | `PortfolioRead` |
| POST | `/portfolios/{portfolio_id}/transactions` | `TransactionRead` |
| GET | `/portfolios/{portfolio_id}/transactions` | `TransactionRead[]` |
| GET | `/portfolios/{portfolio_id}/holdings` | `HoldingRead[]` |
| GET | `/portfolios/{portfolio_id}/valuation` | `PortfolioValuation` |
| GET | `/portfolios/{portfolio_id}/risk` | `RiskAnalyticsRead` |
| GET | `/portfolios/{portfolio_id}/optimize` | `TargetAllocationRead` |
| POST | `/portfolios/{portfolio_id}/recommendation` | `RecommendationRead` (see below) |
| GET | `/portfolios/{portfolio_id}/recommendations` | `RecommendationRead[]` (stub: always `[]`) |
| GET | `/portfolios/{portfolio_id}/recommendations/{recommendation_id}` | `RecommendationRead` (stub: always 404) |
| POST | `/portfolios/{portfolio_id}/snapshots` | `PortfolioSnapshotRead` |
| GET | `/universes` | `UniverseRead[]` (see below) |
| GET | `/ml/evaluation` | `ModelEvaluationRead[]` (stub: always `[]`) |

Endpoints without a section below are described by their schema in `/docs`.

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

- `universe`: a named universe (see `GET /universes`).
- `tickers`: bare NSE symbols (no `.NS`). They are uppercased, trimmed and de-duplicated. At most 100.
- `return_model`: only `"historical"` is accepted for now (optional, default).

**Method**
- About 365 days of adjusted daily closes per ticker. Tickers with no data or fewer than 31 trading days of history are excluded and listed in `excluded` with a reason.
- Remaining tickers are aligned on common dates (at least 31 overlapping days required).
- Expected returns are historical mean daily return × 252. Covariance is Ledoit-Wolf, annualized × 252.
- Weights come from the existing cash-aware optimizer using the risk profile's `max_position_weight` and `target_volatility`.
- `capital` is `cash_balance` rounded down to 0.01. `cash_balance` is stored with 4 decimals, so any sub-paisa remainder (less than ₹0.01) is left unallocated and not reported.
- `amount = target_weight × capital`, rounded down to 0.01. `cash_amount` is the exact remainder, so amounts + `cash_amount` = `capital`, all with 2 decimals.
- `at_position_limit` is true when `target_weight` equals `max_position_weight` within 0.0001.
- Prices are read through the daily price cache (`daily_prices`), and only missing dates are fetched from yfinance.
- Tickers with a zero target weight are omitted from `allocations`.

**Response 200** (`RecommendationRead`)

```json
{
  "id": null,
  "created_at": null,
  "portfolio_id": "3f2a1c9e-0000-4000-8000-000000000001",
  "universe": "custom",
  "universe_as_of": null,
  "return_model": "historical",
  "model_version": null,
  "forecast_as_of": null,
  "capital": "100000.00",
  "allocations": [
    { "ticker": "RELIANCE", "expected_return": "0.197665", "target_weight": "0.1", "amount": "10000.00", "at_position_limit": true },
    { "ticker": "INFY", "expected_return": "0.144422", "target_weight": "0.1", "amount": "10000.00", "at_position_limit": true },
    { "ticker": "HDFCBANK", "expected_return": "0.22987", "target_weight": "0.1", "amount": "10000.00", "at_position_limit": true }
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

- `universe` is the universe name, or `"custom"` for an explicit ticker list. `universe_as_of` is the date of the constituent list, or `null` for a custom list.
- `return_model` is `"historical"` or `"ml"`. Only `"historical"` is produced today.
- `model_version` and `forecast_as_of` are reserved for ML results; always `null` today.
- `id` and `created_at` are reserved for saved recommendations; always `null` from this endpoint today.

**Errors**
- `404`: portfolio not found or not owned by the caller.
- `422`: invalid body (both or neither of `universe`/`tickers`, unsupported `return_model`), unknown or unconfigured universe, no eligible tickers, too few overlapping trading days, or infeasible risk-profile constraints.

## GET /portfolios/{portfolio_id}/recommendations

Saved recommendations for a portfolio, newest first. Not persisted yet, so this
always returns `[]` (after the ownership check). Items will have the
`RecommendationRead` shape with `id` and `created_at` set.

```json
[]
```

## GET /portfolios/{portfolio_id}/recommendations/{recommendation_id}

One saved recommendation (`RecommendationRead`). Not persisted yet, so this
always returns `404 Recommendation not found` for the owner, and
`404 Portfolio not found` for anyone else. See
`frontend/src/lib/mocks/recommendation.ml.json` for the future shape.

## GET /portfolios/overview

Totals and a per-portfolio summary for the caller's portfolios.

- `valuation_status` is `"ok"` when live prices were available, otherwise `"unavailable"`.
- Today valuation fields are always `null`, `valuation_status` is `"unavailable"`, and `latest_recommendation` is `null`.
- `unrealized_pnl_pct` will be a fraction (`0.1111` = 11.11%).

```json
{
  "totals": {
    "portfolio_count": 1,
    "initial_capital": "100000.0000",
    "cash_balance": "50000.0000",
    "market_value": null,
    "total_value": null,
    "unrealized_pnl": null
  },
  "portfolios": [
    {
      "id": "3f2a1c9e-0000-4000-8000-000000000001",
      "name": "Growth",
      "risk_category": "moderate",
      "initial_capital": "100000.0000",
      "cash_balance": "50000.0000",
      "valuation_status": "unavailable",
      "market_value": null,
      "total_value": null,
      "unrealized_pnl": null,
      "unrealized_pnl_pct": null,
      "holdings_count": 3,
      "latest_recommendation": null
    }
  ]
}
```

When set, `latest_recommendation` is a `RecommendationSummary`:
`{id, created_at, universe, return_model, model_version, capital, cash_weight, expected_portfolio_return, expected_portfolio_volatility}`.

## GET /universes

Every known candidate universe. A universe whose constituent list has not been
supplied yet is listed with `configured: false`, `as_of: null` and no tickers.

```json
[
  { "name": "NIFTY50", "as_of": null, "tickers": [], "configured": false }
]
```

## GET /ml/evaluation

Out-of-sample evaluation results per model. Stub: always `[]` until models are
trained. Item shape:

```json
[
  { "model": "gradient_boosting", "mae": "0.0123", "hit_rate": "0.54", "mean_ic": "0.03", "test_blocks": 5, "as_of": "2026-09-01" }
]
```

- `mae`: mean absolute error of the forecast return. `hit_rate`: fraction of correctly predicted signs. `mean_ic`: mean information coefficient across test blocks. `test_blocks`: number of walk-forward test blocks.
