"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { PriceAreaChart } from "@/components/charts/Charts";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Metric, Notice, Skeleton } from "@/components/ui/primitives";
import { apiFetch, getAccessToken } from "@/lib/api";
import { cn } from "@/lib/cn";
import { getErrorMessage } from "@/lib/errors";
import { formatDate, formatPercent, formatPrice } from "@/lib/format";
import type { AllocationDriver } from "@/lib/types/api";

type StockAnalysis = {
  ticker: string;
  current_price: string | null;
  current_quote_available: boolean;
  latest_close: string;
  latest_close_date: string;
  historical_prices: Array<{
    date: string;
    open: string;
    high: string;
    low: string;
    close: string;
    volume: number;
  }>;
  technical_indicators: Record<string, string>;
  return_20d: string | null;
  return_60d: string | null;
  return_252d: string | null;
  annualized_volatility_252d: string | null;
  portfolio_id: string | null;
  recommendation_id: string | null;
  expected_return_annual: string | null;
  expected_return_source: "historical" | "ml" | null;
  model_version: string | null;
  target_weight: string | null;
  current_weight: string | null;
};

type IndicatorInfo = { label: string; definition: string; format: "percent" | "number" };

// Static labels and definitions for the backend's FEATURE_COLUMNS. No values are interpreted here.
const INDICATORS: Record<string, IndicatorInfo> = {
  close_to_sma_20: { label: "Price vs 20-day average", definition: "Price vs its 20-day average (0.05 = 5% above)", format: "percent" },
  close_to_sma_50: { label: "Price vs 50-day average", definition: "Price vs its 50-day average", format: "percent" },
  sma_20_to_sma_50: {
    label: "20-day vs 50-day average",
    definition: "Short-term trend vs medium-term trend (positive = short-term trend is stronger)",
    format: "percent",
  },
  momentum_5: { label: "5-day momentum", definition: "Price change over the last 5 trading days", format: "percent" },
  momentum_20: { label: "20-day momentum", definition: "Price change over the last 20 trading days", format: "percent" },
  momentum_60: { label: "60-day momentum", definition: "Price change over the last 60 trading days", format: "percent" },
  rsi_14: {
    label: "RSI (14)",
    definition: "Relative Strength Index, 0–100; above 70 often means strong recent buying, below 30 strong selling",
    format: "number",
  },
  macd_line: { label: "MACD line", definition: "MACD: gap between 12- and 26-day trends, relative to price", format: "percent" },
  macd_signal: { label: "MACD signal", definition: "9-day average of the MACD line", format: "percent" },
  macd_hist: { label: "MACD histogram", definition: "MACD minus its signal (positive = momentum rising)", format: "percent" },
  atr_14: {
    label: "ATR (14)",
    definition: "Average daily price range over 14 days, relative to price (higher = more volatile)",
    format: "percent",
  },
  realized_vol_20: { label: "20-day volatility", definition: "Annualized volatility of the last 20 days of returns", format: "percent" },
};

const UNKNOWN_INDICATOR_DEFINITION = "Technical input used by the model.";
const TOP_DRIVERS = 5;

function formatIndicator(name: string, value: string): string {
  const info = INDICATORS[name];
  if (!info) return Number(value).toFixed(4);
  return info.format === "percent" ? formatPercent(value, 1) : Number(value).toFixed(1);
}

function percentOrDash(value: string | null, fallback = "—") {
  return value === null ? fallback : formatPercent(value, 1);
}

function signedPercent(value: string) {
  return `${Number(value) > 0 ? "+" : ""}${formatPercent(value, 1)}`;
}

