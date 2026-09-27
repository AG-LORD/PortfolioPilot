import { CASH_COLOR, sliceColor } from "@/components/charts/Charts";
import { formatPercent } from "@/lib/format";
import type { HoldingValuation, PortfolioDrift, RiskAnalytics } from "@/lib/types/api";

type Props = {
  holdingCount: number;
  drift: PortfolioDrift | null;
  valuationHoldings: HoldingValuation[] | null;
  riskAnalytics: RiskAnalytics | null;
};

type Segment = { label: string; weight: number; color: string };

// Groups the backend's current weights (drift) by each holding's sector.
function sectorSegments(drift: PortfolioDrift, holdings: HoldingValuation[] | null): Segment[] {
  const sectorOf = new Map((holdings ?? []).map((h) => [h.ticker, h.sector ?? "Other"]));
  const bySector = new Map<string, number>();
  let cash = 0;
  for (const position of drift.positions) {
    const weight = Number(position.current_weight ?? 0);
    if (weight <= 0) continue;
    if (position.ticker === "CASH") {
      cash = weight;
      continue;
    }
    const sector = sectorOf.get(position.ticker) ?? "Other";
    bySector.set(sector, (bySector.get(sector) ?? 0) + weight);
  }
  const sectors = [...bySector.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([label, weight], index) => ({ label, weight, color: sliceColor(index) }));
  return cash > 0 ? [...sectors, { label: "Cash", weight: cash, color: CASH_COLOR }] : sectors;
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 font-bold tabular-nums">{value}</dd>
      {note && <dd className="text-xs text-muted-foreground">{note}</dd>}
    </div>
  );
}

export function PortfolioHealth({ holdingCount, drift, valuationHoldings, riskAnalytics }: Props) {
  const weightsAvailable = drift !== null && drift.valuation_complete;
  const stocks = weightsAvailable
    ? drift.positions.filter((p) => p.ticker !== "CASH" && Number(p.current_weight ?? 0) > 0)
    : [];
  const largest = stocks.reduce<(typeof stocks)[number] | null>(
    (best, p) => (best === null || Number(p.current_weight) > Number(best.current_weight) ? p : best),
    null,
  );
  const cash = weightsAvailable ? drift.positions.find((p) => p.ticker === "CASH") : undefined;
  const segments = weightsAvailable ? sectorSegments(drift, valuationHoldings) : [];
  const showVolatility = riskAnalytics?.annualized_volatility != null;
  const showSharpe = riskAnalytics?.sharpe_ratio != null;

  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Stat label="Holdings" value={`${holdingCount} stock${holdingCount === 1 ? "" : "s"}`} />
        <Stat
          label="Largest holding"
          value={largest ? formatPercent(largest.current_weight ?? 0, 1) : "—"}
          note={largest ? largest.ticker : undefined}
        />
        <Stat label="Cash" value={cash?.current_weight != null ? formatPercent(cash.current_weight, 1) : "—"} />
        {showVolatility && riskAnalytics && (
          <Stat label="Annualized volatility" value={formatPercent(riskAnalytics.annualized_volatility ?? 0, 1)} />
        )}
        {showSharpe && riskAnalytics && <Stat label="Sharpe ratio" value={Number(riskAnalytics.sharpe_ratio).toFixed(2)} />}
      </dl>

      <div className="mt-6">
        <p className="text-xs font-medium text-muted-foreground">Sector mix</p>
        {segments.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">
            {weightsAvailable ? "No holdings yet." : "Appears when current prices are available for every holding."}
          </p>
        ) : (
          <>
            <div className="mt-2 flex h-3 overflow-hidden rounded-full bg-muted" role="img" aria-label="Sector mix">
              {segments.map((segment) => (
                <span key={segment.label} style={{ width: `${segment.weight * 100}%`, background: segment.color }} />
              ))}
            </div>
            <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs">
              {segments.map((segment) => (
                <li key={segment.label} className="flex items-center gap-1.5">
                  <i className="size-2.5 rounded-sm" style={{ background: segment.color }} aria-hidden="true" />
                  {segment.label} <span className="font-semibold tabular-nums">{formatPercent(segment.weight, 1)}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
      {!showVolatility && (
        <p className="mt-5 text-xs text-muted-foreground">Volatility and Sharpe ratio appear after about 30 days of daily snapshots.</p>
      )}
    </div>
  );
}
