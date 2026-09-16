"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { apiFetch } from "@/lib/api";
import { RISK_QUESTIONS, mapAnswersToRiskProfile, type RiskCategory } from "@/lib/riskMapping";

type PortfolioDetails = {
  name: string;
  purpose: string;
  base_currency: string;
  initial_capital: string;
};

const CURRENCY_PATTERN = /^[A-Z]{3}$/;
const DECIMAL_PATTERN = /^\d+(\.\d+)?$/;

export default function NewPortfolioPage() {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2>(1);

  const [riskAnswers, setRiskAnswers] = useState<Record<string, RiskCategory>>({});

  const [details, setDetails] = useState<PortfolioDetails>({
    name: "",
    purpose: "",
    base_currency: "INR",
    initial_capital: "",
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const allQuestionsAnswered = RISK_QUESTIONS.every((q) => riskAnswers[q.id] !== undefined);

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

    if (!CURRENCY_PATTERN.test(details.base_currency)) {
      errors.base_currency = "Currency must be a 3-letter uppercase code, e.g. INR.";
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
      setSubmitError("We couldn't save your risk profile. Please try again.");
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
          base_currency: details.base_currency,
          initial_capital: details.initial_capital,
          risk_profile_id: riskProfileId,
        }),
      });
      router.push(`/dashboard/portfolios/${portfolio.id}`);
    } catch (err) {
      console.error("Failed to create portfolio:", err);
      setSubmitError(
        "Your risk profile was saved, but creating the portfolio failed. You can try again " +
          "— note that retrying will create a new risk profile, since risk profiles aren't reused yet.",
      );
      setSubmitting(false);
    }
  }

  return (
    <div style={{ padding: 40, maxWidth: 480 }}>
      <h1>Create Portfolio</h1>

      {step === 1 && (
        <div>
          <h2>Step 1: Risk Profile</h2>
          {RISK_QUESTIONS.map((q) => (
            <fieldset key={q.id} style={{ marginBottom: 16 }}>
              <legend>{q.text}</legend>
              {q.options.map((opt) => (
                <label key={opt.value} style={{ display: "block" }}>
                  <input
                    type="radio"
                    name={q.id}
                    value={opt.value}
                    checked={riskAnswers[q.id] === opt.value}
                    onChange={() => setRiskAnswers((prev) => ({ ...prev, [q.id]: opt.value }))}
                  />
                  {opt.label}
                </label>
              ))}
            </fieldset>
          ))}
          <button type="button" disabled={!allQuestionsAnswered} onClick={() => setStep(2)}>
            Next
          </button>
        </div>
      )}

      {step === 2 && (
        <div>
          <h2>Step 2: Portfolio Details</h2>

          <div style={{ marginBottom: 12 }}>
            <label>
              Name
              <br />
              <input
                value={details.name}
                onChange={(e) => setDetails((prev) => ({ ...prev, name: e.target.value }))}
              />
            </label>
            {fieldErrors.name && <p style={{ color: "red" }}>{fieldErrors.name}</p>}
          </div>

          <div style={{ marginBottom: 12 }}>
            <label>
              Purpose (optional)
              <br />
              <input
                value={details.purpose}
                onChange={(e) => setDetails((prev) => ({ ...prev, purpose: e.target.value }))}
              />
            </label>
            {fieldErrors.purpose && <p style={{ color: "red" }}>{fieldErrors.purpose}</p>}
          </div>

          <div style={{ marginBottom: 12 }}>
            <label>
              Base currency
              <br />
              <input
                value={details.base_currency}
                onChange={(e) =>
                  setDetails((prev) => ({ ...prev, base_currency: e.target.value.toUpperCase() }))
                }
              />
            </label>
            {fieldErrors.base_currency && <p style={{ color: "red" }}>{fieldErrors.base_currency}</p>}
          </div>

          <div style={{ marginBottom: 12 }}>
            <label>
              Initial capital
              <br />
              <input
                value={details.initial_capital}
                onChange={(e) =>
                  setDetails((prev) => ({ ...prev, initial_capital: e.target.value }))
                }
              />
            </label>
            {fieldErrors.initial_capital && (
              <p style={{ color: "red" }}>{fieldErrors.initial_capital}</p>
            )}
          </div>

          {submitError && <p style={{ color: "red" }}>{submitError}</p>}

          <button type="button" onClick={() => setStep(1)} disabled={submitting}>
            Back
          </button>{" "}
          <button type="button" onClick={handleCreate} disabled={submitting}>
            {submitting ? "Creating..." : "Create Portfolio"}
          </button>
        </div>
      )}
    </div>
  );
}