function WhyThisEstimate({
  drivers,
  typicalEstimate,
  clipped,
}: {
  drivers: AllocationDriver[];
  typicalEstimate: string | null;
  clipped: boolean;
}) {
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? drivers : drivers.slice(0, TOP_DRIVERS);
  // Bar length is only a visual scale against the largest contribution shown.
  const largest = Math.max(...shown.map((d) => Math.abs(Number(d.contribution))), 0) || 1;

  return (
    <section className="mt-7">
      <h3 className="font-bold">Why this estimate</h3>
      {typicalEstimate !== null && (
        <p className="mt-1 text-xs text-muted-foreground">
          A stock with typical inputs would be estimated at {formatPercent(typicalEstimate, 1)}.
        </p>
      )}
      {clipped && (
        <p className="mt-1 text-xs text-muted-foreground">
          The estimate was capped; the contributions explain the model&apos;s raw estimate before capping.
        </p>
      )}
      <ul className="mt-3 space-y-2">
        {shown.map((driver) => {
          const contribution = Number(driver.contribution);
          const positive = contribution > 0;
          const negative = contribution < 0;
          const width = `${(Math.abs(contribution) / largest) * 50}%`;
          return (
            <li key={driver.feature} className="rounded-md border border-border p-3">
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="font-semibold">{INDICATORS[driver.feature]?.label ?? driver.feature.replaceAll("_", " ")}</span>
                <span className={cn("font-semibold tabular-nums", positive && "text-success", negative && "text-destructive")}>
                  {signedPercent(driver.contribution)}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">Value {formatIndicator(driver.feature, driver.value)}</p>
              {/* Centred track: positive bars grow right, negative bars grow left. */}
              <div className="relative mt-2 h-1.5 rounded-full bg-muted" aria-hidden="true">
                <span className="absolute inset-y-0 left-1/2 w-px bg-border" />
                <span
                  className={cn("absolute inset-y-0 rounded-full", positive ? "left-1/2 bg-success" : "right-1/2 bg-destructive")}
                  style={{ width }}
                />
              </div>
            </li>
          );
        })}
      </ul>
      {drivers.length > TOP_DRIVERS && (
        <Button variant="ghost" size="sm" className="mt-2" onClick={() => setShowAll((value) => !value)}>
          {showAll ? `Show top ${TOP_DRIVERS}` : `Show all ${drivers.length}`}
        </Button>
      )}
    </section>
  );
}

type Props = {
  ticker: string;
  sector?: string | null;
  // "selected": in the plan; "not_selected": considered but left out.
  mode: "selected" | "not_selected";
  portfolioId: string;
  recommendationId?: string;
  // From the recommendation response; the drawer never refetches them.
  drivers?: AllocationDriver[];
  typicalEstimate?: string | null;
  clipped?: boolean;
  // The shrunk estimate the plan used; null on recommendations saved before shrinkage.
  estimateUsed?: string | null;
  onClose: () => void;
};

