"use client";

import Link from "next/link";
import { useState } from "react";
import { ApiError, apiFetch, getAccessToken } from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import { formatCurrency } from "@/lib/format";
import type { RebalanceProposal, RebalanceProposalRequest } from "@/lib/types/api";

type Props = {
  portfolioId: string;
  recommendationId?: string;
};

// Shows the whole-share trades needed to reach a recommendation. Only creates a proposal;
// PortfolioPilot never executes it — the user buys at their broker and records the trade.
export function BuyList({ portfolioId, recommendationId }: Props) {
  const [proposal, setProposal] = useState<RebalanceProposal | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadBuyList() {
    setLoading(true);
    setError(null);
    try {
      const accessToken = await getAccessToken();
      if (!accessToken) throw new Error("You are signed out. Please log in again.");
      const request: RebalanceProposalRequest = { recommendation_id: recommendationId ?? null };
      setProposal(
        await apiFetch<RebalanceProposal>(`/portfolios/${portfolioId}/rebalance-proposals`, accessToken, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(request),
        }),
      );
    } catch (err) {
      if (err instanceof ApiError && (err.status === 409 || err.status === 503)) {
        setError(err.message);
      } else if (err instanceof Error && err.message.startsWith("You are")) {
        setError(err.message);
      } else {
        console.error("Failed to build buy list:", err);
        setError(getErrorMessage(err, "We couldn't build the buy list. Please try again."));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card" style={{ padding: 24 }} aria-labelledby="buy-list-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">Next: buy at your broker</span>
          <h2 className="section-title" id="buy-list-title">Buy list (estimate at current prices)</h2>
        </div>
        <button type="button" className="secondary-button" onClick={() => void loadBuyList()} disabled={loading}>
          {loading ? "Building buy list…" : proposal ? "Refresh buy list" : "Show buy list"}
        </button>
      </div>

      <p className="utility-text" style={{ marginBottom: 16 }}>
        Whole shares only, so a small amount stays in cash. Prices change; use your broker&apos;s actual price when recording.
      </p>

      {error && <div className="notice error" role="alert">{error}</div>}

      {proposal && proposal.trades.length === 0 && (
        <div className="notice success" role="status">Your holdings already match this recommendation.</div>
      )}

      {proposal && proposal.trades.length > 0 && (
        <div style={{ display: "grid", gap: 16 }}>
          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th scope="col">Stock</th>
                  <th scope="col">Side</th>
                  <th scope="col" className="numeric-cell">Whole shares</th>
                  <th scope="col" className="numeric-cell">Estimated price</th>
                  <th scope="col" className="numeric-cell">Estimated cost</th>
                  <th scope="col" className="numeric-cell">Estimated fee</th>
                  <th scope="col"><span className="visually-hidden">Record</span></th>
                </tr>
              </thead>
              <tbody>
                {proposal.trades.map((trade) => (
                  <tr key={`${trade.ticker}-${trade.side}`}>
                    <th scope="row">{trade.ticker}</th>
                    <td>{trade.side}</td>
                    <td className="numeric-cell">{trade.quantity}</td>
                    <td className="numeric-cell">{formatCurrency(trade.estimated_price)}</td>
                    <td className="numeric-cell">{formatCurrency(trade.estimated_gross_amount)}</td>
                    <td className="numeric-cell">{formatCurrency(trade.estimated_fee)}</td>
                    <td>
                      {trade.side === "BUY" && (
                        <Link
                          className="stock-analysis-trigger"
                          href={`/dashboard/portfolios/${portfolioId}?${new URLSearchParams({
                            ticker: trade.ticker,
                            qty: String(trade.quantity),
                            price: trade.estimated_price,
                          }).toString()}#record-trade`}
                        >
                          I bought this
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <dl className="buy-list-totals">
            <div><dt>Buy total</dt><dd>{formatCurrency(proposal.buy_total)}</dd></div>
            <div><dt>Estimated fees</dt><dd>{formatCurrency(proposal.estimated_fees)}</dd></div>
            <div><dt>Cash left after buying</dt><dd>{formatCurrency(proposal.projected_cash)}</dd></div>
          </dl>
          <p className="utility-text">{proposal.fee_assumption}</p>
        </div>
      )}
    </section>
  );
}
