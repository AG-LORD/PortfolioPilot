"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { apiFetch } from "@/lib/api";
import { formatCurrency, formatDate, formatPercent } from "@/lib/format";
import { getErrorMessage } from "@/lib/errors";
import type { PortfolioOverview, PortfolioOverviewItem } from "@/lib/types/api";

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function PortfolioValue({ portfolio }: { portfolio: PortfolioOverviewItem }) {
  // Value and P&L only when the backend could price every holding; otherwise show nothing.
  if (portfolio.valuation_status !== "ok" || portfolio.total_value === null) return null;
  const pnl = portfolio.unrealized_pnl;
  const pnlClass = pnl === null ? "" : Number(pnl) >= 0 ? "pnl-positive" : "pnl-negative";
  return (
    <div className="portfolio-meta" style={{ textAlign: "right" }}>
      <strong>{formatCurrency(portfolio.total_value)}</strong>
      {pnl !== null && (
        <small className={pnlClass}>
          P&amp;L {formatCurrency(pnl)}
          {portfolio.unrealized_pnl_pct !== null && ` (${formatPercent(portfolio.unrealized_pnl_pct, 1)})`}
        </small>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const [overview, setOverview] = useState<PortfolioOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const supabase = createClient();

    async function loadOverview(accessToken: string) {
      try {
        setOverview(await apiFetch<PortfolioOverview>("/portfolios/overview", accessToken));
      } catch (err) {
        console.error("Failed to load portfolios:", err);
        setError(getErrorMessage(err, "Unable to load your portfolios. Please try again."));
      }
    }

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        void loadOverview(session.access_token);
      } else {
        setError("No active session.");
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  if (error) {
    return (
      <main className="page-shell">
        <div className="notice error" role="alert">
          <span className="notice-icon">⚠</span>
          <div>
            <strong>Unable to load your portfolios</strong>
            <p>{error}</p>
          </div>
        </div>
      </main>
    );
  }

  if (!overview) {
    return (
      <main className="page-shell">
        <div className="page-header">
          <div className="page-heading">
            <span className="eyebrow">Portfolio dashboard</span>
            <h1 className="page-title">Your Portfolios</h1>
          </div>
        </div>
        <div className="card list-card">
          <div className="skeleton skeleton-box" />
        </div>
      </main>
    );
  }

  const { totals, portfolios } = overview;
  // The backend sums value only over portfolios it could price ("ok").
  const valuedCount = totals.valued_portfolio_count ?? 0;
  const hasValueTotal = valuedCount > 0 && totals.total_value !== null;

  return (
    <main className="page-shell">
      <header className="page-header">
        <div className="page-heading">
          <span className="eyebrow">Portfolio dashboard</span>
          <h1 className="page-title">Your Portfolios</h1>
        </div>
        <Link href="/dashboard/new-portfolio" className="primary-button">
          + Create Portfolio
        </Link>
      </header>

      <section className={`metric-grid ${hasValueTotal ? "" : "metric-grid-3"}`} aria-label="Portfolio summary">
        <article className="metric-card">
          <span className="metric-label">Portfolios</span>
          <strong className="metric-value">{totals.portfolio_count}</strong>
        </article>
        <article className="metric-card">
          <span className="metric-label">Capital deposited</span>
          <strong className="metric-value">{formatCurrency(totals.initial_capital)}</strong>
        </article>
        <article className="metric-card">
          <span className="metric-label">Cash</span>
          <strong className="metric-value">{formatCurrency(totals.cash_balance)}</strong>
        </article>
        {hasValueTotal && totals.total_value !== null && (
          <article className="metric-card">
            <span className="metric-label">
              {valuedCount < totals.portfolio_count ? `Value (${valuedCount} of ${totals.portfolio_count} portfolios)` : "Value"}
            </span>
            <strong className="metric-value">{formatCurrency(totals.total_value)}</strong>
          </article>
        )}
      </section>

      <section className="card list-card">
        <div className="section-header">
          <h2 className="section-title">Current portfolios</h2>
        </div>

        {portfolios.length === 0 ? (
          <div className="empty-state">
            <div>📊</div>
            <strong>No portfolios yet</strong>
            <p>Create your first portfolio to start generating recommendations.</p>
          </div>
        ) : (
          <div className="portfolio-list">
            {portfolios.map((portfolio) => (
              <Link key={portfolio.id} href={`/dashboard/portfolios/${portfolio.id}`} className="portfolio-list-item">
                <div className="portfolio-meta">
                  <strong>{portfolio.name}</strong>
                  <div className="portfolio-badges">
                    <span className="badge neutral">{capitalize(portfolio.risk_category)}</span>
                    <span className="badge neutral">
                      {portfolio.holdings_count} holding{portfolio.holdings_count === 1 ? "" : "s"}
                    </span>
                    <span className="badge neutral">Cash {formatCurrency(portfolio.cash_balance)}</span>
                  </div>
                  {portfolio.latest_recommendation && (
                    <small>Latest recommendation {formatDate(portfolio.latest_recommendation.created_at)}</small>
                  )}
                </div>
                <PortfolioValue portfolio={portfolio} />
              </Link>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
