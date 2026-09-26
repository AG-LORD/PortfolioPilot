"use client";

import { useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { apiFetch } from "@/lib/api";
import { formatDate, formatPercent } from "@/lib/format";

type EquityPoint = { date: string; total_value: string };
type Strategy = {
  model: string;
  model_version: string;
  cumulative_return: string;
  annualized_return: string | null;
  annualized_volatility: string | null;
  max_drawdown: string;
  sharpe_ratio: string | null;
  turnover: string;
  rebalance_count: number;
  daily_observation_count: number;
  equity_curve: EquityPoint[];
};

type BacktestResult = {
  settings: {
    start: string;
    end: string;
    rebalance_frequency: "daily" | "weekly" | "monthly";
    starting_capital: string;
    return_model: "historical" | "ml";
    max_position_weight: string;
    target_volatility: string;
    universe: string;
    universe_as_of: string | null;
    universe_revision: string;
    price_source: string;
  };
  selected_strategy: string;
  feature_version: string;
  evaluation_version: string;
  daily_risk_free_rate_assumption: string;
  fee_assumption: string;
  execution_assumption: string;
  scored_rows: number;
  effective_start: string;
  effective_end: string;
  excluded: Array<{ ticker: string; reason: string }>;
  strategies: Strategy[];
};

function EquityCurve({ strategies }: { strategies: Strategy[] }) {
  const width = 760;
  const height = 230;
  const values = strategies.flatMap((strategy) => strategy.equity_curve.map((point) => Number(point.total_value)));
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const range = maxValue - minValue || 1;
  const colors = ["#176b57", "#bf6237"];
  const pointsFor = (strategy: Strategy) => strategy.equity_curve.map((point, index) => {
    const x = 12 + (index / Math.max(strategy.equity_curve.length - 1, 1)) * (width - 24);
    const y = height - 16 - ((Number(point.total_value) - minValue) / range) * (height - 32);
    return `${x},${y}`;
  }).join(" ");

  return (
    <div className="backtest-chart-wrap">
      <svg className="backtest-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Simulated historical portfolio value for the compared strategies">
        {[16, height / 2, height - 16].map((y) => <line key={y} x1="10" x2={width - 10} y1={y} y2={y} stroke="#dfe7e2" strokeDasharray="4 5" />)}
        {strategies.map((strategy, index) => (
          <polyline
            key={strategy.model}
            points={pointsFor(strategy)}
            fill="none"
            stroke={colors[index % colors.length]}
            strokeWidth="2.5"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ))}
      </svg>
      <div className="backtest-legend">
        {strategies.map((strategy, index) => (
          <span key={strategy.model}><i style={{ background: colors[index % colors.length] }} />{strategy.model}</span>
        ))}
      </div>
    </div>
  );
}

export default function BacktestingPage() {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [startingCapital, setStartingCapital] = useState("100000");
  const [universe, setUniverse] = useState("NIFTY50");
  const [customTickers, setCustomTickers] = useState("");
  const [returnModel, setReturnModel] = useState<"historical" | "ml">("historical");
  const [frequency, setFrequency] = useState<"daily" | "weekly" | "monthly">("monthly");
  const [maxPositionWeight, setMaxPositionWeight] = useState("0.1");
  const [targetVolatility, setTargetVolatility] = useState("0.15");
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submitBacktest(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const { data: { session } } = await createClient().auth.getSession();
    if (!session) {
      setError("You are signed out. Please log in again.");
      return;
    }
    const request = {
      start,
      end,
      rebalance_frequency: frequency,
      starting_capital: startingCapital,
      universe: universe === "NIFTY50" ? "NIFTY50" : null,
      tickers: universe === "custom" ? customTickers.split(",").map((ticker) => ticker.trim()).filter(Boolean) : null,
      return_model: returnModel,
      max_position_weight: maxPositionWeight,
      target_volatility: targetVolatility,
    };

    try {
      setLoading(true);
      setError(null);
      setResult(await apiFetch<BacktestResult>("/backtests", session.access_token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      }));
    } catch (requestError) {
      console.error("Backtest failed:", requestError);
      setError(requestError instanceof Error ? requestError.message : "Backtest could not be completed.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page-shell">
      <header className="page-header">
        <div className="page-heading">
          <span className="eyebrow">Historical research</span>
          <h1 className="page-title">Backtesting</h1>
          <p className="page-subtitle">Simulated strategies using point-in-time forecasts and adjusted historical prices.</p>
        </div>
        <Link className="secondary-button" href="/dashboard">Back to dashboard</Link>
      </header>

      <form className="card list-card backtest-form" onSubmit={submitBacktest}>
        <div className="section-header">
          <div><h2 className="section-title">Simulation settings</h2><p className="utility-text">No live portfolio data is changed by a backtest.</p></div>
        </div>
        <div className="backtest-fields">
          <label className="field-group"><span className="field-label">Start date</span><input required type="date" value={start} onChange={(event) => setStart(event.target.value)} /></label>
          <label className="field-group"><span className="field-label">End date</span><input required type="date" value={end} onChange={(event) => setEnd(event.target.value)} /></label>
          <label className="field-group"><span className="field-label">Starting capital (INR)</span><input required type="number" min="0.01" step="0.01" value={startingCapital} onChange={(event) => setStartingCapital(event.target.value)} /></label>
          <label className="field-group"><span className="field-label">Universe</span><select value={universe} onChange={(event) => setUniverse(event.target.value)}><option value="NIFTY50">NIFTY 50</option><option value="custom">Custom tickers</option></select></label>
          {universe === "custom" && <label className="field-group backtest-custom-tickers"><span className="field-label">Tickers</span><input required value={customTickers} onChange={(event) => setCustomTickers(event.target.value)} placeholder="TCS, INFY, RELIANCE" /></label>}
          <label className="field-group"><span className="field-label">Return model</span><select value={returnModel} onChange={(event) => setReturnModel(event.target.value as "historical" | "ml")}><option value="historical">Historical baseline</option><option value="ml">ML forecast</option></select></label>
          <label className="field-group"><span className="field-label">Rebalance frequency</span><select value={frequency} onChange={(event) => setFrequency(event.target.value as "daily" | "weekly" | "monthly")}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></label>
          <label className="field-group"><span className="field-label">Maximum position weight</span><input required type="number" min="0.001" max="1" step="0.001" value={maxPositionWeight} onChange={(event) => setMaxPositionWeight(event.target.value)} /></label>
          <label className="field-group"><span className="field-label">Target volatility</span><input required type="number" min="0.001" step="0.001" value={targetVolatility} onChange={(event) => setTargetVolatility(event.target.value)} /></label>
        </div>
        {error && <p className="notice error" role="alert">{error}</p>}
        <button type="submit" className="primary-button" disabled={loading}>
          {loading ? "Running walk-forward simulation..." : "Run backtest"}
        </button>
      </form>

      {result && (
        <div className="backtest-results">
          <section className="card list-card backtest-result-panel">
            <div className="section-header">
              <div>
                <span className="eyebrow">Historical simulation · not live performance</span>
                <h2 className="section-title">{result.settings.universe} · {result.settings.return_model === "ml" ? "ML forecast" : "Historical baseline"}</h2>
                <p className="utility-text">Requested {formatDate(result.settings.start)} – {formatDate(result.settings.end)} · simulated {formatDate(result.effective_start)} – {formatDate(result.effective_end)}</p>
              </div>
              <span className="badge neutral">{result.scored_rows.toLocaleString()} out-of-sample forecasts</span>
            </div>
            <EquityCurve strategies={result.strategies} />
          </section>

          {result.strategies.map((strategy) => (
            <section className="card list-card backtest-result-panel" key={strategy.model}>
              <div className="section-header">
                <div><h2 className="section-title">{strategy.model}</h2><p className="utility-text">{strategy.model_version}</p></div>
                {strategy.model === result.selected_strategy && <span className="badge ml">Selected strategy</span>}
              </div>
              <div className="metric-grid">
                <article className="metric-card"><span className="metric-label">Cumulative return</span><strong className="metric-value">{formatPercent(strategy.cumulative_return)}</strong></article>
                <article className="metric-card"><span className="metric-label">Annualized return</span><strong className="metric-value">{strategy.annualized_return === null ? "—" : formatPercent(strategy.annualized_return)}</strong></article>
                <article className="metric-card"><span className="metric-label">Annualized volatility</span><strong className="metric-value">{strategy.annualized_volatility === null ? "—" : formatPercent(strategy.annualized_volatility)}</strong></article>
                <article className="metric-card"><span className="metric-label">Maximum drawdown</span><strong className="metric-value">{formatPercent(strategy.max_drawdown)}</strong></article>
                <article className="metric-card"><span className="metric-label">Sharpe ratio</span><strong className="metric-value">{strategy.sharpe_ratio ?? "—"}</strong></article>
                <article className="metric-card"><span className="metric-label">Turnover</span><strong className="metric-value">{formatPercent(strategy.turnover)}</strong></article>
                <article className="metric-card"><span className="metric-label">Rebalances</span><strong className="metric-value">{strategy.rebalance_count}</strong></article>
                <article className="metric-card"><span className="metric-label">Daily observations</span><strong className="metric-value">{strategy.daily_observation_count}</strong></article>
              </div>
            </section>
          ))}

          <section className="notice info backtest-assumptions">
            <div>
              <strong>Simulation assumptions</strong>
              <p>{result.settings.price_source}. {result.execution_assumption} {result.fee_assumption} Daily risk-free rate assumption: {result.daily_risk_free_rate_assumption}.</p>
              <p>Feature version {result.feature_version}; evaluation splits {result.evaluation_version}. This is a historical simulation and must not be read as realized or expected live portfolio performance.</p>
            </div>
          </section>
          {result.excluded.length > 0 && (
            <section className="card list-card backtest-result-panel">
              <h2 className="section-title">Excluded tickers</h2>
              <ul className="evaluation-exclusions">{result.excluded.map((item) => <li key={item.ticker}><strong>{item.ticker}</strong>: {item.reason}</li>)}</ul>
            </section>
          )}
        </div>
      )}
    </main>
  );
}