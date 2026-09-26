"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { RecommendationResult } from "@/components/recommendation/RecommendationResult";
import { apiFetch } from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import { createClient } from "@/lib/supabase/client";
import type { Recommendation, RecommendationHistoryItem, RecommendationRequest, ReturnModel } from "@/lib/types/api";

export default function RecommendationPage() {
  const { portfolioId } = useParams<{ portfolioId: string }>();
  const searchParams = useSearchParams();
  const requestedModel: ReturnModel = searchParams.get("model") === "historical" ? "historical" : "ml";
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [history, setHistory] = useState<RecommendationHistoryItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadHistory = useCallback(async (accessToken: string) => {
    const items = await apiFetch<RecommendationHistoryItem[]>(`/portfolios/${portfolioId}/recommendations`, accessToken);
    setHistory(items);
  }, [portfolioId]);

  const openHistoryItem = useCallback(async (id: string) => {
    const { data: { session } } = await createClient().auth.getSession();
    if (!session) {
      setError("You are signed out. Please log in again.");
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const item = await apiFetch<Recommendation>(`/portfolios/${portfolioId}/recommendations/${id}`, session.access_token);
      setRecommendation(item);
    } catch (err) {
      console.error("Failed to load recommendation:", err);
      setError(getErrorMessage(err, "We couldn't load that saved recommendation."));
    } finally {
      setLoading(false);
    }
  }, [portfolioId]);

  const generate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data: { session } } = await createClient().auth.getSession();
      if (!session) throw new Error("You are signed out. Please log in again.");
      const request: RecommendationRequest = { universe: "NIFTY50", tickers: null, return_model: requestedModel };
      const generated = await apiFetch<Recommendation>(`/portfolios/${portfolioId}/recommendation`, session.access_token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      setRecommendation(generated);
      await loadHistory(session.access_token);
    } catch (err) {
      console.error("Failed to generate recommendation:", err);
      setError(
        err instanceof Error && err.message.startsWith("You are")
          ? err.message
          : getErrorMessage(err, "We couldn't generate your recommendation. Please retry."),
      );
    } finally {
      setLoading(false);
    }
  }, [loadHistory, portfolioId, requestedModel]);

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      const { data: { session } } = await createClient().auth.getSession();
      if (session) {
        await loadHistory(session.access_token);
      }
      await generate();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [generate, loadHistory]);

  return (
    <main className="page-shell">
      <header className="page-header">
        <div className="page-heading">
          <span className="eyebrow">Portfolio recommendation</span>
          <h1 className="page-title">Recommended Portfolio</h1>
          <p className="page-subtitle">What PortfolioPilot suggests</p>
        </div>
        <Link href={`/dashboard/portfolios/${portfolioId}`} className="secondary-button">
          Back to current portfolio
        </Link>
      </header>

      {loading && (
        <div className="card" style={{ padding: 24 }}>
          <div className="notice info">
            <span className="notice-icon">⏳</span>
            <div>
              <strong>Generating your recommendation...</strong>
              <p>We are evaluating the NIFTY 50 universe and building a model-based allocation.</p>
            </div>
          </div>
          <div style={{ display: "grid", gap: 16, marginTop: 18 }}>
            <div className="skeleton skeleton-box" />
            <div className="skeleton skeleton-line" style={{ width: "65%" }} />
            <div className="skeleton skeleton-line" style={{ width: "80%" }} />
            <div className="skeleton skeleton-line" style={{ width: "70%" }} />
          </div>
        </div>
      )}

      {!loading && error && (
        <div className="card" style={{ padding: 24 }}>
          <div className="notice error" role="alert">
            <span className="notice-icon">⚠</span>
            <div>
              <strong>We couldn&apos;t generate a recommendation</strong>
              <p>{error}</p>
            </div>
          </div>
          <div style={{ marginTop: 18 }}>
            <button type="button" className="primary-button" onClick={() => void generate()}>
              Retry
            </button>
          </div>
        </div>
      )}

      {!loading && !error && history.length > 0 && (
        <section className="card" style={{ padding: 24, marginBottom: 24 }}>
          <div className="section-header">
            <div>
              <span className="eyebrow">Saved recommendations</span>
              <h2 className="section-title">Recent history</h2>
            </div>
          </div>
          <div className="portfolio-list">
            {history.map((item) => (
              <button
                key={item.id}
                type="button"
                className="portfolio-list-item"
                onClick={() => void openHistoryItem(item.id)}
                style={{ width: "100%", textAlign: "left", cursor: "pointer", border: "none", background: "transparent" }}
              >
                <div className="portfolio-meta">
                  <strong>{item.universe}</strong>
                  <small>{new Date(item.created_at).toLocaleString()}</small>
                </div>
                <div className="portfolio-meta" style={{ textAlign: "right" }}>
                  <small>{item.return_model === "ml" ? "ML" : "Historical"}</small>
                  <small>{item.capital ? `${item.capital} capital` : "—"}</small>
                </div>
              </button>
            ))}
          </div>
        </section>
      )}

      {!loading && !error && recommendation && (
        <RecommendationResult recommendation={recommendation} requestedModel={requestedModel} />
      )}

      {!loading && !error && !recommendation && (
        <div className="card" style={{ padding: 24 }}>
          <div className="empty-state">
            <div>📉</div>
            <strong>No recommendation was returned</strong>
            <p>Please try again.</p>
          </div>
        </div>
      )}
    </main>
  );
}
