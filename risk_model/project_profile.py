"""
Compact Project Profile schema and risk-to-exposure mapping.

This module defines the ~12-field "Project Profile" that replaces per-risk
manual Impact input. It does NOT contain any scoring logic — scoring stays
in ``ImpactEngine`` / the workbook-driven Impact rules. This module only:

1. Defines the profile fields (data schema);
2. Tracks a data status per field (CLIENT_PROVIDED / DERIVED /
   MODEL_ASSUMPTION / MISSING) so missing values are never silently
   converted to zero;
3. Maps each of the 36 Level-3 risks to the profile fields that are
   relevant to its Impact calculation (centralized instead of duplicated
   in UI code);
4. Converts a profile + status map into the exposure dict consumed by the
   existing (unmodified) ``ImpactEngine``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data status
# ---------------------------------------------------------------------------

class DataStatus:
    CLIENT_PROVIDED = "CLIENT_PROVIDED"
    DERIVED = "DERIVED"
    MODEL_ASSUMPTION = "MODEL_ASSUMPTION"
    MISSING = "MISSING"


# ---------------------------------------------------------------------------
# Field schema
# ---------------------------------------------------------------------------

@dataclass
class ProfileField:
    key: str
    label_cn: str
    section: str
    field_type: str  # "select" | "money" | "percent" | "yesno"
    mandatory: bool = False
    options: Optional[List[str]] = None


PROJECT_STAGE_OPTIONS = [
    "Opportunity Screening",
    "Pre-investment / Due Diligence",
    "Construction",
    "Operation",
]

PROFILE_FIELDS: List[ProfileField] = [
    # A. 项目基本信息
    ProfileField("project_stage", "项目阶段", "A. 项目基本信息", "select", mandatory=True, options=PROJECT_STAGE_OPTIONS),
    ProfileField("investment_amount", "项目总投资额", "A. 项目基本信息", "money"),
    ProfileField("annual_revenue", "预计/实际年营业收入", "A. 项目基本信息", "money"),
    ProfileField("annual_ebitda", "预计/实际 EBITDA", "A. 项目基本信息", "money"),
    ProfileField("total_debt", "项目总债务", "A. 项目基本信息", "money"),
    # B. 资金与财务暴露
    ProfileField("fx_debt_share", "外币债务占比 (%)", "B. 资金与财务暴露", "percent"),
    ProfileField("repatriation_requirement", "年度利润或资金汇回需求 (%)", "B. 资金与财务暴露", "percent"),
    # C. 经营与资产暴露
    ProfileField("local_asset_exposure", "当地资产暴露程度 (%)", "C. 经营与资产暴露", "percent"),
    ProfileField("import_dependency", "进口依赖度 (%)", "C. 经营与资产暴露", "percent"),
    ProfileField("government_soe_revenue_share", "政府或国企相关收入占比 (%)", "C. 经营与资产暴露", "percent"),
    ProfileField("regulated_revenue_share", "受政府定价/监管收入占比 (%)", "C. 经营与资产暴露", "percent"),
    # D. 关键依赖
    ProfileField("critical_license_dependency", "是否依赖关键政府许可或审批", "D. 关键依赖", "yesno"),
]

FIELDS_BY_KEY: Dict[str, ProfileField] = {f.key: f for f in PROFILE_FIELDS}
MANDATORY_FIELDS = [f.key for f in PROFILE_FIELDS if f.mandatory]
OPTIONAL_FIELDS = [f.key for f in PROFILE_FIELDS if not f.mandatory]
PERCENT_FIELDS = {f.key for f in PROFILE_FIELDS if f.field_type == "percent"}
MONEY_FIELDS = {f.key for f in PROFILE_FIELDS if f.field_type == "money"}


# ---------------------------------------------------------------------------
# Risk -> relevant profile fields mapping (centralized, not duplicated in UI)
# ---------------------------------------------------------------------------
# Best-effort mapping derived from each risk's workbook Impact核心驱动因素 /
# 计算方式口径 text. Where a risk's workbook Impact formula requires more
# granular data than this compact profile provides, the risk is still
# mapped to its closest relevant fields, but Impact will only be marked
# calculable when those specific fields are actually available - it is
# never forced to be "fully calculable" by inventing new fields.

RISK_EXPOSURE_MAP: Dict[str, List[str]] = {
    "政治稳定性风险": ["local_asset_exposure", "investment_amount"],
    "国家治理能力风险": ["critical_license_dependency", "investment_amount"],
    "战争与内乱风险": ["local_asset_exposure", "investment_amount"],
    "地缘政治、外交关系与国际制裁风险": ["fx_debt_share", "total_debt", "repatriation_requirement"],
    "对华关系风险": ["local_asset_exposure", "critical_license_dependency", "investment_amount"],
    "结构性风险": ["government_soe_revenue_share", "annual_revenue"],
    "通货膨胀风险": ["annual_revenue", "annual_ebitda"],
    "基础设施风险": ["investment_amount", "annual_revenue", "annual_ebitda"],
    "宏观经济增长风险": ["annual_revenue", "annual_ebitda"],
    "政府财政风险": ["government_soe_revenue_share", "regulated_revenue_share"],
    "外汇储备风险": ["fx_debt_share", "total_debt", "repatriation_requirement"],
    "主权信用风险": ["government_soe_revenue_share", "total_debt", "annual_ebitda"],
    "自然灾害与水文气候变化风险": ["local_asset_exposure", "annual_ebitda", "investment_amount"],
    "粮食与能源短缺风险": ["import_dependency", "annual_ebitda"],
    "传染病风险": ["annual_revenue"],
    "社会治安风险": ["local_asset_exposure", "investment_amount"],
    "对中资品牌接纳风险": ["annual_revenue", "government_soe_revenue_share"],
    "语言壁垒风险": [],  # workbook driver (document/language exposure share) not captured by compact profile - flagged as gap
    "宗教与文化差异风险": ["local_asset_exposure"],
    "间谍活动风险": ["critical_license_dependency", "investment_amount"],
    "网络勒索风险": ["annual_ebitda", "annual_revenue"],
    "数据泄露风险": ["annual_ebitda", "annual_revenue"],
    "政府腐败风险": ["government_soe_revenue_share", "critical_license_dependency"],
    "属地金融犯罪风险": ["annual_ebitda", "total_debt"],
    "法律环境风险": ["investment_amount", "annual_ebitda"],
    "外商投资政策风险": ["local_asset_exposure", "investment_amount", "critical_license_dependency"],
    "税收政策风险": ["annual_revenue", "annual_ebitda", "investment_amount"],
    "环保政策风险": ["investment_amount", "annual_ebitda"],
    "土地政策风险": ["local_asset_exposure", "investment_amount"],
    "劳动用工风险": ["annual_ebitda"],
    "外汇管制风险": ["fx_debt_share", "repatriation_requirement", "total_debt"],
    "国家征收风险": ["local_asset_exposure", "investment_amount", "critical_license_dependency"],
    "行业监管风险": ["regulated_revenue_share", "annual_ebitda"],
    "市场准入风险": ["critical_license_dependency", "investment_amount"],
    "行业投资优惠政策风险": ["annual_ebitda", "investment_amount"],
    "指导电价风险": ["regulated_revenue_share", "annual_revenue", "annual_ebitda"],
}


# ---------------------------------------------------------------------------
# Profile -> ImpactEngine canonical exposure key mapping
# ---------------------------------------------------------------------------
# ImpactEngine._METRIC_ALIASES already fuzzy-matches many of these canonical
# names; this mapping only decides which profile field feeds which engine
# exposure key. Impact scoring bands/thresholds/formulas themselves are
# untouched (they live in the workbook and ImpactEngine).

PROFILE_TO_ENGINE_KEY: Dict[str, str] = {
    "investment_amount": "project_investment_amount",
    "annual_revenue": "annual_revenue",
    "annual_ebitda": "ebitda",
    "total_debt": "total_debt",
    "fx_debt_share": "foreign_currency_debt_share",
    "repatriation_requirement": "annual_profit_repatriation",
    "local_asset_exposure": "local_asset_exposure",
    "import_dependency": "import_equipment_fuel_exposure",
    "government_soe_revenue_share": "government_soe_revenue_exposure",
    "regulated_revenue_share": "ppa_tariff_characteristics",
    "critical_license_dependency": "permits_licenses",
}


def field_status(profile: Dict[str, Any], status_map: Dict[str, str], key: str) -> str:
    """Return the data status for a field, defaulting to MISSING (never zero)."""
    value = profile.get(key)
    if value is None or value == "":
        return DataStatus.MISSING
    return status_map.get(key, DataStatus.CLIENT_PROVIDED)


def is_available(profile: Dict[str, Any], status_map: Dict[str, str], key: str) -> bool:
    return field_status(profile, status_map, key) != DataStatus.MISSING


def build_engine_exposure(profile: Dict[str, Any], status_map: Dict[str, str]) -> Dict[str, Any]:
    """
    Convert a ProjectProfile (+ status map) into the exposure dict consumed
    by ImpactEngine. Missing fields are simply omitted - never defaulted to
    zero - so ImpactEngine correctly reports missing-data / Not Calculable
    for risks that depend on them.
    """
    exposure: Dict[str, Any] = {}
    for key, engine_key in PROFILE_TO_ENGINE_KEY.items():
        if not is_available(profile, status_map, key):
            continue
        value = profile[key]
        if key == "critical_license_dependency":
            # Yes -> high dependency (treated as boolean redline-style flag
            # and as a high numeric exposure); No -> low; Unknown is MISSING
            # and already excluded above.
            if value == "Yes":
                exposure[engine_key] = True
            elif value == "No":
                exposure[engine_key] = False
            else:
                continue
        else:
            exposure[engine_key] = value
    return exposure


def completeness(profile: Dict[str, Any], status_map: Dict[str, str]) -> Dict[str, Any]:
    total = len(PROFILE_FIELDS)
    available = sum(1 for f in PROFILE_FIELDS if is_available(profile, status_map, f.key))
    pct = round(100.0 * available / total, 1) if total else 0.0
    return {"total_fields": total, "available_fields": available, "completeness_pct": pct}


def relevant_fields_for_risk(risk_name: str) -> List[str]:
    return RISK_EXPOSURE_MAP.get(risk_name, [])


def risk_relevant_completeness(risk_name: str, profile: Dict[str, Any], status_map: Dict[str, str]) -> Dict[str, Any]:
    """Completeness of the subset of profile fields relevant to one risk (used for Impact Confidence)."""
    keys = relevant_fields_for_risk(risk_name)
    if not keys:
        return {"total": 0, "available": 0, "assumption_count": 0, "pct": 0.0}
    available = 0
    assumption_count = 0
    for key in keys:
        status = field_status(profile, status_map, key)
        if status != DataStatus.MISSING:
            available += 1
        if status == DataStatus.MODEL_ASSUMPTION:
            assumption_count += 1
    pct = round(100.0 * available / len(keys), 1)
    return {"total": len(keys), "available": available, "assumption_count": assumption_count, "pct": pct}


def impact_confidence(risk_name: str, profile: Dict[str, Any], status_map: Dict[str, str]) -> str:
    """
    Impact Confidence is separate from the numerical Impact score. It is
    derived purely from completeness of the relevant exposure variables,
    never from the score itself.
    """
    stats = risk_relevant_completeness(risk_name, profile, status_map)
    if stats["total"] == 0 or stats["available"] == 0:
        return "NOT_ASSESSED"
    if stats["assumption_count"] > 0 and stats["assumption_count"] >= stats["available"]:
        return "LOW"
    if stats["pct"] >= 80:
        return "HIGH"
    if stats["pct"] >= 40:
        return "MEDIUM"
    return "LOW"


def build_risk_exposure(risk_name: str, profile: Dict[str, Any], status_map: Dict[str, str]) -> Dict[str, Any]:
    """
    Build the exposure dict passed into ImpactEngine.score_risk for one
    Level-3 risk, restricted to the profile fields mapped as relevant to
    that risk (see RISK_EXPOSURE_MAP). Missing fields are omitted rather
    than zero-filled. Risks with no mapped fields (a business-rule gap -
    the compact profile does not cover this risk's workbook Impact driver)
    return an empty dict so ImpactEngine reports Not Calculable.
    """
    relevant_keys = relevant_fields_for_risk(risk_name)
    if not relevant_keys:
        return {}
    full_exposure = build_engine_exposure(profile, status_map)
    relevant_engine_keys = {PROFILE_TO_ENGINE_KEY[k] for k in relevant_keys if k in PROFILE_TO_ENGINE_KEY}
    return {k: v for k, v in full_exposure.items() if k in relevant_engine_keys}


def score_risk_impact(risk_name: str, profile: Dict[str, Any], status_map: Dict[str, str], impact_rules_df):
    """
    Score Impact for one Level-3 risk using the compact Project Profile.
    Thin wrapper around the unmodified ImpactEngine: builds the risk-scoped
    exposure dict, calls ImpactEngine.score_risk, and attaches a separate
    Impact Confidence derived only from project-data completeness.
    """
    from .impact_engine import ImpactEngine

    exposure = build_risk_exposure(risk_name, profile, status_map)
    result = ImpactEngine.score_risk(risk_name, exposure, impact_rules_df)
    confidence = impact_confidence(risk_name, profile, status_map)
    not_calculable = result.discrete_score is None
    return result, confidence, not_calculable

