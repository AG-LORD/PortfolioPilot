"use client";

import { useEffect, useState } from "react";
import { ArrowDownRight, ArrowRight, CheckCircle2, ChevronDown, CircleHelp, ShieldCheck } from "lucide-react";
import {
  CASH_COLOR,
  ChartEmpty,
  ChartLegend,
  CompareLineChart,
  Donut,
  sliceColor,
  type DonutSlice,
} from "@/components/charts/Charts";
import { OrderChecklist } from "@/components/plan/OrderChecklist";
import { StockAnalysisDrawer } from "@/components/recommendation/StockAnalysisDrawer";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Metric, Notice, Section, Skeleton, SourcePill } from "@/components/ui/primitives";
import { apiFetch, getAccessToken } from "@/lib/api";
import { cn } from "@/lib/cn";
import { getErrorMessage } from "@/lib/errors";
import { formatCompactINR, formatDate, formatPercent, formatPrice, formatShortDate } from "@/lib/format";
import type { HistoryPreview, NotSelectedItem, NotSelectedReason, Recommendation } from "@/lib/types/api";

const NOT_SELECTED_PREVIEW = 10;

// Why a stock was left out, in plain words. risk_limit is the reason stored by
// recommendations saved before the mean-variance optimizer.
export function notSelectedReasonLabel(item: NotSelectedItem, maxSectorWeight: string | null | undefined): string {
  const labels: Record<NotSelectedReason, string> = {
    negative_estimate: "Expected to fall",
    risk_tradeoff: "Too much risk for its expected return at your risk level",
    sector_limit:
      maxSectorWeight != null
        ? `Sector limit reached (${item.sector ?? "its sector"}, max ${formatPercent(maxSectorWeight, 0)})`
        : `Sector limit reached (${item.sector ?? "its sector"})`,
    risk_limit: "Left out to stay within your risk limit",
  };
  return labels[item.reason];
}

// Why a selected stock didn't get more weight; older recommendations only flag the per-stock cap.
function limitLabel(allocation: Recommendation["allocations"][number]): string | null {
  if (allocation.limit_reason === "sector_limit") return `Held back by the ${allocation.sector ?? "its"} sector limit`;
  if (allocation.limit_reason === "position_limit" || (allocation.limit_reason == null && allocation.at_position_limit)) {
    return "At your per-stock limit";
  }
  return null;
}

// Percentages on the plan page use one decimal.
function pct(value: string | number) {
  return formatPercent(value, 1);
}

function universeLabel(universe: string) {
  return universe === "NIFTY50" ? "NIFTY 50" : universe === "CUSTOM" ? "Your picked stocks" : universe;
}

// One sentence from the backend's not_selected reasons; counting only, no maths on values.
export function planReasonSentence(recommendation: Recommendation): string {
  // Older recommendations didn't record which stocks were left out: say nothing about them.
  if (recommendation.not_selected == null) {
    const n = recommendation.allocations.length;
    return n === 0
      ? "The plan keeps your capital in cash."
      : `The plan invests in ${n} stock${n === 1 ? "" : "s"} within your risk limits.`;
  }
  const notSelected = recommendation.not_selected;
  const falling = notSelected.filter((item) => item.reason === "negative_estimate").length;
  const sectorCapped = notSelected.filter((item) => item.reason === "sector_limit").length;
  const riskier = notSelected.filter((item) => item.reason === "risk_tradeoff" || item.reason === "risk_limit").length;
  const considered = recommendation.allocations.length + notSelected.length;
  const noData = recommendation.excluded.length;
  const scope = recommendation.universe === "NIFTY50" ? `the ${considered} NIFTY 50 stocks analysed` : `your ${considered} stocks`;

  let sentence: string;
  if (notSelected.length === 0) {
    sentence =
      considered === 0
        ? "No stock had enough data to analyse, so everything stays in cash."
        : `All of ${scope} are in the plan.`;
  } else {
    const leftOut = `${notSelected.length} of ${scope} ${notSelected.length === 1 ? "was" : "were"} left out`;
    const parts = [
      falling > 0 ? `${falling} the model expects to fall` : null,
      riskier > 0 ? `${riskier} add too much risk for their expected return` : null,
      sectorCapped > 0 ? `${sectorCapped} hit a sector limit` : null,
    ].filter(Boolean);
    sentence = `${leftOut}: ${parts.join(", ")}.`;
  }
  if (noData > 0) {
    sentence += ` ${noData} more had too little price history to analyse.`;
  }
  return sentence;
}

