from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence
import math
import re

import pandas as pd


@dataclass
class RiskRecord:
    family: str
    level_1: str
    level_2: str
    level_3: str
    risk_type: str
    override_rule: str = ""
    notes: str = ""


@dataclass
class ScoringRule:
    risk_family: str
    risk_name: str
    risk_type: str
    level_indicator: str
    level_scale: str
    score_1: str
    score_2: str
    score_3: str
    score_4: str
    score_5: str
    trend_indicator: str
    trend_1: str
    trend_2: str
    trend_3: str
    trend_4: str
    trend_5: str
    event_indicator: str
    event_1: str
    event_2: str
    event_3: str
    event_4: str
    event_5: str
    level_weight: float
    trend_weight: float
    event_weight: float
    likelihood_formula: str
    likelihood_mapping: str
    status: str


@dataclass
class ImpactRule:
    risk_name: str
    impact_driver: str
    calculation: str
    impact_1: str
    impact_2: str
    impact_3: str
    impact_4: str
    impact_5: str
    redline_rule: str
    denominator: str
    status: str


@dataclass
class WorkbookParameters:
    workbook_path: Path
    risk_model_df: pd.DataFrame
    scoring_rules_df: pd.DataFrame
    impact_rules_df: pd.DataFrame
    risk_matrix_df: pd.DataFrame
    risks: List[RiskRecord] = field(default_factory=list)
    scoring_rules: List[ScoringRule] = field(default_factory=list)
    impact_rules: List[ImpactRule] = field(default_factory=list)
    override_rules: List[str] = field(default_factory=list)
    validation_errors: List[str] = field(default_factory=list)

    @property
    def level_3_risk_count(self) -> int:
        return len(self.risks)

    @property
    def scoring_indicator_count(self) -> int:
        return len(self.scoring_rules)

    @property
    def impact_rule_count(self) -> int:
        return len(self.impact_rules)

    @property
    def override_rule_count(self) -> int:
        return len(self.override_rules)

    def validation_summary(self) -> dict:
        return {
            "level_3_risks": self.level_3_risk_count,
            "scoring_indicators": self.scoring_indicator_count,
            "impact_rules": self.impact_rule_count,
            "override_rules": self.override_rule_count,
            "validation_errors": self.validation_errors,
        }


