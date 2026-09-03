from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from .indicator_engine import IndicatorScoringEngine


@dataclass
class LikelihoodContributor:
    signal_type: str
    indicator_id: str
    raw_value: Any
    sub_score: Optional[int]
    weight: float
    weighted_contribution: Optional[float]
    matched_band: Optional[str]
    missing_data: bool = False


@dataclass
class LikelihoodResult:
    risk_id: str
    risk_name: str
    formula: str
    level_weight: float
    trend_weight: float
    event_weight: float
    level_indicator: Optional[str]
    trend_indicator: Optional[str]
    event_indicator: Optional[str]
    level_subscore: Optional[int]
    trend_subscore: Optional[int]
    event_subscore: Optional[int]
    weighted_raw_score: Optional[float]
    discrete_score: Optional[int]
    top_contributing_indicators: List[LikelihoodContributor] = field(default_factory=list)
    missing_data: bool = False


class LikelihoodEngine:
    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return ""
        return str(value).strip()

    @staticmethod
    def _parse_weight(value: Any) -> float:
        text = LikelihoodEngine._normalize_text(value)
        if not text:
            return 0.0
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if text.endswith("%"):
            return float(text.rstrip("%")) / 100.0
        cleaned = text.replace("%", "")
        try:
            num = float(cleaned)
            return num if num <= 1 else num / 100.0
        except ValueError:
            return 0.0

    @staticmethod
    def _parse_mapping(mapping_text: str) -> List[tuple[float, float, int]]:
        if not mapping_text:
            return []
        parts = re.split(r"[;；,]", mapping_text)
        parsed: List[tuple[float, float, int]] = []
        for part in parts:
            if not part.strip():
                continue
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*[–-]\s*([0-9]+(?:\.[0-9]+)?)\s*[:=]?\s*(\d)", part)
            if match:
                low, high, score = match.groups()
                parsed.append((float(low), float(high), int(score)))
                continue
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*<=?\s*.*?=\s*(\d)", part)
            if match:
                value, score = match.groups()
                parsed.append((float(value), float(value), int(score)))
                continue
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*\.?\s*?=\s*(\d)", part)
            if match:
                value, score = match.groups()
                parsed.append((float(value), float(value), int(score)))
        return parsed

    @staticmethod
    def _discrete_from_raw(raw_score: float, mapping_text: str) -> int:
        if not mapping_text:
            return max(1, min(5, int(round(raw_score))))
        ranges = LikelihoodEngine._parse_mapping(mapping_text)
        if not ranges:
            return max(1, min(5, int(round(raw_score))))
        for low, high, score in ranges:
            if low <= raw_score <= high:
                return score
        if raw_score < ranges[0][0]:
            return 1
        return 5

    @staticmethod
    def _resolve_risk_row(scoring_rules_df: pd.DataFrame, risk_id: Any) -> pd.Series:
        risk_name = LikelihoodEngine._normalize_text(risk_id)
        for _, row in scoring_rules_df.iterrows():
            name = LikelihoodEngine._normalize_text(row.get("三级风险"))
            if name.lower() == risk_name.lower():
                return row
        matches = scoring_rules_df[scoring_rules_df.iloc[:, 1].astype(str).str.lower().str.contains(risk_name.lower(), na=False)]
        if not matches.empty:
            return matches.iloc[0]
        raise ValueError(f"No scoring rule row found for risk_id={risk_id}.")

    @staticmethod
    def _build_indicator_rule(row: pd.Series, signal_type: str, indicator_name: str) -> pd.DataFrame:
        mapping = {
            "Level": ["Score 1", "Score 2", "Score 3", "Score 4", "Score 5"],
            "Trend": ["Trend 1", "Trend 2", "Trend 3", "Trend 4", "Trend 5"],
            "Event": ["Event 1", "Event 2", "Event 3", "Event 4", "Event 5"],
        }
        score_columns = mapping.get(signal_type, ["Score 1", "Score 2", "Score 3", "Score 4", "Score 5"])
        payload = {
            "risk_id": LikelihoodEngine._normalize_text(row.get("三级风险")),
            "indicator_id": LikelihoodEngine._normalize_text(indicator_name),
            "signal_type": signal_type,
        }
        for score_idx, col in enumerate(score_columns, start=1):
            payload[f"score_{score_idx}"] = row.get(col)
        return pd.DataFrame([payload])

    @staticmethod
    def _score_signal(
        risk_name: Any,
        signal_type: str,
        indicator_name: str,
        raw_value: Any,
        rule_row: pd.Series,
    ) -> LikelihoodContributor:
        indicator_rule = LikelihoodEngine._build_indicator_rule(rule_row, signal_type, indicator_name)
        score_result = IndicatorScoringEngine.score_indicator(
            risk_id=risk_name,
            indicator_id=indicator_name,
            raw_value=raw_value,
            parameter_table=indicator_rule,
            signal_type=signal_type,
        )
        weight = 0.0
        if signal_type == "Level":
            weight = LikelihoodEngine._parse_weight(rule_row.get("Level权重"))
        elif signal_type == "Trend":
            weight = LikelihoodEngine._parse_weight(rule_row.get("Trend权重"))
        elif signal_type == "Event":
            weight = LikelihoodEngine._parse_weight(rule_row.get("Event权重"))

        weighted_contribution = None if score_result.standardized_score is None else weight * score_result.standardized_score
        return LikelihoodContributor(
            signal_type=signal_type,
            indicator_id=indicator_name,
            raw_value=raw_value,
            sub_score=score_result.standardized_score,
            weight=weight,
            weighted_contribution=weighted_contribution,
            matched_band=score_result.matched_band,
            missing_data=score_result.missing_data,
        )

    @staticmethod
    def score_risk(
        risk_id: Any,
        indicator_values: Dict[str, Any],
        scoring_rules_df: pd.DataFrame,
    ) -> LikelihoodResult:
        rule_row = LikelihoodEngine._resolve_risk_row(scoring_rules_df, risk_id)
        risk_name = LikelihoodEngine._normalize_text(rule_row.get("三级风险"))

        level_indicator = LikelihoodEngine._normalize_text(rule_row.get("Level指标/基础"))
        trend_indicator = LikelihoodEngine._normalize_text(rule_row.get("Trend指标"))
        event_indicator = LikelihoodEngine._normalize_text(rule_row.get("Event指标"))

        level_weight = LikelihoodEngine._parse_weight(rule_row.get("Level权重"))
        trend_weight = LikelihoodEngine._parse_weight(rule_row.get("Trend权重"))
        event_weight = LikelihoodEngine._parse_weight(rule_row.get("Event权重"))

        contributors: List[LikelihoodContributor] = []
        level_value = indicator_values.get(level_indicator) if level_indicator else None
        trend_value = indicator_values.get(trend_indicator) if trend_indicator else None
        event_value = indicator_values.get(event_indicator) if event_indicator else None

        level_contributor = LikelihoodEngine._score_signal(risk_name, "Level", level_indicator, level_value, rule_row) if level_indicator else None
        trend_contributor = LikelihoodEngine._score_signal(risk_name, "Trend", trend_indicator, trend_value, rule_row) if trend_indicator else None
        event_contributor = LikelihoodEngine._score_signal(risk_name, "Event", event_indicator, event_value, rule_row) if event_indicator else None

        for item in [level_contributor, trend_contributor, event_contributor]:
            if item is not None:
                contributors.append(item)

        level_score = level_contributor.sub_score if level_contributor is not None else None
        trend_score = trend_contributor.sub_score if trend_contributor is not None else None
        event_score = event_contributor.sub_score if event_contributor is not None else None

        weighted_parts = []
        if level_score is not None:
            weighted_parts.append(level_weight * level_score)
        if trend_score is not None:
            weighted_parts.append(trend_weight * trend_score)
        if event_score is not None:
            weighted_parts.append(event_weight * event_score)

        raw_score = sum(weighted_parts) if weighted_parts else None
        mapping_text = LikelihoodEngine._normalize_text(rule_row.get("Likelihood等级映射"))
        discrete_score = LikelihoodEngine._discrete_from_raw(raw_score, mapping_text) if raw_score is not None else None

        missing_data = any(item is not None and item.missing_data for item in [level_contributor, trend_contributor, event_contributor])
        top_contributors = sorted(
            [item for item in contributors if item is not None and item.weight > 0 and item.sub_score is not None],
            key=lambda item: (item.weighted_contribution or 0.0),
            reverse=True,
        )[:3]

        return LikelihoodResult(
            risk_id=str(risk_id),
            risk_name=risk_name,
            formula=LikelihoodEngine._normalize_text(rule_row.get("Likelihood公式")),
            level_weight=level_weight,
            trend_weight=trend_weight,
            event_weight=event_weight,
            level_indicator=level_indicator or None,
            trend_indicator=trend_indicator or None,
            event_indicator=event_indicator or None,
            level_subscore=level_score,
            trend_subscore=trend_score,
            event_subscore=event_score,
            weighted_raw_score=raw_score,
            discrete_score=discrete_score,
            top_contributing_indicators=top_contributors,
            missing_data=missing_data,
        )

    @staticmethod
    def score_many(
        scoring_rules_df: pd.DataFrame,
        indicator_values_by_risk: Dict[str, Dict[str, Any]],
    ) -> Dict[str, LikelihoodResult]:
        results: Dict[str, LikelihoodResult] = {}
        for risk_id, indicator_values in indicator_values_by_risk.items():
            results[risk_id] = LikelihoodEngine.score_risk(risk_id, indicator_values, scoring_rules_df)
        return results
