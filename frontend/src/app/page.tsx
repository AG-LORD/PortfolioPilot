import Link from "next/link";

const decisionStages = [
  ["01", "Market data", "Adjusted price history"],
  ["02", "Point-in-time features", "Signals built from past data"],
  ["03", "Expected returns", "ML forecast or historical baseline"],
  ["04", "Risk-constrained target", "Allocation with cash preserved"],
];

const capabilities = [
  {
    number: "01",
    title: "Manage the portfolio you have",
    body: "Keep portfolio capital, cash, holdings and transactions together in one persistent view.",
  },
  {
    number: "02",
    title: "Understand risk in context",
    body: "Review valuation and snapshot-based risk measures alongside your current portfolio state.",
  },
  {
    number: "03",
    title: "Explore a target allocation",
    body: "Compare historical estimates or ML-assisted forecasts through risk-constrained optimization.",
  },
];

export default function Home() {
  return (
    <main className="landing-page">
      <header className="landing-nav">
        <Link className="landing-brand" href="/" aria-label="PortfolioPilot home">
          <span className="landing-brand-mark" aria-hidden="true">P</span>
          <span>PortfolioPilot</span>
        </Link>
        <nav className="landing-nav-links" aria-label="Main navigation">
          <a href="#approach">Approach</a>
          <a href="#platform">Platform</a>
        </nav>
        <div className="landing-nav-actions">
          <Link className="landing-login" href="/login">Log in</Link>
          <Link className="landing-nav-cta" href="/register">Get started</Link>
        </div>
      </header>

      <section className="landing-hero" aria-labelledby="landing-title">
        <p className="landing-kicker"><span /> A clearer portfolio decision process</p>
        <h1 id="landing-title">PortfolioPilot</h1>
        <p className="landing-lede">ML-assisted, risk-aware portfolio decision support.</p>
        <p className="landing-intro">
          Manage your current portfolio, understand its risk, and explore a target allocation
          grounded in market history and explicit constraints.
        </p>
        <div className="landing-actions">
          <Link className="landing-primary" href="/register">Create an account <span aria-hidden="true">↗</span></Link>
          <Link className="landing-secondary" href="/login">Log in</Link>
        </div>
        <p className="landing-advisory">Recommendations are advisory. Generating one never places a trade.</p>
      </section>

      <section className="landing-approach" id="approach" aria-labelledby="approach-title">
        <div className="landing-section-heading">
          <p className="landing-kicker">A transparent decision path</p>
          <h2 id="approach-title">From market data to a target allocation</h2>
          <p>Each recommendation follows the same visible sequence. Forecasts inform the decision; risk constraints shape it.</p>
        </div>
        <ol className="landing-stage-list">
          {decisionStages.map(([number, title, detail]) => (
            <li className="landing-stage" key={number}>
              <span className="landing-stage-number">{number}</span>
              <strong>{title}</strong>
              <span>{detail}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="landing-platform" id="platform" aria-labelledby="platform-title">
        <div className="landing-platform-heading">
          <p className="landing-kicker">Built around your portfolio</p>
          <h2 id="platform-title">A decision tool, not an autopilot.</h2>
          <p>Portfolio state stays authoritative. Recommendations remain separate from holdings and trades.</p>
        </div>
        <div className="landing-capabilities">
          {capabilities.map((capability) => (
            <article className="landing-capability" key={capability.number}>
              <span>{capability.number}</span>
              <div>
                <h3>{capability.title}</h3>
                <p>{capability.body}</p>
              </div>
            </article>
          ))}
        </div>
        <p className="landing-next-step">
          Portfolio monitoring and rebalancing belong after a target is set: review drift, inspect a proposal,
          and keep any eventual execution under your explicit control.
        </p>
      </section>

      <footer className="landing-footer">
        <Link className="landing-brand" href="/">
          <span className="landing-brand-mark" aria-hidden="true">P</span>
          <span>PortfolioPilot</span>
        </Link>
        <p>Risk-aware decisions. Yours to make.</p>
        <Link href="/register">Get started <span aria-hidden="true">↗</span></Link>
      </footer>
    </main>
  );
}
