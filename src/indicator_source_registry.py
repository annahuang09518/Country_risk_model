"""Indicator-to-data-source registry.

This registry maps each Level-3 risk's workbook Level/Trend/Event indicator
to a concrete, verifiable data connector + series code, when (and only when)
a reliable authoritative source genuinely exists. It does not invent a
source where none exists - unmapped indicators are left for manual analyst
input, consistent with ``docs/country_data_automation_mapping.csv``.

This module contains NO scoring logic. It only describes *where* a raw
value can be automatically retrieved from; the raw value is always scored
by the unmodified ``risk_model.indicator_engine.IndicatorScoringEngine``
using the workbook's own bands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

AUTOMATION_FULLY_AUTOMATABLE = "A. FULLY_AUTOMATABLE"
AUTOMATION_SEMI_AUTOMATABLE = "B. SEMI_AUTOMATABLE"
AUTOMATION_MANUAL = "C. MANUAL"


@dataclass(frozen=True)
class IndicatorSourceMapping:
    risk_level_3: str
    signal_type: str  # "Level" | "Trend" | "Event"
    connector: str  # key into src.data_sources connector registry, or "" if manual
    series_code: str  # provider-specific series/indicator code
    automation_level: str
    trend_window_years: int = 3
    trend_method: str = "absolute_change"
    notes: str = ""


# Only the highest-confidence, verifiable mappings are declared here.
# These correspond to the user's priority list: Political Stability, War &
# Civil Conflict, Sovereign Credit, FX Reserve/Control, Inflation, Fiscal
# Risk, Sanctions, Foreign Investment Policy, Market Access, Tax Policy,
# Industry Regulation, Tariff Risk. Where the workbook's Level/Trend
# indicator is genuinely a macro/governance statistic with a known WB/WGI/
# IMF series code, it is wired below. Everything else remains manual/TBD.
INDICATOR_SOURCE_REGISTRY: list[IndicatorSourceMapping] = [
    # 政治稳定性风险 (Political Stability) - WGI Political Stability and Absence
    # of Violence/Terrorism percentile rank.
    IndicatorSourceMapping(
        risk_level_3="政治稳定性风险",
        signal_type="Level",
        connector="wgi",
        series_code="GOV_WGI_PV.SC",
        automation_level=AUTOMATION_FULLY_AUTOMATABLE,
        notes="World Bank WGI Political Stability and Absence of Violence percentile rank.",
    ),
    IndicatorSourceMapping(
        risk_level_3="政治稳定性风险",
        signal_type="Trend",
        connector="wgi",
        series_code="GOV_WGI_PV.SC",
        automation_level=AUTOMATION_FULLY_AUTOMATABLE,
        trend_window_years=3,
        trend_method="absolute_change",
        notes="3-year change in WGI Political Stability percentile rank.",
    ),
    # 国家治理能力风险 (Governance capacity) - WGI Government Effectiveness.
    IndicatorSourceMapping(
        risk_level_3="国家治理能力风险",
        signal_type="Level",
        connector="wgi",
        series_code="GOV_WGI_GE.SC",
        automation_level=AUTOMATION_FULLY_AUTOMATABLE,
        notes="World Bank WGI Government Effectiveness percentile rank.",
    ),
    # 政府腐败风险 (Government corruption) - WGI Control of Corruption.
    IndicatorSourceMapping(
        risk_level_3="政府腐败风险",
        signal_type="Level",
        connector="wgi",
        series_code="GOV_WGI_CC.SC",
        automation_level=AUTOMATION_FULLY_AUTOMATABLE,
        notes="World Bank WGI Control of Corruption percentile rank.",
    ),
    # 法律环境风险 (Legal environment) - WGI Rule of Law.
    IndicatorSourceMapping(
        risk_level_3="法律环境风险",
        signal_type="Level",
        connector="wgi",
        series_code="GOV_WGI_RL.SC",
        automation_level=AUTOMATION_FULLY_AUTOMATABLE,
        notes="World Bank WGI Rule of Law percentile rank.",
    ),
    # 通货膨胀风险 (Inflation) - World Bank CPI inflation, annual %.
    IndicatorSourceMapping(
        risk_level_3="通货膨胀风险",
        signal_type="Level",
        connector="world_bank",
        series_code="FP.CPI.TOTL.ZG",
        automation_level=AUTOMATION_FULLY_AUTOMATABLE,
        notes="World Bank CPI inflation, annual % (consumer prices).",
    ),
    IndicatorSourceMapping(
        risk_level_3="通货膨胀风险",
        signal_type="Trend",
        connector="world_bank",
        series_code="FP.CPI.TOTL.ZG",
        automation_level=AUTOMATION_FULLY_AUTOMATABLE,
        trend_window_years=3,
        trend_method="absolute_change",
        notes="3-year change in CPI inflation rate.",
    ),
    # 宏观经济增长风险 (Macro growth) - World Bank GDP growth, annual %.
    IndicatorSourceMapping(
        risk_level_3="宏观经济增长风险",
        signal_type="Level",
        connector="world_bank",
        series_code="NY.GDP.MKTP.KD.ZG",
        automation_level=AUTOMATION_FULLY_AUTOMATABLE,
        notes="World Bank GDP growth, annual %.",
    ),
    IndicatorSourceMapping(
        risk_level_3="宏观经济增长风险",
        signal_type="Trend",
        connector="world_bank",
        series_code="NY.GDP.MKTP.KD.ZG",
        automation_level=AUTOMATION_FULLY_AUTOMATABLE,
        trend_window_years=3,
        trend_method="absolute_change",
        notes="3-year change in GDP growth rate.",
    ),
    # 政府财政风险 (Fiscal risk) - IMF general government net lending/borrowing (% GDP).
    IndicatorSourceMapping(
        risk_level_3="政府财政风险",
        signal_type="Level",
        connector="imf",
        series_code="GGXCNL_NGDP",
        automation_level=AUTOMATION_FULLY_AUTOMATABLE,
        notes="IMF WEO general government net lending/borrowing, % of GDP.",
    ),
    IndicatorSourceMapping(
        risk_level_3="政府财政风险",
        signal_type="Trend",
        connector="imf",
        series_code="GGXCNL_NGDP",
        automation_level=AUTOMATION_FULLY_AUTOMATABLE,
        trend_window_years=3,
        trend_method="absolute_change",
        notes="3-year change in fiscal balance % of GDP.",
    ),
    # 外汇储备风险 (FX reserves) - World Bank total reserves in months of imports.
    IndicatorSourceMapping(
        risk_level_3="外汇储备风险",
        signal_type="Level",
        connector="world_bank",
        series_code="FI.RES.TOTL.MO",
        automation_level=AUTOMATION_FULLY_AUTOMATABLE,
        notes="World Bank total reserves in months of imports.",
    ),
    IndicatorSourceMapping(
        risk_level_3="外汇储备风险",
        signal_type="Trend",
        connector="world_bank",
        series_code="FI.RES.TOTL.MO",
        automation_level=AUTOMATION_FULLY_AUTOMATABLE,
        trend_window_years=3,
        trend_method="absolute_change",
        notes="3-year change in reserve cover (months of imports).",
    ),
    # 外汇管制风险 (FX control) - World Bank official exchange rate volatility
    # is not a direct proxy for controls; leaving Level/Trend manual, but the
    # Event signal (e.g. announced FX restriction actions) can leverage the
    # same World Bank exchange-rate series for a supporting data point.
    IndicatorSourceMapping(
        risk_level_3="外汇管制风险",
        signal_type="Level",
        connector="world_bank",
        series_code="PA.NUS.FCRF",
        automation_level=AUTOMATION_SEMI_AUTOMATABLE,
        notes=(
            "World Bank official exchange rate (LCU per USD) is a supporting "
            "data point only; actual FX control classification requires "
            "analyst review of capital-account restriction announcements."
        ),
    ),
    # 主权信用风险 (Sovereign credit) - no free, redistribution-clear API
    # exists for rating-agency scores; IMF external debt % GNI is used as a
    # supporting Level proxy only, consistent with docs/country_data_automation_mapping.csv
    # noting rating-agency data as manual/licensing-restricted.
    IndicatorSourceMapping(
        risk_level_3="主权信用风险",
        signal_type="Level",
        connector="world_bank",
        series_code="DT.DOD.DECT.GN.ZS",
        automation_level=AUTOMATION_SEMI_AUTOMATABLE,
        notes=(
            "World Bank external debt stocks, % of GNI, used as a supporting "
            "proxy only. Sovereign rating agency scores (Moody's/S&P/Fitch) "
            "require commercial licensing and remain manual analyst input."
        ),
    ),
]


def find_mapping(risk_level_3: str, signal_type: str) -> Optional[IndicatorSourceMapping]:
    for mapping in INDICATOR_SOURCE_REGISTRY:
        if mapping.risk_level_3 == risk_level_3 and mapping.signal_type == signal_type:
            return mapping
    return None


def mappings_for_risk(risk_level_3: str) -> list[IndicatorSourceMapping]:
    return [m for m in INDICATOR_SOURCE_REGISTRY if m.risk_level_3 == risk_level_3]