function planSlices(recommendation: Recommendation): DonutSlice[] {
  const stocks = [...recommendation.allocations]
    .sort((a, b) => Number(b.target_weight) - Number(a.target_weight))
    .map((a, index) => ({ name: a.ticker, weight: Number(a.target_weight), color: sliceColor(index) }));
  return Number(recommendation.cash_weight) > 0
    ? [...stocks, { name: "Cash", weight: Number(recommendation.cash_weight), color: CASH_COLOR }]
    : stocks;
}

type DrawerTarget = { ticker: string; mode: "selected" | "not_selected" };

type Props = {
  recommendation: Recommendation;
  adopted: boolean;
  adoptedAt: string | null;
  onAdopt: () => Promise<void>;
};

export function PlanView({ recommendation, adopted, adoptedAt, onAdopt }: Props) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [adopting, setAdopting] = useState(false);
  const [adoptError, setAdoptError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<DrawerTarget | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [preview, setPreview] = useState<HistoryPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [showAllNotSelected, setShowAllNotSelected] = useState(false);

  const recommendationId = recommendation.id;
  const portfolioId = recommendation.portfolio_id;

  useEffect(() => {
    if (!recommendationId) return;
    let cancelled = false;
    void (async () => {
      const accessToken = await getAccessToken();
      if (cancelled || !accessToken) return;
      try {
        const data = await apiFetch<HistoryPreview>(
          `/portfolios/${portfolioId}/recommendations/${recommendationId}/history-preview?period=1y`,
          accessToken,
        );
        if (!cancelled) setPreview(data);
      } catch (err) {
        console.error("Failed to load history preview:", err);
        if (!cancelled) setPreviewError(getErrorMessage(err, "The past-year comparison is unavailable right now."));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [portfolioId, recommendationId]);

  async function confirmAdopt() {
    try {
      setAdopting(true);
      setAdoptError(null);
      await onAdopt();
      setConfirmOpen(false);
    } catch (err) {
      console.error("Failed to adopt plan:", err);
      setAdoptError(getErrorMessage(err, "The plan couldn't be adopted. Please try again."));
    } finally {
      setAdopting(false);
    }
  }

  const slices = planSlices(recommendation);
  const notSelected: NotSelectedItem[] = recommendation.not_selected ?? [];
  const stockCount = recommendation.allocations.length;
  const drawerAllocation = drawer ? recommendation.allocations.find((a) => a.ticker === drawer.ticker) : undefined;
  const drawerNotSelected = drawer ? notSelected.find((n) => n.ticker === drawer.ticker) : undefined;
  const previewPoints = (preview?.points ?? []).map((p) => ({ date: p.date, primary: Number(p.mix), benchmark: Number(p.benchmark) }));

  return (
    <>
      <section className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
        <div className="grid lg:grid-cols-[1.5fr_0.8fr]">
          <div className="p-5 sm:p-7">
            <p className="text-xs font-bold uppercase tracking-widest text-primary">
              {adopted ? `Your active plan (since ${adoptedAt ? formatShortDate(adoptedAt) : "—"})` : "Proposed plan"}
            </p>
            <h2 className="mt-3 max-w-2xl text-2xl font-bold leading-snug">
              {stockCount > 0
                ? `Invest in ${stockCount} stock${stockCount === 1 ? "" : "s"} · keep ${formatPrice(recommendation.cash_amount)} in cash`
                : `Keep all ${formatPrice(recommendation.capital)} in cash for now`}
            </h2>
            <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground">{planReasonSentence(recommendation)}</p>
            <div className="mt-6 grid max-w-xl grid-cols-2 gap-3">
              <Metric
                label="Estimated yearly return"
                value={pct(recommendation.expected_portfolio_return)}
                info="A model estimate from past market data, not a guaranteed return."
              />
              <Metric
                label="Expected yearly swings"
                value={pct(recommendation.expected_portfolio_volatility)}
                info="The model's estimate of how much this mix may move up or down in a year (volatility)."
              />
            </div>
            {recommendation.return_model === "historical" && (
              <p className="mt-4 text-xs text-muted-foreground">ML forecasts were unavailable, so historical averages were used.</p>
            )}
            {!adopted && recommendationId && (
              <Button className="mt-6" onClick={() => setConfirmOpen(true)}>
                Adopt this plan <ArrowRight size={16} aria-hidden="true" />
              </Button>
            )}
            {adopted && (
              <p className="mt-6 flex items-center gap-2 text-sm font-semibold text-success">
                <CheckCircle2 size={16} aria-hidden="true" /> This is the plan your portfolio follows.
              </p>
            )}
          </div>
          <div className="border-t border-border bg-muted/30 p-4 lg:border-t-0 lg:border-l">
            <Donut slices={slices} centerLabel="Capital" centerValue={formatCompactINR(recommendation.capital)} />
            <ul className="grid grid-cols-3 gap-2 text-center text-xs">
              {slices.map((slice) => (
                <li key={slice.name} className="min-w-0">
                  <i className="mx-auto mb-1 block size-2 rounded-full" style={{ background: slice.color }} aria-hidden="true" />
                  <span className="block font-semibold tabular-nums">{pct(slice.weight)}</span>
                  <span className="block wrap-break-word">{slice.name === "Cash" ? "cash" : slice.name}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {adopted && recommendationId && (
        <OrderChecklist portfolioId={portfolioId} recommendationId={recommendationId} planCapital={recommendation.capital} />
      )}

      <Section title="In your plan" subtitle="Stocks selected by the model within your risk limits">
        {stockCount === 0 ? (
          <div className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            No stocks were selected; the plan keeps your capital in cash.
          </div>
        ) : (
          <>
            <div className="table-wrap hidden sm:block">
              <table>
                <thead>
                  <tr>
                    <th>Stock</th>
                    <th>Estimate</th>
                    <th>Weight</th>
                    <th>Amount</th>
                    <th>Source</th>
                    <th>
                      <span className="sr-only">Details</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {recommendation.allocations.map((a) => (
                    <tr key={a.ticker}>
                      <td>
                        <strong>{a.ticker}</strong>
                        {a.sector && <small>{a.sector}</small>}
                      </td>
                      <td className={cn("font-semibold tabular-nums", Number(a.expected_return) > 0 ? "text-success" : "text-destructive")}>
                        {pct(a.expected_return)}
                        {a.clipped && (
                          <span className="ml-1 text-[11px] font-medium text-muted-foreground" title="Estimate was capped to the model's historical range.">
                            (capped)
                          </span>
                        )}
                      </td>
                      <td className="tabular-nums">
                        {pct(a.target_weight)}
                        {limitLabel(a) && <small>{limitLabel(a)}</small>}
                      </td>
                      <td className="tabular-nums">{formatPrice(a.amount)}</td>
                      <td>
                        <SourcePill source={a.source} />
                      </td>
                      <td className="text-right">
                        <Button variant="outline" size="sm" onClick={() => setDrawer({ ticker: a.ticker, mode: "selected" })}>
                          Why? <CircleHelp size={14} aria-hidden="true" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                  <tr>
                    <td>
                      <strong>Cash</strong>
                    </td>
                    <td>—</td>
                    <td className="tabular-nums">{pct(recommendation.cash_weight)}</td>
                    <td className="tabular-nums">{formatPrice(recommendation.cash_amount)}</td>
                    <td />
                    <td />
                  </tr>
                </tbody>
              </table>
            </div>
            <ul className="space-y-3 sm:hidden" aria-label="In your plan">
              {recommendation.allocations.map((a) => (
                <li key={a.ticker} className="rounded-lg border border-border bg-card p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-bold">{a.ticker}</p>
                      {a.sector && <p className="text-xs text-muted-foreground">{a.sector}</p>}
                    </div>
                    <SourcePill source={a.source} />
                  </div>
                  <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <dt className="text-muted-foreground">Estimate</dt>
                      <dd className={cn("font-semibold", Number(a.expected_return) > 0 ? "text-success" : "text-destructive")}>
                        {pct(a.expected_return)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Weight</dt>
                      <dd className="font-semibold">{pct(a.target_weight)}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Amount</dt>
                      <dd className="font-semibold">{formatPrice(a.amount)}</dd>
                    </div>
                  </dl>
                  <Button variant="outline" size="sm" className="mt-3" onClick={() => setDrawer({ ticker: a.ticker, mode: "selected" })}>
                    Why? <CircleHelp size={14} aria-hidden="true" />
                  </Button>
                </li>
              ))}
              <li className="flex items-center justify-between rounded-lg border border-border bg-card p-4 text-sm">
                <span className="font-bold">Cash</span>
                <span className="font-semibold tabular-nums">
                  {pct(recommendation.cash_weight)} · {formatPrice(recommendation.cash_amount)}
                </span>
              </li>
            </ul>
          </>
        )}
      </Section>

      {notSelected.length > 0 && (
        <Section title="Considered, not bought" subtitle="Left out by the model or your risk limits">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Stock</th>
                  <th>Estimate</th>
                  <th>Reason</th>
                  <th>
                    <span className="sr-only">Details</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {(showAllNotSelected ? notSelected : notSelected.slice(0, NOT_SELECTED_PREVIEW)).map((item) => (
                  <tr key={item.ticker}>
                    <td>
                      <strong>{item.ticker}</strong>
                      {item.sector && <small>{item.sector}</small>}
                    </td>
                    <td className={cn("font-semibold tabular-nums", Number(item.expected_return) > 0 ? "text-success" : "text-destructive")}>
                      {pct(item.expected_return)}
                    </td>
                    <td>
                      <span className="inline-flex items-center gap-1.5 text-sm">
                        {item.reason === "negative_estimate" ? (
                          <ArrowDownRight size={15} className="text-destructive" aria-hidden="true" />
                        ) : (
                          <ShieldCheck size={15} className="text-warning-foreground" aria-hidden="true" />
                        )}
                        {notSelectedReasonLabel(item, recommendation.constraints.max_sector_weight)}
                      </span>
                    </td>
                    <td className="text-right">
                      <Button variant="outline" size="sm" onClick={() => setDrawer({ ticker: item.ticker, mode: "not_selected" })}>
                        Why? <CircleHelp size={14} aria-hidden="true" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {notSelected.length > NOT_SELECTED_PREVIEW && (
            <Button variant="ghost" size="sm" className="mt-3" onClick={() => setShowAllNotSelected(!showAllNotSelected)}>
              {showAllNotSelected ? `Show first ${NOT_SELECTED_PREVIEW}` : `Show all ${notSelected.length}`}
              <ChevronDown size={14} className={cn("transition", showAllNotSelected && "rotate-180")} aria-hidden="true" />
            </Button>
          )}
        </Section>
      )}

      {recommendation.excluded.length > 0 && (
        <p className="-mt-3 mb-4 text-xs text-muted-foreground">
          Not analysed (too little data):{" "}
          {recommendation.excluded.map((item) => `${item.ticker} (${item.reason})`).join(", ")}.
        </p>
      )}

      {recommendationId && (
        <Section
          title="Past year of this mix vs NIFTY 50 (for context only)"
          subtitle={
            preview
              ? `Both start at ${formatPrice(recommendation.capital)} on ${formatDate(preview.start)}. ${preview.note}`
              : "Historical context, not a forecast."
          }
        >
          <div className="rounded-lg border border-border bg-card p-3 sm:p-5">
            {previewError ? (
              <ChartEmpty message={previewError} />
            ) : preview === null ? (
              <Skeleton className="h-72" />
            ) : previewPoints.length < 2 ? (
              <ChartEmpty message="Not enough price history for this mix yet." />
            ) : (
              <>
                <ChartLegend
                  items={[
                    { label: "This mix", color: "var(--primary)" },
                    { label: "NIFTY 50", color: "var(--chart-benchmark)", dashed: true },
                  ]}
                />
                <CompareLineChart data={previewPoints} primaryLabel="This mix" />
              </>
            )}
          </div>
        </Section>
      )}

      <div className="mb-4 rounded-lg border border-border bg-card">
        <Button
          variant="ghost"
          className="h-auto w-full justify-between rounded-lg px-5 py-4"
          aria-expanded={advancedOpen}
          aria-controls="advanced-details"
          onClick={() => setAdvancedOpen(!advancedOpen)}
        >
          <span>Advanced details</span>
          <ChevronDown size={17} className={cn("transition", advancedOpen && "rotate-180")} aria-hidden="true" />
        </Button>
        {advancedOpen && (
          <dl id="advanced-details" className="grid gap-5 border-t border-border p-5 text-sm sm:grid-cols-3">
            {[
              ["Maximum per stock", pct(recommendation.constraints.max_position_weight)],
              ["Maximum per sector", recommendation.constraints.max_sector_weight != null ? pct(recommendation.constraints.max_sector_weight) : "—"],
              ["Target volatility", pct(recommendation.constraints.target_volatility)],
              ["Method", recommendation.return_model === "ml" ? "ML-assisted analysis" : "Historical averages"],
              ["Model version", recommendation.model_version ?? "—"],
              [
                "Forecast date",
                recommendation.forecast_as_of
                  ? `${formatDate(recommendation.forecast_as_of)}${
                      recommendation.forecast_source === "precomputed"
                        ? " (nightly model run)"
                        : recommendation.forecast_source === "on_request"
                          ? " (computed on request)"
                          : ""
                    }`
                  : "—",
              ],
              [
                "Universe",
                `${universeLabel(recommendation.universe)}${recommendation.universe_as_of ? ` · list of ${formatDate(recommendation.universe_as_of)}` : ""}`,
              ],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="mt-1 font-bold break-all">{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>

      <Modal open={confirmOpen} onClose={() => setConfirmOpen(false)} labelledBy="adopt-title" describedBy="adopt-body">
        <div className="p-6">
          <div className="mb-4 grid size-11 place-items-center rounded-md bg-primary/10 text-primary">
            <CheckCircle2 aria-hidden="true" />
          </div>
          <h2 id="adopt-title" className="text-xl font-bold">
            Adopt this plan?
          </h2>
          <p id="adopt-body" className="mt-3 text-sm leading-6 text-muted-foreground">
            Nothing is bought. Next you&apos;ll get a list of orders to place at your broker.
          </p>
          {adoptError && (
            <div className="mt-4">
              <Notice tone="error">{adoptError}</Notice>
            </div>
          )}
          <div className="mt-7 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setConfirmOpen(false)} disabled={adopting}>
              Cancel
            </Button>
            <Button onClick={() => void confirmAdopt()} disabled={adopting} autoFocus>
              {adopting ? "Adopting…" : "Adopt plan"}
            </Button>
          </div>
        </div>
      </Modal>

      {drawer && (
        <StockAnalysisDrawer
          key={drawer.ticker}
          ticker={drawer.ticker}
          sector={drawerAllocation?.sector ?? drawerNotSelected?.sector ?? null}
          mode={drawer.mode}
          portfolioId={portfolioId}
          recommendationId={recommendationId}
          drivers={drawerAllocation?.drivers}
          typicalEstimate={drawerAllocation?.typical_estimate ?? null}
          clipped={drawerAllocation?.clipped ?? false}
          onClose={() => setDrawer(null)}
        />
      )}
    </>
  );
}
