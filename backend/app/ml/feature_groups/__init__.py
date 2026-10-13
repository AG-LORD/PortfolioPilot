"""Research feature groups for the offline walk-forward evaluation.

Each group turns one ticker's OHLCV frame into point-in-time features. The
live forecast (app.services.return_providers) still uses only the technical
group through app.services.features.FEATURE_COLUMNS; the other groups are
research-only until an evaluation justifies changing that.
"""
