from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from .indicator_engine import IndicatorScoringEngine


@dataclass
class ImpactContributor:
    metric_name: str
    raw_value: Any
    normalized_value: Optional[float]
    weight: float
    score: Optional[int]
    matched_band: Optional[str]
    missing_data: bool = False
    rationale: str = ""


@dataclass
class ImpactResult:
    risk_id: str
    risk_name: str
    driver: str
    calculation: str
    raw_score: Optional[float]
    discrete_score: Optional[int]
    matched_band: Optional[str]
    floor_rule: str
    applied_floor: Optional[int]
    missing_data: bool = False
    contributors: List[ImpactContributor] = field(default_factory=list)
    explanation: str = ""


class ImpactEngine:
    _METRIC_ALIASES = {
        "project_investment_amount": ["project_investment_amount", "project_investment", "total_investment", "项目总投资", "投资额", "项目投资", "capex", "investment"],
        "total_assets": ["total_assets", "total_asset_value", "assets", "总资产", "资产总额", "asset_value"],
        "annual_revenue": ["annual_revenue", "revenue", "年收入", "营业收入", "收入", "revenue_total"],
        "ebitda": ["ebitda", "earnings_before_interest_tax_and_depreciation", "ebit", "EBITDA", "息税折旧摊销前利润", "利润", "earnings_before_interest"],
        "annual_distributable_cash_flow": ["annual_distributable_cash_flow", "distributable_cash_flow", "free_cash_flow", "FCF", "可分配现金流", "自由现金流", "annual_cash_flow"],
        "total_debt": ["total_debt", "total_outstanding_debt", "project_debt", "总债务", "项目总债务", "债务总额"],
        "local_asset_exposure": ["local_asset_exposure", "local_asset_exposure_pct", "当地资产暴露", "当地资产暴露程度"],
        "local_currency_revenue_share": ["local_currency_revenue_share", "revenue_share_local_currency", "local_currency_share", "当地货币收入占比", "本币收入占比"],
        "foreign_currency_debt_share": ["foreign_currency_debt_share", "foreign_currency_debt_ratio", "usd_debt_share", "外币债务占比", "外币负债占比"],
        "annual_profit_repatriation": ["annual_profit_repatriation", "profit_repatriation", "repatriation", "利润汇回", "利润汇出", "annual_repatriation"],
        "government_soe_revenue_exposure": ["government_soe_revenue_exposure", "government_revenue_exposure", "soe_revenue_exposure", "government_and_soe_public_sector_revenue", "政府国企收入暴露", "政府收入暴露", "国企收入暴露"],
        "project_staff_count": ["project_staff_count", "staff_count", "employee_count", "项目员工数", "员工人数", "岗位数"],
        "expected_operational_interruption_days": ["expected_operational_interruption_days", "operational_interruption_days", "days_outage", "停工天数", "运营中断天数", "outage_days"],
        "project_country_war_zone": ["project_country_war_zone", "war_zone", "warzone", "project_in_war_zone", "战争区", "战区"],
        "uninsured_asset_exposure": ["uninsured_asset_exposure", "uninsured_assets", "asset_loss_exposure", "未投保资产暴露", "未保险资产", " uninsured"],
        "import_equipment_fuel_exposure": ["import_equipment_fuel_exposure", "equipment_fuel_exposure", "import_exposure", "进口设备燃料暴露", "设备燃料依赖", "fuel_import_exposure"],
        "permits_licenses": ["permits_licenses", "permits", "licenses", "permit_license_status", "许可", "牌照", "审批"],
        "subsidies_tax_incentives": ["subsidies_tax_incentives", "tax_incentives", "subsidies", "补贴", "税收优惠", "减税"],
        "ppa_tariff_characteristics": ["ppa_tariff_characteristics", "ppa", "tariff", "购电协议", "电价", "tariff_characteristics", "ppa_characteristics"],
        "operating_loss": ["operating_loss", "loss", "净损失", "损失", "loss_amount"],
        "cash_flow_decline": ["cash_flow_decline", "cash_flow_drop", "经营现金流下降", "现金流下降"],
        "supply_chain_dependency": ["supply_chain_dependency", "supply_chain_exposure", "供应链依赖"],
        "site_security_risk": ["site_security_risk", "security_risk", "治安风险", "安保风险"],
        "local_community_acceptance": ["local_community_acceptance", "community_acceptance", "community_relation", "社区接受度"],
        "currency_exposure": ["currency_exposure", "fx_exposure", "外汇暴露"],
        "contract_enforcement": ["contract_enforcement", "enforcement_risk", "合同执行"],
        "asset_recovery": ["asset_recovery", "recovery_value", "资产回收"],
        "core_systems": ["core_systems", "key_systems", "核心系统"],
        "sensitive_data": ["sensitive_data", "data_sensitivity", "敏感数据"],
        "critical_assets": ["critical_assets", "key_assets", "核心资产"],
        "key_staff": ["key_staff", "critical_staff", "关键岗位"],
    }

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return ""
        return str(value).strip()

    @staticmethod
    def _normalize_key(value: Any) -> str:
        text = ImpactEngine._normalize_text(value).lower()
        text = text.replace("_", "").replace("-", "").replace(" ", "").replace("/", "")
        return text

    @staticmethod
    def _coerce_numeric(value: Any) -> Optional[float]:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            text = value.strip().replace(",", "").replace("%", "").replace("％", "")
            text = text.replace(" ", "").replace("≤", "<=").replace("≥", ">=")
            if text in {"", "n/a", "na", "nan", "-", "--"}:
                return None
            if text.endswith("%"):
                text = text[:-1]
            try:
                return float(text)
            except ValueError:
                return None
        return None

    @staticmethod
    def _resolve_metric_name(exposure: Dict[str, Any], canonical_name: str) -> Optional[str]:
        aliases = ImpactEngine._METRIC_ALIASES.get(canonical_name, [])
        alias_set = {ImpactEngine._normalize_key(a) for a in aliases}
        for candidate in exposure:
            if ImpactEngine._normalize_key(candidate) in alias_set:
                return candidate
        for candidate in exposure:
            key = ImpactEngine._normalize_key(candidate)
            for alias in alias_set:
                if alias in key or key in alias:
                    return candidate
        return None

    @staticmethod
    def _find_relevant_metric_names(formula: str, exposure: Dict[str, Any]) -> List[str]:
        if not formula:
            return []
        formula_key = ImpactEngine._normalize_key(formula)
        matches: List[str] = []
        for candidate in exposure:
            key = ImpactEngine._normalize_key(candidate)
            for canonical, aliases in ImpactEngine._METRIC_ALIASES.items():
                alias_set = {ImpactEngine._normalize_key(a) for a in aliases}
                if key in alias_set or any(alias in key for alias in alias_set):
                    if candidate not in matches:
                        matches.append(candidate)
                        break
            if candidate.lower() in formula_key or formula_key in candidate.lower():
                if candidate not in matches:
                    matches.append(candidate)

        # If formula names financial denominators instead of actual exposure property names, include the common metric keys that are available.
        if not matches:
            for candidate in exposure:
                metrics = [
                    "annual_revenue", "ebitda", "annual_distributable_cash_flow", "project_investment_amount", "total_assets",
                    "government_soe_revenue_exposure", "expected_operational_interruption_days", "uninsured_asset_exposure",
                    "local_currency_revenue_share", "foreign_currency_debt_share", "annual_profit_repatriation",
                ]
                if ImpactEngine._normalize_key(candidate) in {ImpactEngine._normalize_key(m) for m in metrics}:
                    matches.append(candidate)
        return matches

    @staticmethod
    def _parse_weight_terms(formula: str) -> Dict[str, float]:
        weights: Dict[str, float] = {}
        if not formula:
            return weights
        tokens = re.findall(r"(\d+(?:\.\d+)?)\s*%\s*([^+\-*/;，；]+)", formula)
        for value, label in tokens:
            label_key = ImpactEngine._normalize_key(label)
            weights[label_key] = float(value) / 100.0
        return weights

    @staticmethod
    def _resolve_risk_row(impact_rules_df: pd.DataFrame, risk_id: Any) -> pd.Series:
        risk_name = ImpactEngine._normalize_text(risk_id)
        for _, row in impact_rules_df.iterrows():
            name = ImpactEngine._normalize_text(row.get("三级风险"))
            if name.lower() == risk_name.lower():
                return row
        matches = impact_rules_df[impact_rules_df.iloc[:, 0].astype(str).str.lower().str.contains(risk_name.lower(), na=False)]
        if not matches.empty:
            return matches.iloc[0]
        raise ValueError(f"No impact rule row found for risk_id={risk_id}.")

    @staticmethod
    def _parse_floor_value(rule_text: str) -> Optional[int]:
        if not rule_text:
            return None
        text = ImpactEngine._normalize_text(rule_text)
        if "→5" in text or ">=5" in text or "I≥5" in text:
            return 5
        if "→I≥4" in text or "→4" in text or ">=4" in text or "I≥4" in text:
            return 4
        return None

    @staticmethod
    def _redline_triggered(rule_text: str, exposure: Dict[str, Any]) -> bool:
        if not rule_text:
            return False
        text = ImpactEngine._normalize_text(rule_text).lower()
        if "战争区" in text or "warzone" in text or "war_zone" in text or "战区" in text:
            for key, value in exposure.items():
                key_norm = ImpactEngine._normalize_key(key)
                if key_norm in {"projectcountrywarzone", "warzone", "warzoneproject", "war_zone", "projectinwarzone"}:
                    if isinstance(value, bool) and value:
                        return True
        if "核心运营中断" in text or "关键业务长期无法开展" in text or "关键运营" in text:
            value = exposure.get("expected_operational_interruption_days")
            if isinstance(value, (int, float)) and float(value) > 0:
                return True
        if "关键资产" in text or "核心资产" in text:
            asset_flag = exposure.get("critical_assets")
            if isinstance(asset_flag, bool) and asset_flag:
                return True
        if "核心系统" in text or "关键系统" in text:
            system_flag = exposure.get("core_systems")
            if isinstance(system_flag, bool) and system_flag:
                return True
        if "许可" in text or "审批" in text:
            permits_flag = exposure.get("permits_licenses")
            if isinstance(permits_flag, bool) and permits_flag:
                return True
        if "核心支付" in text or "关键支付" in text:
            payment_flag = exposure.get("annual_distributable_cash_flow")
            if isinstance(payment_flag, (int, float)) and float(payment_flag) <= 0:
                return True
        if any(token in text for token in ["核心", "重大", "无法", "失效", "撤销", "停止", "切断", "冻结"]):
            for key, value in exposure.items():
                if isinstance(value, bool) and value:
                    return True
        return False

    @staticmethod
    def _build_rule_table(rule_row: pd.Series) -> pd.DataFrame:
        impact_columns = ["Impact 1", "Impact 2", "Impact 3", "Impact 4", "Impact 5"]
        payload = {
            "risk_id": ImpactEngine._normalize_text(rule_row.get("三级风险")),
            "indicator_id": "impact_driver_metric",
            "signal_type": "Impact",
        }
        for score_idx, column in enumerate(impact_columns, start=1):
            payload[f"score_{score_idx}"] = rule_row.get(column)
        return pd.DataFrame([payload])

    @staticmethod
    def _score_metric_against_impact_band(risk_name: str, raw_value: Any, rule_row: pd.Series) -> ImpactContributor:
        if raw_value is None or raw_value == "":
            return ImpactContributor(
                metric_name="",
                raw_value=None,
                normalized_value=None,
                weight=0.0,
                score=None,
                matched_band=None,
                missing_data=True,
                rationale="Missing project exposure data: no numeric value available for this impact driver.",
            )

        table = ImpactEngine._build_rule_table(rule_row)
        result = IndicatorScoringEngine.score_indicator(
            risk_id=risk_name,
            indicator_id="impact_driver_metric",
            raw_value=raw_value,
            parameter_table=table,
            signal_type="Impact",
        )
        return ImpactContributor(
            metric_name="impact_driver_metric",
            raw_value=raw_value,
            normalized_value=ImpactEngine._coerce_numeric(raw_value),
            weight=1.0,
            score=result.standardized_score,
            matched_band=result.matched_band,
            missing_data=result.missing_data,
            rationale=result.scoring_rationale,
        )

    @staticmethod
    def _infer_metric_weights(formula: str, exposure: Dict[str, Any]) -> Dict[str, float]:
        weight_terms = ImpactEngine._parse_weight_terms(formula)
        if weight_terms:
            relevant = {}
            for metric_name in exposure:
                key = ImpactEngine._normalize_key(metric_name)
                for token_key, weight in weight_terms.items():
                    if token_key in key or key in token_key:
                        relevant[metric_name] = weight
            if relevant:
                return relevant

        relevant_metrics = ImpactEngine._find_relevant_metric_names(formula, exposure)
        if not relevant_metrics:
            return {}
        equal_weight = 1.0 / len(relevant_metrics)
        return {metric: equal_weight for metric in relevant_metrics}

    @staticmethod
    def _candidate_primary_metrics(risk_name: str, formula: str, exposure: Dict[str, Any], rule_row: pd.Series) -> List[ImpactContributor]:
        candidates: List[ImpactContributor] = []
        relevant = ImpactEngine._find_relevant_metric_names(formula, exposure)
        if not relevant:
            numeric_exposure = {
                key: value for key, value in exposure.items() if ImpactEngine._coerce_numeric(value) is not None and not isinstance(value, bool)
            }
            relevant = list(numeric_exposure.keys())
        for metric_name in relevant:
            value = exposure.get(metric_name)
            if value is None:
                continue
            numeric_value = ImpactEngine._coerce_numeric(value)
            if numeric_value is None and not isinstance(value, (str, bool)):
                continue
            score_item = ImpactEngine._score_metric_against_impact_band(risk_name, value, rule_row)
            score_item.metric_name = metric_name
            candidates.append(score_item)
        return candidates

    @staticmethod
    def _calculate_weighted_raw_score(contributors: List[ImpactContributor], weights: Dict[str, float]) -> Optional[float]:
        if not contributors:
            return None
        total_weight = 0.0
        score_sum = 0.0
        for contributor in contributors:
            if contributor.score is None:
                continue
            weight = weights.get(contributor.metric_name, contributor.weight)
            score_sum += weight * float(contributor.score)
            total_weight += weight
        if total_weight == 0:
            return None
        return score_sum / total_weight

    @staticmethod
    def _discrete_from_raw(raw_score: Optional[float]) -> Optional[int]:
        if raw_score is None:
            return None
        if raw_score < 1.5:
            return 1
        if raw_score < 2.5:
            return 2
        if raw_score < 3.5:
            return 3
        if raw_score < 4.5:
            return 4
        return 5

    @staticmethod
    def score_risk(
        risk_id: Any,
        project_exposure: Dict[str, Any],
        impact_rules_df: pd.DataFrame,
    ) -> ImpactResult:
        rule_row = ImpactEngine._resolve_risk_row(impact_rules_df, risk_id)
        risk_name = ImpactEngine._normalize_text(rule_row.get("三级风险"))
        driver_text = ImpactEngine._normalize_text(rule_row.get("Impact核心驱动因素"))
        formula_text = ImpactEngine._normalize_text(rule_row.get("计算方式/口径"))
        floor_rule = ImpactEngine._normalize_text(rule_row.get("红线/Floor规则"))

        relevant_weights = ImpactEngine._infer_metric_weights(formula_text, project_exposure)
        contributors = ImpactEngine._candidate_primary_metrics(risk_name, formula_text, project_exposure, rule_row)

        if not contributors:
            return ImpactResult(
                risk_id=str(risk_id),
                risk_name=risk_name,
                driver=driver_text,
                calculation=formula_text,
                raw_score=None,
                discrete_score=None,
                matched_band=None,
                floor_rule=floor_rule,
                applied_floor=None,
                missing_data=True,
                contributors=[],
                explanation="No project exposure inputs for this risk were available; missing-data flag set to true.",
            )

        valid_contributors = [c for c in contributors if c.score is not None]
        raw_score = ImpactEngine._calculate_weighted_raw_score(valid_contributors, relevant_weights) if valid_contributors else None
        discrete_score = ImpactEngine._discrete_from_raw(raw_score)
        applied_floor = None
        floor_value = ImpactEngine._parse_floor_value(floor_rule)
        redline_hit = floor_value is not None and ImpactEngine._redline_triggered(floor_rule, project_exposure)
        if redline_hit:
            applied_floor = floor_value
            if discrete_score is not None:
                discrete_score = max(discrete_score, floor_value)
            if raw_score is not None:
                raw_score = max(float(raw_score), float(floor_value))
            elif floor_value is not None:
                raw_score = float(floor_value)
        if discrete_score is None and raw_score is not None:
            discrete_score = 1 if raw_score < 1.5 else 2 if raw_score < 2.5 else 3 if raw_score < 3.5 else 4 if raw_score < 4.5 else 5
        if not valid_contributors and floor_value is not None and redline_hit:
            discrete_score = floor_value
            raw_score = float(floor_value)

        missing_data = not valid_contributors
        if missing_data and not redline_hit:
            discrete_score = None
            raw_score = None

        matched_band = None
        if contributors:
            best = max([c for c in contributors if c.score is not None], key=lambda c: c.score, default=None)
            if best is not None:
                matched_band = best.matched_band

        driver_summary = "; ".join(
            f"{c.metric_name}={c.score}/5 ({c.matched_band})" for c in contributors if c.score is not None
        )
        explanation = (
            f"Impact drivers: {driver_text or 'project exposure metrics'}; "
            f"weighted raw score {raw_score} mapped to discrete score {discrete_score}/5; "
            f"driver basis: {driver_summary or 'no matched driver scores'}; "
            f"formula: {formula_text or 'not specified'}."
        )
        if floor_value is not None and applied_floor is not None:
            explanation += f" Red-line floor triggered: {floor_rule}, applied floor {applied_floor}/5."

        return ImpactResult(
            risk_id=str(risk_id),
            risk_name=risk_name,
            driver=driver_text,
            calculation=formula_text,
            raw_score=raw_score,
            discrete_score=discrete_score,
            matched_band=matched_band,
            floor_rule=floor_rule,
            applied_floor=applied_floor,
            missing_data=missing_data,
            contributors=contributors,
            explanation=explanation,
        )

    @staticmethod
    def score_many(
        impact_rules_df: pd.DataFrame,
        exposure_by_risk: Dict[str, Dict[str, Any]],
    ) -> Dict[str, ImpactResult]:
        results: Dict[str, ImpactResult] = {}
        for risk_id, exposure in exposure_by_risk.items():
            results[risk_id] = ImpactEngine.score_risk(risk_id, exposure, impact_rules_df)
        return results
