"""Normalizes observed OSM primary-road feature counts to a ward traffic proxy."""


class TrafficAnalysisAgent:
    def road_density_index(self, primary_road_count: int, normalization_count: int = 20) -> float:
        return round(min(1.0, max(0.0, primary_road_count / normalization_count)), 3)
