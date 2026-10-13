"use client";

import { useEffect, useEffectEvent, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowDownRight, ArrowUpRight, Plus, Trash2 } from "lucide-react";
import {
  CASH_COLOR,
  ChartLegend,
  CompareLineChart,
  Donut,
  DonutLegend,
  sliceColor,
  type DonutSlice,
} from "@/components/charts/Charts";
import { PlanStatusBanner, type PlanStatus } from "@/components/plan/PlanStatusBanner";
import { AddMoneyDialog, DeletePortfolioDialog, RecordTradeDialog } from "@/components/portfolio/PortfolioDialogs";
import { PortfolioHealth } from "@/components/portfolio/PortfolioHealth";
import { Button } from "@/components/ui/Button";
import {
  Breadcrumbs,
  Metric,
  Notice,
  PageContainer,
  PageTitle,
  PortfolioTabs,
  Section,
  Skeleton,
} from "@/components/ui/primitives";
import { ApiError, apiFetch } from "@/lib/api";
import { cn } from "@/lib/cn";
import { getErrorMessage } from "@/lib/errors";
import {
  formatCompactINR,
  formatDate,
  formatPrice,
  formatShares,
  formatSignedPercent,
  formatSignedPrice,
  moneySign,
} from "@/lib/format";
import { createClient } from "@/lib/supabase/client";
import type {
  Portfolio,
  PortfolioDrift,
  PortfolioOverview,
  PortfolioOverviewItem,
  PortfolioPerformance,
  PortfolioValuation,
  RebalancePreview,
  RiskAnalytics,
  Transaction,
} from "@/lib/types/api";

type HoldingRow = { id: string; ticker: string; quantity: string; average_cost: string };

// P&L colour by the amount as displayed; values that round to ₹0.00 stay neutral.
function pnlClass(value: string | number) {
  const sign = moneySign(value);
  return sign > 0 ? "text-success" : sign < 0 ? "text-destructive" : "";
}

function TransactionList({ transactions }: { transactions: Transaction[] }) {
  return (
    <ul className="divide-y divide-border rounded-lg border border-border bg-card">
      {transactions.map((tx) => {
        const deposit = tx.transaction_type === "DEPOSIT";
        const buy = tx.transaction_type === "BUY";
        const title = deposit ? "Added capital" : `${buy ? "Bought" : "Sold"} ${tx.ticker}`;
        const detail = deposit
          ? formatPrice(tx.price)
          : `${formatShares(tx.quantity)} share${Number(tx.quantity) === 1 ? "" : "s"} at ${formatPrice(tx.price)}`;
        const Icon = deposit ? Plus : buy ? ArrowDownRight : ArrowUpRight;
        return (
          <li key={tx.id} className="flex items-center justify-between gap-4 p-4">
            <div className="flex min-w-0 items-center gap-3">
              <span
                className={cn(
                  "grid size-9 shrink-0 place-items-center rounded-md",
                  buy || deposit ? "bg-success/10 text-success" : "bg-muted text-muted-foreground",
                )}
              >
                <Icon size={17} aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-bold">{title}</p>
                <p className="text-xs text-muted-foreground">
                  {formatDate(tx.occurred_at)} · {detail}
                  {Number(tx.fees) > 0 && ` · fees ${formatPrice(tx.fees)}`}
                </p>
              </div>
            </div>
            <span className="text-xs font-semibold text-success">Recorded</span>
          </li>
        );
      })}
    </ul>
  );
}

