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
{ "universe": "NIFTY50", "return_model": "ml" }
```
```json
{ "tickers": ["RELIANCE", "TCS", "INFY"], "return_model": "historical" }
```

- `universe`: a named universe (see `GET /universes`). `NIFTY50` is the official NSE Indices constituent list retrieved 2026-09-25 (`backend/app/data/nifty50.json`).
- `tickers`: bare NSE symbols (no `.NS`). They are uppercased, trimmed and de-duplicated. At most 100.
- `return_model`: `"historical"` (default) or `"ml"`. Any other value is a 422.

**Method**
- Adjusted daily prices come through the price cache (`daily_prices`); only missing dates are fetched from yfinance. The history loaded is 420 calendar days for `historical` and 6 × 365 calendar days for `ml`.
- A ticker needs at least 253 trading days of prices (252 daily returns). Tickers with no data or less history are excluded and listed in `excluded` with a reason.
- **historical:** each ticker's expected return is 252 × the mean of its last 252 daily returns. That is the same definition as the ML evaluation baseline, in annual units.
- **ml:** a HistGradientBoosting model is trained on the point-in-time feature panel using every row whose 20-day label is already known. It predicts each ticker's latest feature row, and the 20-trading-day forecast is converted to annual units as `forecast × 252 / 20`. A ticker with no feature row on the latest date falls back to its historical estimate, and its `source` is `"historical"`. Training happens on each request; nothing is persisted.
- Covariance is the same for both models: Ledoit-Wolf on daily returns over the dates common to all eligible tickers, limited to the last 252 of them (at least 30 required), annualized × 252.
- Weights come from the existing cash-aware optimizer. It maximizes expected return subject to the risk profile's `max_position_weight` and `target_volatility`, and the rest stays in cash.
- `capital` is `cash_balance` rounded down to 0.01. `cash_balance` is stored with 4 decimals, so any sub-paisa remainder (less than ₹0.01) is left unallocated and not reported.
- `amount = target_weight × capital`, rounded down to 0.01. `cash_amount` is the exact remainder, so amounts + `cash_amount` = `capital`, all with 2 decimals.
- `at_position_limit` is true when `target_weight` equals `max_position_weight` within 0.0001.
- Tickers with a zero target weight are omitted from `allocations`.

**Response 200** (`RecommendationRead`). Shape only; `<…>` marks values.

```json
{
  "id": null,
  "created_at": null,
  "portfolio_id": "<uuid>",
  "universe": "NIFTY50",
  "universe_as_of": "2026-09-25",
  "return_model": "ml",
  "model_version": "hist_gradient_boosting-h20-f12-v1",
  "forecast_as_of": "<date of the latest price used>",
  "capital": "<decimal, 2 dp>",
  "allocations": [
    {
      "ticker": "<symbol>",
      "expected_return": "<annualized decimal>",
      "target_weight": "<decimal, 6 dp>",
      "amount": "<decimal, 2 dp>",
      "at_position_limit": true,
      "source": "ml"
    }
  ],
  "cash_weight": "<decimal>",
  "cash_amount": "<decimal, 2 dp>",
  "expected_portfolio_return": "<annualized decimal>",
  "expected_portfolio_volatility": "<annualized decimal>",
  "constraints": { "max_position_weight": "<decimal>", "target_volatility": "<decimal>" },
  "excluded": [
    { "ticker": "<symbol>", "reason": "only 120 trading day(s) of history; at least 253 are needed" }
  ]
}
```

- `universe` is the universe name, or `"custom"` for an explicit ticker list. `universe_as_of` is the date of the constituent list, or `null` for a custom list.
- `return_model` is the model actually used. It is `"ml"` if at least one ticker got an ML forecast, and `"historical"` otherwise, including when `ml` was requested but no ML forecast could be made (for example, too little history to train on).
- `source` (per allocation) is `"ml"` or `"historical"`. In `ml` mode, `"historical"` marks a ticker that fell back.
- `model_version` and `forecast_as_of` are set only when `return_model` is `"ml"`. `model_version` is a fixed identifier (model, horizon, feature count, version), not a training timestamp.
- `expected_portfolio_return` is Σ weight × expected_return. `expected_portfolio_volatility` is √(wᵀΣw) from the covariance above. Both are annualized estimates, not realized results.
- `id` and `created_at` are reserved for saved recommendations; always `null` from this endpoint today.

**Errors**
- `401`: missing, invalid or expired token.
- `404`: portfolio not found or not owned by the caller. This is checked before any market data is fetched.
- `422`:
  - invalid body: both or neither of `universe`/`tickers`, an unsupported `return_model`, or an empty or too-long ticker list
  - unknown or unconfigured universe
  - no eligible tickers
  - fewer than 31 overlapping trading days across tickers
  - infeasible risk-profile constraints
- `503` is not used by this endpoint. A failed market-data download shows up as excluded tickers with the reason `history request failed: …`.

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
  { "name": "NIFTY50", "as_of": "2026-09-25", "tickers": ["ADANIENT", "ADANIPORTS", "…"], "configured": true }
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