export function StockAnalysisDrawer({
  ticker,
  sector,
  mode,
  portfolioId,
  recommendationId,
  drivers = [],
  typicalEstimate = null,
  clipped = false,
  estimateUsed = null,
  onClose,
}: Props) {
  const hasDrivers = drivers.length > 0;
  const [analysis, setAnalysis] = useState<StockAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const accessToken = await getAccessToken();
      if (cancelled) return;
      if (!accessToken) {
        setError("You are signed out. Please log in again.");
        return;
      }
      const query = new URLSearchParams({ portfolio_id: portfolioId });
      if (recommendationId) query.set("recommendation_id", recommendationId);
      try {
        const details = await apiFetch<StockAnalysis>(`/stocks/${encodeURIComponent(ticker)}/analysis?${query.toString()}`, accessToken);
        if (!cancelled) setAnalysis(details);
      } catch (err) {
        console.error("Failed to load stock analysis:", err);
        if (!cancelled) setError(getErrorMessage(err, "Stock analysis is unavailable."));
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [ticker, portfolioId, recommendationId]);

  const prices = (analysis?.historical_prices ?? []).slice(-90).map((p) => ({ date: p.date, close: Number(p.close) }));

  return (
    <Modal open onClose={onClose} labelledBy="stock-analysis-title" variant="sheet">
      <div className="h-full overflow-y-auto p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-primary">
              {mode === "selected" ? "Why it is in your plan" : "Why it was left out"}
            </p>
            <h2 id="stock-analysis-title" className="mt-2 text-2xl font-bold">
              {ticker}
            </h2>
            {sector && <p className="text-sm text-muted-foreground">{sector}</p>}
          </div>
          <Button variant="ghost" size="icon" aria-label="Close details" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </Button>
        </div>

        {error && (
          <div className="mt-6">
            <Notice tone="error">{error}</Notice>
          </div>
        )}
        {!error && !analysis && (
          <div className="mt-7 space-y-3">
            <Skeleton className="h-24" />
            <Skeleton className="h-44" />
          </div>
        )}

        {analysis && (
          <>
            <div className="mt-7 grid grid-cols-2 gap-3">
              {estimateUsed !== null && (
                <Metric
                  label="Estimate used for your plan"
                  value={formatPercent(estimateUsed, 1)}
                  info="Model estimates are pulled toward the average across stocks to avoid over-confidence."
                />
              )}
              <Metric
                label={estimateUsed !== null ? "Model's raw estimate" : "Estimated return"}
                value={percentOrDash(analysis.expected_return_annual, "n/a")}
                note={
                  analysis.expected_return_source === null
                    ? undefined
                    : analysis.expected_return_source === "ml"
                      ? "ML forecast"
                      : "Historical fallback"
                }
                info="A model estimate from past market data, not a guaranteed return."
              />
              <Metric
                label="Portfolio weight"
                value={percentOrDash(analysis.target_weight, "0%")}
                note={analysis.current_weight !== null ? `You hold ${formatPercent(analysis.current_weight, 1)} now` : undefined}
              />
            </div>

            {!analysis.current_quote_available && (
              <p className="mt-4 text-xs text-muted-foreground">
                Current quote unavailable; figures use adjusted daily history through {formatDate(analysis.latest_close_date)}.
              </p>
            )}

            {prices.length > 1 && (
              <section className="mt-7">
                <h3 className="font-bold">Recent price movement</h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  Adjusted daily close, latest 90 sessions · last {formatPrice(analysis.latest_close)} on {formatDate(analysis.latest_close_date)}
                </p>
                <div className="mt-3">
                  <PriceAreaChart points={prices} />
                </div>
              </section>
            )}

            {hasDrivers && <WhyThisEstimate drivers={drivers} typicalEstimate={typicalEstimate} clipped={clipped} />}
            {hasDrivers && (
              <p className="mt-2 text-xs text-muted-foreground">
                Contributions are approximate: each shows how the estimate changes if that input were typical. They explain the
                model, not the market.
              </p>
            )}

            <section className="mt-7">
              <h3 className="font-bold">Recent performance</h3>
              <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
                {[
                  ["20-session return", analysis.return_20d],
                  ["60-session return", analysis.return_60d],
                  ["252-session return", analysis.return_252d],
                  ["Annualized volatility", analysis.annualized_volatility_252d],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-md border border-border p-3">
                    <dt className="text-xs text-muted-foreground">{label}</dt>
                    <dd className="mt-1 font-semibold tabular-nums">{percentOrDash(value)}</dd>
                  </div>
                ))}
              </dl>
            </section>

            <section className="mt-7">
              <h3 className="font-bold">What the model sees</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                Technical indicators at the latest close ({formatDate(analysis.latest_close_date)}); not the saved inputs of an older
                recommendation.
              </p>
              {Object.keys(analysis.technical_indicators).length === 0 ? (
                <p className="mt-3 text-sm text-muted-foreground">Not enough adjusted history to calculate indicators.</p>
              ) : (
                <div className="mt-3 space-y-3">
                  {Object.entries(analysis.technical_indicators).map(([name, value]) => (
                    <div key={name} className="rounded-md border border-border p-4">
                      <div className="flex items-baseline justify-between gap-3">
                        <p className="text-sm font-semibold">{INDICATORS[name]?.label ?? name.replaceAll("_", " ")}</p>
                        <p className="text-sm font-semibold tabular-nums">{formatIndicator(name, value)}</p>
                      </div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        {INDICATORS[name]?.definition ?? UNKNOWN_INDICATOR_DEFINITION}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <p className="mt-7 text-xs leading-5 text-muted-foreground">
              Model estimates can be wrong. Use this as decision support, not a guarantee.
              {analysis.model_version && ` Model ${analysis.model_version}.`}
            </p>
          </>
        )}
      </div>
    </Modal>
  );
}
