import { formatPercent } from "@/lib/format";
import { RISK_QUESTIONS, type RiskCategory, type RiskProfileCreatePayload } from "@/lib/riskMapping";
import { CheckIcon } from "./CheckIcon";

// Presentation-only helper copy for each answer; the mapping values live in riskMapping.
const OPTION_SUBTITLES: Record<string, Record<RiskCategory, string>> = {
  reaction_to_drop: {
    conservative: "I'd rather protect what I have",
    moderate: "Short-term drops don't worry me much",
    aggressive: "Drops are a chance to invest more",
  },
  primary_goal: {
    conservative: "Avoid losses first",
    moderate: "Balance growth and safety",
    aggressive: "Accept ups and downs for higher growth",
  },
  time_horizon: {
    conservative: "Money needed soon",
    moderate: "Medium-term goal",
    aggressive: "Long-term goal",
  },
};

type Props = {
  answers: Record<string, RiskCategory>;
  onAnswer: (questionId: string, value: RiskCategory) => void;
  profile: RiskProfileCreatePayload | null;
};

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function RiskStep({ answers, onAnswer, profile }: Props) {
  return (
    <div className="wizard-stack">
      {RISK_QUESTIONS.map((q, index) => (
        <fieldset key={q.id} className="wizard-question">
          <legend>
            <span className="wizard-question-number" aria-hidden="true">{index + 1}</span>
            <span>
              <span className="visually-hidden">Question {index + 1}: </span>
              {q.text}
            </span>
          </legend>
          <div className="wizard-option-list">
            {q.options.map((opt) => {
              const selected = answers[q.id] === opt.value;
              const id = `${q.id}-${opt.value}`;
              return (
                <label key={opt.value} htmlFor={id} className={`wizard-option ${selected ? "is-selected" : ""}`}>
                  <input
                    id={id}
                    className="visually-hidden"
                    type="radio"
                    name={q.id}
                    value={opt.value}
                    checked={selected}
                    onChange={() => onAnswer(q.id, opt.value)}
                  />
                  <span className="wizard-option-text">
                    <span className="wizard-option-title">{opt.label}</span>
                    <span className="wizard-option-subtitle">{OPTION_SUBTITLES[q.id]?.[opt.value]}</span>
                  </span>
                  <span className="wizard-option-check" aria-hidden="true">
                    {selected && <CheckIcon />}
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>
      ))}

      <div aria-live="polite">
        {profile && (
          <div className="wizard-result">
            <h3 className="wizard-result-title">Your risk profile: {capitalize(profile.category)}</h3>
            <ul className="wizard-result-list">
              <li>No single stock above {formatPercent(profile.max_position_weight)} of your money</li>
              <li>Aims to keep yearly ups and downs around {formatPercent(profile.target_volatility)}</li>
            </ul>
            <p className="wizard-result-note">Based on your 3 answers.</p>
          </div>
        )}
      </div>
    </div>
  );
}
