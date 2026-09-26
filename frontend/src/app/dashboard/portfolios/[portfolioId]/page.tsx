"use client";

import { useEffect, useEffectEvent, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { apiFetch } from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import { formatCurrency, formatDate, formatPercent } from "@/lib/format";

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

type DriftPosition = {
  ticker: string;
  quantity: string | null;
  current_price: string | null;
  current_value: string | null;
  current_weight: string | null;
  target_weight: string | null;
  weight_difference: string | null;
  status: "no_target" | "unavailable" | "overweight" | "underweight" | "at_target";
  excluded: boolean;
  exclusion_reason: string | null;
  requires_attention: boolean;
};

type PortfolioDrift = {
  portfolio_id: string;
  portfolio_value: string | null;
  valuation_complete: boolean;
  missing_prices: string[];
  target_recommendation_id: string | null;
  target_created_at: string | null;
  target_status: "missing" | "current" | "stale";
  drift_threshold: string;
  attention_count: number;
  positions: DriftPosition[];
};

type RebalanceTrade = {
  ticker: string;
  side: "BUY" | "SELL";
  quantity: number;
  estimated_price: string;
  estimated_gross_amount: string;
  estimated_fee: string;
  estimated_net_amount: string;
  current_weight: string;
  target_weight: string;
  resulting_weight: string;
};

type RebalanceWeight = {
  ticker: string;
  current_weight: string;
  target_weight: string;
  resulting_weight: string;
};

type RebalanceProposal = {
  id: string;
  portfolio_id: string;
  recommendation_id: string;
  created_at: string;
  status: "PENDING" | "EXECUTED" | "EXPIRED";
  portfolio_value: string;
  cash_before: string;
  projected_cash: string;
  buy_total: string;
  sell_total: string;
  estimated_fees: string;
  fee_assumption: string;
  trades: RebalanceTrade[];
  resulting_weights: RebalanceWeight[];
};

type RebalanceExecution = {
  proposal_id: string;
  status: "EXECUTED";
  transaction_ids: string[];
  cash_balance: string;
};

export default function PortfolioDetailPage() {
  const { portfolioId } = useParams<{ portfolioId: string }>();

  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [holdings, setHoldings] = useState<Holding[] | null>(null);
  const [transactions, setTransactions] = useState<Transaction[] | null>(null);
  const [valuation, setValuation] = useState<PortfolioValuation | null>(null);
  const [riskAnalytics, setRiskAnalytics] = useState<RiskAnalytics | null>(null);
  const [drift, setDrift] = useState<PortfolioDrift | null>(null);
  const [rebalanceProposal, setRebalanceProposal] = useState<RebalanceProposal | null>(null);
  const [rebalanceLoading, setRebalanceLoading] = useState(false);
  const [rebalanceError, setRebalanceError] = useState<string | null>(null);
  const [rebalanceConfirmed, setRebalanceConfirmed] = useState(false);
  const [rebalanceExecuting, setRebalanceExecuting] = useState(false);
  const [rebalanceExecution, setRebalanceExecution] = useState<RebalanceExecution | null>(null);
  const [capitalAddAmount, setCapitalAddAmount] = useState("10000");
  const [capitalSubmitting, setCapitalSubmitting] = useState(false);
  const [capitalError, setCapitalError] = useState<string | null>(null);
  const [tradeType, setTradeType] = useState<"BUY" | "SELL">("BUY");
  const [tradeTicker, setTradeTicker] = useState("");
  const [tradeQuantity, setTradeQuantity] = useState("");
  const [tradePrice, setTradePrice] = useState("");
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
  const [driftError, setDriftError] = useState<string | null>(null);

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
      setDrift(await apiFetch<PortfolioDrift>(`/portfolios/${portfolioId}/drift`, accessToken));
    } catch (err) {
      console.error("Failed to load portfolio drift:", err);
      setDriftError(getErrorMessage(err, "Portfolio drift is currently unavailable."));
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

  async function handleCapitalAdd(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const amount = Number(capitalAddAmount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setCapitalError("Enter a valid amount greater than zero.");
      return;
    }

    const { data: { session } } = await createClient().auth.getSession();
    if (!session) {
      setCapitalError("You are signed out. Please log in again.");
      return;
    }

    try {
      setCapitalSubmitting(true);
      setCapitalError(null);
      const updated = await apiFetch<Portfolio>(`/portfolios/${portfolioId}/capital`, session.access_token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount: amount.toString() }),
      });
      setPortfolio(updated);
      await loadAll(session.access_token);
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

    const { data: { session } } = await createClient().auth.getSession();
    if (!session) {
      setTradeError("You are signed out. Please log in again.");
      return;
    }

    try {
      setTradeSubmitting(true);
      setTradeError(null);
      await apiFetch<Transaction>(`/portfolios/${portfolioId}/transactions`, session.access_token, {
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
      await loadAll(session.access_token);
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
    const { data: { session } } = await createClient().auth.getSession();
    if (!session) {
      setSnapshotError("You are signed out. Please log in again.");
      return;
    }

    try {
      setSnapshotSubmitting(true);
      setSnapshotError(null);
      setSnapshotMessage(null);
      await apiFetch<unknown>(`/portfolios/${portfolioId}/snapshots`, session.access_token, {
        method: "POST",
      });
      setRiskAnalytics(await apiFetch<RiskAnalytics>(`/portfolios/${portfolioId}/risk`, session.access_token));
      setSnapshotMessage("Portfolio snapshot recorded and risk analytics refreshed.");
    } catch (err) {
      console.error("Failed to record portfolio snapshot:", err);
      setSnapshotError(err instanceof Error ? err.message : "Unable to record a snapshot.");
    } finally {
      setSnapshotSubmitting(false);
    }
  }

  async function handleReviewRebalancing() {
    const { data: { session } } = await createClient().auth.getSession();
    if (!session) {
      setRebalanceError("You are signed out. Please log in again.");
      return;
    }

    try {
      setRebalanceLoading(true);
      setRebalanceError(null);
      const proposal = await apiFetch<RebalanceProposal>(
        `/portfolios/${portfolioId}/rebalance-proposals`,
        session.access_token,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        },
      );
      setRebalanceProposal(proposal);
      setRebalanceConfirmed(false);
      setRebalanceExecution(null);
    } catch (err) {
      console.error("Failed to create rebalance proposal:", err);
      setRebalanceError(err instanceof Error ? err.message : "Unable to prepare a rebalance proposal.");
    } finally {
      setRebalanceLoading(false);
    }
  }

  async function handleExecuteRebalance() {
    if (!rebalanceProposal || !rebalanceConfirmed) return;
    const { data: { session } } = await createClient().auth.getSession();
    if (!session) {
      setRebalanceError("You are signed out. Please log in again.");
      return;
    }

    try {
      setRebalanceExecuting(true);
      setRebalanceError(null);
      const result = await apiFetch<RebalanceExecution>(
        `/portfolios/${portfolioId}/rebalance-proposals/${rebalanceProposal.id}/execute`,
        session.access_token,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ confirm: true }),
        },
      );
      setRebalanceExecution(result);
      setRebalanceProposal({ ...rebalanceProposal, status: "EXECUTED" });
      setRebalanceConfirmed(false);
      await loadAll(session.access_token);
    } catch (err) {
      console.error("Failed to execute rebalance proposal:", err);
      setRebalanceError(err instanceof Error ? err.message : "Unable to execute this proposal.");
    } finally {
      setRebalanceExecuting(false);
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
      <header className="page-header">
        <div className="page-heading">
          <span className="eyebrow">Current portfolio</span>
          <h1 className="page-title">{portfolio.name}</h1>
          <p className="page-subtitle">What you own today</p>
        </div>
        <Link href={`/dashboard/portfolios/${portfolioId}/recommendation`} className="primary-button">
          View recommended portfolio
        </Link>
      </header>

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

      <section className="card list-card drift-section" aria-labelledby="drift-title">
        <div className="section-header">
          <div>
            <h2 className="section-title" id="drift-title">Portfolio drift</h2>
            <p className="utility-text">Current weights compared with the latest saved recommendation.</p>
          </div>
          {drift && (
            <span className={`badge ${drift.target_status === "stale" ? "warning" : "neutral"}`}>
              {drift.target_status === "missing" ? "No target" : drift.target_status === "stale" ? "Target is stale" : "Target current"}
            </span>
          )}
        </div>

        {driftError && <p className="utility-text" role="alert">{driftError}</p>}
        {!driftError && drift === null && <p className="utility-text">Loading portfolio drift...</p>}
        {drift && drift.target_status === "missing" && (
          <p className="empty-state">Generate a recommendation to compare your current portfolio with a target allocation.</p>
        )}
        {drift && drift.target_status === "stale" && (
          <p className="notice warning" role="status">
            Portfolio state changed after this target was generated on {formatDate(drift.target_created_at)}. Generate a new recommendation before relying on this comparison.
          </p>
        )}
        {drift && !drift.valuation_complete && (
          <p className="notice warning" role="status">
            Current weights are unavailable because prices could not be loaded for: {drift.missing_prices.join(", ")}.
          </p>
        )}
        {drift && drift.target_status !== "missing" && (
          <>
            <div className="summary-row drift-summary">
              <span>Portfolio value {drift.portfolio_value ? formatCurrency(drift.portfolio_value, portfolio.base_currency) : "unavailable"}</span>
              <span>Assets needing attention {drift.attention_count}</span>
              <span>Drift threshold {formatPercent(drift.drift_threshold)}</span>
            </div>
            <div className="table-shell">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Asset</th>
                    <th scope="col" className="numeric-cell">Current</th>
                    <th scope="col" className="numeric-cell">Target</th>
                    <th scope="col" className="numeric-cell">Difference</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {drift.positions.map((position) => (
                    <tr key={position.ticker}>
                      <th scope="row">
                        {position.ticker}
                        {position.excluded && <small className="drift-exclusion">Excluded: {position.exclusion_reason}</small>}
                      </th>
                      <td className="numeric-cell">{position.current_weight === null ? "Unavailable" : formatPercent(position.current_weight)}</td>
                      <td className="numeric-cell">{position.target_weight === null ? "—" : formatPercent(position.target_weight)}</td>
                      <td className="numeric-cell">{position.weight_difference === null ? "—" : formatPercent(position.weight_difference)}</td>
                      <td><span className={`drift-status drift-${position.status}`}>{position.status.replaceAll("_", " ")}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <section className="card list-card rebalance-section" aria-labelledby="rebalance-title">
        <div className="section-header">
          <div>
            <h2 className="section-title" id="rebalance-title">Rebalancing proposal</h2>
            <p className="utility-text">Review whole-share trades against the latest saved target.</p>
          </div>
          <button
            type="button"
            className="secondary-button"
            onClick={() => void handleReviewRebalancing()}
            disabled={rebalanceLoading}
          >
            {rebalanceLoading ? "Preparing proposal..." : "Review Rebalancing"}
          </button>
        </div>
        {rebalanceError && <p className="notice error" role="alert">{rebalanceError}</p>}
        {rebalanceExecution && (
          <p className="notice success" role="status">
            Rebalancing completed. {rebalanceExecution.transaction_ids.length} transaction(s) were recorded.
          </p>
        )}
        {rebalanceProposal && (
          <>
            {rebalanceProposal.status === "PENDING" && (
              <p className="notice neutral" role="status">No trades have been executed. Review the proposal before confirming any trades.</p>
            )}
            <div className="summary-row drift-summary">
              <span>Cash before {formatCurrency(rebalanceProposal.cash_before, portfolio.base_currency)}</span>
              <span>Projected cash {formatCurrency(rebalanceProposal.projected_cash, portfolio.base_currency)}</span>
              <span>Buy total {formatCurrency(rebalanceProposal.buy_total, portfolio.base_currency)}</span>
              <span>Sell total {formatCurrency(rebalanceProposal.sell_total, portfolio.base_currency)}</span>
              <span>Estimated fees {formatCurrency(rebalanceProposal.estimated_fees, portfolio.base_currency)}</span>
            </div>
            <p className="utility-text rebalance-fee-note">{rebalanceProposal.fee_assumption}</p>
            {rebalanceProposal.trades.length === 0 ? (
              <div className="empty-state">No whole-share trades are proposed for this portfolio state.</div>
            ) : (
              <div className="table-shell">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Side</th>
                      <th scope="col">Asset</th>
                      <th scope="col" className="numeric-cell">Shares</th>
                      <th scope="col" className="numeric-cell">Price</th>
                      <th scope="col" className="numeric-cell">Gross</th>
                      <th scope="col" className="numeric-cell">Fee</th>
                      <th scope="col" className="numeric-cell">Net</th>
                      <th scope="col" className="numeric-cell">Resulting weight</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rebalanceProposal.trades.map((trade) => (
                      <tr key={`${trade.ticker}-${trade.side}`}>
                        <td>{trade.side}</td>
                        <th scope="row">{trade.ticker}</th>
                        <td className="numeric-cell">{trade.quantity}</td>
                        <td className="numeric-cell">{formatCurrency(trade.estimated_price, portfolio.base_currency)}</td>
                        <td className="numeric-cell">{formatCurrency(trade.estimated_gross_amount, portfolio.base_currency)}</td>
                        <td className="numeric-cell">{formatCurrency(trade.estimated_fee, portfolio.base_currency)}</td>
                        <td className="numeric-cell">{formatCurrency(trade.estimated_net_amount, portfolio.base_currency)}</td>
                        <td className="numeric-cell">{formatPercent(trade.resulting_weight)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="rebalance-resulting">
              <h3 className="section-title">Resulting allocation estimate</h3>
              <div className="summary-row">
                {rebalanceProposal.resulting_weights.map((weight) => (
                  <span key={weight.ticker}>
                    {weight.ticker}: {formatPercent(weight.resulting_weight)}
                  </span>
                ))}
              </div>
            </div>
            {rebalanceProposal.status === "PENDING" && rebalanceProposal.trades.length > 0 && (
              <div className="rebalance-confirmation">
                <label className="rebalance-confirm-label">
                  <input
                    type="checkbox"
                    checked={rebalanceConfirmed}
                    onChange={(event) => setRebalanceConfirmed(event.target.checked)}
                  />
                  I reviewed these trades and explicitly confirm execution.
                </label>
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => void handleExecuteRebalance()}
                  disabled={!rebalanceConfirmed || rebalanceExecuting}
                >
                  {rebalanceExecuting ? "Executing trades..." : "Execute confirmed trades"}
                </button>
              </div>
            )}
          </>
        )}
      </section>

      <div className="detail-grid" style={{ marginBottom: 24 }}>
        <div className="panel" style={{ padding: 20 }}>
          <div className="section-header" style={{ marginBottom: 10 }}>
            <h2 className="section-title" style={{ fontSize: "1.2rem" }}>Portfolio overview</h2>
          </div>
          <div className="info-stack">
            <div className="detail-item">
              <span className="detail-label">Purpose</span>
              <div className="detail-value">{portfolio.purpose ?? "—"}</div>
            </div>
            <div className="detail-item">
              <span className="detail-label">Base currency</span>
              <div className="detail-value">{portfolio.base_currency}</div>
            </div>
          </div>
        </div>

        <div className="panel" style={{ padding: 20 }}>
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
            {capitalError && <p className="utility-text" style={{ color: "#c33131" }}>{capitalError}</p>}
            <button type="submit" className="primary-button" disabled={capitalSubmitting}>
              {capitalSubmitting ? "Adding capital..." : "Add capital"}
            </button>
          </form>
        </div>

        <div className="panel" style={{ padding: 20 }}>
          <div className="section-header" style={{ marginBottom: 10 }}>
            <h2 className="section-title" style={{ fontSize: "1.2rem" }}>Record a trade</h2>
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
        </div>

        <div className="panel" style={{ padding: 20 }}>
          <div className="section-header" style={{ marginBottom: 10 }}>
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
            {snapshotSubmitting ? "Recording snapshot..." : "Record valuation snapshot"}
          </button>
        </div>
      </div>

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
    </main>
  );
}
