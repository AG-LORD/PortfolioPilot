"use client";

import { useEffect, useState } from "react";
import { apiFetch, getAccessToken } from "@/lib/api";
import { formatCurrency, formatDate, formatPercent } from "@/lib/format";
import type { AllocationDriver } from "@/lib/types/api";

type StockAnalysis = {
  ticker: string;
  current_price: string | null;
  current_quote_available: boolean;
  latest_close: string;
  latest_close_date: string;
  historical_prices: Array<{
    date: string;
    open: string;
    high: string;
    low: string;
    close: string;
    volume: number;
  }>;
  technical_indicators: Record<string, string>;
  return_20d: string | null;
  return_60d: string | null;
  return_252d: string | null;
  annualized_volatility_252d: string | null;
  portfolio_id: string | null;
  recommendation_id: string | null;
  expected_return_annual: string | null;
  expected_return_source: "historical" | "ml" | null;
  model_version: string | null;
  target_weight: string | null;
  current_weight: string | null;
};

type IndicatorInfo = { label: string; definition: string; format: "percent" | "number" };

// Static labels and definitions for the backend's FEATURE_COLUMNS. No values are interpreted here.
const INDICATORS: Record<string, IndicatorInfo> = {
  close_to_sma_20: { label: "Price vs 20-day average", definition: "Price vs its 20-day average (0.05 = 5% above)", format: "percent" },
  close_to_sma_50: { label: "Price vs 50-day average", definition: "Price vs its 50-day average", format: "percent" },
  sma_20_to_sma_50: {
    label: "20-day vs 50-day average",
    definition: "Short-term trend vs medium-term trend (positive = short-term trend is stronger)",
    format: "percent",
  },
  momentum_5: { label: "5-day momentum", definition: "Price change over the last 5 trading days", format: "percent" },
  momentum_20: { label: "20-day momentum", definition: "Price change over the last 20 trading days", format: "percent" },
  momentum_60: { label: "60-day momentum", definition: "Price change over the last 60 trading days", format: "percent" },
  rsi_14: {
    label: "RSI (14)",
    definition: "Relative Strength Index, 0–100; above 70 often means strong recent buying, below 30 strong selling",
    format: "number",
  },
  macd_line: { label: "MACD line", definition: "MACD: gap between 12- and 26-day trends, relative to price", format: "percent" },
  macd_signal: { label: "MACD signal", definition: "9-day average of the MACD line", format: "percent" },
  macd_hist: { label: "MACD histogram", definition: "MACD minus its signal (positive = momentum rising)", format: "percent" },
  atr_14: {
    label: "ATR (14)",
    definition: "Average daily price range over 14 days, relative to price (higher = more volatile)",
    format: "percent",
  },
  realized_vol_20: { label: "20-day volatility", definition: "Annualized volatility of the last 20 days of returns", format: "percent" },
};

const UNKNOWN_INDICATOR_DEFINITION = "Technical input used by the model.";

function formatIndicator(name: string, value: string): string {
  const info = INDICATORS[name];
  if (!info) return Number(value).toFixed(4);
  return info.format === "percent" ? formatPercent(value, 1) : Number(value).toFixed(1);
}

function percentOrDash(value: string | null, fallback = "—") {
  return value === null ? fallback : formatPercent(value, 1);
}

const TOP_DRIVERS = 5;

function signedPercent(value: string) {
  return `${Number(value) > 0 ? "+" : ""}${formatPercent(value, 1)}`;
}

function WhyThisEstimate({
  drivers,
  typicalEstimate,
  clipped,
}: {
  drivers: AllocationDriver[];
  typicalEstimate: string | null;
  clipped: boolean;
}) {
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? drivers : drivers.slice(0, TOP_DRIVERS);
  // Bar length is only a visual scale against the largest contribution shown.
  const largest = Math.max(...shown.map((d) => Math.abs(Number(d.contribution))), 0) || 1;

  return (
    <section className="stock-analysis-block">
      <h3>Why this estimate</h3>
      {typicalEstimate !== null && (
        <p className="utility-text">A stock with typical inputs would be estimated at {formatPercent(typicalEstimate, 1)}.</p>
      )}
      {clipped && (
        <p className="utility-text">The estimate was capped; the contributions explain the model&apos;s raw estimate before capping.</p>
      )}
      <ul className="driver-list">
        {shown.map((driver) => {
          const contribution = Number(driver.contribution);
          const direction = contribution > 0 ? "positive" : contribution < 0 ? "negative" : "zero";
          return (
            <li key={driver.feature} className="driver-row">
              <span className="driver-label">{INDICATORS[driver.feature]?.label ?? driver.feature.replaceAll("_", " ")}</span>
              <span className="driver-value">{formatIndicator(driver.feature, driver.value)}</span>
              <span className={`driver-contribution ${direction}`}>{signedPercent(driver.contribution)}</span>
              <span className="driver-bar-track" aria-hidden="true">
                <span
                  className={`driver-bar ${direction}`}
                  style={{ width: `${(Math.abs(contribution) / largest) * 50}%` }}
                />
              </span>
            </li>
          );
        })}
      </ul>
      {drivers.length > TOP_DRIVERS && (
        <button type="button" className="next-step-link driver-toggle" onClick={() => setShowAll((value) => !value)}>
          {showAll ? `Show top ${TOP_DRIVERS}` : `Show all ${drivers.length}`}
        </button>
      )}
    </section>
  );
}