class ParameterLoader:
    REQUIRED_SHEETS = [
        "国别风险模型",
        "评分规则及模型参数",
        "Impact评分规则",
        "Risk Matrix",
    ]

    @staticmethod
    def _normalize(value: object) -> str:
        if pd.isna(value):
            return ""
        return str(value).strip()

    @staticmethod
    def _find_header_row(df: pd.DataFrame, markers: Sequence[str]) -> int:
        for idx in range(len(df)):
            row_values = [ParameterLoader._normalize(v) for v in df.iloc[idx].tolist()]
            joined = " ".join(row_values)
            if any(marker.lower() in joined.lower() for marker in markers):
                return idx
        raise ValueError(f"Could not find header row containing markers: {markers}")

    @staticmethod
    def _parse_weight(value: object) -> float:
        text = ParameterLoader._normalize(value)
        if not text:
            return math.nan
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if text.endswith("%"):
            return float(text.rstrip("%")) / 100.0
        value_str = text.replace("%", "")
        if re.fullmatch(r"\d+(?:\.\d+)?", value_str):
            numeric = float(value_str)
            return numeric / 100.0 if numeric > 1 else numeric
        if re.fullmatch(r"\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?", value_str):
            numbers = re.findall(r"\d+(?:\.\d+)?", value_str)
            if len(numbers) >= 2:
                return (float(numbers[0]) + float(numbers[1])) / 200.0
        return math.nan

    @staticmethod
    def _column_index(header_values: Sequence[object], *candidates: str) -> int:
        normalized_candidates = {candidate.strip().lower() for candidate in candidates}
        for idx, value in enumerate(header_values):
            text = ParameterLoader._normalize(value).lower()
            if text in normalized_candidates:
                return idx
        for idx, value in enumerate(header_values):
            text = ParameterLoader._normalize(value).lower()
            if any(candidate.lower() in text for candidate in candidates):
                return idx
        raise KeyError(f"Could not find columns for: {candidates}, header={header_values}")

    def _load_raw_sheet(self, path: Path, sheet_name: str) -> pd.DataFrame:
        return pd.read_excel(path, sheet_name=sheet_name, header=None)

    def _parse_risk_model(self, df: pd.DataFrame) -> tuple[List[RiskRecord], List[str]]:
        header_row = self._find_header_row(df, ["三级风险", "风险场景"])
        headers = [ParameterLoader._normalize(v) for v in df.iloc[header_row].tolist()]

        family_idx = self._column_index(headers, "一级风险")
        level_2_idx = self._column_index(headers, "二级风险")
        level_3_idx = self._column_index(headers, "三级风险")
        type_idx = next((idx for idx, header in enumerate(headers) if header == "风险类型"), None)
        override_idx = self._column_index(headers, "红线/特殊规则")

        rows: List[RiskRecord] = []
        override_rules: List[str] = []

        for _, row in df.iloc[header_row + 1 :].iterrows():
            level_3_name = ParameterLoader._normalize(row.iloc[level_3_idx])
            if not level_3_name:
                continue

            family = ParameterLoader._normalize(row.iloc[family_idx])
            level_2 = ParameterLoader._normalize(row.iloc[level_2_idx])
            risk_type = ParameterLoader._normalize(row.iloc[type_idx]) if type_idx is not None and type_idx < len(row) else ""
            override_rule = ParameterLoader._normalize(row.iloc[override_idx]) if override_idx < len(row) else ""

            if override_rule:
                override_rules.append(override_rule)

            rows.append(
                RiskRecord(
                    family=family,
                    level_1=family,
                    level_2=level_2,
                    level_3=level_3_name,
                    risk_type=risk_type,
                    override_rule=override_rule,
                    notes="",
                )
            )

        return rows, override_rules

    def _parse_scoring_rules(self, df: pd.DataFrame) -> List[ScoringRule]:
        header_row = self._find_header_row(df, ["风险大类", "三级风险"])
        headers = [ParameterLoader._normalize(v) for v in df.iloc[header_row].tolist()]

        family_idx = self._column_index(headers, "风险大类")
        risk_name_idx = self._column_index(headers, "三级风险")
        risk_type_idx = self._column_index(headers, "风险类型")
        level_indicator_idx = self._column_index(headers, "Level指标/基础")
        level_scale_idx = self._column_index(headers, "Level口径")
        trend_indicator_idx = self._column_index(headers, "Trend指标")
        event_indicator_idx = self._column_index(headers, "Event指标")
        level_weight_idx = self._column_index(headers, "Level权重")
        trend_weight_idx = self._column_index(headers, "Trend权重")
        event_weight_idx = self._column_index(headers, "Event权重")
        formula_idx = self._column_index(headers, "Likelihood公式")
        mapping_idx = self._column_index(headers, "Likelihood等级映射")
        status_idx = self._column_index(headers, "参数状态")

        score_indices = {
            "Score 1": self._column_index(headers, "Score 1"),
            "Score 2": self._column_index(headers, "Score 2"),
            "Score 3": self._column_index(headers, "Score 3"),
            "Score 4": self._column_index(headers, "Score 4"),
            "Score 5": self._column_index(headers, "Score 5"),
        }
        trend_score_indices = {
            "Trend 1": self._column_index(headers, "Trend 1"),
            "Trend 2": self._column_index(headers, "Trend 2"),
            "Trend 3": self._column_index(headers, "Trend 3"),
            "Trend 4": self._column_index(headers, "Trend 4"),
            "Trend 5": self._column_index(headers, "Trend 5"),
        }
        event_score_indices = {
            "Event 1": self._column_index(headers, "Event 1"),
            "Event 2": self._column_index(headers, "Event 2"),
            "Event 3": self._column_index(headers, "Event 3"),
            "Event 4": self._column_index(headers, "Event 4"),
            "Event 5": self._column_index(headers, "Event 5"),
        }

        rules: List[ScoringRule] = []
        for _, row in df.iloc[header_row + 1 :].iterrows():
            risk_name = ParameterLoader._normalize(row.iloc[risk_name_idx])
            if not risk_name:
                continue

            def get_at(index: int) -> str:
                return ParameterLoader._normalize(row.iloc[index]) if index < len(row) else ""

            rule = ScoringRule(
                risk_family=get_at(family_idx),
                risk_name=risk_name,
                risk_type=get_at(risk_type_idx),
                level_indicator=get_at(level_indicator_idx),
                level_scale=get_at(level_scale_idx),
                score_1=get_at(score_indices["Score 1"]),
                score_2=get_at(score_indices["Score 2"]),
                score_3=get_at(score_indices["Score 3"]),
                score_4=get_at(score_indices["Score 4"]),
                score_5=get_at(score_indices["Score 5"]),
                trend_indicator=get_at(trend_indicator_idx),
                trend_1=get_at(trend_score_indices["Trend 1"]),
                trend_2=get_at(trend_score_indices["Trend 2"]),
                trend_3=get_at(trend_score_indices["Trend 3"]),
                trend_4=get_at(trend_score_indices["Trend 4"]),
                trend_5=get_at(trend_score_indices["Trend 5"]),
                event_indicator=get_at(event_indicator_idx),
                event_1=get_at(event_score_indices["Event 1"]),
                event_2=get_at(event_score_indices["Event 2"]),
                event_3=get_at(event_score_indices["Event 3"]),
                event_4=get_at(event_score_indices["Event 4"]),
                event_5=get_at(event_score_indices["Event 5"]),
                level_weight=self._parse_weight(get_at(level_weight_idx)),
                trend_weight=self._parse_weight(get_at(trend_weight_idx)),
                event_weight=self._parse_weight(get_at(event_weight_idx)),
                likelihood_formula=get_at(formula_idx),
                likelihood_mapping=get_at(mapping_idx),
                status=get_at(status_idx),
            )
            rules.append(rule)

        return rules

    def _parse_impact_rules(self, df: pd.DataFrame) -> List[ImpactRule]:
        header_row = self._find_header_row(df, ["Impact核心驱动因素", "三级风险"])
        headers = [ParameterLoader._normalize(v) for v in df.iloc[header_row].tolist()]

        risk_name_idx = self._column_index(headers, "三级风险")
        impact_driver_idx = self._column_index(headers, "Impact核心驱动因素")
        calculation_idx = self._column_index(headers, "计算方式/口径")
        redline_idx = self._column_index(headers, "红线/Floor规则")
        denominator_idx = self._column_index(headers, "建议统一分母")
        status_idx = self._column_index(headers, "参数状态")
        impact_indices = {
            "Impact 1": self._column_index(headers, "Impact 1"),
            "Impact 2": self._column_index(headers, "Impact 2"),
            "Impact 3": self._column_index(headers, "Impact 3"),
            "Impact 4": self._column_index(headers, "Impact 4"),
            "Impact 5": self._column_index(headers, "Impact 5"),
        }

        rules: List[ImpactRule] = []
        for _, row in df.iloc[header_row + 1 :].iterrows():
            risk_name = ParameterLoader._normalize(row.iloc[risk_name_idx])
            if not risk_name or risk_name.startswith("使用说明") or risk_name.startswith("说明"):
                continue

            def get_at(index: int) -> str:
                return ParameterLoader._normalize(row.iloc[index]) if index < len(row) else ""

            rule = ImpactRule(
                risk_name=risk_name,
                impact_driver=get_at(impact_driver_idx),
                calculation=get_at(calculation_idx),
                impact_1=get_at(impact_indices["Impact 1"]),
                impact_2=get_at(impact_indices["Impact 2"]),
                impact_3=get_at(impact_indices["Impact 3"]),
                impact_4=get_at(impact_indices["Impact 4"]),
                impact_5=get_at(impact_indices["Impact 5"]),
                redline_rule=get_at(redline_idx),
                denominator=get_at(denominator_idx),
                status=get_at(status_idx),
            )
            rules.append(rule)

        return rules

    def _parse_risk_matrix(self, df: pd.DataFrame) -> pd.DataFrame:
        header_row = self._find_header_row(df, ["Likelihood", "Impact"])
        data_rows: List[List[str]] = []
        for row_idx in range(header_row + 1, min(len(df), header_row + 10)):
            row = df.iloc[row_idx].tolist()
            if all(pd.isna(v) for v in row[:6]):
                continue
            first = ParameterLoader._normalize(row[0])
            if first not in {"5", "4", "3", "2", "1"}:
                continue
            data_rows.append([ParameterLoader._normalize(v) for v in row[:6]])

        if not data_rows:
            raise ValueError("Could not parse any rows from Risk Matrix sheet")

        if len(data_rows) < 5:
            raise ValueError("Risk Matrix must contain at least 5 likelihood rows")

        matrix = pd.DataFrame(data_rows)
        matrix = matrix.iloc[:, 1:6]
        matrix.columns = [1, 2, 3, 4, 5]
        matrix.index = [5, 4, 3, 2, 1]
        matrix = matrix.rename_axis("Likelihood")
        return matrix

    @staticmethod
    def validate_risks(risks: Iterable[RiskRecord]) -> List[str]:
        errors: List[str] = []
        seen: dict[str, int] = {}
        for risk in risks:
            seen_key = risk.level_3
            if seen_key:
                seen[seen_key] = seen.get(seen_key, 0) + 1
        for risk_name, count in seen.items():
            if count > 1:
                errors.append(f"Duplicated Level-3 risk: {risk_name}")
        if not seen:
            errors.append("No Level-3 risks parsed from workbook.")
        return errors

    @staticmethod
    def validate_scoring_rules(rules: Iterable[ScoringRule]) -> List[str]:
        errors: List[str] = []
        seen_indicators: dict[tuple[str, str, str, str], str] = {}
        rule_list = list(rules)
        for rule in rule_list:
            score_values = [rule.score_1, rule.score_2, rule.score_3, rule.score_4, rule.score_5]
            if any(not value for value in score_values):
                errors.append(f"Incomplete scoring thresholds for {rule.risk_name}: missing score band(s).")

            if math.isnan(rule.level_weight) or math.isnan(rule.trend_weight) or math.isnan(rule.event_weight):
                errors.append(f"Missing weight(s) for {rule.risk_name}.")
            else:
                total = rule.level_weight + rule.trend_weight + rule.event_weight
                if not math.isclose(total, 1.0, abs_tol=1e-6):
                    errors.append(f"Weights do not sum to 1.0 for {rule.risk_name}: {total}")

            if rule.level_weight > 0 and not rule.level_indicator:
                errors.append(f"Missing Level indicator for {rule.risk_name}.")
            if rule.trend_weight > 0 and not rule.trend_indicator:
                errors.append(f"Missing Trend indicator for {rule.risk_name}.")
            if rule.event_weight > 0 and not rule.event_indicator:
                errors.append(f"Missing Event indicator for {rule.risk_name}.")

            key = (rule.risk_name, rule.level_indicator, rule.trend_indicator, rule.event_indicator)
            if key in seen_indicators:
                errors.append(f"Duplicated scoring indicator for {rule.risk_name}.")
            else:
                seen_indicators[key] = rule.risk_name

        if not rule_list:
            errors.append("No scoring rules parsed from workbook.")
        return errors

    @staticmethod
    def validate_impact_rules(rules: Iterable[ImpactRule]) -> List[str]:
        errors: List[str] = []
        seen: set[str] = set()
        rule_list = list(rules)
        for rule in rule_list:
            risk_name = rule.risk_name
            if risk_name in seen:
                errors.append(f"Duplicated impact rule for {risk_name}.")
            seen.add(risk_name)

            score_values = [rule.impact_1, rule.impact_2, rule.impact_3, rule.impact_4, rule.impact_5]
            if any(not value for value in score_values):
                errors.append(f"Incomplete Impact scoring for {risk_name}.")
            if not rule.redline_rule:
                errors.append(f"Missing red-line/floor rule for {risk_name}.")
        if not rule_list:
            errors.append("No impact rules parsed from workbook.")
        return errors

    def load(self, workbook_path: str | Path) -> WorkbookParameters:
        workbook_file = Path(workbook_path)
        if not workbook_file.exists():
            raise FileNotFoundError(f"Workbook not found: {workbook_file}")

        raw_wb = pd.ExcelFile(workbook_file)
        missing_sheets = [sheet for sheet in self.REQUIRED_SHEETS if sheet not in raw_wb.sheet_names]
        if missing_sheets:
            raise ValueError(f"Workbook missing required sheets: {missing_sheets}")

        risk_model_df = self._load_raw_sheet(workbook_file, "国别风险模型")
        scoring_df = self._load_raw_sheet(workbook_file, "评分规则及模型参数")
        impact_df = self._load_raw_sheet(workbook_file, "Impact评分规则")
        risk_matrix_df = self._load_raw_sheet(workbook_file, "Risk Matrix")

        risks, override_rules = self._parse_risk_model(risk_model_df)
        scoring_rules = self._parse_scoring_rules(scoring_df)
        impact_rules = self._parse_impact_rules(impact_df)
        risk_matrix = self._parse_risk_matrix(risk_matrix_df)

        validation_errors = []
        validation_errors.extend(self.validate_risks(risks))
        validation_errors.extend(self.validate_scoring_rules(scoring_rules))
        validation_errors.extend(self.validate_impact_rules(impact_rules))

        return WorkbookParameters(
            workbook_path=workbook_file,
            risk_model_df=risk_model_df,
            scoring_rules_df=scoring_df,
            impact_rules_df=impact_df,
            risk_matrix_df=risk_matrix,
            risks=risks,
            scoring_rules=scoring_rules,
            impact_rules=impact_rules,
            override_rules=override_rules,
            validation_errors=validation_errors,
        )


def load_model_parameters(path: str | Path) -> WorkbookParameters:
    loader = ParameterLoader()
    return loader.load(path)
