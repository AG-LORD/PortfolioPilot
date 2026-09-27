"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { StockSelector } from "@/components/stocks/StockSelector";
import { DetailsStep, type PortfolioDetails } from "@/components/wizard/DetailsStep";
import { ReviewStep } from "@/components/wizard/ReviewStep";
import { RiskStep } from "@/components/wizard/RiskStep";
import { WizardFooter } from "@/components/wizard/WizardFooter";
import { WizardStepper } from "@/components/wizard/WizardStepper";
import { apiFetch, getAccessToken } from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import { RISK_QUESTIONS, mapAnswersToRiskProfile, type RiskCategory } from "@/lib/riskMapping";
import { DEFAULT_SELECTION, isSelectionValid, saveSelection, type StockSelection } from "@/lib/stockSelection";

type Step = 1 | 2 | 3 | 4;

const DECIMAL_PATTERN = /^\d+(\.\d+)?$/;
const stepLabels = ["Risk", "Details", "Stocks", "Review"];
const stepTitles = ["Your risk profile", "Portfolio details", "Choose stocks", "Review"];

function getDetailErrors(details: PortfolioDetails): Partial<Record<keyof PortfolioDetails, string>> {
  const errors: Partial<Record<keyof PortfolioDetails, string>> = {};

  if (!details.name.trim()) {
    errors.name = "Enter a portfolio name.";
  } else if (details.name.length > 100) {
    errors.name = "Name must be 100 characters or fewer.";
  }

  if (details.purpose.length > 255) {
    errors.purpose = "Purpose must be 255 characters or fewer.";
  }

  if (!details.initial_capital) {
    errors.initial_capital = "Enter how much you want to invest.";
  } else if (!DECIMAL_PATTERN.test(details.initial_capital) || Number(details.initial_capital) <= 0) {
    errors.initial_capital = "Enter an amount greater than ₹0.";
  }

  return errors;
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
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const hasMounted = useRef(false);

  const answeredCount = RISK_QUESTIONS.filter((q) => riskAnswers[q.id] !== undefined).length;
  const allQuestionsAnswered = answeredCount === RISK_QUESTIONS.length;
  const riskProfile = allQuestionsAnswered ? mapAnswersToRiskProfile(RISK_QUESTIONS.map((q) => riskAnswers[q.id])) : null;
  const detailErrors = getDetailErrors(details);
  const detailsValid = Object.keys(detailErrors).length === 0;

  // Move focus to the new step's heading so keyboard and screen-reader users land on it.
  useEffect(() => {
    if (!hasMounted.current) {
      hasMounted.current = true;
      return;
    }
    headingRef.current?.focus();
  }, [step]);

  function goTo(target: number) {
    if (submitting) return;
    setStep(target as Step);
  }

  async function handleCreate() {
    if (!riskProfile || !detailsValid || !isSelectionValid(selection)) return;

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

  const backButton =
    step === 1 ? (
      <Link href="/dashboard" className="secondary-button">Back</Link>
    ) : (
      <button type="button" className="secondary-button" onClick={() => goTo(step - 1)} disabled={submitting}>
        Back
      </button>
    );

  let footer;
  if (step === 1) {
    footer = (
      <WizardFooter
        back={backButton}
        continueLabel="Continue"
        onContinue={() => goTo(2)}
        disabled={!allQuestionsAnswered}
        disabledReason="Answer all 3 questions"
      />
    );
  } else if (step === 2) {
    footer = (
      <WizardFooter
        back={backButton}
        continueLabel="Continue"
        onContinue={() => goTo(3)}
        disabled={!detailsValid}
        disabledReason={
          detailErrors.name && !details.name.trim()
            ? "Enter a portfolio name"
            : detailErrors.initial_capital && !details.initial_capital
              ? "Enter your investment amount"
              : "Fix the highlighted fields"
        }
      />
    );
  } else if (step === 3) {
    footer = (
      <WizardFooter
        back={backButton}
        continueLabel="Continue"
        onContinue={() => goTo(4)}
        disabled={!isSelectionValid(selection)}
        disabledReason="Choose at least 1 stock"
      />
    );
  } else {
    footer = (
      <WizardFooter
        back={backButton}
        continueLabel={submitting ? "Creating portfolio…" : "Create portfolio & generate recommendation"}
        onContinue={() => void handleCreate()}
        disabled={submitting}
        busy={submitting}
        wide
      />
    );
  }

  return (
    <main className="wizard-shell">
      <header className="wizard-header">
        <div className="page-heading">
          <span className="eyebrow">Portfolio creation</span>
          <h1 className="wizard-title">Create portfolio</h1>
        </div>
        <Link href="/dashboard" className="ghost-button">Cancel</Link>
      </header>

      <WizardStepper labels={stepLabels} current={step} onSelect={goTo} />

      <section className="card wizard-card" aria-labelledby="wizard-step-title">
        <div className="wizard-card-header">
          <h2 id="wizard-step-title" ref={headingRef} tabIndex={-1} className="wizard-step-title">
            <span className="wizard-step-count">Step {step} of 4</span>
            <span aria-hidden="true"> · </span>
            {stepTitles[step - 1]}
          </h2>
          {step === 1 && (
            <span className="wizard-step-meta" aria-live="polite">
              {answeredCount} of {RISK_QUESTIONS.length} answered
            </span>
          )}
        </div>

        <div className="wizard-card-body">
          {step === 1 && (
            <RiskStep
              answers={riskAnswers}
              onAnswer={(id, value) => setRiskAnswers((prev) => ({ ...prev, [id]: value }))}
              profile={riskProfile}
            />
          )}

          {step === 2 && <DetailsStep details={details} errors={detailErrors} onChange={setDetails} />}

          {step === 3 && (
            <StockSelector value={selection} onChange={setSelection} maxPositionWeight={riskProfile?.max_position_weight} />
          )}

          {step === 4 && riskProfile && (
            <>
              <ReviewStep profile={riskProfile} details={details} selection={selection} onEdit={goTo} disabled={submitting} />
              {submitError && (
                <div className="notice error" role="alert" style={{ marginTop: 18 }}>
                  <span className="notice-icon">⚠</span>
                  <div>{submitError}</div>
                </div>
              )}
            </>
          )}
        </div>

        {footer}
      </section>
    </main>
  );
}
