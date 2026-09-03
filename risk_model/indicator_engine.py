from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Iterable, List, Optional

import pandas as pd


_SCORE_COLUMN_ALIASES = {
    1: ["score_1", "score1", "Score 1", "score 1", "Band 1", "band_1", "Band1"],
    2: ["score_2", "score2", "Score 2", "score 2", "Band 2", "band_2", "Band2"],
    3: ["score_3", "score3", "Score 3", "score 3", "Band 3", "band_3", "Band3"],
    4: ["score_4", "score4", "Score 4", "score 4", "Band 4", "band_4", "Band4"],
    5: ["score_5", "score5", "Score 5", "score 5", "Band 5", "band_5", "Band5"],
}


_RISK_ID_ALIASES = [
    "risk_id",
    "risk",
    "risk_name",
    "level_3_risk",
    "三级风险",
    "risk id",
]


_INDICATOR_ID_ALIASES = [
    "indicator_id",
    "indicator",
    "indicator_name",
    "feature_id",
    "level_indicator",
    "trend_indicator",
    "event_indicator",
    "Level指标/基础",
    "Trend指标",
    "Event指标",
]


_SIGNAL_TYPE_ALIASES = [
    "signal_type",
    "score_type",
    "dimension",
    "indicator_type",
    "type",
    "signal",
    "level",
    "trend",
    "event",
]


@dataclass
class ScoringBand:
    score: int
    label: str
    raw_condition: str
    lower_is_worse: bool = False


@dataclass
class ScoringResult:
    risk_id: str
    indicator_id: str
    signal_type: str
    raw_value: Any
    standardized_score: Optional[int]
    matched_band: Optional[str]
    scoring_rationale: str
    missing_data: bool


