import { CheckIcon } from "./CheckIcon";

type Props = {
  labels: string[];
  current: number;
  onSelect: (step: number) => void;
};

export function WizardStepper({ labels, current, onSelect }: Props) {
  return (
    <nav aria-label="Portfolio creation progress">
      <ol className="wizard-progress">
        {labels.map((label, index) => {
          const step = index + 1;
          const status = step < current ? "done" : step === current ? "current" : "upcoming";
          const dot = (
            <span className="wizard-progress-dot" aria-hidden="true">
              {status === "done" && <CheckIcon size={12} />}
            </span>
          );

          return (
            <li key={label} className={`wizard-progress-step is-${status}`}>
              {status === "done" ? (
                <button type="button" className="wizard-progress-target" onClick={() => onSelect(step)}>
                  {dot}
                  <span className="wizard-progress-label">
                    {label}
                    <span className="visually-hidden"> (completed, go back)</span>
                  </span>
                </button>
              ) : (
                <span className="wizard-progress-target" aria-current={status === "current" ? "step" : undefined}>
                  {dot}
                  <span className="wizard-progress-label">
                    {label}
                    {status === "upcoming" && <span className="visually-hidden"> (not started)</span>}
                  </span>
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
