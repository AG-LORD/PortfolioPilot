"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { apiFetch } from "@/lib/api";
import { formatCurrency, formatDate, formatPercent } from "@/lib/format";
import type { Recommendation } from "@/lib/types/api";

type Props = { recommendation: Recommendation; requestedModel: "ml" | "historical" };

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

function StockCandlestickChart({ prices }: { prices: StockAnalysis["historical_prices"] }) {
  const candles = prices.slice(-90);
  const highest = Math.max(...candles.map((item) => Number(item.high)));
  const lowest = Math.min(...candles.map((item) => Number(item.low)));
  const range = highest - lowest || 1;
  const step = 720 / Math.max(candles.length, 1);
  const y = (value: string) => 12 + ((highest - Number(value)) / range) * 150;

  return (
    <svg className="stock-candlestick-chart" viewBox="0 0 740 180" role="img" aria-label={`${candles.length} most recent adjusted daily candlesticks`}>
      {[12, 87, 162].map((gridY) => <line key={gridY} x1="8" x2="732" y1={gridY} y2={gridY} stroke="#dfe7e2" strokeDasharray="3 5" />)}
      {candles.map((candle, index) => {
        const x = 10 + index * step + step / 2;
        const openY = y(candle.open);
        const closeY = y(candle.close);
        const rising = Number(candle.close) >= Number(candle.open);
        const color = rising ? "#26794e" : "#b4473b";
        return (
          <g key={candle.date}>
            <line x1={x} x2={x} y1={y(candle.high)} y2={y(candle.low)} stroke={color} strokeWidth="1.2" />
            <rect
              x={x - Math.max(1, step * 0.28)}
              y={Math.min(openY, closeY)}
              width={Math.max(2, step * 0.56)}
              height={Math.max(1.5, Math.abs(openY - closeY))}
              fill={rising ? color : "#fff"}
              stroke={color}
              strokeWidth="1.1"
            />
          </g>
        );
      })}
    </svg>
  );
}

