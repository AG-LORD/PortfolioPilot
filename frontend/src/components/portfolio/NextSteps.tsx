import Link from "next/link";

type Props = {
  portfolioId: string;
  hasRecommendation: boolean | null;
  hasHoldings: boolean | null;
  hasPerformanceHistory: boolean | null;
};

type Step = {
  title: string;
  detail: string;
  done: boolean;
  href?: string;
  linkLabel?: string;
};

export function NextSteps({ portfolioId, hasRecommendation, hasHoldings, hasPerformanceHistory }: Props) {
  const steps: Step[] = [
    {
      title: "Get a recommendation",
      detail: "See how PortfolioPilot would split your capital.",
      done: hasRecommendation === true,
      href: `/dashboard/portfolios/${portfolioId}/recommendation`,
      linkLabel: "Open Recommendation",
    },
    {
      title: "Buy the shares with your broker",
      detail: "PortfolioPilot never places orders.",
      // Buying happens outside PortfolioPilot; recorded holdings are the evidence it happened.
      done: hasHoldings === true,
    },
    {
      title: "Record your trades",
      detail: "Enter what you actually bought so holdings and cash stay accurate.",
      done: hasHoldings === true,
      href: "#record-trade",
      linkLabel: "Record a trade",
    },
    {
      title: "Track performance",
      detail: "Needs about 30 days of daily snapshots.",
      done: hasPerformanceHistory === true,
    },
  ];

  const allDone = steps.every((step) => step.done);

  if (allDone) {
    return (
      <section className="next-steps collapsed" aria-label="Next steps">
        <span className="next-step-marker done" aria-hidden="true">✓</span>
        <span>All set: recommendation, trades recorded and performance tracking are in place.</span>
      </section>
    );
  }

  return (
    <section className="card next-steps" aria-labelledby="next-steps-title">
      <h2 className="section-title" id="next-steps-title">Next steps</h2>
      <ol className="next-steps-list">
        {steps.map((step, index) => (
          <li key={step.title} className={`next-step ${step.done ? "done" : ""}`}>
            <span className="next-step-marker" aria-hidden="true">{step.done ? "✓" : index + 1}</span>
            <div className="next-step-body">
              <strong>
                {step.title}
                <span className="visually-hidden">{step.done ? " (done)" : " (not done yet)"}</span>
              </strong>
              <p>{step.detail}</p>
              {step.href && !step.done && (
                step.href.startsWith("#")
                  ? <a href={step.href} className="next-step-link">{step.linkLabel} →</a>
                  : <Link href={step.href} className="next-step-link">{step.linkLabel} →</Link>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