type Props = {
  ticker: string;
  portfolioId: string;
  recommendationId?: string;
  // From the recommendation response; the drawer never refetches them.
  drivers?: AllocationDriver[];
  typicalEstimate?: string | null;
  clipped?: boolean;
  onClose: () => void;
};

function StockCandlestickChart({ prices }: { prices: StockAnalysis["historical_prices"] }) {
  const candles = prices.slice(-90);
  const highest = Math.max(...candles.map((item) => Number(item.high)));
  const lowest = Math.min(...candles.map((item) => Number(item.low)));
  const range = highest - lowest || 1;
  const step = 720 / Math.max(candles.length, 1);
  const y = (value: string) => 12 + ((highest - Number(value)) / range) * 150;

  return (
    <svg className="stock-candlestick-chart" viewBox="0 0 740 180" role="img" aria-label={`${candles.length} most recent adjusted daily candlesticks`}>
      {[12, 87, 162].map((gridY) => <line key={gridY} x1="8" x2="732" y1={gridY} y2={gridY} style={{ stroke: "var(--border)" }} strokeDasharray="3 5" />)}
      {candles.map((candle, index) => {
        const x = 10 + index * step + step / 2;
        const openY = y(candle.open);
        const closeY = y(candle.close);
        const rising = Number(candle.close) >= Number(candle.open);
        const color = rising ? "var(--success)" : "var(--danger)";
        return (
          <g key={candle.date}>
            <line x1={x} x2={x} y1={y(candle.high)} y2={y(candle.low)} style={{ stroke: color }} strokeWidth="1.2" />
            <rect
              x={x - Math.max(1, step * 0.28)}
              y={Math.min(openY, closeY)}
              width={Math.max(2, step * 0.56)}
              height={Math.max(1.5, Math.abs(openY - closeY))}
              style={{ fill: rising ? color : "var(--surface)", stroke: color }}
              strokeWidth="1.1"
            />
          </g>
        );
      })}
    </svg>
  );
}

