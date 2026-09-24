"""Fixed-hyperparameter models, as sklearn Pipelines so any scaling is fit on
the training fold only. No tuning: every value below is a fixed constant
chosen before looking at test results.
"""

from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

RANDOM_STATE = 0
RIDGE_ALPHA = 1.0
HGB_PARAMS = {
    "learning_rate": 0.05,
    "max_iter": 200,
    "max_depth": 3,
    "min_samples_leaf": 50,
    "l2_regularization": 1.0,
    # Early stopping would carve a random validation split out of the
    # training fold; keep training deterministic and on the full fold.
    "early_stopping": False,
    "random_state": RANDOM_STATE,
}

RIDGE = "ridge"
HIST_GRADIENT_BOOSTING = "hist_gradient_boosting"
MODEL_NAMES = (RIDGE, HIST_GRADIENT_BOOSTING)


def make_model(name: str) -> Pipeline:
    if name == RIDGE:
        return Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=RIDGE_ALPHA))])
    if name == HIST_GRADIENT_BOOSTING:
        # Tree splits are invariant to monotone scaling, so no scaler.
        return Pipeline([("model", HistGradientBoostingRegressor(**HGB_PARAMS))])
    raise ValueError(f"Unknown model '{name}'.")
