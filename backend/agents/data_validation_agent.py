"""Validation boundary for external air-quality records before database writes."""

from dataclasses import dataclass


@dataclass
class ValidationResult:
    valid: bool
    reason: str = ""


class DataValidationAgent:
    def validate_reading(self, record: dict) -> ValidationResult:
        required = ("station_name", "lat", "lon", "pm25", "aqi", "timestamp")
        if any(record.get(key) is None for key in required):
            return ValidationResult(False, "missing required reading field")
        if not (-90 <= float(record["lat"]) <= 90 and -180 <= float(record["lon"]) <= 180):
            return ValidationResult(False, "invalid coordinates")
        if not (0 <= float(record["pm25"]) and 0 <= int(record["aqi"]) <= 500):
            return ValidationResult(False, "invalid pollutant or AQI range")
        return ValidationResult(True)
