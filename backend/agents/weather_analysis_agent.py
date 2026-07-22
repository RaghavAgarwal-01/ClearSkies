"""Turns observed weather readings into an explicit dispersion indicator."""


class WeatherAnalysisAgent:
    def dispersion_risk(self, wind_speed_kmh: float | None, humidity_pct: float | None) -> str:
        if wind_speed_kmh is None or humidity_pct is None:
            return "unknown"
        if wind_speed_kmh < 5 and humidity_pct >= 70:
            return "poor"
        if wind_speed_kmh < 12:
            return "limited"
        return "favourable"
