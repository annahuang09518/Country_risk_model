from __future__ import annotations

from typing import Any, Dict, Iterable, List

import pandas as pd
import streamlit as st


COMMON_PROJECT_METRICS = [
    "project_investment_amount",
    "total_assets",
    "annual_revenue",
    "ebitda",
    "annual_distributable_cash_flow",
    "local_currency_revenue_share",
    "foreign_currency_debt_share",
    "annual_profit_repatriation",
    "government_soe_revenue_exposure",
    "project_staff_count",
    "expected_operational_interruption_days",
    "uninsured_asset_exposure",
    "import_equipment_fuel_exposure",
    "permits_licenses",
    "subsidies_tax_incentives",
    "ppa_tariff_characteristics",
    "annual_operating_cost",
    "total_outstanding_debt",
    "foreign_currency_debt_service",
    "local_cash_balance",
    "insured_asset_value",
    "expatriate_employees",
    "chinese_employees",
]


def parse_value(raw: Any) -> Any:
    if raw is None or raw == "":
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return text
    return raw


def ensure_numeric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("%", "")
        if text in {"", "n/a", "N/A", "na", "NA", "nan", "None"}:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def required_country_indicators(params: Any) -> List[str]:
    required: List[str] = []
    for rule in getattr(params, "scoring_rules", []):
        for indicator in [rule.level_indicator, rule.trend_indicator, rule.event_indicator]:
            if indicator and indicator not in required:
                required.append(indicator)
    return required


def required_project_indicators(params: Any) -> List[str]:
    required: List[str] = []
    seen = set()
    for rule in getattr(params, "impact_rules", []):
        text = " ".join(
            [
                getattr(rule, "impact_driver", ""),
                getattr(rule, "calculation", ""),
                getattr(rule, "redline_rule", ""),
            ]
        )
        for metric in COMMON_PROJECT_METRICS:
            if metric.lower() in text.lower() or metric.replace("_", "").lower() in text.lower():
                if metric not in seen:
                    required.append(metric)
                    seen.add(metric)
    if not required:
        required = list(COMMON_PROJECT_METRICS)
    return required


