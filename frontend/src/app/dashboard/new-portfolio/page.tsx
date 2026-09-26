"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { apiFetch } from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import { RISK_QUESTIONS, mapAnswersToRiskProfile, type RiskCategory } from "@/lib/riskMapping";
import type { ReturnModel } from "@/lib/types/api";

type PortfolioDetails = {
  name: string;
  purpose: string;
  initial_capital: string;
};

const DECIMAL_PATTERN = /^\d+(\.\d+)?$/;
const stepLabels = ["Risk Profile", "Portfolio Details", "Investment Options", "Generate Recommendation"];

export default function NewPortfolioPage() {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2>(1);
  const [riskAnswers, setRiskAnswers] = useState<Record<string, RiskCategory>>({});
  const [details, setDetails] = useState<PortfolioDetails>({
    name: "",
    purpose: "",
    initial_capital: "",
  });
  const [returnModel, setReturnModel] = useState<ReturnModel>("ml");
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
    if (!validateDetails()) return;

    setSubmitting(true);
    setSubmitError(null);

    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();

    if (!session) {
      setSubmitError("You're signed out. Please log in again.");
      setSubmitting(false);
      return;
    }

    const answers = RISK_QUESTIONS.map((q) => riskAnswers[q.id]);
    const riskProfilePayload = mapAnswersToRiskProfile(answers);

    let riskProfileId: string;
    try {
      const riskProfile = await apiFetch<{ id: string }>(
        "/users/me/risk-profile",
        session.access_token,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(riskProfilePayload),
        },
      );
      riskProfileId = riskProfile.id;
    } catch (err) {
      console.error("Failed to create risk profile:", err);
      setSubmitError(getErrorMessage(err, "We couldn't save your risk profile. Please try again."));
      setSubmitting(false);
      return;
    }

    try {
      const portfolio = await apiFetch<{ id: string }>("/portfolios", session.access_token, {
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
      router.push(`/dashboard/portfolios/${portfolio.id}/recommendation?model=${returnModel}`);
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
      </header>

      <div className="card" style={{ padding: "26px" }}>
        <div className="stepper" aria-label="Portfolio creation steps">
          {stepLabels.map((label, index) => {
            const currentStep = step === 1 ? 1 : 2;
            const status = index + 1 < currentStep ? "done" : index + 1 === currentStep ? "active" : "";
            return (
              <div key={label} className={`stepper-step ${status}`}>
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
                <h2 className="section-title">Risk Profile</h2>
              </div>
            </div>

            {RISK_QUESTIONS.map((q) => (
              <fieldset key={q.id} style={{ border: "1px solid var(--border)", borderRadius: 20, padding: 18, background: "rgba(248,250,252,0.5)" }}>
                <legend style={{ padding: "0 8px", fontWeight: 700, color: "var(--foreground)" }}>{q.text}</legend>
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
                <span className="eyebrow">Your Risk Profile</span>
                <div className="risk-profile-name">{riskProfile.category.charAt(0).toUpperCase() + riskProfile.category.slice(1)}</div>
                <div className="risk-profile-meta">
                  Based on your responses, this portfolio is targeting a {riskProfile.target_volatility * 100}% annual volatility profile.
                </div>
              </div>
            )}

            <div className="segmented-actions">
              <button type="button" className="primary-button" disabled={!allQuestionsAnswered} onClick={() => setStep(2)}>
                Continue to portfolio details
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="form-grid">
            <div className="section-header" style={{ marginBottom: 0 }}>
              <div>
                <span className="eyebrow">Step 2</span>
                <h2 className="section-title">Portfolio Details</h2>
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
              <label className="field-label" htmlFor="portfolio-capital">Investment capital</label>
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

            <div className="panel" style={{ padding: "18px" }}>
              <div className="section-header" style={{ marginBottom: 12 }}>
                <div>
                  <span className="eyebrow">Investment model</span>
                  <h3 className="section-title" style={{ fontSize: "1.2rem" }}>Return model</h3>
                </div>
              </div>
              <div className="option-grid">
                {[
                  { value: "ml", label: "Machine Learning", description: "Recommended for model-based forecasts" },
                  { value: "historical", label: "Historical Baseline", description: "Uses historical returns when needed" },
                ].map((model) => {
                  const selected = returnModel === model.value;
                  return (
                    <button
                      key={model.value}
                      type="button"
                      className={`option-card ${selected ? "selected" : ""}`}
                      onClick={() => setReturnModel(model.value as ReturnModel)}
                      style={{ textAlign: "left" }}
                    >
                      <span className="option-card-header">
                        <span className="option-title">{model.label}</span>
                        {selected && <span className="badge ml">Selected</span>}
                      </span>
                      <span className="option-body">{model.description}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {submitError && (
              <div className="notice error" role="alert">
                <span className="notice-icon">⚠</span>
                <div>{submitError}</div>
              </div>
            )}

            <div className="segmented-actions">
              <button type="button" className="secondary-button" onClick={() => setStep(1)} disabled={submitting}>
                Back
              </button>
              <button type="button" className="primary-button" onClick={handleCreate} disabled={submitting}>
                {submitting ? "Creating portfolio..." : "Create portfolio & generate recommendation"}
              </button>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
