export type RiskCategory = "conservative" | "moderate" | "aggressive";

export type RiskQuestionOption = {
  label: string;
  value: RiskCategory;
};

export type RiskQuestion = {
  id: string;
  text: string;
  options: RiskQuestionOption[];
};

export const RISK_QUESTIONS: RiskQuestion[] = [
  {
    id: "reaction_to_drop",
    text: "If your portfolio suddenly dropped 20% in value, what would you most likely do?",
    options: [
      { label: "Sell to limit further losses", value: "conservative" },
      { label: "Hold and wait for it to recover", value: "moderate" },
      { label: "Buy more while prices are low", value: "aggressive" },
    ],
  },
  {
    id: "primary_goal",
    text: "What best describes your primary investing goal?",
    options: [
      { label: "Protect the money I already have", value: "conservative" },
      { label: "Steady, balanced growth over time", value: "moderate" },
      { label: "Maximize long-term growth", value: "aggressive" },
    ],
  },
  {
    id: "time_horizon",
    text: "When do you expect to need this money?",
    options: [
      { label: "Within 3 years", value: "conservative" },
      { label: "3 to 7 years", value: "moderate" },
      { label: "More than 7 years", value: "aggressive" },
    ],
  },
];

// Picks whichever category was chosen most often across the answers.
// Ties resolve to "moderate" as the neutral middle option.
export function deriveCategory(answers: RiskCategory[]): RiskCategory {
  const counts: Record<RiskCategory, number> = {
    conservative: 0,
    moderate: 0,
    aggressive: 0,
  };
  for (const answer of answers) counts[answer] += 1;

  if (counts.conservative > counts.moderate && counts.conservative > counts.aggressive) {
    return "conservative";
  }
  if (counts.aggressive > counts.moderate && counts.aggressive > counts.conservative) {
    return "aggressive";
  }
  return "moderate";
}

export type RiskProfileCreatePayload = {
  score: number;
  category: RiskCategory;
  max_position_weight: number;
  max_sector_weight: number;
  drift_threshold: number;
  target_volatility: number;
};

// MVP PRODUCT ASSUMPTION, not derived from any established financial
// methodology. The backend (backend/app/schemas/risk_profile.py) only
// constrains these fields to numeric ranges; it defines no relationship
// between a risk category and specific values. These are deliberately
// simple, internally-consistent placeholders chosen only to satisfy
// those validation constraints so the create-portfolio flow is real
// end-to-end. Revisit before this becomes an actual risk-scoring system.
const CATEGORY_RISK_PROFILES: Record<RiskCategory, RiskProfileCreatePayload> = {
  conservative: {
    score: 25,
    category: "conservative",
    max_position_weight: 0.05,
    max_sector_weight: 0.15,
    drift_threshold: 0.03,
    target_volatility: 0.08,
  },
  moderate: {
    score: 50,
    category: "moderate",
    max_position_weight: 0.1,
    max_sector_weight: 0.25,
    drift_threshold: 0.05,
    target_volatility: 0.15,
  },
  aggressive: {
    score: 80,
    category: "aggressive",
    max_position_weight: 0.2,
    max_sector_weight: 0.4,
    drift_threshold: 0.08,
    target_volatility: 0.25,
  },
};

export function mapAnswersToRiskProfile(answers: RiskCategory[]): RiskProfileCreatePayload {
  const category = deriveCategory(answers);
  return CATEGORY_RISK_PROFILES[category];
}