function HoldingsTable({ valuation, holdings }: { valuation: PortfolioValuation | null; holdings: HoldingRow[] }) {
  const rows = valuation
    ? valuation.holdings.map((h) => ({
        ticker: h.ticker,
        sector: h.sector,
        quantity: h.quantity,
        average_cost: h.average_cost,
        value: h.market_value as string | null,
        pnl: h.unrealized_pnl as string | null,
      }))
    : holdings.map((h) => ({
        ticker: h.ticker,
        sector: null,
        quantity: h.quantity,
        average_cost: h.average_cost,
        value: null,
        pnl: null,
      }));
  const cash = valuation?.cash_balance ?? null;

  return (
    <>
      <div className="table-wrap hidden sm:block">
        <table>
          <thead>
            <tr>
              <th>Holding</th>
              <th>Shares</th>
              <th>Avg. price</th>
              <th>Value</th>
              <th>P&amp;L</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.ticker}>
                <td>
                  <strong>{row.ticker}</strong>
                  {row.sector && <small>{row.sector}</small>}
                </td>
                <td className="tabular-nums">{formatShares(row.quantity)}</td>
                <td className="tabular-nums">{formatPrice(row.average_cost)}</td>
                <td className="tabular-nums">{row.value === null ? "—" : formatPrice(row.value)}</td>
                <td className={cn("tabular-nums", row.pnl !== null && pnlClass(row.pnl))}>
                  {row.pnl === null ? "—" : formatSignedPrice(row.pnl)}
                </td>
              </tr>
            ))}
            {cash !== null && (
              <tr>
                <td>
                  <strong>Cash</strong>
                  <small>Available</small>
                </td>
                <td>—</td>
                <td>—</td>
                <td className="tabular-nums">{formatPrice(cash)}</td>
                <td>—</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <ul className="space-y-3 sm:hidden" aria-label="Holdings">
        {rows.map((row) => (
          <li key={row.ticker} className="rounded-lg border border-border bg-card p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-bold">{row.ticker}</p>
                {row.sector && <p className="text-xs text-muted-foreground">{row.sector}</p>}
              </div>
              <p className="font-semibold tabular-nums">{row.value === null ? "—" : formatPrice(row.value)}</p>
            </div>
            <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
              <div>
                <dt className="text-muted-foreground">Shares</dt>
                <dd className="font-semibold tabular-nums">{formatShares(row.quantity)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Avg. price</dt>
                <dd className="font-semibold tabular-nums">{formatPrice(row.average_cost)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">P&amp;L</dt>
                <dd className={cn("font-semibold tabular-nums", row.pnl !== null && pnlClass(row.pnl))}>
                  {row.pnl === null ? "—" : formatSignedPrice(row.pnl)}
                </dd>
              </div>
            </dl>
          </li>
        ))}
        {cash !== null && (
          <li className="flex items-center justify-between rounded-lg border border-border bg-card p-4">
            <div>
              <p className="font-bold">Cash</p>
              <p className="text-xs text-muted-foreground">Available</p>
            </div>
            <p className="font-semibold tabular-nums">{formatPrice(cash)}</p>
          </li>
        )}
      </ul>
    </>
  );
}

export default function PortfolioDetailPage() {
  const { portfolioId } = useParams<{ portfolioId: string }>();

  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [overviewItem, setOverviewItem] = useState<PortfolioOverviewItem | null>(null);
  const [holdings, setHoldings] = useState<HoldingRow[] | null>(null);
  const [transactions, setTransactions] = useState<Transaction[] | null>(null);
  const [valuation, setValuation] = useState<PortfolioValuation | null>(null);
  const [drift, setDrift] = useState<PortfolioDrift | null>(null);
  const [performance, setPerformance] = useState<PortfolioPerformance | null>(null);
  const [riskAnalytics, setRiskAnalytics] = useState<RiskAnalytics | null>(null);
  const [planStatus, setPlanStatus] = useState<PlanStatus | null>(null);

  const [authError, setAuthError] = useState<string | null>(null);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);
  const [holdingsError, setHoldingsError] = useState<string | null>(null);
  const [transactionsError, setTransactionsError] = useState<string | null>(null);
  const [valuationError, setValuationError] = useState<string | null>(null);

  const [dialog, setDialog] = useState<"trade" | "money" | "delete" | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);

  async function loadPlanStatus(token: string, loaded: Portfolio) {
    if (!loaded.adopted_recommendation_id) {
      setPlanStatus({ kind: "none" });
      return;
    }
    setPlanStatus({ kind: "loading", adoptedAt: loaded.adopted_at });
    try {
      const preview = await apiFetch<RebalancePreview>(
        `/portfolios/${portfolioId}/rebalance-proposals/preview?recommendation_id=${encodeURIComponent(loaded.adopted_recommendation_id)}`,
        token,
      );
      setPlanStatus({ kind: "orders", adoptedAt: loaded.adopted_at, remaining: preview.trades.length });
    } catch (err) {
      console.error("Failed to load plan orders:", err);
      setPlanStatus({
        kind: "unavailable",
        adoptedAt: loaded.adopted_at,
        message:
          err instanceof ApiError && err.status === 503
            ? "Market prices are unavailable, so open orders can't be checked right now."
            : getErrorMessage(err, "Open orders can't be checked right now."),
      });
    }
  }

  async function loadAll(token: string) {
    const base = `/portfolios/${portfolioId}`;
    const [portfolioResult, overviewResult, holdingsResult, txResult, valuationResult, driftResult, perfResult, riskResult] =
      await Promise.allSettled([
        apiFetch<Portfolio>(base, token),
        apiFetch<PortfolioOverview>("/portfolios/overview", token),
        apiFetch<HoldingRow[]>(`${base}/holdings`, token),
        apiFetch<Transaction[]>(`${base}/transactions`, token),
        apiFetch<PortfolioValuation>(`${base}/valuation`, token),
        apiFetch<PortfolioDrift>(`${base}/drift`, token),
        apiFetch<PortfolioPerformance>(`${base}/performance`, token),
        apiFetch<RiskAnalytics>(`${base}/risk`, token),
      ]);

    function settle<T>(result: PromiseSettledResult<T>, set: (value: T) => void, setError: (message: string | null) => void, fallback: string) {
      if (result.status === "fulfilled") {
        set(result.value);
        setError(null);
      } else {
        console.error(fallback, result.reason);
        setError(getErrorMessage(result.reason, fallback));
      }
    }

    settle(portfolioResult, setPortfolio, setPortfolioError, "Unable to load this portfolio.");
    settle(holdingsResult, setHoldings, setHoldingsError, "Unable to load holdings.");
    settle(txResult, setTransactions, setTransactionsError, "Unable to load transactions.");
    settle(valuationResult, setValuation, setValuationError, "Live valuation is currently unavailable.");
    // Optional panels: they simply don't render when their data is unavailable.
    if (driftResult.status === "fulfilled") setDrift(driftResult.value);
    if (perfResult.status === "fulfilled") setPerformance(perfResult.value);
    if (riskResult.status === "fulfilled") setRiskAnalytics(riskResult.value);
    if (overviewResult.status === "fulfilled") {
      setOverviewItem(overviewResult.value.portfolios.find((item) => item.id === portfolioId) ?? null);
    }
    if (portfolioResult.status === "fulfilled") await loadPlanStatus(token, portfolioResult.value);
  }

  const loadAllForSession = useEffectEvent((token: string) => {
    setAccessToken(token);
    void loadAll(token);
  });

  useEffect(() => {
    const supabase = createClient();
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        loadAllForSession(session.access_token);
      } else {
        setAuthError("No active session.");
      }
    });
    return () => subscription.unsubscribe();
  }, [portfolioId]);

  async function reload() {
    if (accessToken) await loadAll(accessToken);
  }

  if (authError || portfolioError) {
    return (
      <PageContainer>
        <Notice tone="error">{authError ?? portfolioError}</Notice>
      </PageContainer>
    );
  }

  if (!portfolio) {
    return (
      <PageContainer>
        <Skeleton className="mb-6 h-10 w-64" />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      </PageContainer>
    );
  }

  const planHref = `/dashboard/portfolios/${portfolioId}/recommendation`;
  const holdingCount = valuation?.holdings.length ?? holdings?.length ?? 0;
  const category = overviewItem ? overviewItem.risk_category.charAt(0).toUpperCase() + overviewItem.risk_category.slice(1) : null;
  const deposits =
    overviewItem?.total_deposited != null
      ? `Deposited ${formatPrice(overviewItem.total_deposited)}`
      : `Initial deposit ${formatPrice(portfolio.initial_capital)}`;
  const eyebrow = [category, deposits].filter(Boolean).join(" · ");

  // Holdings mix: the backend's current weights (drift), only when every holding was priced.
  const weighted = drift?.valuation_complete
    ? drift.positions.filter((p) => p.current_weight !== null && Number(p.current_weight) > 0)
    : [];
  const stockSlices: DonutSlice[] = weighted
    .filter((p) => p.ticker !== "CASH")
    .sort((a, b) => Number(b.current_weight) - Number(a.current_weight))
    .map((p, index) => ({ name: p.ticker, weight: Number(p.current_weight), color: sliceColor(index) }));
  const cashPosition = weighted.find((p) => p.ticker === "CASH");
  const mixSlices = cashPosition
    ? [...stockSlices, { name: "Cash", weight: Number(cashPosition.current_weight), color: CASH_COLOR }]
    : stockSlices;

  const performancePoints = (performance?.points ?? []).map((p) => ({
    date: p.date,
    primary: Number(p.portfolio),
    benchmark: p.benchmark === null ? null : Number(p.benchmark),
  }));
  const hasPerformanceChart = performancePoints.length >= 2;
  const trackingSince = riskAnalytics?.first_snapshot_date ?? new Date().toISOString();

  return (
    <PageContainer>
      <Breadcrumbs current={portfolio.name} />
      <PageTitle eyebrow={eyebrow} title={portfolio.name} />
      <PortfolioTabs portfolioId={portfolioId} active="current" />

      {planStatus && <PlanStatusBanner status={planStatus} planHref={planHref} />}

      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric
          label="Portfolio value"
          value={valuation ? formatPrice(valuation.total_value) : "—"}
          note={valuation ? `As of ${formatDate(new Date().toISOString())}` : (valuationError ?? "Loading…")}
        />
        <Metric
          label="Total P&L"
          value={valuation ? formatSignedPrice(valuation.unrealized_pnl) : "—"}
          valueClassName={valuation ? pnlClass(valuation.unrealized_pnl) : undefined}
          note={
            valuation && moneySign(valuation.unrealized_pnl) !== 0 && overviewItem?.unrealized_pnl_pct != null
              ? `${formatSignedPercent(overviewItem.unrealized_pnl_pct)} on invested`
              : "Unrealised, on current holdings"
          }
        />
        <Metric
          label="Invested"
          value={valuation ? formatPrice(valuation.invested_value) : "—"}
          note={`Across ${holdingCount} stock${holdingCount === 1 ? "" : "s"}`}
        />
        <Metric
          label="Cash available"
          value={formatPrice(valuation?.cash_balance ?? portfolio.cash_balance)}
          action={
            <Button variant="outline" size="sm" onClick={() => setDialog("money")}>
              <Plus size={14} aria-hidden="true" /> Add money
            </Button>
          }
        />
      </div>

      {performance !== null && !hasPerformanceChart && (
        <p className="mt-3 text-xs text-muted-foreground">
          Performance tracking started {formatDate(trackingSince)}. The chart appears after 2 trading days.
        </p>
      )}

      {hasPerformanceChart && (
        <Section title="Portfolio value, compared with NIFTY 50" subtitle="Daily snapshots of your portfolio next to NIFTY 50 scaled to the same start">
          <div className="rounded-lg border border-border bg-card p-3 sm:p-5">
            <ChartLegend
              items={[
                { label: "Portfolio", color: "var(--primary)" },
                { label: "NIFTY 50", color: "var(--chart-benchmark)", dashed: true },
              ]}
            />
            <CompareLineChart data={performancePoints} primaryLabel="Portfolio" />
          </div>
        </Section>
      )}

      <div className={cn("grid gap-6", mixSlices.length > 0 && "lg:grid-cols-[0.8fr_1.4fr]")}>
        {mixSlices.length > 0 && (
          <Section title="Holdings mix">
            <div className="rounded-lg border border-border bg-card p-4">
              <Donut
                slices={mixSlices}
                centerLabel="Value"
                centerValue={drift?.portfolio_value ? formatCompactINR(drift.portfolio_value) : "—"}
              />
              <DonutLegend slices={mixSlices} />
            </div>
          </Section>
        )}
        <Section title="Holdings">
          {holdingsError && <Notice tone="error">{holdingsError}</Notice>}
          {!holdingsError && holdings === null && <Skeleton className="h-40" />}
          {holdings !== null && holdings.length === 0 && (
            <div className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
              No holdings yet. Adopt a plan, place its orders at your broker, then record them from the Plan tab.
            </div>
          )}
          {holdings !== null && holdings.length > 0 && (
            <>
              {valuationError && (
                <p className="mb-3 text-xs text-muted-foreground" role="status">
                  {valuationError} Values and P&amp;L are hidden until prices are available.
                </p>
              )}
              <HoldingsTable valuation={valuation} holdings={holdings} />
            </>
          )}
        </Section>
      </div>

      <Section
        title="Transactions"
        subtitle="Orders recorded in PortfolioPilot"
        action={
          <Button variant="outline" size="sm" onClick={() => setDialog("trade")}>
            Record a trade manually
          </Button>
        }
      >
        {transactionsError && <Notice tone="error">{transactionsError}</Notice>}
        {!transactionsError && transactions === null && <Skeleton className="h-32" />}
        {transactions !== null && transactions.length === 0 && (
          <div className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            No transactions yet.
          </div>
        )}
        {transactions !== null && transactions.length > 0 && <TransactionList transactions={transactions} />}
      </Section>

      <Section title="Portfolio health" subtitle="From your current holdings and prices">
        <PortfolioHealth
          holdingCount={holdingCount}
          drift={drift}
          valuationHoldings={valuation?.holdings ?? null}
          riskAnalytics={riskAnalytics}
        />
      </Section>

      <section className="mt-6 mb-4 rounded-lg border border-destructive/30 bg-card p-5" aria-labelledby="danger-zone-title">
        <h2 id="danger-zone-title" className="font-bold text-destructive">
          Danger zone
        </h2>
        <div className="mt-2 flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
          <p className="text-sm text-muted-foreground">
            Permanently delete this portfolio with its holdings, transactions, plans and history.
          </p>
          <Button variant="destructive-outline" onClick={() => setDialog("delete")}>
            <Trash2 size={16} aria-hidden="true" /> Delete portfolio
          </Button>
        </div>
      </section>

      <RecordTradeDialog open={dialog === "trade"} portfolioId={portfolioId} onClose={() => setDialog(null)} onRecorded={reload} />
      <AddMoneyDialog open={dialog === "money"} portfolioId={portfolioId} onClose={() => setDialog(null)} onAdded={reload} />
      <DeletePortfolioDialog
        open={dialog === "delete"}
        portfolioId={portfolioId}
        portfolioName={portfolio.name}
        onClose={() => setDialog(null)}
      />
    </PageContainer>
  );
}
