"use client";

import { Suspense, useEffect, useEffectEvent, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { NextSteps } from "@/components/portfolio/NextSteps";
import { PortfolioNav } from "@/components/shell/PortfolioNav";
import { apiFetch, getAccessToken } from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import { formatCurrency } from "@/lib/format";
import type { RecommendationSummary } from "@/lib/types/api";

type Portfolio = {
  id: string;
  name: string;
  purpose: string | null;
  base_currency: string;
  initial_capital: string;
  cash_balance: string;
};

type Holding = {
  id: string;
  ticker: string;
  quantity: string;
  average_cost: string;
};

type Transaction = {
  id: string;
  transaction_type: string;
  ticker: string;
  quantity: string;
  price: string;
  fees: string;
  occurred_at: string;
  source: string;
};

type HoldingValuation = {
  ticker: string;
  quantity: string;
  average_cost: string;
  current_price: string;
  market_value: string;
  unrealized_pnl: string;
};

type PortfolioValuation = {
  portfolio_id: string;
  cash_balance: string;
  invested_value: string;
  total_value: string;
  unrealized_pnl: string;
  holdings: HoldingValuation[];
};

type RiskAnalytics = {
  portfolio_id: string;
  observation_count: number;
  first_snapshot_date: string | null;
  last_snapshot_date: string | null;
  cumulative_return: string | null;
  annualized_volatility: string | null;
  max_drawdown: string | null;
  sharpe_ratio: string | null;
  risk_free_rate_annual: string;
  historical_var: string | null;
  historical_cvar: string | null;
  var_confidence: string;
  message: string | null;
};

function PortfolioDetailView() {
  const { portfolioId } = useParams<{ portfolioId: string }>();
  // "I bought this" links from the buy list pre-fill the trade form; the user can edit before recording.
  const searchParams = useSearchParams();

  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [holdings, setHoldings] = useState<Holding[] | null>(null);
  const [transactions, setTransactions] = useState<Transaction[] | null>(null);
  const [valuation, setValuation] = useState<PortfolioValuation | null>(null);
  const [riskAnalytics, setRiskAnalytics] = useState<RiskAnalytics | null>(null);
  const [recommendationCount, setRecommendationCount] = useState<number | null>(null);
  const [capitalAddAmount, setCapitalAddAmount] = useState("10000");
  const [capitalSubmitting, setCapitalSubmitting] = useState(false);
  const [capitalError, setCapitalError] = useState<string | null>(null);
  const [tradeType, setTradeType] = useState<"BUY" | "SELL">("BUY");
  const [tradeTicker, setTradeTicker] = useState(() => searchParams.get("ticker") ?? "");
  const [tradeQuantity, setTradeQuantity] = useState(() => searchParams.get("qty") ?? "");
  const [tradePrice, setTradePrice] = useState(() => searchParams.get("price") ?? "");
  const [tradeFees, setTradeFees] = useState("0");
  const [tradeSubmitting, setTradeSubmitting] = useState(false);
  const [tradeError, setTradeError] = useState<string | null>(null);
  const [snapshotSubmitting, setSnapshotSubmitting] = useState(false);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [snapshotMessage, setSnapshotMessage] = useState<string | null>(null);

  const [authError, setAuthError] = useState<string | null>(null);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);
  const [holdingsError, setHoldingsError] = useState<string | null>(null);
  const [transactionsError, setTransactionsError] = useState<string | null>(null);
  const [valuationError, setValuationError] = useState<string | null>(null);
  const [riskAnalyticsError, setRiskAnalyticsError] = useState<string | null>(null);

  async function loadAll(accessToken: string) {
    try {
      setPortfolio(await apiFetch<Portfolio>(`/portfolios/${portfolioId}`, accessToken));
    } catch (err) {
      console.error("Failed to load portfolio:", err);
      setPortfolioError(getErrorMessage(err, "Unable to load this portfolio."));
    }

    try {
      setHoldings(await apiFetch<Holding[]>(`/portfolios/${portfolioId}/holdings`, accessToken));
    } catch (err) {
      console.error("Failed to load holdings:", err);
      setHoldingsError(getErrorMessage(err, "Unable to load holdings."));
    }

    try {
      setTransactions(await apiFetch<Transaction[]>(`/portfolios/${portfolioId}/transactions`, accessToken));
    } catch (err) {
      console.error("Failed to load transactions:", err);
      setTransactionsError(getErrorMessage(err, "Unable to load transactions."));
    }

    try {
      setValuation(await apiFetch<PortfolioValuation>(`/portfolios/${portfolioId}/valuation`, accessToken));
    } catch (err) {
      console.error("Failed to load valuation:", err);
      setValuationError(getErrorMessage(err, "Live valuation is currently unavailable."));
    }

    try {
      setRiskAnalytics(await apiFetch<RiskAnalytics>(`/portfolios/${portfolioId}/risk`, accessToken));
    } catch (err) {
      console.error("Failed to load risk analytics:", err);
      setRiskAnalyticsError(getErrorMessage(err, "Risk analytics are currently unavailable."));
    }

    try {
      const recommendations = await apiFetch<RecommendationSummary[]>(`/portfolios/${portfolioId}/recommendations`, accessToken);
      setRecommendationCount(recommendations.length);
    } catch (err) {
      console.error("Failed to load recommendations:", err);
    }
  }

  const loadAllForSession = useEffectEvent(loadAll);

  useEffect(() => {
    const supabase = createClient();

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        void loadAllForSession(session.access_token);
      } else {
        setAuthError("No active session.");
      }
    });

    return () => subscription.unsubscribe();
  }, [portfolioId]);

  const portfolioLoaded = portfolio !== null;
  useEffect(() => {
    // The trade form only exists once the portfolio has loaded, so the browser can't scroll to the hash on its own.
    if (portfolioLoaded && window.location.hash === "#record-trade") {
      document.getElementById("record-trade")?.scrollIntoView({ block: "start" });
    }
  }, [portfolioLoaded]);

  async function handleCapitalAdd(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const amount = Number(capitalAddAmount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setCapitalError("Enter a valid amount greater than zero.");
      return;
    }

    const accessToken = await getAccessToken();
    if (!accessToken) {
      setCapitalError("You are signed out. Please log in again.");
      return;
    }

    try {
      setCapitalSubmitting(true);
      setCapitalError(null);
      const updated = await apiFetch<Portfolio>(`/portfolios/${portfolioId}/capital`, accessToken, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount: amount.toString() }),
      });
      setPortfolio(updated);
      await loadAll(accessToken);
      setCapitalAddAmount("10000");
    } catch (err) {
      console.error("Failed to add capital:", err);
      setCapitalError(err instanceof Error ? err.message : "Unable to add capital right now.");
    } finally {
      setCapitalSubmitting(false);
    }
  }

  async function handleTradeSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const quantity = Number(tradeQuantity);
    const price = Number(tradePrice);
    const fees = Number(tradeFees);
    if (!tradeTicker.trim() || !Number.isFinite(quantity) || quantity <= 0 || !Number.isFinite(price) || price <= 0 || !Number.isFinite(fees) || fees < 0) {
      setTradeError("Enter a ticker, positive quantity and price, and non-negative fees.");
      return;
    }

    const accessToken = await getAccessToken();
    if (!accessToken) {
      setTradeError("You are signed out. Please log in again.");
      return;
    }

    try {
      setTradeSubmitting(true);
      setTradeError(null);
      await apiFetch<Transaction>(`/portfolios/${portfolioId}/transactions`, accessToken, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: tradeTicker,
          transaction_type: tradeType,
          quantity: quantity.toString(),
          price: price.toString(),
          fees: fees.toString(),
        }),
      });
      await loadAll(accessToken);
      setTradeTicker("");
      setTradeQuantity("");
      setTradePrice("");
      setTradeFees("0");
    } catch (err) {
      console.error("Failed to record transaction:", err);
      setTradeError(err instanceof Error ? err.message : "Unable to record this trade.");
    } finally {
      setTradeSubmitting(false);
    }
  }

  async function handleCreateSnapshot() {
    const accessToken = await getAccessToken();
    if (!accessToken) {
      setSnapshotError("You are signed out. Please log in again.");
      return;
    }

    try {
      setSnapshotSubmitting(true);
      setSnapshotError(null);
      setSnapshotMessage(null);
      await apiFetch<unknown>(`/portfolios/${portfolioId}/snapshots`, accessToken, {
        method: "POST",
      });
      setRiskAnalytics(await apiFetch<RiskAnalytics>(`/portfolios/${portfolioId}/risk`, accessToken));
      setSnapshotMessage("Today's portfolio value was saved and risk figures were refreshed.");
    } catch (err) {
      console.error("Failed to record portfolio snapshot:", err);
      setSnapshotError(err instanceof Error ? err.message : "Unable to record a snapshot.");
    } finally {
      setSnapshotSubmitting(false);
    }
  }

  if (authError) {
    return (
      <main className="page-shell">
        <div className="notice error" role="alert">
          <span className="notice-icon">⚠</span>
          <div>{authError}</div>
        </div>
      </main>
    );
  }

  if (portfolioError) {
    return (
      <main className="page-shell">
        <div className="notice error" role="alert">
          <span className="notice-icon">⚠</span>
          <div>{portfolioError}</div>
        </div>
      </main>
    );
  }

  if (!portfolio) {
    return (
      <main className="page-shell">
        <div className="card list-card">
          <div className="skeleton skeleton-box" />
        </div>
      </main>
    );
  }

  const valuationByTicker = new Map(valuation?.holdings.map((h) => [h.ticker, h]) ?? []);

  return (
    <main className="page-shell">
      <PortfolioNav portfolioId={portfolioId} current="current" portfolioName={portfolio.name} />
      <header className="page-header">
        <div className="page-heading">
          <span className="eyebrow">Current portfolio · what you currently own</span>
          <h1 className="page-title">{portfolio.name}</h1>
          {portfolio.purpose && <p className="page-subtitle">{portfolio.purpose}</p>}
        </div>
      </header>

      <NextSteps
        portfolioId={portfolioId}
        hasRecommendation={recommendationCount === null ? null : recommendationCount > 0}
        hasHoldings={holdings === null ? null : holdings.length > 0}
        hasPerformanceHistory={riskAnalytics === null ? null : riskAnalytics.observation_count > 0}
      />

      <section className="metric-grid">
        <article className="metric-card">
          <span className="metric-label">Initial capital</span>
          <strong className="metric-value">{formatCurrency(portfolio.initial_capital)}</strong>
        </article>
        <article className="metric-card">
          <span className="metric-label">Cash balance</span>
          <strong className="metric-value">{formatCurrency(portfolio.cash_balance)}</strong>
        </article>
        <article className="metric-card">
          <span className="metric-label">Portfolio value</span>
          <strong className="metric-value">{valuation ? formatCurrency(valuation.total_value) : "—"}</strong>
          {valuationError && <small className="utility-text" role="status">{valuationError}</small>}
        </article>
        <article className="metric-card">
          <span className="metric-label">Invested value</span>
          <strong className="metric-value">{valuation ? formatCurrency(valuation.invested_value) : "—"}</strong>
        </article>
      </section>

      <div className="portfolio-grid" style={{ marginBottom: 24 }}>
        <section className="card list-card">
          <div className="section-header">
            <h2 className="section-title">Holdings</h2>
          </div>

          {holdingsError && <p className="utility-text">{holdingsError}</p>}
          {!holdingsError && holdings === null && <p className="utility-text">Loading holdings...</p>}
          {holdings !== null && holdings.length === 0 && <div className="empty-state"><p>No holdings yet.</p></div>}
          {holdings !== null && holdings.length > 0 && (
            <div className="portfolio-list">
              {holdings.map((holding) => {
                const valuationDetail = valuationByTicker.get(holding.ticker);
                return (
                  <div key={holding.id} className="portfolio-list-item" style={{ alignItems: "flex-start" }}>
                    <div className="portfolio-meta">
                      <strong>{holding.ticker}</strong>
                      <small>Qty {holding.quantity} · Avg cost {formatCurrency(holding.average_cost)}</small>
                    </div>
                    {valuationDetail && (
                      <div className="portfolio-meta" style={{ textAlign: "right" }}>
                        <small>Current price {formatCurrency(valuationDetail.current_price)}</small>
                        <small>Market value {formatCurrency(valuationDetail.market_value)}</small>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <section className="card list-card">
          <div className="section-header">
            <h2 className="section-title">Transactions</h2>
          </div>

          {transactionsError && <p className="utility-text">{transactionsError}</p>}
          {!transactionsError && transactions === null && <p className="utility-text">Loading transactions...</p>}
          {transactions !== null && transactions.length === 0 && <div className="empty-state"><p>No transactions yet.</p></div>}
          {transactions !== null && transactions.length > 0 && (
            <div className="portfolio-list">
              {transactions.map((transaction) => (
                <div key={transaction.id} className="portfolio-list-item" style={{ display: "grid", gap: 4 }}>
                  <div className="portfolio-meta">
                    <strong>{transaction.ticker}</strong>
                    <small>
                      {transaction.transaction_type} · Qty {transaction.quantity} @ {formatCurrency(transaction.price)}
                    </small>
                  </div>
                  <small className="utility-text">{new Date(transaction.occurred_at).toLocaleString()} · {transaction.source}</small>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      <div className="detail-grid" style={{ marginBottom: 24 }}>
        <section className="panel" id="record-trade" style={{ padding: 20, scrollMarginTop: 80 }}>
          <div className="section-header" style={{ marginBottom: 10 }}>
            <div>
              <h2 className="section-title" style={{ fontSize: "1.2rem" }}>Record a trade you made with your broker</h2>
              <p className="field-hint">PortfolioPilot does not place real orders.</p>
            </div>
          </div>
          <form onSubmit={handleTradeSubmit} className="trade-entry-form">
            <div className="segmented-actions" role="group" aria-label="Transaction side">
              {(["BUY", "SELL"] as const).map((side) => (
                <button
                  type="button"
                  key={side}
                  className={`segmented-button ${tradeType === side ? "active" : ""}`}
                  aria-pressed={tradeType === side}
                  onClick={() => setTradeType(side)}
                >
                  {side}
                </button>
              ))}
            </div>
            <label className="field-group">
              <span className="field-label">NSE ticker</span>
              <input value={tradeTicker} onChange={(event) => setTradeTicker(event.target.value)} placeholder="TCS" autoComplete="off" />
            </label>
            <div className="trade-entry-fields">
              <label className="field-group">
                <span className="field-label">Shares</span>
                <input type="number" min="0.000001" step="0.000001" value={tradeQuantity} onChange={(event) => setTradeQuantity(event.target.value)} />
              </label>
              <label className="field-group">
                <span className="field-label">Price ({portfolio.base_currency})</span>
                <input type="number" min="0.0001" step="0.0001" value={tradePrice} onChange={(event) => setTradePrice(event.target.value)} />
              </label>
            </div>
            <label className="field-group">
              <span className="field-label">Fees ({portfolio.base_currency})</span>
              <input type="number" min="0" step="0.0001" value={tradeFees} onChange={(event) => setTradeFees(event.target.value)} />
            </label>
            {tradeError && <p className="notice error" role="alert">{tradeError}</p>}
            <button type="submit" className="primary-button" disabled={tradeSubmitting}>
              {tradeSubmitting ? "Recording trade..." : `Record ${tradeType}`}
            </button>
          </form>
        </section>

        <section className="panel" style={{ padding: 20, display: "grid", gap: 12, alignContent: "start" }}>
          <div className="section-header" style={{ marginBottom: 0 }}>
            <h2 className="section-title" style={{ fontSize: "1.2rem" }}>Risk analytics</h2>
          </div>
          {riskAnalyticsError && <p className="utility-text">{riskAnalyticsError}</p>}
          {!riskAnalyticsError && riskAnalytics === null && <p className="utility-text">Loading risk analytics...</p>}
          {riskAnalytics !== null && (
            <div className="info-stack">
              <div className="detail-item">
                <span className="detail-label">Annualized volatility</span>
                <div className="detail-value">{riskAnalytics.annualized_volatility ?? "Not enough data yet"}</div>
              </div>
              <div className="detail-item">
                <span className="detail-label">Sharpe ratio</span>
                <div className="detail-value">{riskAnalytics.sharpe_ratio ?? "Not enough data yet"}</div>
              </div>
            </div>
          )}
          {snapshotError && <p className="notice error" role="alert">{snapshotError}</p>}
          {snapshotMessage && <p className="notice success" role="status">{snapshotMessage}</p>}
          <button type="button" className="secondary-button" onClick={() => void handleCreateSnapshot()} disabled={snapshotSubmitting}>
            {snapshotSubmitting ? "Updating performance history..." : "Update performance history"}
          </button>
          <p className="field-hint">Saves today&apos;s portfolio value. Risk figures need about 30 days of history.</p>
        </section>
      </div>

      <section className="panel" style={{ padding: 20, maxWidth: 520 }}>
        <div className="section-header" style={{ marginBottom: 10 }}>
          <h2 className="section-title" style={{ fontSize: "1.2rem" }}>Add capital</h2>
        </div>
        <form onSubmit={handleCapitalAdd} style={{ display: "grid", gap: 12 }}>
          <label htmlFor="capital-amount" className="detail-label" style={{ display: "block" }}>
            Deposit amount (INR)
          </label>
          <input
            id="capital-amount"
            type="number"
            min="0.01"
            step="0.01"
            value={capitalAddAmount}
            onChange={(event) => setCapitalAddAmount(event.target.value)}
            className="text-input"
          />
          {capitalError && <p className="utility-text" style={{ color: "var(--danger)" }}>{capitalError}</p>}
          <button type="submit" className="primary-button" disabled={capitalSubmitting}>
            {capitalSubmitting ? "Adding capital..." : "Add capital"}
          </button>
        </form>
      </section>
    </main>
  );
}

export default function PortfolioDetailPage() {
  return (
    <Suspense fallback={<main className="page-shell"><div className="card list-card"><div className="skeleton skeleton-box" /></div></main>}>
      <PortfolioDetailView />
    </Suspense>
  );
}
