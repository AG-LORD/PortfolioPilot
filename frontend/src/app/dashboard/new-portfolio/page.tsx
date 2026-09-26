"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { StockSelector } from "@/components/stocks/StockSelector";
import { apiFetch, getAccessToken } from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import { formatCurrency, formatPercent } from "@/lib/format";
import { RISK_QUESTIONS, mapAnswersToRiskProfile, type RiskCategory } from "@/lib/riskMapping";
import { DEFAULT_SELECTION, isSelectionValid, saveSelection, type StockSelection } from "@/lib/stockSelection";

type PortfolioDetails = {
  name: string;
  purpose: string;
  initial_capital: string;
};

type Step = 1 | 2 | 3 | 4;

const DECIMAL_PATTERN = /^\d+(\.\d+)?$/;
const stepLabels = ["Risk", "Details", "Stocks", "Review"];

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export default function NewPortfolioPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>(1);
  const [riskAnswers, setRiskAnswers] = useState<Record<string, RiskCategory>>({});
  const [details, setDetails] = useState<PortfolioDetails>({
    name: "",
    purpose: "",
    initial_capital: "",
  });
  const [selection, setSelection] = useState<StockSelection>(DEFAULT_SELECTION);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const allQuestionsAnswered = RISK_QUESTIONS.every((q) => riskAnswers[q.id] !== undefined);
  const riskProfile = allQuestionsAnswered ? mapAnswersToRiskProfile(RISK_QUESTIONS.map((q) => riskAnswers[q.id])) : null;

  function validateDetails(): boolean {
    const errors: Record<string, string> = {};

    if (!details.name.trim()) {
      errors.name = "Name is required.";
    } else if (details.name.length > 100) {
      errors.name = "Name must be 100 characters or fewer.";
    }

    if (details.purpose.length > 255) {
      errors.purpose = "Purpose must be 255 characters or fewer.";
    }

    if (!DECIMAL_PATTERN.test(details.initial_capital) || Number(details.initial_capital) <= 0) {
      errors.initial_capital = "Initial capital must be a positive number.";
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleCreate() {
    if (!riskProfile || !validateDetails() || !isSelectionValid(selection)) return;

    setSubmitting(true);
    setSubmitError(null);

    const accessToken = await getAccessToken();
    if (!accessToken) {
      setSubmitError("You're signed out. Please log in again.");
      setSubmitting(false);
      return;
    }

    let riskProfileId: string;
    try {
      const created = await apiFetch<{ id: string }>(
        "/users/me/risk-profile",
        accessToken,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(riskProfile),
        },
      );
      riskProfileId = created.id;
    } catch (err) {
      console.error("Failed to create risk profile:", err);
      setSubmitError(getErrorMessage(err, "We couldn't save your risk profile. Please try again."));
      setSubmitting(false);
      return;
    }

    try {
      const portfolio = await apiFetch<{ id: string }>("/portfolios", accessToken, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: details.name.trim(),
          purpose: details.purpose.trim() || null,
          base_currency: "INR",
          initial_capital: details.initial_capital,
          risk_profile_id: riskProfileId,
        }),
      });
      saveSelection(portfolio.id, selection);
      router.push(`/dashboard/portfolios/${portfolio.id}/recommendation?generate=1`);
    } catch (err) {
      console.error("Failed to create portfolio:", err);
      setSubmitError(
        "Your risk profile was saved, but creating the portfolio failed. You can try again — note that retrying will create a new risk profile, since risk profiles aren't reused yet.",
      );
      setSubmitting(false);
    }
  }

  return (
    <main className="page-shell">
      <header className="page-header">
        <div className="page-heading">
          <span className="eyebrow">Portfolio creation</span>
          <h1 className="page-title">Create Portfolio</h1>
        </div>
        <Link href="/dashboard" className="ghost-button">Cancel</Link>
      </header>

      <div className="card" style={{ padding: "26px" }}>
        <div className="stepper" aria-label="Portfolio creation steps">
          {stepLabels.map((label, index) => {
            const status = index + 1 < step ? "done" : index + 1 === step ? "active" : "";
            return (
              <div key={label} className={`stepper-step ${status}`} aria-current={index + 1 === step ? "step" : undefined}>
                <span className="stepper-number">{index + 1}</span>
                <span>{label}</span>
              </div>
            );
          })}
        </div>

        {step === 1 && (
          <div className="form-grid">
            <div className="section-header" style={{ marginBottom: 0 }}>
              <div>
                <span className="eyebrow">Step 1</span>
                <h2 className="section-title">Risk</h2>
              </div>
            </div>

            {RISK_QUESTIONS.map((q) => (
              <fieldset key={q.id} className="risk-question">
                <legend>{q.text}</legend>
                <div className="option-grid">
                  {q.options.map((opt) => {
                    const selected = riskAnswers[q.id] === opt.value;
                    return (
                      <label
                        key={opt.value}
                        className={`option-card ${selected ? "selected" : ""}`}
                        onClick={() => setRiskAnswers((prev) => ({ ...prev, [q.id]: opt.value }))}
                      >
                        <span className="option-card-header">
                          <span className="option-title">{opt.label}</span>
                          <input
                            type="radio"
                            name={q.id}
                            value={opt.value}
                            checked={selected}
                            onChange={() => setRiskAnswers((prev) => ({ ...prev, [q.id]: opt.value }))}
                            aria-label={opt.label}
                          />
                        </span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>
            ))}

            {riskProfile && (
              <div className="risk-profile-card" role="status">
                <span className="eyebrow">Your risk profile</span>
                <div className="risk-profile-name">{capitalize(riskProfile.category)}</div>
                <div className="risk-profile-meta">Max per stock {formatPercent(riskProfile.max_position_weight)}</div>
                <div className="risk-profile-meta">Target volatility {formatPercent(riskProfile.target_volatility)}</div>
              </div>
            )}

            <div className="segmented-actions">
              <Link href="/dashboard" className="secondary-button">Back</Link>
              <button type="button" className="primary-button" disabled={!allQuestionsAnswered} onClick={() => setStep(2)}>
                Continue
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="form-grid">
            <div className="section-header" style={{ marginBottom: 0 }}>
              <div>
                <span className="eyebrow">Step 2</span>
                <h2 className="section-title">Details</h2>
              </div>
            </div>

            <div className="field-group">
              <label className="field-label" htmlFor="portfolio-name">Portfolio name</label>
              <input
                id="portfolio-name"
                value={details.name}
                onChange={(e) => setDetails((prev) => ({ ...prev, name: e.target.value }))}
                placeholder="For example: Long-term Growth"
              />
              {fieldErrors.name && <p className="field-hint" style={{ color: "var(--danger)" }}>{fieldErrors.name}</p>}
            </div>

            <div className="field-group">
              <label className="field-label" htmlFor="portfolio-purpose">Purpose (optional)</label>
              <input
                id="portfolio-purpose"
                value={details.purpose}
                onChange={(e) => setDetails((prev) => ({ ...prev, purpose: e.target.value }))}
                placeholder="Retirement, home purchase, wealth creation..."
              />
              {fieldErrors.purpose && <p className="field-hint" style={{ color: "var(--danger)" }}>{fieldErrors.purpose}</p>}
            </div>

            <div className="field-group">
              <label className="field-label" htmlFor="portfolio-capital">Investment capital (₹)</label>
              <div className="currency-field">
                <span className="prefix">₹</span>
                <input
                  id="portfolio-capital"
                  inputMode="decimal"
                  value={details.initial_capital}
                  onChange={(e) => setDetails((prev) => ({ ...prev, initial_capital: e.target.value }))}
                  placeholder="500000"
                />
              </div>
              {fieldErrors.initial_capital && (
                <p className="field-hint" style={{ color: "var(--danger)" }}>{fieldErrors.initial_capital}</p>
              )}
            </div>

            <div className="segmented-actions">
              <button type="button" className="secondary-button" onClick={() => setStep(1)}>
                Back
              </button>
              <button type="button" className="primary-button" onClick={() => validateDetails() && setStep(3)}>
                Continue
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="form-grid">
            <div className="section-header" style={{ marginBottom: 0 }}>
              <div>
                <span className="eyebrow">Step 3</span>
                <h2 className="section-title">Stocks</h2>
              </div>
            </div>

            <StockSelector value={selection} onChange={setSelection} maxPositionWeight={riskProfile?.max_position_weight} />

            <div className="segmented-actions">
              <button type="button" className="secondary-button" onClick={() => setStep(2)}>
                Back
              </button>
              <button type="button" className="primary-button" disabled={!isSelectionValid(selection)} onClick={() => setStep(4)}>
                Continue
              </button>
            </div>
          </div>
        )}

        {step === 4 && riskProfile && (
          <div className="form-grid">
            <div className="section-header" style={{ marginBottom: 0 }}>
              <div>
                <span className="eyebrow">Step 4</span>
                <h2 className="section-title">Review</h2>
              </div>
            </div>

            <div className="detail-grid">
              <div className="detail-item">
                <span className="detail-label">Risk profile</span>
                <div className="detail-value">{capitalize(riskProfile.category)}</div>
                <p className="field-hint">
                  Max per stock {formatPercent(riskProfile.max_position_weight)} · Target volatility {formatPercent(riskProfile.target_volatility)}
                </p>
              </div>
              <div className="detail-item">
                <span className="detail-label">Portfolio</span>
                <div className="detail-value">{details.name.trim()}</div>
                <p className="field-hint">Capital {formatCurrency(details.initial_capital)}</p>
              </div>
              <div className="detail-item">
                <span className="detail-label">Stocks</span>
                <div className="detail-value">
                  {selection.mode === "nifty50" ? "All NIFTY 50" : `${selection.tickers.length} stock${selection.tickers.length === 1 ? "" : "s"}`}
                </div>
                {selection.mode === "custom" && <p className="field-hint">{selection.tickers.join(", ")}</p>}
              </div>
              <div className="detail-item">
                <span className="detail-label">Method</span>
                <div className="detail-value">ML-assisted analysis</div>
              </div>
            </div>

            {submitError && (
              <div className="notice error" role="alert">
                <span className="notice-icon">⚠</span>
                <div>{submitError}</div>
              </div>
            )}

            <div className="segmented-actions">
              <button type="button" className="secondary-button" onClick={() => setStep(3)} disabled={submitting}>
                Back
              </button>
              <button type="button" className="primary-button" onClick={() => void handleCreate()} disabled={submitting}>
                {submitting ? "Creating portfolio..." : "Create portfolio & generate recommendation"}
              </button>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
