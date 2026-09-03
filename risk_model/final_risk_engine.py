from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

from .impact_engine import ImpactEngine, ImpactResult
from .likelihood_engine import LikelihoodEngine, LikelihoodResult


@dataclass
class RiskRatingResult:
    risk_id: str
    likelihood_score: Optional[int]
    impact_score: Optional[int]
    baseline_risk_rating: Optional[str]
    override_triggered: str
    override_reason: str
    final_risk_rating: Optional[str]


class RiskRatingEngine:
    _RISK_LABEL_MAP = {
        "low": "Low",
        "低": "Low",
        "medium": "Medium",
        "中": "Medium",
        "moderate": "Medium",
        "high": "High",
        "高": "High",
    }

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _normalize_matrix_label(raw_value: Any) -> Optional[str]:
        text = RiskRatingEngine._normalize_text(raw_value)
        if not text:
            return None
        lower = text.lower()
        for key, label in RiskRatingEngine._RISK_LABEL_MAP.items():
            if key in lower:
                return label
        return None

    @staticmethod
    def _lookup_baseline_risk(likelihood_score: Optional[int], impact_score: Optional[int], risk_matrix_df: pd.DataFrame) -> Optional[str]:
        if likelihood_score is None or impact_score is None:
            return None
        if likelihood_score not in risk_matrix_df.index:
            raise ValueError(f"Likelihood score {likelihood_score} is not present in the risk matrix.")
        if impact_score not in risk_matrix_df.columns:
            raise ValueError(f"Impact score {impact_score} is not present in the risk matrix.")
        matrix_value = risk_matrix_df.loc[likelihood_score, impact_score]
        return RiskRatingEngine._normalize_matrix_label(matrix_value)

    @staticmethod
    def _override_rating(baseline: Optional[str]) -> str:
        if baseline is None:
            return "High"
        return "High" if baseline != "High" else "High"

    @staticmethod
    def _detect_override(
        risk_id: Any,
        likelihood_result: LikelihoodResult,
        impact_result: ImpactResult,
        risk_override_text: str = "",
    ) -> tuple[str, str]:
        if impact_result.applied_floor is not None:
            return "yes", f"Impact red-line/floor triggered: {impact_result.floor_rule or 'impact floor'}"

        if risk_override_text:
            text = RiskRatingEngine._normalize_text(risk_override_text)
            if any(token in text for token in ["战争", "制裁", "征收", "国有化", "许可失败", "汇出", "禁止", "退出", "核心许可", "核心支付"]):
                return "yes", text

        if likelihood_result.missing_data or impact_result.missing_data:
            return "no", "No override rule triggered; data completeness issue remains a missing-data flag rather than an override."

        return "no", "No override rule triggered."

    @staticmethod
    def score_risk(
        risk_id: Any,
        likelihood_indicator_values: Dict[str, Any],
        impact_exposure_values: Dict[str, Any],
        scoring_rules_df: pd.DataFrame,
        impact_rules_df: pd.DataFrame,
        risk_matrix_df: pd.DataFrame,
        risk_override_text: str = "",
    ) -> RiskRatingResult:
        likelihood_result = LikelihoodEngine.score_risk(risk_id, likelihood_indicator_values, scoring_rules_df)
        impact_result = ImpactEngine.score_risk(risk_id, impact_exposure_values, impact_rules_df)

        baseline_exposure = dict(impact_exposure_values)
        for key in list(baseline_exposure.keys()):
            norm = key.lower().replace("_", "").replace("-", "")
            if any(token in norm for token in ["warzone", "redline", "coreassets", "criticalassets", "coresystem", "keysystem", "nationalization", "permitfailure"]):
                del baseline_exposure[key]

        baseline_impact_result = ImpactEngine.score_risk(risk_id, baseline_exposure, impact_rules_df)

        baseline_rating = RiskRatingEngine._lookup_baseline_risk(
            likelihood_result.discrete_score,
            baseline_impact_result.discrete_score,
            risk_matrix_df,
        )

        override_triggered, override_reason = RiskRatingEngine._detect_override(
            risk_id,
            likelihood_result,
            impact_result,
            risk_override_text=risk_override_text,
        )

        final_rating = baseline_rating
        if override_triggered == "yes":
            final_rating = RiskRatingEngine._override_rating(baseline_rating)

        return RiskRatingResult(
            risk_id=str(risk_id),
            likelihood_score=likelihood_result.discrete_score,
            impact_score=impact_result.discrete_score,
            baseline_risk_rating=baseline_rating,
            override_triggered=override_triggered,
            override_reason=override_reason,
            final_risk_rating=final_rating,
        )

    @staticmethod
    def score_many(
        risk_ids: list[Any],
        likelihood_indicator_values_by_risk: Dict[str, Dict[str, Any]],
        impact_exposure_values_by_risk: Dict[str, Dict[str, Any]],
        scoring_rules_df: pd.DataFrame,
        impact_rules_df: pd.DataFrame,
        risk_matrix_df: pd.DataFrame,
        override_text_by_risk: Optional[Dict[str, str]] = None,
    ) -> Dict[str, RiskRatingResult]:
        override_text_by_risk = override_text_by_risk or {}
        results: Dict[str, RiskRatingResult] = {}
        for risk_id in risk_ids:
            results[str(risk_id)] = RiskRatingEngine.score_risk(
                risk_id,
                likelihood_indicator_values_by_risk.get(str(risk_id), {}),
                impact_exposure_values_by_risk.get(str(risk_id), {}),
                scoring_rules_df,
                impact_rules_df,
                risk_matrix_df,
                risk_override_text=override_text_by_risk.get(str(risk_id), ""),
            )
        return results
