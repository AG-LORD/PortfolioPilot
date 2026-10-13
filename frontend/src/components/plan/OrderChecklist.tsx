"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Notice, Section, Skeleton } from "@/components/ui/primitives";
import { apiFetch, getAccessToken } from "@/lib/api";
import { cn } from "@/lib/cn";
import { getErrorMessage } from "@/lib/errors";
import { formatPrice } from "@/lib/format";
import type { BatchTradeItem, RebalancePreview, Transaction } from "@/lib/types/api";

type Row = {
  key: string;
  checked: boolean;
  side: "BUY" | "SELL";
  ticker: string;
  shares: string;
  price: string;
  fees: string;
  estimatedAmount: string;
};

type Props = {
  portfolioId: string;
  // The adopted recommendation; the proposal targets it.
  recommendationId: string;
  // The recommendation's capital; a note appears when the portfolio's value has moved away from it.
  planCapital: string;
  // Called after orders are recorded so the page can refresh anything that depends on holdings.
  onRecorded?: () => void;
};

function rowsFrom(preview: RebalancePreview): Row[] {
  return preview.trades.map((trade) => ({
    key: `${trade.side}-${trade.ticker}`,
    checked: false,
    side: trade.side,
    ticker: trade.ticker,
    shares: String(trade.quantity),
    // Pre-filled with the backend's estimate rounded to paise; the user enters the fill price.
    price: Number(trade.estimated_price).toFixed(2),
    fees: "0",
    estimatedAmount: trade.estimated_gross_amount,
  }));
}

function rowError(row: Row): string | null {
  const shares = Number(row.shares);
  if (!Number.isInteger(shares) || shares < 1) return "Shares must be a whole number of at least 1";
  if (!(Number(row.price) > 0)) return "Enter the price you paid";
  if (!(Number(row.fees) >= 0)) return "Fees can't be negative";
  return null;
}

const CELL_INPUT = "h-8 rounded-md border border-input bg-background px-2 text-sm tabular-nums";

// The order list is re-scaled to the current value; beyond this drift the user should know.
const VALUE_CHANGE_NOTE_THRESHOLD = 0.01;

