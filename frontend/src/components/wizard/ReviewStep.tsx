import type { ReactNode } from "react";
import { formatCurrency, formatPercent } from "@/lib/format";
import type { RiskProfileCreatePayload } from "@/lib/riskMapping";
import type { StockSelection } from "@/lib/stockSelection";
import type { PortfolioDetails } from "./DetailsStep";

type Props = {
  profile: RiskProfileCreatePayload;
  details: PortfolioDetails;
  selection: StockSelection;
  onEdit: (step: number) => void;
  disabled?: boolean;
};

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function ReviewStep({ profile, details, selection, onEdit, disabled }: Props) {
  const rows: { label: string; value: ReactNode; hint?: ReactNode; step: number }[] = [
    {
      label: "Risk profile",
      value: capitalize(profile.category),
      hint: `Max ${formatPercent(profile.max_position_weight)} per stock · ~${formatPercent(profile.target_volatility)} yearly ups and downs`,
      step: 1,
    },
    {
      label: "Portfolio",
      value: details.name.trim(),
      hint: details.purpose.trim() || undefined,
      step: 2,
    },
    { label: "Capital", value: formatCurrency(details.initial_capital), step: 2 },
    {
      label: "Stocks",
      value:
        selection.mode === "nifty50"
          ? "All NIFTY 50"
          : `${selection.tickers.length} stock${selection.tickers.length === 1 ? "" : "s"}`,
      hint: selection.mode === "custom" ? selection.tickers.join(", ") : undefined,
      step: 3,
    },
    { label: "Method", value: "ML-assisted analysis", step: 3 },
  ];

  return (
    <div className="wizard-stack">
      <dl className="wizard-summary">
        {rows.map((row) => (
          <div key={row.label} className="wizard-summary-row">
            <dt>{row.label}</dt>
            <dd>
              <span className="wizard-summary-value">{row.value}</span>
              {row.hint && <span className="wizard-summary-hint">{row.hint}</span>}
            </dd>
            <button
              type="button"
              className="wizard-link-button"
              onClick={() => onEdit(row.step)}
              disabled={disabled}
              aria-label={`Edit ${row.label.toLowerCase()}`}
            >
              Edit
            </button>
          </div>
        ))}
      </dl>

      <section className="wizard-next" aria-labelledby="wizard-next-title">
        <h3 id="wizard-next-title">What happens next</h3>
        <ol>
          <li>PortfolioPilot analyses your selected stocks.</li>
          <li>You get a recommended split of your money.</li>
          <li>Nothing is bought automatically.</li>
        </ol>
      </section>
    </div>
  );
}
