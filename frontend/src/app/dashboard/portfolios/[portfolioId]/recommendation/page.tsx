"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { RecommendationResult } from "@/components/recommendation/RecommendationResult";
import { PortfolioNav } from "@/components/shell/PortfolioNav";
import { StockSelector } from "@/components/stocks/StockSelector";
import { apiFetch, getAccessToken } from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import { formatCurrency, formatDateTime } from "@/lib/format";
import {
  DEFAULT_SELECTION,
  isSelectionValid,
  loadSelection,
  saveSelection,
  selectionToRequest,
  type StockSelection,
} from "@/lib/stockSelection";
import type { PortfolioOverview, Recommendation, RecommendationSummary } from "@/lib/types/api";

type Status = "loading" | "generating" | "ready";

function RecommendationView() {
  const { portfolioId } = useParams<{ portfolioId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [history, setHistory] = useState<RecommendationSummary[]>([]);
  const [selection, setSelection] = useState<StockSelection>(DEFAULT_SELECTION);
  const [showGeneratePanel, setShowGeneratePanel] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [riskCategory, setRiskCategory] = useState<string | null>(null);
  const autoGenerateHandled = useRef(false);

  const loadHistory = useCallback(async (accessToken: string) => {
    const items = await apiFetch<RecommendationSummary[]>(`/portfolios/${portfolioId}/recommendations`, accessToken);
    setHistory(items);
    return items;
  }, [portfolioId]);

  const openHistoryItem = useCallback(async (id: string) => {
    const accessToken = await getAccessToken();
    if (!accessToken) {
      setError("You are signed out. Please log in again.");
      return;
    }

    try {
      setStatus("loading");
      setError(null);
      setRecommendation(await apiFetch<Recommendation>(`/portfolios/${portfolioId}/recommendations/${id}`, accessToken));
    } catch (err) {
      console.error("Failed to load recommendation:", err);
      setError(getErrorMessage(err, "We couldn't load that saved recommendation."));
    } finally {
      setStatus("ready");
    }
  }, [portfolioId]);

  const generate = useCallback(async (chosen: StockSelection) => {
    setStatus("generating");
    setError(null);
    try {
      const accessToken = await getAccessToken();
      if (!accessToken) throw new Error("You are signed out. Please log in again.");
      saveSelection(portfolioId, chosen);
      const generated = await apiFetch<Recommendation>(`/portfolios/${portfolioId}/recommendation`, accessToken, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(selectionToRequest(chosen)),
      });
      setRecommendation(generated);
      setShowGeneratePanel(false);
      await loadHistory(accessToken);
    } catch (err) {
      console.error("Failed to generate recommendation:", err);
      setError(
        err instanceof Error && err.message.startsWith("You are")
          ? err.message
          : getErrorMessage(err, "We couldn't generate your recommendation. Please retry."),
      );
    } finally {
      setStatus("ready");
    }
  }, [loadHistory, portfolioId]);

  useEffect(() => {
    if (autoGenerateHandled.current) return;
    autoGenerateHandled.current = true;
    const shouldGenerate = searchParams.get("generate") === "1";

    async function init() {
      const saved = loadSelection(portfolioId);
      setSelection(saved);

      if (shouldGenerate) {
        router.replace(`/dashboard/portfolios/${portfolioId}/recommendation`);
        await generate(saved);
        return;
      }

      try {
        const accessToken = await getAccessToken();
        if (!accessToken) throw new Error("You are signed out. Please log in again.");
        const items = await loadHistory(accessToken);
        if (items.length > 0) {
          const newest = items.reduce((latest, item) => (item.created_at > latest.created_at ? item : latest));
          await openHistoryItem(newest.id);
          return;
        }
        setShowGeneratePanel(true);
      } catch (err) {
        console.error("Failed to load recommendations:", err);
        setError(
          err instanceof Error && err.message.startsWith("You are")
            ? err.message
            : getErrorMessage(err, "We couldn't load your saved recommendations."),
        );
      }
      setStatus("ready");
    }

    void init();
  }, [generate, loadHistory, openHistoryItem, portfolioId, router, searchParams]);

  useEffect(() => {
    // Only used to name the risk category in the explanation; the sentence omits it if this fails.
    let cancelled = false;
    async function loadRiskCategory() {
      try {
        const accessToken = await getAccessToken();
        if (!accessToken) return;
        const overview = await apiFetch<PortfolioOverview>("/portfolios/overview", accessToken);
        const match = overview.portfolios.find((item) => item.id === portfolioId);
        if (!cancelled && match) setRiskCategory(match.risk_category);
      } catch (err) {
        console.error("Failed to load portfolio overview:", err);
      }
    }
    void loadRiskCategory();
    return () => {
      cancelled = true;
    };
  }, [portfolioId]);

  const busy = status !== "ready";

  return (
    <main className="page-shell">
      <PortfolioNav portfolioId={portfolioId} current="recommendation" />
      <header className="page-header">
        <div className="page-heading">
          <span className="eyebrow">What PortfolioPilot suggests</span>
          <h1 className="page-title">
            {recommendation ? `Recommendation from ${formatDateTime(recommendation.created_at ?? null)}` : "Recommendation"}
          </h1>
        </div>
        {!showGeneratePanel && (
          <button type="button" className="primary-button" disabled={busy} onClick={() => setShowGeneratePanel(true)}>
            Generate new recommendation
          </button>
        )}
      </header>

      {showGeneratePanel && (
        <section className="card" style={{ padding: 24, marginBottom: 24 }} aria-labelledby="generate-title">
          <div className="section-header">
            <div>
              <span className="eyebrow">Stocks to analyze</span>
              <h2 className="section-title" id="generate-title">Generate new recommendation</h2>
            </div>
          </div>
          <StockSelector
            value={selection}
            onChange={setSelection}
            maxPositionWeight={recommendation?.constraints.max_position_weight}
          />
          <div className="segmented-actions" style={{ marginTop: 18 }}>
            {(recommendation || history.length > 0) && (
              <button type="button" className="secondary-button" disabled={busy} onClick={() => setShowGeneratePanel(false)}>
                Cancel
              </button>
            )}
            <button
              type="button"
              className="primary-button"
              disabled={busy || !isSelectionValid(selection)}
              onClick={() => void generate(selection)}
            >
              {status === "generating" ? "Generating…" : "Generate"}
            </button>
          </div>
        </section>
      )}

      {status === "generating" && (
        <div className="card" style={{ padding: 24, marginBottom: 24 }}>
          <div className="notice info" role="status">
            <span className="notice-icon">⏳</span>
            <div>
              <strong>Analyzing market data for your selected stocks…</strong>
            </div>
          </div>
        </div>
      )}

      {status === "loading" && (
        <div className="card" style={{ padding: 24, marginBottom: 24 }}>
          <div style={{ display: "grid", gap: 16 }}>
            <div className="skeleton skeleton-box" />
            <div className="skeleton skeleton-line" style={{ width: "65%" }} />
          </div>
        </div>
      )}

      {!busy && error && (
        <div className="card" style={{ padding: 24, marginBottom: 24 }}>
          <div className="notice error" role="alert">
            <span className="notice-icon">⚠</span>
            <div>
              <strong>Something went wrong</strong>
              <p>{error}</p>
            </div>
          </div>
        </div>
      )}

      {!busy && !error && !recommendation && !showGeneratePanel && history.length === 0 && (
        <div className="card" style={{ padding: 24, marginBottom: 24 }}>
          <div className="empty-state">
            <div>📉</div>
            <strong>No recommendations yet</strong>
            <p>Generate one to see what PortfolioPilot suggests.</p>
            <button type="button" className="primary-button" onClick={() => setShowGeneratePanel(true)}>
              Generate
            </button>
          </div>
        </div>
      )}

      {!busy && recommendation && <RecommendationResult recommendation={recommendation} riskCategory={riskCategory} />}

      {!busy && history.length > 0 && (
        <details className="history-disclosure">
          <summary>Previous recommendations ({history.length})</summary>
          <ul className="history-list">
            {history.map((item) => {
              const shown = recommendation?.id === item.id;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`history-row ${shown ? "active" : ""}`}
                    aria-current={shown ? "true" : undefined}
                    onClick={() => void openHistoryItem(item.id)}
                  >
                    <span>{formatDateTime(item.created_at)}</span>
                    <span className="utility-text">
                      {item.universe === "NIFTY50" ? "NIFTY 50" : item.universe} · ML-assisted · {formatCurrency(item.capital)}
                    </span>
                    {shown && <span className="badge neutral">Shown</span>}
                  </button>
                </li>
              );
            })}
          </ul>
        </details>
      )}
    </main>
  );
}

export default function RecommendationPage() {
  return (
    <Suspense fallback={<main className="page-shell"><div className="card list-card"><div className="skeleton skeleton-box" /></div></main>}>
      <RecommendationView />
    </Suspense>
  );
}