export function StockAnalysisDrawer({ ticker, portfolioId, recommendationId, drivers = [], typicalEstimate = null, clipped = false, onClose }: Props) {
  const hasDrivers = drivers.length > 0;
  const [stockAnalysis, setStockAnalysis] = useState<StockAnalysis | null>(null);
  const [stockAnalysisLoading, setStockAnalysisLoading] = useState(false);
  const [stockAnalysisError, setStockAnalysisError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const accessToken = await getAccessToken();
      if (cancelled) return;
      if (!accessToken) {
        setStockAnalysisError("You are signed out. Please log in again.");
        return;
      }

      const query = new URLSearchParams({ portfolio_id: portfolioId });
      if (recommendationId) query.set("recommendation_id", recommendationId);
      try {
        setStockAnalysisLoading(true);
        const details = await apiFetch<StockAnalysis>(
          `/stocks/${encodeURIComponent(ticker)}/analysis?${query.toString()}`,
          accessToken,
        );
        if (!cancelled) setStockAnalysis(details);
      } catch (err) {
        console.error("Failed to load stock analysis:", err);
        if (!cancelled) setStockAnalysisError(err instanceof Error ? err.message : "Stock analysis is unavailable.");
      } finally {
        if (!cancelled) setStockAnalysisLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [ticker, portfolioId, recommendationId]);

  return (
    <div className="stock-drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        className="stock-analysis-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="stock-analysis-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="stock-drawer-header">
          <div>
            <span className="eyebrow">Evidence</span>
            <h2 id="stock-analysis-title">{ticker} — evidence</h2>
          </div>
          <button type="button" className="stock-drawer-close" aria-label="Close evidence" onClick={onClose}>×</button>
        </header>
        {stockAnalysisLoading && <p className="utility-text">Loading adjusted price history and indicators...</p>}
        {stockAnalysisError && <div className="notice error" role="alert">{stockAnalysisError}</div>}
        {stockAnalysis && (
          <div className="stock-analysis-content">
            <div className="stock-analysis-summary">
              <div><span>Current quote</span><strong>{stockAnalysis.current_price === null ? "Unavailable" : formatCurrency(stockAnalysis.current_price)}</strong></div>
              <div><span>Latest adjusted close</span><strong>{formatCurrency(stockAnalysis.latest_close)}</strong><small>{formatDate(stockAnalysis.latest_close_date)}</small></div>
            </div>
            {!stockAnalysis.current_quote_available && <p className="notice warning">Current quote unavailable; the evidence below uses adjusted daily history through the latest completed market date.</p>}
            <p className="notice info">
              {hasDrivers
                ? "Contributions are approximate: each shows how the estimate changes if that input were typical. They explain the model, not the market."
                : "These are the inputs the model uses. The model does not yet report how much each input contributed to this estimate."}
            </p>
            <section className="stock-analysis-block">
              <h3>Model estimate</h3>
              <dl className="stock-analysis-metrics">
                <div><dt>Estimated annual return</dt><dd>{percentOrDash(stockAnalysis.expected_return_annual, "Not available")}</dd></div>
                <div>
                  <dt>Source</dt>
                  <dd>{stockAnalysis.expected_return_source === null ? "—" : stockAnalysis.expected_return_source === "ml" ? "ML forecast" : "Historical fallback"}</dd>
                </div>
                <div><dt>Model version</dt><dd>{stockAnalysis.model_version ?? "—"}</dd></div>
                <div><dt>Target weight</dt><dd>{percentOrDash(stockAnalysis.target_weight, "Not in this recommendation")}</dd></div>
                {stockAnalysis.current_weight !== null && (
                  <div><dt>Current weight in your portfolio</dt><dd>{percentOrDash(stockAnalysis.current_weight)}</dd></div>
                )}
              </dl>
              <p className="utility-text">Model estimate from past market data. Not a guarantee or prediction of actual returns.</p>
            </section>
            {hasDrivers && <WhyThisEstimate drivers={drivers} typicalEstimate={typicalEstimate} clipped={clipped} />}
            <section className="stock-analysis-block">
              <h3>Recent performance</h3>
              <dl className="stock-analysis-metrics">
                <div><dt>20-session return</dt><dd>{percentOrDash(stockAnalysis.return_20d)}</dd></div>
                <div><dt>60-session return</dt><dd>{percentOrDash(stockAnalysis.return_60d)}</dd></div>
                <div><dt>252-session return</dt><dd>{percentOrDash(stockAnalysis.return_252d)}</dd></div>
                <div><dt>Annualized volatility</dt><dd>{percentOrDash(stockAnalysis.annualized_volatility_252d)}</dd></div>
              </dl>
            </section>
            <section className="stock-analysis-block">
              <h3>Model inputs (technical indicators) · latest close {formatDate(stockAnalysis.latest_close_date)}</h3>
              <p className="utility-text">These values describe the latest available history; they are not the saved point-in-time inputs for an older recommendation.</p>
              {Object.keys(stockAnalysis.technical_indicators).length === 0 ? (
                <p className="utility-text">Not enough adjusted history to calculate indicators.</p>
              ) : (
                <dl className="indicator-list">
                  {Object.entries(stockAnalysis.technical_indicators).map(([name, value]) => (
                    <div key={name}>
                      <dt>{INDICATORS[name]?.label ?? name.replaceAll("_", " ")}</dt>
                      <dd>{formatIndicator(name, value)}</dd>
                      <p>{INDICATORS[name]?.definition ?? UNKNOWN_INDICATOR_DEFINITION}</p>
                    </div>
                  ))}
                </dl>
              )}
            </section>
            {stockAnalysis.historical_prices.length > 0 ? (
              <section className="stock-analysis-block">
                <h3>Adjusted daily price · latest 90 sessions</h3>
                <StockCandlestickChart prices={stockAnalysis.historical_prices} />
              </section>
            ) : (
              <p className="empty-state">No historical prices are available for this ticker.</p>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
