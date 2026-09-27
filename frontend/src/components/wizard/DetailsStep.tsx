import { useLayoutEffect, useRef, useState } from "react";
import { amountInWords, groupIndian, sanitizeAmount } from "./amount";

export type PortfolioDetails = {
  name: string;
  purpose: string;
  initial_capital: string;
};

type Props = {
  details: PortfolioDetails;
  errors: Partial<Record<keyof PortfolioDetails, string>>;
  onChange: (details: PortfolioDetails) => void;
};

const QUICK_PICKS = ["50000", "100000", "500000", "1000000"];

export function DetailsStep({ details, errors, onChange }: Props) {
  const [touched, setTouched] = useState<Partial<Record<keyof PortfolioDetails, boolean>>>({});
  const capitalRef = useRef<HTMLInputElement>(null);
  // Number of digits/points before the caret, so it can be restored after re-grouping.
  const caretSignificant = useRef<number | null>(null);

  useLayoutEffect(() => {
    const input = capitalRef.current;
    const target = caretSignificant.current;
    if (!input || target === null) return;
    caretSignificant.current = null;
    let seen = 0;
    let pos = 0;
    while (pos < input.value.length && seen < target) {
      if (/[\d.]/.test(input.value[pos])) seen += 1;
      pos += 1;
    }
    input.setSelectionRange(pos, pos);
  }, [details.initial_capital]);

  function update(field: keyof PortfolioDetails, value: string) {
    onChange({ ...details, [field]: value });
  }

  function touch(field: keyof PortfolioDetails) {
    setTouched((prev) => ({ ...prev, [field]: true }));
  }

  function errorFor(field: keyof PortfolioDetails) {
    const message = errors[field];
    // Length errors are shown immediately; "missing" errors only once the field has been visited.
    if (!message) return null;
    return touched[field] || details[field].trim() !== "" ? message : null;
  }

  const nameError = errorFor("name");
  const purposeError = errorFor("purpose");
  const capitalError = errorFor("initial_capital");
  const words = amountInWords(details.initial_capital);

  return (
    <div className="wizard-stack">
      <div className="field-group">
        <label className="field-label" htmlFor="portfolio-name">Portfolio name</label>
        <input
          id="portfolio-name"
          value={details.name}
          onChange={(e) => update("name", e.target.value)}
          onBlur={() => touch("name")}
          placeholder="For example: Long-term Growth"
          aria-invalid={nameError ? true : undefined}
          aria-describedby={nameError ? "portfolio-name-error" : undefined}
        />
        {nameError && <p id="portfolio-name-error" className="wizard-field-error">{nameError}</p>}
      </div>

      <div className="field-group">
        <label className="field-label" htmlFor="portfolio-purpose">Purpose <span className="wizard-optional">(optional)</span></label>
        <input
          id="portfolio-purpose"
          value={details.purpose}
          onChange={(e) => update("purpose", e.target.value)}
          onBlur={() => touch("purpose")}
          placeholder="Retirement, home purchase, wealth creation..."
          aria-invalid={purposeError ? true : undefined}
          aria-describedby={purposeError ? "portfolio-purpose-error" : undefined}
        />
        {purposeError && <p id="portfolio-purpose-error" className="wizard-field-error">{purposeError}</p>}
      </div>

      <div className="field-group">
        <label className="field-label" htmlFor="portfolio-capital">Investment capital</label>
        <div className="currency-field">
          <span className="prefix" aria-hidden="true">₹</span>
          <input
            ref={capitalRef}
            id="portfolio-capital"
            inputMode="decimal"
            autoComplete="off"
            value={groupIndian(details.initial_capital)}
            onChange={(e) => {
              const caret = e.target.selectionStart ?? e.target.value.length;
              caretSignificant.current = e.target.value.slice(0, caret).replace(/[^\d.]/g, "").length;
              update("initial_capital", sanitizeAmount(e.target.value));
            }}
            onBlur={() => touch("initial_capital")}
            placeholder="5,00,000"
            aria-invalid={capitalError ? true : undefined}
            aria-describedby={capitalError ? "portfolio-capital-error" : "portfolio-capital-words"}
          />
        </div>
        <div className="wizard-chips" role="group" aria-label="Quick amounts">
          {QUICK_PICKS.map((amount) => (
            <button
              key={amount}
              type="button"
              className={`wizard-chip ${details.initial_capital === amount ? "is-active" : ""}`}
              aria-pressed={details.initial_capital === amount}
              onClick={() => {
                update("initial_capital", amount);
                touch("initial_capital");
              }}
            >
              ₹{groupIndian(amount)}
            </button>
          ))}
        </div>
        {capitalError ? (
          <p id="portfolio-capital-error" className="wizard-field-error">{capitalError}</p>
        ) : (
          <p id="portfolio-capital-words" className="field-hint" aria-live="polite">
            {words ?? " "}
          </p>
        )}
      </div>
    </div>
  );
}
