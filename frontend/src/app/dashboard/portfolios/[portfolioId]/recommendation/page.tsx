"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Loader2, RefreshCw } from "lucide-react";
import { PlanView } from "@/components/plan/PlanView";
import { StockSelector } from "@/components/stocks/StockSelector";
import { Button } from "@/components/ui/Button";
import { Breadcrumbs, Notice, PageContainer, PageTitle, PortfolioTabs, RiskBadge, Section, Skeleton } from "@/components/ui/primitives";
import { apiFetch, getAccessToken } from "@/lib/api";
import { cn } from "@/lib/cn";
import { getErrorMessage } from "@/lib/errors";
import { formatDate, formatDateTime, formatPrice } from "@/lib/format";
import {
  DEFAULT_SELECTION,
  isSelectionValid,
  loadSelection,
  saveSelection,
  selectionToRequest,
  type StockSelection,
} from "@/lib/stockSelection";
import type { Portfolio, PortfolioOverview, Recommendation, RecommendationSummary } from "@/lib/types/api";

type Status = "loading" | "generating" | "ready";

function signedOutError(err: unknown, fallback: string) {
  return err instanceof Error && err.message.startsWith("You are") ? err.message : getErrorMessage(err, fallback);
}

function PlanPageView() {
  const { portfolioId } = useParams<{ portfolioId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [riskCategory, setRiskCategory] = useState<string | null>(null);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [history, setHistory] = useState<RecommendationSummary[]>([]);
  const [selection, setSelection] = useState<StockSelection>(DEFAULT_SELECTION);
  const [showGeneratePanel, setShowGeneratePanel] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const initHandled = useRef(false);

  const loadHistory = useCallback(
    async (accessToken: string) => {
      const items = await apiFetch<RecommendationSummary[]>(`/portfolios/${portfolioId}/recommendations`, accessToken);
      setHistory(items);
      return items;
    },
    [portfolioId],
  );

  const openHistoryItem = useCallback(
    async (id: string) => {
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
    },
    [portfolioId],
  );

  const generate = useCallback(
    async (chosen: StockSelection) => {
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
        setError(signedOutError(err, "We couldn't generate your recommendation. Please retry."));
      } finally {
        setStatus("ready");
      }
    },
    [loadHistory, portfolioId],
  );

  useEffect(() => {
    if (initHandled.current) return;
    initHandled.current = true;
    const shouldGenerate = searchParams.get("generate") === "1";

    async function init() {
      const saved = loadSelection(portfolioId);
      setSelection(saved);
      try {
        const accessToken = await getAccessToken();
        if (!accessToken) throw new Error("You are signed out. Please log in again.");
        const [loaded, overview] = await Promise.all([
          apiFetch<Portfolio>(`/portfolios/${portfolioId}`, accessToken),
          apiFetch<PortfolioOverview>("/portfolios/overview", accessToken).catch((err) => {
            // Only names the risk badge; the page works without it.
            console.error("Failed to load portfolio overview:", err);
            return null;
          }),
        ]);
        setPortfolio(loaded);
        setRiskCategory(overview?.portfolios.find((item) => item.id === portfolioId)?.risk_category ?? null);

        if (shouldGenerate) {
          router.replace(`/dashboard/portfolios/${portfolioId}/recommendation`);
          await generate(saved);
          return;
        }

        const items = await loadHistory(accessToken);
        // The adopted plan when there is one, else the newest recommendation.
        const initial = loaded.adopted_recommendation_id ?? items[0]?.id ?? null;
        if (initial) {
          await openHistoryItem(initial);
          return;
        }
        setShowGeneratePanel(true);
      } catch (err) {
        console.error("Failed to load plan:", err);
        setError(signedOutError(err, "We couldn't load your plan."));
      }
      setStatus("ready");
    }

    void init();
  }, [generate, loadHistory, openHistoryItem, portfolioId, router, searchParams]);

  async function adopt() {
    if (!recommendation?.id) return;
    const accessToken = await getAccessToken();
    if (!accessToken) throw new Error("You are signed out. Please log in again.");
    const updated = await apiFetch<Portfolio>(
      `/portfolios/${portfolioId}/recommendations/${recommendation.id}/adopt`,
      accessToken,
      { method: "POST" },
    );
    setPortfolio(updated);
  }

  const busy = status !== "ready";
  const adopted = Boolean(recommendation?.id && recommendation.id === portfolio?.adopted_recommendation_id);
  const eyebrow = recommendation?.created_at ? `Recommendation · ${formatDate(recommendation.created_at)}` : "Plan";

  return (
    <PageContainer>
      <Breadcrumbs current={portfolio?.name} />
      <PageTitle
        eyebrow={eyebrow}
        title={portfolio?.name ?? "Plan"}
        action={riskCategory ? <RiskBadge category={riskCategory} className="px-3 py-1.5 text-xs" /> : undefined}
      />
      <PortfolioTabs portfolioId={portfolioId} active="plan" />

      {status === "generating" && (
        <div className="mt-6">
          <Notice tone="info">
            <span className="flex items-center gap-2">
              <Loader2 size={16} className="animate-spin" aria-hidden="true" /> Analysing market data for your selected stocks…
            </span>
          </Notice>
        </div>
      )}

      {status === "loading" && (
        <div className="mt-6 space-y-4">
          <Skeleton className="h-72" />
          <Skeleton className="h-40" />
        </div>
      )}

      {!busy && error && (
        <div className="mt-6">
          <Notice tone="error">
            <strong>Something went wrong.</strong> {error}
          </Notice>
        </div>
      )}

      {showGeneratePanel && (
        <Section title="Generate a new recommendation" subtitle="Choose the stocks PortfolioPilot should analyse">
          <div className="rounded-lg border border-border bg-card p-5">
            <StockSelector value={selection} onChange={setSelection} maxPositionWeight={recommendation?.constraints.max_position_weight} />
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              {(recommendation || history.length > 0) && (
                <Button variant="outline" disabled={busy} onClick={() => setShowGeneratePanel(false)}>
                  Cancel
                </Button>
              )}
              <Button disabled={busy || !isSelectionValid(selection)} onClick={() => void generate(selection)}>
                {status === "generating" ? "Generating…" : "Generate"}
              </Button>
            </div>
          </div>
        </Section>
      )}

      {!busy && recommendation && (
        <PlanView
          key={recommendation.id ?? "unsaved"}
          recommendation={recommendation}
          adopted={adopted}
          adoptedAt={portfolio?.adopted_at ?? null}
          onAdopt={adopt}
        />
      )}

      {!busy && !showGeneratePanel && (
        <Section
          title="Previous recommendations"
          subtitle="Open an earlier recommendation, or generate a new one"
          action={
            <Button variant="outline" size="sm" onClick={() => setShowGeneratePanel(true)}>
              <RefreshCw size={14} aria-hidden="true" /> New recommendation
            </Button>
          }
        >
          {history.length === 0 ? (
            <p className="text-sm text-muted-foreground">No saved recommendations yet.</p>
          ) : (
            <ul className="divide-y divide-border rounded-lg border border-border bg-card">
              {history.map((item) => {
                const shown = recommendation?.id === item.id;
                const isAdopted = item.id === portfolio?.adopted_recommendation_id;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={cn(
                        "flex w-full flex-wrap items-center justify-between gap-2 px-4 py-3 text-left text-sm hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        shown && "bg-muted/50",
                      )}
                      aria-current={shown ? "true" : undefined}
                      onClick={() => void openHistoryItem(item.id)}
                    >
                      <span className="font-semibold">{formatDateTime(item.created_at)}</span>
                      <span className="text-xs text-muted-foreground">
                        {item.universe === "NIFTY50" ? "NIFTY 50" : "Picked stocks"} · {formatPrice(item.capital)}
                        {isAdopted && " · Active plan"}
                        {shown && " · Shown"}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Section>
      )}
    </PageContainer>
  );
}

export default function RecommendationPage() {
  return (
    <Suspense
      fallback={
        <PageContainer>
          <Skeleton className="h-72" />
        </PageContainer>
      }
    >
      <PlanPageView />
    </Suspense>
  );
}
