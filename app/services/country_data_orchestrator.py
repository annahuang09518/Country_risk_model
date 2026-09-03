"""Country-data automation orchestrator.

Wires together (in this order, matching the required calculation sequence):

    country selection
    -> IndicatorSourceRegistry (which connector/series applies to which
       workbook Level/Trend/Event indicator)
    -> CountryDataService (fetch, with fallback chain, never fabricating
       zero for missing data)
    -> trend_calculator (pure historical-series -> raw trend value
       transformation, still workbook-band-scored downstream)
    -> IndicatorScoringEngine (UNCHANGED - scores the raw/trend value
       against the workbook's own bands)

This module contains no scoring thresholds and no risk-rating logic. It
only automates data acquisition for indicators that genuinely have an
authoritative source (per docs/country_data_automation_mapping.csv and
src/indicator_source_registry.py); everything else is explicitly left for
manual analyst input with a MISSING/MANUAL status, never a fabricated
default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from risk_model import IndicatorScoringEngine, ScoringRule
from src.country_reference import lookup_country
from src.data_sources import CountryDataService, IMFDataSource, WGIDataSource, WorldBankDataSource
from src.data_sources.base import CountryDataRecord
from src.indicator_source_registry import find_mapping
from src.trend_calculator import calculate_trend

STATUS_AUTO = "AUTO"
STATUS_MANUAL = "MANUAL"
STATUS_MISSING = "MISSING"

_CONNECTOR_REGISTRY = {
    "world_bank": WorldBankDataSource,
    "wgi": WGIDataSource,
    "imf": IMFDataSource,
}


@dataclass
class IndicatorAutomationResult:
    risk_level_3: str
    signal_type: str
    indicator_name: str
    status: str  # AUTO / MANUAL / MISSING
    raw_value: Optional[float]
    unit: str = ""
    source_name: str = ""
    source_url: str = ""
    observation_date: str = ""
    retrieved_at: str = ""
    confidence: str = "Low"
    trend_rationale: str = ""
    standardized_score: Optional[int] = None
    matched_band: Optional[str] = None
    scoring_rationale: str = ""
    missing_data: bool = True


@dataclass
class CountryAutomationSummary:
    country_iso3: str
    results: Dict[str, Dict[str, IndicatorAutomationResult]] = field(default_factory=dict)
    total_indicators: int = 0
    automated_count: int = 0
    missing_count: int = 0

    @property
    def completeness_pct(self) -> float:
        if self.total_indicators == 0:
            return 0.0
        return round(100.0 * (self.total_indicators - self.missing_count) / self.total_indicators, 1)


def _build_service() -> CountryDataService:
    return CountryDataService([WorldBankDataSource(), WGIDataSource(), IMFDataSource()])


def _score_against_rule(risk_name: str, indicator_name: str, signal_type: str, raw_value: Any, rule: ScoringRule):
    if raw_value is None or not indicator_name:
        return None
    score_map = {
        "Level": [rule.score_1, rule.score_2, rule.score_3, rule.score_4, rule.score_5],
        "Trend": [rule.trend_1, rule.trend_2, rule.trend_3, rule.trend_4, rule.trend_5],
        "Event": [rule.event_1, rule.event_2, rule.event_3, rule.event_4, rule.event_5],
    }
    payload = {"risk_id": risk_name, "indicator_id": indicator_name, "signal_type": signal_type}
    for idx, band in enumerate(score_map.get(signal_type, []), start=1):
        payload[f"score_{idx}"] = band
    table = pd.DataFrame([payload])
    return IndicatorScoringEngine.score_indicator(
        risk_id=risk_name,
        indicator_id=indicator_name,
        raw_value=raw_value,
        parameter_table=table,
        signal_type=signal_type,
    )


class CountryDataOrchestrator:
    """Automates country-level indicator retrieval for all mapped risks."""

    def __init__(self, service: Optional[CountryDataService] = None):
        self.service = service or _build_service()

    def fetch_for_risk(
        self,
        country_code: str,
        risk_level_3: str,
        signal_type: str,
        indicator_name: str,
        rule: ScoringRule,
    ) -> IndicatorAutomationResult:
        country = lookup_country(country_code)
        iso3 = country.iso3 if country else (country_code or "").upper()
        mapping = find_mapping(risk_level_3, signal_type)

        if mapping is None or not iso3:
            return IndicatorAutomationResult(
                risk_level_3=risk_level_3,
                signal_type=signal_type,
                indicator_name=indicator_name,
                status=STATUS_MANUAL,
                raw_value=None,
                confidence="Low",
                missing_data=True,
                scoring_rationale="No automated source mapped for this indicator; analyst input required.",
            )

        if signal_type == "Trend":
            records = self.service.fetch_historical(
                iso3, mapping.series_code, max_age_years=999
            )
            trend = calculate_trend(records, window_years=mapping.trend_window_years, method=mapping.trend_method)
            if trend.missing_data or trend.trend_raw_value is None:
                return IndicatorAutomationResult(
                    risk_level_3=risk_level_3,
                    signal_type=signal_type,
                    indicator_name=indicator_name,
                    status=STATUS_MISSING,
                    raw_value=None,
                    confidence="Low",
                    missing_data=True,
                    trend_rationale=trend.rationale,
                    scoring_rationale="Historical data insufficient to compute trend automatically.",
                )
            latest_record = records[0] if records else None
            scoring_result = _score_against_rule(risk_level_3, indicator_name, signal_type, trend.trend_raw_value, rule)
            return IndicatorAutomationResult(
                risk_level_3=risk_level_3,
                signal_type=signal_type,
                indicator_name=indicator_name,
                status=STATUS_AUTO,
                raw_value=trend.trend_raw_value,
                unit=getattr(latest_record, "unit", "") if latest_record else "",
                source_name=getattr(latest_record, "source_name", "") if latest_record else "",
                source_url=getattr(latest_record, "source_url", "") if latest_record else "",
                observation_date=trend.latest_date or "",
                retrieved_at=getattr(latest_record, "retrieved_at", "") if latest_record else "",
                confidence=getattr(latest_record, "confidence", "Medium") if latest_record else "Medium",
                trend_rationale=trend.rationale,
                standardized_score=scoring_result.standardized_score if scoring_result else None,
                matched_band=scoring_result.matched_band if scoring_result else None,
                scoring_rationale=scoring_result.scoring_rationale if scoring_result else "",
                missing_data=False,
            )

        record: CountryDataRecord = self.service.fetch_indicator(iso3, mapping.series_code)
        if record.status != "available" or record.raw_value is None:
            return IndicatorAutomationResult(
                risk_level_3=risk_level_3,
                signal_type=signal_type,
                indicator_name=indicator_name,
                status=STATUS_MISSING,
                raw_value=None,
                confidence="Low",
                missing_data=True,
                scoring_rationale="Automated source returned no data; falling back to manual input.",
            )

        scoring_result = _score_against_rule(risk_level_3, indicator_name, signal_type, record.raw_value, rule)
        return IndicatorAutomationResult(
            risk_level_3=risk_level_3,
            signal_type=signal_type,
            indicator_name=indicator_name,
            status=STATUS_AUTO,
            raw_value=record.raw_value,
            unit=record.unit,
            source_name=record.source_name,
            source_url=record.source_url,
            observation_date=record.observation_date,
            retrieved_at=record.retrieved_at,
            confidence=record.confidence,
            standardized_score=scoring_result.standardized_score if scoring_result else None,
            matched_band=scoring_result.matched_band if scoring_result else None,
            scoring_rationale=scoring_result.scoring_rationale if scoring_result else "",
            missing_data=False,
        )

    def fetch_country_data(self, country_code: str, params) -> CountryAutomationSummary:
        country_entry = lookup_country(country_code)
        summary = CountryAutomationSummary(country_iso3=country_entry.iso3 if country_entry else (country_code or "").upper())
        for risk in params.risks:
            rule = next((item for item in params.scoring_rules if item.risk_name == risk.level_3), None)
            if rule is None:
                continue
            indicators = []
            if rule.level_indicator:
                indicators.append(("Level", rule.level_indicator))
            if rule.trend_indicator:
                indicators.append(("Trend", rule.trend_indicator))
            if rule.event_indicator:
                indicators.append(("Event", rule.event_indicator))

            risk_results: Dict[str, IndicatorAutomationResult] = {}
            for signal_type, indicator_name in indicators:
                summary.total_indicators += 1
                result = self.fetch_for_risk(country_code, risk.level_3, signal_type, indicator_name, rule)
                risk_results[indicator_name] = result
                if result.status == STATUS_AUTO:
                    summary.automated_count += 1
                if result.status == STATUS_MISSING:
                    summary.missing_count += 1
            summary.results[risk.level_3] = risk_results
        return summary
