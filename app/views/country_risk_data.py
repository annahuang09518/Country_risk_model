"""
Page 2: Country Risk Data (automated review dashboard).

For each Level-3 risk, this page shows the AUTO/MANUAL/MISSING status of the
Level/Trend/Event indicators driving Likelihood, populated automatically
from authoritative sources (World Bank, WGI, IMF) via
``app.services.country_data_orchestrator``. Non-automatable indicators
remain open for structured manual analyst input. Raw values are always
scored by the unmodified workbook-driven ``IndicatorScoringEngine`` /
``LikelihoodEngine`` - no scoring logic lives in this file.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional

import pandas as pd
import streamlit as st

from app.components.validation import workbook_scoring_frame
from app.services.country_data_orchestrator import (
    STATUS_AUTO,
    STATUS_MANUAL,
    STATUS_MISSING,
    CountryDataOrchestrator,
)
from risk_model import LikelihoodEngine
from src.country_reference import all_country_display_names, lookup_by_display_name, lookup_country

SIGNAL_LABELS = {"Level": "基础水平", "Trend": "趋势", "Event": "事件"}

STATUS_LABELS = {
    STATUS_AUTO: "自动",
    STATUS_MANUAL: "人工",
    STATUS_MISSING: "缺失",
}


def _as_float(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return text
    return value


@st.cache_data(show_spinner=False, ttl=3600)
def _run_automation(country_display_name: str, _params_signature: int):
    entry = lookup_by_display_name(country_display_name)
    if entry is None:
        return None
    orchestrator = CountryDataOrchestrator()
    return orchestrator.fetch_country_data(entry.iso3, st.session_state.parameters)


def render():
    st.header("国家风险数据")
    st.caption("系统自动从 世界银行 / WGI / IMF 等权威数据源获取国家层面 基础水平 / 趋势 / 事件 指标；无法自动获取的指标需分析师人工录入。")

    if "country_data" not in st.session_state:
        st.session_state.country_data = {}
    if "country_meta" not in st.session_state:
        st.session_state.country_meta = {}

    params = st.session_state.parameters
    if params is None:
        st.warning("模型参数尚未加载。")
        return

    country_names = all_country_display_names()
    current_country = st.session_state.assessment.get("country")
    default_index = None
    if current_country:
        current_entry = lookup_country(current_country)
        if current_entry:
            current_label = f"{current_entry.country_name_cn}（{current_entry.country_name_en}）"
            if current_label in country_names:
                default_index = country_names.index(current_label)

    col_country, col_refresh = st.columns([3, 1])
    with col_country:
        selected_country = st.selectbox(
            "国家 / 经济体",
            country_names,
            index=default_index,
            placeholder="请选择国家或经济体...",
            key="country_data_country_select",
        )
    with col_refresh:
        st.write("")
        st.write("")
        refresh_clicked = st.button("刷新国家数据", use_container_width=True)

    if not selected_country:
        st.info("请选择国家以自动获取国别风险数据。")
        return

    if refresh_clicked:
        _run_automation.clear()

    with st.spinner("正在获取自动化国家数据…"):
        summary = _run_automation(selected_country, len(params.risks))

    if summary is None:
        st.error("无法识别所选国家。")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("必需指标总数", summary.total_indicators)
    c2.metric("已自动获取", summary.automated_count)
    c3.metric("缺失/待人工录入", summary.missing_count)
    c4.metric("数据完整度", f"{summary.completeness_pct}%")

    st.divider()

    for risk in params.risks:
        rule = next((item for item in params.scoring_rules if item.risk_name == risk.level_3), None)
        if rule is None:
            continue
        risk_results = summary.results.get(risk.level_3, {})
        if not risk_results:
            continue

        statuses = [r.status for r in risk_results.values()]
        if STATUS_MISSING in statuses:
            badge = "[缺失]"
        elif STATUS_MANUAL in statuses:
            badge = "[需人工]"
        else:
            badge = "[已自动]"

        with st.expander(f"{badge} {risk.level_3}", expanded=False):
            current_values = st.session_state.country_data.setdefault(risk.level_3, {})
            meta = st.session_state.country_meta.setdefault(risk.level_3, {})

            for indicator_name, result in risk_results.items():
                row_meta = meta.setdefault(indicator_name, {})
                st.markdown(f"**{SIGNAL_LABELS.get(result.signal_type, result.signal_type)}：{indicator_name}** — {STATUS_LABELS.get(result.status, result.status)}")

                if result.status == STATUS_AUTO:
                    current_values[indicator_name] = result.raw_value
                    meta[indicator_name] = {
                        "value": result.raw_value,
                        "source": result.source_name,
                        "observation_date": result.observation_date,
                        "retrieved_at": result.retrieved_at,
                        "confidence": result.confidence,
                        "status": result.status,
                        "rationale": result.trend_rationale or result.scoring_rationale,
                    }
                    cols = st.columns(4)
                    cols[0].write(f"原始值: {result.raw_value}")
                    cols[1].write(f"来源: {result.source_name}")
                    cols[2].write(f"观测日期: {result.observation_date}")
                    cols[3].write(f"置信度: {result.confidence}")
                    if result.standardized_score is not None:
                        st.caption(f"评分: {result.standardized_score} | 匹配区间: {result.matched_band or '未命中'} | {result.scoring_rationale}")
                    if result.trend_rationale:
                        st.caption(result.trend_rationale)
                else:
                    c1, c2, c3, c4 = st.columns([2, 1.3, 1.2, 1.2])
                    with c1:
                        raw_value = st.text_input(
                            "分析师原始值",
                            value="" if row_meta.get("value") is None else str(row_meta.get("value")),
                            key=f"country_{risk.level_3}_{indicator_name}_value",
                        )
                    with c2:
                        source = st.text_input(
                            "证据来源",
                            value=row_meta.get("source", ""),
                            key=f"country_{risk.level_3}_{indicator_name}_source",
                        )
                    with c3:
                        stored_date = row_meta.get("observation_date")
                        if isinstance(stored_date, datetime):
                            date_value = stored_date.date()
                        elif isinstance(stored_date, date):
                            date_value = stored_date
                        elif isinstance(stored_date, str) and stored_date:
                            try:
                                date_value = datetime.fromisoformat(stored_date).date()
                            except ValueError:
                                date_value = date.today()
                        else:
                            date_value = date.today()
                        observation = st.date_input(
                            "观测日期",
                            value=date_value,
                            key=f"country_{risk.level_3}_{indicator_name}_date",
                        )
                    with c4:
                        confidence = st.selectbox(
                            "置信度",
                            ["High", "Medium", "Low"],
                            index=["High", "Medium", "Low"].index(row_meta.get("confidence", "Medium")),
                            format_func=lambda x: {"High":"高", "Medium":"中", "Low":"低"}.get(x, x),
                            key=f"country_{risk.level_3}_{indicator_name}_confidence",
                        )
                    note = st.text_input(
                        "分析师备注",
                        value=row_meta.get("note", ""),
                        key=f"country_{risk.level_3}_{indicator_name}_note",
                    )
                    parsed_value = _as_float(raw_value)
                    current_values[indicator_name] = parsed_value
                    meta[indicator_name] = {
                        "value": parsed_value,
                        "source": source,
                        "observation_date": str(observation),
                        "confidence": confidence,
                        "note": note,
                        "status": STATUS_MANUAL if parsed_value is not None else STATUS_MISSING,
                    }

            likelihood_result = LikelihoodEngine.score_risk(risk.level_3, current_values, workbook_scoring_frame(params))
            st.markdown("**发生可能性结果**")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("发生可能性原始分", "-" if likelihood_result.weighted_raw_score is None else round(likelihood_result.weighted_raw_score, 2))
            with col2:
                st.metric("发生可能性评分", "-" if likelihood_result.discrete_score is None else likelihood_result.discrete_score)
            with col3:
                st.metric("数据缺失", "是" if likelihood_result.missing_data else "否")
            if likelihood_result.top_contributing_indicators:
                st.write("主要驱动指标:")
                for c in likelihood_result.top_contributing_indicators:
                    st.write(f"- {c.indicator_id}：评分 {c.sub_score}（权重 {c.weight}）")

    st.divider()
    if st.button("进入下一步", use_container_width=True):
        st.session_state.results = "ready"
        st.success("国家风险数据已确认。若选择 国别 + 项目风险筛查，请前往「项目影响评估」；否则可直接查看仪表盘。")

