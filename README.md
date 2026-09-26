# PortfolioPilot

### ML-Assisted, Risk-Aware Portfolio Decision Support

PortfolioPilot is a Next.js and FastAPI application for managing Indian-equity portfolios and reviewing advisory target allocations. Portfolio state is persisted in PostgreSQL/Supabase; recommendations do not execute trades.

## Current Workflows

- Register or log in with Supabase Auth.
- Create a risk profile and portfolio, then generate a historical-baseline or ML-assisted recommendation.
- Save recommendations as immutable snapshots and reopen them without regenerating market data.
- View holdings, transactions, valuation, snapshot-based risk analytics, and add capital.
- Review backend-calculated drift against the latest saved target.
- Create a persistent, read-only rebalance proposal; execute only after explicit confirmation.
- Inspect an individual stock’s adjusted OHLC history, existing technical indicators, and portfolio context on demand.
- View the latest saved walk-forward evaluation and run a historical portfolio simulation.

## Recommendation Pipeline

Adjusted price history → point-in-time technical features → ML forecast or historical baseline → expected returns and covariance → risk-constrained optimization → target allocation → immutable recommendation snapshot.

Live recommendation generation does not change cash, holdings, or transactions. Rebalancing is a separate review and execution flow.

## Backtesting

Backtests use purged walk-forward forecasts, adjusted cached prices, and a one-common-session delay between signal and execution. The response clearly identifies fractional-share, zero-fee, and risk-free-rate assumptions. Backtest results are simulated research results, not live portfolio performance.

## Technology

- Frontend: Next.js, React, TypeScript, Tailwind CSS.
- Backend: FastAPI, Pydantic, SQLAlchemy, Alembic.
- Database and identity: PostgreSQL/Supabase and Supabase Auth.
- Market data: yfinance adjusted OHLC, stored through a refresh-aware daily cache.
- Research: pandas, NumPy, scikit-learn, SciPy.

## Local Development

Backend commands run from `backend/`; install `requirements.txt`, configure `DATABASE_URL` and Supabase Auth settings, then start FastAPI with `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`. Apply schema changes with `python -m alembic upgrade head`.

The backend test guard requires a dedicated `TEST_DATABASE_URL` for database tests. `PP_NO_DB=1` runs only tests that do not use the configured database. Frontend commands run from `frontend/`: `npm run dev`, `npm run lint`, and `npm run build`.

## Current Limitations

- The NIFTY 50 evaluation uses a fixed present-day constituent list over historical dates, so survivorship bias remains.
- The evaluation endpoint serves the latest saved offline report; it does not train on demand.
- Rebalance fees are reported as zero because no fee schedule is configured.
- Backtests use fractional shares and adjusted close execution at the next common session; they are not exchange execution simulations.
- Risk analytics use manually triggered snapshots and approximate irregular spacing as daily observations.
- Sector limits are stored in risk profiles but are not enforced without a reliable sector map.
- Account verification, database permissions, and real user-authenticated flows require configured Supabase credentials.