class IndicatorScoringEngine:
    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    @staticmethod
    def _normalize_key(value: Any) -> str:
        return IndicatorScoringEngine._normalize_text(value).lower().replace(" ", "")

    @staticmethod
    def _resolve_column(table: pd.DataFrame, aliases: Iterable[str], required: bool = True) -> Optional[str]:
        lower_map = {IndicatorScoringEngine._normalize_key(col): col for col in table.columns}
        for alias in aliases:
            match = lower_map.get(IndicatorScoringEngine._normalize_key(alias))
            if match is not None:
                return match
        if required:
            raise KeyError(f"Could not find required column; expected one of: {list(aliases)}")
        return None

    @staticmethod
    def _resolve_score_columns(table: pd.DataFrame) -> dict[int, str]:
        resolved: dict[int, str] = {}
        for score in range(1, 6):
            column = None
            for alias in _SCORE_COLUMN_ALIASES[score]:
                if alias in table.columns:
                    column = alias
                    break
            if column is None:
                for col in table.columns:
                    stripped = IndicatorScoringEngine._normalize_key(col)
                    if stripped in {IndicatorScoringEngine._normalize_key(a) for a in _SCORE_COLUMN_ALIASES[score]}:
                        column = col
                        break
            if column is not None:
                resolved[score] = column
        return resolved

    @staticmethod
    def _coerce_numeric(value: Any) -> Optional[float]:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            text = value.strip().replace(",", "").replace("%", "").replace("％", "")
            text = text.replace(" ", "")
            text = text.replace("≥", ">=").replace("≤", "<=")
            if text in {"", "-", "nan", "n/a", "na"}:
                return None
            try:
                return float(text)
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_numeric_band(raw_band: Any) -> Optional[dict]:
        text = IndicatorScoringEngine._normalize_text(raw_band)
        if not text:
            return None

        def parse_segment(segment: str) -> Optional[dict]:
            text_clean = segment.replace("%", "").replace("％", "")
            text_clean = text_clean.replace("–", "-").replace("—", "-")
            text_clean = text_clean.replace("至", "-").replace("到", "-")
            text_clean = text_clean.replace("以上", ">=").replace("以下", "<=")
            text_clean = text_clean.replace("不低于", ">=").replace("不高于", "<=")
            text_clean = text_clean.replace("以上", ">=").replace("以下", "<=")
            text_clean = re.sub(r"\s+", "", text_clean)

            if re.search(r"(?:<=|>=|<|>|≤|≥)", text_clean):
                nums = [float(num) for num in re.findall(r"[-+]?\d+(?:\.\d+)?", text_clean)]
                if not nums:
                    return None
                if len(nums) >= 2:
                    low = min(nums)
                    high = max(nums)
                    return {"op": "range", "low": low, "high": high}
                m = re.search(r"([<>]=?|[<>]|≤|≥)", text_clean)
                if m:
                    op = m.group(1).replace("≤", "<=").replace("≥", ">=")
                    return {"op": op, "value": nums[0]}

            range_match = re.fullmatch(r"(?P<left>[-+]?\d+(?:\.\d+)?)\s*(?P<sep>[-~]|至|到)\s*(?P<right>[-+]?\d+(?:\.\d+)?)", text_clean)
            if range_match:
                left = float(range_match.group("left"))
                right = float(range_match.group("right"))
                return {"op": "range", "low": min(left, right), "high": max(left, right)}

            if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text_clean):
                value = float(text_clean)
                return {"op": "eq", "value": value}

            if re.search(r"(无|none|n/a|na)", text_clean, flags=re.IGNORECASE):
                return {"op": "none"}

            return None

        for separator in ["或", "且", "and"]:
            if separator in text:
                for segment in re.split(rf"{separator}", text):
                    parsed = parse_segment(segment)
                    if parsed is not None:
                        return parsed
                break

        return parse_segment(text)

    @staticmethod
    def _band_matches_numeric(raw_value: float, band_text: Any, lower_is_worse: bool = False) -> bool:
        if raw_value is None:
            return False
        info = IndicatorScoringEngine._parse_numeric_band(band_text)
        if info is None:
            return False
        op = info.get("op")
        if op == "none":
            return False
        if op in {">", ">="}:
            return raw_value > info["value"] if op == ">" else raw_value >= info["value"]
        if op in {"<", "<="}:
            return raw_value < info["value"] if op == "<" else raw_value <= info["value"]
        if op == "range":
            low = info["low"]
            high = info["high"]
            return low <= raw_value <= high
        if op == "eq":
            return raw_value == info["value"]
        return False

    @staticmethod
    def _band_matches_categorical(raw_value: Any, band_text: Any) -> bool:
        raw_norm = IndicatorScoringEngine._normalize_text(raw_value).lower()
        band_norm = IndicatorScoringEngine._normalize_text(band_text).lower()
        if not raw_norm or not band_norm:
            return False
        if raw_norm == band_norm:
            return True
        if raw_norm in band_norm or band_norm in raw_norm:
            return True
        return False

    @staticmethod
    def _band_matches_binary(raw_value: Any, band_text: Any) -> bool:
        if raw_value is None:
            return False
        true_tokens = {"true", "yes", "y", "1", "on", "red", "hit", "triggered", "active", "严重", "发生", "存在"}
        false_tokens = {"false", "no", "n", "0", "off", "clear", "none", "未发生", "无"}
        raw_norm = IndicatorScoringEngine._normalize_text(raw_value).lower()
        band_norm = IndicatorScoringEngine._normalize_text(band_text).lower()
        if band_norm in true_tokens or band_norm in false_tokens:
            valid_bool = band_norm in true_tokens
            raw_bool = raw_norm in true_tokens
            return raw_bool == valid_bool
        return raw_norm == band_norm

    @staticmethod
    def _infer_lower_is_worse(row: pd.Series) -> bool:
        explicit = row.get("lower_is_worse")
        if explicit is not None:
            return str(explicit).strip().lower() in {"1", "true", "yes", "y", "lower_is_worse"}

        explicit_direction = row.get("risk_direction")
        if explicit_direction is not None:
            return str(explicit_direction).strip().lower() in {"low_is_worse", "lower_is_worse", "reverse", "inverse"}

        refs = []
        for score in range(1, 6):
            for alias in _SCORE_COLUMN_ALIASES[score]:
                if alias in row.index:
                    band = row.get(alias)
                    if band is None or (isinstance(band, float) and math.isnan(band)):
                        continue
                    parsed = IndicatorScoringEngine._parse_numeric_band(band)
                    if not parsed:
                        continue
                    op = parsed.get("op")
                    if op == "range":
                        refs.append((score, (parsed["low"] + parsed["high"]) / 2.0))
                    elif op in {">", ">=", "<", "<=", "eq"}:
                        refs.append((score, float(parsed["value"])))
                    break

        if len(refs) >= 2:
            values = [value for _, value in refs]
            if values == sorted(values, reverse=True):
                return True
            if values == sorted(values):
                return False
        return False

    @staticmethod
    def _infer_value_type(parameter_row: pd.Series, raw_value: Any, signal_type: Optional[str] = None) -> str:
        value_type = IndicatorScoringEngine._normalize_text(parameter_row.get("value_type") or parameter_row.get("valueType") or parameter_row.get("data_type") or parameter_row.get("datatype"))
        if value_type:
            return value_type.lower()

        if raw_value is not None:
            if IndicatorScoringEngine._coerce_numeric(raw_value) is not None:
                return "numeric"

        lower_signal = IndicatorScoringEngine._normalize_text(signal_type).lower()
        if isinstance(raw_value, bool):
            return "binary"

        if isinstance(raw_value, str):
            if any(token in raw_value for token in ["yes", "no", "true", "false", "是", "否", "存在", "无", "发生", "未发生"]):
                return "binary"

            if lower_signal in {"trend", "event"}:
                return "categorical"

            def looks_like_numeric_threshold(value: str) -> bool:
                text = IndicatorScoringEngine._normalize_text(value)
                if not text:
                    return False
                if re.search(r"^(?:[A-Za-z]+)?\s*(?:[<>]=?|[<>]|≤|≥)\s*[-+]?\d+(?:\.\d+)?$", text):
                    return True
                if re.search(r"^(?:[-+]?\d+(?:\.\d+)?)\s*(?:[-~]|至|到)\s*(?:[-+]?\d+(?:\.\d+)?)$", text):
                    return True
                if re.search(r"^(?:[A-Za-z]+)?\s*(?:<=|>=|<|>|≤|≥)\s*[-+]?\d+(?:\.\d+)?\s*(?:[-~]|至|到)\s*[-+]?\d+(?:\.\d+)?$", text):
                    return True
                return False

            if raw_value and looks_like_numeric_threshold(raw_value):
                return "numeric"
            text_to_scan = " ".join(
                [str(v) for v in parameter_row.tolist() if isinstance(v, str)]
            )
            if text_to_scan and any(looks_like_numeric_threshold(v) for v in parameter_row.tolist() if isinstance(v, str)):
                return "numeric"
            return "categorical"

        for _, val in parameter_row.items():
            if isinstance(val, str):
                if any(token in val for token in ["<", ">", "-", "至", "–", "≤", "≥"]):
                    return "numeric"
        if isinstance(raw_value, (bool, int)) and not isinstance(raw_value, bool):
            return "binary"
        return "categorical"

    @staticmethod
    def _find_matching_row(parameter_table: pd.DataFrame, risk_id: Any, indicator_id: Any, signal_type: Optional[str] = None) -> pd.Series:
        if parameter_table.empty:
            raise ValueError("Parameter table is empty.")

        table = parameter_table.copy()
        risk_col = IndicatorScoringEngine._resolve_column(table, _RISK_ID_ALIASES)
        indicator_col = IndicatorScoringEngine._resolve_column(table, _INDICATOR_ID_ALIASES)
        signal_col = IndicatorScoringEngine._resolve_column(table, _SIGNAL_TYPE_ALIASES, required=False)

        risk_key = IndicatorScoringEngine._normalize_key(risk_id)
        indicator_key = IndicatorScoringEngine._normalize_key(indicator_id)

        matches = table[
            table[risk_col].map(lambda x: IndicatorScoringEngine._normalize_key(x) == risk_key if x is not None else False)
        ]
        matches = matches[
            matches[indicator_col].map(lambda x: IndicatorScoringEngine._normalize_key(x) == indicator_key if x is not None else False)
        ]
        if signal_type is not None and signal_col is not None:
            signal_key = IndicatorScoringEngine._normalize_key(signal_type)
            matches = matches[
                matches[signal_col].map(lambda x: IndicatorScoringEngine._normalize_key(x) == signal_key if x is not None else False)
            ]

        if matches.empty and signal_type is not None and signal_col is not None:
            signal_key = IndicatorScoringEngine._normalize_key(signal_type)
            partial = table[
                table[risk_col].map(lambda x: IndicatorScoringEngine._normalize_key(x) == risk_key if x is not None else False)
            ]
            partial = partial[
                partial[indicator_col].map(lambda x: IndicatorScoringEngine._normalize_key(x) == indicator_key if x is not None else False)
            ]
            if not partial.empty:
                return partial.iloc[0]

        if matches.empty:
            raise ValueError(f"No parameter rule found for risk_id={risk_id}, indicator_id={indicator_id}, signal_type={signal_type}.")
        return matches.iloc[0]

    @staticmethod
    def _get_score_columns(row: pd.Series) -> dict[int, str]:
        candidates = {}
        for score in range(1, 6):
            for alias in _SCORE_COLUMN_ALIASES[score]:
                if alias in row.index:
                    candidates[score] = alias
                    break
            else:
                for idx_name in row.index:
                    if IndicatorScoringEngine._normalize_key(idx_name) == IndicatorScoringEngine._normalize_key(alias):
                        pass
        return candidates

    @staticmethod
    def _range_match(raw_value: Any, score_band: Any, value_type: str, lower_is_worse: bool = False) -> bool:
        if value_type in {"numeric", "number"}:
            num = IndicatorScoringEngine._coerce_numeric(raw_value)
            if num is None:
                return False
            return IndicatorScoringEngine._band_matches_numeric(num, score_band, lower_is_worse=lower_is_worse)
        if value_type == "binary":
            return IndicatorScoringEngine._band_matches_binary(raw_value, score_band)
        return IndicatorScoringEngine._band_matches_categorical(raw_value, score_band)

    @staticmethod
    def score_indicator(
        risk_id: Any,
        indicator_id: Any,
        raw_value: Any,
        parameter_table: pd.DataFrame,
        signal_type: Optional[str] = None,
    ) -> ScoringResult:
        if raw_value is None or (isinstance(raw_value, float) and math.isnan(raw_value)):
            return ScoringResult(
                risk_id=str(risk_id),
                indicator_id=str(indicator_id),
                signal_type=str(signal_type or ""),
                raw_value=None,
                standardized_score=None,
                matched_band=None,
                scoring_rationale="Missing data: raw value is null/NaN. Missing data flag set to true; no score assigned.",
                missing_data=True,
            )

        row = IndicatorScoringEngine._find_matching_row(parameter_table, risk_id, indicator_id, signal_type)
        score_columns = IndicatorScoringEngine._resolve_score_columns(row.to_frame().T)
        if not score_columns:
            raise ValueError(f"No scoring bands found for indicator {indicator_id} in risk {risk_id}.")

        signal_type_name = IndicatorScoringEngine._normalize_text(
            row.get("signal_type")
            or row.get("score_type")
            or row.get("dimension")
            or row.get("indicator_type")
            or row.get("type")
            or signal_type
            or "Level"
        )

        lower_is_worse = IndicatorScoringEngine._infer_lower_is_worse(row)
        value_type = IndicatorScoringEngine._infer_value_type(row, raw_value, signal_type=signal_type_name)
        candidates = []
        for score in range(1, 6):
            if score not in score_columns:
                continue
            band_text = row[score_columns[score]]
            if band_text is None or (isinstance(band_text, float) and math.isnan(band_text)):
                continue
            matches = IndicatorScoringEngine._range_match(raw_value, band_text, value_type, lower_is_worse=lower_is_worse)
            if matches:
                candidates.append((score, band_text))

        # Handle reverse-direction numeric definitions conservatively by ranking the matching score as the highest severity if the
        # parameter row explicitly marks lower values as higher risk.
        if lower_is_worse and not candidates and value_type in {"numeric", "number"}:
            numeric_value = IndicatorScoringEngine._coerce_numeric(raw_value)
            if numeric_value is not None:
                for score in range(5, 0, -1):
                    if score in score_columns:
                        band_text = row[score_columns[score]]
                        if IndicatorScoringEngine._band_matches_numeric(numeric_value, band_text, lower_is_worse=True):
                            candidates.append((score, band_text))

        if not candidates:
            return ScoringResult(
                risk_id=str(risk_id),
                indicator_id=str(indicator_id),
                signal_type=signal_type_name,
                raw_value=raw_value,
                standardized_score=None,
                matched_band=None,
                scoring_rationale=(
                    f"No scoring band matched raw value {raw_value!r} for {signal_type_name} indicator. "
                    f"Check the parameter row and threshold format."
                ),
                missing_data=False,
            )

        score, matched_band = max(candidates, key=lambda item: item[0])
        rationale = (
            f"Matched {signal_type_name} band '{matched_band}' to raw value {raw_value!r}; "
            f"assigned score {score}/5."
        )
        if lower_is_worse:
            rationale += " Lower values indicate higher risk; reverse-direction handling was applied."

        return ScoringResult(
            risk_id=str(risk_id),
            indicator_id=str(indicator_id),
            signal_type=signal_type_name,
            raw_value=raw_value,
            standardized_score=score,
            matched_band=str(matched_band),
            scoring_rationale=rationale,
            missing_data=False,
        )

    @staticmethod
    def score_many(
        parameter_table: pd.DataFrame,
        rows: Iterable[dict],
    ) -> List[ScoringResult]:
        results: List[ScoringResult] = []
        for row in rows:
            results.append(
                IndicatorScoringEngine.score_indicator(
                    risk_id=row["risk_id"],
                    indicator_id=row["indicator_id"],
                    raw_value=row["raw_value"],
                    parameter_table=parameter_table,
                    signal_type=row.get("signal_type"),
                )
            )
        return results
