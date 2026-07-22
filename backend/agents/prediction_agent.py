"""
prediction_agent.py
---------------------
System Feature 1: Hyperlocal AQI Prediction

Forecasts AQI at ward level for 24/48/72-hour horizons using weather,
traffic, and lagged AQI features. LightGBM regression, per Section 5 of
the plan (best accuracy-to-compute trade-off + explainability for judges).

Confidence is reported as a simple prediction interval derived from the
residual distribution on the held-out test set, not a single point
estimate -- because a forecast without an error bar is not something a
city official should act on.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
try:
    from lightgbm import LGBMRegressor
    _HAS_LIGHTGBM = True
except ImportError:
    _HAS_LIGHTGBM = False
    from sklearn.ensemble import GradientBoostingRegressor

from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error

FEATURE_COLUMNS = [
    "day_of_week",
    "month",
    "temp_c",
    "humidity_pct",
    "wind_speed_kmh",
    "wind_direction_deg",
    "traffic_density_idx",
    "aqi_lag_1",
    "aqi_lag_7",
]


@dataclass
class ForecastResult:
    ward: str
    horizon_hr: int
    predicted_aqi: float
    lower_bound: float
    upper_bound: float
    confidence: float  # 1 - normalized uncertainty width, simple heuristic for UI display


class AQIPredictionAgent:
    """
    Role: Forecasts AQI at ward/grid resolution, 24-72 hours ahead.
    Inputs: validated historical AQI (from Data Validation Agent) + weather
            forecast + traffic index, as engineered features with lags.
    Outputs: ForecastResult per ward/horizon (point estimate + interval).
    Talks to: Recommendation Agent (consumes forecast), Citizen Advisory
              Agent (consumes forecast), Dashboard.
    """

    def __init__(self, random_state: int = 42):
        if _HAS_LIGHTGBM:
            self.model = LGBMRegressor(
                n_estimators=300,
                max_depth=6,
                learning_rate=0.05,
                random_state=random_state,
                verbosity=-1,
            )
        else:
            # Fallback: sklearn's GradientBoostingRegressor provides a
            # comparable gradient-boosted-tree model when lightgbm isn't
            # installed (e.g. missing C++ build deps on some systems).
            self.model = GradientBoostingRegressor(
                n_estimators=300,
                max_depth=6,
                learning_rate=0.05,
                random_state=random_state,
            )
        self._is_trained = False
        self._residual_std = None

    def train(self, training_df: pd.DataFrame, target_col: str = "aqi") -> dict:
        missing = [col for col in [*FEATURE_COLUMNS, target_col] if col not in training_df.columns]
        if missing:
            raise ValueError(f"Forecast training data is missing columns: {', '.join(missing)}")
        training_df = training_df.dropna(subset=[*FEATURE_COLUMNS, target_col])
        if len(training_df) < 10:
            raise ValueError("Forecast model requires at least 10 complete observed daily feature rows.")
        X = training_df[FEATURE_COLUMNS]
        y = training_df[target_col]
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        self.model.fit(X_train, y_train)
        self._is_trained = True

        preds = self.model.predict(X_test)
        residuals = y_test.values - preds
        self._residual_std = float(np.std(residuals))

        return {
            "mae": round(float(mean_absolute_error(y_test, preds)), 2),
            "rmse": round(float(np.sqrt(mean_squared_error(y_test, preds))), 2),
            "residual_std": round(self._residual_std, 2),
        }

    def predict(self, current_conditions: dict, horizon_hr: int = 24) -> ForecastResult:
        if not self._is_trained:
            raise RuntimeError("Prediction model has not been trained. Call .train() first.")

        X = pd.DataFrame([{k: current_conditions[k] for k in FEATURE_COLUMNS}])
        point_estimate = float(self.model.predict(X)[0])

        # Wider interval for longer horizons -- forecast uncertainty compounds
        # over time; this is a simple heuristic scale-up, not a re-trained
        # per-horizon model (that's the Phase 2 upgrade path).
        horizon_multiplier = {24: 1.0, 48: 1.4, 72: 1.8}.get(horizon_hr, 1.0 + (horizon_hr / 100))
        interval_width = self._residual_std * 1.64 * horizon_multiplier  # ~90% interval

        confidence = round(max(0.3, 1 - (interval_width / max(point_estimate, 1))), 2)

        return ForecastResult(
            ward=current_conditions.get("ward", "unknown"),
            horizon_hr=horizon_hr,
            predicted_aqi=round(point_estimate, 1),
            lower_bound=round(max(0, point_estimate - interval_width), 1),
            upper_bound=round(point_estimate + interval_width, 1),
            confidence=confidence,
        )

    def predict_multi_horizon(self, current_conditions: dict, horizons=(24, 48, 72)) -> list[ForecastResult]:
        return [self.predict(current_conditions, h) for h in horizons]


if __name__ == "__main__":
    import sys, os
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from data.mock_data import generate_prediction_training_data, generate_current_conditions

    df = generate_prediction_training_data()
    agent = AQIPredictionAgent()
    metrics = agent.train(df)
    print("Training metrics:", metrics)

    conditions = generate_current_conditions("Ward-1")
    for forecast in agent.predict_multi_horizon(conditions):
        print(forecast)
