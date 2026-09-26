"use client";

import { useState } from "react";
import { BuyList } from "@/components/recommendation/BuyList";
import { StockAnalysisDrawer } from "@/components/recommendation/StockAnalysisDrawer";
import { formatCurrency, formatDate, formatPercent } from "@/lib/format";
import type { Recommendation } from "@/lib/types/api";

type Props = {
  recommendation: Recommendation;
  // From GET /portfolios/overview; omitted from the explanation when unavailable.
  riskCategory?: string | null;
};

const RETURN_DISCLAIMER = "Model estimate from past market data. Not a guarantee or prediction of actual returns.";

// Percentages on the recommendation page use one decimal.
function pct(value: string) {
  return formatPercent(value, 1);
}

function SourceBadge({ source }: { source: "ml" | "historical" }) {
  return (
    <span className={`badge ${source === "ml" ? "ml" : "historical"}`}>
      {source === "ml" ? "ML forecast" : "Historical fallback"}
    </span>
  );
}

function LimitBadge({ atLimit }: { atLimit: boolean }) {
  return atLimit ? <span className="badge limit">At limit</span> : <span className="badge neutral">Open</span>;
}

const CLIPPED_TOOLTIP = "Estimate was capped to the model's historical range.";

function EstimateValue({ value, clipped }: { value: string; clipped?: boolean }) {
  return (
    <>
      {pct(value)}
      {clipped && (
        <span className="badge warning clipped-tag" title={CLIPPED_TOOLTIP} aria-label={`clipped: ${CLIPPED_TOOLTIP}`}>
          clipped
        </span>
      )}
    </>
  );
}

function ReturnLabel() {
  return (
    <>
      Estimated annual return<sup className="footnote-mark" title={RETURN_DISCLAIMER}>*</sup>
    </>
  );
}

