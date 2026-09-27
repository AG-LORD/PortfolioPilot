"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { ArrowDownRight, ArrowRight, ArrowUpRight, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Sparkline } from "@/components/charts/Charts";
import { ButtonLink } from "@/components/ui/Button";
import { Toast } from "@/components/ui/Toast";
import { Breadcrumbs, Notice, PageContainer, PageTitle, RiskBadge, Skeleton } from "@/components/ui/primitives";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/cn";
import { getErrorMessage } from "@/lib/errors";
import { formatPercent, formatPrice, formatRelativeDay, moneySign } from "@/lib/format";
import { createClient } from "@/lib/supabase/client";
import type { PortfolioOverview, PortfolioOverviewItem } from "@/lib/types/api";

function PortfolioCard({ portfolio }: { portfolio: PortfolioOverviewItem }) {
  // Value and P&L only when the backend could price every holding.
  const valued = portfolio.valuation_status === "ok" && portfolio.total_value !== null;
  const pnl = portfolio.unrealized_pnl === null ? null : Number(portfolio.unrealized_pnl);
  // Amounts that round to ₹0.00 are neutral: no arrow, no colour.
  const sign = pnl === null ? 0 : moneySign(pnl);
  const sparkline = portfolio.sparkline.map(Number);

  return (
    <article className="flex flex-col rounded-lg border border-border bg-card p-5 shadow-sm transition hover:border-primary/40">
      <div className="mb-7 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h2 className="font-bold wrap-break-word">{portfolio.name}</h2>
            <RiskBadge category={portfolio.risk_category} />
          </div>
          <p className="text-xs text-muted-foreground">
            {portfolio.holdings_count} stock{portfolio.holdings_count === 1 ? "" : "s"} · Updated{" "}
            {formatRelativeDay(portfolio.updated_at)}
          </p>
        </div>
        <Sparkline values={sparkline} label={`${portfolio.name}: value over the last ${sparkline.length} snapshots`} />
      </div>
      <p className="text-xs text-muted-foreground">Current value</p>
      {valued && portfolio.total_value !== null ? (
        <>
          <p className="mt-1 text-2xl font-bold tabular-nums">{formatPrice(portfolio.total_value)}</p>
          {pnl !== null && (
            <p
              className={cn(
                "mt-2 flex items-center gap-1 text-sm font-semibold",
                sign > 0 && "text-success",
                sign < 0 && "text-destructive",
                sign === 0 && "text-muted-foreground",
              )}
            >
              {sign > 0 && <ArrowUpRight size={15} aria-hidden="true" />}
              {sign < 0 && <ArrowDownRight size={15} aria-hidden="true" />}
              <span className="sr-only">{sign > 0 ? "Gain" : sign < 0 ? "Loss" : "Profit and loss"}:</span>
              {formatPrice(sign === 0 ? 0 : Math.abs(pnl))}
              {sign !== 0 &&
                portfolio.unrealized_pnl_pct !== null &&
                ` (${formatPercent(Math.abs(Number(portfolio.unrealized_pnl_pct)), 1)})`}
            </p>
          )}
        </>
      ) : (
        <p className="mt-1 text-lg font-semibold text-muted-foreground">Value unavailable</p>
      )}
      <ButtonLink href={`/dashboard/portfolios/${portfolio.id}`} variant="outline" className="mt-auto w-full justify-between">
        Open portfolio <ArrowRight size={16} aria-hidden="true" />
      </ButtonLink>
    </article>
  );
}

// Shown after a portfolio was deleted (the Current page redirects here with ?deleted=<name>).
function DeletedToast() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const deleted = searchParams.get("deleted");
  const dismiss = useCallback(() => router.replace("/dashboard", { scroll: false }), [router]);
  if (!deleted) return null;
  return <Toast message={`Deleted "${deleted}".`} onDismiss={dismiss} />;
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

  return (
    <PageContainer>
      <Breadcrumbs />
      <PageTitle
        title="Your portfolios"
        eyebrow="Overview"
        action={
          <ButtonLink href="/dashboard/new-portfolio">
            <Plus size={17} aria-hidden="true" /> Create portfolio
          </ButtonLink>
        }
      />

      {error && (
        <Notice tone="error">
          <strong>Unable to load your portfolios.</strong> {error}
        </Notice>
      )}

      {!error && !overview && (
        <div className="grid gap-5 lg:grid-cols-3">
          <Skeleton className="h-72" />
          <Skeleton className="h-72" />
        </div>
      )}

      {overview && (
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {overview.portfolios.map((portfolio) => (
            <PortfolioCard key={portfolio.id} portfolio={portfolio} />
          ))}
          <Link
            href="/dashboard/new-portfolio"
            className="flex min-h-64 flex-col items-center justify-center rounded-lg border border-dashed border-border bg-card/40 p-5 text-center transition hover:border-primary/50"
          >
            <span className="mb-4 grid size-11 place-items-center rounded-full bg-muted text-muted-foreground">
              <Plus size={20} aria-hidden="true" />
            </span>
            <span className="font-semibold">
              {overview.portfolios.length === 0 ? "Create your first portfolio" : "Create another portfolio"}
            </span>
            <span className="mt-1 max-w-52 text-sm text-muted-foreground">Try a different goal or risk profile.</span>
          </Link>
        </div>
      )}
      <Suspense fallback={null}>
        <DeletedToast />
      </Suspense>
    </PageContainer>
  );
}