def calculate_data_quality(params: Any, country_data: Dict[str, Dict[str, Any]], project_data: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    country_required = required_country_indicators(params)
    project_required = required_project_indicators(params)

    country_available = 0
    country_missing = []
    for indicator in country_required:
        present = False
        for risk_key, values in country_data.items():
            if indicator in values and values.get(indicator) not in (None, ""):
                present = True
                break
        if present:
            country_available += 1
        else:
            country_missing.append(indicator)

    project_available = 0
    project_missing = []
    for metric in project_required:
        present = False
        for risk_key, values in project_data.items():
            if metric in values and values.get(metric) not in (None, ""):
                present = True
                break
        if present:
            project_available += 1
        else:
            project_missing.append(metric)

    total_required = len(country_required) + len(project_required)
    available = country_available + project_available
    missing = len(country_missing) + len(project_missing)
    completeness = round((available / total_required) * 100, 1) if total_required else 0.0
    if completeness >= 85:
        confidence = "High"
    elif completeness >= 60:
        confidence = "Medium"
    else:
        confidence = "Low"

    return {
        "total_required_indicators": total_required,
        "available_required_indicators": available,
        "missing_required_indicators": missing,
        "data_completeness_pct": completeness,
        "confidence_level": confidence,
        "country_missing": country_missing,
        "project_missing": project_missing,
    }


def validate_assessment_setup() -> List[str]:
    errors: List[str] = []
    assessment = st.session_state.get("assessment", {})
    required = [
        ("name", "Assessment Name"),
        ("country", "Country"),
        ("project_name", "Project Name"),
        ("project_type", "Project Type"),
        ("project_stage", "Project Stage"),
    ]
    for key, label in required:
        if not assessment.get(key):
            errors.append(f"Missing required field: {label}")
    return errors


def validate_runtime_inputs(params: Any, country_data: Dict[str, Dict[str, Any]], project_data: Dict[str, Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    errors.extend(validate_assessment_setup())

    country_required = required_country_indicators(params)
    for indicator in country_required:
        found = False
        for risk_values in country_data.values():
            value = risk_values.get(indicator)
            if value not in (None, ""):
                found = True
                break
        if not found:
            errors.append(f"Required country indicator not supplied: {indicator} (explicitly mark missing if unavailable)")

    project_required = required_project_indicators(params)
    for metric in project_required:
        found = False
        for risk_values in project_data.values():
            value = risk_values.get(metric)
            if value not in (None, ""):
                found = True
                break
        if not found:
            errors.append(f"Required project input not supplied: {metric} (explicitly mark missing if unavailable)")

    for risk_key, values in country_data.items():
        for metric, raw_value in values.items():
            if isinstance(raw_value, str):
                if "%" in raw_value and (not 0 <= float(raw_value.replace("%", "")) <= 100):
                    errors.append(f"Percentage out of range for {risk_key}.{metric}")
            numeric = ensure_numeric(raw_value)
            if numeric is not None and numeric < 0:
                errors.append(f"Negative value for {risk_key}.{metric} is not allowed unless explicitly supported by the model.")

    for risk_key, values in project_data.items():
        for metric, raw_value in values.items():
            if isinstance(raw_value, str):
                if "%" in raw_value and (not 0 <= float(raw_value.replace("%", "")) <= 100):
                    errors.append(f"Percentage out of range for {risk_key}.{metric}")
            numeric = ensure_numeric(raw_value)
            if numeric is not None and numeric < 0:
                errors.append(f"Negative value for {risk_key}.{metric} is not allowed unless explicitly supported by the model.")

    return errors


def render_validation_summary() -> None:
    errors = validate_assessment_setup()
    if errors:
        st.warning("评估输入存在以下问题：")
        for error in errors:
            st.write(f"- {error}")
    else:
        st.success("当前评估流程所需输入已完整。")


def build_indicator_rule_table(risk_name: str, indicator_name: str, signal_type: str, score_columns: Dict[int, str]) -> pd.DataFrame:
    row = {"risk_id": risk_name, "indicator_id": indicator_name, "signal_type": signal_type}
    for score_num, col_name in score_columns.items():
        row[f"score_{score_num}"] = col_name
    return pd.DataFrame([row])


def workbook_scoring_frame(params: Any) -> pd.DataFrame:
    rows = []
    for rule in getattr(params, "scoring_rules", []):
        rows.append(
            {
                "风险大类": rule.risk_family,
                "三级风险": rule.risk_name,
                "风险类型": rule.risk_type,
                "Level指标/基础": rule.level_indicator,
                "Level口径": rule.level_scale,
                "Score 1": rule.score_1,
                "Score 2": rule.score_2,
                "Score 3": rule.score_3,
                "Score 4": rule.score_4,
                "Score 5": rule.score_5,
                "Trend指标": rule.trend_indicator,
                "Trend 1": rule.trend_1,
                "Trend 2": rule.trend_2,
                "Trend 3": rule.trend_3,
                "Trend 4": rule.trend_4,
                "Trend 5": rule.trend_5,
                "Event指标": rule.event_indicator,
                "Event 1": rule.event_1,
                "Event 2": rule.event_2,
                "Event 3": rule.event_3,
                "Event 4": rule.event_4,
                "Event 5": rule.event_5,
                "Level权重": rule.level_weight,
                "Trend权重": rule.trend_weight,
                "Event权重": rule.event_weight,
                "Likelihood公式": rule.likelihood_formula,
                "Likelihood等级映射": rule.likelihood_mapping,
                "参数状态": rule.status,
            }
        )
    return pd.DataFrame(rows)


def workbook_impact_frame(params: Any) -> pd.DataFrame:
    rows = []
    for rule in getattr(params, "impact_rules", []):
        rows.append(
            {
                "三级风险": rule.risk_name,
                "Impact核心驱动因素": rule.impact_driver,
                "计算方式/口径": rule.calculation,
                "Impact 1": rule.impact_1,
                "Impact 2": rule.impact_2,
                "Impact 3": rule.impact_3,
                "Impact 4": rule.impact_4,
                "Impact 5": rule.impact_5,
                "红线/Floor规则": rule.redline_rule,
                "建议统一分母": rule.denominator,
                "参数状态": rule.status,
            }
        )
    return pd.DataFrame(rows)
