"""Pure historical-series -> trend raw-value transformation.

This module NEVER invents scoring thresholds. It only converts a series of
raw historical observations into the kind of raw comparison value (e.g. a
percentage-point / percent change over N years) that the workbook's own
Trend scoring bands (``trend_1``..``trend_5`` text) already expect as input
to ``risk_model.indicator_engine.IndicatorScoringEngine``.

The resulting raw value is then scored by the *existing, unmodified*
IndicatorScoringEngine against the workbook's Trend bands - this module does
not decide what counts as "high" or "low" risk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

DEFAULT_TREND_WINDOW_YEARS = 3


@dataclass
class TrendObservation:
    observation_date: str
    raw_value: float


@dataclass
class TrendCalculationResult:
    trend_raw_value: Optional[float]
    latest_value: Optional[float]
    baseline_value: Optional[float]
    latest_date: Optional[str]
    baseline_date: Optional[str]
    window_years: int
    method: str
    missing_data: bool
    rationale: str


def _extract_year(date_str: str) -> Optional[int]:
    if not date_str:
        return None
    text = str(date_str).strip()
    for chunk in (text[:4], text):
        try:
            return int(chunk)
        except ValueError:
            continue
    return None


def _sort_observations(observations: Sequence[Any]) -> List[TrendObservation]:
    parsed: List[TrendObservation] = []
    for obs in observations:
        date = getattr(obs, "observation_date", None)
        value = getattr(obs, "raw_value", None)
        if date is None and isinstance(obs, dict):
            date = obs.get("observation_date")
            value = obs.get("raw_value")
        if value is None or not isinstance(value, (int, float)):
            continue
        year = _extract_year(str(date))
        if year is None:
            continue
        parsed.append(TrendObservation(observation_date=str(date), raw_value=float(value)))
    parsed.sort(key=lambda o: _extract_year(o.observation_date) or 0, reverse=True)
    return parsed


def calculate_trend(
    historical_records: Sequence[Any],
    window_years: int = DEFAULT_TREND_WINDOW_YEARS,
    method: str = "absolute_change",
) -> TrendCalculationResult:
    """Convert a historical observation series into a single trend raw value.

    ``method``:
        - "absolute_change": latest_value - value_from_window_years_ago
        - "percent_change": (latest_value - baseline_value) / abs(baseline_value) * 100

    The window (default 3 years, matching the workbook's most common
    "3-year change" Trend indicator wording) and method are configuration,
    not invented thresholds - the *scoring* of the resulting raw value is
    still performed by the workbook-driven IndicatorScoringEngine.
    """
    observations = _sort_observations(historical_records)
    if not observations:
        return TrendCalculationResult(
            trend_raw_value=None,
            latest_value=None,
            baseline_value=None,
            latest_date=None,
            baseline_date=None,
            window_years=window_years,
            method=method,
            missing_data=True,
            rationale="No historical observations available; trend cannot be calculated.",
        )

    latest = observations[0]
    latest_year = _extract_year(latest.observation_date)
    target_year = (latest_year or 0) - window_years

    baseline = None
    for obs in observations[1:]:
        year = _extract_year(obs.observation_date)
        if year is not None and year <= target_year:
            baseline = obs
            break
    if baseline is None and len(observations) > 1:
        # Fall back to the oldest available observation if the exact window
        # year is not present, rather than silently reporting missing data.
        baseline = observations[-1]

    if baseline is None:
        return TrendCalculationResult(
            trend_raw_value=None,
            latest_value=latest.raw_value,
            baseline_value=None,
            latest_date=latest.observation_date,
            baseline_date=None,
            window_years=window_years,
            method=method,
            missing_data=True,
            rationale=(
                f"Only one historical observation available ({latest.observation_date}); "
                f"a {window_years}-year comparison point is missing."
            ),
        )

    if method == "percent_change":
        if baseline.raw_value == 0:
            trend_value = None
            rationale = "Baseline value is zero; percent-change trend is undefined."
            missing = True
        else:
            trend_value = (latest.raw_value - baseline.raw_value) / abs(baseline.raw_value) * 100
            rationale = (
                f"Percent change from {baseline.observation_date} ({baseline.raw_value}) to "
                f"{latest.observation_date} ({latest.raw_value}) = {trend_value:.2f}%."
            )
            missing = False
    else:
        trend_value = latest.raw_value - baseline.raw_value
        rationale = (
            f"Absolute change from {baseline.observation_date} ({baseline.raw_value}) to "
            f"{latest.observation_date} ({latest.raw_value}) = {trend_value:.2f}."
        )
        missing = False

    return TrendCalculationResult(
        trend_raw_value=trend_value,
        latest_value=latest.raw_value,
        baseline_value=baseline.raw_value,
        latest_date=latest.observation_date,
        baseline_date=baseline.observation_date,
        window_years=window_years,
        method=method,
        missing_data=missing,
        rationale=rationale,
    )
