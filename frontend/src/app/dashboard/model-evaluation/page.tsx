"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { apiFetch } from "@/lib/api";
import { formatDate, formatPercent } from "@/lib/format";

type EvaluationMetric = {
  model: string;
  mae: string;
  hit_rate: string;
  mean_ic: string;
  ic_std_error: string | null;
  test_blocks: number;
  as_of: string;
};

type EvaluationBlock = {
  block: number;
  start: string;
  end: string;
  ic_dates: number;
  mean_ic: string | null;
};

type EvaluationReport = {
  generated_at: string;
  evaluation_version: string;
  feature_version: string;
  model_versions: Record<string, string>;
  settings: {
    universe: string;
    universe_as_of: string | null;
    universe_revision: string;
    start: string;
    end: string;
    blocks: number;
    horizon: number;
    min_feature_history: number;
    source: string;
  };
  data: {
    requested_tickers: number;
    tickers_used: string[];
    excluded: Array<{ ticker: string; reason: string }>;
    panel_rows: number;
    panel_dates: string[] | null;
    scored_rows: number;
    scored_dates: string[] | null;
  };
  metrics: EvaluationMetric[];
  ic_std_error_note: string;
  per_block_ic: Record<string, EvaluationBlock[]>;
};

export default function ModelEvaluationPage() {
  const [report, setReport] = useState<EvaluationReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const supabase = createClient();
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!session) {
        setError("No active session. Please log in again.");
        return;
      }
      setError(null);
      void apiFetch<EvaluationReport>("/ml/evaluation", session.access_token)
        .then(setReport)
        .catch((requestError: unknown) => {
          console.error("Failed to load model evaluation:", requestError);
          setError(requestError instanceof Error ? requestError.message : "Evaluation results are unavailable.");
        });
    });
    return () => subscription.unsubscribe();
  }, []);

  if (error) {
    return (
      <main className="page-shell">
        <header className="page-header">
          <div className="page-heading">
            <span className="eyebrow">Research</span>
            <h1 className="page-title">Model evaluation</h1>
          </div>
          <Link className="secondary-button" href="/dashboard">Back to dashboard</Link>
        </header>
        <div className="notice error" role="alert">{error}</div>
      </main>
    );
  }

  if (!report) {
    return (
      <main className="page-shell">
        <header className="page-header">
          <div className="page-heading">
            <span className="eyebrow">Research</span>
            <h1 className="page-title">Model evaluation</h1>
          </div>
        </header>
        <div className="card list-card"><p className="utility-text">Loading saved evaluation results...</p></div>
      </main>
    );
  }

  const baseline = report.metrics.find((metric) => metric.model === "historical_mean");

  return (
    <main className="page-shell">
      <header className="page-header">
        <div className="page-heading">
          <span className="eyebrow">Offline research · generated {formatDate(report.generated_at)}</span>
          <h1 className="page-title">Model evaluation</h1>
          <p className="page-subtitle">Historical forecast tests, separate from live portfolio recommendations.</p>
        </div>
        <Link className="secondary-button" href="/dashboard">Back to dashboard</Link>
      </header>

      <section className="metric-grid" aria-label="Evaluation summary">
        <article className="metric-card"><span className="metric-label">Universe</span><strong className="metric-value">{report.settings.universe}</strong></article>
        <article className="metric-card"><span className="metric-label">Price period</span><strong className="metric-value evaluation-period">{formatDate(report.settings.start)} – {formatDate(report.settings.end)}</strong></article>
        <article className="metric-card"><span className="metric-label">Scored samples</span><strong className="metric-value">{report.data.scored_rows.toLocaleString()}</strong></article>
        <article className="metric-card"><span className="metric-label">Test blocks</span><strong className="metric-value">{report.settings.blocks}</strong></article>
      </section>

      <section className="card list-card evaluation-panel">
        <div className="section-header">
          <div>
            <h2 className="section-title">Forecast metrics</h2>
            <p className="utility-text">All models use the same scored rows. Lower MAE is better; hit rate and mean IC are directional/ranking diagnostics.</p>
          </div>
          <span className="badge neutral">Baseline: historical mean</span>
        </div>
        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th scope="col">Model</th>
                <th scope="col">Version</th>
                <th scope="col" className="numeric-cell">MAE</th>
                <th scope="col" className="numeric-cell">Hit rate</th>
                <th scope="col" className="numeric-cell">Mean IC</th>
                <th scope="col" className="numeric-cell">IC s.e.</th>
              </tr>
            </thead>
            <tbody>
              {report.metrics.map((metric) => (
                <tr key={metric.model}>
                  <th scope="row">{metric.model}{metric === baseline ? " · baseline" : ""}</th>
                  <td>{report.model_versions[metric.model] ?? "—"}</td>
                  <td className="numeric-cell">{formatPercent(metric.mae)}</td>
                  <td className="numeric-cell">{formatPercent(metric.hit_rate)}</td>
                  <td className="numeric-cell">{metric.mean_ic}</td>
                  <td className="numeric-cell">{metric.ic_std_error ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="utility-text evaluation-note">{report.ic_std_error_note}</p>
      </section>

      <section className="detail-grid evaluation-details">
        <article className="panel evaluation-panel">
          <h2 className="section-title">Method and versions</h2>
          <dl className="evaluation-definition-list">
            <div><dt>Evaluation</dt><dd>{report.evaluation_version}</dd></div>
            <div><dt>Features</dt><dd>{report.feature_version}</dd></div>
            <div><dt>Forecast horizon</dt><dd>{report.settings.horizon} trading days</dd></div>
            <div><dt>Minimum feature history</dt><dd>{report.settings.min_feature_history} trading days</dd></div>
            <div><dt>Data source</dt><dd>{report.settings.source}</dd></div>
            <div><dt>Universe revision</dt><dd>{report.settings.universe_revision}</dd></div>
          </dl>
          <p className="utility-text evaluation-method">
            Expanding walk-forward folds train only on earlier observations and purge a horizon-sized gap before each test block. This evaluates forecasts; it is not a live portfolio return or a portfolio backtest.
          </p>
        </article>

        <article className="panel evaluation-panel">
          <h2 className="section-title">Coverage</h2>
          <dl className="evaluation-definition-list">
            <div><dt>Tickers used</dt><dd>{report.data.tickers_used.length} of {report.data.requested_tickers}</dd></div>
            <div><dt>Feature rows</dt><dd>{report.data.panel_rows.toLocaleString()}</dd></div>
            <div><dt>Scored dates</dt><dd>{report.data.scored_dates ? `${formatDate(report.data.scored_dates[0])} – ${formatDate(report.data.scored_dates[1])}` : "No scored dates"}</dd></div>
          </dl>
          {report.data.excluded.length > 0 ? (
            <ul className="evaluation-exclusions">
              {report.data.excluded.map((item) => <li key={item.ticker}><strong>{item.ticker}</strong>: {item.reason}</li>)}
            </ul>
          ) : (
            <p className="utility-text evaluation-method">No tickers were excluded from this run.</p>
          )}
        </article>
      </section>

      <section className="card list-card evaluation-panel">
        <h2 className="section-title">Mean IC by test block</h2>
        <div className="table-shell">
          <table>
            <thead><tr><th scope="col">Model</th><th scope="col">Block</th><th scope="col">Dates</th><th scope="col" className="numeric-cell">IC dates</th><th scope="col" className="numeric-cell">Mean IC</th></tr></thead>
            <tbody>
              {Object.entries(report.per_block_ic).flatMap(([model, blocks]) => blocks.map((block) => (
                <tr key={`${model}-${block.block}`}>
                  <th scope="row">{model}</th>
                  <td>{block.block}</td>
                  <td>{formatDate(block.start)} – {formatDate(block.end)}</td>
                  <td className="numeric-cell">{block.ic_dates}</td>
                  <td className="numeric-cell">{block.mean_ic ?? "—"}</td>
                </tr>
              )))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}