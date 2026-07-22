"""
attribution_agent.py
---------------------
System Feature 2: Pollution Source Attribution Engine

Attributes a pollution hotspot to a source category (traffic / construction /
industrial / dust / stubble_burning) using land-use, traffic density,
industrial stack count, and satellite thermal anomaly signals -- and returns
a confidence score, not just a label, since this feeds enforcement decisions.

Approach: RandomForestClassifier (interpretable, fast to train, gives
per-class probabilities we can surface as confidence -- exactly what
Section 5 of the plan recommends for the attribution use case).
"""

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

FEATURE_COLUMNS = [
    "traffic_density_idx",
    "construction_permit_density",
    "industrial_stack_count",
    "thermal_anomaly_count",
    "dust_landuse_pct",
    "pm25",
]


@dataclass
class AttributionResult:
    ward: str
    predicted_source: str
    confidence: float
    all_probabilities: dict
    evidence: dict = field(default_factory=dict)


class PollutionAttributionAgent:
    """
    Role: Attributes a pollution hotspot to a source category with a
          statistical confidence score.
    Inputs: hotspot feature row (traffic density, construction density,
            industrial stack count, thermal anomalies, dust land-use %, PM2.5)
    Outputs: AttributionResult (source label + confidence + full probability
             distribution + human-readable evidence)
    Talks to: Recommendation Agent (consumes AttributionResult to build the
              enforcement action list)
    """

    def __init__(self, n_estimators: int = 200, random_state: int = 42):
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=8,
            random_state=random_state,
            class_weight="balanced",
        )
        self._is_trained = False

    def train(self, training_df: pd.DataFrame, label_col: str = "source_label") -> str:
        missing = [col for col in [*FEATURE_COLUMNS, label_col] if col not in training_df.columns]
        if missing:
            raise ValueError(f"Attribution training data is missing columns: {', '.join(missing)}")
        training_df = training_df.dropna(subset=[*FEATURE_COLUMNS, label_col])
        class_counts = training_df[label_col].value_counts()
        if len(class_counts) < 2 or class_counts.min() < 2:
            raise ValueError("Attribution model requires at least two reviewed source labels with two samples each.")
        X = training_df[FEATURE_COLUMNS]
        y = training_df[label_col]
        test_size = max(len(class_counts), round(len(training_df) * 0.2))
        if test_size >= len(training_df):
            test_size = len(class_counts)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )
        self.model.fit(X_train, y_train)
        self._is_trained = True
        y_pred = self.model.predict(X_test)
        return classification_report(y_test, y_pred, zero_division=0)

    def attribute(self, hotspot_row: pd.Series) -> AttributionResult:
        if not self._is_trained:
            raise RuntimeError("Attribution model has not been trained. Call .train() first.")

        X = pd.DataFrame([hotspot_row[FEATURE_COLUMNS]])
        probs = self.model.predict_proba(X)[0]
        classes = self.model.classes_
        prob_map = {cls: round(float(p), 3) for cls, p in zip(classes, probs)}
        top_idx = probs.argmax()
        predicted_source = classes[top_idx]
        confidence = round(float(probs[top_idx]), 3)

        evidence = self._build_evidence(hotspot_row, predicted_source)

        return AttributionResult(
            ward=hotspot_row.get("ward", "unknown"),
            predicted_source=predicted_source,
            confidence=confidence,
            all_probabilities=prob_map,
            evidence=evidence,
        )

    def attribute_batch(self, hotspot_df: pd.DataFrame) -> list[AttributionResult]:
        return [self.attribute(row) for _, row in hotspot_df.iterrows()]

    @staticmethod
    def _build_evidence(row: pd.Series, predicted_source: str) -> dict:
        """
        Human-readable evidence for the recommendation engine / demo UI --
        this is what shows up when an official clicks a hotspot on the map
        and asks "why do you think this is construction dust?"
        """
        evidence_map = {
            "traffic": {"signal": "traffic_density_idx", "value": round(row["traffic_density_idx"], 2)},
            "construction": {"signal": "construction_permit_density", "value": round(row["construction_permit_density"], 2)},
            "industrial": {"signal": "industrial_stack_count", "value": int(row["industrial_stack_count"])},
            "dust": {"signal": "dust_landuse_pct", "value": round(row["dust_landuse_pct"], 2)},
            "stubble_burning": {"signal": "thermal_anomaly_count", "value": int(row["thermal_anomaly_count"])},
        }
        return evidence_map.get(predicted_source, {})


if __name__ == "__main__":
    import sys, os
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from data.mock_data import generate_hotspot_features

    df = generate_hotspot_features()
    agent = PollutionAttributionAgent()
    print(agent.train(df))

    sample = df.iloc[0]
    result = agent.attribute(sample)
    print("\nSample attribution:")
    print(result)
