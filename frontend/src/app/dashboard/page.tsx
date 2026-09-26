"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { apiFetch } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { getErrorMessage } from "@/lib/errors";

type Portfolio = {
  id: string;
  name: string;
  base_currency: string;
  initial_capital: string;
  cash_balance: string;
};

export default function DashboardPage() {
  const [portfolios, setPortfolios] = useState<Portfolio[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const supabase = createClient();

    async function loadPortfolios(accessToken: string) {
      try {
        const data = await apiFetch<Portfolio[]>("/portfolios", accessToken);
        setPortfolios(data);
      } catch (err) {
        console.error("Failed to load portfolios:", err);
        setError(getErrorMessage(err, "Unable to load your portfolios. Please try again."));
      }
    }

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        loadPortfolios(session.access_token);
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

  if (!portfolios) {
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

  return (
    <main className="page-shell">
      <header className="page-header">
        <div className="page-heading">
          <span className="eyebrow">Portfolio dashboard</span>
          <h1 className="page-title">Your Portfolios</h1>
        </div>
        <div className="summary-row">
          <Link href="/dashboard/model-evaluation" className="secondary-button">
            Model evaluation
          </Link>
          <Link href="/dashboard/backtesting" className="secondary-button">
            Backtesting
          </Link>
          <Link href="/dashboard/new-portfolio" className="primary-button">
            + Create Portfolio
          </Link>
        </div>
      </header>

      <section className="metric-grid" aria-label="Portfolio summary">
        <article className="metric-card">
          <span className="metric-label">Total portfolios</span>
          <strong className="metric-value">{portfolios.length}</strong>
        </article>
        <article className="metric-card">
          <span className="metric-label">Total capital</span>
          <strong className="metric-value">
            {formatCurrency(
              portfolios.reduce((sum, portfolio) => sum + Number(portfolio.initial_capital || 0), 0),
            )}
          </strong>
        </article>
        <article className="metric-card">
          <span className="metric-label">Cash held</span>
          <strong className="metric-value">
            {formatCurrency(
              portfolios.reduce((sum, portfolio) => sum + Number(portfolio.cash_balance || 0), 0),
            )}
          </strong>
        </article>
        <article className="metric-card">
          <span className="metric-label">Status</span>
          <strong className="metric-value">{portfolios.length > 0 ? "Active" : "Ready"}</strong>
        </article>
      </section>

      <section className="card list-card">
        <div className="section-header">
          <h2 className="section-title">Current portfolios</h2>
          <span className="badge neutral">{portfolios.length} portfolio{portfolios.length === 1 ? "" : "s"}</span>
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
              <Link
                key={portfolio.id}
                href={`/dashboard/portfolios/${portfolio.id}`}
                className="portfolio-list-item"
              >
                <div className="portfolio-meta">
                  <strong>{portfolio.name}</strong>
                  <small>
                    {portfolio.base_currency} · Initial capital {formatCurrency(portfolio.initial_capital)}
                  </small>
                </div>
                <div className="summary-row">
                  <span className="badge neutral">Cash {formatCurrency(portfolio.cash_balance)}</span>
                  <span className="utility-text">Open →</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