export function RecommendationResult({ recommendation, requestedModel }: Props) {
  const hasMlFallbacks = requestedModel === "ml" && recommendation.allocations.some((allocation) => allocation.source === "historical");
  const [analysisTicker, setAnalysisTicker] = useState<string | null>(null);
  const [stockAnalysis, setStockAnalysis] = useState<StockAnalysis | null>(null);
  const [stockAnalysisLoading, setStockAnalysisLoading] = useState(false);
  const [stockAnalysisError, setStockAnalysisError] = useState<string | null>(null);

  async function openStockAnalysis(ticker: string) {
    setAnalysisTicker(ticker);
    setStockAnalysis(null);
    setStockAnalysisError(null);
    const { data: { session } } = await createClient().auth.getSession();
    if (!session) {
      setStockAnalysisError("You are signed out. Please log in again.");
      return;
    }

    const query = new URLSearchParams({ portfolio_id: recommendation.portfolio_id });
    if (recommendation.id) query.set("recommendation_id", recommendation.id);
    try {
      setStockAnalysisLoading(true);
      const details = await apiFetch<StockAnalysis>(
        `/stocks/${encodeURIComponent(ticker)}/analysis?${query.toString()}`,
        session.access_token,
      );
      setStockAnalysis(details);
    } catch (err) {
      console.error("Failed to load stock analysis:", err);
      setStockAnalysisError(err instanceof Error ? err.message : "Stock analysis is unavailable.");
    } finally {
      setStockAnalysisLoading(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: 24 }}>
      <section className="card" style={{ padding: 24 }}>
        <div className="summary-row" style={{ marginBottom: 20 }}>
          <div className="info-stack">
            <span className="eyebrow">Recommendation summary</span>
            <h2 className="section-title">What PortfolioPilot suggests</h2>
          </div>
          <span className="badge neutral">
            {requestedModel === "ml" ? "Machine Learning" : "Historical Baseline"}
          </span>
        </div>

        {hasMlFallbacks && (
          <div className="notice info" role="status" style={{ marginBottom: 20 }}>
            <span className="notice-icon">ℹ</span>
            <div>
              <strong>Machine Learning was requested.</strong>
              <p>Some stocks use the Historical Baseline because an ML forecast was unavailable for them.</p>
            </div>
          </div>
        )}

        <div className="metric-grid">
          <article className="metric-card">
            <span className="metric-label">Investment capital</span>
            <strong className="metric-value">{formatCurrency(recommendation.capital)}</strong>
          </article>
          <article className="metric-card">
            <span className="metric-label">Expected return</span>
            <strong className="metric-value">{formatPercent(recommendation.expected_portfolio_return)}</strong>
          </article>
          <article className="metric-card">
            <span className="metric-label">Expected volatility</span>
            <strong className="metric-value">{formatPercent(recommendation.expected_portfolio_volatility)}</strong>
          </article>
          <article className="metric-card">
            <span className="metric-label">Cash allocation</span>
            <strong className="metric-value">{formatPercent(recommendation.cash_weight)}</strong>
          </article>
        </div>

        <div className="detail-grid">
          <div className="detail-item">
            <span className="detail-label">Universe</span>
            <div className="detail-value">{recommendation.universe === "NIFTY50" ? "NIFTY 50" : recommendation.universe}</div>
          </div>
          <div className="detail-item">
            <span className="detail-label">As of</span>
            <div className="detail-value">{formatDate(recommendation.universe_as_of)}</div>
          </div>
          <div className="detail-item">
            <span className="detail-label">Return model</span>
            <div className="detail-value">{recommendation.return_model === "ml" ? "Machine Learning" : "Historical Baseline"}</div>
          </div>
          <div className="detail-item">
            <span className="detail-label">Actual source used</span>
            <div className="detail-value">{recommendation.return_model === "ml" ? "Machine Learning" : "Historical Baseline"}</div>
          </div>
          {recommendation.return_model === "ml" && (
            <>
              <div className="detail-item">
                <span className="detail-label">Model version</span>
                <div className="detail-value">{recommendation.model_version ?? "Not available"}</div>
              </div>
              <div className="detail-item">
                <span className="detail-label">Forecast date</span>
                <div className="detail-value">{formatDate(recommendation.forecast_as_of)}</div>
              </div>
            </>
          )}
        </div>
      </section>

      <section className="card" style={{ padding: 24 }}>
        <div className="section-header">
          <div>
            <span className="eyebrow">Portfolio allocation</span>
            <h2 className="section-title">Allocation</h2>
          </div>
        </div>

        <div className="notice info recommendation-method-note">
          <div>
            <strong>How this target is formed</strong>
            <p>Adjusted market history → point-in-time technical features → ML forecast or historical baseline → risk constraints → optimized target allocation.</p>
            <p>Expected returns and source are shown per allocation. Opening stock analysis shows the latest completed-session indicators, not reconstructed historical forecast features.</p>
          </div>
        </div>

        {recommendation.allocations.length === 0 ? (
          <div className="empty-state">
            <div>📊</div>
            <strong>No stock allocations were returned.</strong>
          </div>
        ) : (
          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th>Stock</th>
                  <th>Analysis</th>
                  <th className="numeric-cell">Expected return</th>
                  <th className="numeric-cell">Weight</th>
                  <th className="numeric-cell">₹ Amount</th>
                  <th>Source</th>
                  <th>At limit</th>
                </tr>
              </thead>
              <tbody>
                {recommendation.allocations.map((allocation) => (
                  <tr key={allocation.ticker}>
                    <th scope="row">{allocation.ticker}</th>
                    <td>
                      <button type="button" className="stock-analysis-trigger" onClick={() => void openStockAnalysis(allocation.ticker)}>
                        Analyze
                      </button>
                    </td>
                    <td className="numeric-cell">{formatPercent(allocation.expected_return)}</td>
                    <td className="numeric-cell">{formatPercent(allocation.target_weight)}</td>
                    <td className="numeric-cell">{formatCurrency(allocation.amount)}</td>
                    <td>
                      <span className={`badge ${allocation.source === "ml" ? "ml" : "historical"}`}>
                        {allocation.source === "ml" ? "Machine Learning" : "Historical Baseline"}
                      </span>
                    </td>
                    <td>
                      {allocation.at_position_limit ? (
                        <span className="badge limit">At limit</span>
                      ) : (
                        <span className="badge neutral">Open</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card" style={{ padding: 24 }}>
        <div className="section-header">
          <div>
            <span className="eyebrow">Cash position</span>
            <h2 className="section-title">Cash allocation</h2>
          </div>
        </div>
        <div className="detail-grid">
          <div className="detail-item">
            <span className="detail-label">Cash weight</span>
            <div className="detail-value">{formatPercent(recommendation.cash_weight)}</div>
          </div>
          <div className="detail-item">
            <span className="detail-label">Cash amount</span>
            <div className="detail-value">{formatCurrency(recommendation.cash_amount)}</div>
          </div>
        </div>
      </section>

      <section className="card" style={{ padding: 24 }}>
        <div className="section-header">
          <div>
            <span className="eyebrow">Excluded holdings</span>
            <h2 className="section-title">Excluded stocks</h2>
          </div>
        </div>

        {recommendation.excluded.length === 0 ? (
          <div className="empty-state">
            <div>✅</div>
            <strong>No stocks were excluded.</strong>
          </div>
        ) : (
          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th>Stock</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {recommendation.excluded.map((item) => (
                  <tr key={item.ticker}>
                    <td>{item.ticker}</td>
                    <td>{item.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="notice warning">
        <span className="notice-icon">⚠</span>
        <div>
          <strong>This is a recommendation only.</strong>
          <p>No trades were made and your holdings and cash are unchanged.</p>
        </div>
      </div>

      {analysisTicker && (
        <div className="stock-drawer-backdrop" role="presentation" onMouseDown={() => setAnalysisTicker(null)}>
          <aside
            className="stock-analysis-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="stock-analysis-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header className="stock-drawer-header">
              <div>
                <span className="eyebrow">Stock analysis</span>
                <h2 id="stock-analysis-title">{analysisTicker}</h2>
              </div>
              <button type="button" className="stock-drawer-close" aria-label="Close stock analysis" onClick={() => setAnalysisTicker(null)}>×</button>
            </header>
            {stockAnalysisLoading && <p className="utility-text">Loading adjusted price history and indicators...</p>}
            {stockAnalysisError && <div className="notice error" role="alert">{stockAnalysisError}</div>}
            {stockAnalysis && (
              <div className="stock-analysis-content">
                <div className="stock-analysis-summary">
                  <div><span>Current quote</span><strong>{stockAnalysis.current_price === null ? "Unavailable" : formatCurrency(stockAnalysis.current_price)}</strong></div>
                  <div><span>Latest adjusted close</span><strong>{formatCurrency(stockAnalysis.latest_close)}</strong><small>{formatDate(stockAnalysis.latest_close_date)}</small></div>
                </div>
                {!stockAnalysis.current_quote_available && <p className="notice warning">Current quote unavailable; historical analysis below uses adjusted daily history through the latest completed market date.</p>}
                {stockAnalysis.historical_prices.length > 0 ? (
                  <section className="stock-analysis-block">
                    <h3>Adjusted daily price · latest 90 sessions</h3>
                    <StockCandlestickChart prices={stockAnalysis.historical_prices} />
                  </section>
                ) : (
                  <p className="empty-state">No historical prices are available for this ticker.</p>
                )}
                <section className="stock-analysis-block">
                  <h3>Returns and volatility</h3>
                  <dl className="stock-analysis-metrics">
                    <div><dt>20-session return</dt><dd>{stockAnalysis.return_20d === null ? "—" : formatPercent(stockAnalysis.return_20d)}</dd></div>
                    <div><dt>60-session return</dt><dd>{stockAnalysis.return_60d === null ? "—" : formatPercent(stockAnalysis.return_60d)}</dd></div>
                    <div><dt>252-session return</dt><dd>{stockAnalysis.return_252d === null ? "—" : formatPercent(stockAnalysis.return_252d)}</dd></div>
                    <div><dt>Annualized volatility</dt><dd>{stockAnalysis.annualized_volatility_252d === null ? "—" : formatPercent(stockAnalysis.annualized_volatility_252d)}</dd></div>
                  </dl>
                </section>
                <section className="stock-analysis-block">
                  <h3>Technical indicators · latest close {formatDate(stockAnalysis.latest_close_date)}</h3>
                  <p className="utility-text">These values describe the latest available history; they are not the saved point-in-time features for an older recommendation.</p>
                  {Object.keys(stockAnalysis.technical_indicators).length === 0 ? (
                    <p className="utility-text">Not enough adjusted history to calculate indicators.</p>
                  ) : (
                    <dl className="stock-analysis-metrics">
                      {Object.entries(stockAnalysis.technical_indicators).map(([name, value]) => (
                        <div key={name}><dt>{name.replaceAll("_", " ")}</dt><dd>{Number(value).toFixed(4)}</dd></div>
                      ))}
                    </dl>
                  )}
                </section>
                <section className="stock-analysis-block">
                  <h3>Portfolio context</h3>
                  <dl className="stock-analysis-metrics">
                    <div><dt>Current portfolio weight</dt><dd>{stockAnalysis.current_weight === null ? "Unavailable" : formatPercent(stockAnalysis.current_weight)}</dd></div>
                    <div><dt>Saved target weight</dt><dd>{stockAnalysis.target_weight === null ? "Not in saved target" : formatPercent(stockAnalysis.target_weight)}</dd></div>
                    <div><dt>Saved expected return</dt><dd>{stockAnalysis.expected_return_annual === null ? "Not available" : formatPercent(stockAnalysis.expected_return_annual)}</dd></div>
                    <div><dt>Forecast source</dt><dd>{stockAnalysis.expected_return_source ?? "—"}</dd></div>
                    <div><dt>Model version</dt><dd>{stockAnalysis.model_version ?? "—"}</dd></div>
                  </dl>
                </section>
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
