"""
recommendation_agent.py
-------------------------
System Feature 3: AI Intervention Recommendation Engine

Converts Attribution Agent output (source + confidence) and Prediction
Agent output (forecast severity) into concrete, role-specific action
recommendations -- the piece that turns "AQI is high" into "do this,
by this time, because of this."

Design: rule-based decision matrix (source x severity -> actions), not an
LLM call. This is deliberate: enforcement/emergency recommendations need
to be deterministic, auditable, and instant -- an LLM adds latency, cost,
and non-determinism where a lookup table is more defensible in front of
judges asking "how do you know this recommendation is safe to act on?"
(An LLM Explanation Agent -- separate component -- can narrate *why* in
natural language on top of this deterministic core.)
"""

from dataclasses import dataclass, field
from typing import Optional

AQI_SEVERITY_BANDS = [
    (0, 100, "satisfactory"),
    (101, 200, "moderate"),
    (201, 300, "poor"),
    (301, 400, "very_poor"),
    (401, 10_000, "severe"),
]

# source x severity -> list of (action, role, urgency_hours)
ACTION_MATRIX = {
    "traffic": {
        "moderate": [("Increase signal green-time on high-density corridors during peak hours", "traffic_police", 24)],
        "poor": [
            ("Deploy traffic police to reroute heavy vehicles away from the hotspot corridor", "traffic_police", 12),
            ("Issue public advisory recommending public transport for affected ward", "citizen_comms", 12),
        ],
        "very_poor": [
            ("Activate odd-even or heavy-vehicle restriction for the ward (GRAP-aligned)", "traffic_police", 6),
            ("Deploy mobile anti-smog units on the corridor", "municipal_ops", 6),
        ],
        "severe": [
            ("Immediate heavy-vehicle ban + reroute through alternate corridors", "traffic_police", 2),
            ("Deploy water sprinkler vehicles along the corridor", "municipal_ops", 2),
        ],
    },
    "construction": {
        "moderate": [("Verify dust-control compliance (green netting, water spraying) at active sites", "spcb_inspector", 24)],
        "poor": [
            ("Dispatch inspector to verify dust mitigation measures within 12 hours", "spcb_inspector", 12),
            ("Notify site operator to increase water spraying frequency", "site_operator", 12),
        ],
        "very_poor": [
            ("Issue formal non-compliance notice if dust controls are inadequate", "spcb_inspector", 6),
            ("Mandate immediate water sprinkling every 2 hours at the site", "site_operator", 6),
        ],
        "severe": [
            ("Suspend construction activity at the site pending compliance review", "spcb_inspector", 2),
            ("Emergency water sprinkling + tarp covering of exposed material", "site_operator", 2),
        ],
    },
    "industrial": {
        "moderate": [("Flag stack emissions for routine SPCB review", "spcb_inspector", 24)],
        "poor": [("Schedule stack emission inspection within 24 hours", "spcb_inspector", 24)],
        "very_poor": [
            ("Priority inspection of stack emissions within 6 hours", "spcb_inspector", 6),
            ("Request operator to reduce production load temporarily if feasible", "site_operator", 6),
        ],
        "severe": [
            ("Emergency stack inspection + potential temporary shutdown order", "spcb_inspector", 2),
            ("Escalate to SPCB regional office for emergency directive", "spcb_regional_office", 2),
        ],
    },
    "dust": {
        "moderate": [("Schedule road/open-area water sprinkling in the ward", "municipal_ops", 24)],
        "poor": [("Increase water sprinkling frequency on unpaved roads/open areas", "municipal_ops", 12)],
        "very_poor": [("Deploy mechanical road sweepers + water sprinkling twice daily", "municipal_ops", 6)],
        "severe": [("Continuous water sprinkling + temporary green barriers at open dust sources", "municipal_ops", 2)],
    },
    "stubble_burning": {
        "moderate": [("Monitor NASA FIRMS thermal anomaly feed for the region", "agriculture_dept", 24)],
        "poor": [("Alert agriculture department to nearby active burning sites", "agriculture_dept", 12)],
        "very_poor": [
            ("Dispatch field team to active burning coordinates for immediate action", "agriculture_dept", 6),
            ("Issue regional health advisory for wards downwind of the burning zone", "citizen_comms", 6),
        ],
        "severe": [
            ("Emergency inter-district coordination to suppress active fires", "agriculture_dept", 2),
            ("Trigger GRAP Stage IV-equivalent regional health advisory", "citizen_comms", 2),
        ],
    },
}

# A missing attribution must still produce an actionable, explicitly
# diagnostic response instead of silently rendering an empty actions panel.
ACTION_MATRIX["unknown"] = {
    "satisfactory": [("Validate station calibration and inspect nearby sources", "field_inspector", 72)],
    "moderate": [("Validate station calibration and inspect nearby sources", "field_inspector", 48)],
    "poor": [("Dispatch a field inspection to identify the emission source", "field_inspector", 24)],
    "very_poor": [("Dispatch an urgent field inspection and verify the monitoring station", "field_inspector", 12)],
    "severe": [("Trigger emergency source investigation and verify monitoring data", "field_inspector", 4)],
}


@dataclass
class RecommendedAction:
    action: str
    responsible_role: str
    urgency_hours: int


@dataclass
class RecommendationBundle:
    ward: str
    source: str
    severity: str
    forecast_aqi: float
    actions: list[RecommendedAction] = field(default_factory=list)
    festival_context: Optional[str] = None


class RecommendationAgent:
    """
    Role: Converts source attribution + forecast severity into ranked,
          role-specific action recommendations.
    Inputs: AttributionResult (from Pollution Attribution Agent), forecast
            AQI (from Prediction Agent), optional festival-spike context
            (from Trend Analysis Agent).
    Outputs: RecommendationBundle (ready for the Admin Panel / Enforcement
             Prioritization Agent).
    Talks to: Enforcement Prioritization Agent (consumes actions tagged
              for inspector roles), Citizen Advisory Agent (consumes
              actions tagged for citizen_comms).
    """

    def severity_band(self, aqi: float) -> str:
        for low, high, band in AQI_SEVERITY_BANDS:
            if low <= aqi <= high:
                return band
        return "severe"

    def recommend(
        self,
        ward: str,
        source: str,
        forecast_aqi: float,
        festival_context: Optional[str] = None,
    ) -> RecommendationBundle:
        severity = self.severity_band(forecast_aqi)
        source_actions = ACTION_MATRIX.get(source, {})
        raw_actions = source_actions.get(severity, [])

        actions = [
            RecommendedAction(action=a, responsible_role=role, urgency_hours=hrs)
            for a, role, hrs in raw_actions
        ]
        # sort most urgent first
        actions.sort(key=lambda x: x.urgency_hours)

        return RecommendationBundle(
            ward=ward,
            source=source,
            severity=severity,
            forecast_aqi=forecast_aqi,
            actions=actions,
            festival_context=festival_context,
        )

    def recommend_from_attribution_and_forecast(self, attribution_result, forecast_result, festival_context=None) -> RecommendationBundle:
        """Convenience wrapper that takes the actual agent output objects directly."""
        return self.recommend(
            ward=attribution_result.ward,
            source=attribution_result.predicted_source,
            forecast_aqi=forecast_result.predicted_aqi,
            festival_context=festival_context,
        )


if __name__ == "__main__":
    agent = RecommendationAgent()
    bundle = agent.recommend(ward="Ward-2", source="construction", forecast_aqi=340)
    print(bundle)
