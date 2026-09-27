import type { ReactNode } from "react";

type Props = {
  back: ReactNode;
  continueLabel: ReactNode;
  onContinue: () => void;
  disabled?: boolean;
  disabledReason?: string | null;
  busy?: boolean;
  wide?: boolean;
};

export function WizardFooter({ back, continueLabel, onContinue, disabled, disabledReason, busy, wide }: Props) {
  const showReason = disabled && !busy && disabledReason;
  return (
    <footer className="wizard-footer">
      <div className="wizard-footer-back">{back}</div>
      <div className={`wizard-footer-continue ${wide ? "is-wide" : ""}`}>
        <button
          type="button"
          className="primary-button"
          onClick={onContinue}
          disabled={disabled}
          aria-busy={busy || undefined}
          aria-describedby={showReason ? "wizard-continue-reason" : undefined}
        >
          {busy && <span className="wizard-spinner" aria-hidden="true" />}
          {continueLabel}
        </button>
        {showReason && (
          <p id="wizard-continue-reason" className="wizard-footer-reason">
            {disabledReason}
          </p>
        )}
      </div>
    </footer>
  );
}