export function RecommendationResult({ recommendation, riskCategory }: Props) {
  const usedHistoricalBaseline = recommendation.return_model === "historical";
  const hasMlFallbacks = !usedHistoricalBaseline && recommendation.allocations.some((allocation) => allocation.source === "historical");
  const [analysisTicker, setAnalysisTicker] = useState<string | null>(null);
  const analysisAllocation = recommendation.allocations.find((allocation) => allocation.ticker === analysisTicker);

  const stockCount = recommendation.allocations.length;
  const atCapCount = recommendation.allocations.filter((allocation) => allocation.at_position_limit).length;
  const showLimitColumn = atCapCount < stockCount;
  const columnCount = showLimitColumn ? 7 : 6;
  const categoryLabel = riskCategory ? `${riskCategory.charAt(0).toUpperCase()}${riskCategory.slice(1)} profile: ` : "Your profile: ";

  return (
    <div style={{ display: "grid", gap: 24 }}>
      <div className="notice info" role="note">
        <span className="notice-icon">ℹ</span>
        <div>
          <strong>Recommendation only — no trades were made.</strong>
          <p>Holdings and cash are unchanged.</p>
        </div>
      </div>

      <section className="card" style={{ padding: 24 }}>
        <p className="recommendation-explanation">
          {categoryLabel}max {pct(recommendation.constraints.max_position_weight)} per stock, target volatility{" "}
          {pct(recommendation.constraints.target_volatility)}. {atCapCount} of {stockCount} stocks reached the per-stock cap;{" "}
          {pct(recommendation.cash_weight)} stays in cash.
        </p>

        {usedHistoricalBaseline && (
          <div className="notice warning" role="status" style={{ marginBottom: 20 }}>
            <span className="notice-icon">ℹ</span>
            <div>
              <p>ML forecasts were unavailable, so the historical baseline was used.</p>
            </div>
          </div>
        )}

        {hasMlFallbacks && (
          <div className="notice info" role="status" style={{ marginBottom: 20 }}>
            <span className="notice-icon">ℹ</span>
            <div>
              <p>Some stocks use a historical fallback because an ML forecast was unavailable for them.</p>
            </div>
          </div>
        )}

        <div className="metric-grid metric-grid-3">
          <article className="metric-card">
            <span className="metric-label">Investment capital</span>
            <strong className="metric-value">{formatCurrency(recommendation.capital)}</strong>
          </article>
          <article className="metric-card">
            <span className="metric-label"><ReturnLabel /></span>
            <strong className="metric-value">{pct(recommendation.expected_portfolio_return)}</strong>
          </article>
          <article className="metric-card">
            <span className="metric-label">Expected volatility</span>
            <strong className="metric-value">{pct(recommendation.expected_portfolio_volatility)}</strong>
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
            <span className="detail-label">Method</span>
            <div className="detail-value">ML-assisted analysis</div>
          </div>
          <div className="detail-item">
            <span className="detail-label">Model version</span>
            <div className="detail-value">{recommendation.model_version ?? "—"}</div>
            {recommendation.forecast_as_of && (
              <p className="field-hint">
                Forecasts from {formatDate(recommendation.forecast_as_of)}
                {recommendation.forecast_source === "precomputed" && " (nightly model run)"}
                {recommendation.forecast_source === "on_request" && " (computed on request)"}
              </p>
            )}
          </div>
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
            <strong>How this was worked out</strong>
            <p>
              PortfolioPilot looks at each stock&apos;s recent price behaviour (trends, momentum, volatility), estimates its return with a
              machine-learning model, then splits your money so no stock exceeds your limit and total risk stays within your target. If
              the model has no estimate for a stock, its historical average return is used (marked &apos;Historical fallback&apos;).
            </p>
          </div>
        </div>

        {stockCount === 0 && (
          <div className="empty-state" style={{ marginBottom: 16 }}>
            <div>📊</div>
            <strong>No stock allocations were returned.</strong>
          </div>
        )}

        <div className="table-shell allocation-table">
          <table>
            <thead>
              <tr>
                <th>Stock</th>
                <th>Evidence</th>
                <th className="numeric-cell"><ReturnLabel /></th>
                <th className="numeric-cell">Weight</th>
                <th className="numeric-cell">₹ Amount</th>
                <th>Source</th>
                {showLimitColumn && <th>At limit</th>}
              </tr>
            </thead>
            <tbody>
              {recommendation.allocations.map((allocation) => (
                <tr key={allocation.ticker}>
                  <th scope="row">{allocation.ticker}</th>
                  <td>
                    <button type="button" className="stock-analysis-trigger" onClick={() => setAnalysisTicker(allocation.ticker)}>
                      Evidence
                    </button>
                  </td>
                  <td className="numeric-cell"><EstimateValue value={allocation.expected_return} clipped={allocation.clipped} /></td>
                  <td className="numeric-cell">{pct(allocation.target_weight)}</td>
                  <td className="numeric-cell">{formatCurrency(allocation.amount)}</td>
                  <td><SourceBadge source={allocation.source} /></td>
                  {showLimitColumn && <td><LimitBadge atLimit={allocation.at_position_limit} /></td>}
                </tr>
              ))}
              <tr className="allocation-cash-row">
                <th scope="row">Cash</th>
                <td />
                <td className="numeric-cell">—</td>
                <td className="numeric-cell">{pct(recommendation.cash_weight)}</td>
                <td className="numeric-cell">{formatCurrency(recommendation.cash_amount)}</td>
                <td colSpan={columnCount - 5} />
              </tr>
              <tr className="allocation-total-row">
                <th scope="row">Total</th>
                <td colSpan={3} />
                <td className="numeric-cell">{formatCurrency(recommendation.capital)}</td>
                <td colSpan={columnCount - 5} />
              </tr>
            </tbody>
          </table>
        </div>

        <ul className="allocation-cards" aria-label="Allocation">
          {recommendation.allocations.map((allocation) => (
            <li key={allocation.ticker} className="allocation-card">
              <div className="allocation-card-head">
                <strong>{allocation.ticker}</strong>
                <SourceBadge source={allocation.source} />
              </div>
              <div className="allocation-card-figures">
                <span>{pct(allocation.target_weight)}</span>
                <strong>{formatCurrency(allocation.amount)}</strong>
              </div>
              <dl className="allocation-card-details">
                <div><dt><ReturnLabel /></dt><dd><EstimateValue value={allocation.expected_return} clipped={allocation.clipped} /></dd></div>
                {showLimitColumn && <div><dt>At limit</dt><dd><LimitBadge atLimit={allocation.at_position_limit} /></dd></div>}
              </dl>
              <button type="button" className="stock-analysis-trigger" onClick={() => setAnalysisTicker(allocation.ticker)}>
                Evidence
              </button>
            </li>
          ))}
          <li className="allocation-card allocation-card-cash">
            <div className="allocation-card-head"><strong>Cash</strong></div>
            <div className="allocation-card-figures">
              <span>{pct(recommendation.cash_weight)}</span>
              <strong>{formatCurrency(recommendation.cash_amount)}</strong>
            </div>
          </li>
          <li className="allocation-card allocation-card-total">
            <div className="allocation-card-head"><strong>Total</strong></div>
            <div className="allocation-card-figures">
              <span />
              <strong>{formatCurrency(recommendation.capital)}</strong>
            </div>
          </li>
        </ul>

        <p className="footnote"><sup>*</sup> {RETURN_DISCLAIMER}</p>
      </section>

      <BuyList key={recommendation.id ?? "unsaved"} portfolioId={recommendation.portfolio_id} recommendationId={recommendation.id} />

      <section className="card" style={{ padding: 24 }}>
        <div className="section-header">
          <div>
            <span className="eyebrow">Excluded candidates</span>
            <h2 className="section-title">Excluded candidates</h2>
          </div>
        </div>

        {recommendation.excluded.length === 0 ? (
          <div className="empty-state">
            <div>✅</div>
            <strong>No candidates were excluded.</strong>
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

      {analysisTicker && (
        <StockAnalysisDrawer
          key={analysisTicker}
          ticker={analysisTicker}
          portfolioId={recommendation.portfolio_id}
          recommendationId={recommendation.id}
          drivers={analysisAllocation?.drivers}
          typicalEstimate={analysisAllocation?.typical_estimate ?? null}
          clipped={analysisAllocation?.clipped ?? false}
          onClose={() => setAnalysisTicker(null)}
        />
      )}
    </div>
  );
}