export function OrderChecklist({ portfolioId, recommendationId, planCapital, onRecorded }: Props) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [portfolioValue, setPortfolioValue] = useState<string | null>(null);
  const [holdingCount, setHoldingCount] = useState<number | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(
    async (accessToken: string) => {
      try {
        const preview = await apiFetch<RebalancePreview>(
          `/portfolios/${portfolioId}/rebalance-proposals/preview?recommendation_id=${encodeURIComponent(recommendationId)}`,
          accessToken,
        );
        setRows(rowsFrom(preview));
        setPortfolioValue(preview.portfolio_value);
        setLoadError(null);
      } catch (err) {
        console.error("Failed to load order checklist:", err);
        setLoadError(getErrorMessage(err, "The order checklist is unavailable right now."));
      }
    },
    [portfolioId, recommendationId],
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const accessToken = await getAccessToken();
      if (cancelled) return;
      if (!accessToken) {
        setLoadError("You are signed out. Please log in again.");
        return;
      }
      await load(accessToken);
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  function update(key: string, patch: Partial<Row>) {
    setRows((current) => current?.map((row) => (row.key === key ? { ...row, ...patch } : row)) ?? current);
  }

  const ticked = rows?.filter((row) => row.checked) ?? [];
  const firstInvalid = ticked.map(rowError).find((error) => error !== null) ?? null;

  async function recordTicked() {
    if (ticked.length === 0 || firstInvalid) return;
    const accessToken = await getAccessToken();
    if (!accessToken) {
      setSubmitError("You are signed out. Please log in again.");
      return;
    }
    const body: BatchTradeItem[] = ticked.map((row) => ({
      side: row.side,
      ticker: row.ticker,
      quantity: String(Number(row.shares)),
      price: Number(row.price).toFixed(2),
      fees: Number(row.fees).toFixed(2),
    }));
    try {
      setSubmitting(true);
      setSubmitError(null);
      setMessage(null);
      await apiFetch<Transaction[]>(`/portfolios/${portfolioId}/transactions/batch`, accessToken, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const [, holdings] = await Promise.all([
        load(accessToken),
        apiFetch<unknown[]>(`/portfolios/${portfolioId}/holdings`, accessToken),
      ]);
      setHoldingCount(holdings.length);
      setMessage(`Recorded ${body.length} order${body.length === 1 ? "" : "s"}.`);
      onRecorded?.();
    } catch (err) {
      console.error("Failed to record orders:", err);
      setSubmitError(getErrorMessage(err, "The orders couldn't be recorded. Nothing was saved."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Section title="Order checklist" subtitle="Tick orders after you place them at your broker, adjust shares and prices to your fills, then record them.">
      {loadError && <Notice tone="error">{loadError}</Notice>}
      {portfolioValue !== null &&
        Number(planCapital) > 0 &&
        Math.abs(Number(portfolioValue) - Number(planCapital)) / Number(planCapital) > VALUE_CHANGE_NOTE_THRESHOLD && (
          <div className="mb-4">
            <Notice tone="info">
              Your portfolio is now {formatPrice(portfolioValue)}. The order list scales this plan to your current value. Generate a
              new recommendation to re-plan with the new amount.
            </Notice>
          </div>
        )}
      {!loadError && rows === null && <Skeleton className="h-32" />}
      {message && (
        <div className="mb-4">
          <Notice tone="success">
            {message}
            {holdingCount !== null && ` You now hold ${holdingCount} stock${holdingCount === 1 ? "" : "s"}.`}
          </Notice>
        </div>
      )}
      {rows !== null && rows.length === 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-success/25 bg-success/10 p-4" role="status">
          <CheckCircle2 className="text-success" size={20} aria-hidden="true" />
          <p className="font-semibold">Your holdings match your plan ✓</p>
        </div>
      )}
      {rows !== null && rows.length > 0 && (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="w-12">
                    <span className="sr-only">Placed</span>
                  </th>
                  <th>Side</th>
                  <th>Ticker</th>
                  <th>Shares</th>
                  <th>Price</th>
                  <th>Fees</th>
                  <th>Est. amount</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key}>
                    <td>
                      <input
                        aria-label={`Placed ${row.side.toLowerCase()} ${row.ticker} order`}
                        type="checkbox"
                        checked={row.checked}
                        onChange={(e) => update(row.key, { checked: e.target.checked })}
                        className="size-4 accent-primary"
                      />
                    </td>
                    <td>
                      <span className={cn("text-xs font-bold", row.side === "BUY" ? "text-success" : "text-destructive")}>{row.side}</span>
                    </td>
                    <td>
                      <strong>{row.ticker}</strong>
                    </td>
                    <td>
                      <input
                        aria-label={`${row.ticker} shares`}
                        type="number"
                        inputMode="numeric"
                        min="1"
                        step="1"
                        value={row.shares}
                        onChange={(e) => update(row.key, { shares: e.target.value })}
                        className={cn(CELL_INPUT, "w-20")}
                      />
                    </td>
                    <td>
                      <div className="flex items-center">
                        <span className="mr-1 text-muted-foreground">₹</span>
                        <input
                          aria-label={`${row.ticker} price`}
                          type="number"
                          inputMode="decimal"
                          min="0.01"
                          step="0.01"
                          value={row.price}
                          onChange={(e) => update(row.key, { price: e.target.value })}
                          className={cn(CELL_INPUT, "w-28")}
                        />
                      </div>
                    </td>
                    <td>
                      <div className="flex items-center">
                        <span className="mr-1 text-muted-foreground">₹</span>
                        <input
                          aria-label={`${row.ticker} fees`}
                          type="number"
                          inputMode="decimal"
                          min="0"
                          step="0.01"
                          value={row.fees}
                          onChange={(e) => update(row.key, { fees: e.target.value })}
                          className={cn(CELL_INPUT, "w-24")}
                        />
                      </div>
                    </td>
                    <td className="font-semibold tabular-nums">{formatPrice(row.estimatedAmount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">Est. amount is for the proposed shares at the estimated price.</p>
          {submitError && (
            <div className="mt-4">
              <Notice tone="error">{submitError}</Notice>
            </div>
          )}
          <div className="mt-4 flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <ShieldCheck size={15} aria-hidden="true" />
              PortfolioPilot never places orders.
            </p>
            <div className="flex flex-col items-start gap-1 sm:items-end">
              <Button disabled={ticked.length === 0 || firstInvalid !== null || submitting} onClick={() => void recordTicked()}>
                {submitting ? "Recording…" : `Record ticked orders${ticked.length ? ` (${ticked.length})` : ""}`}
              </Button>
              {firstInvalid && <p className="text-xs text-destructive">{firstInvalid}</p>}
            </div>
          </div>
        </>
      )}
    </Section>
  );
}
